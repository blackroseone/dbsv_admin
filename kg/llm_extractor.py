# -*- coding: utf-8 -*-
"""
知识图谱 LLM 实体提取器
使用大模型从文本中提取实体和关系
"""
import json
import re
from typing import List, Dict
from utils import call_llm

# ==================== Prompt 模板 ====================

ENTITY_EXTRACTION_PROMPT = """你是一个数据库领域知识图谱构建专家。请从以下文本中提取结构化实体和关系。

## 提取要求

1. **实体类型**：
   - `database_product`：数据库产品（如 MySQL, Oracle, OceanBase）
   - `version`：版本号（如 8.0.32, 19c）
   - `parameter`：配置参数（如 innodb_buffer_pool_size）
   - `sql_statement`：SQL 语句类型（如 SELECT, CREATE TABLE）
   - `function`：函数（如 COUNT(), TO_CHAR()）
   - `system_view`：系统视图（如 v$session, information_schema）
   - `error_code`：错误码（如 ORA-01555）
   - `command_tool`：命令行工具（如 mysqldump, obd）
   - `architecture`：架构/部署模式（如 主从复制, MGR, RAC）
   - `performance_metric`：性能指标（如 QPS, TPS, RT）
   - `concept`：概念（如 ACID, MVCC, 索引）
   - `troubleshooting`：故障场景（如 连接数爆满, 慢查询）
   - `operating_system`：操作系统（如 CentOS, RHEL）
   - `hardware`：硬件（如 CPU, 内存, SSD）

2. **关系类型**：
   - `belongs_to`：属于
   - `compatible_with`：兼容
   - `incompatible_with`：不兼容
   - `alternative_to`：替代方案
   - `requires`：依赖/要求
   - `has_parameter`：拥有参数
   - `similar_to`：相似/对应
   - `part_of`：组成部分
   - `causes`：导致
   - `solves`：解决
   - `related_to`：相关

3. **输出格式**：
   必须以 JSON 格式输出，不要包含任何其他文本：

```json
{
  "entities": [
    {
      "entity_type": "实体类型",
      "name": "实体名称（原文中的形式）",
      "normalized_name": "规范化名称（小写、去空格）",
      "aliases": ["别名1", "别名2"],
      "description": "简要描述",
      "confidence": 0.95
    }
  ],
  "relationships": [
    {
      "from_entity": "源实体名称",
      "from_type": "源实体类型",
      "to_entity": "目标实体名称",
      "to_type": "目标实体类型",
      "relation_type": "关系类型",
      "confidence": 0.9
    }
  ]
}
```

## 提取原则

- 只提取文本中明确提及的实体，不要编造
- 优先提取数据库领域的专业实体
- 关系必须有明确的文本依据
- 置信度范围 0.0-1.0，基于文本明确程度
- 如果某个类型没有实体，返回空数组

## 待提取文本

{text}

请直接输出 JSON，不要添加任何解释或标记："""


RELATION_EXTRACTION_PROMPT = """你是一个数据库领域知识图谱关系推理专家。请分析以下实体列表，推断它们之间可能的关系。

## 已知实体

{entities}

## 原始文本片段

{text}

## 关系类型

- `belongs_to`：属于（如 MySQL 8.0 属于 MySQL）
- `compatible_with`：兼容（如 GaussDB 兼容 MySQL 协议）
- `incompatible_with`：不兼容
- `alternative_to`：替代方案（如 TiDB 是 MySQL 的替代）
- `requires`：依赖/要求（如 MySQL 8.0 要求 CentOS 7+）
- `has_parameter`：拥有参数
- `similar_to`：相似/对应（如 OceanBase 的 ob_tcp_invited_nodes 对应 MySQL 的 bind-address）
- `part_of`：组成部分
- `causes`：导致（如 连接数爆满 导致 业务中断）
- `solves`：解决（如 增加 innodb_buffer_pool_size 解决 缓存不足）
- `related_to`：相关

## 输出格式

```json
{
  "relationships": [
    {
      "from_entity": "源实体名称",
      "from_type": "源实体类型",
      "to_entity": "目标实体名称",
      "to_type": "目标实体类型",
      "relation_type": "关系类型",
      "confidence": 0.9,
      "reason": "推理依据"
    }
  ]
}
```

## 推理原则

- 只推断有明确文本依据或强领域知识支持的关系
- 置信度范围 0.0-1.0
- 不要编造关系，不确定的不输出
- 优先推断直接关系，避免过度推理

请直接输出 JSON："""


# ==================== LLM 提取函数 ====================

def extract_entities_with_llm(text: str, max_length: int = 4000) -> List[Dict]:
    """使用 LLM 从文本中提取实体

    Args:
        text: 待提取的文本
        max_length: 最大处理长度（避免超出上下文限制）

    Returns:
        实体列表
    """
    # 截断文本
    truncated = text[:max_length]
    if len(text) > max_length:
        truncated = text[:max_length].rsplit('\n', 1)[0] + '\n...'

    prompt = ENTITY_EXTRACTION_PROMPT.format(text=truncated)

    messages = [
        {"role": "system", "content": "你是一个数据库领域知识图谱构建专家。"},
        {"role": "user", "content": prompt}
    ]

    try:
        response, error = call_llm(messages)
        if error or not response:
            print(f"[KG LLM Extractor] LLM 调用失败: {error}")
            return []

        # 解析 JSON
        result = _parse_json_response(response)
        if not result:
            return []

        entities = result.get('entities', [])

        # 添加来源信息
        for entity in entities:
            entity['extract_method'] = 'llm'
            entity['source_text'] = truncated[:200]  # 保留部分原文用于调试

        return entities

    except Exception as e:
        print(f"[KG LLM Extractor] 提取失败: {e}")
        return []


