# -*- coding: utf-8 -*-
"""Agent 工具连接器：数据库/SSH 连接的加载与真实执行

驱动依赖（缺失时工具返回提示而非崩溃）：
- MySQL 系（mysql/tdsql/oceanbase/goldendb）: pymysql
- Oracle: oracledb（thin 模式，无需安装客户端）
- GaussDB: psycopg2
- 达梦 DM: dmPython（可选）
- SSH: paramiko
"""
import io
import re
from typing import Dict, List, Optional, Tuple

from db.database import get_db
from utils import decrypt_secret


def _safe_identifier(name: str) -> Optional[str]:
    """校验表名/标识符，仅允许 字母数字下划线美元符井号（可含 schema. 前缀）

    防止将用户输入直接拼入 SQL（如 SHOW CREATE TABLE / WHERE table_name）。
    返回规范化后的标识符；非法返回 None。
    """
    if not name:
        return None
    name = name.strip()
    parts = name.split('.')
    if len(parts) > 2:
        return None
    for part in parts:
        if re.match(r'^[A-Za-z_][A-Za-z0-9_$#]*$', part) is None:
            return None
    return '.'.join(parts)


def load_db_conn(db_conn_id: str) -> Tuple[Optional[Dict], Optional[str]]:
    """加载数据库连接配置并解密密码

    Returns:
        (conn_info, error)；error 非空表示加载失败
    """
    if not db_conn_id:
        return None, "未配置数据库连接"
    conn = get_db()
    row = conn.execute(
        "SELECT id, name, db_type, host, port, username, password_encrypted, "
        "database, sid, service_name FROM agent_db_connections WHERE id=?",
        (db_conn_id,)
    ).fetchone()
    if not row:
        return None, f"数据库连接不存在: {db_conn_id}"
    info = dict(row)
    info['password'] = decrypt_secret(info.pop('password_encrypted', '') or '')
    return info, None


def load_ssh_conn(ssh_conn_id: str) -> Tuple[Optional[Dict], Optional[str]]:
    """加载 SSH 连接配置并解密凭据

    Returns:
        (conn_info, error)；error 非空表示加载失败
    """
    if not ssh_conn_id:
        return None, "未配置SSH连接"
    conn = get_db()
    row = conn.execute(
        "SELECT id, name, host, port, username, auth_type, password_encrypted, "
        "private_key_encrypted, passphrase_encrypted "
        "FROM agent_ssh_connections WHERE id=?",
        (ssh_conn_id,)
    ).fetchone()
    if not row:
        return None, f"SSH连接不存在: {ssh_conn_id}"
    info = dict(row)
    info['password'] = decrypt_secret(info.pop('password_encrypted', '') or '')
    info['private_key'] = decrypt_secret(info.pop('private_key_encrypted', '') or '')
    info['passphrase'] = decrypt_secret(info.pop('passphrase_encrypted', '') or '')
    return info, None


def run_sql(conn_info: Dict, sql: str, max_rows: int = 100, timeout: int = 10) -> Dict:
    """按 db_type 执行 SQL 查询

    Returns:
        {'columns': [...], 'rows': [[...]], 'row_count': N} 或 {'error': ...}
    """
    db_type = (conn_info.get('db_type') or '').lower()
    if db_type in ('mysql', 'tdsql', 'oceanbase', 'goldendb'):
        return _query_pymysql(conn_info, sql, max_rows, timeout)
    if db_type == 'oracle':
        return _query_oracledb(conn_info, sql, max_rows, timeout)
    if db_type == 'gaussdb':
        return _query_psycopg2(conn_info, sql, max_rows, timeout)
    if db_type == 'dm':
        return _query_dmpython(conn_info, sql, max_rows, timeout)
    return {"error": f"暂不支持该数据库类型的连接执行: {db_type}"}


def _query_pymysql(conn_info: Dict, sql: str, max_rows: int, timeout: int) -> Dict:
    try:
        import pymysql
    except ImportError:
        return {"error": "需要安装 pymysql 才能查询 MySQL 系数据库（pip install pymysql）"}
    try:
        conn = pymysql.connect(
            host=conn_info.get('host', ''),
            port=int(conn_info.get('port') or 3306),
            user=conn_info.get('username', ''),
            password=conn_info.get('password', ''),
            database=conn_info.get('database') or None,
            charset='utf8mb4',
            connect_timeout=timeout,
            read_timeout=timeout,
        )
    except Exception as e:
        return {"error": f"数据库连接失败: {e}"}
    try:
        cur = conn.cursor()
        cur.execute(sql)
        if cur.description:
            columns = [d[0] for d in cur.description]
            rows = [list(r) for r in cur.fetchmany(max_rows)]
        else:
            columns, rows = [], []
        return {"columns": columns, "rows": rows, "row_count": len(rows)}
    except Exception as e:
        return {"error": f"数据库查询失败: {e}"}
    finally:
        conn.close()


