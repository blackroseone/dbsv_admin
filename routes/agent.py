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
        "SELECT id, title, ssh_connection_id, db_connection_id, scope_type, scope_json, "
        "status, current_step, created_at, updated_at "
        "FROM agent_sessions ORDER BY created_at DESC"
    ).fetchall()
    return jsonify({'sessions': [dict(r) for r in rows]})


@agent_bp.route('/api/agent/sessions', methods=['POST'])
def create_session():
    """创建Agent会话

    body 可选：scope=[{type,topo_id,conn_id,name}...]（v4.0 多节点范围），
    或 legacy ssh_connection_id/db_connection_id。两者都缺则按旧行为创建。
    """
    from db.database import set_session_scope, get_session_scope

    data = request.get_json()

    session_id = str(uuid.uuid4())
    title = data.get('title', '新会话')
    scope = data.get('scope')
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

    # v4.0：带 scope 的会话写入范围（set_session_scope 同步旧列）；无 scope 走 legacy
    if isinstance(scope, list) and scope:
        set_session_scope(session_id, 'scope', scope)

    add_operation_log('Agent', '创建会话', title)

    sc = get_session_scope(session_id)
    return jsonify({
        'message': '创建成功',
        'session': {
            'id': session_id,
            'title': title,
            'status': 'idle',
            'scope_type': sc['scope_type'],
            'scope_json': json.dumps(sc['targets'], ensure_ascii=False),
        }
    })


@agent_bp.route('/api/agent/sessions/<session_id>/scope', methods=['GET', 'PUT'])
def session_scope(session_id):
    """获取/更新会话范围（v4.0）

    GET: 返回解析后的 targets + 会话状态（范围面板徽标/编辑回显用）。
    PUT: 更新范围；会话执行中拒绝（409）。scope 原样存储（含未配置节点，
    引擎运行时可分辨并跳过）。
    """
    from db.database import get_session_scope, set_session_scope
    from agent.scope import resolve_scope

    conn = get_db()
    row = conn.execute(
        "SELECT id, status FROM agent_sessions WHERE id=?", (session_id,)).fetchone()
    if not row:
        return jsonify({'error': '会话不存在'}), 404

    if request.method == 'GET':
        sc = get_session_scope(session_id)
        return jsonify({
            'scope_type': sc['scope_type'],
            'targets': resolve_scope(sc['targets']),
            'status': row['status'],
        })

    if row['status'] == 'running':
        return jsonify({'error': '会话执行中，禁止修改范围'}), 409
    data = request.get_json() or {}
    scope = data.get('scope')
    if not isinstance(scope, list):
        return jsonify({'error': 'scope 必须是列表'}), 400
    set_session_scope(session_id, 'scope', scope)
    return jsonify({'message': '范围已更新', 'scope': resolve_scope(scope)})


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
    conn.execute("DELETE FROM agent_plans WHERE session_id=?", (session_id,))
    conn.execute("DELETE FROM agent_sessions WHERE id=?", (session_id,))
    conn.commit()

    add_operation_log('Agent', '删除会话', session_id)

    return jsonify({'message': '删除成功'})


# ==================== Agent会话范围（v4.0 多节点批量） ====================

@agent_bp.route('/api/agent/scope/resolve', methods=['POST'])
def scope_resolve():
    """批量解析拓扑节点 → 连接的可用状态（范围面板渲染 ✅/⚠️ + 混型警示）

    body: {"targets": [{"type":"ssh"|"db", "topo_id":...|"conn_id":..., "name":...}]}
    resp: {"nodes":[...resolve_target...], "db_types":[...], "mixed": bool}
    """
    from agent.scope import resolve_scope, scope_db_types

    data = request.get_json() or {}
    targets = data.get('targets') or []
    nodes = resolve_scope(targets)
    types = scope_db_types(nodes)
    return jsonify({
        'nodes': nodes,
        'db_types': types['db_types'],
        'mixed': types['mixed'],
    })


# ==================== Agent执行（核心）====================

@agent_bp.route('/api/agent/run', methods=['POST'])
def run_agent():
    """启动Agent任务（SSE流式）"""
    data = request.get_json()

    session_id = data.get('session_id')
    question = data.get('question')
    model_id = data.get('model_id')
    skill_name = data.get('skill_name')  # 可选：手动指定技能（v4.0）
    disable_memory = bool(data.get('disable_memory', False))  # v4.2.1 会话级关闭长期记忆召回
    plan_mode = bool(data.get('plan_mode', False))  # v4.4 plan 模式：先给整体方案再执行

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

    # v4.0：会话范围（多节点批量）。请求显式 scope 优先，否则从会话读取。
    from db.database import get_session_scope
    scope = data.get('scope')
    if scope is None:
        scope = get_session_scope(session_id).get('targets', [])

    # 会话标题自动命名：默认「新会话」用首问句替换，便于会话列表区分
    if not row['title'] or row['title'].strip() in ('', '新会话'):
        new_title = ' '.join(question.split())[:24].strip() or '新会话'
        conn.execute(
            "UPDATE agent_sessions SET title=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
            (new_title, session_id))
        conn.commit()

    def generate():
        """生成SSE流"""
        agent = SmartOpsAgent(
            session_id=session_id,
            ssh_conn_id=ssh_conn_id,
            db_conn_id=db_conn_id,
            scope=scope,
            manual_skill_name=skill_name,
            model_id=model_id,
            disable_memory=disable_memory,
            plan_mode=plan_mode
        )

        try:
            for event in agent.run_stream(question):
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)}, ensure_ascii=False)}\n\n"

        yield "data: [DONE]\n\n"

    return Response(generate(), mimetype='text/event-stream')


