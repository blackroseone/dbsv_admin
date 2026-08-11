"""Agent工具定义 - MCP风格
每个工具包含：Info（声明/Schema）+ InvokableRun（实际执行）
"""
from typing import Dict, Any, Callable, List, Optional
from dataclasses import dataclass
import json

from agent.harness import Harness, OperationLevel
from agent.connectors import (
    load_db_conn, run_sql, load_ssh_conn, run_ssh_command,
    build_schema_query, build_metric_query,
)


@dataclass
class ToolContext:
    """工具执行上下文：携带连接配置与操作级别"""
    db_conn_id: Optional[str] = None
    ssh_conn_id: Optional[str] = None
    db_type: str = ''
    operation_level: OperationLevel = OperationLevel.READONLY


@dataclass
class ToolInfo:
    """工具信息"""
    name: str
    description: str
    parameters: Dict[str, Any]


@dataclass
class Tool:
    """工具"""
    info: ToolInfo
    run: Callable[[Dict], Dict]


# 工具注册表
TOOLS = {}


def register_tool(name: str, description: str, parameters: Dict):
    """注册工具装饰器"""
    def decorator(func: Callable[[Dict], Dict]):
        tool_info = ToolInfo(name=name, description=description, parameters=parameters)
        tool = Tool(info=tool_info, run=func)
        TOOLS[name] = tool
        return func
    return decorator


@register_tool(
    name="query_database",
    description="执行SQL查询（只读）",
    parameters={
        "type": "object",
        "properties": {
            "sql": {"type": "string", "description": "SQL查询语句"},
            "max_rows": {"type": "integer", "default": 100}
        },
        "required": ["sql"]
    }
)
def query_database(params: Dict, ctx: ToolContext) -> Dict:
    """执行SQL查询（需数据库连接配置）"""
    sql = params.get("sql", "")
    max_rows = params.get("max_rows", 100)

    if not ctx or not ctx.db_conn_id:
        return {"error": "未配置数据库连接，无法执行查询"}

    # 双重校验：即使绕过引擎，工具自身也拒绝非只读 SQL
    is_safe, err = Harness.validate_sql(sql, ctx.operation_level)
    if not is_safe:
        return {"error": f"SQL被安全校验拦截: {err}"}

    conn_info, load_err = load_db_conn(ctx.db_conn_id)
    if load_err:
        return {"error": load_err}
    return run_sql(conn_info, sql, max_rows=max_rows)


@register_tool(
    name="execute_command",
    description="通过SSH执行数据库命令",
    parameters={
        "type": "object",
        "properties": {
            "command": {"type": "string", "description": "要执行的命令"},
            "timeout": {"type": "integer", "default": 30}
        },
        "required": ["command"]
    }
)
def execute_command(params: Dict, ctx: ToolContext) -> Dict:
    """执行SSH命令（需SSH连接配置）"""
    command = params.get("command", "")
    timeout = params.get("timeout", 30)

    if not ctx or not ctx.ssh_conn_id:
        return {"error": "未配置SSH连接，无法执行命令"}

    # 命令白名单 + 级别校验（双重防护）
    is_safe, err = Harness.validate_command(command, ctx.db_type, ctx.operation_level)
    if not is_safe:
        return {"error": f"命令被安全校验拦截: {err}"}

    conn_info, load_err = load_ssh_conn(ctx.ssh_conn_id)
    if load_err:
        return {"error": load_err}
    return run_ssh_command(conn_info, command, timeout=timeout)


@register_tool(
    name="get_schema_info",
    description="获取数据库Schema信息",
    parameters={
        "type": "object",
        "properties": {
            "table_name": {"type": "string", "description": "可选，指定表名"}
        }
    }
)
def get_schema_info(params: Dict, ctx: ToolContext) -> Dict:
    """获取Schema信息（表清单或表结构，需数据库连接）"""
    table_name = params.get("table_name")

    if not ctx or not ctx.db_conn_id:
        return {"error": "未配置数据库连接，无法获取Schema"}

    try:
        sql = build_schema_query(ctx.db_type, table_name)
    except ValueError as e:
        return {"error": str(e)}

    conn_info, load_err = load_db_conn(ctx.db_conn_id)
    if load_err:
        return {"error": load_err}
    result = run_sql(conn_info, sql)
    if 'error' in result:
        return result
    return {
        "tables": result.get('rows', []),
        "columns": result.get('columns', []),
        "row_count": result.get('row_count', 0),
        "table_name": table_name or ''
    }


@register_tool(
    name="get_performance_metrics",
    description="获取数据库性能指标",
    parameters={
        "type": "object",
        "properties": {
            "metric_type": {
                "type": "string",
                "enum": ["sessions", "locks", "waits", "sql_stats", "table_stats"]
            }
        }
    }
)
def get_performance_metrics(params: Dict, ctx: ToolContext) -> Dict:
    """获取性能指标（需数据库连接）"""
    metric_type = params.get("metric_type", "sessions")

    if not ctx or not ctx.db_conn_id:
        return {"error": "未配置数据库连接，无法获取性能指标"}

    try:
        sql = build_metric_query(ctx.db_type, metric_type)
    except ValueError as e:
        return {"error": str(e)}

    conn_info, load_err = load_db_conn(ctx.db_conn_id)
    if load_err:
        return {"error": load_err}
    result = run_sql(conn_info, sql)
    if 'error' in result:
        return result
    return {
        "metrics": result.get('rows', []),
        "columns": result.get('columns', []),
        "row_count": result.get('row_count', 0),
        "metric_type": metric_type
    }


