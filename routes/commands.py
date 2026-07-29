# -*- coding: utf-8 -*-
"""常用命令库 API"""
import os
import json
from flask import Blueprint, request, jsonify

commands_bp = Blueprint('commands', __name__)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
COMMANDS_DIR = os.path.join(BASE_DIR, 'data', 'commands')


def _load_commands_file(db_type):
    filepath = os.path.join(COMMANDS_DIR, f"{db_type}.json")
    if os.path.exists(filepath):
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    return None


def _save_commands_file(db_type, data):
    os.makedirs(COMMANDS_DIR, exist_ok=True)
    filepath = os.path.join(COMMANDS_DIR, f"{db_type}.json")
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


@commands_bp.route('/api/commands', methods=['GET'])
def get_commands():
    db_type = request.args.get('db_type', '')

    saved = _load_commands_file(db_type)
    if saved:
        return jsonify(saved)

    default_commands = get_default_commands(db_type)
    return jsonify({'commands': default_commands})


@commands_bp.route('/api/commands', methods=['POST'])
def save_commands():
    data = request.get_json()
    db_type = data.get('db_type', '')
    commands = data.get('commands', [])

    if not db_type:
        return jsonify({'error': '请指定数据库类型'}), 400

    _save_commands_file(db_type, {'commands': commands})
    return jsonify({'message': '保存成功'})


@commands_bp.route('/api/commands/category', methods=['POST'])
def add_category():
    """添加命令分类"""
    data = request.get_json()
    db_type = data.get('db_type', '')
    category_name = data.get('category_name', '')

    if not db_type or not category_name:
        return jsonify({'error': '请填写完整信息'}), 400

    # 加载现有命令
    saved = _load_commands_file(db_type)
    if saved:
        commands = saved.get('commands', [])
    else:
        commands = get_default_commands(db_type)

    # 检查分类是否已存在
    for cat in commands:
        if cat.get('category') == category_name:
            return jsonify({'error': '该分类已存在'}), 400

    # 添加新分类
    commands.append({
        'category': category_name,
        'commands': []
    })

    _save_commands_file(db_type, {'commands': commands})
    return jsonify({'message': '分类添加成功', 'commands': commands})


@commands_bp.route('/api/commands/command', methods=['POST'])
def add_command():
    """添加命令"""
    data = request.get_json()
    db_type = data.get('db_type', '')
    category = data.get('category', '')
    name = data.get('name', '')
    cmd = data.get('cmd', '')
    desc = data.get('desc', '')

    if not db_type or not category or not name or not cmd:
        return jsonify({'error': '请填写完整信息'}), 400

    # 加载现有命令
    saved = _load_commands_file(db_type)
    if saved:
        commands = saved.get('commands', [])
    else:
        commands = get_default_commands(db_type)

    # 查找分类
    target_category = None
    for cat in commands:
        if cat.get('category') == category:
            target_category = cat
            break

    if not target_category:
        return jsonify({'error': '分类不存在'}), 400

    # 添加命令
    target_category['commands'].append({
        'name': name,
        'cmd': cmd,
        'desc': desc
    })

    _save_commands_file(db_type, {'commands': commands})
    return jsonify({'message': '命令添加成功', 'commands': commands})


@commands_bp.route('/api/commands/command', methods=['DELETE'])
def delete_command():
    """删除命令"""
    data = request.get_json()
    db_type = data.get('db_type', '')
    category = data.get('category', '')
    index = data.get('index', -1)

    if not db_type or not category or index < 0:
        return jsonify({'error': '请指定数据库类型、分类和命令索引'}), 400

    # 加载现有命令
    saved = _load_commands_file(db_type)
    if saved:
        commands = saved.get('commands', [])
    else:
        commands = get_default_commands(db_type)

    # 查找分类
    target_category = None
    for cat in commands:
        if cat.get('category') == category:
            target_category = cat
            break

    if not target_category:
        return jsonify({'error': '分类不存在'}), 400

    # 删除命令
    cmds = target_category.get('commands', [])
    if index >= len(cmds):
        return jsonify({'error': '命令索引超出范围'}), 400

    cmds.pop(index)

    _save_commands_file(db_type, {'commands': commands})
    return jsonify({'message': '删除成功', 'commands': commands})