@agent_bp.route('/api/agent/sessions/<session_id>/stop', methods=['POST'])
def stop_session(session_id):
    """请求停止 Agent 执行：写进程内取消标志，引擎在下一轮循环收敛并置 cancelled。"""
    from agent.engine import request_cancel
    request_cancel(session_id)
    add_operation_log('Agent', '停止执行', session_id)
    return jsonify({'message': '已请求停止'})


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


@agent_bp.route('/api/agent/skills', methods=['POST'])
def create_skill():
    """新增/更新技能（自动沉淀技能库的人工维护：编辑/停用）"""
    data = request.get_json() or {}
    name = (data.get('name') or '').strip()
    if not name:
        return jsonify({'error': '技能名不能为空'}), 400

    from db.database import save_skill
    skill_id = save_skill(
        name=name,
        db_type=data.get('db_type'),
        category=data.get('category') or 'diagnosis',
        description=data.get('description', ''),
        prompt_template=data.get('prompt_template', ''),
        required_tools=data.get('required_tools'),
        knowledge_tags=data.get('knowledge_tags'),
        trigger_keywords=data.get('trigger_keywords'),
        source_session=data.get('source_session', ''),
        confidence=data.get('confidence', 0.8),
        status=data.get('status', 'active'),
        priority=data.get('priority', 0),
    )
    add_operation_log('Agent', '保存技能', name)
    return jsonify({'message': '保存成功', 'id': skill_id})


@agent_bp.route('/api/agent/skills/from-doc', methods=['POST'])
def create_skill_from_doc():
    """上传操作手册 → 生成技能（LLM 提炼 / 离线回退）。

    两种输入：
    - multipart `file`（上传文档）
    - `filename` 表单字段（读取 data/manuals/ 下已有手册）
    可选表单字段：db_type / category / model_id
    """
    import os
    import tempfile
    from utils import extract_content, allowed_file, safe_join
    from agent.skills import SkillManager

    file = request.files.get('file')
    filename = (request.form.get('filename') or '').strip()
    db_type = (request.form.get('db_type') or '').strip() or None
    category = (request.form.get('category') or 'diagnosis').strip()
    model_id = request.form.get('model_id') or None

    text = None
    temp_path = None
    try:
        if file and file.filename:
            if not allowed_file(file.filename):
                return jsonify({'error': '不支持的文件类型'}), 400
            suffix = os.path.splitext(file.filename)[1]
            with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
                file.save(f.name)
                temp_path = f.name
            text = extract_content(temp_path)
        elif filename:
            from config import MANUALS_DIR
            filepath = safe_join(MANUALS_DIR, filename)
            if not filepath or not os.path.isfile(filepath):
                return jsonify({'error': '手册文件不存在'}), 404
            text = extract_content(filepath)
        else:
            return jsonify({'error': '请上传文件或指定手册文件名'}), 400
    except Exception as e:
        return jsonify({'error': f'文件解析失败: {e}'}), 400
    finally:
        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except OSError:
                pass

    if not text or not text.strip():
        return jsonify({'error': '未能从文件中提取文本内容'}), 400

    skill_name = SkillManager().crystallize_from_document(
        text, db_type=db_type, category=category, model_id=model_id)
    if not skill_name:
        return jsonify({'error': '技能生成失败（LLM 不可用且无法回退）'}), 500

    add_operation_log('Agent', '文档生成技能', skill_name)
    return jsonify({'message': '技能生成成功', 'skill_name': skill_name})


@agent_bp.route('/api/agent/skills/<skill_name>', methods=['DELETE'])
def remove_skill(skill_name):
    """删除技能（自动沉淀技能库维护）"""
    from db.database import delete_skill
    delete_skill(skill_name)
    add_operation_log('Agent', '删除技能', skill_name)
    return jsonify({'message': '删除成功'})


# ==================== 长期记忆管理 ====================

@agent_bp.route('/api/agent/memory', methods=['GET'])
def list_memory_records():
    """长期记忆列表（支持 keyword/entity_type 过滤）"""
    keyword = request.args.get('keyword')
    entity_type = request.args.get('entity_type')
    from db.database import search_memory_by_keyword, list_memory

    if keyword:
        records = search_memory_by_keyword(keyword, limit=50)
    else:
        records = list_memory(entity_type=entity_type or None, limit=100)

    return jsonify({'memory': records, 'count': len(records)})


