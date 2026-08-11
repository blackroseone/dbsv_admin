# -*- coding: utf-8 -*-
"""大模型配置 API"""
import os
import json
from datetime import datetime
from flask import Blueprint, request, jsonify
from db.database import get_config, set_config, get_all_config, get_db_types, get_topology_data, get_favorites, add_operation_log, get_feature_config, update_feature_config
from utils import call_llm

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

config_bp = Blueprint('config', __name__)


def _get_models_config():
    """获取所有模型配置"""
    models = get_config('llm_models', [])
    if not isinstance(models, list):
        models = []
    return models


def _get_default_model_id():
    """获取默认模型ID"""
    return get_config('default_model_id', '')


@config_bp.route('/api/config/llm', methods=['GET'])
def get_llm_config():
    """获取当前默认模型配置（兼容旧接口）"""
    models = _get_models_config()
    default_id = _get_default_model_id()

    # 找到默认模型
    default_model = None
    for model in models:
        if model.get('id') == default_id:
            default_model = model
            break

    # 如果没有默认模型，使用第一个
    if not default_model and models:
        default_model = models[0]

    if default_model:
        api_key = default_model.get('api_key', '')
        result = {
            'api_url': default_model.get('api_url', ''),
            'model_name': default_model.get('model_name', ''),
        }
        if api_key and len(api_key) > 8:
            result['api_key_masked'] = api_key[:4] + '****' + api_key[-4:]
        elif api_key:
            result['api_key_masked'] = '****'
        else:
            result['api_key_masked'] = ''
        return jsonify(result)

    # 兼容旧配置
    api_url = get_config('api_url', '')
    api_key = get_config('api_key', '')
    model_name = get_config('model_name', '')

    result = {
        'api_url': api_url,
        'model_name': model_name,
    }
    if api_key and len(api_key) > 8:
        result['api_key_masked'] = api_key[:4] + '****' + api_key[-4:]
    elif api_key:
        result['api_key_masked'] = '****'
    else:
        result['api_key_masked'] = ''

    return jsonify(result)


@config_bp.route('/api/config/llm/models', methods=['GET'])
def get_llm_models():
    """获取所有模型配置列表"""
    models = _get_models_config()
    default_id = _get_default_model_id()

    # 为每个模型添加是否默认标记，并隐藏完整api_key
    result_models = []
    for model in models:
        model_copy = dict(model)
        api_key = model_copy.get('api_key', '')
        if api_key and len(api_key) > 8:
            model_copy['api_key_masked'] = api_key[:4] + '****' + api_key[-4:]
        elif api_key:
            model_copy['api_key_masked'] = '****'
        else:
            model_copy['api_key_masked'] = ''
        # 不返回完整api_key
        model_copy.pop('api_key', None)
        model_copy['is_default'] = (model_copy.get('id') == default_id)
        result_models.append(model_copy)

    return jsonify({
        'models': result_models,
        'default_model_id': default_id
    })


@config_bp.route('/api/config/llm/models', methods=['POST'])
def save_llm_model():
    """保存模型配置（新增或更新）"""
    data = request.get_json()
    if not data:
        return jsonify({'error': '请求数据为空'}), 400

    model_id = data.get('id', '')
    api_url = data.get('api_url', '').strip()
    api_key = data.get('api_key', '').strip()
    model_name = data.get('model_name', '').strip()
    display_name = data.get('display_name', '').strip() or model_name

    if not api_url:
        return jsonify({'error': '请输入API地址'}), 400
    if not api_key:
        return jsonify({'error': '请输入API Key'}), 400
    if not model_name:
        return jsonify({'error': '请输入模型名称'}), 400

    # 温度参数（可选，0-2，默认 0.7）
    temperature = data.get('temperature', 0.7)
    if temperature is None or temperature == '':
        temperature = 0.7
    try:
        temperature = float(temperature)
    except (TypeError, ValueError):
        return jsonify({'error': '温度参数必须是数字(0-2)'}), 400
    if temperature < 0 or temperature > 2:
        return jsonify({'error': '温度参数必须在0-2之间'}), 400

    models = _get_models_config()

    # 查找现有模型或创建新模型
    existing = None
    for i, model in enumerate(models):
        if model.get('id') == model_id:
            existing = i
            break

    if existing is not None:
        # 更新现有模型
        models[existing] = {
            'id': model_id,
            'display_name': display_name,
            'api_url': api_url,
            'api_key': api_key,
            'model_name': model_name,
            'temperature': temperature,
        }
        action = '更新'
    else:
        # 添加新模型
        import uuid
        new_id = str(uuid.uuid4())
        models.append({
            'id': new_id,
            'display_name': display_name,
            'api_url': api_url,
            'api_key': api_key,
            'model_name': model_name,
            'temperature': temperature,
        })
        model_id = new_id
        action = '添加'

    set_config('llm_models', models)

    # 如果是第一个模型或没有默认模型，设为默认
    if len(models) == 1 or not _get_default_model_id():
        set_config('default_model_id', model_id)

    add_operation_log('系统配置', f'{action}LLM模型', f'模型: {display_name}')
    return jsonify({'message': f'{action}成功', 'id': model_id})


@config_bp.route('/api/config/llm/models/<model_id>', methods=['DELETE'])
def delete_llm_model(model_id):
    """删除模型配置"""
    models = _get_models_config()
    models = [m for m in models if m.get('id') != model_id]
    set_config('llm_models', models)

    # 如果删除的是默认模型，重新设置默认
    default_id = _get_default_model_id()
    if default_id == model_id:
        if models:
            set_config('default_model_id', models[0].get('id', ''))
        else:
            set_config('default_model_id', '')

    add_operation_log('系统配置', '删除LLM模型', model_id)
    return jsonify({'message': '删除成功'})


