"""Agent核心API路由"""
import json
import uuid
from flask import Blueprint, request, jsonify, Response
from db.database import get_db, add_operation_log
from agent.engine import SmartOpsAgent

agent_bp = Blueprint('agent', __name__)


# ==================== Agent会话管理 ====================

@agent_bp.route('/api/agent/sessions', methods=['GET'])
def list_sessions():
    """获取Agent会话列表"""
    conn = get_db()
    rows = conn.execute(
        "SELECT id, title, ssh_connection_id, db_connection_id, "
        "status, current_step, created_at, updated_at "
        "FROM agent_sessions ORDER BY created_at DESC"
    ).fetchall()
    return jsonify({'sessions': [dict(r) for r in rows]})


@agent_bp.route('/api/agent/sessions', methods=['POST'])
def create_session():
    """创建Agent会话"""
    data = request.get_json()

    session_id = str(uuid.uuid4())
    title = data.get('title', '新会话')
    ssh_conn_id = data.get('ssh_connection_id')
    db_conn_id = data.get('db_connection_id')

    conn = get_db()
    conn.execute(
        """INSERT INTO agent_sessions
           (id, title, ssh_connection_id, db_connection_id)
           VALUES (?, ?, ?, ?)""",
        (session_id, title, ssh_conn_id, db_conn_id)
    )
    conn.commit()

    add_operation_log('Agent', '创建会话', title)

    return jsonify({
        'message': '创建成功',
        'session': {
            'id': session_id,
            'title': title,
            'status': 'idle'
        }
    })


@agent_bp.route('/api/agent/sessions/<session_id>', methods=['GET'])
def get_session(session_id):
    """获取Agent会话详情"""
    conn = get_db()
    row = conn.execute(
        "SELECT * FROM agent_sessions WHERE id=?",
        (session_id,)
    ).fetchone()

    if not row:
        return jsonify({'error': '会话不存在'}), 404

    # 获取执行步骤
    steps = conn.execute(
        "SELECT * FROM agent_steps WHERE session_id=? ORDER BY step_number",
        (session_id,)
    ).fetchall()

    return jsonify({
        'session': dict(row),
        'steps': [dict(s) for s in steps]
    })


@agent_bp.route('/api/agent/sessions/<session_id>', methods=['DELETE'])
def delete_session(session_id):
    """删除Agent会话"""
    conn = get_db()
    conn.execute("DELETE FROM agent_steps WHERE session_id=?", (session_id,))
    conn.execute("DELETE FROM agent_sessions WHERE id=?", (session_id,))
    conn.commit()

    add_operation_log('Agent', '删除会话', session_id)

    return jsonify({'message': '删除成功'})


# ==================== Agent执行（核心）====================

@agent_bp.route('/api/agent/run', methods=['POST'])
def run_agent():
    """启动Agent任务（SSE流式）"""
    data = request.get_json()

    session_id = data.get('session_id')
    question = data.get('question')
    model_id = data.get('model_id')

    if not session_id or not question:
        return jsonify({'error': '缺少session_id或question'}), 400

    # 获取会话信息
    conn = get_db()
    row = conn.execute(
        "SELECT * FROM agent_sessions WHERE id=?",
        (session_id,)
    ).fetchone()

    if not row:
        return jsonify({'error': '会话不存在'}), 404

    ssh_conn_id = row['ssh_connection_id']
    db_conn_id = row['db_connection_id']

    def generate():
        """生成SSE流"""
        agent = SmartOpsAgent(
            session_id=session_id,
            ssh_conn_id=ssh_conn_id,
            db_conn_id=db_conn_id,
            model_id=model_id
        )

        try:
            for event in agent.run_stream(question):
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)}, ensure_ascii=False)}\n\n"

        yield "data: [DONE]\n\n"

    return Response(generate(), mimetype='text/event-stream')


@agent_bp.route('/api/agent/sessions/<session_id>/steps', methods=['GET'])
def get_session_steps(session_id):
    """获取会话执行步骤"""
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM agent_steps WHERE session_id=? ORDER BY step_number",
        (session_id,)
    ).fetchall()

    return jsonify({
        'steps': [dict(r) for r in rows]
    })


# ==================== Skills管理 ====================

@agent_bp.route('/api/agent/skills', methods=['GET'])
def list_skills():
    """获取Skills列表"""
    from agent.skills import SkillManager

    manager = SkillManager()
    db_type = request.args.get('db_type')
    category = request.args.get('category')

    skills = manager.find_skills(db_type=db_type, category=category)

    return jsonify({
        'skills': skills
    })


@agent_bp.route('/api/agent/skills/<skill_name>', methods=['GET'])
def get_skill(skill_name):
    """获取单个Skill详情"""
    from agent.skills import SkillManager

    manager = SkillManager()
    skill = manager.get_skill(skill_name)

    if not skill:
        return jsonify({'error': 'Skill不存在'}), 404

    return jsonify({
        'skill': skill
    })


# ==================== 工具Schema ====================

@agent_bp.route('/api/agent/tools', methods=['GET'])
def list_tools():
    """获取可用工具列表"""
    from agent.tools import get_tool_schemas

    schemas = get_tool_schemas()

    return jsonify({
        'tools': schemas
    })
