import sys
sys.stdout.reconfigure(encoding='utf-8')

import os
sys.path.insert(0, 'D:\\claude\\dbsv_admin')

from db.database import get_db
conn = get_db()

# 查看实际去重后的实体数量
print('=== 去重后实体统计 ===')
unique = conn.execute('SELECT COUNT(DISTINCT normalized_name || entity_type) FROM kg_entities').fetchone()[0]
print(f'唯一实体组合: {unique}')

# 查看关系类型分布
print('\n=== 关系类型分布 ===')
rels = conn.execute('SELECT relation_type, COUNT(*) as count FROM kg_relationships GROUP BY relation_type ORDER BY count DESC').fetchall()
for r in rels:
    print(f"{r['relation_type']}: {r['count']}")

# 查看前10个实体
print('\n=== 实体示例 ===')
entities = conn.execute("SELECT entity_type, name, normalized_name FROM kg_entities ORDER BY id LIMIT 10").fetchall()
for e in entities:
    print(f"[{e['entity_type']}] {e['name']} ({e['normalized_name']})")

# 查看参数实体示例
print('\n=== 参数实体示例 ===')
params = conn.execute("SELECT name, normalized_name FROM kg_entities WHERE entity_type='parameter' ORDER BY id LIMIT 10").fetchall()
for p in params:
    print(f"  - {p['name']}")
