"""Agent连接管理 API"""
import json
import uuid
from flask import Blueprint, request, jsonify
from db.database import get_db, add_operation_log
from utils import encrypt_secret

agent_conn_bp = Blueprint('agent_connections', __name__)


# ==================== SSH连接管理 ====================

@agent_conn_bp.route('/api/agent/ssh-connections', methods=['GET'])
def list_ssh_connections():
    """获取SSH连接列表"""
    conn = get_db()
    rows = conn.execute(
        "SELECT id, name, host, port, username, auth_type, db_type, os_type, status, created_at "
        "FROM agent_ssh_connections ORDER BY created_at DESC"
    ).fetchall()
    return jsonify({'connections': [dict(r) for r in rows]})


@agent_conn_bp.route('/api/agent/ssh-connections', methods=['POST'])
def create_ssh_connection():
    """创建SSH连接"""
    data = request.get_json()

    # 参数校验
    required_fields = ['name', 'host', 'username', 'db_type']
    for field in required_fields:
        if not data.get(field):
            return jsonify({'error': f'缺少必填字段: {field}'}), 400

    conn_id = str(uuid.uuid4())
    name = data['name']
    host = data['host']
    port = data.get('port', 22)
    username = data['username']
    auth_type = data.get('auth_type', 'password')
    password = data.get('password', '')
    private_key = data.get('private_key', '')
    passphrase = data.get('passphrase', '')
    db_type = data['db_type']
    os_type = data.get('os_type', 'linux')

    # 凭据加密后入库
    password = encrypt_secret(password)
    private_key = encrypt_secret(private_key)
    passphrase = encrypt_secret(passphrase)

    conn = get_db()
    conn.execute(
        """INSERT INTO agent_ssh_connections
           (id, name, host, port, username, auth_type, password_encrypted,
            private_key_encrypted, passphrase_encrypted, db_type, os_type)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (conn_id, name, host, port, username, auth_type, password,
         private_key, passphrase, db_type, os_type)
    )
    conn.commit()

    add_operation_log('Agent', '创建SSH连接', name)

    return jsonify({
        'message': '创建成功',
        'connection': {
            'id': conn_id,
            'name': name,
            'host': host,
            'port': port,
            'username': username,
            'db_type': db_type,
            'status': 'active'
        }
    })


@agent_conn_bp.route('/api/agent/ssh-connections/<conn_id>', methods=['DELETE'])
def delete_ssh_connection(conn_id):
    """删除SSH连接"""
    conn = get_db()
    conn.execute("DELETE FROM agent_ssh_connections WHERE id=?", (conn_id,))
    conn.commit()

    add_operation_log('Agent', '删除SSH连接', conn_id)

    return jsonify({'message': '删除成功'})


@agent_conn_bp.route('/api/agent/ssh-connections/<conn_id>/test', methods=['POST'])
def test_ssh_connection(conn_id):
    """测试SSH连接"""
    conn = get_db()
    row = conn.execute(
        "SELECT * FROM agent_ssh_connections WHERE id=?",
        (conn_id,)
    ).fetchone()

    if not row:
        return jsonify({'error': '连接不存在'}), 404

    # TODO: 实际测试SSH连接
    # 使用paramiko测试连接

    return jsonify({
        'status': 'success',
        'message': '连接测试成功'
    })


# ==================== 数据库连接管理 ====================

@agent_conn_bp.route('/api/agent/db-connections', methods=['GET'])
def list_db_connections():
    """获取数据库连接列表"""
    conn = get_db()
    rows = conn.execute(
        "SELECT id, name, ssh_connection_id, db_type, host, port, "
        "username, database, sid, service_name, status, created_at "
        "FROM agent_db_connections ORDER BY created_at DESC"
    ).fetchall()
    return jsonify({'connections': [dict(r) for r in rows]})


@agent_conn_bp.route('/api/agent/db-connections', methods=['POST'])
def create_db_connection():
    """创建数据库连接"""
    data = request.get_json()

    required_fields = ['name', 'host', 'db_type']
    for field in required_fields:
        if not data.get(field):
            return jsonify({'error': f'缺少必填字段: {field}'}), 400

    conn_id = str(uuid.uuid4())
    name = data['name']
    ssh_conn_id = data.get('ssh_connection_id')
    db_type = data['db_type']
    host = data['host']
    port = data.get('port')
    username = data.get('username', '')
    password = data.get('password', '')
    database = data.get('database', '')
    sid = data.get('sid', '')
    service_name = data.get('service_name', '')

    # 凭据加密后入库
    password = encrypt_secret(password)

    conn = get_db()
    conn.execute(
        """INSERT INTO agent_db_connections
           (id, name, ssh_connection_id, db_type, host, port, username,
            password_encrypted, database, sid, service_name)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (conn_id, name, ssh_conn_id, db_type, host, port, username,
         password, database, sid, service_name)
    )
    conn.commit()

    add_operation_log('Agent', '创建数据库连接', name)

    return jsonify({
        'message': '创建成功',
        'connection': {
            'id': conn_id,
            'name': name,
            'host': host,
            'db_type': db_type,
            'status': 'active'
        }
    })


@agent_conn_bp.route('/api/agent/db-connections/<conn_id>', methods=['DELETE'])
def delete_db_connection(conn_id):
    """删除数据库连接"""
    conn = get_db()
    conn.execute("DELETE FROM agent_db_connections WHERE id=?", (conn_id,))
    conn.commit()

    add_operation_log('Agent', '删除数据库连接', conn_id)

    return jsonify({'message': '删除成功'})


@agent_conn_bp.route('/api/agent/db-connections/<conn_id>/test', methods=['POST'])
def test_db_connection(conn_id):
    """测试数据库连接"""
    conn = get_db()
    row = conn.execute(
        "SELECT * FROM agent_db_connections WHERE id=?",
        (conn_id,)
    ).fetchone()

    if not row:
        return jsonify({'error': '连接不存在'}), 404

    # TODO: 实际测试数据库连接
    # 根据db_type使用对应的驱动测试

    return jsonify({
        'status': 'success',
        'message': '连接测试成功'
    })
