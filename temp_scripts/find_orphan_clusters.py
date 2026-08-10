import sqlite3

conn = sqlite3.connect('data/db_tool.db')
conn.row_factory = sqlite3.Row

# 查找没有关联服务器的集群
cursor = conn.execute('''
    SELECT c.id, c.name, c.resource_pool_id
    FROM clusters c
    LEFT JOIN servers s ON c.id = s.cluster_id
    WHERE s.id IS NULL
''')

orphan_clusters = cursor.fetchall()

print(f"找到 {len(orphan_clusters)} 个没有关联服务器的集群:\n")

for cluster in orphan_clusters:
    print(f"ID: {cluster['id']}")
    print(f"名称: {cluster['name']}")
    print(f"resource_pool_id: {cluster['resource_pool_id']}")
    print("-" * 50)

conn.close()
