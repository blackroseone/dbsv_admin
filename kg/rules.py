# -*- coding: utf-8 -*-
"""
知识图谱规则实体提取器
基于正则表达式和词典匹配提取结构化实体
"""
import re
from functools import lru_cache
from typing import List, Dict, Tuple

# ==================== 数据库产品词典 ====================

DATABASE_PRODUCTS = {
    # 关系型数据库
    'mysql': ['MySQL', 'MariaDB', 'Percona Server'],
    'oracle': ['Oracle', 'Oracle Database', 'Oracle RAC', 'Oracle Exadata'],
    'postgresql': ['PostgreSQL', 'Postgres', 'EnterpriseDB'],
    'sqlserver': ['SQL Server', 'MSSQL', 'Microsoft SQL Server'],
    'db2': ['DB2', 'IBM DB2'],
    'sqlite': ['SQLite'],
    'oceanbase': ['OceanBase', 'OB', 'OceanBase 数据库'],
    'gaussdb': ['GaussDB', 'GaussDB(for MySQL)', 'GaussDB(for openGauss)', '华为 GaussDB'],
    'goldendb': ['GoldenDB', 'GoldenDB 分布式数据库'],
    'dameng': ['达梦', '达梦数据库', 'DM', 'DM8', '达梦 DM'],
    'tdsql': ['TDSQL', 'TDSQL-C', 'TDSQL-PG', '腾讯 TDSQL'],
    'tidb': ['TiDB', 'PingCAP TiDB'],
    'polardb': ['PolarDB', '阿里云 PolarDB'],
    'cockroachdb': ['CockroachDB', 'Cockroach DB'],
    'yugabytedb': ['YugabyteDB', 'Yugabyte DB'],
    'greenplum': ['Greenplum', 'Greenplum Database'],
    'clickhouse': ['ClickHouse'],
    'doris': ['Apache Doris', 'Doris'],
    'starrocks': ['StarRocks'],
    'mongodb': ['MongoDB', 'Mongo'],
    'redis': ['Redis'],
    'elasticsearch': ['Elasticsearch', 'ES'],
    'influxdb': ['InfluxDB'],
    'neo4j': ['Neo4j'],
    'cassandra': ['Cassandra', 'Apache Cassandra'],
    'hbase': ['HBase', 'Apache HBase'],
    'hive': ['Hive', 'Apache Hive'],
    'spark': ['Spark', 'Apache Spark'],
    'flink': ['Flink', 'Apache Flink'],
    'kafka': ['Kafka', 'Apache Kafka'],
    'rabbitmq': ['RabbitMQ'],
    'rocketmq': ['RocketMQ'],
    'etcd': ['etcd'],
    'zookeeper': ['ZooKeeper', 'ZK'],
}

# 反向映射：别名 -> 标准名
PRODUCT_ALIAS_MAP = {}
for std_name, aliases in DATABASE_PRODUCTS.items():
    PRODUCT_ALIAS_MAP[std_name.lower()] = std_name
    for alias in aliases:
        PRODUCT_ALIAS_MAP[alias.lower()] = std_name

# ==================== 操作系统词典 ====================

OPERATING_SYSTEMS = {
    'centos': ['CentOS', 'CentOS 7', 'CentOS 8', 'CentOS Stream'],
    'rhel': ['RHEL', 'Red Hat Enterprise Linux', 'RedHat'],
    'ubuntu': ['Ubuntu', 'Ubuntu Server'],
    'debian': ['Debian'],
    'suse': ['SUSE', 'SLES', 'openSUSE'],
    'windows': ['Windows', 'Windows Server', 'WinServer'],
    'aix': ['AIX', 'IBM AIX'],
    'hpux': ['HP-UX', 'HPUX'],
    'solaris': ['Solaris', 'Oracle Solaris'],
    'euleros': ['EulerOS', '华为 EulerOS', 'openEuler'],
    'kylin': ['麒麟', '银河麒麟', 'KylinOS'],
    'uos': ['统信 UOS', 'UOS'],
    'neokylin': ['中标麒麟', 'NeoKylin'],
    'anolis': ['Anolis OS', '龙蜥'],
    'rocky': ['Rocky Linux'],
    'alma': ['AlmaLinux'],
    'fedora': ['Fedora'],
    'alpine': ['Alpine Linux', 'Alpine'],
}