def _query_oracledb(conn_info: Dict, sql: str, max_rows: int, timeout: int) -> Dict:
    try:
        import oracledb
    except ImportError:
        return {"error": "需要安装 oracledb 才能查询 Oracle 数据库（pip install oracledb）"}
    try:
        host = conn_info.get('host', '')
        port = conn_info.get('port') or 1521
        service = conn_info.get('service_name')
        sid = conn_info.get('sid')
        if service:
            dsn = f"{host}:{port}/{service}"
        elif sid:
            dsn = f"{host}:{port}:{sid}"
        else:
            dsn = host or None
        conn = oracledb.connect(
            user=conn_info.get('username', ''),
            password=conn_info.get('password', ''),
            dsn=dsn,
            connect_timeout=timeout,
        )
    except Exception as e:
        return {"error": f"数据库连接失败: {e}"}
    try:
        cur = conn.cursor()
        cur.execute(sql)
        if cur.description:
            columns = [d[0] for d in cur.description]
            rows = [list(r) for r in cur.fetchmany(max_rows)]
        else:
            columns, rows = [], []
        return {"columns": columns, "rows": rows, "row_count": len(rows)}
    except Exception as e:
        return {"error": f"数据库查询失败: {e}"}
    finally:
        conn.close()


def _query_psycopg2(conn_info: Dict, sql: str, max_rows: int, timeout: int) -> Dict:
    try:
        import psycopg2
    except ImportError:
        return {"error": "需要安装 psycopg2 才能查询 GaussDB/PostgreSQL（pip install psycopg2-binary）"}
    try:
        conn = psycopg2.connect(
            host=conn_info.get('host', ''),
            port=int(conn_info.get('port') or 5432),
            user=conn_info.get('username', ''),
            password=conn_info.get('password', ''),
            dbname=conn_info.get('database') or 'postgres',
            connect_timeout=timeout,
        )
    except Exception as e:
        return {"error": f"数据库连接失败: {e}"}
    try:
        cur = conn.cursor()
        cur.execute(sql)
        if cur.description:
            columns = [d[0] for d in cur.description]
            rows = [list(r) for r in cur.fetchmany(max_rows)]
        else:
            columns, rows = [], []
        return {"columns": columns, "rows": rows, "row_count": len(rows)}
    except Exception as e:
        return {"error": f"数据库查询失败: {e}"}
    finally:
        conn.close()


def _query_dmpython(conn_info: Dict, sql: str, max_rows: int, timeout: int) -> Dict:
    try:
        import dmPython
    except ImportError:
        return {"error": "需要安装 dmPython 才能查询达梦数据库"}
    try:
        conn = dmPython.connect(
            user=conn_info.get('username', ''),
            password=conn_info.get('password', ''),
            server=conn_info.get('host', ''),
            port=int(conn_info.get('port') or 5236),
            database=conn_info.get('database') or '',
        )
    except Exception as e:
        return {"error": f"数据库连接失败: {e}"}
    try:
        cur = conn.cursor()
        cur.execute(sql)
        if cur.description:
            columns = [d[0] for d in cur.description]
            rows = [list(r) for r in cur.fetchmany(max_rows)]
        else:
            columns, rows = [], []
        return {"columns": columns, "rows": rows, "row_count": len(rows)}
    except Exception as e:
        return {"error": f"数据库查询失败: {e}"}
    finally:
        conn.close()


def _load_private_key(key_str: str, passphrase: Optional[str]) -> Optional[object]:
    """按多种私钥格式尝试解析（RSA/Ed25519/ECDSA/DSS）"""
    import paramiko
    for cls in (paramiko.RSAKey, paramiko.Ed25519Key, paramiko.ECDSAKey, paramiko.DSSKey):
        try:
            return cls.from_private_key(io.StringIO(key_str), password=passphrase or None)
        except Exception:
            continue
    return None


def run_ssh_command(conn_info: Dict, command: str, timeout: int = 30) -> Dict:
    """通过 SSH 执行命令

    Returns:
        {'stdout': ..., 'stderr': ..., 'exit_code': N} 或 {'error': ...}
    """
    try:
        import paramiko
    except ImportError:
        return {"error": "需要安装 paramiko 才能执行SSH命令（pip install paramiko）"}
    try:
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        kwargs = {
            'hostname': conn_info.get('host', ''),
            'port': int(conn_info.get('port') or 22),
            'username': conn_info.get('username', ''),
            'timeout': timeout,
        }
        if conn_info.get('private_key'):
            pkey = _load_private_key(conn_info['private_key'], conn_info.get('passphrase'))
            if pkey is None:
                return {"error": "SSH私钥解析失败（格式不支持或口令错误）"}
            kwargs['pkey'] = pkey
        else:
            kwargs['password'] = conn_info.get('password', '')
        client.connect(**kwargs)
    except Exception as e:
        return {"error": f"SSH连接失败: {e}"}
    try:
        stdin, stdout, stderr = client.exec_command(command, timeout=timeout)
        out = stdout.read().decode('utf-8', errors='replace')
        err = stderr.read().decode('utf-8', errors='replace')
        exit_code = stdout.channel.recv_exit_status()
        return {"stdout": out, "stderr": err, "exit_code": exit_code}
    except Exception as e:
        return {"error": f"SSH命令执行失败: {e}"}
    finally:
        client.close()


