"""Agent工具定义 - MCP风格
每个工具包含：Info（声明/Schema）+ InvokableRun（实际执行）
"""
from typing import Dict, Any, Callable, List, Optional
from dataclasses import dataclass, field
import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed

from agent.harness import Harness, OperationLevel
from agent.connectors import (
    load_db_conn, run_sql, load_ssh_conn, run_ssh_command,
    build_schema_query, build_metric_query,
)


# 批量 fan-out 并发上限：与引擎并行（max 4）嵌套时单回合最多 16 个连接，可控
FAN_OUT_CONCURRENCY = 4


@dataclass
class ToolContext:
    """工具执行上下文：携带连接配置、操作级别与会话范围（v4.0 批量）"""
    db_conn_id: Optional[str] = None
    ssh_conn_id: Optional[str] = None
    db_type: str = ''
    operation_level: OperationLevel = OperationLevel.READONLY
    targets: List[Dict] = field(default_factory=list)  # 会话范围已解析 target 列表
    session_id: Optional[str] = None                    # 批量执行取消感知用


# ==================== 批量 fan-out 辅助（v4.0） ====================

# 占位符替换：值仅来自已解析的拓扑/连接信息（白名单来源），
# 且替换后命令/SQL 会重新过 Harness 校验，防止节点名本身构成注入。
_PLACEHOLDER_RE = re.compile(r'\{(\w+)\}')


def _substitute_placeholders(text: str, target: Dict) -> str:
    """把命令/SQL 中的 {host}/{port}/{instance}/{node} 占位符替换为节点值。

    值仅取自拓扑/连接（host/port）与拓扑节点名（instance/node），
    均为受信来源；用户/模型自由文本不参与替换。
    """
    values = {
        'host': target.get('host') or '',
        'port': str(target.get('port') or ''),
        'instance': target.get('name') or '',
        'node': target.get('name') or '',
        'node_name': target.get('name') or '',
    }

    def repl(m):
        key = m.group(1)
        return values.get(key, m.group(0))

    return _PLACEHOLDER_RE.sub(repl, text)


def _load_conn(conn_type: str, conn_id: str):
    """按类型加载连接（fan-out 内逐节点用，避免循环依赖）"""
    if conn_type == 'ssh':
        return load_ssh_conn(conn_id)
    return load_db_conn(conn_id)


def _node_label(target: Dict) -> str:
    return target.get('name') or target.get('host') or str(target.get('conn_id') or '')


def _select_nodes(ctx: ToolContext, conn_type: str, target_name: Optional[str] = None):
    """筛选范围内该类型的已解析节点（按 conn_id 去重）。

    - 无范围（legacy 单连接会话）时用会话单连接合成单节点，保持旧行为；
    - 指定 target 时仅返回匹配节点（不存在→None, 错误信息）。
    """
    if ctx.targets:
        nodes = [t for t in ctx.targets
                 if t.get('type') == conn_type and t.get('resolved')]
    else:
        cid = ctx.db_conn_id if conn_type == 'db' else ctx.ssh_conn_id
        nodes = [{'type': conn_type, 'topo_id': None, 'conn_id': cid,
                  'name': '', 'host': None, 'port': None}] if cid else []
    seen, unique = set(), []
    for t in nodes:
        cid = t.get('conn_id')
        if cid:
            if cid in seen:
                continue
            seen.add(cid)
        unique.append(t)
    if not unique:
        return None, '范围内无已配置的该类型节点'
    if target_name:
        tname = str(target_name).strip()
        hits = [t for t in unique
                if tname == (t.get('name') or '')
                or tname == (t.get('host') or '')
                or tname in (t.get('name') or '')]
        if not hits:
            return None, f'目标节点不在范围: {target_name}'
        return hits[:1], None
    return unique, None


