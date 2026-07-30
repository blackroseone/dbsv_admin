# -*- coding: utf-8 -*-
"""
知识图谱数据库 CRUD 操作
"""
import json
import sqlite3
from db.database import get_db, transaction


# ==================== 实体 CRUD ====================

def save_entity(entity_type, name, normalized_name=None, aliases=None, description=None,
                properties=None, source_file_id=None, source_chunk_id=None,
                confidence=1.0, extract_method='rule'):
    """保存或更新实体，返回实体 ID"""
    if normalized_name is None:
        normalized_name = name.lower().strip()
    aliases_str = json.dumps(aliases or [], ensure_ascii=False)
    props_str = json.dumps(properties or {}, ensure_ascii=False)

    with transaction() as tx:
        # 检查是否已存在
        existing = tx.fetchone(
            "SELECT id FROM kg_entities WHERE normalized_name=? AND entity_type=?",
            (normalized_name, entity_type)
        )
        if existing:
            entity_id = existing['id']
            # 更新实体（合并别名和属性）
            old = tx.fetchone(
                "SELECT aliases, properties FROM kg_entities WHERE id=?",
                (entity_id,)
            )
            old_aliases = json.loads(old['aliases']) if old['aliases'] else []
            old_props = json.loads(old['properties']) if old['properties'] else {}

            # 合并别名
            new_aliases = list(set(old_aliases + (aliases or [])))
            # 合并属性
            new_props = {**old_props, **(properties or {})}

            tx.execute(
                """UPDATE kg_entities SET
                    name=?, aliases=?, description=COALESCE(?, description),
                    properties=?, confidence=MAX(confidence, ?),
                    source_file_id=COALESCE(source_file_id, ?),
                    source_chunk_id=COALESCE(source_chunk_id, ?),
                    updated_at=CURRENT_TIMESTAMP
                WHERE id=?""",
                (name, json.dumps(new_aliases, ensure_ascii=False), description,
                 json.dumps(new_props, ensure_ascii=False), confidence,
                 source_file_id, source_chunk_id, entity_id)
            )
        else:
            cursor = tx.execute(
                """INSERT INTO kg_entities
                    (entity_type, name, normalized_name, aliases, description,
                     properties, source_file_id, source_chunk_id, confidence, extract_method)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (entity_type, name, normalized_name, aliases_str, description,
                 props_str, source_file_id, source_chunk_id, confidence, extract_method)
            )
            entity_id = cursor.lastrowid

    return entity_id


def get_entity_by_id(entity_id):
    """通过 ID 获取实体"""
    conn = get_db()
    row = conn.execute(
        "SELECT * FROM kg_entities WHERE id=?", (entity_id,)
    ).fetchone()
    if not row:
        return None
    entity = dict(row)
    entity['aliases'] = json.loads(entity.get('aliases', '[]'))
    entity['properties'] = json.loads(entity.get('properties', '{}'))
    return entity


def get_entity_by_name(name, entity_type=None):
    """通过名称获取实体（支持规范化匹配）"""
    normalized = name.lower().strip()
    conn = get_db()
    if entity_type:
        row = conn.execute(
            "SELECT * FROM kg_entities WHERE normalized_name=? AND entity_type=?",
            (normalized, entity_type)
        ).fetchone()
    else:
        row = conn.execute(
            "SELECT * FROM kg_entities WHERE normalized_name=?",
            (normalized,)
        ).fetchone()

    if not row:
        # 尝试别名匹配
        if entity_type:
            rows = conn.execute(
                "SELECT * FROM kg_entities WHERE entity_type=?",
                (entity_type,)
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM kg_entities").fetchall()

        for r in rows:
            aliases = json.loads(r['aliases']) if r['aliases'] else []
            if name in aliases or normalized in [a.lower() for a in aliases]:
                entity = dict(r)
                entity['aliases'] = aliases
                entity['properties'] = json.loads(entity.get('properties', '{}'))
                return entity
        return None

    entity = dict(row)
    entity['aliases'] = json.loads(entity.get('aliases', '[]'))
    entity['properties'] = json.loads(entity.get('properties', '{}'))
    return entity


def search_entities(keyword, entity_type=None, limit=20):
    """模糊搜索实体

    搜索策略：
    1. 优先精确匹配（name = keyword）
    2. 其次前缀匹配（name LIKE 'keyword%'）
    3. 最后模糊匹配（name LIKE '%keyword%'）
    """
    conn = get_db()
    normalized = keyword.lower().strip()

    # 构建查询：优先精确匹配，然后前缀匹配，最后模糊匹配
    if entity_type:
        # 先精确匹配
        exact_rows = conn.execute(
            """SELECT * FROM kg_entities
            WHERE entity_type=? AND (name = ? OR normalized_name = ?)
            ORDER BY confidence DESC, name""",
            (entity_type, keyword, normalized)
        ).fetchall()

        # 再前缀匹配
        prefix_pattern = f"{keyword}%"
        prefix_rows = conn.execute(
            """SELECT * FROM kg_entities
            WHERE entity_type=? AND (name LIKE ? OR normalized_name LIKE ?)
            AND name != ? AND normalized_name != ?
            ORDER BY confidence DESC, name
            LIMIT ?""",
            (entity_type, prefix_pattern, prefix_pattern, keyword, normalized, limit)
        ).fetchall()

        # 最后模糊匹配
        fuzzy_pattern = f"%{keyword}%"
        fuzzy_rows = conn.execute(
            """SELECT * FROM kg_entities
            WHERE entity_type=? AND (name LIKE ? OR normalized_name LIKE ? OR description LIKE ?)
            AND name != ? AND normalized_name != ?
            AND name NOT LIKE ? AND normalized_name NOT LIKE ?
            ORDER BY confidence DESC, name
            LIMIT ?""",
            (entity_type, fuzzy_pattern, fuzzy_pattern, fuzzy_pattern,
             keyword, normalized, prefix_pattern, prefix_pattern, limit)
        ).fetchall()
    else:
        # 先精确匹配
        exact_rows = conn.execute(
            """SELECT * FROM kg_entities
            WHERE name = ? OR normalized_name = ?
            ORDER BY confidence DESC, name""",
            (keyword, normalized)
        ).fetchall()

        # 再前缀匹配
        prefix_pattern = f"{keyword}%"
        prefix_rows = conn.execute(
            """SELECT * FROM kg_entities
            WHERE (name LIKE ? OR normalized_name LIKE ?)
            AND name != ? AND normalized_name != ?
            ORDER BY confidence DESC, name
            LIMIT ?""",
            (prefix_pattern, prefix_pattern, keyword, normalized, limit)
        ).fetchall()

        # 最后模糊匹配
        fuzzy_pattern = f"%{keyword}%"
        fuzzy_rows = conn.execute(
            """SELECT * FROM kg_entities
            WHERE (name LIKE ? OR normalized_name LIKE ? OR description LIKE ?)
            AND name != ? AND normalized_name != ?
            AND name NOT LIKE ? AND normalized_name NOT LIKE ?
            ORDER BY confidence DESC, name
            LIMIT ?""",
            (fuzzy_pattern, fuzzy_pattern, fuzzy_pattern,
             keyword, normalized, prefix_pattern, prefix_pattern, limit)
        ).fetchall()

    # 合并结果，去重
    seen = set()
    results = []
    for row in exact_rows + prefix_rows + fuzzy_rows:
        entity = dict(row)
        if entity['id'] not in seen:
            seen.add(entity['id'])
            entity['aliases'] = json.loads(entity.get('aliases', '[]'))
            entity['properties'] = json.loads(entity.get('properties', '{}'))
            results.append(entity)
            if len(results) >= limit:
                break

    return results


def get_entities_by_type(entity_type, limit=100):
    """获取指定类型的所有实体"""
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM kg_entities WHERE entity_type=? ORDER BY name LIMIT ?",
        (entity_type, limit)
    ).fetchall()

    results = []
    for row in rows:
        entity = dict(row)
        entity['aliases'] = json.loads(entity.get('aliases', '[]'))
        entity['properties'] = json.loads(entity.get('properties', '{}'))
        results.append(entity)
    return results


def get_entity_types():
    """获取所有实体类型及其数量"""
    conn = get_db()
    rows = conn.execute(
        "SELECT entity_type, COUNT(*) as count FROM kg_entities GROUP BY entity_type ORDER BY count DESC"
    ).fetchall()
    return [dict(r) for r in rows]


def delete_entity(entity_id):
    """删除实体（级联删除关系和 chunk 关联）"""
    conn = get_db()
    conn.execute("DELETE FROM kg_entities WHERE id=?", (entity_id,))
    conn.commit()


def get_entity_stats():
    """获取知识图谱统计信息"""
    conn = get_db()
    entity_count = conn.execute(
        "SELECT COUNT(*) as count FROM kg_entities"
    ).fetchone()['count']

    relation_count = conn.execute(
        "SELECT COUNT(*) as count FROM kg_relationships"
    ).fetchone()['count']

    chunk_link_count = conn.execute(
        "SELECT COUNT(*) as count FROM kg_chunk_entities"
    ).fetchone()['count']

    type_stats = conn.execute(
        "SELECT entity_type, COUNT(*) as count FROM kg_entities GROUP BY entity_type ORDER BY count DESC"
    ).fetchall()

    relation_type_stats = conn.execute(
        "SELECT relation_type, COUNT(*) as count FROM kg_relationships GROUP BY relation_type ORDER BY count DESC"
    ).fetchall()

    return {
        'entity_count': entity_count,
        'relation_count': relation_count,
        'chunk_link_count': chunk_link_count,
        'entity_types': [dict(r) for r in type_stats],
        'relation_types': [dict(r) for r in relation_type_stats]
    }


# ==================== 关系 CRUD ====================

def save_relationship(from_entity_id, to_entity_id, relation_type, confidence=1.0,
                      properties=None, source_chunk_id=None, source_file_id=None,
                      extract_method='rule'):
    """保存或更新关系，返回关系 ID"""
    props_str = json.dumps(properties or {}, ensure_ascii=False)

    with transaction() as tx:
        # 检查是否已存在
        existing = tx.fetchone(
            """SELECT id FROM kg_relationships
            WHERE from_entity_id=? AND to_entity_id=? AND relation_type=?""",
            (from_entity_id, to_entity_id, relation_type)
        )
        if existing:
            rel_id = existing['id']
            tx.execute(
                """UPDATE kg_relationships SET
                    confidence=MAX(confidence, ?),
                    properties=?,
                    source_chunk_id=COALESCE(source_chunk_id, ?),
                    source_file_id=COALESCE(source_file_id, ?)
                WHERE id=?""",
                (confidence, props_str, source_chunk_id, source_file_id, rel_id)
            )
        else:
            cursor = tx.execute(
                """INSERT INTO kg_relationships
                    (from_entity_id, to_entity_id, relation_type, confidence,
                     properties, source_chunk_id, source_file_id, extract_method)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (from_entity_id, to_entity_id, relation_type, confidence,
                 props_str, source_chunk_id, source_file_id, extract_method)
            )
            rel_id = cursor.lastrowid

    return rel_id