OS_ALIAS_MAP = {}
for std_name, aliases in OPERATING_SYSTEMS.items():
    OS_ALIAS_MAP[std_name.lower()] = std_name
    for alias in aliases:
        OS_ALIAS_MAP[alias.lower()] = std_name

# ==================== 硬件词典 ====================

HARDWARE = {
    'cpu': ['CPU', '处理器', '中央处理器'],
    'memory': ['内存', 'RAM', 'DRAM'],
    'disk': ['磁盘', '硬盘', 'HDD', 'SSD', 'NVMe'],
    'network': ['网卡', '网络', 'NIC', '带宽'],
    'storage': ['存储', 'SAN', 'NAS', '对象存储'],
}

# ==================== 性能指标词典 ====================

PERFORMANCE_METRICS = {
    'qps': ['QPS', 'Queries Per Second', '每秒查询数'],
    'tps': ['TPS', 'Transactions Per Second', '每秒事务数'],
    'rt': ['RT', '响应时间', 'Response Time', 'Latency'],
    'throughput': ['吞吐量', 'Throughput'],
    'concurrency': ['并发数', '并发连接数', 'Connections'],
    'iops': ['IOPS', '每秒 IO 次数'],
    'cpu_usage': ['CPU 使用率', 'CPU 利用率'],
    'memory_usage': ['内存使用率', '内存利用率'],
    'disk_usage': ['磁盘使用率', '磁盘利用率'],
    'cache_hit': ['缓存命中率', 'Cache Hit Ratio', 'Buffer Hit'],
    'lock_wait': ['锁等待', 'Lock Wait'],
    'slow_query': ['慢查询', 'Slow Query'],
}

# ==================== 架构/部署模式词典 ====================

ARCHITECTURES = {
    'master_slave': ['主从复制', '主从架构', 'Master-Slave', 'Master/Slave'],
    'master_master': ['主主复制', '双主架构', 'Master-Master'],
    'mgr': ['MGR', 'MySQL Group Replication', '组复制'],
    'rac': ['RAC', 'Real Application Clusters', 'Oracle RAC'],
    'dataguard': ['Data Guard', 'DG'],
    'mpp': ['MPP', '大规模并行处理', 'Massively Parallel Processing'],
    'sharding': ['分片', 'Sharding', '水平分片'],
    'distributed': ['分布式', '分布式架构', 'Distributed'],
    'standalone': ['单机', '单实例', 'Standalone'],
    'cluster': ['集群', 'Cluster'],
    'cloud_native': ['云原生', 'Cloud Native'],
    'container': ['容器化', 'Docker', 'Kubernetes', 'K8s'],
    'microservices': ['微服务', 'Microservices'],
}

# ==================== 概念词典 ====================

CONCEPTS = {
    'acid': ['ACID', '原子性', '一致性', '隔离性', '持久性'],
    'mvcc': ['MVCC', '多版本并发控制'],
    'index': ['索引', 'B+树索引', '哈希索引', '全文索引'],
    'partition': ['分区', '表分区', 'Partition'],
    'transaction': ['事务', 'Transaction'],
    'lock': ['锁', '行锁', '表锁', '悲观锁', '乐观锁'],
    'replication': ['复制', 'Replication', '数据复制'],
    'backup': ['备份', 'Backup', '全量备份', '增量备份'],
    'recovery': ['恢复', 'Recovery', '数据恢复'],
    'ha': ['高可用', 'HA', 'High Availability'],
    'dr': ['灾备', '容灾', 'Disaster Recovery'],
    'monitoring': ['监控', 'Monitoring', '告警'],
    'migration': ['迁移', 'Migration', '数据迁移'],
    'upgrade': ['升级', 'Upgrade', '版本升级'],
    'optimization': ['优化', '性能优化', 'SQL 优化'],
    'security': ['安全', 'Security', '权限', '审计'],
    'compliance': ['合规', 'Compliance'],
}

