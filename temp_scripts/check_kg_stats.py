import sys
sys.stdout.reconfigure(encoding='utf-8')

import os
sys.path.insert(0, 'D:\\claude\\dbsv_admin')

from db.database import get_db
conn = get_db()

# 统计实体类型分布
print('=== 知识图谱统计 ===')
types = conn.execute('SELECT entity_type, COUNT(*) as count FROM kg_entities GROUP BY entity_type ORDER BY count DESC').fetchall()
for t in types:
    print(f"{t['entity_type']}: {t['count']}")

print(f"\n总计实体: {conn.execute('SELECT COUNT(*) FROM kg_entities').fetchone()[0]}")
print(f"总计关系: {conn.execute('SELECT COUNT(*) FROM kg_relationships').fetchone()[0]}")
print(f"总计关联: {conn.execute('SELECT COUNT(*) FROM kg_chunk_entities').fetchone()[0]}")