# ==================== 查询生成 ====================

def build_schema_query(db_type: str, table_name: Optional[str] = None) -> str:
    """生成只读 schema 查询（表清单或表结构）"""
    db_type = (db_type or '').lower()
    if table_name:
        ident = _safe_identifier(table_name)
        if ident is None:
            raise ValueError(f"非法表名: {table_name}")
        if db_type in ('mysql', 'tdsql', 'oceanbase', 'goldendb'):
            return f"SHOW CREATE TABLE {ident}"
        if db_type in ('oracle', 'dm'):
            return (f"SELECT column_name, data_type, data_length, nullable "
                    f"FROM user_tab_columns WHERE table_name = UPPER('{ident}') ORDER BY column_id")
        if db_type == 'gaussdb':
            return (f"SELECT column_name, data_type FROM information_schema.columns "
                    f"WHERE table_name = '{ident}' ORDER BY ordinal_position")
        raise ValueError(f"暂不支持 {db_type} 的表结构查询")
    if db_type in ('mysql', 'tdsql', 'oceanbase', 'goldendb'):
        return "SHOW TABLES"
    if db_type in ('oracle', 'dm'):
        return "SELECT table_name FROM user_tables ORDER BY table_name"
    if db_type == 'gaussdb':
        return "SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename"
    raise ValueError(f"暂不支持 {db_type} 的 schema 查询")


_METRIC_QUERIES = {
    'sessions': {
        'mysql': "SHOW PROCESSLIST",
        'oracle': "SELECT sid, serial#, username, status, program FROM v$session ORDER BY sid",
        'dm': "SELECT session_id, user_name, state FROM v$sessions",
        'gaussdb': "SELECT pid, usename, state, query FROM pg_stat_activity ORDER BY pid",
    },
    'locks': {
        'mysql': "SELECT * FROM information_schema.innodb_lock_waits",
        'oracle': "SELECT sid, type, block FROM v$lock WHERE type IN ('TM','TX') ORDER BY sid",
        'dm': "SELECT session_id, blocked, lock_mode FROM v$lock",
        'gaussdb': "SELECT pid, locktype, mode FROM pg_locks LIMIT 50",
    },
    'waits': {
        'mysql': "SHOW ENGINE INNODB STATUS",
        'oracle': "SELECT event, COUNT(*) AS cnt FROM v$session_wait GROUP BY event ORDER BY cnt DESC",
        'dm': "SELECT event, COUNT(*) AS cnt FROM v$session_wait GROUP BY event ORDER BY cnt DESC",
        'gaussdb': "SELECT wait_event_type, wait_event, COUNT(*) AS cnt FROM pg_stat_activity GROUP BY wait_event_type, wait_event ORDER BY cnt DESC",
    },
    'sql_stats': {
        'mysql': "SELECT digest_text, count_star, sum_timer_wait FROM performance_schema.events_statements_summary_by_digest ORDER BY sum_timer_wait DESC LIMIT 10",
        'oracle': "SELECT sql_id, elapsed_time, sql_text FROM v$sql ORDER BY elapsed_time DESC FETCH FIRST 10 ROWS ONLY",
        'dm': "SELECT sql_text, total_exec_time FROM v$sql ORDER BY total_exec_time DESC",
        'gaussdb': "SELECT query, total_time FROM pg_stat_statements ORDER BY total_time DESC LIMIT 10",
    },
    'table_stats': {
        'mysql': "SELECT table_name, table_rows, ROUND(data_length/1024/1024,2) AS data_mb FROM information_schema.tables WHERE table_schema=DATABASE() ORDER BY data_length DESC LIMIT 10",
        'oracle': "SELECT segment_name, ROUND(SUM(bytes)/1024/1024,2) AS size_mb FROM user_segments GROUP BY segment_name ORDER BY size_mb DESC",
        'dm': "SELECT table_name, num_rows FROM user_tables ORDER BY num_rows DESC",
        'gaussdb': "SELECT relname, n_live_tup FROM pg_stat_user_tables ORDER BY n_live_tup DESC LIMIT 10",
    },
}


def build_metric_query(db_type: str, metric_type: str) -> str:
    """生成只读性能指标查询"""
    db_type = (db_type or '').lower()
    sql = _METRIC_QUERIES.get(metric_type, {}).get(db_type)
    if not sql:
        raise ValueError(f"暂不支持 {db_type} 的 {metric_type} 指标")
    return sql
