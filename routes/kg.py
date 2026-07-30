# -*- coding: utf-8 -*-
"""
知识图谱 API 路由
提供实体查询、关系查询、图谱搜索、子图提取等接口
"""
import json
from flask import Blueprint, request, jsonify

from db.kg_database import (
    get_entity_by_id, get_entity_by_name, search_entities,
    get_entities_by_type, get_entity_types, get_entity_stats,
    get_relationships_by_entity, get_relationships_between,
    get_entities_by_chunk, get_chunks_by_entity,
    clear_knowledge_graph
)
from kg.graph import (
    get_entity_neighbors, find_shortest_path, extract_subgraph,
    search_entities_enhanced, enhance_qa_context, get_graph_overview
)

kg_bp = Blueprint('kg', __name__)


# ==================== 实体查询 API ====================

@kg_bp.route('/api/kg/entities/search', methods=['GET'])
def search_entities_api():
    """搜索实体
    GET /api/kg/entities/search?q=MySQL&type=database_product&limit=20
    """
    keyword = request.args.get('q', '')
    entity_type = request.args.get('type') or None
    limit = request.args.get('limit', 20, type=int)
    include_neighbors = request.args.get('neighbors', 'false').lower() == 'true'
    neighbor_depth = request.args.get('depth', 1, type=int)

    if not keyword:
        return jsonify({'error': '缺少搜索关键词'}), 400

    try:
        result = search_entities_enhanced(
            keyword, entity_type,
            include_neighbors=include_neighbors,
            neighbor_depth=neighbor_depth
        )
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@kg_bp.route('/api/kg/entities/<int:entity_id>', methods=['GET'])
def get_entity_api(entity_id):
    """获取实体详情
    GET /api/kg/entities/123
    """
    entity = get_entity_by_id(entity_id)
    if not entity:
        return jsonify({'error': '实体不存在'}), 404

    # 获取实体关系
    relationships = get_relationships_by_entity(entity_id, direction='both')

    # 获取关联的 chunk
    chunks = get_chunks_by_entity(entity_id)

    return jsonify({
        'entity': entity,
        'relationships': relationships,
        'chunks': chunks[:20]  # 限制数量
    })


@kg_bp.route('/api/kg/entities/by-name', methods=['GET'])
def get_entity_by_name_api():
    """通过名称获取实体
    GET /api/kg/entities/by-name?name=MySQL&type=database_product
    """
    name = request.args.get('name', '')
    entity_type = request.args.get('type') or None

    if not name:
        return jsonify({'error': '缺少实体名称'}), 400

    entity = get_entity_by_name(name, entity_type)
    if not entity:
        return jsonify({'error': '实体不存在'}), 404

    return jsonify(entity)


@kg_bp.route('/api/kg/entities/by-type/<entity_type>', methods=['GET'])
def get_entities_by_type_api(entity_type):
    """获取指定类型的实体列表
    GET /api/kg/entities/by-type/database_product?limit=100
    """
    limit = request.args.get('limit', 100, type=int)
    entities = get_entities_by_type(entity_type, limit=limit)
    return jsonify({'entities': entities})


@kg_bp.route('/api/kg/entity-types', methods=['GET'])
def get_entity_types_api():
    """获取所有实体类型及其数量
    GET /api/kg/entity-types
    """
    types = get_entity_types()
    return jsonify({'types': types})


# ==================== 关系查询 API ====================

@kg_bp.route('/api/kg/entities/<int:entity_id>/neighbors', methods=['GET'])
def get_entity_neighbors_api(entity_id):
    """获取实体的邻居子图
    GET /api/kg/entities/123/neighbors?depth=2&relation_types=compatible_with,requires
    """
    depth = request.args.get('depth', 1, type=int)
    relation_types_str = request.args.get('relation_types', '')
    relation_types = [t.strip() for t in relation_types_str.split(',') if t.strip()] or None

    entity_types_str = request.args.get('entity_types', '')
    entity_types = [t.strip() for t in entity_types_str.split(',') if t.strip()] or None

    try:
        result = get_entity_neighbors(
            entity_id, max_depth=depth,
            relation_types=relation_types,
            entity_types=entity_types
        )
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@kg_bp.route('/api/kg/path', methods=['GET'])
def find_path_api():
    """查找两个实体之间的最短路径
    GET /api/kg/path?from=1&to=2&max_depth=5
    """
    from_id = request.args.get('from', type=int)
    to_id = request.args.get('to', type=int)
    max_depth = request.args.get('max_depth', 5, type=int)

    if not from_id or not to_id:
        return jsonify({'error': '缺少起始或目标实体 ID'}), 400

    path = find_shortest_path(from_id, to_id, max_depth=max_depth)
    if not path:
        return jsonify({'error': '未找到路径'}), 404

    return jsonify(path)