# ==================== 正则模式 ====================

def _word(alias):
    """构造对中文语境安全的词边界：仅对拉丁字母/数字/下划线生效，
    避免 \b 在「使用MySQL数据库」等汉字紧邻场景失配"""
    return r'(?<![A-Za-z0-9_])' + re.escape(alias) + r'(?![A-Za-z0-9_])'


@lru_cache(maxsize=None)
def _alias_pattern(alias):
    """按别名缓存预编译的词边界正则。

    词典提取器按 chunk 调用（块 500 后调用次数约 ×4），若每次现编
    会放大编译成本；别名集合有限，缓存不会无界增长。
    """
    return re.compile(_word(alias), re.IGNORECASE)


@lru_cache(maxsize=None)
def _param_prefix_pattern(prefix):
    """按参数前缀缓存预编译正则（prefix_xxx 或 prefix.xxx 格式）。"""
    return re.compile(
        r'(?<![A-Za-z0-9_])(' + re.escape(prefix) + r'[a-zA-Z0-9_]+)(?![A-Za-z0-9_])',
        re.IGNORECASE
    )


# 通用参数模式（大写下划线格式）
GENERIC_PARAM_PATTERN = re.compile(
    r'(?<![A-Za-z0-9_])([A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+)(?![A-Za-z0-9_])')


# 版本号模式（版本组支持 Oracle 19c 等字母后缀）
VERSION_PATTERN = re.compile(
    r'(?<![A-Za-z0-9_])(?:MySQL|Oracle|PostgreSQL|SQL Server|DB2|OceanBase|GaussDB|'
    r'GoldenDB|达梦|DM|TiDB|MariaDB|Redis|MongoDB|Elasticsearch|'
    r'Kafka|ClickHouse|CentOS|RHEL|Ubuntu|Windows|AIX)\s*'
    r'(?:V|v|Version|版本)?\s*'
    r'(\d+(?:\.\d+)*(?:[a-zA-Z]\d*)?(?:\s*(?:R|r)?\d+)?)',
    re.IGNORECASE
)

# 通用版本号模式（数字.数字.数字）
GENERIC_VERSION_PATTERN = re.compile(
    r'(?<![A-Za-z0-9_])(\d+\.\d+(?:\.\d+)?(?:[-_.]?(?:alpha|beta|rc|RC|ga|GA|sp|SP)\d*)?)(?![A-Za-z0-9_])'
)

# 错误码模式
ERROR_CODE_PATTERNS = {
    'oracle': re.compile(r'\bORA-\d{5,6}\b'),
    'mysql': re.compile(r'\bERROR\s+(\d{4,5})\b', re.IGNORECASE),
    # PostgreSQL 仅在出现 SQLSTATE 码时提取，避免把 "ERROR: <任意文本>" 建成噪音实体
    'postgresql': re.compile(r'\bSQLSTATE[:\s]*\d{2}[A-Z0-9]{3}\b', re.IGNORECASE),
    'oceanbase': re.compile(r'\bOB-\d{4,6}\b'),
    'gaussdb': re.compile(r'\bGS-\d{4,6}\b'),
    'sqlserver': re.compile(r'\bMsg\s+\d+\b', re.IGNORECASE),
    'db2': re.compile(r'\bSQL\d{4}[N|W|E]\b'),
}

