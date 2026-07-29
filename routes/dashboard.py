# -*- coding: utf-8 -*-
"""仪表盘 API - 统计数据、健康检查、快捷键、标签"""
import os
from flask import Blueprint, request, jsonify
from db.database import (
    get_db_types, get_operation_logs, get_config,
    get_knowledge_files, get_topology_data, get_db
)

dashboard_bp = Blueprint('dashboard', __name__)

# 知识库标签定义
KNOWLEDGE_TAGS = [
    {'id': 'install', 'name': '安装部署', 'color': '#4CAF50', 'icon': '📦'},
    {'id': 'maintain', 'name': '日常运维', 'color': '#2196F3', 'icon': '🔧'},
    {'id': 'troubleshoot', 'name': '故障处理', 'color': '#f44336', 'icon': '🚨'},
    {'id': 'performance', 'name': '性能优化', 'color': '#FF9800', 'icon': '⚡'},
    {'id': 'backup', 'name': '备份恢复', 'color': '#9C27B0', 'icon': '💾'},
    {'id': 'security', 'name': '安全管理', 'color': '#607D8B', 'icon': '🔒'},
    {'id': 'upgrade', 'name': '升级迁移', 'color': '#795548', 'icon': '🔄'},
    {'id': 'case', 'name': '故障案例', 'color': '#E91E63', 'icon': '📋'}
]

# 快捷键定义
SHORTCUTS = [
    {'key': 'Ctrl+1', 'action': '打开仪表盘'},
    {'key': 'Ctrl+2', 'action': '打开知识库'},
    {'key': 'Ctrl+3', 'action': '打开知识问答'},
    {'key': 'Ctrl+4', 'action': '打开SQL工具'},
    {'key': 'Ctrl+5', 'action': '打开操作手册'},
    {'key': 'Ctrl+6', 'action': '打开命令速查'},
    {'key': 'Ctrl+7', 'action': '打开集群拓扑'},
    {'key': 'Ctrl+8', 'action': '打开数据库管理'},
    {'key': 'Ctrl+9', 'action': '打开系统配置'},
    {'key': 'Ctrl+K', 'action': '搜索命令'},
    {'key': 'ESC', 'action': '关闭对话框'},
    {'key': 'Enter', 'action': '发送问答（问答模块）'},
    {'key': 'Shift+Enter', 'action': '换行（问答模块）'}
]


@dashboard_bp.route('/api/stats', methods=['GET'])
def get_stats():
    """获取系统统计数据"""
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    DATA_DIR = os.path.join(BASE_DIR, 'data')
    KNOWLEDGE_DIR = os.path.join(DATA_DIR, 'knowledge')
    MANUALS_DIR = os.path.join(DATA_DIR, 'manuals')

    stats = {
        'db_types_count': 0,
        'knowledge_files': 0,
        'manuals_count': 0,
        'clusters_count': 0,
        'by_db_type': {},
        'embeddings_by_db_type': {}  # 新增：向量索引数量统计
    }

    # 获取数据库类型
    db_types = get_db_types()
    stats['db_types_count'] = len(db_types)

    # 从数据库统计知识库文件
    conn = get_db()
    rows = conn.execute(
        "SELECT db_type, COUNT(*) as cnt FROM knowledge_files GROUP BY db_type"
    ).fetchall()
    for row in rows:
        stats['by_db_type'][row['db_type']] = row['cnt']
        stats['knowledge_files'] += row['cnt']

    # 统计向量索引数量（按数据库类型）
    try:
        embedding_rows = conn.execute(
            "SELECT k.db_type, COUNT(*) as cnt FROM embeddings e JOIN knowledge_files k ON e.file_id = k.id GROUP BY k.db_type"
        ).fetchall()
        for row in embedding_rows:
            stats['embeddings_by_db_type'][row['db_type']] = row['cnt']
    except Exception:
        pass  # 如果表不存在或查询失败，忽略

    # 确保所有数据库类型都有统计，并按照默认顺序排序
    from db.database import DEFAULT_DB_TYPES
    ordered_stats = {}
    for t in DEFAULT_DB_TYPES:
        ordered_stats[t['id']] = stats['by_db_type'].get(t['id'], 0)
    # 添加自定义类型（不在默认列表中的）
    for db_type_id, count in stats['by_db_type'].items():
        if db_type_id not in ordered_stats:
            ordered_stats[db_type_id] = count
    stats['by_db_type'] = ordered_stats

    # 同样对向量索引统计进行排序
    ordered_embeddings = {}
    for t in DEFAULT_DB_TYPES:
        ordered_embeddings[t['id']] = stats['embeddings_by_db_type'].get(t['id'], 0)
    for db_type_id, count in stats['embeddings_by_db_type'].items():
        if db_type_id not in ordered_embeddings:
            ordered_embeddings[db_type_id] = count
    stats['embeddings_by_db_type'] = ordered_embeddings

    # 统计运维手册
    if os.path.exists(MANUALS_DIR):
        stats['manuals_count'] = len([f for f in os.listdir(MANUALS_DIR) if os.path.isfile(os.path.join(MANUALS_DIR, f))])

    # 统计集群
    clusters_data = get_topology_data()
    stats['clusters_count'] = len(clusters_data.get('clusters', []))

    return jsonify(stats)


@dashboard_bp.route('/api/health', methods=['GET'])
def health_check():
    """系统健康检查"""
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    DATA_DIR = os.path.join(BASE_DIR, 'data')
    KNOWLEDGE_DIR = os.path.join(DATA_DIR, 'knowledge')

    api_url = get_config('api_url', '')
    api_key = get_config('api_key', '')

    health = {
        'status': 'healthy',
        'version': '2.0',
        'checks': {
            'config': {
                'status': 'ok' if api_url and api_key else 'warning',
                'message': 'LLM配置正常' if api_url else 'LLM未配置'
            },
            'data_dir': {
                'status': 'ok' if os.path.exists(DATA_DIR) else 'error',
                'message': '数据目录正常'
            },
            'knowledge_dir': {
                'status': 'ok' if os.path.exists(KNOWLEDGE_DIR) else 'error',
                'message': '知识库目录正常'
            }
        }
    }

    # 检查是否有任何错误状态
    if any(check['status'] == 'error' for check in health['checks'].values()):
        health['status'] = 'unhealthy'

    return jsonify(health)


@dashboard_bp.route('/api/shortcuts', methods=['GET'])
def get_shortcuts():
    """获取快捷键列表"""
    return jsonify({'shortcuts': SHORTCUTS})


@dashboard_bp.route('/api/tags', methods=['GET'])
def get_tags():
    """获取标签列表"""
    return jsonify({'tags': KNOWLEDGE_TAGS})


@dashboard_bp.route('/api/logs', methods=['GET'])
def get_logs():
    """获取操作日志"""
    limit = request.args.get('limit', 50, type=int)
    module = request.args.get('module', '')

    logs = get_operation_logs(limit=limit, module=module if module else None)
    return jsonify({'logs': logs})


@dashboard_bp.route('/api/logs', methods=['DELETE'])
def clear_logs():
    """清空操作日志"""
    from db.database import clear_operation_logs
    clear_operation_logs()
    return jsonify({'message': '日志已清空'})


@dashboard_bp.route('/api/logs/modules', methods=['GET'])
def get_log_modules():
    """获取日志模块列表"""
    from db.database import get_log_modules
    modules = get_log_modules()
    return jsonify({'modules': modules})