def _fan_out(ctx: ToolContext, conn_type: str, node_exec: Callable) -> Dict:
    """批量执行：对范围内该类型已解析节点并发执行 node_exec(target, conn_info)。

    - 单节点时直接返回 node_exec 结果（保持 legacy 行为，不包 batch_result）；
    - 多节点时节点间检查取消标志（M5），已取消节点标注不执行；
    - 返回 {"type":"batch_result","results":[{node, ok, output|error}, ...]}。
    """
    nodes, err = _select_nodes(ctx, conn_type)
    if err:
        return {"error": err}
    if len(nodes) == 1:
        conn_info, load_err = _load_conn(conn_type, nodes[0]['conn_id'])
        if load_err:
            return {"error": load_err}
        return node_exec(nodes[0], conn_info)

    from agent.engine import _is_cancelled  # 延迟导入避免循环依赖
    session_id = getattr(ctx, 'session_id', None)
    results = []
    with ThreadPoolExecutor(max_workers=min(FAN_OUT_CONCURRENCY, len(nodes))) as ex:
        futs = []
        for t in nodes:
            if session_id and _is_cancelled(session_id):
                results.append({"node": _node_label(t), "ok": False, "error": "已停止（用户取消）"})
                continue
            conn_info, load_err = _load_conn(conn_type, t['conn_id'])
            if load_err:
                results.append({"node": _node_label(t), "ok": False, "error": load_err})
                continue
            futs.append(ex.submit(node_exec, t, conn_info))
        for fut in as_completed(futs):
            try:
                results.append(fut.result())
            except Exception as e:
                results.append({"node": "", "ok": False, "error": f"执行异常: {e}"})
    return {"type": "batch_result", "results": results}


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
            "max_rows": {"type": "integer", "default": 100},
            "target": {"type": "string", "description": "可选，目标节点名（实例名/主机名）。不填则对会话范围内所有已配置数据库节点批量执行。"}
        },
        "required": ["sql"]
    }
)
def query_database(params: Dict, ctx: ToolContext) -> Dict:
    """执行SQL查询（需数据库连接配置；范围内多节点时批量执行）"""
    sql = params.get("sql", "")
    max_rows = params.get("max_rows", 100)
    target = params.get("target")

    has_db = bool(ctx and (ctx.db_conn_id
                 or any(t.get('type') == 'db' and t.get('resolved') for t in ctx.targets)))
    if not has_db:
        return {"error": "未配置数据库连接，无法执行查询"}

    # 预校验（范围主 db_type，快速失败）；逐节点校验在 fan-out 内按各节点 db_type 重验（H1）
    is_safe, err = Harness.validate_sql(sql, ctx.operation_level)
    if not is_safe:
        return {"error": f"SQL被安全校验拦截: {err}"}

    def node_exec(t: Dict, conn_info: Dict) -> Dict:
        node_sql = _substitute_placeholders(sql, t)
        node_db_type = (conn_info.get('db_type') or '').lower() or (ctx.db_type or '').lower()
        safe2, err2 = Harness.validate_sql(node_sql, ctx.operation_level)
        if not safe2:
            return {"node": _node_label(t), "ok": False,
                    "error": f"安全校验拦截({node_db_type}): {err2}"}
        result = run_sql(conn_info, node_sql, max_rows=max_rows)
        if 'error' in result:
            return {"node": _node_label(t), "ok": False, "error": result['error']}
        return {"node": _node_label(t), "ok": True,
                "columns": result.get('columns', []),
                "rows": result.get('rows', []),
                "row_count": result.get('row_count', 0)}

    if target:
        nodes, t_err = _select_nodes(ctx, 'db', target)
        if t_err:
            return {"error": t_err}
        conn_info, load_err = _load_conn('db', nodes[0]['conn_id'])
        if load_err:
            return {"error": load_err}
        return node_exec(nodes[0], conn_info)
    return _fan_out(ctx, 'db', node_exec)


