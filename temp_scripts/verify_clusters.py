import sqlite3

conn = sqlite3.connect('data/db_tool.db')
conn.row_factory = sqlite3.Row

cursor = conn.execute('SELECT id, name, resource_pool_id FROM clusters')
clusters = cursor.fetchall()

print(f"剩余 {len(clusters)} 个集群:\n")
for cluster in clusters:
    # 统计每个集群关联的服务器数量
    cursor = conn.execute('SELECT COUNT(*) FROM servers WHERE cluster_id = ?', (cluster['id'],))
    server_count = cursor.fetchone()[0]
    print(f"ID: {cluster['id']}")
    print(f"名称: {cluster['name']}")
    print(f"服务器数量: {server_count}")
    print("-" * 50)

conn.close()
