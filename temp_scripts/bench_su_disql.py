# -*- coding: utf-8 -*-
"""受控 su + disql 精确用例（一次性，不入库）"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

from agent.harness import Harness

# 用户原始命令（JSON 解析后的实际字符串）
cmd2 = "su - dmdba -c '/dm/dmdbms/bin/disql SYSDBA/SYSDBA@localhost:5236' <<< 'SELECT COUNT(*) AS ACTIVE_SESSIONS FROM V$SESSIONS WHERE STATE=''ACTIVE'';' 2>/dev/null"
cmd3 = 'su - dmdba -c "disql SYSDBA/SYSDBA@localhost:5238 -e \'SELECT COUNT(*) FROM V\\$SESSIONS WHERE STATE=\\"\'\\"\'ACTIVE\'\\"\'\\"\'"'

print('cmd2 静态:', Harness.classify_command(cmd2, 'dm'))

# cmd3：模拟 LLM 审查钩子的两路
Harness.command_judge_fn = lambda c: {'allow': True, 'risk': 'low', 'reason': '只读 SELECT'}
print('cmd3 钩子放行:', Harness.classify_command(cmd3, 'dm'))
Harness.command_judge_fn = lambda c: {'allow': False, 'risk': 'high', 'reason': '危险'}
print('cmd3 钩子拒绝:', Harness.classify_command(cmd3, 'dm'))
Harness.command_judge_fn = None
print('cmd3 无钩子:', Harness.classify_command(cmd3, 'dm'))
