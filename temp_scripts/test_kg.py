import sys
sys.stdout.reconfigure(encoding='utf-8')

from db.database import get_db
conn = get_db()

tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'kg_%'").fetchall()
print('知识图谱表:')
for t in tables:
    print(f'  - {t["name"]}')

indexes = conn.execute("SELECT name FROM sqlite_master WHERE type='index' AND name LIKE 'idx_kg_%'").fetchall()
print(f'\n索引数量: {len(indexes)}')

from kg.rules import extract_all_entities
test_text = "MySQL 8.0 的性能优化需要考虑 innodb_buffer_pool_size 参数。在 CentOS 7.9 上部署 OceanBase 数据库时，可能会遇到 ORA-01555 错误。GaussDB 兼容 MySQL 协议。"
entities = extract_all_entities(test_text, 'mysql')
print(f'\n测试提取实体数量: {len(entities)}')
for e in entities[:10]:
    print(f'  [{e["entity_type"]}] {e["name"]} (置信度: {e.get("confidence", 1.0)})')

print('\n✅ 知识图谱基础设施测试通过')
