# -*- coding: utf-8 -*-
"""
SQLite 数据库管理层
"""
import os
import sqlite3
import threading
import json

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, 'data')
DB_PATH = os.environ.get('DB_TOOL_TEST_DB') or os.path.join(DATA_DIR, 'db_tool.db')

_local = threading.local()


def get_db():
    """获取当前线程的数据库连接（线程安全）"""
    if not hasattr(_local, 'conn') or _local.conn is None:
        os.makedirs(DATA_DIR, exist_ok=True)
        _local.conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        _local.conn.row_factory = sqlite3.Row
        _local.conn.execute("PRAGMA journal_mode=WAL")
        _local.conn.execute("PRAGMA foreign_keys=ON")
        _local.conn.execute("PRAGMA busy_timeout=5000")  # 等待锁释放最多5秒
    return _local.conn


def close_db(exception=None):
    """关闭当前请求的数据库连接"""
    conn = getattr(_local, 'conn', None)
    if conn is not None:
        try:
            conn.close()
        except sqlite3.Error:
            pass
        finally:
            _local.conn = None


# ==================== 事务上下文管理器 ====================

class transaction:
    """显式事务上下文管理器，支持自动提交和回滚"""

    def __init__(self):
        self.conn = None

    def __enter__(self):
        self.conn = get_db()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None:
            self.conn.rollback()
        else:
            self.conn.commit()
        return False  # 不吞掉异常

    def execute(self, sql, parameters=()):
        """执行SQL语句"""
        return self.conn.execute(sql, parameters)

    def executemany(self, sql, parameters):
        """批量执行SQL语句"""
        return self.conn.executemany(sql, parameters)

    def fetchone(self, sql, parameters=()):
        """执行查询并返回单行"""
        return self.conn.execute(sql, parameters).fetchone()

    def fetchall(self, sql, parameters=()):
        """执行查询并返回所有行"""
        return self.conn.execute(sql, parameters).fetchall()


