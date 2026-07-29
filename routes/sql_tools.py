# -*- coding: utf-8 -*-
"""SQL工具 API"""
import json
from flask import Blueprint, request, jsonify, Response
from db.database import get_db_types
from utils import call_llm, stream_llm_response

# 导入本地 SQL 语法检查模块
try:
    from sql_checker import check_sql_syntax, get_sql_info, format_sql_local, is_dialect_supported
    SQL_CHECKER_AVAILABLE = True
except ImportError:
    SQL_CHECKER_AVAILABLE = False

sql_tools_bp = Blueprint('sql_tools', __name__)


@sql_tools_bp.route('/api/sql/format', methods=['POST'])
def format_sql():
    data = request.get_json()
    sql = data.get('sql', '')

    if not sql:
        return jsonify({'error': '请输入SQL语句'}), 400

    messages = [
        {"role": "system", "content": "你是一个SQL格式化工具。请将用户提供的SQL语句进行格式化，使其更易读。只返回格式化后的SQL，不要添加任何解释。"},
        {"role": "user", "content": sql}
    ]

    formatted, error = call_llm(messages)
    if error:
        return jsonify({'error': error}), 500

    return jsonify({'formatted_sql': formatted})


@sql_tools_bp.route('/api/sql/convert', methods=['POST'])
def convert_sql():
    data = request.get_json()
    sql = data.get('sql', '')
    source_db = data.get('source_db', '')
    target_db = data.get('target_db', '')

    if not sql or not source_db or not target_db:
        return jsonify({'error': '请填写完整信息'}), 400

    db_types = get_db_types()
    source_name = source_db
    target_name = target_db
    for t in db_types:
        if t['id'] == source_db:
            source_name = t['name']
        if t['id'] == target_db:
            target_name = t['name']

    messages = [
        {"role": "system", "content": f"""你是一个SQL转换专家。请将{source_name}的SQL语句转换为{target_name}的等效SQL。
注意：
1. 处理语法差异
2. 处理函数差异
3. 处理数据类型差异
4. 只返回转换后的SQL，不要添加解释"""},
        {"role": "user", "content": sql}
    ]

    converted, error = call_llm(messages)
    if error:
        return jsonify({'error': error}), 500

    return jsonify({'converted_sql': converted})


@sql_tools_bp.route('/api/sql/explain', methods=['POST'])
def explain_sql():
    data = request.get_json()
    db_type = data.get('db_type', '')
    explain_result = data.get('explain_result', '')

    if not explain_result:
        return jsonify({'error': '请输入执行计划结果'}), 400

    db_types = get_db_types()
    db_name = db_type
    for t in db_types:
        if t['id'] == db_type:
            db_name = t['name']
            break

    messages = [
        {"role": "system", "content": f"""你是一个{db_name}性能优化专家。请分析以下执行计划，并提供：
1. 执行计划解读
2. 性能瓶颈识别
3. 优化建议
4. 索引建议（如需要）"""},
        {"role": "user", "content": f"执行计划：\n{explain_result}"}
    ]

    analysis, error = call_llm(messages)
    if error:
        return jsonify({'error': error}), 500

    return jsonify({'analysis': analysis})


@sql_tools_bp.route('/api/sql/review', methods=['POST'])
def review_sql():
    data = request.get_json()
    if not data:
        return jsonify({'error': '请求数据为空'}), 400

    db_type = data.get('db_type', '')
    sql = data.get('sql', '')

    if not sql:
        return jsonify({'error': '请输入SQL语句'}), 400

    db_types = get_db_types()
    db_name = db_type
    for t in db_types:
        if t['id'] == db_type:
            db_name = t['name']
            break

    system_prompt = f"""你是一个{db_name}数据库SQL审核专家。请对用户提供的SQL进行审核。

审核要点：
1. 语法正确性
2. 性能优化建议
3. 安全性检查（SQL注入风险）
4. 最佳实践建议
5. 索引使用建议

请按以下格式返回：
## 审核结果
[总体评价]

## 发现的问题
[问题列表]

## 优化建议
[建议列表]

## 优化后的SQL（如有必要）
[优化后的SQL]"""

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"请审核以下{db_name} SQL语句：\n\n```sql\n{sql}\n```"}
    ]

    review, error = call_llm(messages)
    if error:
        return jsonify({'error': error}), 500

    return jsonify({'review': review})


