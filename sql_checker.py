# -*- coding: utf-8 -*-
"""
本地 SQL 语法检查模块
使用 sqlglot 进行快速的本地 SQL 语法解析和检查
"""
import sqlglot
from sqlglot import parse

# 数据库类型到 sqlglot 方言的映射
DIALECT_MAP = {
    'mysql': 'mysql',
    'oracle': 'oracle',
    'postgres': 'postgres',
    'sqlite': 'sqlite',
    'hive': 'hive',
    'spark': 'spark',
    'presto': 'presto',
    'bigquery': 'bigquery',
    'snowflake': 'snowflake',
    'duckdb': 'duckdb',
    'clickhouse': 'clickhouse',
    'redshift': 'redshift',
    'tsql': 'tsql',  # SQL Server
    'trino': 'trino',
    'druid': 'druid',
    'teradata': 'teradata',
    'starrocks': 'starrocks',
    'doris': 'doris',
    'drill': 'drill',
    'exasol': 'exasol',
    'singlestore': 'singlestore',
    'materialize': 'materialize',
    'risingwave': 'risingwave',
    'solr': 'solr',
    'prql': 'prql',
    'tableau': 'tableau',
    'dune': 'dune',
    'fabric': 'fabric',
    'dremio': 'dremio',
    'athena': 'athena',
    'databricks': 'databricks',
}

# 国产数据库兼容性映射（使用兼容的方言进行语法检查）
COMPATIBILITY_MAP = {
    'dm': 'oracle',        # 达梦兼容 Oracle 语法
    'goldendb': 'mysql',   # GoldenDB 基于 MySQL
    'oceanbase': 'mysql',  # OceanBase 兼容 MySQL
    'tdsql': 'mysql',      # TDSQL 基于 MySQL
    'gaussdb': 'postgres', # GaussDB 基于 PostgreSQL
}

# 不支持本地解析的数据库类型（需要回退到 LLM）
UNSUPPORTED_DIALECTS = {
    # 已添加兼容性映射，不再直接视为不支持
}


def get_supported_dialects():
    """获取支持的方言列表"""
    return list(DIALECT_MAP.keys()) + list(COMPATIBILITY_MAP.keys())


def is_dialect_supported(db_type):
    """检查数据库类型是否支持本地语法检查"""
    if not db_type:
        return False
    db_type_lower = db_type.lower()
    return db_type_lower in DIALECT_MAP or db_type_lower in COMPATIBILITY_MAP


def get_dialect_for_check(db_type):
    """
    获取用于语法检查的方言

    优先使用直接映射，如果没有则使用兼容性映射
    """
    if not db_type:
        return None

    db_type_lower = db_type.lower()

    # 直接支持的方言
    if db_type_lower in DIALECT_MAP:
        return DIALECT_MAP[db_type_lower], None

    # 兼容性映射
    if db_type_lower in COMPATIBILITY_MAP:
        actual_dialect = COMPATIBILITY_MAP[db_type_lower]
        return actual_dialect, db_type_lower

    return None, None


