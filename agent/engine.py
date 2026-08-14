"""Agent核心引擎 - ReAct循环 + 知识库增强 + Skills指导 + 学习闭环 + 变更审批流"""
import json
import uuid
import re
import time
import threading
from typing import Dict, List, Optional, Generator, Tuple
from datetime import datetime, timedelta

from db.database import get_db
from utils import call_llm
from rag.embedder import Embedder
from agent.harness import Harness, OperationLevel
from agent.skills import SkillManager
from agent.state import AgentState, AgentPhase, AgentStatus
from agent.tools import get_tool_schemas, execute_tool, ToolContext


class SmartOpsAgent:
    """智能运维Agent（第三代 - 自主决策模式）"""

    # 知识库检索阈值（与 routes/qa.py 对齐，分块 500 后实测上调）
    MIN_SIMILARITY_THRESHOLD = 0.75
    MIN_KNOWLEDGE_COVERAGE = 0.80

    # 可并行执行的只读工具白名单（无副作用，并行线程安全）
    PARALLEL_SAFE_TOOLS = {
        'query_database', 'get_schema_info', 'get_performance_metrics',
        'get_monitor_metrics', 'retrieve_check', 'retrieve_knowledge',
    }
    PARALLEL_MAX_WORKERS = 4
    MAX_PARALLEL_CALLS = 5

    # 上下文压缩：对话历史超过该条数触发中间摘要，保留头尾逐字
    HISTORY_COMPRESS_THRESHOLD = 10
    HISTORY_KEEP_TAIL = 6
    HISTORY_SUMMARY_MAX_CHARS = 1500

    def __init__(self, session_id: str, ssh_conn_id: Optional[str] = None,
                 db_conn_id: Optional[str] = None, model_id: Optional[str] = None):
        self.session_id = session_id
        self.ssh_conn_id = ssh_conn_id
        self.db_conn_id = db_conn_id
        self.model_id = model_id
        self.embedder = Embedder()
        self.skill_manager = SkillManager()
        self.harness = Harness()
        from config import AGENT_MAX_STEPS, AGENT_MAX_HISTORY_CHARS
        self.state = AgentState(session_id, max_steps=int(AGENT_MAX_STEPS))
        self.max_history_chars = int(AGENT_MAX_HISTORY_CHARS)

        # 最近动作指纹（死循环检测）
        self._recent_actions = []

        # 操作级别（默认只读）
        self.operation_level = OperationLevel.READONLY

    def run_stream(self, user_question: str) -> Generator[Dict, None, None]:
        """ReAct主循环（流式输出），带状态持久化与异常兜底"""
        self.state.set_status(AgentStatus.RUNNING)
        self._persist_session(AgentStatus.RUNNING)
        try:
            yield from self._react_loop(user_question)
        except Exception as e:
            self.state.set_error(str(e))
            self._persist_session(AgentStatus.ERROR)
            raise

    def _react_loop(self, user_question: str) -> Generator[Dict, None, None]:
        """ReAct 主循环体（生成器）：检索 → 决策 → 执行 → 观察 → 总结"""
        # 1. 检索知识库（自动）
        yield {"type": "retrieving_start", "message": "正在检索知识库..."}
        knowledge_result = self._retrieve_knowledge_strict(user_question)

        if knowledge_result['status'] == 'insufficient':
            # 知识库不足，发出警告但仍继续
            yield {
                "type": "knowledge_warning",
                "message": knowledge_result['message'],
                "refs": knowledge_result.get('results', [])
            }
        else:
            yield {
                "type": "knowledge_refs",
                "refs": knowledge_result['results']
            }

        knowledge_refs = knowledge_result['results']
        chunk_ids = knowledge_result.get('chunk_ids', [])

        # 2. 匹配Skills
        matched_skills = self.skill_manager.match_skills_by_intent(
            user_question, self._get_db_type()
        )

        # 2.5 长期记忆召回（环境上下文）
        memory_refs = self._recall_memory(user_question)

        # 3. 构建system prompt（注入知识库 + 知识图谱 + Skills + 环境上下文）
        kg_context = self._retrieve_kg_context(user_question, chunk_ids) if chunk_ids else None
        system_prompt = self._build_system_prompt(knowledge_refs, matched_skills, kg_context, memory_refs)

        # 4. ReAct循环
        # 用户问题作为对话起点；每步的思考与观察结果通过 add_message 回流，
        # 使模型能基于上一轮工具结果继续推理（链式 ReAct）。
        self.state.add_message('user', user_question)

        while self.state.current_step < self.state.max_steps:
            # 迭代预算：对话历史字符超限 → 强制收敛
            if self._history_chars() > self.max_history_chars:
                yield {"type": "executing_warning",
                       "warning": "⚠️ 对话历史过长，停止继续执行，直接给出结论"}
                break

            # Thinking
            yield {"type": "thinking_start", "step": self.state.current_step}
            thought = self._think(system_prompt)
            yield {"type": "thinking_chunk", "content": thought}
            yield {"type": "thinking_end"}

            step = self.state.add_step(AgentPhase.THINKING, thought=thought,
                                       knowledge_refs=knowledge_refs)
            self._persist_step(step)
            self.state.add_message('assistant', thought)

            # Decision: 提取工具调用（支持一次多个，只读工具并行执行）
            actions = self._extract_tool_calls(thought, max_calls=self.MAX_PARALLEL_CALLS)
            if not actions:
                break

            # 死循环检测：连续相同动作指纹 ≥3 次 → 强制收敛
            self._recent_actions.append(self._action_fingerprint(actions))
            if (len(self._recent_actions) >= 3
                    and len(set(self._recent_actions[-3:])) == 1):
                yield {"type": "executing_warning",
                       "warning": "⚠️ 检测到重复执行相同操作，停止继续，直接给出结论"}
                self.state.add_message('user', "⚠️ 检测到重复执行相同操作，请直接给出结论，不要再调用工具")
                break

            # 变更类：识别操作计划 → 审批暂停 → 获批执行 / 拒绝继续 / 超时收尾
            plan_obj = next((a.get('plan') for a in actions if a.get('type') == 'plan'), None)
            if plan_obj:
                plan_result = yield from self._handle_plan_approval(plan_obj)
                if plan_result == 'expired':
                    break
                # 获批执行（计划操作已记步骤）或拒绝后，本轮不执行其他工具，进入下一轮思考
                continue

            # Planning
            if len(actions) == 1:
                yield {"type": "planning", "action": actions[0]}
            else:
                yield {"type": "planning", "action": {"tool": "parallel",
                                                      "actions": actions}}

            # Execution：按三态分类处理（safe 直接执行 / approval 转审批 / reject 拒绝）
            safe_actions = []
            approval_actions = []
            rejected_actions = []
            for action in actions:
                cls, reason = self._classify_action(action)
                if cls == 'safe':
                    safe_actions.append(action)
                elif cls == 'approval':
                    approval_actions.append((action, reason))
                else:
                    rejected_actions.append((action, reason))

            # 1) reject：命令注入等硬拒绝（安全底线）
            for action, reason in rejected_actions:
                observation = f"❌ 安全校验拒绝: {reason}"
                yield {"type": "executing_error", "error": observation}
                step = self.state.add_step(AgentPhase.EXECUTING, action=action,
                                           observation=observation)
                self._persist_step(step)
                yield {"type": "observing", "observation": observation}
                self.state.add_message('user', f"观察结果:\n{observation}")

            # 2) approval：自动生成审批计划，等待 DBA 决定（不再硬拒绝）
            expired = False
            for action, reason in approval_actions:
                plan = self._build_approval_plan(action, reason)
                plan_result = yield from self._handle_plan_approval(plan)
                if plan_result == 'expired':
                    expired = True
                    break
            if expired:
                break

            # 3) safe：只读操作直接执行
            if safe_actions:
                results = self._execute_actions(safe_actions, knowledge_refs)
                for item in results:
                    action = item['action']
                    if not item['is_safe']:
                        yield {"type": "executing_error", "error": item['observation']}
                    else:
                        if item['warning']:
                            yield {"type": "executing_warning", "warning": item['warning']}
                        yield {"type": "executing_end", "result": item['result']}

                    step = self.state.add_step(AgentPhase.EXECUTING, action=action,
                                               observation=item['observation'])
                    self._persist_step(step)

                    # Observation
                    yield {"type": "observing", "observation": item['observation']}

                    # 观察结果回流对话历史
                    self.state.add_message('user', f"观察结果:\n{item['observation']}")

            self.state.next_step()

        # Conclusion
        yield {"type": "concluding_start"}
        conclusion = self._conclude(knowledge_refs)
        yield {"type": "concluding_chunk", "content": conclusion}
        yield {"type": "concluding_end"}

        step = self.state.add_step(AgentPhase.CONCLUDING, thought=conclusion)
        self._persist_step(step)
        self.state.set_status(AgentStatus.COMPLETED)
        self._persist_session(AgentStatus.COMPLETED)

        # 学习闭环：成功诊断 → 后台沉淀技能 + 写长期记忆（不阻塞流式返回）
        threading.Thread(
            target=self._crystallize_after_success,
            args=(user_question, conclusion, knowledge_refs),
            daemon=True,
        ).start()

        yield {"type": "done"}

    def _retrieve_knowledge_strict(self, query: str, top_k: int = 5) -> Dict:
        """严格检索知识库（带阈值控制）"""
        db_type = self._get_db_type()

        # 1. 向量检索
        results = self.embedder.similarity_search(query, db_type=db_type, top_k=top_k)

        # 2. 过滤低相似度结果
        filtered_results = [r for r in results if r.get('similarity', 0) >= self.MIN_SIMILARITY_THRESHOLD]

        # 3. 检查知识覆盖率
        chunk_ids = [r.get('chunk_id') for r in filtered_results if r.get('chunk_id')]

        if not filtered_results:
            return {
                'status': 'insufficient',
                'message': f'知识库中未找到相似度≥{self.MIN_SIMILARITY_THRESHOLD}的相关文档',
                'results': [],
                'chunk_ids': []
            }

        max_similarity = max(r.get('similarity', 0) for r in filtered_results)
        if max_similarity < self.MIN_KNOWLEDGE_COVERAGE:
            return {
                'status': 'insufficient',
                'message': f'知识库相似度过低（最高: {max_similarity:.2f}），无法确认操作正确性',
                'results': self._format_knowledge_refs(filtered_results),
                'chunk_ids': chunk_ids
            }

        return {
            'status': 'sufficient',
            'results': self._format_knowledge_refs(filtered_results),
            'chunk_ids': chunk_ids
        }

    def _retrieve_kg_context(self, query: str, chunk_ids: List[int]) -> Optional[Dict]:
        """基于检索到的 chunk 获取知识图谱上下文（实体卡片/关系链）"""
        try:
            from kg.graph import enhance_qa_context
            return enhance_qa_context(chunk_ids, query)
        except Exception as e:
            print(f"[Agent] 知识图谱上下文检索失败: {e}")
            return None

    def _format_knowledge_refs(self, results: List[Dict]) -> List[Dict]:
        """格式化知识库引用"""
        refs = []
        for r in results:
            refs.append({
                'file': r.get('filename', '未知'),
                'chunk': r.get('chunk_text', '')[:200],
                'similarity': round(r.get('similarity', 0), 3)
            })
        return refs

    def _build_system_prompt(self, knowledge_refs: List[Dict],
                            skills: List[Dict],
                            kg_context: Optional[Dict] = None,
                            memory_refs: Optional[List[Dict]] = None) -> str:
        """构建system prompt（注入知识库 + 知识图谱 + Skills）"""
        prompt = """你是一个智能数据库运维Agent。你的任务是根据用户的指令，自主分析、自主决策、自主执行数据库运维任务。

## 核心原则
1. **知识库优先**：你只能基于检索到的知识库内容回答问题
2. **禁止编造**：如果知识库中没有相关信息，你必须明确回答"知识库中没有相关信息，无法确认该参数/命令的正确性"
3. **置信度标注**：每个回答必须标注置信度：
   - 🟢 高置信度：完全基于知识库原文
   - 🟡 中置信度：部分基于知识库，部分推断
   - 🔴 低置信度：基于模型一般知识，可能存在错误
4. **操作确认**：涉及任何操作时，必须列出知识库引用来源
5. **只读原则**：所有操作必须是只读的，禁止修改数据

## 可用工具
- query_database: 执行SQL查询（只读）
- execute_command: 通过SSH执行数据库命令
- get_schema_info: 获取数据库Schema信息
- get_performance_metrics: 获取性能指标
- get_monitor_metrics: 查询外部监控平台落库的监控指标（蓝鲸等，CPU/内存/磁盘等）
- retrieve_check: 检索运维检查项（专家检查知识库，含 SQL/命令/建议）

## 工作模式（ReAct）
1. Thought: 分析用户需求，制定执行计划
2. Action: 调用合适的工具获取数据（格式: {"tool": "xxx", "parameters": {...}}）
3. Observation: 观察执行结果
4. Thought: 基于结果继续分析或总结

## 变更类操作（需审批）
涉及修改参数/配置/执行变更命令（如 ALTER SYSTEM SET、SET GLOBAL、srvctl start/stop）属于**变更类**。
- 变更类操作必须先输出**操作计划**等待 DBA 审批，格式：
```json
{"type": "plan", "plan": {"title": "计划标题", "scope": "影响范围", "operations": [{"tool": "query_database", "parameters": {"sql": "ALTER SYSTEM SET ..."}, "impact": "影响说明", "risk": "high/medium/low"}], "rollback": "回滚方法"}}
```
- 审批通过后引擎按计划执行；执行中遇问题请用只读工具自行分析探索，再追加新的操作计划等待审批，直至任务完成。
- 不得直接调用工具执行变更 SQL/命令（会被安全校验拦截）。

## 输出格式
当你需要调用工具时，请使用以下JSON格式：
```json
{"tool": "query_database", "parameters": {"sql": "SELECT ..."}}
```

如果需要同时查多个只读指标/对象，可以一次输出多个工具调用（JSON数组），它们会被并行执行：
```json
[{"tool": "get_monitor_metrics", "parameters": {"metric_type": "cpu_usage"}},
 {"tool": "query_database", "parameters": {"sql": "SELECT ..."}}]
```
注意：仅只读工具（query_database/get_schema_info/get_performance_metrics/get_monitor_metrics/retrieve_check/retrieve_knowledge）可并行；execute_command 涉及命令执行，请逐个调用。

如果不需要工具，直接给出分析结论。
"""

        # 注入知识库引用
        if knowledge_refs:
            prompt += "\n## 参考知识库文档\n"
            for i, ref in enumerate(knowledge_refs, 1):
                prompt += f"[{i}] {ref['file']} (相似度: {ref['similarity']})\n"
                prompt += f"{ref['chunk']}\n\n"

        # 注入Skills（自动沉淀技能全文注入，最多 2 个；内置技能 200 字预览）
        if skills:
            prompt += "\n## 适用技能\n"
            auto_injected = 0
            for skill in skills:
                prompt += f"- {skill['name']}: {skill['description']}\n"
                template = skill.get('prompt_template') or ''
                is_auto = skill.get('usage_count') is not None  # DB 自动沉淀技能
                if is_auto:
                    try:
                        from db.database import bump_skill_usage
                        bump_skill_usage(skill['name'])
                    except Exception:
                        pass
                    if template and auto_injected < 2:
                        prompt += f"  操作指南:\n{template}\n"
                        auto_injected += 1
                    elif template:
                        prompt += f"  操作指南: {template[:200]}...\n"
                elif template:
                    prompt += f"  操作指南: {template[:200]}...\n"

        # 注入长期记忆（环境上下文，含图谱补充）
        if memory_refs:
            prompt += "\n## 环境上下文（历史记录，供参考）\n"
            for mem in memory_refs[:8]:
                entity = mem.get('entity_name') or '通用'
                prompt += f"- [{mem.get('entity_type', 'general')}:{entity}] {mem.get('fact', '')[:150]}\n"
                if mem.get('graph_context'):
                    prompt += f"  {mem['graph_context']}\n"
                if (mem.get('confidence') or 1) < 0.7:
                    prompt += "  （低置信度，需现场验证）\n"

        # 注入知识图谱上下文
        if kg_context:
            cards = kg_context.get('entity_cards') or []
            chains = kg_context.get('relation_chains') or []
            if cards or chains:
                prompt += "\n## 知识图谱上下文\n"
                if cards:
                    prompt += "相关实体：\n"
                    for card in cards[:10]:
                        prompt += f"- {card['name']} ({card['type']})"
                        if card.get('description'):
                            prompt += f": {card['description'][:100]}"
                        prompt += "\n"
                        if card.get('relations'):
                            rels = ", ".join(
                                f"{r['relation_type']}→{r['target_name']}"
                                for r in card['relations'][:5] if r.get('target_name')
                            )
                            if rels:
                                prompt += f"  关系: {rels}\n"
                if chains:
                    prompt += "\n实体间路径：\n"
                    for chain in chains[:5]:
                        names = [n.get('name', '') for n in chain.get('path', [])
                                 if isinstance(n, dict) and n.get('name')]
                        if names:
                            prompt += " -> ".join(names) + "\n"

        return prompt

    def _think(self, system_prompt: str) -> str:
        """LLM思考（基于对话历史，过长时自动压缩中间步骤）"""
        messages = self._build_messages(system_prompt)

        response, _ = call_llm(messages, model_id=self.model_id)
        return response

    def _build_messages(self, system_prompt: str) -> List[Dict]:
        """构造 LLM 消息列表：对话历史过长时做头尾保护 + 中间摘要压缩。

        保留用户问题（首条）与最近 HISTORY_KEEP_TAIL 条消息逐字，
        中间消息各截断后拼成一条历史摘要，控制超长 prompt。
        """
        history = self.state.conversation_history
        if len(history) <= self.HISTORY_COMPRESS_THRESHOLD:
            return [{"role": "system", "content": system_prompt}, *history]

        head = history[:1]  # 用户问题（头）
        tail = history[-self.HISTORY_KEEP_TAIL:]  # 最近观察（尾，逐字保留）
        middle = history[1:-self.HISTORY_KEEP_TAIL]

        summary_lines = []
        total = 0
        for m in middle:
            snippet = (m.get('content') or '')[:120]
            summary_lines.append(f"[{m.get('role')}] {snippet}")
            total += len(snippet) + 8
            if total > self.HISTORY_SUMMARY_MAX_CHARS:
                break
        summary = "[历史摘要，已压缩较早步骤]\n" + "\n".join(summary_lines)

        return [
            {"role": "system", "content": system_prompt},
            head[0],
            {"role": "user", "content": summary},
            *tail,
        ]

    def _extract_tool_calls(self, thought: str,
                            max_calls: int = 5) -> List[Dict]:
        """基于思考提取工具调用 JSON 列表（支持并行多调用）

        容错 markdown 代码围栏与嵌套括号/字符串内的大括号，
        逐个扫描平衡的大括号对象，收集所有带 tool 字段的调用（上限 max_calls）。
        """
        if not thought:
            return []
        # 剥离 ```json ... ``` 代码围栏（保留内部内容）
        fenced = re.search(r'```(?:json)?\s*(.*?)```', thought, re.DOTALL)
        if fenced:
            thought = fenced.group(1)

        calls = []
        start = thought.find('{')
        while start != -1:
            depth = 0
            in_string = False
            escape = False
            end = -1
            for i in range(start, len(thought)):
                ch = thought[i]
                if in_string:
                    if escape:
                        escape = False
                    elif ch == '\\':
                        escape = True
                    elif ch == '"':
                        in_string = False
                    continue
                if ch == '"':
                    in_string = True
                elif ch == '{':
                    depth += 1
                elif ch == '}':
                    depth -= 1
                    if depth == 0:
                        end = i
                        break
            if end == -1:
                break
            candidate = thought[start:end + 1]
            try:
                obj = json.loads(candidate)
                if isinstance(obj, dict):
                    if obj.get('tool'):
                        calls.append(obj)
                        if len(calls) >= max_calls:
                            break
                    elif obj.get('type') == 'plan' and isinstance(obj.get('plan'), dict):
                        # 变更类操作计划是独立动作，遇到即止
                        calls.append(obj)
                        break
            except (json.JSONDecodeError, ValueError):
                pass
            # 前一个对象非工具调用，继续找下一个 {（如模型先输出了一段分析 JSON）
            start = thought.find('{', end)
        return calls

    @staticmethod
    def _action_fingerprint(actions: List[Dict]) -> str:
        """动作指纹：tool + 参数规范化，用于死循环检测"""
        return json.dumps(actions, sort_keys=True, ensure_ascii=False)

    def _history_chars(self) -> int:
        """对话历史总字符数（迭代预算）"""
        return sum(len(m.get('content', '')) for m in self.state.conversation_history)

    def _execute_actions(self, actions: List[Dict],
                         knowledge_refs: List[Dict]) -> List[Dict]:
        """批量执行工具调用：全部只读且 >1 个时并行，否则串行。

        每个动作先过 Harness 安全验证；返回
        [{action, observation, result, is_safe, error, warning}, ...]。
        """
        validated = []
        for action in actions:
            is_safe, error = self._validate_action(action)
            validated.append({'action': action, 'is_safe': is_safe, 'error': error})

        can_parallel = (
            len(validated) > 1
            and all(v['is_safe'] for v in validated)
            and all(v['action'].get('tool') in self.PARALLEL_SAFE_TOOLS for v in validated)
        )

        if can_parallel:
            from concurrent.futures import ThreadPoolExecutor
            results_map = {}
            with ThreadPoolExecutor(max_workers=min(self.PARALLEL_MAX_WORKERS,
                                                    len(validated))) as pool:
                future_to_idx = {
                    pool.submit(self._run_one_action, v, knowledge_refs): i
                    for i, v in enumerate(validated)
                }
                for fut in future_to_idx:
                    results_map[future_to_idx[fut]] = fut.result()
            return [results_map[i] for i in range(len(validated))]

        return [self._run_one_action(v, knowledge_refs) for v in validated]

    def _run_one_action(self, item: Dict, knowledge_refs: List[Dict]) -> Dict:
        """执行单个已校验动作：知识库支撑提示 + 执行 + 格式化观察"""
        action = item['action']
        if not item['is_safe']:
            return {**item, 'observation': f"❌ 安全验证失败: {item['error']}",
                    'result': None, 'warning': None}
        warning = None
        if not self._verify_knowledge_support(action, knowledge_refs):
            warning = "⚠️ 该操作缺乏知识库支撑，执行风险较高"
        result = self._execute_action(action)
        return {**item, 'observation': self._format_result(result),
                'result': result, 'warning': warning}

    # ==================== 变更类操作：审批流 ====================

    def _handle_plan_approval(self, plan: Dict) -> Generator[Dict, None, str]:
        """变更类操作审批流：创建计划 → 暂停轮询审批 → 获批执行 / 拒绝继续 / 超时收尾。

        返回 'approved' / 'rejected' / 'expired'。
        """
        from db.database import create_plan, get_plan, update_plan_status
        plan_id = create_plan(self.session_id, plan.get('title', '操作计划'), plan)
        yield {"type": "approval_required", "plan_id": plan_id, "plan": plan}

        from config import AGENT_PLAN_TIMEOUT_MINUTES
        deadline = datetime.now() + timedelta(minutes=int(AGENT_PLAN_TIMEOUT_MINUTES))
        while True:
            if datetime.now() > deadline:
                update_plan_status(plan_id, 'expired')
                yield {"type": "approval_expired", "plan_id": plan_id}
                return 'expired'
            row = get_plan(plan_id)
            status = (row or {}).get('status', 'expired')
            if status == 'approved':
                break
            if status == 'rejected':
                comment = (row or {}).get('comment', '') or ''
                yield {"type": "approval_rejected", "plan_id": plan_id, "comment": comment}
                self.state.add_message(
                    'user', f"操作计划被拒绝：{comment or '未提供原因'}。"
                            f"可基于反馈调整计划或只读探索，禁止执行写操作。")
                return 'rejected'
            time.sleep(2)

        yield {"type": "approval_granted", "plan_id": plan_id}
        self.state.add_message('user', "操作计划已批准。开始执行已批准的操作。")
        yield from self._execute_plan_operations(plan)
        return 'approved'

    def _execute_plan_operations(self, plan: Dict) -> Generator[Dict, None, None]:
        """按计划确定性执行已批准的变更操作（会话现有连接）。遇错即停。

        逐 op：Harness 变更白名单二次校验 → load 连接 → run_sql/run_ssh_command →
        流式结果 + 记录 AgentStep + 观察回流历史。失败即停止剩余操作，交给模型自分析。
        """
        from agent.connectors import load_db_conn, load_ssh_conn, run_sql, run_ssh_command
        operations = plan.get('operations') or []
        db_type = self._get_db_type()

        for i, op in enumerate(operations, 1):
            tool = op.get('tool')
            params = op.get('parameters') or {}
            if tool == 'query_database':
                cls, err = Harness.classify_sql(params.get('sql', ''))
            elif tool == 'execute_command':
                cls, err = Harness.classify_command(params.get('command', ''), db_type)
            else:
                cls, err = 'reject', f'计划操作不支持的工具: {tool}'

            if cls == 'reject':
                observation = f"❌ 计划操作 {i} 校验失败: {err}"
                yield {"type": "plan_operation_result", "index": i, "tool": tool,
                       "parameters": params, "status": "rejected", "error": err}
                self.state.add_message('user', observation)
                self._persist_plan_step(i, op, observation, None)
                break  # 遇错即停

            if tool == 'query_database':
                conn_info, load_err = load_db_conn(self.db_conn_id)
                if load_err:
                    result = {"error": load_err}
                else:
                    result = run_sql(conn_info, params.get('sql', ''))
            else:
                conn_info, load_err = load_ssh_conn(self.ssh_conn_id)
                if load_err:
                    result = {"error": load_err}
                else:
                    result = run_ssh_command(conn_info, params.get('command', ''),
                                             timeout=params.get('timeout', 30))

            observation = self._format_result(result)
            is_error = 'error' in result
            yield {"type": "plan_operation_result", "index": i, "tool": tool,
                   "parameters": params, "status": "error" if is_error else "success",
                   "result": result}
            self.state.add_message('user', f"计划操作 {i} 观察结果:\n{observation}")
            self._persist_plan_step(i, op, observation, result)
            if is_error:
                break  # 遇错即停，交给模型自分析

    def _persist_plan_step(self, index: int, op: Dict,
                           observation: str, result: Optional[Dict]) -> None:
        """把单个计划操作记录为执行步骤（消耗一个步数预算）"""
        step = self.state.add_step(
            AgentPhase.EXECUTING,
            action={'tool': op.get('tool'), 'parameters': op.get('parameters')},
            observation=observation,
        )
        self._persist_step(step)
        self.state.current_step += 1

    def _classify_action(self, action: Dict) -> Tuple[str, Optional[str]]:
        """三态分类动作：safe（只读直接执行）/ approval（变更或未知走审批）/ reject（注入拒绝）"""
        tool = action.get("tool")
        params = action.get("parameters", {})

        if tool == "query_database":
            return self.harness.classify_sql(params.get("sql", ""))
        elif tool == "execute_command":
            return self.harness.classify_command(params.get("command", ""),
                                                 self._get_db_type())
        # 其余工具（schema/性能/监控/检查项/知识检索）均为只读
        return 'safe', None

    def _build_approval_plan(self, action: Dict, reason: str = '') -> Dict:
        """把单个待审批动作包装成操作计划，走审批流"""
        tool = action.get("tool")
        params = action.get("parameters", {})
        if tool == 'execute_command':
            title = f"执行命令: {params.get('command', '')[:40]}"
        elif tool == 'query_database':
            title = f"执行SQL: {params.get('sql', '')[:40]}"
        else:
            title = f"调用工具: {tool}"
        return {
            'title': title,
            'scope': reason or '变更类/未授权操作，需 DBA 审批',
            'operations': [{
                'tool': tool,
                'parameters': params,
                'impact': '',
                'risk': 'medium',
            }],
            'rollback': '未提供（请 DBA 评估）',
        }

    def _validate_action(self, action: Dict) -> Tuple[bool, str]:
        """验证动作安全性"""
        tool = action.get("tool")
        params = action.get("parameters", {})

        if tool == "query_database":
            sql = params.get("sql", "")
            return self.harness.validate_sql(sql, self.operation_level)
        elif tool == "execute_command":
            command = params.get("command", "")
            db_type = self._get_db_type()
            return self.harness.validate_command(command, db_type, self.operation_level)

        return True, None

    def _verify_knowledge_support(self, action: Dict, knowledge_refs: List[Dict]) -> bool:
        """验证操作是否有知识库支撑"""
        if not knowledge_refs:
            return False

        tool = action.get("tool")
        params = action.get("parameters", {})

        if tool == "query_database":
            sql = params.get("sql", "")
            # 提取SQL中的表名、参数名
            # 简化版：检查SQL中是否有知识库中提到的关键词
            for ref in knowledge_refs:
                if any(keyword in sql.lower() for keyword in ref['chunk'].lower().split()):
                    return True

        elif tool == "execute_command":
            command = params.get("command", "")
            # 检查命令是否在知识库中有提及
            for ref in knowledge_refs:
                if command.split()[0] in ref['chunk']:
                    return True

        return False

    def _persist_step(self, step) -> None:
        """持久化单个执行步骤到 agent_steps"""
        try:
            conn = get_db()
            conn.execute(
                """INSERT INTO agent_steps
                   (session_id, step_number, phase, thought, action, observation, knowledge_refs)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (self.session_id, step.step_number, step.phase.value,
                 step.thought,
                 json.dumps(step.action, ensure_ascii=False) if step.action else None,
                 step.observation,
                 json.dumps(step.knowledge_refs, ensure_ascii=False) if step.knowledge_refs else None)
            )
            conn.commit()
        except Exception as e:
            print(f"[Agent] 步骤持久化失败: {e}")

    def _persist_session(self, status: AgentStatus) -> None:
        """持久化会话状态到 agent_sessions"""
        try:
            conn = get_db()
            conn.execute(
                "UPDATE agent_sessions SET status=?, current_step=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
                (status.value, self.state.current_step, self.session_id)
            )
            conn.commit()
        except Exception as e:
            print(f"[Agent] 会话状态持久化失败: {e}")

    def _execute_action(self, action: Dict) -> Dict:
        """执行工具（注入连接上下文）"""
        tool = action["tool"]
        params = action.get("parameters", {})
        ctx = ToolContext(
            db_conn_id=self.db_conn_id,
            ssh_conn_id=self.ssh_conn_id,
            db_type=self._get_db_type(),
            operation_level=self.operation_level
        )
        # 使用工具注册表执行
        return execute_tool(tool, params, ctx)

    def _format_result(self, result: Dict) -> str:
        """格式化执行结果为文本"""
        if "error" in result:
            return f"❌ 执行出错: {result['error']}"

        if "rows" in result:
            rows = result["rows"]
            columns = result.get("columns", [])
            return f"📊 查询结果: {len(rows)} 行\n" + self._format_table(columns, rows)

        if "metrics" in result and isinstance(result["metrics"], list):
            metric_type = result.get("metric_type", "性能指标")
            return f"📈 {metric_type}:\n" + self._format_table(result.get("columns", []), result["metrics"])

        if "tables" in result and isinstance(result["tables"], list):
            return f"📋 Schema信息:\n" + self._format_table(result.get("columns", []), result["tables"])

        if "stdout" in result:
            text = f"💻 命令输出:\n{result['stdout']}"
            if result.get("stderr"):
                text += f"\n[stderr] {result['stderr']}"
            return text

        if "results" in result and isinstance(result["results"], list):
            return f"📚 检索到 {len(result['results'])} 条知识：\n" + "\n".join(
                f"- {r.get('filename', '未知')} (相似度: {r.get('similarity', 0):.3f})"
                for r in result["results"][:10]
            )

        return str(result)

    def _format_table(self, columns: List[str], rows: List[List]) -> str:
        """格式化为Markdown表格"""
        if not columns:
            return "无数据"

        lines = []
        lines.append("| " + " | ".join(columns) + " |")
        lines.append("| " + " | ".join(["---"] * len(columns)) + " |")
        for row in rows[:50]:  # 限制行数
            lines.append("| " + " | ".join(str(c) for c in row) + " |")
        return "\n".join(lines)

    def _conclude(self, knowledge_refs: List[Dict]) -> str:
        """生成最终结论"""
        thoughts = [s.thought for s in self.state.steps if s.thought]
        observations = [s.observation for s in self.state.steps if s.observation]

        # 构建置信度信息
        max_similarity = 0
        if knowledge_refs:
            max_similarity = max(r.get('similarity', 0) for r in knowledge_refs)

        confidence = "🔴 低置信度"
        if max_similarity >= 0.85:
            confidence = "🟢 高置信度"
        elif max_similarity >= 0.75:
            confidence = "🟡 中置信度"

        prompt = f"""基于以下分析和观察结果，给出最终结论和建议：

分析过程:
{chr(10).join(thoughts)}

观察结果:
{chr(10).join(observations)}

知识库支撑: {confidence} (最高相似度: {max_similarity:.2f})

请给出：
1. 问题诊断结论
2. 具体建议
3. 后续操作建议
4. 置信度说明
"""

        messages = [
            {"role": "system", "content": "你是一个数据库运维专家，请基于分析结果给出专业建议。必须标注置信度。"},
            {"role": "user", "content": prompt}
        ]

        response, _ = call_llm(messages, model_id=self.model_id)
        return response

    def _recall_memory(self, question: str) -> List[Dict]:
        """召回长期记忆：语义优先，关键词兜底；对主机/实例/集群记忆做图谱补充。

        返回 [{...memory, graph_context?: str}]
        """
        try:
            from db.database import (search_memory_semantic, search_memory_by_keyword,
                                     bump_memory_usage)
            refs = search_memory_semantic(question, limit=6)
            if not refs:
                refs = search_memory_by_keyword(question, limit=6)
            for r in refs:
                bump_memory_usage(r['id'])
            return self._enrich_memory_graph(refs)
        except Exception as e:
            print(f"[Agent] 记忆召回失败: {e}")
            return []

    def _enrich_memory_graph(self, refs: List[Dict]) -> List[Dict]:
        """对主机/实例/集群类记忆补充知识图谱上下文（实体描述 + 邻居关系），最多补 2 条"""
        enriched = 0
        for r in refs:
            if enriched >= 2:
                break
            et = r.get('entity_type', '')
            en = r.get('entity_name', '')
            if et not in ('host', 'db_instance', 'cluster') or not en:
                continue
            try:
                from kg.graph import search_entities_enhanced
                result = search_entities_enhanced(en, include_neighbors=True,
                                                  max_relations=10)
                entities = result.get('entities') or []
                subgraph = result.get('subgraph') or {}
                lines = []
                center_id = None
                if entities:
                    e0 = entities[0]
                    center_id = e0.get('id')
                    desc = (e0.get('description') or '')[:80]
                    if desc:
                        lines.append(f"{e0.get('name')}({e0.get('entity_type')}): {desc}")
                for node in (subgraph.get('nodes') or {}).values():
                    if node.get('id') == center_id:
                        continue
                    lines.append(f"  关联 {node.get('name')}({node.get('entity_type')})")
                    if len(lines) >= 6:
                        break
                if lines:
                    r['graph_context'] = "\n".join(lines)
                    enriched += 1
            except Exception:
                continue
        return refs

    def _crystallize_after_success(self, user_question: str, conclusion: str,
                                   knowledge_refs: List[Dict]) -> None:
        """学习闭环：成功诊断后沉淀技能 + 写入长期记忆。

        条件：至少 2 次工具调用且无执行出错。运行于后台线程，
        任何异常都不影响已返回的诊断结果。
        """
        try:
            tool_steps = [s for s in self.state.steps if s.action and s.action.get('tool')]
            if len(tool_steps) < 2:
                return
            if any('❌ 执行出错' in (s.observation or '') for s in tool_steps):
                return

            trace = {
                'question': user_question,
                'db_type': self._get_db_type(),
                'session_id': self.session_id,
                'model_id': self.model_id,
                'steps': [
                    {'thought': s.thought, 'action': s.action, 'observation': s.observation}
                    for s in tool_steps
                ],
                'conclusion': conclusion,
            }
            skill_name = self.skill_manager.crystallize_skill(trace)
            if skill_name:
                print(f"[Agent] 已沉淀技能: {skill_name}")

            self._write_memory(user_question, conclusion, knowledge_refs)
        except Exception as e:
            print(f"[Agent] 学习闭环失败（不影响诊断）: {e}")

    def _write_memory(self, user_question: str, conclusion: str,
                      knowledge_refs: List[Dict]) -> None:
        """把本次诊断的环境事实写入长期记忆（写前事实校验，防污染）"""
        try:
            from db.database import save_memory
            entity_name, entity_type = self._extract_entity(user_question)
            fact = self._condense_fact(conclusion)
            if not fact:
                return
            confidence = self._validate_fact(entity_name, knowledge_refs)
            if confidence is None:
                print(f"[Agent] 记忆校验未通过，跳过写入: {fact[:40]}")
                return
            save_memory(
                entity_type=entity_type,
                entity_name=entity_name,
                fact=fact,
                category='incident',
                confidence=confidence,
                source=f'agent_session:{self.session_id}',
            )
        except Exception as e:
            print(f"[Agent] 记忆写入失败: {e}")

    def _validate_fact(self, entity_name: str, knowledge_refs: List[Dict]):
        """记忆写入事实校验：图谱实体 + 知识库支撑 + 监控对象交叉验证。

        返回置信度 (0~1)；无任何支撑且无实体时返回 None（跳过不写）。
        """
        score = 0.0
        if entity_name:
            try:
                from db.kg_database import search_entities
                if search_entities(entity_name, limit=1):
                    score += 0.4
            except Exception:
                pass
            try:
                from db.database import get_mon_objects
                if any(o.get('object_name') == entity_name for o in get_mon_objects()):
                    score += 0.3
            except Exception:
                pass
        if knowledge_refs:
            max_sim = max((r.get('similarity', 0) or 0) for r in knowledge_refs)
            if max_sim >= 0.75:
                score += 0.3
        if score <= 0.1 and not entity_name:
            return None
        if score >= 0.4:
            return min(0.5 + score * 0.5, 0.85)
        return 0.3

    @staticmethod
    def _extract_entity(question: str) -> Tuple[str, str]:
        """从问题提取对象（主机IP/实例名），无则 (空, general)"""
        ip = re.search(r'\b(?:\d{1,3}\.){3}\d{1,3}\b', question)
        if ip:
            return ip.group(0), 'host'
        host = re.search(
            r'([a-zA-Z][a-zA-Z0-9_-]*-(?:prod|test|dev|mysql|oracle|dm)[a-zA-Z0-9_-]*)',
            question, re.I)
        if host:
            return host.group(1), 'db_instance'
        return '', 'general'

    @staticmethod
    def _condense_fact(conclusion: str, max_len: int = 200) -> str:
        """把结论压成一条可检索的事实句（去换行/冗余）"""
        if not conclusion:
            return ''
        return re.sub(r'\s+', ' ', conclusion).strip()[:max_len]

    def _get_db_type(self) -> str:
        """获取当前数据库类型：优先数据库连接，其次 SSH 连接，最后兜底。

        仅配置 SSH（如只通过服务器命令诊断）时，也应正确识别 db_type，
        避免 fallback 到默认 oracle 导致 SQL/命令策略误判。
        """
        conn = get_db()
        if self.db_conn_id:
            row = conn.execute(
                "SELECT db_type FROM agent_db_connections WHERE id=?",
                (self.db_conn_id,)
            ).fetchone()
            if row and row['db_type']:
                return row['db_type']
        if self.ssh_conn_id:
            row = conn.execute(
                "SELECT db_type FROM agent_ssh_connections WHERE id=?",
                (self.ssh_conn_id,)
            ).fetchone()
            if row and row['db_type']:
                return row['db_type']
        return 'oracle'

    def get_state(self) -> Dict:
        """获取Agent状态"""
        return self.state.to_dict()
