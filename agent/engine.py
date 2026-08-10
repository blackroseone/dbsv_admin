"""Agent核心引擎 - ReAct循环 + 知识库增强 + Skills指导"""
import json
import uuid
import re
from typing import Dict, List, Optional, Generator, Tuple
from datetime import datetime

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

    def __init__(self, session_id: str, ssh_conn_id: Optional[str] = None,
                 db_conn_id: Optional[str] = None, model_id: Optional[str] = None):
        self.session_id = session_id
        self.ssh_conn_id = ssh_conn_id
        self.db_conn_id = db_conn_id
        self.model_id = model_id
        self.embedder = Embedder()
        self.skill_manager = SkillManager()
        self.harness = Harness()
        self.state = AgentState(session_id)

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

        # 3. 构建system prompt（注入知识库 + 知识图谱 + Skills）
        kg_context = self._retrieve_kg_context(user_question, chunk_ids) if chunk_ids else None
        system_prompt = self._build_system_prompt(knowledge_refs, matched_skills, kg_context)

        # 4. ReAct循环
        # 用户问题作为对话起点；每步的思考与观察结果通过 add_message 回流，
        # 使模型能基于上一轮工具结果继续推理（链式 ReAct）。
        self.state.add_message('user', user_question)

        while self.state.current_step < self.state.max_steps:
            # Thinking
            yield {"type": "thinking_start", "step": self.state.current_step}
            thought = self._think(system_prompt)
            yield {"type": "thinking_chunk", "content": thought}
            yield {"type": "thinking_end"}

            step = self.state.add_step(AgentPhase.THINKING, thought=thought,
                                       knowledge_refs=knowledge_refs)
            self._persist_step(step)
            self.state.add_message('assistant', thought)

            # Decision: 是否需要执行工具？（不再调用工具时自然结束）
            action = self._decide_action(thought)
            if not action:
                break

            # Planning
            yield {"type": "planning", "action": action}

            # Execution
            yield {"type": "executing_start", "tool": action.get("tool"),
                   "parameters": action.get("parameters")}

            # 安全验证
            is_safe, error = self._validate_action(action)
            if not is_safe:
                observation = f"❌ 安全验证失败: {error}"
                yield {"type": "executing_error", "error": observation}
            else:
                # 知识库验证（执行前检查是否有知识库支撑）
                has_knowledge = self._verify_knowledge_support(action, knowledge_refs)
                if not has_knowledge:
                    observation = "⚠️ 警告：该操作缺乏知识库支撑，执行风险较高"
                    yield {"type": "executing_warning", "warning": observation}

                result = self._execute_action(action)
                observation = self._format_result(result)
                yield {"type": "executing_end", "result": result}

            step = self.state.add_step(AgentPhase.EXECUTING, action=action,
                                       observation=observation)
            self._persist_step(step)

            # Observation
            yield {"type": "observing", "observation": observation}

            # 观察结果回流对话历史
            self.state.add_message('user', f"观察结果:\n{observation}")

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
                            kg_context: Optional[Dict] = None) -> str:
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

## 工作模式（ReAct）
1. Thought: 分析用户需求，制定执行计划
2. Action: 调用合适的工具获取数据（格式: {"tool": "xxx", "parameters": {...}}）
3. Observation: 观察执行结果
4. Thought: 基于结果继续分析或总结

## 输出格式
当你需要调用工具时，请使用以下JSON格式：
```json
{"tool": "query_database", "parameters": {"sql": "SELECT ..."}}
```

如果不需要工具，直接给出分析结论。
"""

        # 注入知识库引用
        if knowledge_refs:
            prompt += "\n## 参考知识库文档\n"
            for i, ref in enumerate(knowledge_refs, 1):
                prompt += f"[{i}] {ref['file']} (相似度: {ref['similarity']})\n"
                prompt += f"{ref['chunk']}\n\n"

        # 注入Skills
        if skills:
            prompt += "\n## 适用技能\n"
            for skill in skills:
                prompt += f"- {skill['name']}: {skill['description']}\n"
                if skill.get('prompt_template'):
                    prompt += f"  操作指南: {skill['prompt_template'][:200]}...\n"

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
        """LLM思考（基于完整对话历史，含先前的工具观察结果）"""
        messages = [
            {"role": "system", "content": system_prompt},
            *self.state.conversation_history,
        ]

        response, _ = call_llm(messages, model_id=self.model_id)
        return response

    def _decide_action(self, thought: str) -> Optional[Dict]:
        """基于思考提取工具调用 JSON

        容错 markdown 代码围栏与嵌套括号/字符串内的大括号，
        逐个尝试平衡的大括号对象，找到带 tool 字段的调用。
        """
        if not thought:
            return None
        # 剥离 ```json ... ``` 代码围栏（保留内部内容）
        fenced = re.search(r'```(?:json)?\s*(.*?)```', thought, re.DOTALL)
        if fenced:
            thought = fenced.group(1)

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
                return None
            candidate = thought[start:end + 1]
            try:
                obj = json.loads(candidate)
                if isinstance(obj, dict) and obj.get('tool'):
                    return obj
            except (json.JSONDecodeError, ValueError):
                pass
            # 前一个对象非工具调用，继续找下一个 {（如模型先输出了一段分析 JSON）
            start = thought.find('{', end)
        return None

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

    def _get_db_type(self) -> str:
        """获取当前数据库类型"""
        if self.db_conn_id:
            conn = get_db()
            row = conn.execute(
                "SELECT db_type FROM agent_db_connections WHERE id=?",
                (self.db_conn_id,)
            ).fetchone()
            if row:
                return row['db_type']
        return 'oracle'

    def get_state(self) -> Dict:
        """获取Agent状态"""
        return self.state.to_dict()