# 常见参数前缀（提高参数识别准确率）
PARAMETER_PREFIXES = {
    'mysql': ['innodb_', 'max_', 'min_', 'log_', 'binlog_', 'relay_',
              'slow_', 'general_', 'performance_', 'table_', 'thread_',
              'query_', 'sort_', 'join_', 'tmp_', 'bulk_', 'key_',
              'ft_', 'range_', 'read_', 'write_', 'connect_',
              'wait_', 'interactive_', 'net_', 'slave_', 'master_',
              'rpl_', 'group_', 'auto_', 'character_', 'collation_',
              'default_', 'init_', 'local_', 'secure_', 'sql_',
              'transaction_', 'unique_', 'updatable_', 'optimizer_',
              'histogram_', 'information_', 'show_'],
    'oracle': ['db_', 'sga_', 'pga_', 'log_', 'archive_', 'undo_',
               'control_', 'data_', 'temp_', 'sort_', 'hash_',
               'parallel_', 'optimizer_', 'query_', 'result_',
               'resource_', 'session_', 'processes', 'open_cursors',
               'nls_', 'remote_', 'sql_', 'star_', 'trace_',
               'user_', 'audit_', 'os_'],
    'postgresql': ['max_', 'min_', 'shared_', 'wal_', 'checkpoint_',
                   'archive_', 'effective_', 'random_', 'seq_',
                   'work_', 'maintenance_', 'autovacuum_', 'log_',
                   'client_', 'tcp_', 'ssl_', 'password_',
                   'timezone', 'datestyle', 'lc_'],
    'oceanbase': ['ob_', 'zone_', 'server_', 'tenant_', 'unit_',
                  'memory_', 'cpu_', 'disk_', 'data_', 'clog_',
                  'syslog_', 'rootservice_', 'merge_', 'minor_',
                  'major_', 'freeze_', 'compaction_', 'backup_',
                  'restore_', 'transfer_', 'rebalance_'],
    'gaussdb': ['gs_', 'enable_', 'max_', 'min_', 'work_',
                'maintenance_', 'autovacuum_', 'checkpoint_',
                'wal_', 'archive_', 'log_', 'shared_',
                'effective_', 'random_', 'seq_'],
}

# SQL 关键字模式
SQL_KEYWORDS = re.compile(
    r'(?<![A-Za-z0-9_])(SELECT|INSERT|UPDATE|DELETE|CREATE|DROP|ALTER|TRUNCATE|'
    r'GRANT|REVOKE|COMMIT|ROLLBACK|BEGIN|END|SAVEPOINT|'
    r'EXPLAIN|ANALYZE|OPTIMIZE|LOCK|UNLOCK|CALL|EXECUTE|'
    r'MERGE|UPSERT|REPLACE|LOAD|UNLOAD|COPY|IMPORT|EXPORT)(?![A-Za-z0-9_])',
    re.IGNORECASE
)

# 系统视图模式（去掉无前缀限定的 all_/user_，避免把普通文本误判为系统视图）
SYSTEM_VIEW_PATTERN = re.compile(
    r'(?<![A-Za-z0-9_])(v\$\w+|information_schema\.\w+|pg_\w+|sys\.\w+|'
    r'performance_schema\.\w+|mysql\.\w+|dba_\w+)(?![A-Za-z0-9_])',
    re.IGNORECASE
)

# 函数模式
FUNCTION_PATTERN = re.compile(
    r'(?<![A-Za-z0-9_])([A-Z_][A-Z0-9_]*\s*\()',
    re.IGNORECASE
)

# 不应被识别为函数的 SQL 关键字/子句词（过滤 IN( / OVER( / CASE( 等误报）
FUNCTION_STOPLIST = {
    'select', 'from', 'where', 'and', 'or', 'not', 'in', 'over', 'case',
    'when', 'then', 'else', 'end', 'if', 'values', 'set', 'update', 'insert',
    'delete', 'create', 'alter', 'drop', 'truncate', 'grant', 'revoke',
    'group', 'order', 'having', 'limit', 'offset', 'join', 'left', 'right',
    'inner', 'outer', 'cross', 'using', 'on', 'as', 'by', 'union', 'all',
    'distinct', 'exists', 'between', 'like', 'null', 'true', 'false',
    'begin', 'commit', 'rollback', 'savepoint', 'lock', 'unlock', 'call',
    'execute', 'return', 'declare', 'into',
}

# 命令行工具模式
COMMAND_PATTERN = re.compile(
    r'(?<![A-Za-z0-9_])(mysqldump|mysql|mysqladmin|obd|obclient|gs_ctl|gs_guc|'
    r'gs_dump|gs_restore|sqlplus|exp|imp|expdp|impdp|rman|'
    r'pg_dump|pg_restore|psql|createdb|dropdb|vacuumdb|'
    r'obproxy|ob_admin|ob_config|ob_check|ob_clean|'
    r'redis-cli|mongo|mongodump|mongoexport|mongoimport|'
    r'kafka-topics|kafka-console-consumer|kafka-console-producer)(?![A-Za-z0-9_])',
    re.IGNORECASE
)