# ==================== 流式输出接口 ====================

def _stream_response(messages, model_id=None):
    """通用流式响应生成器"""
    for data in stream_llm_response(messages, model_id=model_id):
        yield data


@sql_tools_bp.route('/api/sql/format/stream', methods=['POST'])
def format_sql_stream():
    """SQL格式化（流式输出）"""
    data = request.get_json()
    sql = data.get('sql', '')

    if not sql:
        return jsonify({'error': '请输入SQL语句'}), 400

    messages = [
        {"role": "system", "content": "你是一个SQL格式化工具。请将用户提供的SQL语句进行格式化，使其更易读。只返回格式化后的SQL，不要添加任何解释。"},
        {"role": "user", "content": sql}
    ]

    return Response(_stream_response(messages), mimetype='text/event-stream')


@sql_tools_bp.route('/api/sql/convert/stream', methods=['POST'])
def convert_sql_stream():
    """SQL转换（流式输出）"""
    data = request.get_json()
    sql = data.get('sql', '')
    source_db = data.get('source_db', '')
    target_db = data.get('target_db', '')

    if not sql or not source_db or not target_db:
        return jsonify({'error': '请填写完整信息'}), 400

    db_types = get_db_types()
    source_name = source_db
    target_name = target_db
    for t in db_types:
        if t['id'] == source_db:
            source_name = t['name']
        if t['id'] == target_db:
            target_name = t['name']

    messages = [
        {"role": "system", "content": f"""你是一个SQL转换专家。请将{source_name}的SQL语句转换为{target_name}的等效SQL。
注意：
1. 处理语法差异
2. 处理函数差异
3. 处理数据类型差异
4. 只返回转换后的SQL，不要添加解释"""},
        {"role": "user", "content": sql}
    ]

    return Response(_stream_response(messages), mimetype='text/event-stream')


@sql_tools_bp.route('/api/sql/explain/stream', methods=['POST'])
def explain_sql_stream():
    """执行计划分析（流式输出）"""
    data = request.get_json()
    db_type = data.get('db_type', '')
    explain_result = data.get('explain_result', '')

    if not explain_result:
        return jsonify({'error': '请输入执行计划结果'}), 400

    db_types = get_db_types()
    db_name = db_type
    for t in db_types:
        if t['id'] == db_type:
            db_name = t['name']
            break

    messages = [
        {"role": "system", "content": f"""你是一个{db_name}性能优化专家。请分析以下执行计划，并提供：
1. 执行计划解读
2. 性能瓶颈识别
3. 优化建议
4. 索引建议（如需要）"""},
        {"role": "user", "content": f"执行计划：\n{explain_result}"}
    ]

    return Response(_stream_response(messages, model_id=data.get('model_id', '')), mimetype='text/event-stream')


@sql_tools_bp.route('/api/sql/review/stream', methods=['POST'])
def review_sql_stream():
    """SQL审核（流式输出）"""
    data = request.get_json()
    if not data:
        return jsonify({'error': '请求数据为空'}), 400

    db_type = data.get('db_type', '')
    sql = data.get('sql', '')
    model_id = data.get('model_id', '')
    review_mode = data.get('review_mode', 'syntax')  # 新增：审核模式

    if not sql:
        return jsonify({'error': '请输入SQL语句'}), 400

    db_types = get_db_types()
    db_name = db_type
    for t in db_types:
        if t['id'] == db_type:
            db_name = t['name']
            break

    # 根据审核模式选择不同的提示词
    if review_mode == 'syntax':
        system_prompt = f"""你是一个{db_name}数据库SQL语法检查工具。

请检查以下SQL语句的语法是否正确：
1. 关键字拼写是否正确
2. 语句结构是否完整
3. 括号是否匹配
4. 引号是否成对出现
5. 分号使用是否正确

如果语法正确，请简洁回复"✅ 语法正确"。
如果有错误，请指出：
- 错误位置（行号或附近代码）
- 错误原因
- 修正建议（简要）"""
    else:
        # 综合审核模式
        system_prompt = f"""你是一个{db_name}数据库SQL审核专家。

请对以下SQL进行审核，重点关注：
1. 语法正确性
2. 性能优化建议（如索引、查询优化等）
3. 安全性问题（SQL注入风险等）
4. 最佳实践建议

请简洁地列出发现的问题和建议，避免冗长。"""

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"请审核以下{db_name} SQL语句：\n\n```sql\n{sql}\n```"}
    ]

    return Response(_stream_response(messages, model_id=model_id), mimetype='text/event-stream')