def get_default_commands(db_type):
    """获取默认命令模板"""
    defaults = {
        'mysql': [
            {'category': '连接管理', 'commands': [
                {'name': '连接数据库', 'cmd': 'mysql -u root -p -h host', 'desc': '连接MySQL数据库'},
                {'name': '查看连接', 'cmd': 'SHOW PROCESSLIST;', 'desc': '查看当前连接'},
                {'name': '杀死连接', 'cmd': 'KILL id;', 'desc': '终止指定连接'},
                {'name': '查看版本', 'cmd': 'SELECT VERSION();', 'desc': '查看MySQL版本'}
            ]},
            {'category': '库表操作', 'commands': [
                {'name': '查看数据库', 'cmd': 'SHOW DATABASES;', 'desc': '列出所有数据库'},
                {'name': '查看表', 'cmd': 'SHOW TABLES;', 'desc': '列出当前库所有表'},
                {'name': '查看表结构', 'cmd': 'DESC table_name;', 'desc': '查看表结构'},
                {'name': '查看建表语句', 'cmd': 'SHOW CREATE TABLE table_name;', 'desc': '查看建表SQL'},
                {'name': '查看表大小', 'cmd': "SELECT table_name, round(data_length/1024/1024,2) as '数据(MB)', round(index_length/1024/1024,2) as '索引(MB)' FROM information_schema.tables WHERE table_schema='dbname';", 'desc': '查看表大小'}
            ]},
            {'category': '性能诊断', 'commands': [
                {'name': '查看状态', 'cmd': 'SHOW STATUS;', 'desc': '查看服务器状态'},
                {'name': '查看变量', 'cmd': 'SHOW VARIABLES;', 'desc': '查看系统变量'},
                {'name': '查看慢查询', 'cmd': 'SHOW VARIABLES LIKE "slow_query_log";', 'desc': '查看慢查询配置'},
                {'name': '执行计划', 'cmd': 'EXPLAIN SELECT ...;', 'desc': '查看SQL执行计划'},
                {'name': '查看锁等待', 'cmd': 'SELECT * FROM information_schema.innodb_lock_waits;', 'desc': '查看锁等待'},
                {'name': '查看死锁', 'cmd': 'SHOW ENGINE INNODB STATUS;', 'desc': '查看InnoDB状态'}
            ]},
            {'category': '备份恢复', 'commands': [
                {'name': '逻辑备份', 'cmd': 'mysqldump -u root -p dbname > backup.sql', 'desc': '备份单个数据库'},
                {'name': '逻辑恢复', 'cmd': 'mysql -u root -p dbname < backup.sql', 'desc': '恢复数据库'},
                {'name': '表备份', 'cmd': 'mysqldump -u root -p dbname table_name > table.sql', 'desc': '备份单表'},
                {'name': '全库备份', 'cmd': 'mysqldump -u root -p --all-databases > all.sql', 'desc': '备份所有数据库'}
            ]},
            {'category': '用户权限', 'commands': [
                {'name': '创建用户', 'cmd': "CREATE USER 'user'@'host' IDENTIFIED BY 'password';", 'desc': '创建用户'},
                {'name': '授权', 'cmd': "GRANT ALL PRIVILEGES ON dbname.* TO 'user'@'host';", 'desc': '授权用户'},
                {'name': '刷新权限', 'cmd': 'FLUSH PRIVILEGES;', 'desc': '刷新权限'},
                {'name': '查看用户', 'cmd': "SELECT user,host FROM mysql.user;", 'desc': '查看所有用户'}
            ]}
        ],
        'oracle': [
            {'category': '连接管理', 'commands': [
                {'name': 'SQL*Plus连接', 'cmd': 'sqlplus username/password@host:port/service', 'desc': '连接Oracle'},
                {'name': '查看会话', 'cmd': "SELECT sid,serial#,username,status FROM v$session WHERE type='USER';", 'desc': '查看用户会话'},
                {'name': '杀死会话', 'cmd': "ALTER SYSTEM KILL SESSION 'sid,serial#' IMMEDIATE;", 'desc': '终止会话'},
                {'name': '查看版本', 'cmd': 'SELECT * FROM v$version;', 'desc': '查看Oracle版本'}
            ]},
            {'category': '表空间管理', 'commands': [
                {'name': '查看表空间', 'cmd': 'SELECT tablespace_name,status FROM dba_tablespaces;', 'desc': '查看所有表空间'},
                {'name': '查看数据文件', 'cmd': 'SELECT file_name,tablespace_name,bytes/1024/1024 as MB FROM dba_data_files;', 'desc': '查看数据文件'},
                {'name': '创建表空间', 'cmd': "CREATE TABLESPACE ts_name DATAFILE '/path/file.dbf' SIZE 100M AUTOEXTEND ON;", 'desc': '创建表空间'},
                {'name': '查看使用率', 'cmd': "SELECT tablespace_name, round((used_space/tablespace_size)*100,2) as used_pct FROM dba_tablespace_usage_metrics;", 'desc': '查看表空间使用率'}
            ]},
            {'category': '性能诊断', 'commands': [
                {'name': '查看等待事件', 'cmd': 'SELECT event,count(*) FROM v$session_wait GROUP BY event ORDER BY count(*) DESC;', 'desc': '查看等待事件'},
                {'name': '查看执行计划', 'cmd': 'EXPLAIN PLAN FOR SELECT ...;', 'desc': '生成执行计划'},
                {'name': '查看AWR报告', 'cmd': '@?/rdbms/admin/awrrpt.sql', 'desc': '生成AWR报告'},
                {'name': '查看慢SQL', 'cmd': 'SELECT sql_id,elapsed_time,sql_text FROM v$sql ORDER BY elapsed_time DESC FETCH FIRST 10 ROWS ONLY;', 'desc': '查看慢SQL'}
            ]},
            {'category': '备份恢复', 'commands': [
                {'name': 'RMAN备份', 'cmd': 'rman target / \nBACKUP DATABASE;', 'desc': 'RMAN全库备份'},
                {'name': '导出数据', 'cmd': 'expdp username/password directory=dir dumpfile=exp.dmp logfile=exp.log', 'desc': '数据泵导出'},
                {'name': '导入数据', 'cmd': 'impdp username/password directory=dir dumpfile=exp.dmp logfile=imp.log', 'desc': '数据泵导入'}
            ]}
        ],
        'dm': [
            {'category': '连接管理', 'commands': [
                {'name': 'disql连接', 'cmd': 'disql username/password@host:port', 'desc': '连接达梦数据库'},
                {'name': '查看连接', 'cmd': 'SELECT * FROM V$SESSIONS;', 'desc': '查看当前会话'},
                {'name': '杀死会话', 'cmd': 'SP_CLOSE_SESSION(session_id);', 'desc': '终止会话'},
                {'name': '查看版本', 'cmd': 'SELECT * FROM V$VERSION;', 'desc': '查看版本'}
            ]},
            {'category': '表空间管理', 'commands': [
                {'name': '查看表空间', 'cmd': 'SELECT * FROM V$TABLESPACE;', 'desc': '查看表空间'},
                {'name': '查看数据文件', 'cmd': 'SELECT * FROM V$DATAFILE;', 'desc': '查看数据文件'},
                {'name': '创建表空间', 'cmd': "CREATE TABLESPACE ts_name DATAFILE '/path/file.dbf' SIZE 100;", 'desc': '创建表空间'}
            ]},
            {'category': '备份恢复', 'commands': [
                {'name': '逻辑备份', 'cmd': 'dexp username/password file=backup.dmp log=backup.log', 'desc': '逻辑导出'},
                {'name': '逻辑恢复', 'cmd': 'dimp username/password file=backup.dmp log=restore.log', 'desc': '逻辑导入'},
                {'name': '物理备份', 'cmd': "backup database backupset '/bak/full';", 'desc': '物理备份'}
            ]},
            {'category': '性能诊断', 'commands': [
                {'name': '查看慢SQL', 'cmd': 'SELECT * FROM V$LONG_EXEC_SQLS;', 'desc': '查看慢SQL'},
                {'name': '执行计划', 'cmd': 'EXPLAIN SELECT ...;', 'desc': '查看执行计划'},
                {'name': '查看锁', 'cmd': 'SELECT * FROM V$LOCK WHERE BLOCKED=1;', 'desc': '查看锁信息'}
            ]}
        ],
        'oceanbase': [
            {'category': '连接管理', 'commands': [
                {'name': '连接OB', 'cmd': 'obclient -u user@tenant -h host -P port -p', 'desc': '连接OceanBase'},
                {'name': '查看连接', 'cmd': 'SHOW PROCESSLIST;', 'desc': '查看连接列表'},
                {'name': '查看版本', 'cmd': 'SELECT version();', 'desc': '查看版本'}
            ]},
            {'category': '集群管理', 'commands': [
                {'name': '查看集群', 'cmd': 'SELECT * FROM oceanbase.DBA_OB_SERVERS;', 'desc': '查看集群节点'},
                {'name': '查看租户', 'cmd': 'SELECT * FROM oceanbase.DBA_OB_TENANTS;', 'desc': '查看租户列表'},
                {'name': '查看资源池', 'cmd': 'SELECT * FROM oceanbase.DBA_OB_RESOURCE_POOLS;', 'desc': '查看资源池'},
                {'name': '查看Unit', 'cmd': 'SELECT * FROM oceanbase.DBA_OB_UNIT_CONFIGS;', 'desc': '查看Unit配置'}
            ]},
            {'category': '性能诊断', 'commands': [
                {'name': '慢查询', 'cmd': 'SELECT * FROM oceanbase.GV$OB_SQL_AUDIT WHERE elapsed_time > 1000000;', 'desc': '查看慢SQL'},
                {'name': '执行计划', 'cmd': 'EXPLAIN SELECT ...;', 'desc': '查看执行计划'},
                {'name': '查看等待事件', 'cmd': 'SELECT * FROM oceanbase.GV$OB_SESSION_WAIT;', 'desc': '查看等待事件'}
            ]}
        ],
        'goldendb': [
            {'category': '连接管理', 'commands': [
                {'name': '连接GoldenDB', 'cmd': 'mysql -u user -p -h host -P port', 'desc': '连接GoldenDB（MySQL协议）'},
                {'name': '查看节点', 'cmd': 'SHOW NODES;', 'desc': '查看集群节点'}
            ]},
            {'category': '分片管理', 'commands': [
                {'name': '查看分片', 'cmd': 'SHOW SHARDS;', 'desc': '查看分片信息'},
                {'name': '查看分片表', 'cmd': "SELECT * FROM information_schema.tables WHERE table_type='SHARDED';", 'desc': '查看分片表'}
            ]}
        ],
        'tdsql': [
            {'category': '连接管理', 'commands': [
                {'name': '连接TDSQL', 'cmd': 'mysql -u user -p -h host -P port', 'desc': '连接TDSQL（MySQL协议）'},
                {'name': '查看分布式信息', 'cmd': 'SHOW DISTRIBUTION;', 'desc': '查看分布式信息'}
            ]},
            {'category': '分片管理', 'commands': [
                {'name': '查看分片', 'cmd': 'SHOW SHARDING;', 'desc': '查看分片配置'},
                {'name': '查看Set', 'cmd': 'SHOW SETS;', 'desc': '查看Set信息'}
            ]}
        ],
        'gaussdb': [
            {'category': '连接管理', 'commands': [
                {'name': '连接GaussDB', 'cmd': 'gsql -U user -h host -p port -d dbname', 'desc': '连接GaussDB'},
                {'name': '查看连接', 'cmd': 'SELECT * FROM pg_stat_activity;', 'desc': '查看当前连接'},
                {'name': '杀死连接', 'cmd': 'SELECT pg_terminate_backend(pid);', 'desc': '终止连接'}
            ]},
            {'category': '集群管理', 'commands': [
                {'name': '查看节点', 'cmd': 'SELECT * FROM pg_stat_replication;', 'desc': '查看复制节点'},
                {'name': '查看CN', 'cmd': "SELECT * FROM pgxc_node WHERE node_type='C';", 'desc': '查看CN节点'},
                {'name': '查看DN', 'cmd': "SELECT * FROM pgxc_node WHERE node_type='D';", 'desc': '查看DN节点'}
            ]},
            {'category': '性能诊断', 'commands': [
                {'name': '执行计划', 'cmd': 'EXPLAIN ANALYZE SELECT ...;', 'desc': '查看执行计划'},
                {'name': '慢查询', 'cmd': 'SELECT * FROM pg_stat_statements ORDER BY total_time DESC LIMIT 10;', 'desc': '查看慢SQL'},
                {'name': '表膨胀', 'cmd': "SELECT schemaname,tablename,n_dead_tup FROM pg_stat_user_tables ORDER BY n_dead_tup DESC;", 'desc': '查看表膨胀'}
            ]}
        ]
    }

    return defaults.get(db_type, [
        {'category': '常用命令', 'commands': [
            {'name': '示例命令', 'cmd': 'command example', 'desc': '命令说明，请自行添加'}
        ]}
    ])


@commands_bp.route('/api/commands/search', methods=['GET'])
def search_commands():
    """跨库搜索命令"""
    from db.database import get_db_types

    keyword = request.args.get('keyword', '').lower()
    if not keyword:
        return jsonify({'results': []})

    results = []
    db_types = get_db_types()

    for db_type in db_types:
        commands = get_default_commands(db_type['id'])
        for category in commands:
            for cmd in category.get('commands', []):
                if (keyword in cmd['name'].lower() or
                    keyword in cmd['cmd'].lower() or
                    keyword in cmd['desc'].lower()):
                    results.append({
                        'db_type': db_type['id'],
                        'db_name': db_type['name'],
                        'category': category['category'],
                        **cmd
                    })

    return jsonify({'results': results})