@register_tool(
    name="get_monitor_metrics",
    description="查询外部监控平台落库的监控指标（蓝鲸等，读本地 mon_metric_data）。"
                "参数 metric_type 为指标名（如 cpu_usage/mem_usage），object_name 为对象名，"
                "均可不填以查全部；返回 {columns, metrics} 表格。",
    parameters={
        "type": "object",
        "properties": {
            "metric_type": {"type": "string", "description": "指标名，留空查全部"},
            "object_type": {"type": "string", "description": "对象类型（host/db_instance/cluster），可留空"},
            "object_name": {"type": "string", "description": "对象名（主机名/实例名），可留空"},
            "limit": {"type": "integer", "default": 50}
        }
    }
)
def get_monitor_metrics(params: Dict, ctx: ToolContext) -> Dict:
    """查询落库的监控指标（本地 mon_metric_data，无需目标库连接）"""
    from db.database import get_mon_metrics

    result = get_mon_metrics(
        object_type=params.get('object_type') or None,
        object_name=params.get('object_name') or None,
        metric=params.get('metric_type') or None,
        limit=params.get('limit', 50),
    )
    return {
        "metrics": result.get('metrics', []),
        "columns": result.get('columns', []),
        "row_count": result.get('row_count', 0),
        "metric_type": params.get('metric_type') or 'all',
    }


@register_tool(
    name="retrieve_check",
    description="检索运维检查项（来自反编译的专家检查知识库）。按关键词/db_type/类别查检查项，"
                "返回其 SQL、命令、诊断建议与适用版本，用于指导问题诊断。",
    parameters={
        "type": "object",
        "properties": {
            "keyword": {"type": "string", "description": "检索关键词（问题/错误码/对象名），可留空"},
            "db_type": {"type": "string", "description": "数据库类型（mysql/oracle/dm/gaussdb 等），可留空"},
            "category": {"type": "string", "description": "检查项类别（check/ash/log），可留空"},
            "limit": {"type": "integer", "default": 10}
        }
    }
)
def retrieve_check(params: Dict, ctx: ToolContext) -> Dict:
    """检索运维检查项（知识图谱 check_item 实体）"""
    from db.kg_database import search_entities, get_entities_by_type

    keyword = (params.get('keyword') or '').strip()
    db_type = (params.get('db_type') or '').strip()
    category = (params.get('category') or '').strip()
    limit = min(int(params.get('limit', 10)), 50)

    if keyword:
        items = search_entities(keyword, entity_type='check_item', limit=max(limit * 3, 30))
    else:
        # 无关键词时取全量再按 db_type/category 过滤（properties 在 JSON 列，无法 SQL 过滤）
        items = get_entities_by_type('check_item', limit=10000)

    results = []
    for e in items:
        props = e.get('properties', {})
        if db_type and props.get('db_type', '') != db_type:
            continue
        if category and props.get('category', '') != category:
            continue
        results.append({
            'name': e.get('name', ''),
            'description': e.get('description', ''),
            'category': props.get('category', ''),
            'db_type': props.get('db_type', ''),
            'functions': props.get('functions', []),
            'sql': props.get('sql', []),
            'commands': props.get('commands', []),
            'knowledge_text': props.get('knowledge_text', []),
            'thresholds': props.get('thresholds', []),
        })
        if len(results) >= limit:
            break

    return {'results': results, 'count': len(results)}


@register_tool(
    name="retrieve_knowledge",
    description="从知识库检索相关文档",
    parameters={
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "检索查询"},
            "db_type": {"type": "string", "description": "数据库类型过滤"},
            "top_k": {"type": "integer", "default": 5}
        },
        "required": ["query"]
    }
)
def retrieve_knowledge(params: Dict, ctx: ToolContext) -> Dict:
    """检索知识库（向量相似度）"""
    query = params.get("query", "")
    db_type = params.get("db_type") or (ctx.db_type if ctx else '')
    top_k = params.get("top_k", 5)

    from rag.embedder import Embedder
    embedder = Embedder()
    results = embedder.similarity_search(query, db_type=db_type or None, top_k=top_k)
    return {"results": results, "count": len(results)}


def get_tool_schemas() -> List[Dict]:
    """获取所有工具的JSON Schema（用于LLM Function Calling）"""
    schemas = []
    for tool in TOOLS.values():
        schemas.append({
            "type": "function",
            "function": {
                "name": tool.info.name,
                "description": tool.info.description,
                "parameters": tool.info.parameters
            }
        })
    return schemas


def execute_tool(tool_name: str, parameters: Dict, ctx: Optional[ToolContext] = None) -> Dict:
    """执行工具

    Args:
        tool_name: 工具名
        parameters: 工具参数
        ctx: 工具上下文（连接配置 + 操作级别），由引擎注入
    """
    tool = TOOLS.get(tool_name)
    if not tool:
        return {"error": f"未知工具: {tool_name}"}

    try:
        return tool.run(parameters, ctx)
    except Exception as e:
        return {"error": f"工具执行失败: {str(e)}"}


def get_tool_names() -> List[str]:
    """获取所有工具名称"""
    return list(TOOLS.keys())