def get_relationships_by_entity(entity_id, direction='both'):
    """获取实体的关系
    direction: 'outgoing' | 'incoming' | 'both'
    """
    conn = get_db()
    relationships = []

    if direction in ('outgoing', 'both'):
        rows = conn.execute(
            """SELECT r.*, e.name as to_name, e.entity_type as to_type
            FROM kg_relationships r
            JOIN kg_entities e ON r.to_entity_id = e.id
            WHERE r.from_entity_id=?""",
            (entity_id,)
        ).fetchall()
        for row in rows:
            rel = dict(row)
            rel['direction'] = 'outgoing'
            rel['properties'] = json.loads(rel.get('properties', '{}'))
            relationships.append(rel)

    if direction in ('incoming', 'both'):
        rows = conn.execute(
            """SELECT r.*, e.name as from_name, e.entity_type as from_type
            FROM kg_relationships r
            JOIN kg_entities e ON r.from_entity_id = e.id
            WHERE r.to_entity_id=?""",
            (entity_id,)
        ).fetchall()
        for row in rows:
            rel = dict(row)
            rel['direction'] = 'incoming'
            rel['properties'] = json.loads(rel.get('properties', '{}'))
            relationships.append(rel)

    return relationships


def get_relationships_between(from_entity_id, to_entity_id):
    """获取两个实体之间的所有关系"""
    conn = get_db()
    rows = conn.execute(
        """SELECT * FROM kg_relationships
        WHERE (from_entity_id=? AND to_entity_id=?) OR (from_entity_id=? AND to_entity_id=?)
        ORDER BY confidence DESC""",
        (from_entity_id, to_entity_id, to_entity_id, from_entity_id)
    ).fetchall()

    results = []
    for row in rows:
        rel = dict(row)
        rel['properties'] = json.loads(rel.get('properties', '{}'))
        results.append(rel)
    return results


