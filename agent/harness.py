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
    #   actions: 允许的只读动作词（必须至少出现一个）
    #   blocked_actions: 需更高权限的变更动作词 {动作词: 要求级别}
    #   is_change: 命令本身即变更（如 dminit 创建实例）
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

    # ==================== 命令安全目录（分级） ====================

    # T1 硬拒绝命令：不可逆破坏 / 系统关停 / 磁盘分区 / 代码执行 / 提权 / 外联。
    # 即使经 LLM 审查也只降级到审批（DBA 决策），绝不直接执行。
    REJECT_COMMANDS = {
        # 文件/数据不可逆破坏
        'rm', 'shred', 'dd', 'mkfs', 'mkfifo', 'mknod', 'truncate', 'unlink',
        # 文件系统/磁盘分区
        'mkswap', 'swapon', 'swapoff', 'fdisk', 'parted', 'sfdisk', 'gdisk',
        'mdadm', 'pvcreate', 'vgcreate', 'lvcreate', 'pvremove', 'vgremove', 'lvremove',
        # 系统关停
        'shutdown', 'reboot', 'halt', 'poweroff', 'init', 'telinit',
        # 代码执行 / 提权 / 外联
        # 注：su 已从硬拒改为受控门控（仅 -c 命令形式 + 非 root + 内层只读），见 _is_controlled_su_readonly
        'sh', 'bash', 'zsh', 'dash', 'python', 'python2', 'python3', 'perl',
        'ruby', 'php', 'lua', 'node', 'gcc', 'cc', 'g++', 'make',
        'nc', 'ncat', 'socat', 'wget', 'curl', 'sudo', 'scp', 'sftp', 'rsync',
    }
    # 前缀匹配的硬拒绝（如 mkfs.ext4）
    REJECT_COMMAND_PREFIXES = ('mkfs.',)

    # T2 纯只读命令：参数视为数据，仅做路径穿越检查（不扫危险 token，避免误伤
    # grep/awk 等 pattern）。含命令自身无写语义、无参数级写向量的命令。
    ALWAYS_READONLY_COMMANDS = {
        # 进程/资源状态
        'ps', 'pstree', 'pgrep', 'pidof', 'top', 'htop', 'free', 'vmstat',
        'iostat', 'mpstat', 'sar', 'pidstat', 'uptime', 'w', 'who', 'last', 'id',
        'nproc', 'getconf', 'hostid',
        # 系统信息/时间
        'uname', 'hostname', 'date', 'cal', 'lsmod', 'lsof', 'ss', 'netstat',
        'ipcs', 'lspci', 'lsusb', 'lsblk', 'blkid', 'findmnt', 'lscpu',
        'lsmem', 'lshw', 'dmidecode', 'sensors',
        # 文件查看/文本处理（无就地写语义）
        'cat', 'ls', 'head', 'tail', 'sort', 'uniq', 'wc', 'cut', 'tr', 'expr',
        'printf', 'basename', 'dirname', 'rev', 'paste', 'join', 'nl', 'od',
        'hexdump', 'strings', 'stat', 'file', 'readlink', 'realpath', 'pwd',
        'which', 'whereis', 'type', 'tree', 'df', 'du', 'locate',
        'md5sum', 'sha1sum', 'sha256sum', 'cksum', 'cmp', 'diff', 'comm', 'fold',
        'fmt', 'column', 'expand', 'unexpand', 'tac', 'seq', 'echo',
        # 搜索/过滤
        'grep', 'egrep', 'fgrep', 'rg',
        # 解压到 stdout / 归档列表
        'zcat', 'bzcat', 'xzcat', 'lz4cat', 'zipinfo',
        # 网络只读查询
        'host', 'dig', 'nslookup', 'getent',
        # 环境只读查询
        'printenv',
    }

    # 短参数簇匹配（-dc/-tzc/-lv 等组合短参数按簇内字母判断，无法用 `-c\b` 精确锚定）
    _ARCHIVE_READONLY = [r'^-{1,2}[a-zA-Z]*[ctl][a-zA-Z]*$',
                         r'--stdout', r'--to-stdout', r'--test', r'--list']
    _ARCHIVE_DECOMPRESS = [r'^-{1,2}[a-zA-Z]*d[a-zA-Z]*$',
                           r'--decompress', r'--compress']

    # T3 参数门控命令：readonly（命中任一即只读放行，优先）/ change（命中任一即审批）
    # / reject（命中任一即硬拒）；无命中走 default。
    # 注：default 用 'safe'/'approval'/'reject' 三态（'readonly' 为 'safe' 的兼容别名）。
    PARAM_GATED_COMMANDS = {
        # 文本处理：无 -i 就地改写即只读；system(/popen( 是代码执行向量
        'sed': {'change': [r'^-{1,2}[a-zA-Z]*i[a-zA-Z]*$', r'--in-place'],
                'reject': [r'system\s*\(', r'popen\s*\('],
                'default': 'safe'},
        'awk': {'reject': [r'system\s*\(', r'popen\s*\(', r'getline'],
                'default': 'safe'},
        # find：-delete/-exec 等是破坏/任意执行向量
        'find': {'reject': [r'-delete\b', r'-exec\b', r'-ok\b', r'-execdir\b', r'-okdir\b'],
                 'change': [r'-fprint', r'-fprintf', r'-fls'],
                 'default': 'safe'},
        # 归档：仅列出/测试只读
        'tar': {'readonly': [r'^-t', r'^--list'],
                'change': [r'^-x', r'^-c', r'^-A', r'^-r', r'^-u', r'^-d',
                           r'--extract', r'--create', r'--delete', r'--remove-files'],
                'default': 'approval'},
        # 解压/压缩族：-c/-t/-l（组合簇）输出到 stdout / 测试 / 列表 → 只读；-d 就地解压 → 变更
        'gzip': {'readonly': list(_ARCHIVE_READONLY),
                 'change': list(_ARCHIVE_DECOMPRESS),
                 'default': 'approval'},
        'gunzip': {'readonly': list(_ARCHIVE_READONLY),
                   'change': list(_ARCHIVE_DECOMPRESS),
                   'default': 'approval'},
        'bzip2': {'readonly': list(_ARCHIVE_READONLY),
                  'change': list(_ARCHIVE_DECOMPRESS),
                  'default': 'approval'},
        'bunzip2': {'readonly': list(_ARCHIVE_READONLY),
                    'change': list(_ARCHIVE_DECOMPRESS),
                    'default': 'approval'},
        'xz': {'readonly': list(_ARCHIVE_READONLY),
               'change': list(_ARCHIVE_DECOMPRESS),
               'default': 'approval'},
        'unxz': {'readonly': list(_ARCHIVE_READONLY),
                 'change': list(_ARCHIVE_DECOMPRESS),
                 'default': 'approval'},
        'zstd': {'readonly': list(_ARCHIVE_READONLY),
                 'change': list(_ARCHIVE_DECOMPRESS),
                 'default': 'approval'},
        'unzstd': {'readonly': list(_ARCHIVE_READONLY),
                   'change': list(_ARCHIVE_DECOMPRESS),
                   'default': 'approval'},
        'lz4': {'readonly': list(_ARCHIVE_READONLY),
                'change': list(_ARCHIVE_DECOMPRESS),
                'default': 'approval'},
        'unzip': {'readonly': [r'^-{1,2}[a-zA-Z]*[lp][a-zA-Z]*$', r'-Z\b'],
                  'change': [r'^-{1,2}[a-zA-Z]*[xd][a-zA-Z]*$', r'--extract'],
                  'default': 'approval'},
        'zip': {'readonly': [r'^-{1,2}[a-zA-Z]*l[a-zA-Z]*$', r'--list'],
                'change': [r'^-{1,2}[a-zA-Z]*[xdufmr][a-zA-Z]*$'],
                'default': 'approval'},
        # 服务管理：只读动作 safe，启停/使能动作 approval
        'systemctl': {'readonly': [r'status\b', r'list-units', r'list-timers', r'list-sockets',
                                   r'is-active', r'is-enabled', r'is-failed', r'show\b', r'cat\b'],
                      'change': [r'start\b', r'stop\b', r'restart\b', r'reload\b',
                                 r'daemon-reload', r'enable\b', r'disable\b', r'mask\b',
                                 r'unmask\b', r'kill\b', r'isolate\b', r'set-default', r'reset-failed'],
                      'default': 'approval'},
        'service': {'readonly': [r'status\b'],
                    'change': [r'start\b', r'stop\b', r'restart\b', r'reload\b'],
                    'default': 'approval'},
        'chkconfig': {'readonly': [r'--list'],
                      'change': [r'on\b', r'off\b', r'reset\b'],
                      'default': 'approval'},
        # 系统参数：sysctl -w / = 是写
        'sysctl': {'change': [r'-w\b', r'='],
                   'default': 'safe'},
        # 内核日志：dmesg -c/-C 清空环形缓冲
        'dmesg': {'change': [r'-c\b', r'-C\b'],
                  'default': 'safe'},
        # 网卡参数：ethtool -s 等改参数
        'ethtool': {'change': [r'-s\b', r'-A\b', r'-G\b', r'-K\b', r'-L\b', r'-N\b', r'--set-'],
                    'default': 'safe'},
        # 计划任务：crontab -l 列表只读
        'crontab': {'readonly': [r'-l\b'],
                    'change': [r'-e\b', r'-r\b'],
                    'default': 'approval'},
        # 进程控制（用户确认：审批）：-l 列表只读
        'kill': {'readonly': [r'-l\b'],
                 'default': 'approval'},
        'killall': {'readonly': [r'-l\b'],
                    'default': 'approval'},
        'pkill': {'readonly': [r'-l\b'],
                  'default': 'approval'},
        # ip：show/list/裸子命令只读，增删改查审批（专用逻辑 _evaluate_ip）
        'ip': {'mode': 'ip'},
    }

    # T3 变更写操作：无只读用法，一律审批
    CHANGE_COMMANDS = {
        'cp', 'mv', 'ln', 'mkdir', 'rmdir', 'touch', 'chmod', 'chown', 'chgrp',
        'tee', 'install', 'rename', 'split', 'csplit', 'patch',
        'yum', 'dnf', 'apt', 'apt-get', 'rpm', 'dpkg', 'zypper',
    }

    # 包装命令：真正执行其参数（timeout/env/nice/watch/xargs 等）。
    # 不入任何只读白名单；被包装命令若为 T1 硬拒命令（如 `timeout 10 rm`）→ 硬拒。
    WRAPPER_COMMANDS = {'env', 'timeout', 'nice', 'watch', 'xargs',
                        'nohup', 'setsid', 'stdbuf', 'taskset'}

    # SQL 客户端命令：SQL 须走 query_database 工具校验，故不放入只读白名单；
    # 但当内嵌 SQL 可提取且通过 validate_sql 只读校验时放行（如 SSH 会话下
    # `su - dmdba -c 'disql ... -e SELECT'` / `disql ... <<< 'SELECT'`）。
    SQL_CLIENT_COMMANDS = {'disql', 'mysql', 'sqlplus', 'psql', 'gsql',
                           'isql', 'tsql', 'sqlite3', 'db2'}

    # 注入元字符（不含单管道 |；单管道按段受控放行，|| 仍拦截）
    INJECTION_METACHARS = (';', '&', '>', '<', '`', '$(', '${', '||')
    # 命令级危险特征（作用于变更命令参数 token）
    DANGEROUS_METACHARS = [';', '|', '>', '<', '&', '`', '$(', '${']

    # 可插拔的 LLM 审查钩子：judge_fn(command) -> {"allow": bool, "risk": str, "reason": str} | None。
    # 默认 None（纯静态，离线可用）；由引擎按配置挂载（agent/command_judge.py）。
    command_judge_fn = None

    LEVEL_ORDER = {
        OperationLevel.READONLY: 0,
        OperationLevel.DIAGNOSIS: 1,
        OperationLevel.MAINTENANCE: 2,
        OperationLevel.DANGEROUS: 3,
    }

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

    @staticmethod
    def _is_hard_rejected(cmd_name: str) -> bool:
        """T1 硬拒绝判定：精确名 + 前缀匹配（mkfs.*）"""
        if cmd_name in Harness.REJECT_COMMANDS:
            return True
        return any(cmd_name.startswith(p) for p in Harness.REJECT_COMMAND_PREFIXES)

    @staticmethod
    def _is_path_like(arg: str) -> bool:
        """参数是否「像路径」：仅此类参数才做 .. 穿越检查，避免误伤 grep 正则（a..b）"""
        return arg.startswith(('/', '.', '~')) or '/' in arg

    # ==================== 命令校验（融合判定） ====================

    @classmethod
    def validate_command(cls, command: str, db_type: str,
                         level: OperationLevel = OperationLevel.READONLY) -> Tuple[bool, str]:
        """验证命令是否可作为只读命令直接执行

        校验：只读链（含 ;/&&/||/| 与 /dev/null 重定向与只读命令替换）→ 放行；
        注入元字符 → 拦截；按 `|` 分段逐段评估（T1/T2/T3/数据库策略/变更）。
        未知命令段若有 LLM 审查钩子，审查 allow 则放行（与 classify_command 同一目标
        + 同一缓存，保证引擎 _validate_action 与 tools.py 双重校验一致）。

        Returns:
            (is_safe, error_message)
        """
        if not command or not command.strip():
            return False, "命令为空"

        # 禁止换行/控制字符（多行命令注入）
        if re.search(r'[\n\r\t\x00-\x08\x0b\x0c\x0e-\x1f]', command):
            return False, "检测到危险控制字符"

        # 纯只读诊断命令链（如 `ps -ef | grep x`、`cat a 2>/dev/null || cat b`）→ 放行
        if cls._is_diagnostic_chain(command, db_type):
            return True, None

        # 注入元字符：不含单个管道 |（单管道按段受控放行），但 || 仍拦截
        for m in cls.INJECTION_METACHARS:
            if m in command:
                return False, f"检测到危险字符: {m}"

        # 按管道分段（引号感知），逐段评估
        segments = [s.strip() for s in cls._split_shell(command, seps=('|',))]
        if any(not s for s in segments):
            return False, "管道存在空命令段"

        for seg in segments:
            toks = seg.split()
            seg_cls, err = cls._evaluate_segment(toks, db_type, level)
            if seg_cls == 'safe':
                continue
            # 未知命令段：LLM 审查整个命令串（第二意见，allow 则视为安全）
            if seg_cls == 'unknown' and cls.command_judge_fn is not None:
                verdict = cls._invoke_judge(command)
                if verdict and verdict.get('allow'):
                    continue
                return False, f"命令 {toks[0] if toks else ''} 不在白名单中（数据库类型: {db_type}）"
            return False, err or f"命令 {toks[0] if toks else ''} 校验失败"

        return True, None

    @classmethod
    def _invoke_judge(cls, command: str) -> Optional[Dict]:
        """调用可插拔 LLM 审查钩子；钩子异常/未挂载 → None（保持静态判定）"""
        judge_fn = cls.command_judge_fn
        if judge_fn is None:
            return None
        try:
            verdict = judge_fn(command)
            return verdict if isinstance(verdict, dict) else None
        except Exception as e:
            print(f"[Harness] LLM 审查调用异常（保持静态判定）: {e}")
            return None

    @classmethod
    def _evaluate_segment(cls, cmd_parts: List[str], db_type: str,
                          level: OperationLevel) -> Tuple[str, Optional[str]]:
        """评估单个命令段（无管道）：返回 'safe'/'approval'/'reject'/'unknown' + reason"""
        if not cmd_parts:
            return 'reject', '空命令'
        cmd_name = cmd_parts[0]

        # T1 硬拒绝
        if cls._is_hard_rejected(cmd_name):
            return 'reject', f"危险命令: {cmd_name}"

        # T2 纯只读：参数视为数据，仅路径穿越检查
        if cmd_name in cls.ALWAYS_READONLY_COMMANDS:
            for arg in cmd_parts[1:]:
                if cls._is_path_like(arg) and '..' in arg:
                    return 'reject', f"检测到危险路径参数: {arg}"
            return 'safe', None

        # T3 参数门控
        gate = cls.PARAM_GATED_COMMANDS.get(cmd_name)
        if gate is not None:
            return cls._evaluate_gated(cmd_parts, gate)

        # T3 变更写操作（无只读用法）→ 审批
        if cmd_name in cls.CHANGE_COMMANDS:
            return 'approval', None

        # 受控 su：仅 `-c <只读>` 形式且目标非 root；否则拒绝（su 单独/交互/root 切换）
        if cmd_name == 'su':
            if cls._is_controlled_su_readonly(' '.join(cmd_parts), db_type):
                return 'safe', None
            return 'reject', 'su 需以 -c 命令形式、目标非 root、内层只读'

        # SQL 客户端：内嵌 SQL 通过只读校验才放行（su -c 'disql ... -e SELECT' 同理）
        if cmd_name in cls.SQL_CLIENT_COMMANDS:
            return cls._evaluate_sql_client(' '.join(cmd_parts))

        # 数据库专用命令策略
        policy = cls.COMMAND_POLICY.get(cls._normalize_db_type(db_type), {}).get(cmd_name)
        if policy is not None:
            return cls._evaluate_policy(cmd_parts, policy, level)

        # 未知/包装命令：T1 命令名作为参数出现（如 `timeout 10 rm ...`）→ 硬拒
        if any(cls._is_hard_rejected(t) for t in cmd_parts[1:]):
            return 'reject', '命令参数含危险命令'
        return 'unknown', f"命令 {cmd_name} 不在白名单"

    @classmethod
    def _evaluate_gated(cls, cmd_parts: List[str], gate: Dict) -> Tuple[str, Optional[str]]:
        """参数门控命令评估：reject → readonly(safe) → change(approval) → default"""
        cmd_name = cmd_parts[0]
        if gate.get('mode') == 'ip':
            return cls._evaluate_ip(cmd_parts)
        args = cmd_parts[1:]

        def hit(patterns):
            for pat in patterns:
                for tok in args:
                    if re.search(pat, tok):
                        return True
            return False

        reject_pat = gate.get('reject')
        if reject_pat and hit(reject_pat):
            return 'reject', f"命令 {cmd_name} 含破坏性参数"

        readonly_pat = gate.get('readonly')
        if readonly_pat and hit(readonly_pat):
            return cls._check_gated_paths(cmd_name, args)

        change_pat = gate.get('change')
        if change_pat and hit(change_pat):
            return 'approval', None

        default = gate.get('default', 'approval')
        if default == 'readonly':
            default = 'safe'
        if default == 'safe':
            return cls._check_gated_paths(cmd_name, args)
        return default, None

    @classmethod
    def _check_gated_paths(cls, cmd_name: str, args: List[str]) -> Tuple[str, Optional[str]]:
        """只读门控放行前的路径穿越检查"""
        for arg in args:
            if cls._is_path_like(arg) and '..' in arg:
                return 'reject', f"检测到危险路径参数: {arg}"
        return 'safe', None

    @classmethod
    def _evaluate_ip(cls, cmd_parts: List[str]) -> Tuple[str, Optional[str]]:
        """ip 命令：show/list/裸子命令（addr/route/link/neigh）只读；增删改查审批"""
        args = cmd_parts[1:]
        change_verbs = ('add', 'del', 'set', 'up', 'down', 'replace', 'change', 'flush')
        if any(a in change_verbs for a in args):
            return 'approval', None
        if not args or any(a in ('show', 'list') for a in args):
            return 'safe', None
        if args[-1] in ('addr', 'route', 'link', 'neigh', 'address', 'maddr', 'mroute'):
            return 'safe', None
        return 'approval', None

    @classmethod
    def _evaluate_policy(cls, cmd_parts: List[str], policy: Dict,
                         level: OperationLevel) -> Tuple[str, Optional[str]]:
        """数据库专用命令策略：只读动作 safe；变更动作/特权工具 approval；畸形 reject"""
        cmd_name = cmd_parts[0]
        actions = policy.get('actions') or []
        blocked = policy.get('blocked_actions', {})
        args = cmd_parts[1:]
        min_level = policy.get('level', OperationLevel.READONLY)

        # 变更动作（start/stop）或命令本身标记变更 → 审批
        if policy.get('is_change', False) or any(a in blocked for a in args):
            return 'approval', None
        # 只读动作命中：当前级别达标 → safe，否则提升为审批
        if actions and any(a in args for a in actions):
            if cls.LEVEL_ORDER[level] >= cls.LEVEL_ORDER[min_level]:
                return 'safe', None
            return 'approval', None
        # 无只读动作定义（备份/导出等特权工具，如 rman/mysqldump）→ 审批
        if not actions:
            return 'approval', None
        # 定义了只读动作但未命中 → 命令畸形
        return 'reject', f"命令 {cmd_name} 缺少允许的动作词（{', '.join(actions)}）"

    # ==================== 受控 su 与 SQL 客户端只读门 ====================

    @staticmethod
    def _strip_quoted(text: str) -> str:
        """把单/双引号包裹的内容（含转义）替换为空格，返回未加引号的骨架。

        用于只在引号外检测命令分隔符/元字符——引号内（如 SQL 里的 `;`、grep 正则
        里的 `|`）是数据而非 shell 分隔符。
        """
        out = []
        i, n = 0, len(text)
        in_s = in_d = False
        while i < n:
            ch = text[i]
            if in_s:
                if ch == "'":
                    in_s = False
                elif ch == '\\' and i + 1 < n:
                    out.append(' ')
                    out.append(' ')
                    i += 2
                    continue
                out.append(' ')
                i += 1
                continue
            if in_d:
                if ch == '"':
                    in_d = False
                elif ch == '\\' and i + 1 < n:
                    out.append(' ')
                    out.append(' ')
                    i += 2
                    continue
                out.append(' ')
                i += 1
                continue
            if ch == "'":
                in_s = True
                out.append(' ')
                i += 1
                continue
            if ch == '"':
                in_d = True
                out.append(' ')
                i += 1
                continue
            out.append(ch)
            i += 1
        return ''.join(out)

    @staticmethod
    def _extract_sql(text: str, allow_sql_keyword: bool = False) -> Optional[str]:
        """从命令串中提取内嵌 SQL。

        优先级：显式 `-e/--execute/<<<` 引号内容 → （allow_sql_keyword 时）任意以
        SELECT/SHOW/EXPLAIN/DESCRIBE/WITH 开头的引号串（覆盖 `disql -c "SQL;"`、
        `su ... -c 'disql' -c "SQL;"` 等写法）。
        支持单引号（含 DM 风格 '' 转义引号）与双引号（含 \\" 转义）包裹。
        """
        patterns = (
            r'(?:--execute|-e)\s*(\'((?:[^\']|\'\')*)\'|"((?:[^"]|\\")*)")',
            r'--execute\s*=\s*(\'((?:[^\']|\'\')*)\'|"((?:[^"]|\\")*)")',
            r'<<<\s*(\'((?:[^\']|\'\')*)\'|"((?:[^"]|\\")*)")',
        )
        for pat in patterns:
            m = re.search(pat, text)
            if m:
                return m.group(2) if m.group(2) is not None else m.group(3)
        if allow_sql_keyword:
            for qpat in (r"'((?:[^']|'')*)'", r'"((?:[^"]|\\")*)"'):
                for m in re.finditer(qpat, text):
                    cand = m.group(1)
                    if re.match(r'\s*(SELECT|SHOW|EXPLAIN|DESCRIBE|WITH)\b', cand, re.I):
                        return cand
        return None

    @classmethod
    def _evaluate_sql_client(cls, cmd_str: str) -> Tuple[str, Optional[str]]:
        """SQL 客户端命令：内嵌 SQL 通过只读校验才放行，否则审批/未知。"""
        sql = cls._extract_sql(cmd_str, allow_sql_keyword=True)
        if not sql:
            return 'unknown', '无法提取内嵌 SQL'
        # 归一化 DM 风格 '' 转义引号后校验（只读判定，不改变实际执行语义）
        is_safe, err = cls.validate_sql(re.sub(r"''", "'", sql), OperationLevel.READONLY)
        if is_safe:
            return 'safe', None
        return 'approval', f"内嵌 SQL 非只读，需审批: {err or ''}"

    @classmethod
    def _is_controlled_su_readonly(cls, command: str,
                                   db_type: Optional[str] = None) -> bool:
        """受控 su 只读判定：`su [-lm] <非root用户> -c '<只读命令>'`，可带只读 SQL。

        仅放行：
        - 必须 `-c` 命令形式（su 单独/交互式切换 → 拒绝）；
        - 目标用户非 root（`su - root` 仍拒绝）；
        - 内层为 SQL 客户端（disql/mysql 等，含路径）且内嵌 SQL 只读；或内层整条
          命令为只读链（`cat x | grep y` 这类管道）；
        - 外层骨架（引号内容剔除）不含命令分隔符/管道/重定向。
        引号内字符视为数据：SQL 末尾的 `;`、grep 正则里的 `|` 不再误判为注入。
        """
        if not command or not command.strip():
            return False
        cleaned = re.sub(r'\d*\s*>\s*/dev/null', '', command).strip()
        if not cleaned:
            return False
        toks = cleaned.split()
        if toks[0] != 'su':
            return False
        # 提取第一个 -c 引号命令（单引号含 '' 转义 / 双引号含 \" 转义）
        cm = re.search(r'-c\s+(\'((?:[^\']|\'\')*)\'|"((?:[^"]|\\")*)")', cleaned)
        if not cm:
            return False
        inner = cm.group(2) if cm.group(2) is not None else cm.group(3)
        if not inner or inner.split()[0] == 'su':
            return False  # 禁止嵌套 su
        # 目标用户：-c 前最后一个非选项参数；缺省为 root
        prefix = cleaned[:cm.start()]
        usertoks = [t for t in prefix.split() if not t.startswith('-') and t != 'su']
        user = usertoks[-1] if usertoks else 'root'
        if user == 'root':
            return False
        # 外层骨架（先摘掉 heredoc 区域，再剔除引号内容）：不得含命令分隔符/管道/
        # 重定向；`$()`/反引号由链逻辑下游兜底
        no_heredoc = re.sub(r'<<<\s*(\'((?:[^\']|\'\')*)\'|"((?:[^"]|\\")*)")',
                            ' ', cleaned)
        if re.search(r'[;&|<>]', cls._strip_quoted(no_heredoc)):
            return False
        inner_name = inner.split()[0]
        inner_base = inner_name.rsplit('/', 1)[-1]
        is_sql_client = inner_base in cls.SQL_CLIENT_COMMANDS
        if is_sql_client:
            # SQL 可能在 -c 内层（disql -e/-c 'SQL'）、外层第二个 -c 或 <<< heredoc
            sql = cls._extract_sql(inner, allow_sql_keyword=True) \
                or cls._extract_sql(cleaned, allow_sql_keyword=True)
        else:
            # 非 SQL 客户端：仅显式 -e/<<< 的 SQL
            sql = cls._extract_sql(cleaned, allow_sql_keyword=False)
        if sql:
            # 内层骨架不得含分隔符/危险命令（防 `-e 'SELECT 1'; rm -rf /`）
            if re.search(r'[;&|]', cls._strip_quoted(inner)):
                return False
            if any(cls._is_hard_rejected(t) for t in inner.split()):
                return False
            is_safe, _ = cls.validate_sql(re.sub(r"''", "'", sql), OperationLevel.READONLY)
            return is_safe
        # 无内嵌 SQL：内层整条命令须为只读链（含管道，如 `cat x | grep y`）
        return cls._is_diagnostic_chain(inner, db_type)

    @classmethod
    def _static_classify(cls, command: str, db_type: str) -> Tuple[str, Optional[str]]:
        """静态判定（纯脚本，不调 LLM）：safe / approval / reject / unknown"""
        if not command or not command.strip():
            return 'reject', '命令为空'
        if re.search(r'[\n\r\t\x00-\x08\x0b\x0c\x0e-\x1f]', command):
            return 'reject', '检测到危险控制字符'

        # 纯只读诊断命令链 → safe
        if cls._is_diagnostic_chain(command, db_type):
            return 'safe', None

        # 注入元字符（不含单管道 |）→ reject（交由融合矩阵决定是否降级审批）
        for m in cls.INJECTION_METACHARS:
            if m in command:
                return 'reject', f"检测到危险注入特征: {m}"

        # 按 | 分段逐段评估
        segments = [s.strip() for s in cls._split_shell(command, seps=('|',))]
        had_unknown = False
        for seg in segments:
            if not seg:
                return 'reject', '管道存在空命令段'
            toks = seg.split()
            seg_cls, reason = cls._evaluate_segment(toks, db_type, OperationLevel.READONLY)
            if seg_cls == 'reject':
                return 'reject', reason
            if seg_cls == 'approval':
                return 'approval', None
            if seg_cls == 'unknown':
                had_unknown = True
        if had_unknown:
            first = segments[0].strip().split()
            name = first[0] if first else ''
            return 'unknown', f"命令 {name} 不在白名单"
        return 'safe', None

    @classmethod
    def classify_command(cls, command: str, db_type: str) -> Tuple[str, Optional[str]]:
        """命令三态分类（融合判定矩阵）

        - safe：只读白名单（含只读诊断链），直接执行免审批
        - approval：变更类命令 / 脚本判拒绝但 LLM 判可放行的命令 / 未知待审批命令
        - reject：脚本与 LLM 均拒绝的命令（硬拒/注入）

        静态判定为 reject 或 unknown 时，若有 LLM 审查钩子，发起一次独立审查作
        第二意见：
          reject + allow → approval（DBA 决定，根治脚本误拒）
          reject + reject → reject
          unknown + allow → safe（只读直接执行）
          unknown + reject(high) → reject；unknown + reject(非high) → approval

        Returns:
            (classification, reason)；reason 为 None 表示无需说明
        """
        if not command or not command.strip():
            return 'reject', "命令为空"
        if re.search(r'[\n\r\t\x00-\x08\x0b\x0c\x0e-\x1f]', command):
            return 'reject', "检测到危险控制字符"

        static_cls, static_reason = cls._static_classify(command, db_type)

        # 静态 safe / approval → 快速路径直接返回（不调 LLM）
        if static_cls in ('safe', 'approval'):
            return static_cls, static_reason

        # 静态 reject / unknown → 独立 LLM 审查（第二意见）
        verdict = cls._invoke_judge(command)
        if verdict:
            allow = bool(verdict.get('allow'))
            risk = verdict.get('risk', 'medium')
            if static_cls == 'reject':
                if allow:
                    return 'approval', (f"静态判断拒绝，LLM 判读可放行"
                                        f"（{verdict.get('reason', '')}），需审批")
                return 'reject', static_reason
            # static unknown
            if allow:
                return 'safe', f"LLM判读只读放行: {verdict.get('reason', '')}"
            if risk == 'high':
                return 'reject', f"LLM判读危险: {verdict.get('reason', '')}"
            return 'approval', static_reason

        # 无 LLM 审查结果（未挂载/失败/返回空）：unknown 降级为审批，reject 保持拒绝
        if static_cls == 'unknown':
            return 'approval', static_reason
        return static_cls, static_reason

    @classmethod
    def _split_shell(cls, command: str, seps=('&&', '||', ';', '|')):
        """按 shell 分隔符切分命令，忽略引号内（单/双引号）的分隔符。

        用于命令链/管道的分段校验，避免 grep 模式里的 '|' 等被误拆成独立段。
        """
        parts = []
        current = []
        in_single = in_double = False
        i, n = 0, len(command)
        while i < n:
            ch = command[i]
            if in_single:
                current.append(ch)
                if ch == "'":
                    in_single = False
                i += 1
                continue
            if in_double:
                current.append(ch)
                if ch == '\\' and i + 1 < n:
                    current.append(command[i + 1])
                    i += 2
                    continue
                if ch == '"':
                    in_double = False
                i += 1
                continue
            if ch == "'":
                in_single = True
                current.append(ch)
                i += 1
                continue
            if ch == '"':
                in_double = True
                current.append(ch)
                i += 1
                continue
            matched = None
            for s in seps:
                if command.startswith(s, i):
                    matched = s
                    break
            if matched:
                parts.append(''.join(current))
                current = []
                i += len(matched)
                continue
            current.append(ch)
            i += 1
        parts.append(''.join(current))
        return parts

    @classmethod
    def _sanitize_safe_substitutions(cls, command: str,
                                     db_type: Optional[str] = None) -> Optional[str]:
        """把命令中的只读命令替换（$() 或反引号）替换为占位符。

        内层命令必须是只读命令且通过校验（如 $(date +%Y%m) 取当前月份日志）；
        否则返回 None（视为注入，如 $(rm -rf /)）。
        """
        invalid = False

        def repl(m):
            nonlocal invalid
            inner = m.group(1).strip()
            toks = inner.split()
            if not toks:
                invalid = True
                return m.group(0)
            seg_cls, _ = cls._evaluate_segment(toks, db_type or '',
                                               OperationLevel.READONLY)
            if seg_cls != 'safe':
                invalid = True
                return m.group(0)
            return 'X'  # 占位符

        for pat in (r'\$\(([^()]*)\)', r'`([^`]*)`'):
            command = re.sub(pat, repl, command)
            if invalid:
                return None
        return command

    @classmethod
    def _is_diagnostic_chain(cls, command: str,
                             db_type: Optional[str] = None) -> bool:
        """判断命令是否为「纯只读诊断命令链」。

        由只读命令通过 ; / && / || / | 分隔，可带 2>/dev/null、>/dev/null 重定向
        （抑制 stderr/清空输出），可含只读命令替换（$(date +%Y%m) 等）。
        只要每一段都评估为 safe（T2/T3 只读用法）就视为安全的只读巡检放行。

        背景执行 &、变量展开 ${、任意非 /dev/null 重定向、危险命令替换等不算诊断链。
        """
        if not command or not command.strip():
            return False
        # 背景执行 &、变量展开 ${ → 非诊断链
        if re.search(r'(?<![&|])&(?![&|])', command) or '${' in command:
            return False
        # 受控 su 只读查询（su - dmdba -c 'disql...' <<< 'SELECT...'）→ 放行，
        # 需在 /dev/null 与 heredoc 元字符检查前拦截
        if cls._is_controlled_su_readonly(command, db_type):
            return True
        # 命令替换 $()/反引号：内层必须是只读命令，否则视为注入
        if '$(' in command or '`' in command:
            cleaned_sub = cls._sanitize_safe_substitutions(command, db_type)
            if cleaned_sub is None:
                return False
            command = cleaned_sub
        # 去除 /dev/null 重定向（2>/dev/null、>/dev/null、1>/dev/null，允许空格）
        cleaned = re.sub(r'\d*\s*>\s*/dev/null', '', command)
        if not cleaned.strip():
            return False
        # 仍有其他重定向（> 到非 /dev/null，或 < 输入重定向）→ 非诊断链
        if re.search(r'[<>]', cleaned):
            return False
        # 按分隔符分段（; || && |，引号感知），逐段必须是只读命令
        parts = cls._split_shell(cleaned)
        for seg in parts:
            seg = seg.strip()
            if not seg:
                return False
            toks = seg.split()
            if not toks:
                return False
            seg_cls, _ = cls._evaluate_segment(toks, db_type or '',
                                               OperationLevel.READONLY)
            if seg_cls != 'safe':
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
            if cls._is_hard_rejected(arg):
                return False, f"检测到危险参数: {arg}"
            if cls._is_path_like(arg) and '..' in arg:
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