def init_db():
    """初始化数据库表结构"""
    conn = get_db()
    conn.executescript('''
        CREATE TABLE IF NOT EXISTS config (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS db_types (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            icon TEXT DEFAULT '📁'
        );

        CREATE TABLE IF NOT EXISTS knowledge_files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            db_type TEXT NOT NULL,
            filename TEXT NOT NULL,
            file_path TEXT NOT NULL,
            file_size INTEGER,
            content_text TEXT,
            tags TEXT DEFAULT '[]',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(db_type, filename)
        );

        CREATE TABLE IF NOT EXISTS qa_conversations (
            id TEXT PRIMARY KEY,
            title TEXT,
            db_type TEXT,
            model_id TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        -- 消息表（支持多轮对话）
        CREATE TABLE IF NOT EXISTS qa_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            conversation_id TEXT NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('user', 'assistant', 'system')),
            content TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (conversation_id) REFERENCES qa_conversations(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_qa_messages_conversation ON qa_messages(conversation_id);

        CREATE TABLE IF NOT EXISTS favorites (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            db_type TEXT NOT NULL,
            filename TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(db_type, filename)
        );

        CREATE TABLE IF NOT EXISTS resource_pools (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            db_type TEXT,
            environment TEXT DEFAULT 'production',
            description TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        -- 集群表（属于某个资源池）
        CREATE TABLE IF NOT EXISTS clusters (
            id TEXT PRIMARY KEY,
            resource_pool_id TEXT NOT NULL,
            name TEXT NOT NULL,
            description TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (resource_pool_id) REFERENCES resource_pools(id) ON DELETE CASCADE
        );

        -- 物理机表
        CREATE TABLE IF NOT EXISTS servers (
            id TEXT PRIMARY KEY,
            resource_pool_id TEXT NOT NULL,
            cluster_id TEXT DEFAULT '',
            name TEXT NOT NULL,
            host TEXT,
            datacenter TEXT DEFAULT '',
            node_role TEXT DEFAULT '计算节点',
            hardware_type TEXT DEFAULT '非信创物理机',
            cpu TEXT,
            memory TEXT,
            description TEXT,
            FOREIGN KEY (resource_pool_id) REFERENCES resource_pools(id) ON DELETE CASCADE
        );

        -- 实例表
        CREATE TABLE IF NOT EXISTS instances (
            id TEXT PRIMARY KEY,
            server_id TEXT NOT NULL,
            tenant_id TEXT,
            name TEXT NOT NULL,
            port TEXT DEFAULT '3306',
            cpu TEXT,
            memory TEXT,
            role TEXT DEFAULT 'slave',
            tenant_role TEXT DEFAULT 'slave',
            description TEXT,
            FOREIGN KEY (server_id) REFERENCES servers(id) ON DELETE CASCADE,
            FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE SET NULL
        );

        -- 租户（实例集群）表
        CREATE TABLE IF NOT EXISTS tenants (
            id TEXT PRIMARY KEY,
            resource_pool_id TEXT NOT NULL,
            cluster_id TEXT DEFAULT '',
            name TEXT NOT NULL,
            topology_type TEXT DEFAULT 'master-slave',
            spec TEXT DEFAULT 'small-8c32g',
            description TEXT,
            FOREIGN KEY (resource_pool_id) REFERENCES resource_pools(id) ON DELETE CASCADE
        );

        -- 实例之间的关系表（主从关系）
        CREATE TABLE IF NOT EXISTS instance_relations (
            from_instance_id TEXT NOT NULL,
            to_instance_id TEXT NOT NULL,
            relation_type TEXT DEFAULT 'replication',
            PRIMARY KEY (from_instance_id, to_instance_id),
            FOREIGN KEY (from_instance_id) REFERENCES instances(id) ON DELETE CASCADE,
            FOREIGN KEY (to_instance_id) REFERENCES instances(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS embeddings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_id INTEGER,
            chunk_index INTEGER,
            chunk_text TEXT,
            embedding BLOB,
            FOREIGN KEY (file_id) REFERENCES knowledge_files(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_knowledge_files_db_type ON knowledge_files(db_type);
        CREATE INDEX IF NOT EXISTS idx_knowledge_files_db_type_created ON knowledge_files(db_type, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_qa_messages_conversation ON qa_messages(conversation_id);
        CREATE INDEX IF NOT EXISTS idx_servers_cluster ON servers(cluster_id);
        CREATE INDEX IF NOT EXISTS idx_instances_server ON instances(server_id);
        CREATE INDEX IF NOT EXISTS idx_tenants_cluster ON tenants(cluster_id);
        CREATE INDEX IF NOT EXISTS idx_embeddings_file ON embeddings(file_id);

        -- ==================== Agent模块数据表 ====================

        -- SSH连接配置（目标服务器）
        CREATE TABLE IF NOT EXISTS agent_ssh_connections (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            host TEXT NOT NULL,
            port INTEGER DEFAULT 22,
            username TEXT NOT NULL,
            auth_type TEXT DEFAULT 'password',
            password_encrypted TEXT,
            private_key_encrypted TEXT,
            passphrase_encrypted TEXT,
            db_type TEXT NOT NULL,
            os_type TEXT DEFAULT 'linux',
            status TEXT DEFAULT 'active',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        -- 数据库连接配置（用于SQL查询）
        CREATE TABLE IF NOT EXISTS agent_db_connections (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            ssh_connection_id TEXT,
            db_type TEXT NOT NULL,
            host TEXT NOT NULL,
            port INTEGER,
            username TEXT,
            password_encrypted TEXT,
            database TEXT,
            sid TEXT,
            service_name TEXT,
            status TEXT DEFAULT 'active',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (ssh_connection_id) REFERENCES agent_ssh_connections(id)
        );

        -- Agent会话
        CREATE TABLE IF NOT EXISTS agent_sessions (
            id TEXT PRIMARY KEY,
            title TEXT DEFAULT '新会话',
            ssh_connection_id TEXT,
            db_connection_id TEXT,
            status TEXT DEFAULT 'idle',
            current_step INTEGER DEFAULT 0,
            max_steps INTEGER DEFAULT 10,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        -- Agent执行步骤（ReAct过程记录）
        CREATE TABLE IF NOT EXISTS agent_steps (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            step_number INTEGER NOT NULL,
            phase TEXT NOT NULL,
            thought TEXT,
            action TEXT,
            observation TEXT,
            knowledge_refs TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (session_id) REFERENCES agent_sessions(id)
        );

        -- Agent Skills（操作指南/领域知识）
        CREATE TABLE IF NOT EXISTS agent_skills (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            db_type TEXT,
            category TEXT NOT NULL,
            description TEXT NOT NULL,
            prompt_template TEXT,
            required_tools TEXT,
            knowledge_tags TEXT,
            priority INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_agent_steps_session ON agent_steps(session_id);
        CREATE INDEX IF NOT EXISTS idx_agent_skills_db_type ON agent_skills(db_type);
        CREATE INDEX IF NOT EXISTS idx_agent_skills_category ON agent_skills(category);

        -- ==================== 操作日志 ====================

        CREATE TABLE IF NOT EXISTS operation_logs (
            id TEXT PRIMARY KEY,
            timestamp TEXT NOT NULL,
            module TEXT NOT NULL,
            action TEXT NOT NULL,
            detail TEXT DEFAULT '',
            status TEXT DEFAULT 'success',
            ip TEXT DEFAULT ''
        );
        CREATE INDEX IF NOT EXISTS idx_operation_logs_timestamp ON operation_logs(timestamp DESC);
        CREATE INDEX IF NOT EXISTS idx_operation_logs_module ON operation_logs(module);

        -- 日志分析任务表
        CREATE TABLE IF NOT EXISTS log_analysis_tasks (
            id TEXT PRIMARY KEY,
            name TEXT,
            question TEXT,
            db_type TEXT DEFAULT '',
            status TEXT DEFAULT 'pending',
            current_stage TEXT DEFAULT '',
            stages TEXT DEFAULT '{}',
            report TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            completed_at TIMESTAMP
        );

        -- 日志分析文件表
        CREATE TABLE IF NOT EXISTS log_analysis_files (
            id TEXT PRIMARY KEY,
            task_id TEXT NOT NULL,
            filename TEXT NOT NULL,
            file_path TEXT NOT NULL,
            file_size INTEGER,
            content_text TEXT,
            is_key_log BOOLEAN DEFAULT 0,
            FOREIGN KEY (task_id) REFERENCES log_analysis_tasks(id) ON DELETE CASCADE
        );

        -- ==================== 知识图谱表 ====================

        -- 实体表
        CREATE TABLE IF NOT EXISTS kg_entities (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            entity_type TEXT NOT NULL,
            name TEXT NOT NULL,
            normalized_name TEXT NOT NULL,
            aliases TEXT DEFAULT '[]',
            description TEXT,
            properties TEXT DEFAULT '{}',
            source_file_id INTEGER,
            source_chunk_id INTEGER,
            confidence REAL DEFAULT 1.0,
            extract_method TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(normalized_name, entity_type)
        );

        -- 关系表
        CREATE TABLE IF NOT EXISTS kg_relationships (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            from_entity_id INTEGER NOT NULL,
            to_entity_id INTEGER NOT NULL,
            relation_type TEXT NOT NULL,
            confidence REAL DEFAULT 1.0,
            properties TEXT DEFAULT '{}',
            source_chunk_id INTEGER,
            source_file_id INTEGER,
            extract_method TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (from_entity_id) REFERENCES kg_entities(id) ON DELETE CASCADE,
            FOREIGN KEY (to_entity_id) REFERENCES kg_entities(id) ON DELETE CASCADE
        );

        -- chunk-实体关联表（多对多）
        CREATE TABLE IF NOT EXISTS kg_chunk_entities (
            chunk_id INTEGER NOT NULL,
            entity_id INTEGER NOT NULL,
            mention_count INTEGER DEFAULT 1,
            PRIMARY KEY (chunk_id, entity_id),
            FOREIGN KEY (chunk_id) REFERENCES embeddings(id) ON DELETE CASCADE,
            FOREIGN KEY (entity_id) REFERENCES kg_entities(id) ON DELETE CASCADE
        );

        -- 知识图谱索引
        CREATE INDEX IF NOT EXISTS idx_kg_entities_type ON kg_entities(entity_type);
        CREATE INDEX IF NOT EXISTS idx_kg_entities_name ON kg_entities(normalized_name);
        CREATE INDEX IF NOT EXISTS idx_kg_rel_from ON kg_relationships(from_entity_id);
        CREATE INDEX IF NOT EXISTS idx_kg_rel_to ON kg_relationships(to_entity_id);
        CREATE INDEX IF NOT EXISTS idx_kg_rel_type ON kg_relationships(relation_type);
        CREATE INDEX IF NOT EXISTS idx_kg_chunk_e ON kg_chunk_entities(chunk_id);
        CREATE INDEX IF NOT EXISTS idx_kg_chunk_eid ON kg_chunk_entities(entity_id);
    ''')
    conn.commit()

    # 初始化功能配置表
    _init_feature_config(conn)

    # 数据库迁移：添加 datacenter 字段到 servers 表
    try:
        conn.execute("SELECT datacenter FROM servers LIMIT 1")
    except sqlite3.OperationalError:
        conn.execute("ALTER TABLE servers ADD COLUMN datacenter TEXT DEFAULT ''")
        conn.commit()

    # 数据库迁移：添加 cpu 和 memory 字段到 servers 表
    try:
        conn.execute("SELECT cpu FROM servers LIMIT 1")
    except sqlite3.OperationalError:
        conn.execute("ALTER TABLE servers ADD COLUMN cpu TEXT")
        conn.commit()

    try:
        conn.execute("SELECT memory FROM servers LIMIT 1")
    except sqlite3.OperationalError:
        conn.execute("ALTER TABLE servers ADD COLUMN memory TEXT")
        conn.commit()

    # 数据库迁移：添加 role 字段到 instances 表
    try:
        conn.execute("SELECT role FROM instances LIMIT 1")
    except sqlite3.OperationalError:
        conn.execute("ALTER TABLE instances ADD COLUMN role TEXT DEFAULT 'slave'")
        conn.commit()

    # 数据库迁移：添加 tenant_id 和 tenant_role 字段到 instances 表
    try:
        conn.execute("SELECT tenant_id FROM instances LIMIT 1")
    except sqlite3.OperationalError:
        conn.execute("ALTER TABLE instances ADD COLUMN tenant_id TEXT")
        conn.commit()

    try:
        conn.execute("SELECT tenant_role FROM instances LIMIT 1")
    except sqlite3.OperationalError:
        conn.execute("ALTER TABLE instances ADD COLUMN tenant_role TEXT DEFAULT 'slave'")
        conn.commit()

    # 数据库迁移：删除 tenant_instances 表（如果存在）
    try:
        conn.execute("SELECT 1 FROM tenant_instances LIMIT 1")
        # 如果表存在，迁移数据到 instances 表
        rows = conn.execute("SELECT tenant_id, instance_id, role FROM tenant_instances").fetchall()
        for row in rows:
            conn.execute(
                "UPDATE instances SET tenant_id=?, tenant_role=? WHERE id=?",
                (row['tenant_id'], row['role'], row['instance_id'])
            )
        conn.execute("DROP TABLE tenant_instances")
        conn.commit()
    except sqlite3.OperationalError:
        pass  # 表不存在，无需处理

    # 数据库迁移：添加 node_role 字段到 servers 表
    try:
        conn.execute("SELECT node_role FROM servers LIMIT 1")
    except sqlite3.OperationalError:
        conn.execute("ALTER TABLE servers ADD COLUMN node_role TEXT DEFAULT '计算节点'")
        conn.commit()

    # 数据库迁移：添加 hardware_type 字段到 servers 表
    try:
        conn.execute("SELECT hardware_type FROM servers LIMIT 1")
    except sqlite3.OperationalError:
        conn.execute("ALTER TABLE servers ADD COLUMN hardware_type TEXT DEFAULT '非信创物理机'")
        conn.commit()

    # 数据库迁移：添加 spec 字段到 tenants 表
    try:
        conn.execute("SELECT spec FROM tenants LIMIT 1")
    except sqlite3.OperationalError:
        conn.execute("ALTER TABLE tenants ADD COLUMN spec TEXT DEFAULT 'small-8c32g'")
        conn.commit()

    # 数据库迁移：将 clusters 表重命名为 resource_pools 表
    try:
        conn.execute("SELECT 1 FROM resource_pools LIMIT 1")
    except sqlite3.OperationalError:
        # resource_pools 表不存在，需要创建并迁移数据
        conn.execute('''
            CREATE TABLE resource_pools AS
            SELECT * FROM clusters
        ''')
        conn.execute('''
            CREATE UNIQUE INDEX idx_resource_pools_id ON resource_pools(id)
        ''')
        conn.commit()

    # 数据库迁移：为 servers 表添加 resource_pool_id 字段
    try:
        conn.execute("SELECT resource_pool_id FROM servers LIMIT 1")
    except sqlite3.OperationalError:
        conn.execute("ALTER TABLE servers ADD COLUMN resource_pool_id TEXT")
        # 将现有的 cluster_id 迁移到 resource_pool_id
        conn.execute('''
            UPDATE servers SET resource_pool_id = cluster_id
        ''')
        conn.commit()

    # 数据库迁移：为 tenants 表添加 resource_pool_id 字段
    try:
        conn.execute("SELECT resource_pool_id FROM tenants LIMIT 1")
    except sqlite3.OperationalError:
        conn.execute("ALTER TABLE tenants ADD COLUMN resource_pool_id TEXT")
        # 将现有的 cluster_id 迁移到 resource_pool_id
        conn.execute('''
            UPDATE tenants SET resource_pool_id = cluster_id
        ''')
        conn.commit()

    # 数据库迁移：为 log_analysis_tasks 表添加 db_type 字段
    try:
        conn.execute("SELECT db_type FROM log_analysis_tasks LIMIT 1")
    except sqlite3.OperationalError:
        conn.execute("ALTER TABLE log_analysis_tasks ADD COLUMN db_type TEXT DEFAULT ''")
        conn.commit()

    # 数据库迁移：删除 servers 表的 cpu 和 memory 字段（数据迁移到 description）
    # 注意：SQLite 不支持直接删除列，这里只是标记，实际删除需要重建表
    # 暂时保留，通过前端不再使用这些字段


