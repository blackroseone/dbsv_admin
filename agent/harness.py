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
            # 实例创建（安装类，本身即变更，is_change=True 走审批）
            'dbca': {'level': OperationLevel.MAINTENANCE, 'is_change': True},
        },
        'mysql': {
            'mysqladmin': {'level': OperationLevel.READONLY,
                           'actions': ['status', 'processlist', 'extended-status', 'ping']},
            'mysqldump': {'level': OperationLevel.MAINTENANCE},
            # 实例初始化/启动
            'mysqld': {'level': OperationLevel.MAINTENANCE, 'is_change': True},
            'mysql_install_db': {'level': OperationLevel.MAINTENANCE, 'is_change': True},
        },
        'dm': {
            'dexp': {'level': OperationLevel.MAINTENANCE},
            'dimp': {'level': OperationLevel.MAINTENANCE},
            # 实例创建/启动/服务注册
            'dminit': {'level': OperationLevel.MAINTENANCE, 'is_change': True},
            'dmserver': {'level': OperationLevel.MAINTENANCE, 'is_change': True},
            'dm_service_installer': {'level': OperationLevel.MAINTENANCE, 'is_change': True},
        },
        'gaussdb': {
            # 实例初始化/启动（GaussDB/PostgreSQL）
            'gs_initdb': {'level': OperationLevel.MAINTENANCE, 'is_change': True},
            'gs_ctl': {'level': OperationLevel.MAINTENANCE, 'is_change': True},
            'initdb': {'level': OperationLevel.MAINTENANCE, 'is_change': True},
            'pg_ctl': {'level': OperationLevel.MAINTENANCE, 'is_change': True},
        },
    }

    # 数据库类型别名归并：国产库复用同族策略（与 connectors.run_sql 一致）
    # tdsql/oceanbase/goldendb → mysql，便于 COMMAND_POLICY 按族查找。
    DB_TYPE_ALIASES = {
        'tdsql': 'mysql', 'oceanbase': 'mysql', 'goldendb': 'mysql',
        'postgresql': 'gaussdb',
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
        'ethtool', 'ipcs', 'which', 'find', 'echo',
        # 管道内纯文本处理（字段提取/替换/切片等）
        'awk', 'sed', 'cut', 'tr', 'expr', 'printf', 'basename', 'dirname',
        'rev', 'paste', 'join', 'nl', 'od', 'hexdump',
    }
    # 只读诊断命令中禁止出现的破坏性参数（如 find -delete/-exec/-ok，精确匹配）
    DIAGNOSTIC_FORBIDDEN_ARGS = {
        'find': {'-delete', '-exec', '-ok', '-execdir', '-okdir'},
        'sed': {'-i', '--in-place'},  # sed 就地改写文件是写操作，非只读诊断
    }
    # 只读诊断命令中禁止的参数子串（awk/sed 的代码执行/注入向量）
    DIAGNOSTIC_FORBIDDEN_SUBSTR = {
        'awk': ['system(', 'popen(', 'getline'],
        'sed': ['system(', 'popen('],
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
    def _normalize_db_type(cls, db_type: str) -> str:
        """归一化数据库类型（国产库归并到同族，与 connectors.run_sql 一致）"""
        if not db_type:
            return db_type
        return cls.DB_TYPE_ALIASES.get(db_type.lower(), db_type.lower())

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

        # 纯只读诊断命令链（如 `ps -ef | grep x`、`cat a 2>/dev/null || cat b`）→ 放行
        if cls._is_diagnostic_chain(command):
            return True, None

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
        policy = cls.COMMAND_POLICY.get(cls._normalize_db_type(db_type), {}).get(cmd_name)
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
        """校验通用只读诊断命令：路径穿越检查 + 破坏性参数/代码执行向量拦截，
        参数视为数据不扫危险 token（避免误伤 grep sudo 等 pattern）。"""
        forbidden = cls.DIAGNOSTIC_FORBIDDEN_ARGS.get(cmd_name, set())
        if forbidden and any(t in forbidden for t in cmd_parts[1:]):
            return False, f"检测到破坏性参数: {next(t for t in cmd_parts[1:] if t in forbidden)}"
        substrs = cls.DIAGNOSTIC_FORBIDDEN_SUBSTR.get(cmd_name, [])
        for arg in cmd_parts[1:]:
            for s in substrs:
                if s in arg:
                    return False, f"检测到危险参数: {s}"
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

    @classmethod
    def _is_diagnostic_chain(cls, command: str) -> bool:
        """判断命令是否为「纯只读诊断命令链」。

        由只读诊断命令通过 ; / && / || / | 分隔，可带 2>/dev/null、>/dev/null 重定向
        （抑制 stderr/清空输出）。只要每一段都是 READONLY_DIAGNOSTIC_COMMANDS 内的
        命令且无破坏性参数（如 find -delete/-exec），就视为安全的只读巡检放行。

        背景执行 &、命令替换、任意重定向（非 /dev/null）等一律不算诊断链。
        """
        if not command or not command.strip():
            return False
        # 背景执行 &、命令替换、变量展开 → 非诊断链
        if re.search(r'(?<![&|])&(?![&|])', command) or '`' in command \
                or '${' in command or '$(' in command:
            return False
        # 去除 /dev/null 重定向（2>/dev/null、>/dev/null、1>/dev/null，允许空格）
        cleaned = re.sub(r'\d*\s*>\s*/dev/null', '', command)
        if not cleaned.strip():
            return False
        # 仍有其他重定向（> 到非 /dev/null，或 < 输入重定向）→ 非诊断链
        if re.search(r'[<>]', cleaned):
            return False
        # 按分隔符分段（; || && |），逐段必须是只读诊断命令且通过统一校验
        parts = re.split(r'\s*(?:;|\|\||&&|\|)\s*', cleaned)
        for seg in parts:
            seg = seg.strip()
            if not seg:
                return False
            toks = seg.split()
            if toks[0] not in cls.READONLY_DIAGNOSTIC_COMMANDS:
                return False
            ok, _ = cls._validate_diagnostic_command(toks[0], toks)
            if not ok:
                return False
        return True

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
        """校验变更命令：必须在 COMMAND_POLICY 白名单内、级别 ≥ MAINTENANCE，
        且为变更类操作——即命中 blocked_actions 中的 start/stop 等动作词，
        或命令本身标记 is_change=True（如 dminit 创建实例，无只读用法）。
        独立校验全局危险特征。

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
        policy = cls.COMMAND_POLICY.get(cls._normalize_db_type(db_type), {}).get(cmd_name)
        if policy is None:
            return False, f"命令 {cmd_name} 不在白名单中（数据库类型: {db_type}）"

        min_level = policy.get('level', OperationLevel.READONLY)
        if cls.LEVEL_ORDER[OperationLevel.MAINTENANCE] < cls.LEVEL_ORDER[min_level]:
            return False, f"命令 {cmd_name} 需要级别 {min_level.value}"

        # 变更类判定：命令本身标记 is_change，或命中 blocked_actions 变更动作词
        blocked = policy.get('blocked_actions', {})
        is_change = policy.get('is_change', False)
        if not is_change and not any(arg in blocked for arg in cmd_parts[1:]):
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

    # ==================== 三态分类（供引擎决定执行/审批/拒绝） ====================

    @classmethod
    def classify_command(cls, command: str, db_type: str) -> Tuple[str, Optional[str]]:
        """命令三态分类

        - safe：只读白名单（含只读诊断命令管道），直接执行免审批
        - approval：变更类命令（is_change/start/stop）或非注入的未知命令，走审批
        - reject：命令注入特征（; && || 重定向 命令替换等），硬拒绝

        Returns:
            (classification, reason)；reason 为 None 表示无需说明
        """
        if not command or not command.strip():
            return 'reject', "命令为空"
        if re.search(r'[\n\r\t\x00-\x08\x0b\x0c\x0e-\x1f]', command):
            return 'reject', "检测到危险控制字符"

        # 纯只读诊断命令链（ps|grep、cat 2>/dev/null || cat 等）→ 直接执行免审批
        if cls._is_diagnostic_chain(command):
            return 'safe', None

        # 危险命令名（rm/dd/mkfs/...）→ 硬拒绝，即使走审批也不允许
        cmd_name = command.strip().split()[0]
        if cmd_name in cls.DANGEROUS_TOKENS:
            return 'reject', f"危险命令: {cmd_name}"

        # 硬注入特征（不含单管道 |）
        for m in (';', '&', '>', '<', '`', '$(', '${', '||'):
            if m in command:
                return 'reject', f"检测到危险注入特征: {m}"

        # 只读白名单（含 ps|grep 等只读诊断管道）→ 直接执行
        is_safe, err = cls.validate_command(command, db_type, OperationLevel.READONLY)
        if is_safe:
            return 'safe', None

        # 已知只读诊断命令但校验失败（如 find -delete 破坏性参数）→ 硬拒绝
        if cmd_name in cls.READONLY_DIAGNOSTIC_COMMANDS:
            return 'reject', f"只读诊断命令校验失败: {err}"

        # 含管道的非只读命令 → 拒绝（管道在变更/未知场景是注入风险）
        if '|' in command:
            return 'reject', "检测到危险管道注入"

        # 变更白名单 → 审批
        is_change, _ = cls.validate_change_command(command, db_type)
        if is_change:
            return 'approval', None

        # 非注入的未知命令 → 审批（审批权交给用户，而非硬拒绝）
        cmd_name = command.strip().split()[0]
        return 'approval', f"命令 {cmd_name} 不在白名单，需审批后执行"

    @classmethod
    def classify_sql(cls, sql: str) -> Tuple[str, Optional[str]]:
        """SQL 三态分类：safe（只读直接执行）/ approval（变更走审批）/ reject（危险拒绝）"""
        if not sql or not sql.strip():
            return 'reject', "SQL为空"
        is_safe, _ = cls.validate_sql(sql, OperationLevel.READONLY)
        if is_safe:
            return 'safe', None
        is_change, _ = cls.validate_change_sql(sql)
        if is_change:
            return 'approval', None
        return 'reject', "SQL 既非只读也非可审批的变更语句"
