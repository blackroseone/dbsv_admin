"""Harness - 安全约束框架
核心理念：Agent必须通过规定的专用工具访问数据库和服务器
所有操作必须经过安全验证，禁止危险操作
"""
from enum import Enum
from typing import Dict, List, Optional, Tuple
import re
import sqlparse


class OperationLevel(Enum):
    """操作安全级别"""
    READONLY = "readonly"      # 只读查询
    DIAGNOSIS = "diagnosis"    # 诊断级（可执行show/status等）
    MAINTENANCE = "maintenance" # 维护级（可执行备份等）
    DANGEROUS = "dangerous"    # 危险操作（需二次确认）


class Harness:
    """安全约束框架"""

    # SQL白名单（按级别）
    SQL_WHITELIST = {
        OperationLevel.READONLY: {'SELECT', 'EXPLAIN', 'DESCRIBE', 'SHOW'},
        OperationLevel.DIAGNOSIS: {'SELECT', 'EXPLAIN', 'DESCRIBE', 'SHOW',
                                    'ALTER SESSION', 'SET'},
        OperationLevel.MAINTENANCE: {'SELECT', 'EXPLAIN', 'DESCRIBE', 'SHOW',
                                      'ALTER SESSION', 'SET', 'ANALYZE'},
    }

    # 危险SQL模式（黑名单）
    DANGEROUS_PATTERNS = [
        r'\b(DROP|DELETE|UPDATE|INSERT|CREATE|ALTER|TRUNCATE|GRANT|REVOKE)\b',
        r'\bEXEC\b\s*\(',
        r'\bINTO\s+OUTFILE\b',
        r';.*\b(SELECT|INSERT|UPDATE|DELETE)\b',
    ]

    # 命令白名单（按数据库类型）
    COMMAND_WHITELIST = {
        'oracle': {
            'crsctl': ['check', 'status', 'query', 'config'],
            'srvctl': ['status', 'config', 'start', 'stop'],
            'sqlplus': ['-S', '/ as sysdba', '-silent'],
            'lsnrctl': ['status', 'services', 'start', 'stop'],
            'expdp': ['--help'],
            'rman': ['target', 'catalog'],
        },
        'mysql': {
            'mysql': ['-e', '-u', '-p', '-h', '-P', '--show-warnings'],
            'mysqldump': ['--single-transaction', '--no-data', '--schema-only',
                          '-u', '-p', '-h', '-P'],
            'mysqladmin': ['status', 'processlist', 'extended-status', 'ping'],
        },
        'dm': {
            'disql': ['-S', '-e'],
            'dexp': ['--help'],
            'dimp': ['--help'],
        }
    }

    @classmethod
    def validate_sql(cls, sql: str, level: OperationLevel = OperationLevel.READONLY) -> Tuple[bool, str]:
        """验证SQL安全性

        Returns:
            (is_safe, error_message)
        """
        if not sql or not sql.strip():
            return False, "SQL语句为空"

        # 1. 解析SQL
        try:
            parsed = sqlparse.parse(sql)
        except Exception as e:
            return False, f"SQL解析失败: {e}"

        # 2. 检查语句类型
        allowed = cls.SQL_WHITELIST.get(level, set())
        for statement in parsed:
            first_token = None
            for token in statement.tokens:
                if token.ttype in (sqlparse.tokens.DML, sqlparse.tokens.DDL):
                    first_token = token.value.upper()
                    break

            if first_token and first_token not in allowed:
                return False, f"禁止执行 {first_token} 语句（当前级别: {level.value}）"

        # 3. 正则匹配危险模式
        upper_sql = sql.upper()
        for pattern in cls.DANGEROUS_PATTERNS:
            if re.search(pattern, upper_sql):
                return False, "检测到潜在危险操作，已阻止执行"

        return True, None

    @classmethod
    def validate_command(cls, command: str, db_type: str) -> Tuple[bool, str]:
        """验证命令安全性

        Returns:
            (is_safe, error_message)
        """
        if not command or not command.strip():
            return False, "命令为空"

        # 1. 提取命令名
        cmd_parts = command.strip().split()
        if not cmd_parts:
            return False, "空命令"

        cmd_name = cmd_parts[0]

        # 2. 检查是否在白名单中
        whitelist = cls.COMMAND_WHITELIST.get(db_type, {})
        if cmd_name not in whitelist:
            return False, f"命令 {cmd_name} 不在白名单中（数据库类型: {db_type}）"

        # 3. 检查参数
        dangerous_args = ['rm', 'dd', 'mkfs', '>', '|', '&&', '||']
        for arg in cmd_parts[1:]:
            if any(d in arg for d in dangerous_args):
                return False, f"检测到危险参数: {arg}"

        return True, None

    @classmethod
    def get_allowed_commands(cls, db_type: str) -> Dict[str, List[str]]:
        """获取允许执行的命令列表"""
        return cls.COMMAND_WHITELIST.get(db_type, {})

    @classmethod
    def get_allowed_sql_types(cls, level: OperationLevel = OperationLevel.READONLY) -> set:
        """获取允许的SQL类型"""
        return cls.SQL_WHITELIST.get(level, set())
