# -*- coding: utf-8 -*-
"""Agent 会话范围解析：拓扑节点 → SSH/DB 连接的消歧匹配

职责：
- 拓扑树（topo_servers / topo_instances）与 agent_ssh_connections /
  agent_db_connections 之间的对应关系解析；
- 解析策略：显式钉定（topo_server_id / topo_instance_id）优先 → 按
  主机[+端口+db_type+库] 自动匹配 → 多候选置 ambiguous（绝不随意取一个）；
- 未匹配节点返回 suggest（host/port/db_type 等），供前端一键补配预填。

注意：topo_instances 本身无 host/db_type 列，host 取自父 topo_servers、
db_type 取自所属 topo_resource_pools（池内同型是常态，跨池勾选即混型）。

使用方：routes/agent.py 的 /api/agent/scope/resolve、agent/engine.py 的 target 列表构建。
"""
from typing import Dict, List, Optional, Set

from db.database import get_db


def _normalize_host(host: str) -> str:
    """主机名/内网IP 规范化：去首尾空白并转小写（大小写不敏感匹配）"""
    return (host or '').strip().lower()


def _load_ssh_conn_row(conn_id: str) -> Optional[Dict]:
    conn = get_db()
    row = conn.execute(
        "SELECT id, name, host, port, username, db_type, status, topo_server_id "
        "FROM agent_ssh_connections WHERE id=?", (conn_id,)).fetchone()
    return dict(row) if row else None


def _load_db_conn_row(conn_id: str) -> Optional[Dict]:
    conn = get_db()
    row = conn.execute(
        "SELECT id, name, db_type, host, port, username, database, sid, service_name, "
        "status, topo_instance_id FROM agent_db_connections WHERE id=?",
        (conn_id,)).fetchone()
    return dict(row) if row else None


def _server_row(server_id: str) -> Optional[Dict]:
    conn = get_db()
    row = conn.execute(
        "SELECT s.*, rp.db_type AS pool_db_type "
        "FROM topo_servers s LEFT JOIN topo_resource_pools rp "
        "  ON s.resource_pool_id = rp.id WHERE s.id=?", (server_id,)).fetchone()
    return dict(row) if row else None


def _instance_row(instance_id: str) -> Optional[Dict]:
    conn = get_db()
    row = conn.execute(
        "SELECT i.*, s.host AS server_host, rp.db_type AS pool_db_type "
        "FROM topo_instances i "
        "JOIN topo_servers s ON i.server_id = s.id "
        "LEFT JOIN topo_resource_pools rp ON s.resource_pool_id = rp.id "
        "WHERE i.id=?", (instance_id,)).fetchone()
    return dict(row) if row else None


def _auto_ssh_match(server_host: str) -> Dict:
    """按规范化主机匹配活跃 SSH 连接；返回 {conn_id, ambiguous}"""
    conn = get_db()
    host = _normalize_host(server_host)
    if not host:
        return {'conn_id': None, 'ambiguous': False}
    rows = conn.execute(
        "SELECT id, host FROM agent_ssh_connections WHERE status='active'").fetchall()
    hits = [r['id'] for r in rows if _normalize_host(r['host']) == host]
    if len(hits) == 1:
        return {'conn_id': hits[0], 'ambiguous': False}
    return {'conn_id': None, 'ambiguous': len(hits) > 1}


def _auto_db_match(host: str, port, db_type: str, database: Optional[str]) -> Dict:
    """按 主机+端口+db_type+库 匹配活跃 DB 连接；返回 {conn_id, ambiguous}

    库过滤仅当拓扑实例显式声明 database 时才收紧（否则同机同端口多库连接
    天然 ambiguous，属保守行为）。
    """
    conn = get_db()
    norm_host = _normalize_host(host)
    if not norm_host:
        return {'conn_id': None, 'ambiguous': False}
    rows = conn.execute(
        "SELECT id, host, port, db_type, database FROM agent_db_connections "
        "WHERE status='active'").fetchall()
    hits = []
    for r in rows:
        if _normalize_host(r['host']) != norm_host:
            continue
        if (r['db_type'] or '').lower() != (db_type or '').lower():
            continue
        if port and r['port'] and int(r['port']) != int(port):
            continue
        # 实例显式声明库时，仅匹配库名严格相等的连接（空库连接不匹配，需人工钉定）；
        # 实例未声明库时不收紧，多候选即 ambiguous。
        if database and (r['database'] or '') != database:
            continue
        hits.append(r['id'])
    if len(hits) == 1:
        return {'conn_id': hits[0], 'ambiguous': False}
    return {'conn_id': None, 'ambiguous': len(hits) > 1}