@register_tool(
    name="execute_command",
    description="通过SSH执行数据库命令",
    parameters={
        "type": "object",
        "properties": {
            "command": {"type": "string", "description": "要执行的命令"},
            "timeout": {"type": "integer", "default": 30},
            "target": {"type": "string", "description": "可选，目标节点名（主机名/实例名）。不填则对会话范围内所有已配置服务器节点批量执行。"}
        },
        "required": ["command"]
    }
)
def execute_command(params: Dict, ctx: ToolContext) -> Dict:
    """执行SSH命令（需SSH连接配置；范围内多节点时批量执行）"""
    command = params.get("command", "")
    timeout = params.get("timeout", 30)
    target = params.get("target")

    has_ssh = bool(ctx and (ctx.ssh_conn_id
                  or any(t.get('type') == 'ssh' and t.get('resolved') for t in ctx.targets)))
    if not has_ssh:
        return {"error": "未配置SSH连接，无法执行命令"}

    # 命令白名单 + 级别校验（快速失败）；逐节点校验在 fan-out 内按各节点 db_type 重验（H1）
    is_safe, err = Harness.validate_command(command, ctx.db_type, ctx.operation_level)
    if not is_safe:
        return {"error": f"命令被安全校验拦截: {err}"}

    def node_exec(t: Dict, conn_info: Dict) -> Dict:
        node_cmd = _substitute_placeholders(command, t)
        node_db_type = (conn_info.get('db_type') or '').lower() or (ctx.db_type or '').lower()
        safe2, err2 = Harness.validate_command(node_cmd, node_db_type, ctx.operation_level)
        if not safe2:
            return {"node": _node_label(t), "ok": False,
                    "error": f"安全校验拦截({node_db_type}): {err2}"}
        result = run_ssh_command(conn_info, node_cmd, timeout=timeout)
        if 'error' in result:
            return {"node": _node_label(t), "ok": False, "error": result['error']}
        out = result.get('stdout', '')
        err_text = result.get('stderr', '')
        if err_text:
            out += f"\n[stderr] {err_text}"
        return {"node": _node_label(t), "ok": (result.get('exit_code', 0) == 0),
                "output": out.strip()[:3000]}

    if target:
        nodes, t_err = _select_nodes(ctx, 'ssh', target)
        if t_err:
            return {"error": t_err}
        conn_info, load_err = _load_conn('ssh', nodes[0]['conn_id'])
        if load_err:
            return {"error": load_err}
        return node_exec(nodes[0], conn_info)
    return _fan_out(ctx, 'ssh', node_exec)


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
    """获取Schema信息（表清单或表结构，需数据库连接；多节点按各节点 db_type 批量）"""
    table_name = params.get("table_name")

    has_db = bool(ctx and (ctx.db_conn_id
                 or any(t.get('type') == 'db' and t.get('resolved') for t in ctx.targets)))
    if not has_db:
        return {"error": "未配置数据库连接，无法获取Schema"}

    def node_exec(t: Dict, conn_info: Dict) -> Dict:
        node_db_type = (conn_info.get('db_type') or '').lower() or (ctx.db_type or '').lower()
        try:
            sql = build_schema_query(node_db_type, table_name)
        except ValueError as e:
            return {"node": _node_label(t), "ok": False, "error": str(e)}
        result = run_sql(conn_info, sql)
        if 'error' in result:
            return {"node": _node_label(t), "ok": False, "error": result['error']}
        return {"node": _node_label(t), "ok": True,
                "columns": result.get('columns', []),
                "rows": result.get('rows', []),
                "row_count": result.get('row_count', 0)}

    return _fan_out(ctx, 'db', node_exec)


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
    """获取性能指标（需数据库连接；多节点按各节点 db_type 批量）"""
    metric_type = params.get("metric_type", "sessions")

    has_db = bool(ctx and (ctx.db_conn_id
                 or any(t.get('type') == 'db' and t.get('resolved') for t in ctx.targets)))
    if not has_db:
        return {"error": "未配置数据库连接，无法获取性能指标"}

    def node_exec(t: Dict, conn_info: Dict) -> Dict:
        node_db_type = (conn_info.get('db_type') or '').lower() or (ctx.db_type or '').lower()
        try:
            sql = build_metric_query(node_db_type, metric_type)
        except ValueError as e:
            return {"node": _node_label(t), "ok": False, "error": str(e)}
        result = run_sql(conn_info, sql)
        if 'error' in result:
            return {"node": _node_label(t), "ok": False, "error": result['error']}
        return {"node": _node_label(t), "ok": True,
                "columns": result.get('columns', []),
                "rows": result.get('rows', []),
                "row_count": result.get('row_count', 0)}

    return _fan_out(ctx, 'db', node_exec)


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
