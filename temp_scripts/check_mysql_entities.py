import sys
sys.stdout.reconfigure(encoding='utf-8')

import os
sys.path.insert(0, 'D:\\claude\\dbsv_admin')

from db.database import get_db
conn = get_db()

# 搜索包含 MySQL 的实体
print('=== 搜索包含 MySQL 的实体 ===')
rows = conn.execute(
    "SELECT entity_type, name, normalized_name FROM kg_entities WHERE name LIKE '%MySQL%' ORDER BY entity_type, name LIMIT 20"
).fetchall()
for r in rows:
    print(f"[{r['entity_type']}] {r['name']} ({r['normalized_name']})")

print('\n=== 搜索 database_product 类型的 MySQL ===')
rows = conn.execute(
    "SELECT entity_type, name, normalized_name FROM kg_entities WHERE entity_type='database_product' AND name LIKE '%MySQL%'"
).fetchall()
for r in rows:
    print(f"[{r['entity_type']}] {r['name']} ({r['normalized_name']})")
