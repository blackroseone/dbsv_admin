# -*- coding: utf-8 -*-
"""数据库类型管理 API"""
from flask import Blueprint, request, jsonify
from db.database import get_db_types, add_db_type, delete_db_type

db_types_bp = Blueprint('db_types', __name__)


@db_types_bp.route('/api/db-types', methods=['GET'])
def get_db_types_list():
    return jsonify({'types': get_db_types()})


@db_types_bp.route('/api/db-types', methods=['POST'])
def add_db_type_api():
    data = request.get_json()
    if not data:
        return jsonify({'error': '请求数据为空'}), 400

    db_id = data.get('id', '').strip().lower()
    db_name = data.get('name', '').strip()
    db_icon = data.get('icon', '📁')

    if not db_id or not db_name:
        return jsonify({'error': '请填写数据库ID和名称'}), 400

    success, error = add_db_type(db_id, db_name, db_icon)
    if not success:
        return jsonify({'error': error}), 400

    return jsonify({'message': '添加成功', 'types': get_db_types()})


@db_types_bp.route('/api/db-types/<db_id>', methods=['DELETE'])
def delete_db_type_api(db_id):
    delete_db_type(db_id)
    return jsonify({'message': '删除成功', 'types': get_db_types()})