@kg_bp.route('/api/kg/relationships', methods=['GET'])
def get_relationships_between_api():
    """获取两个实体之间的关系
    GET /api/kg/relationships?from=1&to=2
    """
    from_id = request.args.get('from', type=int)
    to_id = request.args.get('to', type=int)

    if not from_id or not to_id:
        return jsonify({'error': '缺少实体 ID'}), 400

    relationships = get_relationships_between(from_id, to_id)
    return jsonify({'relationships': relationships})


# ==================== 子图提取 API ====================

@kg_bp.route('/api/kg/subgraph', methods=['POST'])
def extract_subgraph_api():
    """提取子图
    POST /api/kg/subgraph
    Body: {"entity_ids": [1, 2, 3], "depth": 2, "relation_types": ["compatible_with"]}
    """
    data = request.get_json() or {}
    entity_ids = data.get('entity_ids', [])
    depth = data.get('depth', 1)
    relation_types = data.get('relation_types')

    if not entity_ids:
        return jsonify({'error': '缺少实体 ID 列表'}), 400

    try:
        result = extract_subgraph(
            entity_ids, max_depth=depth,
            relation_types=relation_types
        )
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ==================== Chunk 关联 API ====================

@kg_bp.route('/api/kg/chunks/<int:chunk_id>/entities', methods=['GET'])
def get_chunk_entities_api(chunk_id):
    """获取 chunk 关联的实体
    GET /api/kg/chunks/123/entities
    """
    entities = get_entities_by_chunk(chunk_id)
    return jsonify({'entities': entities})


@kg_bp.route('/api/kg/entities/<int:entity_id>/chunks', methods=['GET'])
def get_entity_chunks_api(entity_id):
    """获取实体关联的 chunk
    GET /api/kg/entities/123/chunks
    """
    chunks = get_chunks_by_entity(entity_id)
    return jsonify({'chunks': chunks})


# ==================== QA 增强 API ====================

@kg_bp.route('/api/kg/qa-enhance', methods=['POST'])
def qa_enhance_api():
    """为问答增强图谱上下文
    POST /api/kg/qa-enhance
    Body: {"chunk_ids": [1, 2, 3], "question": "MySQL 性能优化"}
    """
    data = request.get_json() or {}
    chunk_ids = data.get('chunk_ids', [])
    question = data.get('question', '')

    if not chunk_ids:
        return jsonify({'error': '缺少 chunk ID 列表'}), 400

    try:
        result = enhance_qa_context(chunk_ids, question)
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ==================== 图谱概览 API ====================

@kg_bp.route('/api/kg/overview', methods=['GET'])
def get_overview_api():
    """获取知识图谱概览统计
    GET /api/kg/overview
    """
    try:
        overview = get_graph_overview()
        return jsonify(overview)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@kg_bp.route('/api/kg/stats', methods=['GET'])
def get_stats_api():
    """获取知识图谱统计
    GET /api/kg/stats
    """
    stats = get_entity_stats()
    return jsonify(stats)


# ==================== 管理 API ====================

@kg_bp.route('/api/kg/clear', methods=['POST'])
def clear_graph_api():
    """清空知识图谱（危险操作）
    POST /api/kg/clear
    """
    try:
        clear_knowledge_graph()
        return jsonify({'success': True, 'message': '知识图谱已清空'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ==================== 页面路由 ====================

@kg_bp.route('/kg')
def kg_page():
    """知识图谱浏览页面"""
    from flask import send_from_directory
    import os
    static_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'static')
    return send_from_directory(static_dir, 'kg.html')