# ==================== 提取函数 ====================

def extract_database_products(text: str) -> List[Dict]:
    """提取数据库产品实体"""
    entities = []
    found = set()

    for alias, std_name in PRODUCT_ALIAS_MAP.items():
        if std_name in found:
            continue

        # 构建匹配模式（支持大小写不敏感）
        aliases = DATABASE_PRODUCTS[std_name]
        for product_name in aliases:
            # 使用 ASCII 词边界匹配（中文语境安全）
            pattern = _alias_pattern(product_name)
            matches = list(pattern.finditer(text))
            if matches:
                found.add(std_name)
                # 取第一个匹配的位置
                match = matches[0]
                entities.append({
                    'entity_type': 'database_product',
                    'name': product_name,
                    'normalized_name': std_name,
                    'aliases': [a for a in aliases if a != product_name],
                    'confidence': 1.0,
                    'extract_method': 'rule',
                    'positions': [(m.start(), m.end()) for m in matches]
                })
                break

    return entities


def extract_versions(text: str) -> List[Dict]:
    """提取版本号实体

    去重键为 (product, version)：同一版本号归属不同产品时保留各自实体
    （如 "MySQL 8.0 和 Oracle 8.0" 各出一个）。
    """
    entities = []
    found = set()  # {(product_std, version)}

    # 带产品名的版本
    for match in VERSION_PATTERN.finditer(text):
        full_match = match.group(0)
        version = match.group(1)
        if not version:
            continue
        # 提取产品名
        product_text = full_match[:match.start(1) - match.start()].strip()
        product_std = None
        for alias, std in PRODUCT_ALIAS_MAP.items():
            if alias in product_text.lower():
                product_std = std
                break
        key = (product_std, version)
        if key in found:
            continue
        found.add(key)
        entities.append({
            'entity_type': 'version',
            'name': full_match.strip(),
            'normalized_name': f"{product_std}_{version}" if product_std else version,
            'aliases': [version],
            'description': f"{product_text} 的版本号" if product_text else "版本号",
            'properties': {'version': version, 'product': product_std},
            'confidence': 0.9,
            'extract_method': 'rule',
            'positions': [(match.start(), match.end())]
        })

    # 通用版本号（如果前面没有产品名）
    for match in GENERIC_VERSION_PATTERN.finditer(text):
        version = match.group(1)
        # 检查上下文是否有产品名
        context_start = max(0, match.start() - 50)
        context = text[context_start:match.start()]
        product_std = None
        for alias, std in PRODUCT_ALIAS_MAP.items():
            if alias in context.lower():
                product_std = std
                break
        if not product_std:
            continue

        key = (product_std, version)
        if key in found:
            continue
        # 避免对已提取的完整版本（如 8.0.1）再建前缀版本（8.0）实体
        if any(p == product_std and v.startswith(version + '.') for p, v in found):
            continue

        found.add(key)
        entities.append({
            'entity_type': 'version',
            'name': version,
            'normalized_name': f"{product_std}_{version}",
            'aliases': [],
            'description': f"{product_std} 的版本号",
            'properties': {'version': version, 'product': product_std},
            'confidence': 0.7,
            'extract_method': 'rule',
            'positions': [(match.start(), match.end())]
        })

    return entities


def extract_error_codes(text: str) -> List[Dict]:
    """提取错误码实体"""
    entities = []
    found = set()

    for db_type, pattern in ERROR_CODE_PATTERNS.items():
        for match in pattern.finditer(text):
            code = match.group(0)
            if code not in found:
                found.add(code)
                entities.append({
                    'entity_type': 'error_code',
                    'name': code,
                    'normalized_name': code.lower(),
                    'aliases': [],
                    'description': f"{db_type} 错误码",
                    'properties': {'db_type': db_type},
                    'confidence': 1.0,
                    'extract_method': 'rule',
                    'positions': [(match.start(), match.end())]
                })

    return entities


