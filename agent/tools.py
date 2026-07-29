"""Agent工具定义 - MCP风格
每个工具包含：Info（声明/Schema）+ InvokableRun（实际执行）
"""
from typing import Dict, Any, Callable, List
from dataclasses import dataclass
import json


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
def query_database(params: Dict) -> Dict:
    """执行SQL查询"""
    sql = params["sql"]
    max_rows = params.get("max_rows", 100)

    # 实际执行逻辑由Agent核心引擎注入
    return {
        "columns": [],
        "rows": [],
        "row_count": 0,
        "note": "工具已注册，实际执行需要数据库连接"
    }


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
def execute_command(params: Dict) -> Dict:
    """执行SSH命令"""
    command = params["command"]
    timeout = params.get("timeout", 30)

    # 实际执行逻辑由Agent核心引擎注入
    return {
        "stdout": "",
        "stderr": "",
        "exit_code": 0,
        "note": "工具已注册，实际执行需要SSH连接"
    }


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
def get_schema_info(params: Dict) -> Dict:
    """获取Schema信息"""
    table_name = params.get("table_name")

    return {
        "tables": [],
        "note": "工具已注册，实际执行需要数据库连接"
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
def get_performance_metrics(params: Dict) -> Dict:
    """获取性能指标"""
    metric_type = params.get("metric_type", "sessions")

    return {
        "metrics": [],
        "note": "工具已注册，实际执行需要数据库连接"
    }


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
def retrieve_knowledge(params: Dict) -> Dict:
    """检索知识库"""
    query = params["query"]
    db_type = params.get("db_type")
    top_k = params.get("top_k", 5)

    return {
        "results": [],
        "note": "工具已注册，实际执行需要RAG引擎"
    }


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


def execute_tool(tool_name: str, parameters: Dict) -> Dict:
    """执行工具"""
    tool = TOOLS.get(tool_name)
    if not tool:
        return {"error": f"未知工具: {tool_name}"}

    try:
        return tool.run(parameters)
    except Exception as e:
        return {"error": f"工具执行失败: {str(e)}"}


def get_tool_names() -> List[str]:
    """获取所有工具名称"""
    return list(TOOLS.keys())
