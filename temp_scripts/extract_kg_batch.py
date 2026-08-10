# -*- coding: utf-8 -*-
"""
批量从现有知识库文件中提取知识图谱实体
"""
import sys
sys.stdout.reconfigure(encoding='utf-8')

import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db.database import get_db
from db.kg_database import save_entity, save_relationship, link_chunk_entity
from kg.rules import extract_all_entities, infer_relationships

def get_all_chunks():
    """获取所有 chunk"""
    conn = get_db()
    rows = conn.execute(
        """SELECT e.id, e.file_id, e.chunk_index, e.chunk_text, k.db_type, k.filename
        FROM embeddings e
        JOIN knowledge_files k ON e.file_id = k.id
        ORDER BY k.db_type, k.filename, e.chunk_index"""
    ).fetchall()
    return [dict(r) for r in rows]


def extract_kg_from_chunks(batch_size=100):
    """从所有 chunk 中提取知识图谱实体"""
    chunks = get_all_chunks()
    total = len(chunks)
    print(f"[KG] 共有 {total} 个 chunk 待处理")

    entity_count = 0
    relation_count = 0
    chunk_link_count = 0

    for i, chunk in enumerate(chunks):
        chunk_id = chunk['id']
        chunk_text = chunk['chunk_text']
        db_type = chunk['db_type']
        file_id = chunk['file_id']

        # 提取实体
        entities = extract_all_entities(chunk_text, db_type)

        if entities:
            # 保存实体并建立 chunk 关联
            entity_ids = {}
            for entity in entities:
                try:
                    entity_id = save_entity(
                        entity_type=entity['entity_type'],
                        name=entity['name'],
                        normalized_name=entity.get('normalized_name', entity['name'].lower().strip()),
                        aliases=entity.get('aliases', []),
                        description=entity.get('description', ''),
                        properties=entity.get('properties', {}),
                        source_file_id=file_id,
                        source_chunk_id=chunk_id,
                        confidence=entity.get('confidence', 1.0),
                        extract_method=entity.get('extract_method', 'rule')
                    )
                    entity_ids[(entity['entity_type'], entity['normalized_name'])] = entity_id
                    entity_count += 1

                    # 建立 chunk-实体关联
                    mention_count = len(entity.get('positions', []))
                    link_chunk_entity(chunk_id, entity_id, mention_count or 1)
                    chunk_link_count += 1
                except Exception as e:
                    print(f"[KG] 保存实体失败 {entity['name']}: {e}")

            # 关系推理
            if len(entities) > 1:
                relationships = infer_relationships(entities, chunk_text)
                for rel in relationships:
                    try:
                        from_key = (rel['from_entity']['entity_type'], rel['from_entity']['normalized_name'])
                        to_key = (rel['to_entity']['entity_type'], rel['to_entity']['normalized_name'])

                        from_id = entity_ids.get(from_key)
                        to_id = entity_ids.get(to_key)

                        if from_id and to_id:
                            save_relationship(
                                from_entity_id=from_id,
                                to_entity_id=to_id,
                                relation_type=rel['relation_type'],
                                confidence=rel.get('confidence', 0.8),
                                source_chunk_id=chunk_id,
                                source_file_id=file_id,
                                extract_method=rel.get('extract_method', 'rule')
                            )
                            relation_count += 1
                    except Exception as e:
                        print(f"[KG] 保存关系失败: {e}")

        if (i + 1) % batch_size == 0:
            print(f"[KG] 已处理 {i + 1}/{total} chunks, 实体: {entity_count}, 关系: {relation_count}, 关联: {chunk_link_count}")

    print(f"\n[KG] 提取完成!")
    print(f"  - 处理 chunks: {total}")
    print(f"  - 提取实体: {entity_count}")
    print(f"  - 推理关系: {relation_count}")
    print(f"  - chunk 关联: {chunk_link_count}")

    return {
        'total_chunks': total,
        'entity_count': entity_count,
        'relation_count': relation_count,
        'chunk_link_count': chunk_link_count
    }


if __name__ == '__main__':
    print("=" * 60)
    print("知识图谱批量提取")
    print("=" * 60)

    # 检查当前实体数量
    conn = get_db()
    existing = conn.execute("SELECT COUNT(*) as count FROM kg_entities").fetchone()['count']
    print(f"[KG] 当前已有实体: {existing}")

    if existing > 0:
        print("[KG] 已有实体数据，跳过提取（如需重新提取，请先清空 kg_entities 表）")
    else:
        result = extract_kg_from_chunks()
        print(f"\n[KG] 提取结果: {result}")

    print("\n✅ 知识图谱数据提取完成")
