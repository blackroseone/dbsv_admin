import sqlite3
import os

DB_PATH = 'data/db_tool.db'
conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

# 获取所有表名
cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
tables = cursor.fetchall()

print('=== 数据库中的所有表 ===')
for table in tables:
    print(f'  - {table[0]}')
print()

# 查询每个表的数据
for table_name in [t[0] for t in tables]:
    print(f'=== 表: {table_name} ===')
    try:
        cursor.execute(f'SELECT * FROM {table_name}')
        rows = cursor.fetchall()
        if rows:
            # 获取列名
            columns = [description[0] for description in cursor.description]
            print(f'列名: {columns}')
            print(f'数据行数: {len(rows)}')
            for i, row in enumerate(rows):
                if i >= 5:  # 只显示前5行
                    print(f'  ... 还有 {len(rows) - 5} 行')
                    break
                print(f'  行 {i+1}: {dict(row)}')
        else:
            print('  (空表)')
    except Exception as e:
        print(f'  查询失败: {e}')
    print()

conn.close()