def extract_operating_systems(text: str) -> List[Dict]:
    """提取操作系统实体"""
    entities = []
    found = set()

    for alias, std_name in OS_ALIAS_MAP.items():
        if std_name in found:
            continue

        aliases = OPERATING_SYSTEMS[std_name]
        for os_name in aliases:
            pattern = _alias_pattern(os_name)
            matches = list(pattern.finditer(text))
            if matches:
                found.add(std_name)
                entities.append({
                    'entity_type': 'operating_system',
                    'name': os_name,
                    'normalized_name': std_name,
                    'aliases': [a for a in aliases if a != os_name],
                    'confidence': 1.0,
                    'extract_method': 'rule',
                    'positions': [(m.start(), m.end()) for m in matches]
                })
                break

    return entities


def extract_parameters(text: str, db_type: str = None) -> List[Dict]:
    """提取参数实体"""
    entities = []
    found = set()

    # 如果指定了数据库类型，使用对应的参数前缀
    prefixes = []
    if db_type and db_type in PARAMETER_PREFIXES:
        prefixes = PARAMETER_PREFIXES[db_type]
    else:
        # 使用所有前缀
        for p_list in PARAMETER_PREFIXES.values():
            prefixes.extend(p_list)
        prefixes = list(set(prefixes))

    # 基于前缀匹配
    for prefix in prefixes:
        # 匹配 prefix_xxx 或 prefix.xxx 格式
        pattern = _param_prefix_pattern(prefix)
        for match in pattern.finditer(text):
            param = match.group(1)
            param_lower = param.lower()
            if param_lower not in found:
                found.add(param_lower)

                # 推断所属数据库
                inferred_db = db_type
                if not inferred_db:
                    for db, db_prefixes in PARAMETER_PREFIXES.items():
                        if prefix.lower() in [p.lower() for p in db_prefixes]:
                            inferred_db = db
                            break

                entities.append({
                    'entity_type': 'parameter',
                    'name': param,
                    'normalized_name': param_lower,
                    'aliases': [],
                    'description': f"{inferred_db or '数据库'} 参数" if inferred_db else "数据库参数",
                    'properties': {'db_type': inferred_db, 'prefix': prefix},
                    'confidence': 0.85,
                    'extract_method': 'rule',
                    'positions': [(match.start(), match.end())]
                })

    # 通用参数模式（大写下划线格式）
    for match in GENERIC_PARAM_PATTERN.finditer(text):
        param = match.group(1)
        param_lower = param.lower()
        if param_lower not in found and len(param) > 5:
            found.add(param_lower)
            entities.append({
                'entity_type': 'parameter',
                'name': param,
                'normalized_name': param_lower,
                'aliases': [],
                'confidence': 0.6,
                'extract_method': 'rule',
                'positions': [(match.start(), match.end())]
            })

    return entities


def extract_sql_statements(text: str) -> List[Dict]:
    """提取 SQL 语句类型"""
    entities = []
    found = set()

    for match in SQL_KEYWORDS.finditer(text):
        keyword = match.group(1).upper()
        if keyword not in found:
            found.add(keyword)
            entities.append({
                'entity_type': 'sql_statement',
                'name': keyword,
                'normalized_name': keyword.lower(),
                'aliases': [],
                'confidence': 1.0,
                'extract_method': 'rule',
                'positions': [(match.start(), match.end())]
            })

    return entities


def extract_system_views(text: str) -> List[Dict]:
    """提取系统视图"""
    entities = []
    found = set()

    for match in SYSTEM_VIEW_PATTERN.finditer(text):
        view = match.group(1)
        view_lower = view.lower()
        if view_lower not in found:
            found.add(view_lower)
            entities.append({
                'entity_type': 'system_view',
                'name': view,
                'normalized_name': view_lower,
                'aliases': [],
                'confidence': 1.0,
                'extract_method': 'rule',
                'positions': [(match.start(), match.end())]
            })

    return entities