@config_bp.route('/api/config/llm/models/<model_id>/default', methods=['POST'])
def set_default_model(model_id):
    """设置默认模型"""
    models = _get_models_config()
    found = False
    for model in models:
        if model.get('id') == model_id:
            found = True
            break

    if not found:
        return jsonify({'error': '模型不存在'}), 404

    set_config('default_model_id', model_id)
    add_operation_log('系统配置', '设置默认模型', model_id)
    return jsonify({'message': '设置成功'})


@config_bp.route('/api/config/qa-prompt', methods=['GET'])
def get_qa_prompt():
    """获取问答系统提示词配置（未配置返回空字符串，问答模块自动回退默认模板）"""
    return jsonify({'prompt': get_config('qa_system_prompt', '')})


@config_bp.route('/api/config/qa-prompt', methods=['PUT'])
def update_qa_prompt():
    """更新问答系统提示词配置"""
    data = request.get_json() or {}
    prompt = data.get('prompt', '').strip()
    set_config('qa_system_prompt', prompt)
    add_operation_log('系统配置', '更新问答提示词', prompt[:50] or '(已清空)')
    return jsonify({'message': '保存成功'})


@config_bp.route('/api/config/test', methods=['POST'])
def test_connection():
    """测试连接（使用默认模型或指定模型）"""
    data = request.get_json() or {}
    model_id = data.get('model_id', '')

    models = _get_models_config()

    # 找到要测试的模型
    target_model = None
    if model_id:
        for model in models:
            if model.get('id') == model_id:
                target_model = model
                break

    # 如果没有指定模型，使用默认模型
    if not target_model:
        default_id = _get_default_model_id()
        for model in models:
            if model.get('id') == default_id:
                target_model = model
                break

    # 兼容旧配置
    if not target_model:
        api_url = get_config('api_url', '')
        api_key = get_config('api_key', '')
        model_name = get_config('model_name', '')
        if api_url and api_key:
            target_model = {
                'api_url': api_url,
                'api_key': api_key,
                'model_name': model_name
            }

    if not target_model:
        return jsonify({'error': '请先配置API信息'}), 400

    api_url = target_model.get('api_url', '')
    api_key = target_model.get('api_key', '')
    model_name = target_model.get('model_name', '')

    if not api_url or not api_key:
        return jsonify({'error': '请先配置API信息'}), 400

    messages = [
        {"role": "user", "content": "Hello, this is a connection test. Please reply with 'OK'."}
    ]

    # 使用目标模型的ID进行测试（兼容旧配置无id的情况）
    target_model_id = target_model.get('id', '')
    answer, error = call_llm(messages, model_id=target_model_id)
    if error:
        add_operation_log('系统配置', '测试连接', '失败', 'error')
        return jsonify({
            'error': error,
            'details': {
                'api_url': api_url,
                'model_name': model_name,
                'api_key_length': len(api_key) if api_key else 0
            }
        }), 500

    add_operation_log('系统配置', '测试连接', '成功')
    return jsonify({'message': '连接测试成功', 'response': answer})


@config_bp.route('/api/config/export', methods=['GET'])
def export_config():
    """导出配置"""
    config_data = {
        'db_types': get_db_types(),
        'topology': get_topology_data(),
        'favorites': get_favorites(),
        'export_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    }
    return jsonify(config_data)


@config_bp.route('/api/config/import', methods=['POST'])
def import_config():
    """导入配置"""
    data = request.get_json()
    if not data:
        return jsonify({'error': '数据为空'}), 400

    # 导入数据库类型
    if 'db_types' in data:
        from db.database import add_db_type
        for db_type in data['db_types']:
            if 'id' in db_type and 'name' in db_type:
                add_db_type(db_type['id'], db_type['name'], db_type.get('icon', '📁'))

    # 导入收藏夹
    if 'favorites' in data:
        from db.database import toggle_favorite
        for fav in data['favorites'].get('files', []):
            parts = fav.split('/')
            if len(parts) == 2:
                toggle_favorite(parts[0], parts[1])

    return jsonify({'message': '导入成功'})


@config_bp.route('/api/config/docs/<filename>', methods=['GET'])
def get_doc_content(filename):
    """读取项目文档内容"""
    allowed_files = ['README.md', 'version_update.md']
    if filename not in allowed_files:
        return jsonify({'error': '文件不存在'}), 404

    filepath = os.path.join(BASE_DIR, filename)
    if not os.path.exists(filepath):
        return jsonify({'error': '文件不存在'}), 404

    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        return jsonify({'filename': filename, 'content': content})
    except Exception as e:
        return jsonify({'error': f'读取文件失败: {str(e)}'}), 500


# ==================== 功能配置 API ====================

@config_bp.route('/api/config/features', methods=['GET'])
def get_features():
    """获取功能配置列表"""
    features = get_feature_config()
    return jsonify({'features': features})


@config_bp.route('/api/config/features/<module_id>', methods=['PUT'])
def update_feature(module_id):
    """更新功能配置"""
    data = request.get_json() or {}
    is_enabled = data.get('is_enabled', True)
    update_feature_config(module_id, is_enabled)
    add_operation_log('系统配置', '更新功能配置', f'{module_id}: {"启用" if is_enabled else "禁用"}')
    return jsonify({'message': '更新成功'})