# ==================== 配置 CRUD ====================

def get_config(key, default=None):
    conn = get_db()
    row = conn.execute("SELECT value FROM config WHERE key=?", (key,)).fetchone()
    if row:
        try:
            return json.loads(row['value'])
        except (json.JSONDecodeError, TypeError):
            return row['value']
    return default


def set_config(key, value):
    conn = get_db()
    # 统一使用 JSON 序列化存储，确保字符串也能正确解析
    v = json.dumps(value, ensure_ascii=False)
    conn.execute(
        "INSERT OR REPLACE INTO config (key, value) VALUES (?, ?)",
        (key, v)
    )
    conn.commit()


def get_all_config():
    conn = get_db()
    rows = conn.execute("SELECT key, value FROM config").fetchall()
    result = {}
    for row in rows:
        try:
            result[row['key']] = json.loads(row['value'])
        except (json.JSONDecodeError, TypeError):
            result[row['key']] = row['value']
    return result


# ==================== 数据库类型 CRUD ====================

DEFAULT_DB_TYPES = [
    {'id': 'oracle', 'name': 'Oracle', 'icon': '🏛️'},
    {'id': 'mysql', 'name': 'MySQL', 'icon': '🐬'},
    {'id': 'tdsql', 'name': 'TDSQL', 'icon': '☁️'},
    {'id': 'oceanbase', 'name': 'OceanBase', 'icon': '🌊'},
    {'id': 'goldendb', 'name': 'GoldenDB', 'icon': '🥇'},
    {'id': 'dm', 'name': '达梦(DM)', 'icon': '🐉'},
    {'id': 'gaussdb', 'name': 'GaussDB', 'icon': '🦢'}
]


