# -*- coding: utf-8 -*-
"""
知识图谱查询引擎
提供邻居查询、最短路径、子图提取等功能
"""
import json
from typing import List, Dict, Optional, Set, Tuple
from collections import deque
from db.kg_database import (
    get_entity_by_id, get_entity_by_name, get_relationships_by_entity,
    get_entities_by_chunk, get_chunks_by_entity, search_entities,
    get_entity_types
)


# ==================== 邻居查询 ====================

def get_entity_neighbors(entity_id: int, max_depth: int = 1,
                         relation_types: List[str] = None,
                         entity_types: List[str] = None,
                         max_relations: int = 50) -> Dict:
    """获取实体的邻居子图

    Args:
        entity_id: 实体 ID
        max_depth: 最大搜索深度
        relation_types: 限制关系类型（None 表示不限）
        entity_types: 限制邻居实体类型（None 表示不限）
        max_relations: 每层最大关系数（防止关系过多的实体导致性能问题）

    Returns:
        {'nodes': [...], 'edges': [...], 'center': {...}}
    """
    visited_entities = {entity_id}
    nodes = {}
    edges = []

    # 获取中心实体
    center = get_entity_by_id(entity_id)
    if not center:
        return {'nodes': [], 'edges': [], 'center': None}

    nodes[entity_id] = _format_node(center)

    # BFS 遍历
    queue = deque([(entity_id, 0)])
    while queue:
        current_id, depth = queue.popleft()
        if depth >= max_depth:
            continue

        # 获取关系（限制数量）
        relationships = get_relationships_by_entity(current_id, direction='both')

        # 按关系类型分组，每组限制数量
        rel_groups = {}
        for rel in relationships:
            rel_type = rel['relation_type']
            if rel_type not in rel_groups:
                rel_groups[rel_type] = []
            rel_groups[rel_type].append(rel)

        # 每组取前 N 个，总共不超过 max_relations
        filtered_rels = []
        per_type_limit = max(5, max_relations // len(rel_groups)) if rel_groups else max_relations
        for rel_type, rels in rel_groups.items():
            filtered_rels.extend(rels[:per_type_limit])

        # 按置信度排序，取前 max_relations
        filtered_rels.sort(key=lambda r: r.get('confidence', 0), reverse=True)
        filtered_rels = filtered_rels[:max_relations]

        for rel in filtered_rels:
            # 过滤关系类型
            if relation_types and rel['relation_type'] not in relation_types:
                continue

            # 确定邻居实体 ID
            if rel['direction'] == 'outgoing':
                neighbor_id = rel['to_entity_id']
            else:
                neighbor_id = rel['from_entity_id']

            # 获取邻居实体
            if neighbor_id not in nodes:
                neighbor = get_entity_by_id(neighbor_id)
                if not neighbor:
                    continue

                # 过滤实体类型
                if entity_types and neighbor['entity_type'] not in entity_types:
                    continue

                nodes[neighbor_id] = _format_node(neighbor)

            # 添加边
            edge = _format_edge(rel)
            if edge not in edges:
                edges.append(edge)

            # 继续 BFS
            if neighbor_id not in visited_entities:
                visited_entities.add(neighbor_id)
                queue.append((neighbor_id, depth + 1))

    return {
        'nodes': list(nodes.values()),
        'edges': edges,
        'center': nodes[entity_id]
    }


# ==================== 最短路径 ====================

def find_shortest_path(from_entity_id: int, to_entity_id: int,
                       max_depth: int = 5,
                       relation_types: List[str] = None) -> Optional[Dict]:
    """查找两个实体之间的最短路径

    Args:
        from_entity_id: 起始实体 ID
        to_entity_id: 目标实体 ID
        max_depth: 最大搜索深度
        relation_types: 限制关系类型

    Returns:
        {'path': [entity, relation, entity, ...], 'length': N} 或 None
    """
    if from_entity_id == to_entity_id:
        entity = get_entity_by_id(from_entity_id)
        return {
            'path': [_format_node(entity)] if entity else [],
            'length': 0
        }

    # BFS
    queue = deque([(from_entity_id, [])])
    visited = {from_entity_id}

    while queue:
        current_id, path = queue.popleft()

        if len(path) // 2 >= max_depth:
            continue

        relationships = get_relationships_by_entity(current_id, direction='outgoing')

        for rel in relationships:
            if relation_types and rel['relation_type'] not in relation_types:
                continue

            neighbor_id = rel['to_entity_id']

            if neighbor_id == to_entity_id:
                # 找到路径
                current_entity = get_entity_by_id(current_id)
                target_entity = get_entity_by_id(to_entity_id)

                if not current_entity or not target_entity:
                    continue

                full_path = path + [
                    _format_node(current_entity),
                    _format_edge(rel),
                    _format_node(target_entity)
                ]

                return {
                    'path': full_path,
                    'length': len(full_path) // 2
                }

            if neighbor_id not in visited:
                visited.add(neighbor_id)
                current_entity = get_entity_by_id(current_id)
                if current_entity:
                    new_path = path + [
                        _format_node(current_entity),
                        _format_edge(rel)
                    ]
                    queue.append((neighbor_id, new_path))

    return None


# ==================== 子图提取 ====================

def extract_subgraph(entity_ids: List[int], max_depth: int = 1,
                     relation_types: List[str] = None) -> Dict:
    """提取多个实体构成的子图

    Args:
        entity_ids: 种子实体 ID 列表
        max_depth: 每个种子的扩展深度
        relation_types: 限制关系类型

    Returns:
        {'nodes': [...], 'edges': [...]}
    """
    nodes = {}
    edges = []
    visited = set()

    for seed_id in entity_ids:
        if seed_id in visited:
            continue

        # BFS 从种子扩展
        queue = deque([(seed_id, 0)])
        visited.add(seed_id)

        while queue:
            current_id, depth = queue.popleft()

            # 获取实体
            if current_id not in nodes:
                entity = get_entity_by_id(current_id)
                if entity:
                    nodes[current_id] = _format_node(entity)

            if depth >= max_depth:
                continue

            # 获取关系
            relationships = get_relationships_by_entity(current_id, direction='both')

            for rel in relationships:
                if relation_types and rel['relation_type'] not in relation_types:
                    continue

                if rel['direction'] == 'outgoing':
                    neighbor_id = rel['to_entity_id']
                else:
                    neighbor_id = rel['from_entity_id']

                # 添加边
                edge = _format_edge(rel)
                if edge not in edges:
                    edges.append(edge)

                # 添加邻居节点
                if neighbor_id not in nodes:
                    neighbor = get_entity_by_id(neighbor_id)
                    if neighbor:
                        nodes[neighbor_id] = _format_node(neighbor)

                if neighbor_id not in visited:
                    visited.add(neighbor_id)
                    queue.append((neighbor_id, depth + 1))

    return {
        'nodes': list(nodes.values()),
        'edges': edges
    }


# ==================== 实体搜索增强 ====================

def search_entities_enhanced(keyword: str, entity_type: str = None,
                             include_neighbors: bool = False,
                             neighbor_depth: int = 1,
                             max_relations: int = 30) -> Dict:
    """增强的实体搜索，可选包含邻居子图

    Args:
        keyword: 搜索关键词
        entity_type: 实体类型过滤
        include_neighbors: 是否包含邻居
        neighbor_depth: 邻居深度
        max_relations: 每层最大关系数

    Returns:
        {'entities': [...], 'subgraph': {...} (可选)}
    """
    entities = search_entities(keyword, entity_type, limit=20)

    result = {'entities': entities}

    if include_neighbors and entities:
        # 获取第一个实体的邻居
        first_entity = entities[0]
        subgraph = get_entity_neighbors(
            first_entity['id'],
            max_depth=neighbor_depth,
            max_relations=max_relations
        )
        result['subgraph'] = subgraph

    return result


# ==================== 问答增强查询 ====================

def enhance_qa_context(chunk_ids: List[int], question: str) -> Dict:
    """为问答增强图谱上下文

    Args:
        chunk_ids: 检索到的 chunk ID 列表
        question: 用户问题

    Returns:
        {'entity_cards': [...], 'relation_chains': [...], 'related_chunks': [...]}
    """
    # 1. 从 chunk 提取实体
    chunk_entities = {}
    for chunk_id in chunk_ids:
        entities = get_entities_by_chunk(chunk_id)
        for entity in entities:
            eid = entity['id']
            if eid not in chunk_entities:
                chunk_entities[eid] = {
                    'entity': entity,
                    'chunk_ids': []
                }
            chunk_entities[eid]['chunk_ids'].append(chunk_id)

    # 2. 构建实体卡片
    entity_cards = []
    for eid, data in chunk_entities.items():
        entity = data['entity']
        # 获取实体的关系
        relationships = get_relationships_by_entity(eid, direction='both')

        # 只保留重要的关系（置信度 > 0.7）
        important_rels = [r for r in relationships if r.get('confidence', 0) > 0.7]

        # 限制关系数量
        important_rels = important_rels[:5]

        entity_cards.append({
            'id': entity['id'],
            'name': entity['name'],
            'type': entity['entity_type'],
            'description': entity.get('description', ''),
            'mention_count': len(data['chunk_ids']),
            'relations': [
                {
                    'direction': r['direction'],
                    'relation_type': r['relation_type'],
                    'target_name': r.get('to_name' if r['direction'] == 'outgoing' else 'from_name', ''),
                    'target_type': r.get('to_type' if r['direction'] == 'outgoing' else 'from_type', ''),
                    'confidence': r.get('confidence', 1.0)
                }
                for r in important_rels
            ]
        })

    # 3. 查找实体间的关系链
    entity_ids = list(chunk_entities.keys())
    relation_chains = []

    if len(entity_ids) >= 2:
        # 查找每对实体之间的路径
        for i in range(min(len(entity_ids), 5)):
            for j in range(i + 1, min(len(entity_ids), 5)):
                path = find_shortest_path(entity_ids[i], entity_ids[j], max_depth=3)
                if path and path['length'] > 0:
                    relation_chains.append(path)

    # 4. 获取相关 chunk（通过实体关联）
    related_chunks = []
    for eid in list(chunk_entities.keys())[:3]:
        chunks = get_chunks_by_entity(eid)
        for chunk in chunks:
            if chunk['id'] not in chunk_ids:
                related_chunks.append({
                    'id': chunk['id'],
                    'filename': chunk['filename'],
                    'db_type': chunk['db_type'],
                    'chunk_text': chunk['chunk_text'][:200] + '...',
                    'mention_count': chunk['mention_count']
                })

    # 去重并限制数量
    seen = set()
    unique_related = []
    for chunk in related_chunks:
        if chunk['id'] not in seen and len(unique_related) < 5:
            seen.add(chunk['id'])
            unique_related.append(chunk)

    return {
        'entity_cards': entity_cards[:10],  # 最多 10 个实体卡片
        'relation_chains': relation_chains[:5],  # 最多 5 条关系链
        'related_chunks': unique_related
    }


# ==================== 图谱统计 ====================

def get_graph_overview() -> Dict:
    """获取知识图谱概览"""
    from db.kg_database import get_entity_stats

    stats = get_entity_stats()

    # 获取热门实体（关联 chunk 最多的）
    from db.database import get_db
    conn = get_db()
    popular_entities = conn.execute(
        """SELECT e.id, e.name, e.entity_type, COUNT(ce.chunk_id) as chunk_count
        FROM kg_entities e
        JOIN kg_chunk_entities ce ON e.id = ce.entity_id
        GROUP BY e.id
        ORDER BY chunk_count DESC
        LIMIT 10"""
    ).fetchall()

    stats['popular_entities'] = [dict(r) for r in popular_entities]

    return stats


# ==================== 辅助函数 ====================

def _format_node(entity: Dict) -> Dict:
    """格式化节点用于前端展示"""
    return {
        'id': entity['id'],
        'name': entity['name'],
        'type': entity['entity_type'],
        'normalized_name': entity.get('normalized_name', entity['name'].lower()),
        'description': entity.get('description', ''),
        'confidence': entity.get('confidence', 1.0),
        'aliases': entity.get('aliases', []),
        'properties': entity.get('properties', {})
    }


def _format_edge(relationship: Dict) -> Dict:
    """格式化边用于前端展示"""
    return {
        'id': relationship.get('id'),
        'source': relationship.get('from_entity_id'),
        'target': relationship.get('to_entity_id'),
        'relation_type': relationship['relation_type'],
        'direction': relationship.get('direction', 'outgoing'),
        'confidence': relationship.get('confidence', 1.0),
        'source_name': relationship.get('from_name', ''),
        'target_name': relationship.get('to_name', '')
    }