@agent_bp.route('/api/agent/memory', methods=['POST'])
def add_memory_record():
    """显式记录长期记忆（DBA 反馈/拓扑/偏好，高置信度）"""
    data = request.get_json() or {}
    fact = (data.get('fact') or '').strip()
    if not fact:
        return jsonify({'error': '记忆内容不能为空'}), 400

    from db.database import save_memory
    mem_id = save_memory(
        entity_type=data.get('entity_type') or 'general',
        entity_name=data.get('entity_name', ''),
        fact=fact,
        category=data.get('category', 'preference'),
        confidence=data.get('confidence', 0.9),
        source='dba_feedback',
    )
    add_operation_log('Agent', '记录记忆', fact[:50])
    return jsonify({'message': '记录成功', 'id': mem_id})


@agent_bp.route('/api/agent/memory/<int:memory_id>', methods=['DELETE'])
def delete_memory_record(memory_id):
    """删除一条长期记忆"""
    from db.database import delete_memory
    delete_memory(memory_id)
    add_operation_log('Agent', '删除记忆', str(memory_id))
    return jsonify({'message': '删除成功'})


# ==================== 操作计划审批 ====================

@agent_bp.route('/api/agent/approve', methods=['POST'])
def approve_plan():
    """审批操作计划（变更类）：approve 放行引擎执行，reject 拒绝，revise 附修改要求重出方案。"""
    data = request.get_json() or {}
    plan_id = data.get('plan_id')
    action = data.get('action')  # 'approve' | 'reject' | 'revise'
    comment = (data.get('comment') or '').strip()

    if not plan_id or action not in ('approve', 'reject', 'revise'):
        return jsonify({'error': '缺少plan_id或action'}), 400
    if action == 'revise' and not comment:
        return jsonify({'error': '修改并重新提供方案请附上希望调整的内容'}), 400

    from db.database import get_plan, update_plan_status
    plan = get_plan(plan_id)
    if not plan:
        return jsonify({'error': '计划不存在'}), 404
    if plan['status'] != 'pending':
        return jsonify({'error': f"计划已处理（{plan['status']}）"}), 400

    status = {'approve': 'approved', 'reject': 'rejected',
              'revise': 'revised'}.get(action)
    update_plan_status(plan_id, status, approved_by='dba', comment=comment)
    add_operation_log('Agent', '审批操作计划', f'{status} {plan.get("title", "")[:40]}')
    return jsonify({'message': '审批已提交', 'plan_id': plan_id, 'status': status})


# ==================== DBA 反馈闭环 ====================

@agent_bp.route('/api/agent/feedback', methods=['POST'])
def submit_feedback():
    """DBA 反馈闭环：评价该会话沉淀的技能/记忆，可附带纠正文本。

    - up   → 该会话技能 confidence+0.05、记忆 confidence+0.1
    - down → 该会话技能 deprecated、该会话记忆删除
    - correction 非空 → 存为高置信度偏好记忆（source=dba_feedback）
    """
    data = request.get_json() or {}
    session_id = data.get('session_id')
    feedback = data.get('feedback')  # 'up' | 'down'
    correction = (data.get('correction') or '').strip()

    if not session_id or feedback not in ('up', 'down'):
        return jsonify({'error': '缺少session_id或feedback'}), 400

    from db.database import (get_skills_by_source, save_skill,
                             list_memory_by_source, delete_memory, save_memory)

    source = f'agent_session:{session_id}'
    affected_skills = 0
    affected_memory = 0

    # 技能调整（只动该会话自己沉淀的技能）
    for skill in get_skills_by_source(session_id):
        conf = float(skill.get('confidence') or 0.8)
        if feedback == 'up':
            status, new_conf = 'active', min(conf + 0.05, 0.95)
        else:
            status, new_conf = 'deprecated', max(conf - 0.2, 0.1)
        save_skill(
            name=skill['name'],
            db_type=skill.get('db_type'),
            category=skill.get('category', 'diagnosis'),
            description=skill.get('description', ''),
            prompt_template=skill.get('prompt_template', ''),
            required_tools=skill.get('required_tools'),
            knowledge_tags=skill.get('knowledge_tags'),
            trigger_keywords=skill.get('trigger_keywords'),
            source_session=session_id,
            confidence=new_conf,
            status=status,
            priority=skill.get('priority', 0),
        )
        affected_skills += 1

    # 记忆调整（只动该会话自动写入的记忆）
    for mem in list_memory_by_source(source):
        if feedback == 'up':
            save_memory(
                entity_type=mem.get('entity_type', 'general'),
                entity_name=mem.get('entity_name', ''),
                fact=mem.get('fact', ''),
                category=mem.get('category', ''),
                confidence=min(float(mem.get('confidence') or 0.5) + 0.1, 0.95),
                source=source,
            )
        else:
            delete_memory(mem['id'])
        affected_memory += 1

    # 纠正文本 → 高置信度偏好记忆
    if correction:
        save_memory(
            entity_type='preference',
            entity_name='',
            fact=correction,
            category='feedback',
            confidence=0.9,
            source='dba_feedback',
        )

    add_operation_log('Agent', 'DBA反馈', f'{feedback} ({session_id})')
    return jsonify({
        'message': '反馈已记录',
        'affected_skills': affected_skills,
        'affected_memory': affected_memory,
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