def check_sql_syntax(sql, db_type='mysql'):
    """
    本地 SQL 语法检查

    参数:
        sql: SQL 语句
        db_type: 数据库类型

    返回:
        (is_valid, message, details)
        - is_valid: bool, 语法是否正确
        - message: str, 检查结果摘要
        - details: dict, 详细信息
    """
    if not sql or not sql.strip():
        return False, "❌ SQL 语句为空", {
            'error_type': 'empty',
            'suggestion': '请输入 SQL 语句'
        }

    # 获取用于检查的方言
    dialect, original_type = get_dialect_for_check(db_type)

    if not dialect:
        # 未知类型，尝试用通用方式解析
        dialect = None
        original_type = None

    try:
        # 使用 sqlglot 解析 SQL
        if dialect:
            parsed = parse(sql, read=dialect)
        else:
            # 通用解析
            parsed = parse(sql)

        if not parsed or len(parsed) == 0:
            return False, "❌ 无法解析 SQL 语句", {
                'error_type': 'parse_error',
                'suggestion': '请检查 SQL 语句是否完整'
            }

        # 检查是否有语法错误
        errors = []
        for stmt in parsed:
            if stmt is None:
                errors.append("语句解析为空")
                continue

            # 检查语句类型
            stmt_type = stmt.key if hasattr(stmt, 'key') else 'unknown'

            # 检查是否有错误标记
            if hasattr(stmt, 'errors') and stmt.errors:
                for error in stmt.errors:
                    errors.append(str(error))

        if errors:
            error_msg = "; ".join(errors[:3])  # 最多显示 3 个错误
            return False, f"❌ 发现 {len(errors)} 个语法问题", {
                'error_type': 'syntax_error',
                'errors': errors,
                'suggestion': '请根据错误信息修正 SQL'
            }

        # 语法正确
        stmt_types = []
        for stmt in parsed:
            if stmt and hasattr(stmt, 'key'):
                stmt_types.append(stmt.key)

        # 构建提示信息
        if original_type and original_type != dialect:
            # 使用了兼容性映射
            compatibility_names = {
                'dm': '达梦',
                'goldendb': 'GoldenDB',
                'oceanbase': 'OceanBase',
                'tdsql': 'TDSQL',
                'gaussdb': 'GaussDB',
            }
            db_name = compatibility_names.get(original_type, original_type)
            dialect_name = {
                'oracle': 'Oracle',
                'mysql': 'MySQL',
                'postgres': 'PostgreSQL',
            }.get(dialect, dialect)

            message = f"✅ 语法正确（使用 {dialect_name} 语法检查 {db_name}）"
        else:
            message = "✅ 语法正确"

        return True, message, {
            'error_type': None,
            'statement_types': stmt_types,
            'statement_count': len(parsed),
            'dialect': dialect or 'generic',
            'original_type': original_type,
            'suggestion': None
        }

    except sqlglot.errors.ParseError as e:
        # 解析错误
        error_msg = str(e)
        # 提取更友好的错误信息
        friendly_msg = _extract_friendly_error(error_msg)
        return False, f"❌ {friendly_msg}", {
            'error_type': 'parse_error',
            'original_error': error_msg,
            'suggestion': '请检查 SQL 语法是否正确'
        }
    except Exception as e:
        # 其他错误
        return False, f"❌ 检查失败: {str(e)}", {
            'error_type': 'unknown',
            'suggestion': '请稍后重试或使用 LLM 审核'
        }


def _extract_friendly_error(error_msg):
    """从 sqlglot 错误信息中提取友好的错误描述"""
    if "Invalid expression" in error_msg:
        return "SQL 表达式无效，请检查语法"
    elif "Expecting" in error_msg:
        return "SQL 语句不完整，缺少必要部分"
    elif "Unexpected token" in error_msg:
        return "发现意外的字符或关键字"
    elif "Required keyword" in error_msg:
        return "缺少必要的关键字"
    else:
        # 返回简化的错误信息
        return error_msg.split('\n')[0] if '\n' in error_msg else error_msg


def get_sql_info(sql, db_type='mysql'):
    """
    获取 SQL 语句的详细信息

    返回:
        dict: 包含语句类型、表名、列名等信息
    """
    try:
        dialect = DIALECT_MAP.get(db_type.lower())
        if dialect:
            parsed = parse(sql, read=dialect)
        else:
            parsed = parse(sql)

        if not parsed:
            return None

        info = {
            'statement_types': [],
            'tables': set(),
            'columns': set(),
            'functions': set(),
        }

        for stmt in parsed:
            if stmt is None:
                continue

            # 语句类型
            if hasattr(stmt, 'key'):
                info['statement_types'].append(stmt.key)

            # 提取表名
            for table in stmt.find_all(sqlglot.exp.Table):
                if table.name:
                    info['tables'].add(table.name)

            # 提取列名
            for column in stmt.find_all(sqlglot.exp.Column):
                if column.name:
                    info['columns'].add(column.name)

            # 提取函数
            for func in stmt.find_all(sqlglot.exp.Func):
                if hasattr(func, 'key'):
                    info['functions'].add(func.key)

        # 将 set 转换为 list
        info['tables'] = list(info['tables'])
        info['columns'] = list(info['columns'])
        info['functions'] = list(info['functions'])

        return info

    except Exception:
        return None


def format_sql_local(sql, db_type='mysql'):
    """
    本地 SQL 格式化

    返回:
        (formatted_sql, error)
    """
    try:
        dialect = DIALECT_MAP.get(db_type.lower())
        if dialect:
            parsed = parse(sql, read=dialect)
        else:
            parsed = parse(sql)

        if not parsed:
            return None, "无法解析 SQL"

        # 格式化每个语句
        formatted = []
        for stmt in parsed:
            if stmt:
                formatted.append(stmt.sql(pretty=True, dialect=dialect))

        return '\n\n'.join(formatted), None

    except Exception as e:
        return None, str(e)
