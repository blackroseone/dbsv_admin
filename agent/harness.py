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

    # 危险SQL关键字（黑名单，token级扫描，忽略字符串与注释）
    DANGEROUS_SQL_KEYWORDS = {'DROP', 'DELETE', 'UPDATE', 'INSERT', 'CREATE', 'ALTER',
                              'TRUNCATE', 'GRANT', 'REVOKE', 'EXEC', 'OUTFILE',
                              'DUMPFILE', 'LOAD_FILE'}

    # 命令策略（按数据库类型）：
    #   level: 命令要求的最低操作级别
    #   actions: 允许的动作词（必须至少出现一个）
    #   blocked_actions: 需要更高级别的动作词 {动作词: 要求级别}
    # SQL 客户端命令（mysql/sqlplus/disql）有意不在白名单中，SQL 统一走
    # query_database 工具（受 validate_sql 保护），避免 -e/@脚本 绕过校验。
    COMMAND_POLICY = {
        'oracle': {
            'crsctl': {'level': OperationLevel.READONLY,
                       'actions': ['check', 'status', 'query', 'config']},
            'srvctl': {'level': OperationLevel.READONLY,
                       'actions': ['status', 'config'],
                       'blocked_actions': {'start': OperationLevel.MAINTENANCE,
                                           'stop': OperationLevel.MAINTENANCE}},
            'lsnrctl': {'level': OperationLevel.READONLY,
                        'actions': ['status', 'services'],
                        'blocked_actions': {'start': OperationLevel.MAINTENANCE,
                                            'stop': OperationLevel.MAINTENANCE}},
            'rman': {'level': OperationLevel.MAINTENANCE},
            'expdp': {'level': OperationLevel.MAINTENANCE},
        },
        'mysql': {
            'mysqladmin': {'level': OperationLevel.READONLY,
                           'actions': ['status', 'processlist', 'extended-status', 'ping']},
            'mysqldump': {'level': OperationLevel.MAINTENANCE},
        },
        'dm': {
            'dexp': {'level': OperationLevel.MAINTENANCE},
            'dimp': {'level': OperationLevel.MAINTENANCE},
        },
    }

    # 通用 Linux 只读诊断命令（跨数据库类型，服务器 OS 层面巡检）。
    # 这些命令无副作用、不依赖 db_type；参数视为数据而非可执行对象，
    # 因此只做路径穿越检查、不扫危险 token（避免误伤 grep sudo 等 pattern）。
    READONLY_DIAGNOSTIC_COMMANDS = {
        'ps', 'grep', 'pgrep', 'df', 'free', 'top', 'netstat', 'ss',
        'cat', 'ls', 'uptime', 'who', 'w', 'uname', 'lscpu', 'lsmem',
        'du', 'wc', 'head', 'tail', 'sort', 'uniq', 'ip', 'hostname',
        'date', 'id', 'last', 'dmesg', 'lsof', 'vmstat', 'iostat',
        'sar', 'mpstat', 'pidstat', 'lsblk', 'blkid', 'mount', 'findmnt',
        'ethtool', 'ipcs',
    }

    # 需限制动作词的系统服务命令（仅放行只读动作）
    READONLY_SERVICE_COMMANDS = {
        'systemctl': {'actions': ['status', 'list-units', 'is-active', 'show']},
        'service': {'actions': ['status']},
        'chkconfig': {'actions': ['--list']},
    }

    LEVEL_ORDER = {
        OperationLevel.READONLY: 0,
        OperationLevel.DIAGNOSIS: 1,
        OperationLevel.MAINTENANCE: 2,
        OperationLevel.DANGEROUS: 3,
    }

    # 命令级危险特征（作用于整个命令串/参数 token）
    DANGEROUS_METACHARS = [';', '|', '>', '<', '&', '`', '$(', '${']
    DANGEROUS_TOKENS = {'rm', 'dd', 'mkfs', 'mkfifo', 'sh', 'bash', 'sudo', 'su',
                        'wget', 'curl', 'nc', 'python', 'perl'}

    @classmethod
    def validate_sql(cls, sql: str, level: OperationLevel = OperationLevel.READONLY) -> Tuple[bool, str]:
        """验证SQL安全性

        校验前先剥离注释（/* */、--、#），防止用注释拆分关键字绕过。
        逐语句检查主导动作是否在级别白名单内，并扫描危险关键字
        （忽略字符串字面量与注释，避免误报）。

        Returns:
            (is_safe, error_message)
        """
        if not sql or not sql.strip():
            return False, "SQL语句为空"

        # 1. 剥离注释（含 MySQL 的 # 注释），防止 DE/**/LETE 之类绕过
        try:
            clean_sql = sqlparse.format(sql, strip_comments=True, reindent=False)
        except Exception:
            clean_sql = sql
        clean_sql = re.sub(r'#[^\n]*', ' ', clean_sql)

        # 2. 解析去注释后的 SQL
        try:
            parsed = sqlparse.parse(clean_sql)
        except Exception as e:
            return False, f"SQL解析失败: {e}"

        # 3. 逐语句检查
        allowed = cls.SQL_WHITELIST.get(level, set())
        for statement in parsed:
            if statement.is_whitespace:
                continue
            action = cls._first_action(statement)
            if action is None:
                return False, "无法识别SQL语句类型"
            if action not in allowed:
                return False, f"禁止执行 {action} 语句（当前级别: {level.value}）"
            # 危险关键字扫描仅针对 SELECT：SHOW/EXPLAIN/DESCRIBE 语句天然只读，
            # 其中的 CREATE/ALTER 等是对象描述而非执行（如 SHOW CREATE TABLE）
            if action == 'SELECT' and cls._has_dangerous_token(statement):
                return False, "检测到潜在危险操作，已阻止执行"

        return True, None

    @staticmethod
    def _first_action(statement) -> Optional[str]:
        """返回语句的主导动作关键字（大写），跳过 CTE 前缀（WITH/AS/RECURSIVE）"""
        for token in statement.flatten():
            if token.is_whitespace or token.ttype in sqlparse.tokens.Comment:
                continue
            ttype = token.ttype
            if ttype in (sqlparse.tokens.DML, sqlparse.tokens.DDL):
                return token.value.upper()
            if ttype in sqlparse.tokens.Keyword:
                val = token.value.upper()
                if val in ('WITH', 'AS', 'RECURSIVE'):
                    continue
                return val
            # 其他 token（名称/括号/数字等）：跳过继续找
        return None

    @classmethod
    def _has_dangerous_token(cls, statement) -> bool:
        """扫描非字符串/非注释 token 中的危险关键字

        对任意非字符串/非注释 token 按精确值匹配（如 OUTFILE/LOAD_FILE 这类
        sqlparse 不识别为关键字的 Name token 也能命中）。
        """
        for token in statement.flatten():
            if token.is_whitespace or token.ttype in sqlparse.tokens.Comment:
                continue
            if token.ttype in sqlparse.tokens.String:
                continue
            if token.value.upper() in cls.DANGEROUS_SQL_KEYWORDS:
                return True
        return False

    @classmethod
    def validate_command(cls, command: str, db_type: str,
                         level: OperationLevel = OperationLevel.READONLY) -> Tuple[bool, str]:
        """验证命令安全性

        校验：危险元字符（不含管道）→ 按 `|` 分段 → 每段单独校验
        （数据库专用命令或通用只读诊断命令）。

        允许只读命令之间用单管道连接（如 `ps -ef | grep dmserver`），
        但整串仍禁止 `;`/`&&`/`||`/重定向/命令替换等注入特征。

        Returns:
            (is_safe, error_message)
        """
        if not command or not command.strip():
            return False, "命令为空"

        # 禁止换行/控制字符（多行命令注入）
        if re.search(r'[\n\r\t\x00-\x08\x0b\x0c\x0e-\x1f]', command):
            return False, "检测到危险控制字符"

        # 危险元字符：不含单个管道 |（单管道按段受控放行），但 || 仍拦截
        for m in (';', '&', '>', '<', '`', '$(', '${', '||'):
            if m in command:
                return False, f"检测到危险字符: {m}"

        # 按管道分段，逐段校验
        segments = [s.strip() for s in command.split('|')]
        if any(not s for s in segments):
            return False, "管道存在空命令段"

        for seg in segments:
            ok, err = cls._validate_single_command(seg, db_type, level)
            if not ok:
                return False, err

        return True, None

    @classmethod
    def _validate_single_command(cls, command: str, db_type: str,
                                 level: OperationLevel) -> Tuple[bool, str]:
        """校验单段命令（无管道）：数据库专用命令或通用只读诊断命令"""
        cmd_parts = command.strip().split()
        if not cmd_parts:
            return False, "空命令"
        cmd_name = cmd_parts[0]

        # 1. 数据库专用命令（按 db_type 策略）
        policy = cls.COMMAND_POLICY.get(db_type, {}).get(cmd_name)
        if policy is not None:
            return cls._validate_policy_command(cmd_name, cmd_parts, policy, level)

        # 2. 通用只读诊断命令
        if cmd_name in cls.READONLY_DIAGNOSTIC_COMMANDS:
            return cls._validate_diagnostic_command(cmd_name, cmd_parts)

        # 3. 需限制动作词的系统服务命令
        svc_policy = cls.READONLY_SERVICE_COMMANDS.get(cmd_name)
        if svc_policy is not None:
            return cls._validate_policy_command(cmd_name, cmd_parts, svc_policy, level)

        return False, f"命令 {cmd_name} 不在白名单中（数据库类型: {db_type}）"

    @classmethod
    def _validate_policy_command(cls, cmd_name: str, cmd_parts: List[str],
                                 policy: Dict, level: OperationLevel) -> Tuple[bool, str]:
        """校验带策略的命令：级别门槛 → 危险动作 → 动作词 → 危险参数扫描"""
        min_level = policy.get('level', OperationLevel.READONLY)
        if cls.LEVEL_ORDER[level] < cls.LEVEL_ORDER[min_level]:
            return False, f"命令 {cmd_name} 需要级别 {min_level.value}，当前级别 {level.value}"

        blocked = policy.get('blocked_actions', {})
        for arg in cmd_parts[1:]:
            if arg in blocked and cls.LEVEL_ORDER[level] < cls.LEVEL_ORDER[blocked[arg]]:
                return False, f"子命令 {arg} 需要级别 {blocked[arg].value}，当前级别 {level.value}"

        actions = policy.get('actions')
        if actions and not any(a in cmd_parts[1:] for a in actions):
            return False, f"命令 {cmd_name} 缺少允许的动作词（{', '.join(actions)}）"

        return cls._check_dangerous_args(cmd_parts, check_tokens=True)

    @classmethod
    def _validate_diagnostic_command(cls, cmd_name: str,
                                     cmd_parts: List[str]) -> Tuple[bool, str]:
        """校验通用只读诊断命令：仅做路径穿越检查，参数视为数据不扫危险 token"""
        return cls._check_dangerous_args(cmd_parts, check_tokens=False)

    @classmethod
    def _check_dangerous_args(cls, cmd_parts: List[str],
                              check_tokens: bool = True) -> Tuple[bool, str]:
        """扫描命令参数的全局危险特征（危险 token / 路径穿越）"""
        for arg in cmd_parts[1:]:
            if check_tokens and arg in cls.DANGEROUS_TOKENS:
                return False, f"检测到危险参数: {arg}"
            if '..' in arg:
                return False, f"检测到危险路径参数: {arg}"
        return True, None

    # ==================== 变更类操作校验（审批后执行前二次校验） ====================

    # 参数/配置变更 SQL 白名单（主导语句必须命中其一）
    CHANGE_SQL_WHITELIST = [
        (re.compile(r'ALTER\s+SYSTEM\s+SET', re.I), 'ALTER SYSTEM SET'),
        (re.compile(r'SET\s+GLOBAL', re.I), 'SET GLOBAL'),
        (re.compile(r'ALTER\s+SESSION\s+SET', re.I), 'ALTER SESSION SET'),
        (re.compile(r'ALTER\s+DATABASE\s+\S+\s+SET', re.I), 'ALTER DATABASE SET'),
    ]
    # 变更 SQL 危险关键字（一旦出现即拒绝；ALTER 由白名单模式管控，不入黑名单）
    CHANGE_SQL_BLACKLIST = {'DROP', 'DELETE', 'UPDATE', 'INSERT', 'TRUNCATE',
                            'GRANT', 'REVOKE', 'CREATE', 'EXEC', 'EXECUTE',
                            'OUTFILE', 'LOAD_FILE', 'RENAME'}

    @classmethod
    def validate_change_sql(cls, sql: str) -> Tuple[bool, str]:
        """校验变更 SQL：仅放行参数/配置变更语句（ALTER SYSTEM SET / SET GLOBAL /
        ALTER SESSION SET / ALTER DATABASE ... SET）。

        用于操作计划经 DBA 审批后、引擎执行前的二次校验，防止被污染的计划
        执行危险语句（DROP/UPDATE/INSERT 等）。
        """
        if not sql or not sql.strip():
            return False, "SQL为空"
        try:
            clean_sql = sqlparse.format(sql, strip_comments=True, reindent=False)
        except Exception:
            clean_sql = sql
        clean_sql = re.sub(r'#[^\n]*', ' ', clean_sql)

        matched = None
        for pat, label in cls.CHANGE_SQL_WHITELIST:
            if pat.search(clean_sql):
                matched = label
                break
        if matched is None:
            return False, ("仅允许参数/配置变更语句"
                           "（ALTER SYSTEM SET / SET GLOBAL / ALTER SESSION SET / ALTER DATABASE ... SET）")

        try:
            parsed = sqlparse.parse(clean_sql)
        except Exception as e:
            return False, f"SQL解析失败: {e}"
        for statement in parsed:
            for token in statement.flatten():
                if token.is_whitespace or token.ttype in sqlparse.tokens.Comment:
                    continue
                if token.ttype in sqlparse.tokens.String:
                    continue
                if token.value.upper() in cls.CHANGE_SQL_BLACKLIST:
                    return False, f"检测到危险关键字: {token.value}"
        return True, None

    @classmethod
    def validate_change_command(cls, command: str, db_type: str) -> Tuple[bool, str]:
        """校验变更命令：必须在 COMMAND_POLICY 白名单内、级别 ≥ MAINTENANCE、
        且含需审批的变更类动作（blocked_actions 中的 start/stop 等），
        而非只读 check/status。独立校验全局危险特征。

        注意：不依赖 validate_command 的只读 actions 检查（该检查会把
        start/stop 等变更动作一并拒绝）；变更命令走本方法独立语义。
        """
        if not command or not command.strip():
            return False, "命令为空"
        if re.search(r'[\n\r\t\x00-\x08\x0b\x0c\x0e-\x1f]', command):
            return False, "检测到危险控制字符"

        cmd_parts = command.strip().split()
        if not cmd_parts:
            return False, "空命令"
        cmd_name = cmd_parts[0]
        policy = cls.COMMAND_POLICY.get(db_type, {}).get(cmd_name)
        if policy is None:
            return False, f"命令 {cmd_name} 不在白名单中（数据库类型: {db_type}）"

        min_level = policy.get('level', OperationLevel.READONLY)
        if cls.LEVEL_ORDER[OperationLevel.MAINTENANCE] < cls.LEVEL_ORDER[min_level]:
            return False, f"命令 {cmd_name} 需要级别 {min_level.value}"

        blocked = policy.get('blocked_actions', {})
        if not any(arg in blocked for arg in cmd_parts[1:]):
            return False, "命令不含需审批的变更类动作（start/stop/…）"

        for arg in cmd_parts[1:]:
            if any(m in arg for m in cls.DANGEROUS_METACHARS):
                return False, f"检测到危险参数: {arg}"
            if arg in cls.DANGEROUS_TOKENS:
                return False, f"检测到危险参数: {arg}"
            if '..' in arg:
                return False, f"检测到危险路径参数: {arg}"
        return True, None

    @classmethod
    def get_allowed_commands(cls, db_type: str) -> Dict[str, List[str]]:
        """获取允许执行的命令列表（命令名 → 允许的动作词/要求级别）"""
        return cls.COMMAND_POLICY.get(db_type, {})

    @classmethod
    def get_allowed_sql_types(cls, level: OperationLevel = OperationLevel.READONLY) -> set:
        """获取允许的SQL类型"""
        return cls.SQL_WHITELIST.get(level, set())