def extract_functions(text: str) -> List[Dict]:
    """提取函数"""
    entities = []
    found = set()

    for match in FUNCTION_PATTERN.finditer(text):
        func = match.group(1).rstrip('(').strip()
        func_lower = func.lower()
        # 过滤 SQL 关键字（IN/OVER/CASE/WHEN 等）误报为函数
        if func_lower not in found and len(func) > 2 and func_lower not in FUNCTION_STOPLIST:
            found.add(func_lower)
            entities.append({
                'entity_type': 'function',
                'name': func,
                'normalized_name': func_lower,
                'aliases': [],
                'confidence': 0.8,
                'extract_method': 'rule',
                'positions': [(match.start(), match.end() - 1)]
            })

    return entities


def extract_commands(text: str) -> List[Dict]:
    """提取命令行工具"""
    entities = []
    found = set()

    for match in COMMAND_PATTERN.finditer(text):
        cmd = match.group(1)
        cmd_lower = cmd.lower()
        if cmd_lower not in found:
            found.add(cmd_lower)
            entities.append({
                'entity_type': 'command_tool',
                'name': cmd,
                'normalized_name': cmd_lower,
                'aliases': [],
                'confidence': 1.0,
                'extract_method': 'rule',
                'positions': [(match.start(), match.end())]
            })

    return entities


def extract_architectures(text: str) -> List[Dict]:
    """提取架构/部署模式"""
    entities = []
    found = set()

    for std_name, aliases in ARCHITECTURES.items():
        for arch_name in aliases:
            pattern = _alias_pattern(arch_name)
            matches = list(pattern.finditer(text))
            if matches:
                if std_name not in found:
                    found.add(std_name)
                    entities.append({
                        'entity_type': 'architecture',
                        'name': arch_name,
                        'normalized_name': std_name,
                        'aliases': [a for a in aliases if a != arch_name],
                        'confidence': 1.0,
                        'extract_method': 'rule',
                        'positions': [(m.start(), m.end()) for m in matches]
                    })
                break

    return entities


def extract_concepts(text: str) -> List[Dict]:
    """提取概念"""
    entities = []
    found = set()

    for std_name, aliases in CONCEPTS.items():
        for concept_name in aliases:
            pattern = _alias_pattern(concept_name)
            matches = list(pattern.finditer(text))
            if matches:
                if std_name not in found:
                    found.add(std_name)
                    entities.append({
                        'entity_type': 'concept',
                        'name': concept_name,
                        'normalized_name': std_name,
                        'aliases': [a for a in aliases if a != concept_name],
                        'confidence': 1.0,
                        'extract_method': 'rule',
                        'positions': [(m.start(), m.end()) for m in matches]
                    })
                break

    return entities


def extract_performance_metrics(text: str) -> List[Dict]:
    """提取性能指标"""
    entities = []
    found = set()

    for std_name, aliases in PERFORMANCE_METRICS.items():
        for metric_name in aliases:
            pattern = _alias_pattern(metric_name)
            matches = list(pattern.finditer(text))
            if matches:
                if std_name not in found:
                    found.add(std_name)
                    entities.append({
                        'entity_type': 'performance_metric',
                        'name': metric_name,
                        'normalized_name': std_name,
                        'aliases': [a for a in aliases if a != metric_name],
                        'confidence': 1.0,
                        'extract_method': 'rule',
                        'positions': [(m.start(), m.end()) for m in matches]
                    })
                break

    return entities


def extract_hardware(text: str) -> List[Dict]:
    """提取硬件"""
    entities = []
    found = set()

    for std_name, aliases in HARDWARE.items():
        for hw_name in aliases:
            pattern = _alias_pattern(hw_name)
            matches = list(pattern.finditer(text))
            if matches:
                if std_name not in found:
                    found.add(std_name)
                    entities.append({
                        'entity_type': 'hardware',
                        'name': hw_name,
                        'normalized_name': std_name,
                        'aliases': [a for a in aliases if a != hw_name],
                        'confidence': 1.0,
                        'extract_method': 'rule',
                        'positions': [(m.start(), m.end()) for m in matches]
                    })
                break

    return entities


# ==================== 主提取函数 ====================

