"""Skills - 领域知识与操作指南
解决"做什么"的问题，为Agent提供操作指南和行业经验

双层技能池：
- 内置技能（DEFAULT_SKILLS，只读）
- 自动沉淀技能（agent_skills 表）：成功诊断后由 crystallize_skill 写入，
  按 trigger_keywords 参与意图匹配，支持 Curator 去重/淘汰防污染。
"""
import json
import re
from typing import Dict, List, Optional
from datetime import datetime, timedelta


class SkillManager:
    """技能管理器"""

    # 内置Skills（可扩展）
    DEFAULT_SKILLS = [
        {
            "name": "慢查询诊断",
            "db_type": "mysql",
            "category": "diagnosis",
            "description": "诊断MySQL慢查询问题",
            "prompt_template": """你是一个MySQL慢查询诊断专家。请按以下步骤分析：
1. 查询performance_schema.events_statements_summary_by_digest，找出执行时间最长的SQL
2. 分析这些SQL的执行计划（EXPLAIN）
3. 检查相关表的索引情况
4. 给出优化建议

注意：只执行SELECT查询，禁止修改数据。""",
            "required_tools": ["query_database"],
            "knowledge_tags": ["mysql", "performance", "optimization"]
        },
        {
            "name": "Oracle集群状态检查",
            "db_type": "oracle",
            "category": "diagnosis",
            "description": "检查Oracle RAC集群状态",
            "prompt_template": """你是一个Oracle RAC诊断专家。请按以下步骤检查：
1. 使用crsctl check crs检查集群状态
2. 使用srvctl status database检查数据库状态
3. 查询v$instance检查实例状态
4. 查询gv$session检查会话分布
5. 给出状态报告和建议

注意：只执行状态检查命令，禁止修改配置。""",
            "required_tools": ["execute_command", "query_database"],
            "knowledge_tags": ["oracle", "rac", "cluster"]
        },
        {
            "name": "数据库备份检查",
            "db_type": None,
            "category": "maintenance",
            "description": "检查数据库备份状态",
            "prompt_template": """你是一个数据库备份检查专家。请检查：
1. 最近的备份记录
2. 备份文件完整性
3. 备份策略是否符合要求
4. 给出备份状态报告

注意：只查询备份状态，不执行备份操作。""",
            "required_tools": ["query_database", "execute_command"],
            "knowledge_tags": ["backup", "recovery"]
        },
        {
            "name": "MySQL性能分析",
            "db_type": "mysql",
            "category": "diagnosis",
            "description": "分析MySQL数据库性能问题",
            "prompt_template": """你是一个MySQL性能分析专家。请按以下步骤分析：
1. 查询SHOW GLOBAL STATUS获取全局状态
2. 查询SHOW ENGINE INNODB STATUS获取InnoDB状态
3. 查询performance_schema.threads检查线程状态
4. 分析慢查询日志
5. 给出性能优化建议

注意：只执行状态查询，禁止修改配置。""",
            "required_tools": ["query_database", "execute_command"],
            "knowledge_tags": ["mysql", "performance", "innodb"]
        },
        {
            "name": "Oracle AWR报告分析",
            "db_type": "oracle",
            "category": "diagnosis",
            "description": "分析Oracle AWR性能报告",
            "prompt_template": """你是一个Oracle AWR分析专家。请按以下步骤分析：
1. 查询DBA_HIST_SNAPSHOT获取快照信息
2. 查询DBA_HIST_SQLSTAT获取SQL统计信息
3. 查询DBA_HIST_SYSMETRIC_HISTORY获取系统指标
4. 分析等待事件和Top SQL
5. 给出性能优化建议

注意：只查询AWR视图，禁止修改数据。""",
            "required_tools": ["query_database"],
            "knowledge_tags": ["oracle", "awr", "performance"]
        },
        {
            "name": "达梦数据库状态检查",
            "db_type": "dm",
            "category": "diagnosis",
            "description": "检查达梦数据库运行状态",
            "prompt_template": """你是一个达梦数据库诊断专家。请按以下步骤检查：
1. 查询v$database检查数据库状态
2. 查询v$instance检查实例状态
3. 查询v$session检查会话信息
4. 查询v$lock检查锁信息
5. 给出状态报告和建议

注意：只执行状态查询，禁止修改配置。""",
            "required_tools": ["query_database"],
            "knowledge_tags": ["dm", "status", "diagnosis"]
        },
        {
            "name": "PostgreSQL性能诊断",
            "db_type": "postgresql",
            "category": "diagnosis",
            "description": "诊断PostgreSQL性能问题",
            "prompt_template": """你是一个PostgreSQL性能诊断专家。请按以下步骤分析：
1. 查询pg_stat_activity分析当前会话与等待事件
2. 查询pg_stat_statements找出耗时最长的SQL
3. 分析相关表的执行计划（EXPLAIN ANALYZE）
4. 检查索引使用情况与autovacuum状态
5. 给出优化建议

注意：只执行SELECT查询，禁止修改数据。""",
            "required_tools": ["query_database"],
            "knowledge_tags": ["postgresql", "performance", "optimization"]
        },
        {
            "name": "Redis状态检查",
            "db_type": "redis",
            "category": "diagnosis",
            "description": "检查Redis运行状态与内存",
            "prompt_template": """你是一个Redis诊断专家。请按以下步骤检查：
1. 执行INFO server/memory/clients/stats获取运行状态
2. 执行SLOWLOG GET分析慢查询
3. 执行CLIENT LIST检查连接分布
4. 分析内存使用与淘汰策略（maxmemory-policy）
5. 给出状态报告与优化建议

注意：只执行只读命令，禁止FLUSHALL/CONFIG SET/SHUTDOWN等修改操作。""",
            "required_tools": ["execute_command"],
            "knowledge_tags": ["redis", "memory", "status"]
        }
    ]

    def __init__(self):
        self._skills = {}
        self._load_default_skills()
        self._load_db_skills()

    def _load_default_skills(self):
        """加载默认技能"""
        for skill in self.DEFAULT_SKILLS:
            self._skills[skill["name"]] = skill

    def _load_db_skills(self):
        """加载 DB 中 active 的自动沉淀技能（同名覆盖内置）"""
        try:
            from db.database import list_skills
            for skill in list_skills(active_only=True):
                self._skills[skill["name"]] = skill
        except Exception:
            pass

    def get_skill(self, name: str) -> Optional[Dict]:
        """获取技能"""
        return self._skills.get(name)

    def find_skills(self, db_type: Optional[str] = None,
                    category: Optional[str] = None) -> List[Dict]:
        """查找匹配的技能"""
        results = []
        for skill in self._skills.values():
            if db_type and skill.get("db_type") and skill["db_type"] != db_type:
                continue
            if category and skill.get("category") != category:
                continue
            results.append(skill)
        return results

    def match_skills_by_intent(self, user_question: str, db_type: str) -> List[Dict]:
        """根据用户意图匹配技能

        内置技能用硬编码关键词映射；自动沉淀技能按 trigger_keywords 动态匹配。
        """
        matched = []
        q = user_question.lower()

        # 1. 内置技能：关键词映射
        keywords_map = {
            "慢查询": ["慢查询诊断"],
            "性能": ["慢查询诊断", "MySQL性能分析", "Oracle AWR报告分析"],
            "awr": ["Oracle AWR报告分析"],
            "集群": ["Oracle集群状态检查"],
            "RAC": ["Oracle集群状态检查"],
            "备份": ["数据库备份检查"],
            "状态": ["Oracle集群状态检查", "达梦数据库状态检查"],
            "达梦": ["达梦数据库状态检查"],
            "dm": ["达梦数据库状态检查"],
            "postgres": ["PostgreSQL性能诊断"],
            "pg": ["PostgreSQL性能诊断"],
            "redis": ["Redis状态检查"],
        }

        for keyword, skill_names in keywords_map.items():
            if keyword.lower() in q:
                for name in skill_names:
                    skill = self._skills.get(name)
                    if skill and (not skill.get("db_type") or skill["db_type"] == db_type):
                        if skill not in matched:
                            matched.append(skill)

        # 2. 自动沉淀技能：trigger_keywords 命中（任一关键词出现在问题中）
        for skill in self._skills.values():
            if skill in matched:
                continue
            if skill.get('status') and skill['status'] != 'active':
                continue
            keywords = [str(k).strip().lower() for k in (skill.get('trigger_keywords') or [])
                        if str(k).strip()]
            if not keywords:
                continue
            if skill.get('db_type') and skill['db_type'] != db_type:
                continue
            if any(k in q for k in keywords):
                matched.append(skill)

        # v4.4 专家技能优先
        matched.sort(key=lambda s: (not bool(s.get('is_expert')),))
        return matched

    def get_all_skills(self) -> List[Dict]:
        """获取所有技能"""
        return list(self._skills.values())

    def add_skill(self, skill: Dict):
        """添加自定义技能（同时持久化到 agent_skills 表）"""
        self._skills[skill["name"]] = skill
        try:
            from db.database import save_skill
            save_skill(
                name=skill["name"],
                db_type=skill.get('db_type'),
                category=skill.get('category') or 'diagnosis',
                description=skill.get('description', ''),
                prompt_template=skill.get('prompt_template', ''),
                required_tools=skill.get('required_tools'),
                knowledge_tags=skill.get('knowledge_tags'),
                trigger_keywords=skill.get('trigger_keywords'),
                source_session=skill.get('source_session', ''),
                confidence=skill.get('confidence', 0.8),
                status=skill.get('status', 'active'),
                priority=skill.get('priority', 0),
            )
        except Exception as e:
            print(f"[Skill] 技能持久化失败: {e}")

    def remove_skill(self, name: str) -> bool:
        """移除技能（同时从 agent_skills 表删除）"""
        if name in self._skills:
            del self._skills[name]
            try:
                from db.database import delete_skill
                delete_skill(name)
            except Exception:
                pass
            return True
        return False

    # ==================== 自动沉淀（crystallize） ====================

    def crystallize_skill(self, trace: Dict) -> Optional[str]:
        """从一次成功诊断轨迹沉淀技能到 DB。

        trace: {question, db_type, steps, conclusion, session_id, model_id}
        - 先走 LLM 生成（可读步骤指南）；LLM 失败回退模板组合。
        - Curator 去重：同 db_type+category 且 trigger_keywords 重叠 ≥50% 的
          已有技能 → 合并更新（保留原名与 usage），不新增。

        返回技能名；失败返回 None（不抛出）。
        """
        try:
            from db.database import save_skill, get_skill_by_name
            skill = self._generate_skill(trace)
            if not skill or not skill.get('name'):
                return None

            merged, _ = self._dedupe_or_new(skill)
            name = merged['name']
            save_skill(
                name=name,
                db_type=merged.get('db_type') or trace.get('db_type'),
                category=merged.get('category') or 'diagnosis',
                description=merged.get('description', ''),
                prompt_template=merged.get('prompt_template', ''),
                required_tools=merged.get('required_tools'),
                knowledge_tags=merged.get('knowledge_tags'),
                trigger_keywords=merged.get('trigger_keywords'),
                source_session=trace.get('session_id', ''),
                confidence=merged.get('confidence', 0.8),
                status='active',
                priority=merged.get('priority', 0),
            )
            # 同步内存池
            db_skill = get_skill_by_name(name)
            if db_skill:
                self._skills[name] = db_skill
            return name
        except Exception as e:
            print(f"[Skill] 技能沉淀失败: {e}")
            return None

    def crystallize_from_document(self, text: str, db_type: Optional[str] = None,
                                  category: str = 'diagnosis',
                                  model_id: Optional[str] = None) -> Optional[str]:
        """从操作手册/文档正文沉淀技能到 DB。

        - 先走 LLM 提炼（可读步骤指南）；LLM 不可用回退文档摘录模板。
        - 同样经过 Curator 写时去重合并。

        返回技能名；失败返回 None（不抛出）。
        """
        try:
            from db.database import save_skill, get_skill_by_name
            if not text or not text.strip():
                return None
            skill = self._llm_skill_from_document(text, db_type, category, model_id)
            if not skill:
                skill = self._fallback_skill_from_document(text, db_type, category)
            if not skill or not skill.get('name'):
                return None

            merged, _ = self._dedupe_or_new(skill)
            name = merged['name']
            save_skill(
                name=name,
                db_type=merged.get('db_type') or db_type,
                category=merged.get('category') or category,
                description=merged.get('description', ''),
                prompt_template=merged.get('prompt_template', ''),
                required_tools=merged.get('required_tools'),
                knowledge_tags=merged.get('knowledge_tags'),
                trigger_keywords=merged.get('trigger_keywords'),
                source_session=merged.get('source_session', ''),
                confidence=merged.get('confidence', 0.8),
                status='active',
                priority=merged.get('priority', 10),   # 手动 SOP 高优先级（自动沉淀默认 0）
                is_expert=1,                           # v4.4 手动 SOP 标记为专家技能，匹配时优先
            )
            db_skill = get_skill_by_name(name)
            if db_skill:
                self._skills[name] = db_skill
            return name
        except Exception as e:
            print(f"[Skill] 文档技能沉淀失败: {e}")
            return None

    def _llm_skill_from_document(self, text: str, db_type: Optional[str],
                                 category: str, model_id: Optional[str]) -> Optional[Dict]:
        """LLM 从操作手册/文档提炼技能 JSON"""
        try:
            from utils import call_llm
            snippet = text[:6000]  # 截断控制 token
            prompt = f"""你是数据库运维专家。以下是用户提供的运维操作手册/问题修复流程文档。请将其沉淀为一个可复用技能（Skill），用于未来遇到同类问题时指导诊断与操作。

文档类型: {db_type or '通用'}
期望类别: {category or 'diagnosis'}

文档内容:
{snippet}

请输出一个 JSON 对象（不要任何其他文字、不要 markdown 围栏）:
{{
  "name": "简短技能名，如「MySQL连接数故障恢复」",
  "description": "一句话说明该技能解决什么问题",
  "category": "diagnosis 或 maintenance",
  "trigger_keywords": ["触发词数组：问题症状/错误码/指标名/对象名，5-10个，用于意图匹配"],
  "prompt_template": "操作指南：从文档提炼出可执行的诊断/修复步骤，含SQL/命令示例，600字内"
}}"""
            messages = [
                {"role": "system", "content": "你是一个数据库运维专家。只输出一个 JSON 对象，不要任何其他文字。"},
                {"role": "user", "content": prompt},
            ]
            response, err = call_llm(messages, model_id=model_id)
            if err or not response:
                return None
            content = response.strip()
            fenced = re.search(r'```(?:json)?\s*(.*?)```', content, re.DOTALL)
            if fenced:
                content = fenced.group(1)
            start, end = content.find('{'), content.rfind('}')
            if start == -1 or end == -1 or end <= start:
                return None
            obj = json.loads(content[start:end + 1])
            name = str(obj.get('name', '')).strip()
            if not name:
                return None
            return {
                'name': name,
                'db_type': db_type,
                'description': str(obj.get('description', '')).strip(),
                'category': str(obj.get('category', '') or category or 'diagnosis').strip(),
                'trigger_keywords': [str(k).strip() for k in (obj.get('trigger_keywords') or [])
                                     if str(k).strip()][:12],
                'prompt_template': str(obj.get('prompt_template', '')).strip(),
                'confidence': 0.8,
            }
        except Exception:
            return None

    def _fallback_skill_from_document(self, text: str, db_type: Optional[str],
                                      category: str) -> Optional[Dict]:
        """离线回退：从文档标题/正文摘录拼接技能（LLM 不可用时保证闭环可用）"""
        lines = [l.strip() for l in text.splitlines() if l.strip()]
        title = ''
        for l in lines[:30]:
            if l.startswith('#'):
                title = l.lstrip('#').strip()
                break
        if not title:
            title = lines[0][:30] if lines else '操作手册技能'
        title = re.sub(r'\s+', ' ', title).strip()

        name = self._extract_skill_name(title, db_type or '')
        keywords = self._extract_keywords_from_text(text)
        body = '\n'.join(lines)[:1500]
        template = (f"适用文档：{title}\n"
                    f"文档步骤摘录：\n{body}\n\n"
                    f"注意：执行变更类操作前需确认影响范围并获批准。")
        return {
            'name': name,
            'db_type': db_type,
            'description': f"根据操作手册「{title[:20]}」沉淀的技能",
            'category': category or 'diagnosis',
            'trigger_keywords': keywords,
            'prompt_template': template,
            'confidence': 0.6,
        }

    def _generate_skill(self, trace: Dict) -> Optional[Dict]:
        """生成技能：优先 LLM，失败回退模板"""
        skill = self._llm_generate_skill(trace)
        if skill:
            return skill
        return self._fallback_skill(trace)

    def _llm_generate_skill(self, trace: Dict) -> Optional[Dict]:
        """LLM 生成技能 JSON（name/description/category/trigger_keywords/prompt_template）"""
        try:
            from utils import call_llm
            steps_text = self._format_trace(trace)
            prompt = f"""你是数据库运维专家。以下是 Agent 对一次数据库问题的一次成功诊断轨迹。请将其沉淀为一个可复用技能，用于未来遇到同类问题时指导诊断。

用户问题: {trace.get('question', '')}
数据库类型: {trace.get('db_type') or '通用'}

诊断步骤:
{steps_text}

最终结论:
{trace.get('conclusion', '')}

请输出一个 JSON 对象（不要任何其他文字、不要 markdown 围栏）:
{{
  "name": "简短技能名，如「MySQL慢查询诊断」",
  "description": "一句话说明该技能解决什么问题",
  "category": "diagnosis 或 maintenance",
  "trigger_keywords": ["触发词数组：问题症状/错误码/指标名/表名，5-10个，用于下次意图匹配"],
  "prompt_template": "操作指南：按步骤说明如何诊断该类问题，含可执行SQL/命令示例，600字内"
}}"""
            messages = [
                {"role": "system", "content": "你是一个数据库运维专家。只输出一个 JSON 对象，不要任何其他文字。"},
                {"role": "user", "content": prompt},
            ]
            response, err = call_llm(messages, model_id=trace.get('model_id'))
            if err or not response:
                return None
            content = response.strip()
            fenced = re.search(r'```(?:json)?\s*(.*?)```', content, re.DOTALL)
            if fenced:
                content = fenced.group(1)
            start, end = content.find('{'), content.rfind('}')
            if start == -1 or end == -1 or end <= start:
                return None
            obj = json.loads(content[start:end + 1])
            name = str(obj.get('name', '')).strip()
            if not name:
                return None
            return {
                'name': name,
                'db_type': trace.get('db_type'),
                'description': str(obj.get('description', '')).strip(),
                'category': str(obj.get('category', 'diagnosis')).strip() or 'diagnosis',
                'trigger_keywords': [str(k).strip() for k in (obj.get('trigger_keywords') or [])
                                     if str(k).strip()][:12],
                'prompt_template': str(obj.get('prompt_template', '')).strip(),
            }
        except Exception:
            return None

    def _fallback_skill(self, trace: Dict) -> Optional[Dict]:
        """离线回退：从轨迹拼接技能（LLM 不可用/失败时保证闭环可用）"""
        question = trace.get('question', '')
        db_type = trace.get('db_type') or ''
        steps = trace.get('steps', [])
        conclusion = trace.get('conclusion', '')

        name = self._extract_skill_name(question, db_type)
        keywords = self._extract_keywords(question, steps, conclusion)

        lines = []
        if question:
            lines.append(f"适用场景：{question[:120]}")
        for i, st in enumerate(steps, 1):
            part = f"{i}. "
            thought = (st.get('thought') or '').strip()
            action = st.get('action') or {}
            obs = (st.get('observation') or '').strip()
            if thought:
                part += f"分析：{thought[:150]}。"
            if action:
                tool = action.get('tool', '')
                params = json.dumps(action.get('parameters', {}), ensure_ascii=False)
                part += f"执行 {tool}: {params[:200]}。"
            if obs:
                part += f"结果：{obs[:150]}。"
            lines.append(part)
        if conclusion:
            lines.append(f"结论：{conclusion[:300]}")
        lines.append("注意：仅执行只读操作，所有 SQL/命令需通过安全校验。")

        return {
            'name': name,
            'db_type': trace.get('db_type'),
            'description': f"{db_type or '通用'}问题诊断技能",
            'category': 'diagnosis',
            'trigger_keywords': keywords,
            'prompt_template': "\n".join(lines),
            'confidence': 0.6,
        }

    def _extract_skill_name(self, question: str, db_type: str) -> str:
        """从问题提取核心词作为技能名（LLM 不可用时）"""
        # 优先提取 4-10 字的连续中文短语（去掉常见问句语气词）
        cleaned = re.sub(r'[？?\s]', '', question)
        m = re.search(r'[一-龥]{4,10}', cleaned)
        core = m.group(0) if m else '问题诊断'
        # 去掉问句冗余后缀
        for tail in ('怎么办', '怎么处理', '如何排查', '是什么原因'):
            if core.endswith(tail):
                core = core[:-len(tail)]
                break
        prefix = db_type or '通用'
        return f"{prefix}_{core}"[:40]

    def _extract_keywords(self, question: str, steps: List[Dict],
                          conclusion: str) -> List[str]:
        """提取触发关键词：错误码/指标/症状词 + 问题/工具参数中的实体词"""
        text = ' '.join(filter(None, [question, conclusion or '']))
        for st in steps:
            action = st.get('action') or {}
            for v in (action.get('parameters') or {}).values():
                if isinstance(v, str):
                    text += ' ' + v
        return self._extract_keywords_from_text(text)

    @staticmethod
    def _extract_keywords_from_text(text: str, limit: int = 12) -> List[str]:
        """从任意文本提取触发关键词：错误码 / SQL 表名 / 常见症状与操作词"""
        keywords = []
        # 错误码（ORA-xxxxx / ERROR nnnn）
        for c in re.findall(r'ORA-\d+', text, re.I):
            keywords.append(c.upper())
        for c in re.findall(r'ERROR\s*\d+', text, re.I):
            keywords.append(c.upper().replace(' ', ''))
        # SQL 表名（FROM/JOIN/UPDATE/INTO/TABLE 后的标识符，取末段）
        for m in re.finditer(r'\b(?:FROM|JOIN|UPDATE|INTO|TABLE)\s+([A-Za-z_][A-Za-z0-9_.]*)',
                             text, re.I):
            tname = m.group(1).split('.')[-1]
            if 3 <= len(tname) <= 40 and tname.lower() not in ('dual',):
                keywords.append(tname)
        # 数据库参数/标识符（snake_case 4-40 字符，如 max_connections）
        for m in re.findall(r'\b[a-z][a-z0-9]*(?:_[a-z0-9]+)+\b', text):
            if 4 <= len(m) <= 40:
                keywords.append(m)
        # 常见症状/指标/操作词
        for kw in ('慢查询', '连接数', '锁等待', '死锁', '表空间', 'CPU', '内存',
                   '磁盘', '性能', '备份', '集群', '主从', '日志', '告警', '吞吐',
                   '重启', '故障', '修复', '参数', '扩容', '迁移'):
            if kw.lower() in text.lower():
                keywords.append(kw)

        # 保序去重
        seen = set()
        result = []
        for k in keywords:
            if k not in seen:
                seen.add(k)
                result.append(k)
        return result[:limit]

    def _format_trace(self, trace: Dict) -> str:
        """把诊断步骤序列格式化为文本（供 LLM 生成技能）"""
        lines = []
        for i, st in enumerate(trace.get('steps', []), 1):
            thought = (st.get('thought') or '').strip()
            action = st.get('action') or {}
            obs = (st.get('observation') or '').strip()
            line = f"{i}. "
            if thought:
                line += f"分析: {thought[:200]}\n   "
            if action:
                params = json.dumps(action.get('parameters', {}), ensure_ascii=False)
                line += f"工具: {action.get('tool', '')} {params[:300]}\n   "
            if obs:
                line += f"观察: {obs[:200]}"
            lines.append(line)
        return "\n".join(lines)

    # ==================== Curator（防技能库腐烂） ====================

    def _dedupe_or_new(self, new_skill: Dict):
        """Curator 写时去重：同 db_type+category 且 trigger_keywords 重叠 ≥50% 视为同技能。

        返回 (skill_dict, is_update)。合并时保留原技能名与 usage_count，
        仅当新技能 prompt_template 更长（更完整）才覆盖内容，防技能库漂移。
        """
        from db.database import list_skills
        new_kws = set(new_skill.get('trigger_keywords') or [])
        if not new_kws:
            return new_skill, False
        for exist in list_skills(active_only=True):
            if exist.get('db_type') != new_skill.get('db_type'):
                continue
            if exist.get('category') != new_skill.get('category'):
                continue
            exist_kws = set(exist.get('trigger_keywords') or [])
            if not exist_kws:
                continue
            overlap = len(new_kws & exist_kws) / len(new_kws)
            if overlap < 0.5:
                continue
            merged = dict(exist)
            new_pt = new_skill.get('prompt_template', '')
            if len(new_pt) > len(exist.get('prompt_template', '')):
                merged['prompt_template'] = new_pt
                merged['description'] = new_skill.get('description', exist.get('description'))
                merged['trigger_keywords'] = new_skill.get('trigger_keywords', exist.get('trigger_keywords'))
                merged['source_session'] = new_skill.get('source_session', exist.get('source_session'))
                merged['confidence'] = max(exist.get('confidence', 0), new_skill.get('confidence', 0.8))
            return merged, True
        return new_skill, False

    def curator_deprecate_stale(self, days: int = 30) -> List[str]:
        """Curator 淘汰：usage_count=0 且创建超过 days 天的技能标为 deprecated。

        返回被淘汰的技能名列表。保留数据可查，前端可删除。
        """
        try:
            from db.database import list_skills, set_skill_status
        except Exception:
            return []
        threshold = datetime.now() - timedelta(days=days)
        deprecated = []
        for skill in list_skills(active_only=True):
            if skill.get('usage_count', 0) > 0:
                continue
            created_at = skill.get('created_at')
            if not created_at:
                continue
            try:
                created = datetime.strptime(created_at, '%Y-%m-%d %H:%M:%S')
            except (ValueError, TypeError):
                continue
            if created < threshold:
                try:
                    set_skill_status(skill['name'], 'deprecated')
                    deprecated.append(skill['name'])
                except Exception:
                    continue
        return deprecated
