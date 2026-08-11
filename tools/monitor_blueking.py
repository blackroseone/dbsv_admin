# -*- coding: utf-8 -*-
"""蓝鲸监控数据中间脚本

从蓝鲸监控平台数据库拉取监控指标，规范化后写入 dbsv_admin 的
mon_metric_data 表，供运维 Agent（get_monitor_metrics）与展示/评分消费。

当前为**框架**：连接与查询定义配置化，蓝鲸表结构待用户提供后填入
BlueKingMetrics.QUERIES（见下方 TODO 标注）。连接凭据不硬编码，
从环境变量或配置文件读取。

用法:
    python tools/monitor_blueking.py --pull             # 拉取一次并落库
    python tools/monitor_blueking.py --pull --dry-run   # 试跑，只打印不落库
    python tools/monitor_blueking.py --list-metrics     # 列出已配置的指标查询
"""
import argparse
import json
import os
import sys

# 允许从项目根导入 db
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ==================== 配置 ====================

# 蓝鲸监控库连接（优先环境变量，避免硬编码凭据）
BLUEKING_CONN = {
    'db_type': os.environ.get('BLUEKING_DB_TYPE', 'mysql'),   # mysql / postgresql
    'host': os.environ.get('BLUEKING_HOST', ''),
    'port': int(os.environ.get('BLUEKING_PORT', '3306')),
    'database': os.environ.get('BLUEKING_DB', ''),
    'username': os.environ.get('BLUEKING_USER', ''),
    'password': os.environ.get('BLUEKING_PASSWORD', ''),
}


class BlueKingMetrics:
    """蓝鲸指标查询注册表：metric 名 -> 查询定义。

    每条定义：
      sql: 从蓝鲸库拉该指标数据的 SQL
      object_type: 落库的 object_type（db_instance / host / cluster）
      object_col / metric_col / value_col / time_col: 结果行到 mon_metric_data 的字段映射
      unit: 指标单位

    TODO(蓝鲸表结构未提供): 以下 QUERIES 为占位。拿到蓝鲸监控库表结构后，
    按上述约定填充真实 SQL 与字段映射，即可端到端拉取。
    """
    QUERIES = {
        # 'cpu_usage': {
        #     'sql': "SELECT host, cpu_usage, collect_time FROM blueking_cpu_usage WHERE collect_time >= %(since)s",
        #     'object_type': 'host',
        #     'object_col': 'host',
        #     'metric_col': None,   # 用 key 作 metric 名
        #     'value_col': 'cpu_usage',
        #     'time_col': 'collect_time',
        #     'unit': '%',
        # },
    }


# ==================== 连接 ====================

def _connect():
    """按 db_type 连接蓝鲸监控库，返回 connection 对象"""
    db_type = BLUEKING_CONN['db_type']
    if db_type == 'mysql':
        try:
            import pymysql
        except ImportError:
            raise RuntimeError('缺少依赖 pymysql，请先 pip install pymysql')
        return pymysql.connect(
            host=BLUEKING_CONN['host'], port=BLUEKING_CONN['port'],
            user=BLUEKING_CONN['username'], password=BLUEKING_CONN['password'],
            database=BLUEKING_CONN['database'], charset='utf8mb4',
            connect_timeout=10, read_timeout=30,
        )
    if db_type == 'postgresql':
        try:
            import psycopg2
        except ImportError:
            raise RuntimeError('缺少依赖 psycopg2，请先 pip install psycopg2')
        return psycopg2.connect(
            host=BLUEKING_CONN['host'], port=BLUEKING_CONN['port'],
            user=BLUEKING_CONN['username'], password=BLUEKING_CONN['password'],
            dbname=BLUEKING_CONN['database'], connect_timeout=10,
        )
    raise RuntimeError(f'不支持的蓝鲸库类型: {db_type}')


def _run_query(conn, sql):
    """执行查询，返回 (columns, rows)"""
    cur = conn.cursor()
    cur.execute(sql)
    columns = [d[0] for d in cur.description]
    rows = cur.fetchall()
    cur.close()
    return columns, rows


# ==================== 拉取与规范化 ====================

def pull_metrics(dry_run=False):
    """拉取所有已配置指标，规范化并写入 mon_metric_data"""
    from db.database import save_mon_metrics

    if not BlueKingMetrics.QUERIES:
        print('[monitor] 尚无已配置的蓝鲸指标查询。请先提供蓝鲸表结构并填充 '
              'tools/monitor_blueking.py 的 BlueKingMetrics.QUERIES。')
        return 0

    if not BLUEKING_CONN['host']:
        print('[monitor] 未配置蓝鲸库连接（环境变量 BLUEKING_HOST 等）。')
        return 0

    conn = _connect()
    total = 0
    try:
        for metric, q in BlueKingMetrics.QUERIES.items():
            print(f'[monitor] 拉取指标 {metric} ...')
            columns, rows = _run_query(conn, q['sql'])
            # 字段索引定位
            object_type = q['object_type']
            ci = columns.index(q['object_col']) if q.get('object_col') else 0
            vi = columns.index(q['value_col'])
            ti = columns.index(q['time_col'])
            mi = columns.index(q['metric_col']) if q.get('metric_col') else None
            unit = q.get('unit', '')

            metrics = []
            for row in rows:
                metrics.append({
                    'source': 'blueking',
                    'object_type': object_type,
                    'object_name': str(row[ci]),
                    'metric': str(row[mi]) if mi is not None else metric,
                    'value': row[vi],
                    'unit': unit,
                    'record_time': str(row[ti]),
                })
            total += len(metrics)
            print(f'[monitor]   共 {len(metrics)} 条')
            if not dry_run:
                save_mon_metrics(metrics)
    finally:
        conn.close()

    print(f'[monitor] 完成，共 {total} 条指标记录' + ('（dry-run 未落库）' if dry_run else '已落库'))
    return total


def list_metrics():
    """列出已配置指标查询"""
    if not BlueKingMetrics.QUERIES:
        print('未配置指标查询（BlueKingMetrics.QUERIES 为空）')
        return
    for name, q in BlueKingMetrics.QUERIES.items():
        print(f'- {name}: 对象={q["object_type"]}, 单位={q.get("unit", "")}')
        print(f'    SQL: {q["sql"][:100]}')


def main():
    parser = argparse.ArgumentParser(description='蓝鲸监控数据中间脚本')
    parser.add_argument('--pull', action='store_true', help='拉取蓝鲸指标并落库')
    parser.add_argument('--dry-run', action='store_true', help='试跑，不落库')
    parser.add_argument('--list-metrics', action='store_true', help='列出已配置指标查询')
    args = parser.parse_args()

    if args.list_metrics:
        list_metrics()
    elif args.pull:
        pull_metrics(dry_run=args.dry_run)
    else:
        parser.print_help()


if __name__ == '__main__':
    main()