def resolve_target(target: Dict) -> Optional[Dict]:
    """解析单个 target 为可执行/可展示的完整节点信息。

    target: {type:'ssh'|'db', topo_id?, conn_id?, name?}
    - 显式 conn_id 且无 topo_id：legacy/已指定连接，直接加载（match='manual'）；
    - 有 topo_id：钉定 → 自动匹配 → 未匹配（suggest/ambiguous）。
    返回 None 仅当 target 类型非法。
    """
    ttype = target.get('type')
    if ttype not in ('ssh', 'db'):
        return None
    topo_id = target.get('topo_id')
    conn_id = target.get('conn_id')
    out = {
        'type': ttype,
        'topo_id': topo_id,
        'conn_id': conn_id,
        'name': target.get('name', ''),
        'conn_name': '',
        'host': None, 'port': None, 'db_type': None,
        'resolved': False, 'match': None, 'ambiguous': False,
        'suggest': None,
    }

    # 路径A：显式连接（legacy / 前端已指定 conn_id；无拓扑名，name=连接名）
    if conn_id and not topo_id:
        row = _load_ssh_conn_row(conn_id) if ttype == 'ssh' else _load_db_conn_row(conn_id)
        if row:
            out.update({
                'name': out['name'] or row['name'],
                'conn_name': row['name'],
                'host': row.get('host'),
                'port': row.get('port'),
                'db_type': row.get('db_type'),
                'resolved': True,
                'match': 'manual',
            })
        return out

    conn = get_db()
    if ttype == 'ssh':
        server = _server_row(topo_id) if topo_id else None
        if not server:
            return out
        # name 保留拓扑节点名（模型按拓扑名引用节点）；连接名单独放 conn_name
        out['name'] = out['name'] or server['name']
        out['host'] = server.get('host')
        out['db_type'] = server.get('pool_db_type')
        pin = conn.execute(
            "SELECT id FROM agent_ssh_connections "
            "WHERE topo_server_id=? AND status='active'", (server['id'],)).fetchone()
        if pin:
            row = _load_ssh_conn_row(pin['id'])
            out.update({'conn_id': row['id'], 'host': row['host'],
                        'port': row['port'], 'db_type': row['db_type'],
                        'conn_name': row['name'],
                        'resolved': True, 'match': 'pinned'})
            return out
        m = _auto_ssh_match(server.get('host'))
        if m['conn_id']:
            row = _load_ssh_conn_row(m['conn_id'])
            out.update({'conn_id': row['id'], 'host': row['host'],
                        'port': row['port'], 'db_type': row['db_type'],
                        'conn_name': row['name'],
                        'resolved': True, 'match': 'auto'})
        else:
            out['ambiguous'] = m['ambiguous']
            out['suggest'] = {'host': server.get('host'), 'port': 22,
                              'db_type': server.get('pool_db_type')}
        return out

    # ttype == 'db'
    inst = _instance_row(topo_id) if topo_id else None
    if not inst:
        return out
    out['name'] = out['name'] or inst['name']
    out['host'] = inst.get('server_host')
    out['port'] = inst.get('port')
    out['db_type'] = inst.get('pool_db_type')
    pin = conn.execute(
        "SELECT id FROM agent_db_connections "
        "WHERE topo_instance_id=? AND status='active'", (inst['id'],)).fetchone()
    if pin:
        row = _load_db_conn_row(pin['id'])
        out.update({'conn_id': row['id'], 'host': row['host'],
                    'port': row['port'], 'db_type': row['db_type'],
                    'conn_name': row['name'],
                    'resolved': True, 'match': 'pinned'})
        return out
    m = _auto_db_match(inst.get('server_host'), inst.get('port'),
                       inst.get('pool_db_type'), inst.get('database'))
    if m['conn_id']:
        row = _load_db_conn_row(m['conn_id'])
        out.update({'conn_id': row['id'], 'host': row['host'],
                    'port': row['port'], 'db_type': row['db_type'],
                    'conn_name': row['name'],
                    'resolved': True, 'match': 'auto'})
    else:
        out['ambiguous'] = m['ambiguous']
        out['suggest'] = {'host': inst.get('server_host'), 'port': inst.get('port'),
                          'db_type': inst.get('pool_db_type'),
                          'database': inst.get('database'), 'sid': inst.get('sid'),
                          'service_name': inst.get('service_name')}
    return out


def resolve_scope(targets: List[Dict]) -> List[Dict]:
    """批量解析 targets；保留未解析项（前端展示 ⚠️，引擎只对 resolved 执行）"""
    resolved = []
    for t in targets or []:
        r = resolve_target(t)
        if r is not None:
            resolved.append(r)
    return resolved


def scope_labels(targets: List[Dict]) -> Set[str]:
    """收集范围节点的名称集合（name/host/conn_name），用于范围外 target 检测"""
    labels = set()
    for t in targets or []:
        for key in ('name', 'conn_name', 'host'):
            val = (t.get(key) or '').strip()
            if val:
                labels.add(val)
    return labels


def scope_db_types(targets: List[Dict]) -> Dict:
    """范围数据库类型集合与混型标记（混型守卫与前端警示用）"""
    types = sorted({(t.get('db_type') or '').lower() for t in targets or []
                    if t.get('db_type')})
    return {'db_types': types, 'mixed': len(types) > 1}
