"""Agent核心引擎 - ReAct循环 + 知识库增强 + Skills指导 + 学习闭环 + 变更审批流"""
import json
import uuid
import re
import time
import threading
from typing import Dict, List, Optional, Generator, Tuple, Any
from datetime import datetime, timedelta

from db.database import get_db
from utils import call_llm, call_llm_stream
from rag.embedder import Embedder
from agent.harness import Harness, OperationLevel
from agent.skills import SkillManager
from agent.state import AgentState, AgentPhase, AgentStatus
from agent.tools import get_tool_schemas, execute_tool, ToolContext


# 进程内会话取消标志：{session_id: True}。单进程 Flask 下有效，
# 由 routes stop 端点写入、引擎 ReAct 循环在下一轮收敛检查消费。
_cancel_flags: Dict[str, bool] = {}


def request_cancel(session_id: str) -> None:
    """请求取消一个正在执行的 Agent 会话（stop 端点调用）"""
    _cancel_flags[session_id] = True


def clear_cancel(session_id: str) -> None:
    """清除会话取消标志（新一轮 run 启动时调用，避免上一轮取消污染）"""
    _cancel_flags.pop(session_id, None)


def _is_cancelled(session_id: str) -> bool:
    return _cancel_flags.get(session_id, False)


class SmartOpsAgent:
    """智能运维Agent（第三代 - 自主决策模式）"""

    # 知识库检索阈值（与 routes/qa.py 对齐，v4.4.0 句界分块后实测校准维持）
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

    # 思考/结论生成显式 max_tokens：防弱模型长结论被提供商默认上限截断
    MAX_LLM_TOKENS = 4096

    def __init__(self, session_id: str, ssh_conn_id: Optional[str] = None,
                 db_conn_id: Optional[str] = None, model_id: Optional[str] = None,
                 scope: Optional[List[Dict]] = None,
                 manual_skill_name: Optional[str] = None,
                 disable_memory: bool = False,
                 plan_mode: bool = False):
        self.session_id = session_id
        self.ssh_conn_id = ssh_conn_id
        self.db_conn_id = db_conn_id
        self.model_id = model_id
        self.embedder = Embedder()
        self.skill_manager = SkillManager()
        self.harness = Harness()

        # v4.0 会话范围（多节点批量）：
        # - 有 scope 时解析为 targets（含未配置节点，resolved=False）；
        # - 无 scope（legacy 单连接）时退化为 ssh/db 连接对。
        # targets 供工具 fan-out 逐节点执行；scope_labels 供范围外 target 检测。
        from agent.scope import resolve_scope, scope_labels
        if scope:
            self.targets = resolve_scope(scope)
        else:
            legacy = []
            if ssh_conn_id:
                legacy.append({'type': 'ssh', 'topo_id': None,
                               'conn_id': ssh_conn_id, 'name': ''})
            if db_conn_id:
                legacy.append({'type': 'db', 'topo_id': None,
                               'conn_id': db_conn_id, 'name': ''})
            self.targets = resolve_scope(legacy)
        self.scope_labels = scope_labels(self.targets)

        # 手动指定技能（v4.0）：注入完整 prompt_template（绕开自动匹配的截断预览）
        self.manual_skill = (self.skill_manager.get_skill(manual_skill_name)
                             if manual_skill_name else None)
        # v4.2.1 会话级开关：关闭后不召回长期记忆（跨会话环境上下文）
        self.disable_memory = disable_memory
        # v4.4 plan 模式：先输出整体执行方案，用户确认后再执行
        self.plan_mode = plan_mode
        # 命令安全融合判定：静态判拒绝/未知的命令挂载独立 LLM 审查钩子（第二意见）。
        # 钩子在 harness 内部，引擎 _validate_action 与 tools.py 双重校验共用同一目标
        # + 同一 TTL 缓存，保证不会出现"引擎放行、工具层拦截"。
        from config import COMMAND_LLM_JUDGE
        if COMMAND_LLM_JUDGE:
            from functools import partial
            from agent.command_judge import judge_command
            Harness.command_judge_fn = partial(judge_command, model_id=self.model_id)
        from config import AGENT_MAX_STEPS, AGENT_MAX_HISTORY_CHARS, AGENT_MAX_WALL_CLOCK_SECONDS
        self.state = AgentState(session_id, max_steps=int(AGENT_MAX_STEPS))
        self.max_history_chars = int(AGENT_MAX_HISTORY_CHARS)
        self.max_wall_clock_seconds = int(AGENT_MAX_WALL_CLOCK_SECONDS)

        # 最近动作指纹（死循环检测）
        self._recent_actions = []

        # 操作级别（默认只读）
        self.operation_level = OperationLevel.READONLY

        # 是否执行过变更类操作（审批计划），决定结论采用简洁/分析两种格式
        self._executed_change_plan = False
        # 批量变更失败节点集合（continue-on-error 收集，供结论与前端重试）
        self._plan_failed_nodes = set()
        # 变更操作执行后待验证标记：模型想在验证前直接收敛时拦截一次，强制先做只读验证
        self._pending_verification = False
        # 验证拦截已重试一次（二次仍无验证动作才放行，避免死循环）
        self._verification_nudge_done = False
        # 工具调用 JSON 解析失败已回喂纠正的次数（限 1 次，防无限重试）
        self._extract_failed_nudges = 0

    def run_stream(self, user_question: str) -> Generator[Dict, None, None]:
        """ReAct主循环（流式输出），带状态持久化与异常兜底"""
        clear_cancel(self.session_id)  # 新一轮启动，清除上一轮可能的取消标记
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
        # v4.0 M7：手动指定技能时跳过同名自动匹配，避免同一技能模板重复注入
        if self.manual_skill:
            manual_name = self.manual_skill.get('name')
            matched_skills = [s for s in matched_skills
                              if s.get('name') != manual_name]

        # v4.4 激活 knowledge_tags：用技能标签对检索结果重排序（含 tag 的优先）
        tag_set = set()
        for sk in matched_skills:
            kt = sk.get('knowledge_tags')
            if kt:
                tag_set.update(t.lower() for t in (kt if isinstance(kt, list) else [kt]))
        if tag_set and knowledge_refs:
            def _tag_score(ref):
                text = (ref.get('chunk', '') + ' ' + ref.get('file', '')).lower()
                return sum(1 for t in tag_set if t in text)
            knowledge_refs = sorted(knowledge_refs, key=_tag_score, reverse=True)

        # 2.5 长期记忆召回（环境上下文）；会话级开关关闭时跳过（v4.2.1）
        memory_refs = [] if self.disable_memory else self._recall_memory(user_question)

        # 3. 构建system prompt（注入知识库 + 知识图谱 + Skills + 环境上下文）
        kg_context = self._retrieve_kg_context(user_question, chunk_ids) if chunk_ids else None
        system_prompt = self._build_system_prompt(knowledge_refs, matched_skills, kg_context, memory_refs)

        # 4. ReAct循环
        # 用户问题作为对话起点；每步的思考与观察结果通过 add_message 回流，
        # 使模型能基于上一轮工具结果继续推理（链式 ReAct）。
        self.state.add_message('user', user_question)

        cancelled = False  # 被 DBA 停止：跳过结论，会话置 cancelled
        loop_start = time.monotonic()  # 墙钟起点：LLM 慢/某步阻塞时按时限收敛
        while self.state.current_step < self.state.max_steps:
            # 取消：DBA 点了停止 → 收敛退出（跳过结论）
            if _is_cancelled(self.session_id):
                cancelled = True
                break
            # 墙钟超时：总时长超限 → 强制收敛到结论（不置 cancelled，保留部分结论）
            if time.monotonic() - loop_start > self.max_wall_clock_seconds:
                yield {"type": "executing_warning",
                       "warning": f"⚠️ 执行已超过 {self.max_wall_clock_seconds}s 上限，收敛并给出当前结论"}
                break
            # 迭代预算：对话历史字符超限 → 强制收敛
            if self._history_chars() > self.max_history_chars:
                yield {"type": "executing_warning",
                       "warning": "⚠️ 对话历史过长，停止继续执行，直接给出结论"}
                break

            # Thinking
            yield {"type": "thinking_start", "step": self.state.current_step}
            thought = yield from self._think_stream(system_prompt)
            yield {"type": "thinking_end"}

            step = self.state.add_step(AgentPhase.THINKING, thought=thought,
                                       knowledge_refs=knowledge_refs)
            self._persist_step(step)
            self.state.add_message('assistant', thought)

            # Decision: 提取工具调用（支持一次多个，只读工具并行执行）
            actions = self._extract_tool_calls(thought, max_calls=self.MAX_PARALLEL_CALLS)
            if not actions:
                # 变更执行后待验证：模型想直接给结论 → 拦一次，注入验证引导后重试本轮
                if self._pending_verification and not self._verification_nudge_done:
                    self._verification_nudge_done = True
                    yield {"type": "executing_warning",
                           "warning": "⚠️ 已批准的操作已执行，请先验证执行结果再给结论"}
                    self.state.add_message(
                        'user', "已批准的操作已执行。写结论前请先用只读工具验证执行结果"
                                "（tail 日志 / 检查进程 / 查询状态），确认无报错后再给最终结论。")
                    continue
                # 工具调用解析失败回喂：模型明显在输出工具 JSON 但无法解析 → 纠正一次后重试
                if self._extract_failed_nudges < 1 and self._looks_like_tool_json(thought):
                    self._extract_failed_nudges += 1
                    yield {"type": "executing_warning",
                           "warning": "⚠️ 工具调用格式无法解析，请重新输出"}
                    self.state.add_message(
                        'user', f"你的工具调用 JSON 无法解析（片段: {thought[:200]}）。"
                                "请只输出合法的工具调用 JSON，格式: "
                                '{"tool": "工具名", "parameters": {...}}。')
                    continue
                self._pending_verification = False
                break
            # 模型已产出工具调用（通常是验证动作），解除待验证标记
            self._pending_verification = False

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
                if plan_result == 'cancelled':
                    cancelled = True
                    break
                # 获批执行（计划操作已记步骤）/ 拒绝 / 要求修改后，本轮不执行其他工具，进入下一轮思考
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
                if plan is None:
                    # 范围扩展目标未配置连接/拓扑中不存在：不弹审批，指引补配
                    target = (action.get('parameters', {}).get('target') or '').strip()
                    yield {"type": "executing_warning",
                           "warning": f"节点 {target} 未配置连接，需先在范围面板一键配置后重试"}
                    continue
                plan_result = yield from self._handle_plan_approval(plan)
                if plan_result == 'scope_approved':
                    # M1：范围已扩展，原动作重投本回合继续执行（目标现已在范围）
                    orig = plan.get('_original_action')
                    if orig and self._classify_action(orig)[0] == 'safe':
                        safe_actions.append(orig)
                    continue
                if plan_result == 'expired':
                    expired = True
                    break
                if plan_result == 'cancelled':
                    cancelled = True
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

                    # 观察结果回流对话历史（大结果只存摘要，全量仅经 SSE 展示）
                    self.state.add_message(
                        'user', f"观察结果:\n{self._history_observation(item['observation'])}")

            self.state.next_step()

        # Conclusion（按需生成）：
        # - 未执行任何工具（直接回答/征求意见）：思考即对用户的回应，不再发起独立结论调用，
        #   发 final_thinking 事件让前端把最后思考展开为可见回复（避免空结论/重复）；
        # - 执行过诊断/变更：生成「分析结论」汇总结果；
        # - DBA 停止：跳过结论直接收尾置 cancelled。
        if not cancelled:
            tool_steps = [s for s in self.state.steps
                          if s.action and isinstance(s.action, dict) and s.action.get('tool')]
            has_conclusion = bool(tool_steps) or self._executed_change_plan
            conclusion = ''
            if has_conclusion:
                yield {"type": "concluding_start"}
                conclusion = yield from self._conclude_stream(knowledge_refs)
                yield {"type": "concluding_end"}

                step = self.state.add_step(AgentPhase.CONCLUDING, thought=conclusion)
                self._persist_step(step)
            else:
                yield {"type": "final_thinking"}
                conclusion = self.state.steps[-1].thought if self.state.steps else ''
            self.state.set_status(AgentStatus.COMPLETED)
            self._persist_session(AgentStatus.COMPLETED)

            # 学习闭环：成功诊断 → 后台沉淀技能 + 写长期记忆（不阻塞流式返回）
            if has_conclusion:
                threading.Thread(
                    target=self._crystallize_after_success,
                    args=(user_question, conclusion, knowledge_refs),
                    daemon=True,
                ).start()
        else:
            yield {"type": "cancelled", "message": "⏹ 已取消"}
            self.state.set_status(AgentStatus.CANCELLED)
            self._persist_session(AgentStatus.CANCELLED)

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

        # 检索后补相邻块上下文：固定分块可能导致跨块内容截断，
        # 对每个命中块拼接其 chunk_index±1 同文件相邻块，避免后续相关部分丢失
        try:
            from db.database import get_chunk_neighbors
            for r in filtered_results:
                cid = r.get('chunk_id')
                if not cid:
                    continue
                nb = get_chunk_neighbors(cid, radius=1)
                if nb['before'] or nb['after']:
                    r['chunk_text'] = '\n'.join(
                        nb['before'] + [r.get('chunk_text', '')] + nb['after']
                    )
        except Exception as e:
            print(f"[Agent] 补相邻块失败（不影响主流程）: {e}")

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
        """格式化知识库引用（chunk 注入长度从 config 取，原硬编码 200 放宽到容纳相邻块拼接）"""
        from config import KNOWLEDGE_CHUNK_INJECT_LIMIT
        refs = []
        for r in results:
            refs.append({
                'file': r.get('filename', '未知'),
                'chunk': r.get('chunk_text', '')[:KNOWLEDGE_CHUNK_INJECT_LIMIT],
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
0. **简洁优先**：若请求只需单条查询或直接回答（查版本/状态/参数、问含义、问候致谢等），直接用一句话回答，或调用一次必要工具后立即结束。禁止为简单任务做多步思考、检索知识库、输出章节标题、标注置信度、罗列建议。
1. **知识库优先**：分析/建议类回答尽量基于检索到的知识库内容
2. **禁止编造**：知识库缺失时如实说明；但**变更类操作不以知识库为前置条件**——正确性由 DBA 审批把关，你负责输出可执行的操作计划
3. **置信度标注**：仅分析/建议类结论需要标注置信度；变更操作计划不需要标注
4. **操作确认**：涉及操作时列出知识库引用来源（仅当确实有引用时）
5. **只读工具原则**：所有工具调用只读（变更 SQL/命令会被安全校验拦截）；**变更操作统一走"操作计划审批"执行，不通过工具直接执行**

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
5. **答案即止**：一旦拿到足够信息立即停止并给结论，不要为了"严谨"继续调用工具；单条查询能解决就不要多步。

## 变更类操作（需审批）
涉及修改参数/配置/执行变更命令（如 ALTER SYSTEM SET、SET GLOBAL、srvctl start/stop、重启/启停实例、su 切换执行服务启停）属于**变更类**。
- **用户明确要求变更时，直接进入计划流程**：不要拒绝、不要要求先做诊断、不要复述风险与置信度。风险写进计划每个操作的 risk 字段，审批由 DBA 把关。
- **目标对象推断**：优先用当前会话的数据库/SSH 连接指向的实例；会话历史或长期记忆中有明确实例的用它；确实无法确定时**只问一个简短问题**（如"重启哪个实例？"），得到答复后立即输出计划。不要向用户索要主机IP/端口——连接信息已在会话中配置。
- **必须输出结构化的操作计划 JSON 等待 DBA 审批**（系统会自动弹出审批面板，不要用自然语言请求用户确认）：
```json
{"type": "plan", "plan": {"title": "计划标题", "scope": "影响范围", "operations": [{"tool": "execute_command", "parameters": {"command": "..."}, "impact": "影响说明", "risk": "high/medium/low"}], "rollback": "回滚方法"}}
```
- 审批通过后引擎按计划执行；执行中遇问题请用只读工具自行分析探索，再追加新的操作计划等待审批，直至任务完成。
- **变更操作执行后必须验证（覆盖"答案即止"）**：每项已批准操作执行后、写结论前，必须用只读工具验证执行结果——
  1. 服务/实例启停 → systemctl status / ps / 实例状态查询，确认目标状态；
  2. 有日志的操作（安装/备份/初始化/配置）→ tail 日志确认无 ERROR 级错误、出现成功标记；
  3. 验证输出必须写入结论（"已确认 xxx"），不得仅凭命令返回码下结论。
  "答案即止"不适用于变更操作：验证完成才能结束。
- **禁止**：用散文（Markdown 表格/自然语言）输出计划、向用户提问"是否确认/是否同意"、拒绝执行已明确的变更指令。审批通过操作计划面板完成，无需征询用户文字确认。
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

        # v4.4 plan 模式：先输出整体方案，用户确认后再执行
        if self.plan_mode:
            prompt += """
## Plan 模式（当前启用）
你当前处于 Plan 模式。请先输出**整体执行方案**，不要直接调用工具执行。方案格式：
```json
{"type":"plan","plan":{"title":"方案标题","operations":[
  {"tool":"get_schema_info","parameters":{...},"phase":"探查","desc":"步骤说明"},
  {"tool":"query_database","parameters":{"sql":"SELECT ..."},"phase":"探查","desc":"..."},
  {"tool":"execute_command","parameters":{"command":"..."},"phase":"变更","desc":"..."}
]}}
```
要求：
- operations 含「探查」(只读) 与「变更」(写操作) 两类步骤，按执行顺序排列
- 每步说明 desc 与所属 phase
- 变更步骤在用户确认方案后仍需逐项审批（安全底线）
- 输出方案后停止，等待用户确认
"""

        # v4.0 会话操作范围注入（多节点批量；各节点 db_type 逐点列出，混型时按方言分别写 SQL）
        if self.targets:
            scope_lines = []
            for t in self.targets:
                tag = '✅' if t.get('resolved') else '⚠️未配置连接'
                dbtype = t.get('db_type') or ''
                host = t.get('host') or ''
                scope_lines.append(
                    f"- {t.get('name') or t.get('conn_id')} "
                    f"(主机: {host}, 类型: {t.get('type')}/{dbtype}) {tag}")
            prompt += (f"\n## 会话操作范围（当前 {len(self.targets)} 个节点，批量执行）\n"
                       + "\n".join(scope_lines)
                       + """

- 批量：query_database/get_schema_info/get_performance_metrics 只作用于范围内「数据库实例」节点，execute_command 只作用于「服务器」节点；不指定 target 时自动对范围内所有可用节点批量执行。
- target：工具参数 target 可指定单个节点（用节点名或主机名）。
- 占位符：命令/SQL 中可用 {host}/{port}/{instance}/{node}，引擎按各节点替换后再执行。
- 方言：范围内各节点 db_type 可能不同，SQL/命令必须匹配目标节点的数据库方言；跨混型范围时分别处理或注明差异。
- 范围外节点：若需操作范围外的节点，先用自然语言请求「扩展操作范围至节点 X」（将弹出审批），不要直接使用范围外节点名。
- ⚠️未配置连接的节点不会执行，请提醒 DBA 先配置连接。
""")

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

        # v4.0 手动指定技能：注入完整操作指南（绕开自动匹配的截断预览）
        if self.manual_skill and self.manual_skill.get('prompt_template'):
            prompt += (f"\n## 指定技能操作指南（必须严格遵循）\n"
                       f"{self.manual_skill['prompt_template']}\n")

        # v4.4 激活 required_tools：技能声明的工具白名单约束本次工具调用
        tool_whitelist = set()
        for sk in skills:
            rt = sk.get('required_tools')
            if rt:
                tool_whitelist.update(rt if isinstance(rt, list) else [rt])
        if self.manual_skill and self.manual_skill.get('required_tools'):
            tool_whitelist.update(self.manual_skill['required_tools'])
        if tool_whitelist:
            prompt += (f"\n## 工具使用约束\n"
                       f"本次操作仅允许调用以下工具：{', '.join(sorted(tool_whitelist))}。"
                       f"如需其他工具，先说明原因再调用。\n")

        # 注入长期记忆（环境上下文，含图谱补充）
        if memory_refs:
            prompt += "\n## 环境上下文（历史记录，供参考）\n"
            from config import MEMORY_INJECT_TOP_K
            for mem in memory_refs[:MEMORY_INJECT_TOP_K]:
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

    def _stream_llm(self, messages: List[Dict],
                    event_type: str) -> Generator[Dict, None, str]:
        """流式调用 LLM：逐 delta 产出 {event_type, content} 事件，返回完整文本。

        流式失败/无配置时回退非流式调用（一次性产出），保证不中断。
        """
        full = ''

        def fallback():
            response, err = call_llm(messages, model_id=self.model_id)
            if err:
                print(f"[Agent] LLM 非流式回退失败: {err}")
            text = response or ''
            yield {"type": event_type, "content": text}
            return text

        try:
            # 显式 max_tokens：防弱模型长结论被提供商默认上限截断（结论/思考类生成）
            for delta, err in call_llm_stream(messages, model_id=self.model_id,
                                              max_tokens=self.MAX_LLM_TOKENS):
                if err:
                    if not full:
                        return (yield from fallback())
                    break  # 已产出部分内容，保留部分
                if delta:
                    full += delta
                    yield {"type": event_type, "content": delta}
        except Exception as e:
            print(f"[Agent] LLM 流式调用异常（回退非流式）: {e}")
            if not full:
                return (yield from fallback())
        if not full:
            # 双失败（流式 + 非流式均空）：产出可感知警告，避免前端无任何反馈的静默空转
            yield {"type": "executing_warning",
                   "warning": "⚠️ LLM 调用失败或返回空，本次步骤无输出"}
        return full

    def _think(self, system_prompt: str) -> str:
        """LLM思考（基于对话历史，过长时自动压缩中间步骤，非流式）"""
        messages = self._build_messages(system_prompt)

        response, _ = call_llm(messages, model_id=self.model_id)
        return response

    def _think_stream(self, system_prompt: str) -> Generator[Dict, None, str]:
        """LLM思考（流式）：逐 token 产出 thinking_chunk，返回完整思考文本"""
        messages = self._build_messages(system_prompt)
        return (yield from self._stream_llm(messages, 'thinking_chunk'))

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
        # 剥离所有 ```json ... ``` 代码围栏标记、保留全文：
        # 模型若分段各包一个 JSON，只取第一个 fence 会丢后续调用；
        # 分两步删（开 fence 含可选 json 前缀 → 闭 fence），避免交替匹配在相邻 fence 间残留
        thought = re.sub(r'```(?:json)?', '', thought)
        thought = re.sub(r'```', '', thought)

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
            # 容错模型常见 JSON 错误：对象/数组尾部的多余逗号（{...,} / [...,]）
            candidate = re.sub(r',\s*([}\]])', r'\1', candidate)
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
        """动作指纹：工具名 + 参数键集合（参数值微变不视为新动作），用于死循环检测。

        全参数 JSON 作为指纹过严：模型反复改 LIMIT/条件重查会因参数微变而无法触发检测。
        """
        def norm(a):
            if not isinstance(a, dict):
                return 'other'
            if a.get('type') == 'plan':
                return 'plan'
            params = a.get('parameters')
            keys = ','.join(sorted(params.keys())) if isinstance(params, dict) else ''
            return f"{a.get('tool', '')}:{keys}"
        return json.dumps([norm(a) for a in actions], ensure_ascii=False)

    @staticmethod
    def _looks_like_tool_json(thought: str) -> bool:
        """判断思考文本是否明显在输出工具调用 JSON（带引号的键），用于解析失败时回喂纠正"""
        return '"tool"' in thought and '"parameters"' in thought

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
        """执行单个已校验动作：执行 + 格式化观察。

        不再输出「缺乏知识库支撑」警告：该启发式对 OS 级/诊断类命令几乎必然误报
        （命令首词不在检索到的知识块里就告警），噪音大于价值，已移除。
        """
        action = item['action']
        if not item['is_safe']:
            return {**item, 'observation': f"❌ 安全验证失败: {item['error']}",
                    'result': None, 'warning': None}
        try:
            result = self._execute_action(action)
            return {**item, 'observation': self._format_result(result),
                    'result': result, 'warning': None}
        except Exception as e:
            # 单个工具异常兜底：转观察结果，避免并行线程内异常中断整个 ReAct 循环
            return {**item,
                    'observation': f"❌ 工具执行出错: {e}",
                    'result': None, 'warning': None}

    # ==================== 变更类操作：审批流 ====================

    def _handle_plan_approval(self, plan: Dict) -> Generator[Dict, None, str]:
        """变更类操作审批流：创建计划 → 暂停轮询审批 → 获批执行 / 拒绝继续 / 修改重出方案 / 超时收尾 / 取消。

        返回 'approved' / 'rejected' / 'revised' / 'expired' / 'cancelled'。
        """
        from db.database import create_plan, get_plan, update_plan_status
        # 用命令真实危险性重算每个 op 的 risk（不信任模型自填），供审批条标注
        self._enrich_plan_risks(plan)
        # v4.4 plan 模式下的整体方案标记 kind='overall_plan'，变更审批保持默认
        plan_kind = 'overall_plan' if self.plan_mode else 'change_approval'
        plan_id = create_plan(self.session_id, plan.get('title', '操作计划'), plan, kind=plan_kind)
        yield {"type": "approval_required", "plan_id": plan_id, "plan": plan}

        from config import AGENT_PLAN_TIMEOUT_MINUTES
        deadline = datetime.now() + timedelta(minutes=int(AGENT_PLAN_TIMEOUT_MINUTES))
        while True:
            if _is_cancelled(self.session_id):
                # DBA 停止了执行：不落 cancelled 状态（计划仍 pending，避免与超时混淆）
                return 'cancelled'
            if datetime.now() > deadline:
                update_plan_status(plan_id, 'expired')
                yield {"type": "approval_expired", "plan_id": plan_id}
                return 'expired'
            row = get_plan(plan_id)
            status = (row or {}).get('status', 'expired')
            if status == 'approved':
                break
            if status == 'revised':
                # 修改并重新提供方案：把 DBA 的修改要求回流给模型，重新输出计划
                comment = (row or {}).get('comment', '') or ''
                yield {"type": "approval_revised", "plan_id": plan_id, "comment": comment}
                self.state.add_message(
                    'user', f"DBA 要求修改：{comment or '未说明'}。"
                            f"请基于反馈调整并重新输出操作计划（{{\"type\": \"plan\", \"plan\": {{...}}}}）"
                            f"等待审批；若无需再变更请直接给出结论，禁止执行写操作。")
                return 'revised'
            if status == 'rejected':
                comment = (row or {}).get('comment', '') or ''
                yield {"type": "approval_rejected", "plan_id": plan_id, "comment": comment}
                self.state.add_message(
                    'user', f"操作计划被拒绝：{comment or '未提供原因'}。"
                            f"可基于反馈调整计划或只读探索，禁止执行写操作。")
                return 'rejected'
            time.sleep(2)

        yield {"type": "approval_granted", "plan_id": plan_id}
        if plan.get('kind') == 'scope':
            # v4.0 范围扩展计划：无命令/SQL，批准后直接扩展范围并返回 'scope_approved'
            # （React 循环据此把原动作重投本回合继续执行，避免二次审批）
            self._apply_scope_extension(plan.get('targets') or [])
            yield {"type": "scope_extended", "plan_id": plan_id,
                   "targets": plan.get('targets') or []}
            return 'scope_approved'
        self.state.add_message('user', "操作计划已批准。开始执行已批准的操作。")
        yield from self._execute_plan_operations(plan)
        # 变更已执行：标记待验证，下一轮模型若想直接收敛会被拦一次，强制先做只读验证
        self._pending_verification = True
        self._verification_nudge_done = False
        return 'approved'

    def _execute_plan_operations(self, plan: Dict) -> Generator[Dict, None, None]:
        """按计划确定性执行已批准的变更操作（会话范围多节点，continue-on-error）。

        逐 op：Harness 计划级二次校验（只挡注入/绕过，策略级拒绝放行）→ 选定目标节点
        （默认全范围该类型节点；op.targets 可限定）→ 逐节点执行（并发上限 4）→
        plan_operation_result 逐节点流式（含 node+status）→ 遇错收集继续剩余操作。
        失败节点记入 self._plan_failed_nodes，供结论与前端「仅重试失败节点」。
        """
        from agent.connectors import run_sql, run_ssh_command
        from agent.tools import _select_nodes, _substitute_placeholders, _node_label, _fan_out
        operations = plan.get('operations') or []
        db_type = self._get_db_type()

        # 标记已执行变更类操作，最终结论改用简洁格式
        self._executed_change_plan = True
        self._plan_failed_nodes = set()

        for i, op in enumerate(operations, 1):
            tool = op.get('tool')
            params = op.get('parameters') or {}
            op_targets = op.get('targets')  # 可选：计划操作限定的目标节点名列表

            # v4.4 只读探查类工具：直接执行，不走 fan-out 审批
            READONLY_PLAN_TOOLS = {'get_schema_info', 'get_performance_metrics',
                                   'retrieve_knowledge', 'retrieve_check',
                                   'get_monitor_metrics'}
            if tool in READONLY_PLAN_TOOLS:
                ok, err = True, ''
                conn_type = '__readonly__'   # 标记走只读执行路径
            elif tool == 'query_database':
                cls, err = Harness.classify_sql(params.get('sql', ''))
                conn_type = 'db'
                if cls == 'reject':
                    ok = False
                else:
                    ok = True
            elif tool == 'execute_command':
                ok, err = Harness.validate_plan_operation(
                    params.get('command', ''), db_type)
                conn_type = 'ssh'
            else:
                ok, err = False, f'计划操作不支持的工具: {tool}'
                conn_type = None

            if not ok:
                observation = f"❌ 计划操作 {i} 校验失败: {err}"
                yield {"type": "plan_operation_result", "index": i, "tool": tool,
                       "parameters": params, "status": "rejected", "error": err}
                self.state.add_message('user', observation)
                self._persist_plan_step(i, op, observation, None)
                continue  # 收集语义：校验失败也继续剩余操作

            # v4.4 只读探查工具：单次执行（不 fan-out），结果直接产出
            if conn_type == '__readonly__':
                try:
                    ctx = ToolContext(db_conn_id=self.db_conn_id, ssh_conn_id=self.ssh_conn_id,
                                      db_type=db_type, targets=self.targets,
                                      session_id=self.session_id)
                    result = execute_tool(tool, params, ctx)
                    yield {"type": "plan_operation_result", "index": i, "tool": tool,
                           "parameters": params, "status": "success", "result": result}
                    obs = f"计划操作 {i}（只读探查）结果:\n{json.dumps(result, ensure_ascii=False)[:500]}"
                    self.state.add_message('user', self._history_observation(obs))
                    self._persist_plan_step(i, op, obs, result)
                except Exception as e:
                    yield {"type": "plan_operation_result", "index": i, "tool": tool,
                           "parameters": params, "status": "error", "error": str(e)}
                continue   # 只读工具不走下方 fan-out

            # 选定目标节点（默认全范围该类型；op.targets 限定子集）
            ctx = ToolContext(db_conn_id=self.db_conn_id, ssh_conn_id=self.ssh_conn_id,
                              db_type=db_type, targets=self.targets,
                              session_id=self.session_id)
            nodes, _ = _select_nodes(ctx, conn_type, None)
            if op_targets:
                names = {str(n).strip() for n in op_targets}
                nodes = [t for t in (nodes or [])
                         if (t.get('name') or '') in names or (t.get('host') or '') in names]
            if not nodes:
                observation = f"❌ 计划操作 {i} 无可用执行节点"
                yield {"type": "plan_operation_result", "index": i, "tool": tool,
                       "parameters": params, "status": "error", "error": observation}
                self.state.add_message('user', observation)
                self._persist_plan_step(i, op, observation, None)
                continue

            def node_exec(t: Dict, conn_info: Dict) -> Dict:
                if tool == 'query_database':
                    node_sql = _substitute_placeholders(params.get('sql', ''), t)
                    cls2, _ = Harness.classify_sql(node_sql)
                    if cls2 == 'reject':
                        return {"node": _node_label(t), "ok": False,
                                "error": "SQL 注入拦截（替换后）"}
                    result = run_sql(conn_info, node_sql,
                                     max_rows=params.get('max_rows', 100))
                else:
                    node_cmd = _substitute_placeholders(params.get('command', ''), t)
                    ok2, err2 = Harness.validate_plan_operation(
                        node_cmd, conn_info.get('db_type') or db_type)
                    if not ok2:
                        return {"node": _node_label(t), "ok": False,
                                "error": f"注入拦截: {err2}"}
                    result = run_ssh_command(conn_info, node_cmd,
                                             timeout=params.get('timeout', 300))
                if 'error' in result:
                    return {"node": _node_label(t), "ok": False, "error": result['error']}
                return {"node": _node_label(t), "ok": True, "result": result}

            batch = _fan_out(ToolContext(targets=nodes, session_id=self.session_id,
                                         db_type=db_type), conn_type, node_exec)
            results = batch.get('results') if batch.get('type') == 'batch_result' else [batch]

            node_obs = []
            for r in results:
                label = r.get('node') or '?'
                if r.get('ok'):
                    yield {"type": "plan_operation_result", "index": i, "tool": tool,
                           "parameters": params, "node": label,
                           "status": "success", "result": r.get('result') or {}}
                    node_obs.append(f"✅ {label}")
                else:
                    self._plan_failed_nodes.add(label)
                    yield {"type": "plan_operation_result", "index": i, "tool": tool,
                           "parameters": params, "node": label,
                           "status": "error", "error": r.get('error')}
                    node_obs.append(f"❌ {label}: {r.get('error')}")

            observation = f"计划操作 {i} 执行结果（{len(results)} 节点）:\n" + "\n".join(node_obs)
            if self._plan_failed_nodes:
                # 失败引导：避免模型只下"部分节点失败"结论了事，驱动其用只读工具定位原因
                observation += ("\n⚠️ 存在失败节点，请用只读工具检查其日志/状态，"
                                "定位原因后再决定下一步（如仅对失败节点重试）。")
            self.state.add_message('user', self._history_observation(observation))
            self._persist_plan_step(i, op, observation, results)

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

        # v4.0 范围外 target：转审批（扩展操作范围后本回合重投执行）
        target = params.get("target")
        if target and tool in ('execute_command', 'query_database'):
            tname = str(target).strip()
            if tname and tname not in self.scope_labels:
                return 'approval', f"目标节点不在会话范围: {tname}（需扩展操作范围）"

        if tool == "query_database":
            return self.harness.classify_sql(params.get("sql", ""))
        elif tool == "execute_command":
            return self.harness.classify_command(params.get("command", ""),
                                                 self._get_db_type())
        # 其余工具（schema/性能/监控/检查项/知识检索）均为只读
        return 'safe', None

    def _build_approval_plan(self, action: Dict, reason: str = '') -> Optional[Dict]:
        """把单个待审批动作包装成操作计划，走审批流。

        v4.0 范围扩展：reason 以「目标节点不在会话范围」开头时返回 kind:'scope' 计划
        （嵌入原动作，批准后由 React 循环重投执行）；目标节点未配置连接或拓扑中不存在
        则返回 None，调用方改发 executing_warning 指引补配，不弹审批。
        """
        tool = action.get("tool")
        params = action.get("parameters", {})
        if reason and reason.startswith('目标节点不在会话范围'):
            target = (params.get('target') or '').strip()
            node = self._find_topo_node(target)
            if not node:
                return None  # 拓扑中找不到该节点
            from agent.scope import resolve_target
            resolved = resolve_target({'type': node['type'], 'topo_id': node['id'],
                                       'name': node['name']})
            if not resolved or not resolved.get('resolved'):
                return None  # 节点未配置连接，不弹审批
            return {
                'kind': 'scope',
                'title': f"扩展操作范围至节点 {target}",
                'scope': f"批准后将节点 {target} 加入会话范围并继续执行该操作",
                'targets': [{'name': target}],
                'operations': [],
                'rollback': '',
                '_original_action': action,  # 批准后本回合重投（M1）
            }
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
                'risk': self._estimate_op_risk(tool, params),
            }],
            'rollback': '未提供（请 DBA 评估）',
        }

    def _estimate_op_risk(self, tool: str, params: Dict) -> str:
        """估算单个操作的危险级别（审批标注用，不参与放行决策）"""
        if tool == 'execute_command':
            return Harness.estimate_command_risk(
                params.get('command', ''), self._get_db_type())
        if tool == 'query_database':
            sql = params.get('sql', '')
            is_safe, _ = Harness.validate_sql(sql, OperationLevel.READONLY)
            return 'low' if is_safe else 'medium'
        return 'medium'

    def _enrich_plan_risks(self, plan: Dict) -> None:
        """按命令真实危险性重算操作计划里每个 op 的 risk（审批标注用）。

        只读 SQL/命令 → low；普通变更 → medium；T1/su/注入 → high。
        不改动放行语义，仅修正展示风险，不信任模型自填值。
        """
        for op in (plan.get('operations') or []):
            op['risk'] = self._estimate_op_risk(op.get('tool', ''), op.get('parameters') or {})

    def _find_topo_node(self, name: str) -> Optional[Dict]:
        """在拓扑资源池树中按 name/host 查找服务器或实例节点。

        返回 {type:'ssh'|'db', id, name}；未找到返回 None。
        """
        from db.database import get_topology_data
        name = (name or '').strip()
        if not name:
            return None
        try:
            data = get_topology_data()
        except Exception:
            return None
        for pool in data.get('clusters', []):
            for s in pool.get('servers', []):
                if name == (s.get('name') or '') or name == (s.get('host') or ''):
                    return {'type': 'ssh', 'id': s['id'], 'name': s.get('name') or name}
                for i in s.get('instances', []):
                    if name == (i.get('name') or ''):
                        return {'type': 'db', 'id': i['id'], 'name': i.get('name') or name}
        return None

    def _apply_scope_extension(self, names: List[Any]) -> None:
        """把范围外节点加入会话范围并持久化（范围扩展审批批准后调用）。

        names 元素可为字符串或 {'name':...} 字典（兼容两类调用方）。
        仅加入拓扑中可解析的节点；未配置连接或找不到的跳过。
        """
        from agent.scope import resolve_target
        from db.database import get_session_scope, set_session_scope
        added = []
        for item in names or []:
            name = item.strip() if isinstance(item, str) \
                else ((item or {}).get('name') or '').strip()
            if not name or name in self.scope_labels:
                continue
            node = self._find_topo_node(name)
            if not node:
                continue
            target = {'type': node['type'], 'topo_id': node['id'], 'name': node['name']}
            resolved = resolve_target(target)
            if resolved and resolved.get('resolved'):
                self.targets.append(resolved)
                for key in ('name', 'conn_name', 'host'):
                    val = resolved.get(key)
                    if val:
                        self.scope_labels.add(val)
                added.append(target)
        if added:
            cur = get_session_scope(self.session_id).get('targets') or []
            for t in added:
                if not any(x.get('type') == t['type'] and x.get('topo_id') == t['topo_id']
                           for x in cur):
                    cur.append(t)
            set_session_scope(self.session_id, 'scope', cur)

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
        """执行工具（注入连接上下文 + 会话范围 targets，v4.0 批量）"""
        tool = action["tool"]
        params = action.get("parameters", {})
        ctx = ToolContext(
            db_conn_id=self.db_conn_id,
            ssh_conn_id=self.ssh_conn_id,
            db_type=self._get_db_type(),
            operation_level=self.operation_level,
            targets=self.targets,
            session_id=self.session_id
        )
        # 使用工具注册表执行
        return execute_tool(tool, params, ctx)

    def _history_observation(self, observation: str, limit: int = 1500) -> str:
        """写入对话历史的观察摘要：超长按「头+尾」保留，避免大结果撑爆历史字符预算。

        全量观察仍经 SSE observing 事件展示给前端；history 只存摘要供模型链式推理。
        """
        obs = observation or ''
        if len(obs) <= limit:
            return obs
        half = (limit - len('\n... [中间省略] ...\n')) // 2
        return obs[:half] + '\n... [中间省略] ...\n' + obs[-half:]

    def _format_result(self, result: Dict) -> str:
        """格式化执行结果为文本"""
        if result.get('type') == 'batch_result':
            # 批量结果：逐节点紧凑摘要（结构化数据经 SSE result 传前端，不落历史）
            results = result.get('results', [])
            ok_count = sum(1 for r in results if r.get('ok'))
            fail_count = len(results) - ok_count
            lines = [f"📡 批量执行结果 ({len(results)} 节点, ✅{ok_count}/❌{fail_count}):"]
            for r in results:
                label = r.get('node') or '?'
                if r.get('ok'):
                    if 'row_count' in r:
                        out_str = f"{r.get('row_count', 0)} 行"
                    else:
                        # 变更类节点保留退出码 + 输出尾部（成功/失败标记常在尾部）
                        out = str(r.get('output') or 'ok').replace('\n', ' ')
                        tail = out[-200:]
                        out_str = (out if len(out) <= 200 else '...' + tail)
                    lines.append(f"- ✅ {label}: {out_str}")
                else:
                    lines.append(f"- ❌ {label}: {r.get('error', '失败')}")
            return "\n".join(lines)

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

        # 单目标/单节点执行：{node, ok, output} 包装（v4.0 逐节点执行返回形态）
        if "output" in result and "node" in result:
            text = f"💻 {result['node']} 命令输出:\n{result['output']}"
            if result.get('ok') is False and result.get('error'):
                text = f"❌ {result['node']}: {result['error']}"
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

    def _build_conclude_messages(self, knowledge_refs: List[Dict]) -> List[Dict]:
        """构建最终结论的消息列表：按执行情况选简洁/极简/收敛三种格式。

        变更操作 → 简洁；未执行任何工具（如仅澄清/待补充信息）→ 极简直接；
        执行过诊断 → 收敛的分析格式（控制篇幅，禁止泛泛建议）。
        """
        thoughts = [s.thought for s in self.state.steps if s.thought]
        observations = [s.observation for s in self.state.steps if s.observation]
        tool_steps = [s for s in self.state.steps
                      if s.action and isinstance(s.action, dict) and s.action.get('tool')]

        if self._executed_change_plan:
            # 变更类操作：聚焦操作结果，简洁明了，不展开长篇分析
            failed_nodes = ', '.join(sorted(self._plan_failed_nodes)) or '无'
            prompt = f"""以下是本次变更操作的执行记录，请给出简洁的操作结论：

操作步骤:
{chr(10).join(thoughts)}

执行结果:
{chr(10).join(observations)}

批量变更失败节点: {failed_nodes}

请用简洁语言给出（2-4 句即可）：
1. 操作是否成功（一句话，含失败节点，如有）
2. 关键结果（如新状态、进程、配置生效等）
3. 如有必要，仅保留 1-2 条后续验证建议（失败节点需提示重试）

要求：只讲操作结果和必要提醒，不要长篇分析、不要罗列通用建议、不要展开置信度说明。"""
            system = "你是一个数据库运维专家，请基于操作执行结果给出简洁结论，避免冗长。"
        elif not tool_steps:
            # 未调用任何工具（直接作答/仅澄清）：极简收尾，不套分析报告模板。
            # 注意：思考中可能已给出答案（简单任务直接回答），需明确区分两种收尾。
            prompt = f"""以下是本次对话的分析过程（未调用任何工具）：

{chr(10).join(thoughts) or '(无分析内容)'}

请用 1-3 句话直接给出最终回应：
1. 若已在分析中给出答案/可直接回答，用一两句话复述结论要点，直接结束；
2. 若缺少关键信息，明确指出缺什么、需要用户提供什么，然后停止；
3. 不要展开分析、不要罗列通用建议、不要标注置信度、不要输出章节标题。"""
            system = "你是一个数据库运维专家，回答务必简短直接，避免冗长。"
        else:
            # 执行过诊断：收敛的分析格式，控制篇幅，禁止泛泛建议
            max_similarity = 0
            if knowledge_refs:
                max_similarity = max(r.get('similarity', 0) for r in knowledge_refs)

            confidence = "🔴 低置信度"
            if max_similarity >= 0.85:
                confidence = "🟢 高置信度"
            elif max_similarity >= 0.75:
                confidence = "🟡 中置信度"

            prompt = f"""基于以下分析和观察结果，给出最终结论和建议（控制篇幅）：

分析过程:
{chr(10).join(thoughts)}

观察结果:
{chr(10).join(observations)}

知识库支撑: {confidence} (最高相似度: {max_similarity:.2f})

请给出：
1. 问题诊断结论（2-4 句，直接说问题与依据）
2. 具体建议（与本次观察/操作直接相关；若建议下一步操作，直接给，不要泛泛而谈）

要求：不要罗列通用最佳实践（监控建设、流程规范等）、不要展开置信度说明、不要重复分析过程。若本次只执行了单次查询，直接给出一两句话的结论并包含关键结果，不要展开分析、不要罗列建议。"""
            system = "你是一个数据库运维专家，请基于分析结果给出专业建议，保持简洁，避免冗余。"

        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt}
        ]
        return messages

    def _conclude(self, knowledge_refs: List[Dict]) -> str:
        """生成最终结论（非流式）"""
        messages = self._build_conclude_messages(knowledge_refs)
        response, _ = call_llm(messages, model_id=self.model_id)
        return response

    def _conclude_stream(self, knowledge_refs: List[Dict]) -> Generator[Dict, None, str]:
        """生成最终结论（流式）：逐 token 产出 concluding_chunk。

        LLM 未产出结论（调用失败/空响应）时，用最近一次观察作确定性兜底，
        保证「分析结论」块永不为空。
        """
        messages = self._build_conclude_messages(knowledge_refs)
        text = yield from self._stream_llm(messages, 'concluding_chunk')
        if not (text or '').strip():
            last_obs = next((o for o in reversed(
                [s.observation for s in self.state.steps if s.observation])), '')
            fallback = f"执行完成。{last_obs[:200]}" if last_obs else "本次执行已完成。"
            yield {"type": "concluding_chunk", "content": fallback}
            print(f"[Agent] 结论为空，已用观察兜底: {fallback[:60]}")
            return fallback
        return text

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
