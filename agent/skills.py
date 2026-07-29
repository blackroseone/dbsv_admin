"""Skills - 领域知识与操作指南
解决"做什么"的问题，为Agent提供操作指南和行业经验
"""
from typing import Dict, List, Optional
import json


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
        }
    ]

    def __init__(self):
        self._skills = {}
        self._load_default_skills()

    def _load_default_skills(self):
        """加载默认技能"""
        for skill in self.DEFAULT_SKILLS:
            self._skills[skill["name"]] = skill

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

        使用关键词匹配进行意图识别
        """
        matched = []
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
        }

        for keyword, skill_names in keywords_map.items():
            if keyword.lower() in user_question.lower():
                for name in skill_names:
                    skill = self._skills.get(name)
                    if skill and (not skill.get("db_type") or skill["db_type"] == db_type):
                        if skill not in matched:
                            matched.append(skill)

        return matched

    def get_all_skills(self) -> List[Dict]:
        """获取所有技能"""
        return list(self._skills.values())

    def add_skill(self, skill: Dict):
        """添加自定义技能"""
        self._skills[skill["name"]] = skill

    def remove_skill(self, name: str) -> bool:
        """移除技能"""
        if name in self._skills:
            del self._skills[name]
            return True
        return False
