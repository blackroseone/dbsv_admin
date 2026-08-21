# -*- coding: utf-8 -*-
"""临时验证：句子边界优先分块效果（不依赖嵌入模型、只读不写库）

用法: python temp_scripts/test_chunk_sent_boundary.py
预期: 连续散文类文本的块末句末比例应接近 100%；表格/代码类允许非句末。
"""
import sys
import os

sys.stdout.reconfigure(encoding='utf-8')
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

from rag.embedder import chunk_text

SENT_END = set('。！？；!?;.\n')

SAMPLES = {
    '中文连续段落(无换行)': (
        '数据库慢查询是运维中的常见问题。当一条SQL执行时间超过阈值时会被记录到慢查询日志。'
        '常见原因包括缺失索引、统计信息过期、数据量增长导致的执行计划劣化。'
        '定位慢查询的第一步是开启慢查询日志并设置合理的阈值。'
        '第二步使用EXPLAIN分析执行计划，重点观察全表扫描和临时表。'
        '第三步结合索引建议工具评估优化方案。优化后需要持续观察确认效果。'
    ) * 3,
    '英文连续段落': (
        'Slow queries are a common issue in database operations. '
        'When a SQL statement exceeds the time threshold it is logged. '
        'Common causes include missing indexes and stale statistics. '
        'The first step is enabling the slow query log with a proper threshold. '
        'Then use EXPLAIN to analyze the execution plan carefully. '
        'Finally evaluate the optimization with indexing tools. '
    ) * 3,
    '表格(无标点行)': '\n'.join(
        f'col_a_{i} | col_b_{i} | col_c_{i} | value_{i} | {i * 37}' for i in range(60)),
    '中英混合': (
        'Oracle RAC环境下需要注意节点间负载均衡。Load balancing is critical. '
        '服务端TAF配置决定了故障切换行为。Client-side TAF is deprecated. '
        '建议使用SCAN地址连接。Always prefer SCAN over VIP addresses. '
    ) * 4,
}

print('=' * 64)
for name, text in SAMPLES.items():
    chunks = chunk_text(text)
    n = len(chunks)
    sent_end_cnt = sum(1 for c in chunks if c.strip() and c.rstrip()[-1] in SENT_END)
    over = sum(1 for c in chunks if len(c) > 550)   # 略放宽观察超限
    print(f'[{name}] {n} 块 | 块末句末 {sent_end_cnt}/{n} ({100*sent_end_cnt/max(n,1):.0f}%) | 超550字符 {over} 块')
    for i, c in enumerate(chunks[:3]):
        tail = c.rstrip()[-1] if c.strip() else ''
        print(f'   块{i}: len={len(c)} 末字符={tail!r}')
print('=' * 64)
print('预期: 前两类块末句末≈100%；表格类允许非句末（段落兜底生效）；无块超 chunk_size。')
