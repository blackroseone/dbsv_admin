import sqlite3
import json

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

# 删除这些集群
print("\n正在删除这些集群...")
for cluster in orphan_clusters:
    conn.execute('DELETE FROM clusters WHERE id = ?', (cluster['id'],))
    print(f"已删除: {cluster['name']}")

conn.commit()
print(f"\n共删除 {len(orphan_clusters)} 个集群")

# 验证删除后的集群数量
cursor = conn.execute('SELECT COUNT(*) FROM clusters')
count = cursor.fetchone()[0]
print(f"当前clusters表剩余 {count} 条记录")

conn.close()
