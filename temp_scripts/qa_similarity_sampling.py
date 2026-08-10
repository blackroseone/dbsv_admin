# -*- coding: utf-8 -*-
"""采样真实用户问题，统计向量检索相似度分布（分块 500 后重调阈值用）

用法: python temp_scripts/qa_similarity_sampling.py
输出: 每个问题的 top-10 相似度；命中集分布（min/max/median/P20/P30）；
     在 0.50/0.55/0.60 阈值下有多少问题有命中。
"""
import sys
import os
import io
import statistics

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
os.environ['TRANSFORMERS_OFFLINE'] = '1'

import sqlite3
from rag.embedder import Embedder
from db.database import get_db_types

DB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', 'db_tool.db')
MAX_QUERIES = 30

conn = sqlite3.connect(DB)
# 取真实用户问题（去重，排除过短）
rows = conn.execute(
    """SELECT qm.content, qc.db_type FROM qa_messages qm
       JOIN qa_conversations qc ON qm.conversation_id = qc.id
       WHERE qm.role='user' AND length(qm.content) > 8
       ORDER BY qm.id DESC LIMIT 200"""
).fetchall()
conn.close()

# 去重并截取
seen = set()
queries = []
for content, db_type in rows:
    q = content.strip().replace('\n', ' ')[:200]
    if q and q not in seen:
        seen.add(q)
        queries.append((q, db_type or ''))
    if len(queries) >= MAX_QUERIES:
        break

print(f'采样问题数: {len(queries)}')

embedder = Embedder()
db_types = {t['id']: t['name'] for t in get_db_types()}

all_top10 = []
threshold_hits = {0.50: 0, 0.55: 0, 0.60: 0}
for q, db_type in queries:
    target = db_type if db_type in db_types else None
    results = embedder.similarity_search(q, db_type=target, top_k=10)
    sims = [round(r.get('similarity', 0), 3) for r in results]
    all_top10.append(sims)
    for th in threshold_hits:
        if any(s >= th for s in sims):
            threshold_hits[th] += 1

# 命中集 = 所有问题的 top-1 相似度（检索质量核心指标）
top1 = [s[0] if s else 0 for s in all_top10]
# 所有 top-10 相似度合并分布
flat = [s for sims in all_top10 for s in sims]

def percentile(data, p):
    if not data:
        return 0
    data = sorted(data)
    k = (len(data) - 1) * p / 100
    f = int(k)
    c = f + 1 if f + 1 < len(data) else f
    return data[f] + (data[c] - data[f]) * (k - f)

print('=' * 60)
print(f'top-1 相似度分布（每问题最高命中）:')
print(f'  min={min(top1):.3f}  P20={percentile(top1,20):.3f}  P30={percentile(top1,30):.3f}  '
      f'median={statistics.median(top1):.3f}  max={max(top1):.3f}')
print(f'  有命中(top1>0)的问题数: {sum(1 for s in top1 if s>0)}/{len(top1)}')
print(f'top-10 合并相似度分布:')
print(f'  min={min(flat):.3f}  P20={percentile(flat,20):.3f}  P30={percentile(flat,30):.3f}  '
      f'median={statistics.median(flat):.3f}  max={max(flat):.3f}')
print(f'各阈值下有命中(top-10内)的问题占比:')
for th, cnt in threshold_hits.items():
    print(f'  >= {th}: {cnt}/{len(queries)} ({100*cnt/max(len(queries),1):.0f}%)')
print('=' * 60)
print('提示: 若命中率在 0.55 偏低(漏检多)，可下调 MIN_SIMILARITY_THRESHOLD；')
print('若大量 0.50~0.60 命中但回答被幻觉污染，可上调。')