# ==================== 本地 SQL 语法检查接口 ====================

@sql_tools_bp.route('/api/sql/check', methods=['POST'])
def check_sql():
    """本地 SQL 语法检查"""
    data = request.get_json()
    if not data:
        return jsonify({'error': '请求数据为空'}), 400

    sql = data.get('sql', '')
    db_type = data.get('db_type', 'mysql')

    if not sql:
        return jsonify({'error': '请输入SQL语句'}), 400

    # 检查 sqlglot 是否可用
    if not SQL_CHECKER_AVAILABLE:
        return jsonify({
            'error': '本地 SQL 语法检查模块未安装',
            'suggestion': '请执行: pip install sqlglot'
        }), 500

    # 执行本地语法检查
    is_valid, message, details = check_sql_syntax(sql, db_type)

    # 获取 SQL 详细信息
    sql_info = get_sql_info(sql, db_type)

    return jsonify({
        'is_valid': is_valid,
        'message': message,
        'details': details,
        'sql_info': sql_info,
        'mode': 'local',
        'db_type': db_type
    })


@sql_tools_bp.route('/api/sql/check/stream', methods=['POST'])
def check_sql_stream():
    """本地 SQL 语法检查（流式输出）"""
    data = request.get_json()
    if not data:
        return jsonify({'error': '请求数据为空'}), 400

    sql = data.get('sql', '')
    db_type = data.get('db_type', 'mysql')

    if not sql:
        return jsonify({'error': '请输入SQL语句'}), 400

    def generate():
        # 检查 sqlglot 是否可用
        if not SQL_CHECKER_AVAILABLE:
            yield f"data: {json.dumps({'error': '本地 SQL 语法检查模块未安装，请执行: pip install sqlglot'})}\n\n"
            yield "data: [DONE]\n\n"
            return

        # 执行本地语法检查
        is_valid, message, details = check_sql_syntax(sql, db_type)

        if is_valid is None:
            # 不支持该方言，回退到 LLM
            yield f"data: {json.dumps({'content': message})}\n\n"
            yield f"data: {json.dumps({'content': '\\n正在使用 LLM 进行审核...\\n'})}\n\n"
            yield "data: [DONE]\n\n"
            return

        # 返回检查结果
        if is_valid:
            yield f"data: {json.dumps({'content': f'{message}\\n'})}\n\n"

            # 获取 SQL 详细信息
            sql_info = get_sql_info(sql, db_type)
            if sql_info:
                info_text = "\n**SQL 信息：**\n"
                if sql_info.get('statement_types'):
                    info_text += f"- 语句类型: {', '.join(sql_info['statement_types'])}\n"
                if sql_info.get('tables'):
                    info_text += f"- 涉及表: {', '.join(sql_info['tables'])}\n"
                if sql_info.get('columns'):
                    info_text += f"- 涉及列: {', '.join(sql_info['columns'][:10])}\n"
                yield f"data: {json.dumps({'content': info_text})}\n\n"
        else:
            yield f"data: {json.dumps({'content': f'{message}\\n'})}\n\n"

            # 返回详细信息
            if details.get('errors'):
                error_text = "\n**详细错误：**\n"
                for i, error in enumerate(details['errors'][:5], 1):
                    error_text += f"{i}. {error}\n"
                yield f"data: {json.dumps({'content': error_text})}\n\n"

            if details.get('suggestion'):
                yield f"data: {json.dumps({'content': f"\\n**建议：** {details['suggestion']}"})}\n\n"

        yield "data: [DONE]\n\n"

    return Response(generate(), mimetype='text/event-stream')