def get_db_types() -> list[dict]:
    """获取所有数据库类型"""
    conn = get_db()
    rows = conn.execute("SELECT id, name, icon FROM db_types").fetchall()
    if not rows:
        # 首次初始化默认类型
        for t in DEFAULT_DB_TYPES:
            conn.execute(
                "INSERT OR IGNORE INTO db_types (id, name, icon) VALUES (?, ?, ?)",
                (t['id'], t['name'], t['icon'])
            )
        conn.commit()
        rows = conn.execute("SELECT id, name, icon FROM db_types").fetchall()
    else:
        # 同步更新默认类型的图标（如果已更改）
        for t in DEFAULT_DB_TYPES:
            conn.execute(
                "UPDATE db_types SET icon = ? WHERE id = ? AND icon != ?",
                (t['icon'], t['id'], t['icon'])
            )
        conn.commit()

    # 按照 DEFAULT_DB_TYPES 的顺序排序
    db_types = [dict(r) for r in rows]
    order_map = {t['id']: i for i, t in enumerate(DEFAULT_DB_TYPES)}
    db_types.sort(key=lambda x: order_map.get(x['id'], 999))
    return db_types


def add_db_type(db_id, name, icon='📁'):
    conn = get_db()
    try:
        conn.execute(
            "INSERT INTO db_types (id, name, icon) VALUES (?, ?, ?)",
            (db_id, name, icon)
        )
        conn.commit()
        return True, None
    except sqlite3.IntegrityError:
        return False, '该数据库类型已存在'


def delete_db_type(db_id):
    conn = get_db()
    conn.execute("DELETE FROM db_types WHERE id=?", (db_id,))
    conn.commit()


# ==================== 功能配置 CRUD ====================

DEFAULT_FEATURES = [
    {'module_id': 'knowledge', 'module_name': '知识库', 'module_icon': '📚', 'sort_order': 1},
    {'module_id': 'qa', 'module_name': '知识问答', 'module_icon': '💬', 'sort_order': 2},
    {'module_id': 'log_analysis', 'module_name': '日志分析', 'module_icon': '📋', 'sort_order': 3},
    {'module_id': 'sql_tools', 'module_name': 'SQL工具', 'module_icon': '🔧', 'sort_order': 4},
    {'module_id': 'manuals', 'module_name': '运维手册', 'module_icon': '📖', 'sort_order': 5},
    {'module_id': 'commands', 'module_name': '命令速查', 'module_icon': '⌨️', 'sort_order': 6},
    {'module_id': 'topology', 'module_name': '集群拓扑', 'module_icon': '🗺️', 'sort_order': 7},
    {'module_id': 'dashboard', 'module_name': '仪表盘', 'module_icon': '📊', 'sort_order': 8}
]