def extract_relations_with_llm(text: str, entities: List[Dict], max_length: int = 3000) -> List[Dict]:
    """使用 LLM 推断实体间关系

    Args:
        text: 原始文本
        entities: 已提取的实体列表
        max_length: 最大处理长度

    Returns:
        关系列表
    """
    if len(entities) < 2:
        return []

    # 格式化实体列表
    entity_lines = []
    for e in entities:
        entity_lines.append(f"- [{e.get('entity_type', 'unknown')}] {e.get('name', 'unknown')}")
    entity_text = '\n'.join(entity_lines)

    # 截断文本
    truncated = text[:max_length]

    prompt = RELATION_EXTRACTION_PROMPT.format(
        entities=entity_text,
        text=truncated
    )

    messages = [
        {"role": "system", "content": "你是一个数据库领域知识图谱关系推理专家。"},
        {"role": "user", "content": prompt}
    ]

    try:
        response, error = call_llm(messages)
        if error or not response:
            print(f"[KG LLM Extractor] 关系提取 LLM 调用失败: {error}")
            return []

        result = _parse_json_response(response)
        if not result:
            return []

        relationships = result.get('relationships', [])

        # 添加来源信息
        for rel in relationships:
            rel['extract_method'] = 'llm'

        return relationships

    except Exception as e:
        print(f"[KG LLM Extractor] 关系提取失败: {e}")
        return []


def extract_entities_and_relations(text: str, db_type: str = None) -> Dict:
    """完整的 LLM 实体和关系提取

    Args:
        text: 待提取的文本
        db_type: 数据库类型（用于上下文）

    Returns:
        {'entities': [...], 'relationships': [...]}
    """
    # 提取实体
    entities = extract_entities_with_llm(text)

    # 提取关系
    relationships = []
    if len(entities) >= 2:
        relationships = extract_relations_with_llm(text, entities)

    return {
        'entities': entities,
        'relationships': relationships
    }


# ==================== 辅助函数 ====================

def _parse_json_response(response: str) -> Dict:
    """从 LLM 响应中解析 JSON"""
    if not response:
        return {}

    # 尝试直接解析
    try:
        return json.loads(response.strip())
    except json.JSONDecodeError:
        pass

    # 尝试提取 JSON 代码块
    json_pattern = re.compile(r'```(?:json)?\s*(.*?)\s*```', re.DOTALL)
    matches = json_pattern.findall(response)

    for match in matches:
        try:
            return json.loads(match.strip())
        except json.JSONDecodeError:
            continue

    # 尝试提取花括号包裹的内容
    try:
        start = response.index('{')
        end = response.rindex('}')
        return json.loads(response[start:end+1])
    except (ValueError, json.JSONDecodeError):
        pass

    print(f"[KG LLM Extractor] 无法解析 JSON: {response[:200]}")
    return {}


def _merge_entities(rule_entities: List[Dict], llm_entities: List[Dict]) -> List[Dict]:
    """合并规则提取和 LLM 提取的实体，去重"""
    entity_map = {}

    # 先添加规则实体（置信度更高）
    for e in rule_entities:
        key = (e.get('entity_type'), e.get('normalized_name', e.get('name', '').lower()))
        entity_map[key] = e

    # 再添加 LLM 实体（如果未重复）
    for e in llm_entities:
        key = (e.get('entity_type'), e.get('normalized_name', e.get('name', '').lower()))
        if key not in entity_map:
            entity_map[key] = e
        else:
            # 合并别名
            existing = entity_map[key]
            new_aliases = set(existing.get('aliases', [])) | set(e.get('aliases', []))
            existing['aliases'] = list(new_aliases)
            # 取更高置信度
            existing['confidence'] = max(existing.get('confidence', 0), e.get('confidence', 0))

    return list(entity_map.values())


def _merge_relationships(rule_rels: List[Dict], llm_rels: List[Dict]) -> List[Dict]:
    """合并规则推断和 LLM 提取的关系，去重"""
    rel_map = {}

    for rel in rule_rels + llm_rels:
        # 构建关系键
        from_name = rel.get('from_entity', {}).get('name', '') if isinstance(rel.get('from_entity'), dict) else rel.get('from_entity', '')
        to_name = rel.get('to_entity', {}).get('name', '') if isinstance(rel.get('to_entity'), dict) else rel.get('to_entity', '')
        rel_type = rel.get('relation_type', '')

        key = (from_name.lower(), to_name.lower(), rel_type.lower())

        if key not in rel_map:
            rel_map[key] = rel
        else:
            # 取更高置信度
            existing = rel_map[key]
            existing['confidence'] = max(existing.get('confidence', 0), rel.get('confidence', 0))

    return list(rel_map.values())
