# -*- coding: utf-8 -*-
"""命令追踪（一次性，不入库）"""
import sys, os, re
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
from agent.harness import Harness, OperationLevel

cmd = "su - dmdba -c '/dm/dmdbms/bin/disql SYSDBA/SYSDBA@localhost:5236' -c \"SELECT INSTANCE_NAME, STATUS$, MODE$, OPEN_TIME FROM V$INSTANCE;\""
print('cmd repr  :', repr(cmd))
print('chain     :', Harness._is_diagnostic_chain(cmd, 'dm'))
print('controlled:', Harness._is_controlled_su_readonly(cmd, 'dm'))
print('classify  :', Harness.classify_command(cmd, 'dm'))
print('amp guard :', bool(re.search(r'(?<![&|])&(?![&|])', cmd)))
print('has ${    :', '${' in cmd)
print('strip_quoted:', repr(Harness._strip_quoted(cmd)))