def _init_feature_config(conn):
    """初始化功能配置表"""
    # 创建表
    conn.execute('''
        CREATE TABLE IF NOT EXISTS feature_config (
            module_id TEXT PRIMARY KEY,
            module_name TEXT NOT NULL,
            module_icon TEXT DEFAULT '📦',
            is_enabled BOOLEAN DEFAULT 1,
            sort_order INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()

    # 初始化默认数据
    for feature in DEFAULT_FEATURES:
        conn.execute('''
            INSERT OR IGNORE INTO feature_config (module_id, module_name, module_icon, is_enabled, sort_order)
            VALUES (?, ?, ?, ?, ?)
        ''', (feature['module_id'], feature['module_name'], feature['module_icon'], 1, feature['sort_order']))
    conn.commit()


def get_feature_config():
    """获取功能配置列表"""
    conn = get_db()
    rows = conn.execute(
        "SELECT module_id, module_name, module_icon, is_enabled, sort_order FROM feature_config ORDER BY sort_order"
    ).fetchall()
    return [dict(r) for r in rows]


def update_feature_config(module_id, is_enabled):
    """更新功能配置"""
    conn = get_db()
    conn.execute(
        "UPDATE feature_config SET is_enabled = ? WHERE module_id = ?",
        (1 if is_enabled else 0, module_id)
    )
    conn.commit()


# ==================== 知识库文件 CRUD ====================

def get_knowledge_files(db_type, tag=None, keyword=None):
    conn = get_db()
    if keyword:
        rows = conn.execute(
            "SELECT id, db_type, filename, file_path, file_size, tags, created_at "
            "FROM knowledge_files WHERE db_type=? AND content_text LIKE ? ORDER BY created_at DESC",
            (db_type, f'%{keyword}%')
        ).fetchall()
    elif tag:
        rows = conn.execute(
            "SELECT id, db_type, filename, file_path, file_size, tags, created_at "
            "FROM knowledge_files WHERE db_type=? AND tags LIKE ? ORDER BY created_at DESC",
            (db_type, f'%"{tag}"%')
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT id, db_type, filename, file_path, file_size, tags, created_at "
            "FROM knowledge_files WHERE db_type=? ORDER BY created_at DESC",
            (db_type,)
        ).fetchall()
    return [dict(r) for r in rows]


def search_knowledge_content(db_type, keyword):
    """搜索知识库文件内容，返回匹配的上下文"""
    conn = get_db()
    rows = conn.execute(
        "SELECT filename, content_text, created_at FROM knowledge_files "
        "WHERE db_type=? AND content_text LIKE ? ORDER BY created_at DESC",
        (db_type, f'%{keyword}%')
    ).fetchall()

    results = []
    for row in rows:
        content = row['content_text'] or ''
        idx = content.lower().find(keyword.lower())
        if idx >= 0:
            start = max(0, idx - 50)
            end = min(len(content), idx + len(keyword) + 50)
            context = content[start:end]
            results.append({
                'filename': row['filename'],
                'context': f'...{context}...',
                'modified': row['created_at']
            })
    return results


def add_knowledge_file(db_type, filename, file_path, file_size, content_text='', tags=None):
    tags_str = json.dumps(tags or [], ensure_ascii=False)
    with transaction() as tx:
        # 检查文件是否已存在
        existing = tx.fetchone(
            "SELECT id FROM knowledge_files WHERE db_type=? AND filename=?",
            (db_type, filename)
        )
        if existing:
            # 文件已存在，更新
            file_id = existing['id']
            tx.execute(
                "UPDATE knowledge_files SET file_path=?, file_size=?, content_text=?, tags=? "
                "WHERE db_type=? AND filename=?",
                (file_path, file_size, content_text, tags_str, db_type, filename)
            )
        else:
            # 新文件，插入
            cursor = tx.execute(
                "INSERT INTO knowledge_files (db_type, filename, file_path, file_size, content_text, tags) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (db_type, filename, file_path, file_size, content_text, tags_str)
            )
            file_id = cursor.lastrowid
    return file_id


def delete_knowledge_file(db_type, filename):
    conn = get_db()
    conn.execute(
        "DELETE FROM knowledge_files WHERE db_type=? AND filename=?",
        (db_type, filename)
    )
    conn.commit()


def get_knowledge_file_path(db_type, filename):
    conn = get_db()
    row = conn.execute(
        "SELECT file_path FROM knowledge_files WHERE db_type=? AND filename=?",
        (db_type, filename)
    ).fetchone()
    return row['file_path'] if row else None


def get_knowledge_file_by_id(file_id):
    """通过ID获取知识库文件信息"""
    conn = get_db()
    row = conn.execute(
        "SELECT id, db_type, filename, file_path, file_size, content_text, tags, created_at FROM knowledge_files WHERE id=?",
        (file_id,)
    ).fetchone()
    return dict(row) if row else None


def get_all_knowledge_files(db_type=None):
    """获取所有知识库文件（用于重建索引）"""
    conn = get_db()
    if db_type:
        rows = conn.execute(
            "SELECT id, db_type, filename, file_path FROM knowledge_files WHERE db_type=?",
            (db_type,)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT id, db_type, filename, file_path FROM knowledge_files"
        ).fetchall()
    return [dict(r) for r in rows]


def update_knowledge_content(file_id, content_text):
    conn = get_db()
    conn.execute(
        "UPDATE knowledge_files SET content_text=? WHERE id=?",
        (content_text, file_id)
    )
    conn.commit()


# ==================== 收藏 CRUD ====================

def get_favorites():
    conn = get_db()
    rows = conn.execute("SELECT db_type, filename FROM favorites").fetchall()
    return {'files': [f"{r['db_type']}/{r['filename']}" for r in rows]}


def toggle_favorite(db_type, filename):
    conn = get_db()
    row = conn.execute(
        "SELECT id FROM favorites WHERE db_type=? AND filename=?",
        (db_type, filename)
    ).fetchone()
    if row:
        conn.execute("DELETE FROM favorites WHERE id=?", (row['id'],))
        conn.commit()
        return '取消收藏'
    else:
        conn.execute(
            "INSERT INTO favorites (db_type, filename) VALUES (?, ?)",
            (db_type, filename)
        )
        conn.commit()
        return '已收藏'


# ==================== 会话管理 CRUD ====================

def create_conversation(conv_id, title, db_type, model_id=''):
    """创建新会话"""
    conn = get_db()
    conn.execute(
        "INSERT INTO qa_conversations (id, title, db_type, model_id) VALUES (?, ?, ?, ?)",
        (conv_id, title, db_type, model_id)
    )
    conn.commit()


def get_conversations(limit=100):
    """获取会话列表"""
    conn = get_db()
    rows = conn.execute(
        "SELECT id, title, db_type, model_id, created_at, updated_at FROM qa_conversations "
        "ORDER BY updated_at DESC LIMIT ?", (limit,)
    ).fetchall()
    return [dict(r) for r in rows]


def get_conversation(conv_id):
    """获取单个会话详情"""
    conn = get_db()
    row = conn.execute(
        "SELECT id, title, db_type, model_id, created_at, updated_at FROM qa_conversations "
        "WHERE id=?", (conv_id,)
    ).fetchone()
    return dict(row) if row else None


def update_conversation_time(conv_id):
    """更新会话更新时间"""
    conn = get_db()
    conn.execute(
        "UPDATE qa_conversations SET updated_at=CURRENT_TIMESTAMP WHERE id=?",
        (conv_id,)
    )
    conn.commit()


def update_conversation_title(conv_id, title):
    """更新会话标题"""
    conn = get_db()
    conn.execute(
        "UPDATE qa_conversations SET title=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
        (title, conv_id)
    )
    conn.commit()


def delete_conversation(conv_id):
    """删除会话（级联删除消息）"""
    conn = get_db()
    try:
        # 先删除关联的消息（显式删除，避免依赖外键级联）
        msg_cursor = conn.execute("DELETE FROM qa_messages WHERE conversation_id=?", (conv_id,))
        msg_deleted = msg_cursor.rowcount
        # 再删除会话
        conv_cursor = conn.execute("DELETE FROM qa_conversations WHERE id=?", (conv_id,))
        conv_deleted = conv_cursor.rowcount
        conn.commit()
        if conv_deleted > 0:
            print(f"删除会话成功: {conv_id}, 删除消息数: {msg_deleted}")
            return True
        else:
            print(f"删除会话失败: {conv_id} 不存在")
            return False
    except Exception as e:
        conn.rollback()
        print(f"删除会话失败: {e}")
        return False


def clear_conversations():
    """清空所有会话（级联删除消息）"""
    conn = get_db()
    conn.execute("DELETE FROM qa_messages")
    conn.execute("DELETE FROM qa_conversations")
    conn.commit()


def add_message(conv_id, role, content):
    """添加消息到会话"""
    conn = get_db()
    conn.execute(
        "INSERT INTO qa_messages (conversation_id, role, content) VALUES (?, ?, ?)",
        (conv_id, role, content)
    )
    conn.commit()


def get_messages(conv_id):
    """获取会话的所有消息"""
    conn = get_db()
    rows = conn.execute(
        "SELECT id, role, content, created_at FROM qa_messages "
        "WHERE conversation_id=? ORDER BY created_at ASC",
        (conv_id,)
    ).fetchall()
    return [dict(r) for r in rows]


# ==================== 资源池 CRUD ====================

def get_resource_pools():
    """获取所有资源池（包含统计信息）"""
    conn = get_db()
    # 使用单个查询获取所有统计信息，避免N+1问题
    rows = conn.execute(
        """
        SELECT
            rp.id,
            rp.name,
            rp.db_type,
            rp.environment,
            rp.description,
            rp.created_at,
            COALESCE(s.server_count, 0) as server_count,
            COALESCE(i.instance_count, 0) as instance_count,
            COALESCE(t.tenant_count, 0) as tenant_count,
            COALESCE(c.cluster_count, 0) as cluster_count
        FROM resource_pools rp
        LEFT JOIN (
            SELECT resource_pool_id, COUNT(*) as server_count
            FROM servers
            GROUP BY resource_pool_id
        ) s ON rp.id = s.resource_pool_id
        LEFT JOIN (
            SELECT s.resource_pool_id, COUNT(*) as instance_count
            FROM instances i
            JOIN servers s ON i.server_id = s.id
            GROUP BY s.resource_pool_id
        ) i ON rp.id = i.resource_pool_id
        LEFT JOIN (
            SELECT resource_pool_id, COUNT(*) as tenant_count
            FROM tenants
            GROUP BY resource_pool_id
        ) t ON rp.id = t.resource_pool_id
        LEFT JOIN (
            SELECT resource_pool_id, COUNT(DISTINCT cluster_id) as cluster_count
            FROM servers
            WHERE cluster_id != ''
            GROUP BY resource_pool_id
        ) c ON rp.id = c.resource_pool_id
        ORDER BY rp.name
        """
    ).fetchall()

    return [dict(r) for r in rows]


def add_resource_pool(pool_id, name, db_type, environment, description):
    """添加资源池"""
    conn = get_db()
    conn.execute(
        "INSERT INTO resource_pools (id, name, db_type, environment, description) "
        "VALUES (?, ?, ?, ?, ?)",
        (pool_id, name, db_type, environment, description)
    )
    conn.commit()


def update_resource_pool(pool_id, **kwargs):
    """更新资源池"""
    conn = get_db()
    allowed = {'name', 'db_type', 'environment', 'description'}
    updates = {k: v for k, v in kwargs.items() if k in allowed and v is not None}
    if not updates:
        return
    set_clause = ', '.join(f"{k}=?" for k in updates)
    values = list(updates.values()) + [pool_id]
    conn.execute(f"UPDATE resource_pools SET {set_clause} WHERE id=?", values)
    conn.commit()


def delete_resource_pool(pool_id):
    """删除资源池"""
    conn = get_db()
    conn.execute("DELETE FROM resource_pools WHERE id=?", (pool_id,))
    conn.commit()


# ==================== 集群拓扑 CRUD ====================

def _fetch_servers_for_cluster(conn, resource_pool_id):
    """获取指定资源池下的所有物理机及其实例"""
    servers_rows = conn.execute(
        "SELECT id, name, host, datacenter, cluster_id, node_role, hardware_type, cpu, memory, description "
        "FROM servers WHERE resource_pool_id=?",
        (resource_pool_id,)
    ).fetchall()

    servers = []
    for s in servers_rows:
        server = dict(s)
        # 获取实例
        instances_rows = conn.execute(
            "SELECT id, name, port, cpu, memory, role, tenant_id, tenant_role, description "
            "FROM instances WHERE server_id=?",
            (s['id'],)
        ).fetchall()
        server['instances'] = [dict(i) for i in instances_rows]
        # 添加 cluster_name 字段
        if server.get('cluster_id'):
            cluster_row = conn.execute(
                "SELECT name FROM clusters WHERE id=?",
                (server['cluster_id'],)
            ).fetchone()
            server['cluster_name'] = cluster_row['name'] if cluster_row else server['cluster_id']
        servers.append(server)

    return servers


def _fetch_tenants_for_cluster(conn, resource_pool_id):
    """获取指定资源池下的所有租户"""
    tenants_rows = conn.execute(
        "SELECT id, name, topology_type, spec, description FROM tenants WHERE resource_pool_id=?",
        (resource_pool_id,)
    ).fetchall()

    tenants = []
    for t in tenants_rows:
        tenant = dict(t)
        # 获取租户关联的实例
        ti_rows = conn.execute(
            "SELECT i.id as instance_id, i.tenant_role as role, i.name, i.port, s.host "
            "FROM instances i "
            "JOIN servers s ON i.server_id = s.id "
            "WHERE i.tenant_id=?",
            (t['id'],)
        ).fetchall()
        tenant['instances'] = [dict(r) for r in ti_rows]
        tenants.append(tenant)

    return tenants


def _build_cluster_data(conn, cluster_row):
    """构建单个集群的完整数据"""
    cluster = dict(cluster_row)
    resource_pool_id = cluster['id']

    # 获取物理机
    servers = _fetch_servers_for_cluster(conn, resource_pool_id)
    cluster['servers'] = servers

    # 获取租户
    tenants = _fetch_tenants_for_cluster(conn, resource_pool_id)
    cluster['tenants'] = tenants

    # 建立 tenant_id -> name 映射
    tenant_map = {t['id']: t['name'] for t in tenants}

    # 为实例添加租户名称
    for server in servers:
        for instance in server['instances']:
            tenant_id = instance.get('tenant_id')
            instance['tenant_name'] = tenant_map.get(tenant_id, '')

    # 获取实例关系
    relations_rows = conn.execute(
        "SELECT ir.from_instance_id, ir.to_instance_id, ir.relation_type "
        "FROM instance_relations ir "
        "JOIN instances i ON ir.from_instance_id = i.id "
        "JOIN servers s ON i.server_id = s.id "
        "WHERE s.cluster_id=?",
        (resource_pool_id,)
    ).fetchall()
    cluster['relations'] = [dict(r) for r in relations_rows]

    return cluster


def get_clusters():
    """获取所有集群（包含物理机、实例、租户）

    注意：该函数实际查询 resource_pools 表，返回资源池拓扑数据。
    保留此名称是为了向后兼容，新代码建议使用 get_topology_data() 别名。
    """
    conn = get_db()
    clusters_rows = conn.execute(
        "SELECT id, name, db_type, environment, description, created_at FROM resource_pools"
    ).fetchall()

    clusters = []
    for c in clusters_rows:
        cluster = _build_cluster_data(conn, c)
        clusters.append(cluster)

    return {'clusters': clusters}


# 别名：更准确的函数名
get_topology_data = get_clusters


def get_topology_text():
    """将集群拓扑数据格式化为结构化文本"""
    data = get_topology_data()
    clusters = data.get('clusters', [])

    if not clusters:
        return ""

    lines = []
    lines.append("=" * 60)
    lines.append("集群拓扑信息")
    lines.append("=" * 60)
    lines.append("")

    for cluster in clusters:
        lines.append(f"集群名称：{cluster.get('name', '未命名')}")
        lines.append(f"环境：{cluster.get('environment', 'production')}")
        lines.append(f"数据库类型：{cluster.get('db_type', '未知')}")
        if cluster.get('description'):
            lines.append(f"描述：{cluster['description']}")
        lines.append("")

        # 物理机
        servers = cluster.get('servers', [])
        if servers:
            lines.append("物理机列表：")
            for server in servers:
                host = server.get('host', '')
                host_str = f" ({host})" if host else ""
                lines.append(f"  - {server.get('name', '未命名')}{host_str}")

                if server.get('datacenter'):
                    lines.append(f"    数据中心：{server['datacenter']}")
                if server.get('cpu'):
                    lines.append(f"    CPU：{server['cpu']}")
                if server.get('memory'):
                    lines.append(f"    内存：{server['memory']}")

                # 实例
                instances = server.get('instances', [])
                if instances:
                    lines.append("    实例：")
                    for inst in instances:
                        lines.append(f"      - {inst.get('name', '未命名')} (端口：{inst.get('port', '3306')})")
                        if inst.get('cpu') or inst.get('memory'):
                            specs = []
                            if inst.get('cpu'):
                                specs.append(f"CPU: {inst['cpu']}")
                            if inst.get('memory'):
                                specs.append(f"内存: {inst['memory']}")
                            lines.append(f"        规格：{', '.join(specs)}")
            lines.append("")

        # 租户
        tenants = cluster.get('tenants', [])
        if tenants:
            lines.append("租户列表：")
            for tenant in tenants:
                lines.append(f"  - {tenant.get('name', '未命名')} ({tenant.get('topology_type', '未知架构')})")
                if tenant.get('description'):
                    lines.append(f"    描述：{tenant['description']}")

                instances = tenant.get('instances', [])
                if instances:
                    lines.append("    实例：")
                    for inst in instances:
                        role = inst.get('role', 'slave')
                        lines.append(f"      - {inst.get('name', '未命名')} ({inst.get('host', '未知IP')}) - {role}")
            lines.append("")

        lines.append("-" * 60)
        lines.append("")

    return "\n".join(lines)


def get_system_knowledge_files():
    """获取所有 _system 类型的知识库文件"""
    conn = get_db()
    rows = conn.execute(
        "SELECT id, db_type, filename, file_path, file_size, tags, created_at "
        "FROM knowledge_files WHERE db_type='_system' ORDER BY created_at DESC"
    ).fetchall()
    return [dict(r) for r in rows]


def delete_system_knowledge_files():
    """删除所有 _system 类型的知识库文件记录"""
    conn = get_db()
    conn.execute("DELETE FROM knowledge_files WHERE db_type='_system'")
    conn.commit()


def add_cluster(cluster_id, name, db_type, environment, description):
    """添加物理集群"""
    conn = get_db()
    conn.execute(
        "INSERT INTO clusters (id, name, db_type, environment, description) "
        "VALUES (?, ?, ?, ?, ?)",
        (cluster_id, name, db_type, environment, description)
    )
    conn.commit()


def update_cluster(cluster_id, **kwargs):
    """更新物理集群"""
    conn = get_db()
    allowed = {'name', 'db_type', 'environment', 'description'}
    updates = {k: v for k, v in kwargs.items() if k in allowed and v is not None}
    if not updates:
        return
    set_clause = ', '.join(f"{k}=?" for k in updates)
    values = list(updates.values()) + [cluster_id]
    conn.execute(f"UPDATE clusters SET {set_clause} WHERE id=?", values)
    conn.commit()


def delete_cluster(cluster_id):
    """删除物理集群"""
    conn = get_db()
    conn.execute("DELETE FROM clusters WHERE id=?", (cluster_id,))
    conn.commit()


def add_server(server_id, resource_pool_id, name, host, description, datacenter='', node_role='计算节点', hardware_type='非信创物理机', cpu='', memory='', cluster_id=''):
    """添加物理机"""
    conn = get_db()
    conn.execute(
        "INSERT INTO servers (id, resource_pool_id, cluster_id, name, host, datacenter, node_role, hardware_type, cpu, memory, description) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (server_id, resource_pool_id, cluster_id, name, host, datacenter, node_role, hardware_type, cpu, memory, description)
    )
    conn.commit()


def delete_server(server_id):
    """删除物理机"""
    conn = get_db()
    conn.execute("DELETE FROM servers WHERE id=?", (server_id,))
    conn.commit()


def add_instance(instance_id, server_id, name, port, cpu, memory, role, tenant_id, tenant_role, description):
    """添加实例"""
    conn = get_db()
    conn.execute(
        "INSERT INTO instances (id, server_id, name, port, cpu, memory, role, tenant_id, tenant_role, description) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (instance_id, server_id, name, port, cpu, memory, role, tenant_id, tenant_role, description)
    )
    conn.commit()


def delete_instance(instance_id):
    """删除实例"""
    conn = get_db()
    conn.execute("DELETE FROM instances WHERE id=?", (instance_id,))
    conn.commit()


def get_instance_detail(instance_id):
    """获取实例详情"""
    conn = get_db()
    row = conn.execute(
        "SELECT i.id, i.name, i.port, i.cpu, i.memory, i.role, i.tenant_id, i.tenant_role, i.description, "
        "s.id as server_id, s.name as server_name, s.host as server_host, "
        "c.id as cluster_id, c.name as cluster_name "
        "FROM instances i "
        "JOIN servers s ON i.server_id = s.id "
        "JOIN clusters c ON s.cluster_id = c.id "
        "WHERE i.id=?",
        (instance_id,)
    ).fetchone()

    if not row:
        return None

    detail = dict(row)

    # 获取所属租户（直接从 instances 表的 tenant_id 字段）
    if detail.get('tenant_id'):
        tenant_row = conn.execute(
            "SELECT id, name, ? as role FROM tenants WHERE id=?",
            (detail.get('tenant_role', 'slave'), detail['tenant_id'])
        ).fetchone()
        if tenant_row:
            detail['tenants'] = [dict(tenant_row)]
        else:
            detail['tenants'] = []
    else:
        detail['tenants'] = []

    return detail


def add_tenant(tenant_id, cluster_id, name, topology_type, spec, description):
    """添加租户"""
    conn = get_db()
    conn.execute(
        "INSERT INTO tenants (id, cluster_id, name, topology_type, spec, description) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (tenant_id, cluster_id, name, topology_type, spec, description)
    )
    conn.commit()


def delete_tenant(tenant_id):
    """删除租户"""
    conn = get_db()
    conn.execute("DELETE FROM tenants WHERE id=?", (tenant_id,))
    conn.commit()


def update_instance_tenant(instance_id, tenant_id, tenant_role):
    """更新实例的租户关联"""
    conn = get_db()
    conn.execute(
        "UPDATE instances SET tenant_id=?, tenant_role=? WHERE id=?",
        (tenant_id, tenant_role, instance_id)
    )
    conn.commit()


def remove_instance_tenant(instance_id):
    """移除实例的租户关联"""
    conn = get_db()
    conn.execute(
        "UPDATE instances SET tenant_id=NULL, tenant_role='slave' WHERE id=?",
        (instance_id,)
    )
    conn.commit()


def add_instance_relation(from_id, to_id, relation_type='replication'):
    """添加实例关系"""
    conn = get_db()
    conn.execute(
        "INSERT OR IGNORE INTO instance_relations (from_instance_id, to_instance_id, relation_type) "
        "VALUES (?, ?, ?)",
        (from_id, to_id, relation_type)
    )
    conn.commit()


def remove_instance_relation(from_id, to_id):
    """移除实例关系"""
    conn = get_db()
    conn.execute(
        "DELETE FROM instance_relations WHERE from_instance_id=? AND to_instance_id=?",
        (from_id, to_id)
    )
    conn.commit()


# ==================== 嵌入向量 CRUD ====================

def save_embeddings(file_id, chunks_with_embeddings):
    """保存文件的嵌入向量，chunks_with_embeddings: [(chunk_index, chunk_text, embedding_bytes), ...]"""
    with transaction() as tx:
        tx.execute("DELETE FROM embeddings WHERE file_id=?", (file_id,))
        tx.executemany(
            "INSERT INTO embeddings (file_id, chunk_index, chunk_text, embedding) VALUES (?, ?, ?, ?)",
            [(file_id, idx, text, emb) for idx, text, emb in chunks_with_embeddings]
        )


def get_all_embeddings():
    """获取所有嵌入向量（用于相似度搜索）"""
    conn = get_db()
    rows = conn.execute(
        "SELECT e.id, e.file_id, e.chunk_index, e.chunk_text, e.embedding, k.db_type, k.filename "
        "FROM embeddings e JOIN knowledge_files k ON e.file_id = k.id"
    ).fetchall()
    return [dict(r) for r in rows]


def get_embeddings_by_db_type(db_type):
    """获取指定数据库类型的所有嵌入向量"""
    conn = get_db()
    rows = conn.execute(
        "SELECT e.id, e.file_id, e.chunk_index, e.chunk_text, e.embedding, k.filename "
        "FROM embeddings e JOIN knowledge_files k ON e.file_id = k.id "
        "WHERE k.db_type=?",
        (db_type,)
    ).fetchall()
    return [dict(r) for r in rows]


# ==================== 操作日志 CRUD ====================

def add_operation_log(module, action, detail='', status='success', ip=''):
    """添加操作日志"""
    import uuid
    from datetime import datetime
    conn = get_db()
    log_id = str(uuid.uuid4())
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    conn.execute(
        "INSERT INTO operation_logs (id, timestamp, module, action, detail, status, ip) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (log_id, timestamp, module, action, detail, status, ip)
    )
    conn.commit()

    # 只保留最近500条日志
    conn.execute(
        "DELETE FROM operation_logs WHERE id NOT IN "
        "(SELECT id FROM operation_logs ORDER BY timestamp DESC LIMIT 500)"
    )
    conn.commit()


def get_operation_logs(limit=50, module=None):
    """获取操作日志"""
    conn = get_db()
    if module:
        rows = conn.execute(
            "SELECT id, timestamp, module, action, detail, status, ip "
            "FROM operation_logs WHERE module=? ORDER BY timestamp DESC LIMIT ?",
            (module, limit)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT id, timestamp, module, action, detail, status, ip "
            "FROM operation_logs ORDER BY timestamp DESC LIMIT ?",
            (limit,)
        ).fetchall()
    return [dict(r) for r in rows]


def clear_operation_logs():
    """清空操作日志"""
    conn = get_db()
    conn.execute("DELETE FROM operation_logs")
    conn.commit()


def get_log_modules():
    """获取日志模块列表"""
    conn = get_db()
    rows = conn.execute(
        "SELECT DISTINCT module FROM operation_logs ORDER BY module"
    ).fetchall()
    return [r['module'] for r in rows]


# ==================== 日志分析 CRUD ====================

def add_log_analysis_task(task_id, name, question, db_type=''):
    """添加日志分析任务"""
    conn = get_db()
    conn.execute(
        "INSERT INTO log_analysis_tasks (id, name, question, db_type, status) VALUES (?, ?, ?, ?, ?)",
        (task_id, name, question, db_type, 'pending')
    )
    conn.commit()


def update_log_analysis_task(task_id, **kwargs):
    """更新日志分析任务"""
    conn = get_db()
    allowed = {'name', 'question', 'db_type', 'status', 'current_stage', 'stages', 'report', 'completed_at'}
    updates = {k: v for k, v in kwargs.items() if k in allowed and v is not None}
    if not updates:
        return
    set_clause = ', '.join(f"{k}=?" for k in updates)
    values = list(updates.values()) + [task_id]
    conn.execute(f"UPDATE log_analysis_tasks SET {set_clause} WHERE id=?", values)
    conn.commit()


def get_log_analysis_task(task_id):
    """获取单个日志分析任务"""
    conn = get_db()
    row = conn.execute(
        "SELECT id, name, question, db_type, status, current_stage, stages, report, created_at, completed_at "
        "FROM log_analysis_tasks WHERE id=?",
        (task_id,)
    ).fetchone()
    if not row:
        return None
    return dict(row)


def get_log_analysis_tasks(limit=50):
    """获取日志分析任务列表"""
    conn = get_db()
    rows = conn.execute(
        "SELECT id, name, question, db_type, status, current_stage, created_at, completed_at "
        "FROM log_analysis_tasks ORDER BY created_at DESC LIMIT ?",
        (limit,)
    ).fetchall()
    return [dict(r) for r in rows]


def delete_log_analysis_task(task_id):
    """删除日志分析任务（级联删除关联文件）"""
    with transaction() as tx:
        tx.execute("DELETE FROM log_analysis_files WHERE task_id=?", (task_id,))
        tx.execute("DELETE FROM log_analysis_tasks WHERE id=?", (task_id,))


def add_log_analysis_file(file_id, task_id, filename, file_path, file_size, content_text):
    """添加日志分析文件"""
    conn = get_db()
    conn.execute(
        "INSERT INTO log_analysis_files (id, task_id, filename, file_path, file_size, content_text) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (file_id, task_id, filename, file_path, file_size, content_text)
    )
    conn.commit()


def get_log_analysis_files(task_id):
    """获取任务的日志文件列表"""
    conn = get_db()
    rows = conn.execute(
        "SELECT id, task_id, filename, file_path, file_size, is_key_log, content_text "
        "FROM log_analysis_files WHERE task_id=?",
        (task_id,)
    ).fetchall()
    return [dict(r) for r in rows]


def delete_log_analysis_files(task_id):
    """删除任务的所有日志文件"""
    conn = get_db()
    conn.execute("DELETE FROM log_analysis_files WHERE task_id=?", (task_id,))
    conn.commit()