def extract_all_entities(text: str, db_type: str = None) -> List[Dict]:
    """从文本中提取所有类型的实体"""
    all_entities = []

    extractors = [
        extract_database_products,
        extract_versions,
        extract_error_codes,
        extract_operating_systems,
        lambda t: extract_parameters(t, db_type),
        extract_sql_statements,
        extract_system_views,
        extract_functions,
        extract_commands,
        extract_architectures,
        extract_concepts,
        extract_performance_metrics,
        extract_hardware,
    ]

    for extractor in extractors:
        try:
            entities = extractor(text)
            all_entities.extend(entities)
        except Exception as e:
            print(f"[KG Rule Extractor] {extractor.__name__} 失败: {e}")

    return all_entities


# ==================== 关系推理 ====================

def _nearby(entity_a: Dict, entity_b: Dict, max_distance: int = 200) -> bool:
    """判断两个实体在文本中的位置是否邻近（任一位置对的距离 <= max_distance），
    避免同文本任意共现就全量建边（笛卡尔积污染）"""
    pos_a = entity_a.get('positions', [])
    pos_b = entity_b.get('positions', [])
    for sa, _ in pos_a:
        for sb, _ in pos_b:
            if abs(sa - sb) <= max_distance:
                return True
    return False


def infer_relationships(entities: List[Dict], text: str) -> List[Dict]:
    """基于提取的实体推断关系"""
    relationships = []

    # 构建实体映射
    entity_map = {}
    for e in entities:
        key = (e['entity_type'], e['normalized_name'])
        entity_map[key] = e

    # 1. 版本归属：version -> belongs_to -> database_product
    versions = [e for e in entities if e['entity_type'] == 'version']
    products = [e for e in entities if e['entity_type'] == 'database_product']

    for v in versions:
        product = v.get('properties', {}).get('product')
        if product:
            # 查找对应的产品实体
            for p in products:
                if p['normalized_name'] == product:
                    relationships.append({
                        'from_entity': p,
                        'to_entity': v,
                        'relation_type': 'has_version',
                        'confidence': 0.9,
                        'extract_method': 'rule'
                    })
                    break

    # 2. 参数归属：parameter -> belongs_to -> database_product
    params = [e for e in entities if e['entity_type'] == 'parameter']
    for param in params:
        db = param.get('properties', {}).get('db_type')
        if db:
            for p in products:
                if p['normalized_name'] == db:
                    relationships.append({
                        'from_entity': p,
                        'to_entity': param,
                        'relation_type': 'has_parameter',
                        'confidence': 0.85,
                        'extract_method': 'rule'
                    })
                    break

    # 3. 操作系统依赖：database_product -> requires -> operating_system
    #    仅当产品与操作系统在文本中位置邻近时建边，避免 n×m 笛卡尔积
    os_entities = [e for e in entities if e['entity_type'] == 'operating_system']
    if os_entities and products:
        for p in products:
            for os in os_entities:
                if not _nearby(p, os):
                    continue
                relationships.append({
                    'from_entity': p,
                    'to_entity': os,
                    'relation_type': 'requires',
                    'confidence': 0.6,
                    'extract_method': 'rule'
                })

    # 4. 错误码归属：error_code -> belongs_to -> database_product
    errors = [e for e in entities if e['entity_type'] == 'error_code']
    for err in errors:
        db = err.get('properties', {}).get('db_type')
        if db:
            for p in products:
                if p['normalized_name'] == db:
                    relationships.append({
                        'from_entity': p,
                        'to_entity': err,
                        'relation_type': 'has_error_code',
                        'confidence': 0.9,
                        'extract_method': 'rule'
                    })
                    break

    # 5. 架构归属：architecture -> part_of -> database_product
    #    仅当架构与产品位置邻近时建边
    archs = [e for e in entities if e['entity_type'] == 'architecture']
    for arch in archs:
        for p in products:
            if not _nearby(arch, p):
                continue
            relationships.append({
                'from_entity': p,
                'to_entity': arch,
                'relation_type': 'has_architecture',
                'confidence': 0.6,
                'extract_method': 'rule'
            })

    return relationships
