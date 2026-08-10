import sqlite3
import json

conn = sqlite3.connect('data/db_tool.db')
conn.row_factory = sqlite3.Row

cursor = conn.execute('SELECT * FROM clusters')
rows = cursor.fetchall()

# 转换为字典列表
clusters = []
for row in rows:
    clusters.append({
        'id': row['id'],
        'resource_pool_id': row['resource_pool_id'],
        'name': row['name'],
        'description': row['description']
    })

conn.close()

# 写入JSON文件
with open('clusters_data.json', 'w', encoding='utf-8') as f:
    json.dump(clusters, f, ensure_ascii=False, indent=2)

print(f"clusters 表共有 {len(clusters)} 条记录,已导出到 clusters_data.json")