def delete_relationship(rel_id):
    """删除关系"""
    conn = get_db()
    conn.execute("DELETE FROM kg_relationships WHERE id=?", (rel_id,))
    conn.commit()


# ==================== Chunk-实体关联 CRUD ====================

def link_chunk_entity(chunk_id, entity_id, mention_count=1):
    """关联 chunk 和实体"""
    conn = get_db()
    try:
        conn.execute(
            """INSERT INTO kg_chunk_entities (chunk_id, entity_id, mention_count)
            VALUES (?, ?, ?)
            ON CONFLICT(chunk_id, entity_id) DO UPDATE SET
            mention_count = mention_count + excluded.mention_count""",
            (chunk_id, entity_id, mention_count)
        )
        conn.commit()
    except sqlite3.IntegrityError:
        pass  # 外键约束失败时静默处理


def get_entities_by_chunk(chunk_id):
    """获取 chunk 关联的所有实体"""
    conn = get_db()
    rows = conn.execute(
        """SELECT e.*, ce.mention_count
        FROM kg_entities e
        JOIN kg_chunk_entities ce ON e.id = ce.entity_id
        WHERE ce.chunk_id=?""",
        (chunk_id,)
    ).fetchall()

    results = []
    for row in rows:
        entity = dict(row)
        entity['aliases'] = json.loads(entity.get('aliases', '[]'))
        entity['properties'] = json.loads(entity.get('properties', '{}'))
        results.append(entity)
    return results


