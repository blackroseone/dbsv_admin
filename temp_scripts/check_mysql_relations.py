import sys
sys.stdout.reconfigure(encoding='utf-8')

import os
sys.path.insert(0, 'D:\\claude\\dbsv_admin')

from db.database import get_db
conn = get_db()

# 查找 MySQL 实体
mysql = conn.execute(
    "SELECT id, name, entity_type FROM kg_entities WHERE normalized_name = 'mysql' AND entity_type = 'database_product'"
).fetchone()

if mysql:
    print(f"MySQL 实体 ID: {mysql['id']}")

    # 统计关系数量
    outgoing = conn.execute(
        "SELECT COUNT(*) as count FROM kg_relationships WHERE from_entity_id = ?",
        (mysql['id'],)
    ).fetchone()['count']

    incoming = conn.execute(
        "SELECT COUNT(*) as count FROM kg_relationships WHERE to_entity_id = ?",
        (mysql['id'],)
    ).fetchone()['count']

    print(f"出向关系: {outgoing}")
    print(f"入向关系: {incoming}")
    print(f"总关系: {outgoing + incoming}")

    # 查看关系类型分布
    print("\n关系类型分布:")
    rel_types = conn.execute(
        """SELECT relation_type, COUNT(*) as count
        FROM kg_relationships
        WHERE from_entity_id = ? OR to_entity_id = ?
        GROUP BY relation_type
        ORDER BY count DESC""",
        (mysql['id'], mysql['id'])
    ).fetchall()
    for r in rel_types:
        print(f"  {r['relation_type']}: {r['count']}")
else:
    print("未找到 MySQL 实体")