def get_chunks_by_entity(entity_id):
    """获取实体关联的所有 chunk"""
    conn = get_db()
    rows = conn.execute(
        """SELECT e.id, e.file_id, e.chunk_index, e.chunk_text,
               k.filename, k.db_type, ce.mention_count
        FROM embeddings e
        JOIN knowledge_files k ON e.file_id = k.id
        JOIN kg_chunk_entities ce ON e.id = ce.chunk_id
        WHERE ce.entity_id=?""",
        (entity_id,)
    ).fetchall()
    return [dict(r) for r in rows]


def unlink_chunk_entity(chunk_id, entity_id):
    """解除 chunk 和实体的关联"""
    conn = get_db()
    conn.execute(
        "DELETE FROM kg_chunk_entities WHERE chunk_id=? AND entity_id=?",
        (chunk_id, entity_id)
    )
    conn.commit()


# ==================== 批量操作 ====================

def save_entities_batch(entities):
    """批量保存实体
    entities: [{entity_type, name, normalized_name, aliases, description,
                properties, source_file_id, source_chunk_id, confidence, extract_method}, ...]
    返回 [(entity_id, name), ...]
    """
    results = []
    for entity in entities:
        try:
            eid = save_entity(**entity)
            results.append((eid, entity['name']))
        except Exception as e:
            print(f"[KG] 保存实体失败: {entity.get('name', 'unknown')} - {e}")
    return results


def save_relationships_batch(relationships):
    """批量保存关系
    relationships: [{from_entity_id, to_entity_id, relation_type, confidence,
                     properties, source_chunk_id, source_file_id, extract_method}, ...]
    """
    results = []
    for rel in relationships:
        try:
            rid = save_relationship(**rel)
            results.append(rid)
        except Exception as e:
            print(f"[KG] 保存关系失败: {rel} - {e}")
    return results


def link_chunks_entities_batch(links):
    """批量关联 chunk 和实体
    links: [(chunk_id, entity_id, mention_count), ...]
    """
    conn = get_db()
    conn.executemany(
        """INSERT INTO kg_chunk_entities (chunk_id, entity_id, mention_count)
        VALUES (?, ?, ?)
        ON CONFLICT(chunk_id, entity_id) DO UPDATE SET
        mention_count = mention_count + excluded.mention_count""",
        links
    )
    conn.commit()


# ==================== 清理操作 ====================

def clear_knowledge_graph():
    """清空整个知识图谱（保留表结构）"""
    conn = get_db()
    conn.execute("DELETE FROM kg_chunk_entities")
    conn.execute("DELETE FROM kg_relationships")
    conn.execute("DELETE FROM kg_entities")
    conn.commit()


def clear_entities_by_file(file_id):
    """清除指定文件来源的所有实体和关系"""
    conn = get_db()
    # 先删除关联
    conn.execute(
        """DELETE FROM kg_chunk_entities
        WHERE chunk_id IN (SELECT id FROM embeddings WHERE file_id=?)""",
        (file_id,)
    )
    # 删除关系
    conn.execute(
        "DELETE FROM kg_relationships WHERE source_file_id=?",
        (file_id,)
    )
    # 删除实体（只删除仅来源于此文件的实体）
    conn.execute(
        """DELETE FROM kg_entities
        WHERE source_file_id=? AND id NOT IN (
            SELECT DISTINCT entity_id FROM kg_chunk_entities
        )""",
        (file_id,)
    )
    conn.commit()
