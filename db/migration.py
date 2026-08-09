# -*- coding: utf-8 -*-
"""
从 JSON 文件迁移数据到 SQLite
"""
import os
import json
from datetime import datetime
from .database import (
    get_db, set_config, get_db_types, add_db_type,
    add_knowledge_file, get_favorites,
    toggle_favorite, add_resource_pool, DB_PATH
)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_FILE = os.path.join(BASE_DIR, 'config.json')
DB_TYPES_FILE = os.path.join(BASE_DIR, 'db_types.json')
TOPOLOGY_FILE = os.path.join(BASE_DIR, 'topology.json')
FAVORITES_FILE = os.path.join(BASE_DIR, 'favorites.json')
KNOWLEDGE_DIR = os.path.join(BASE_DIR, 'data', 'knowledge')


def _load_json(filepath, default=None):
    if os.path.exists(filepath):
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    return default if default is not None else {}


def migrate_json_to_sqlite():
    """将现有 JSON 数据迁移到 SQLite（仅首次执行）"""
    # 测试数据库跳过迁移
    if os.environ.get('DB_TOOL_TEST_DB'):
        return False

    if os.path.exists(DB_PATH):
        conn = get_db()
        # 检查是否已有数据
        count = conn.execute("SELECT COUNT(*) FROM config").fetchone()[0]
        db_count = conn.execute("SELECT COUNT(*) FROM db_types").fetchone()[0]
        if count > 0 or db_count > 0:
            return False  # 已有数据，跳过迁移

    print("正在从 JSON 文件迁移数据到 SQLite...")

    # 迁移配置
    config = _load_json(CONFIG_FILE, {})
    for key, value in config.items():
        set_config(key, value)
    if config:
        print(f"  - 配置: 迁移 {len(config)} 项")

    # 迁移数据库类型
    db_types = _load_json(DB_TYPES_FILE, None)
    if db_types and isinstance(db_types, list):
        conn = get_db()
        for t in db_types:
            conn.execute(
                "INSERT OR IGNORE INTO db_types (id, name, icon) VALUES (?, ?, ?)",
                (t['id'], t['name'], t.get('icon', '📁'))
            )
        conn.commit()
        print(f"  - 数据库类型: 迁移 {len(db_types)} 项")

    # 迁移收藏
    favorites = _load_json(FAVORITES_FILE, {'files': []})
    fav_files = favorites.get('files', [])
    if fav_files:
        for fav in fav_files:
            parts = fav.split('/', 1)
            if len(parts) == 2:
                toggle_favorite(parts[0], parts[1])
        print(f"  - 收藏: 迁移 {len(fav_files)} 项")

    # 迁移集群拓扑（只迁移集群基本信息）
    topology = _load_json(TOPOLOGY_FILE, {'clusters': []})
    clusters = topology.get('clusters', [])
    if clusters:
        for cluster in clusters:
            cluster_id = cluster.get('id', '')
            add_resource_pool(
                cluster_id,
                cluster.get('name', ''),
                cluster.get('db_type', ''),
                cluster.get('environment', 'production'),
                cluster.get('description', '')
            )
        print(f"  - 集群: 迁移 {len(clusters)} 个")

    # 迁移知识库文件元数据
    migrated_files = 0
    if os.path.exists(KNOWLEDGE_DIR):
        for db_type_dir in os.listdir(KNOWLEDGE_DIR):
            db_type_path = os.path.join(KNOWLEDGE_DIR, db_type_dir)
            if not os.path.isdir(db_type_path):
                continue
            for filename in os.listdir(db_type_path):
                filepath = os.path.join(db_type_path, filename)
                if os.path.isfile(filepath):
                    stat = os.stat(filepath)
                    tags = []
                    if '[案例]' in filename or '故障' in filename:
                        tags.append('case')
                    add_knowledge_file(
                        db_type_dir, filename, filepath,
                        stat.st_size, '', tags
                    )
                    migrated_files += 1
    if migrated_files:
        print(f"  - 知识库文件: 迁移 {migrated_files} 个")

    print("数据迁移完成！")
    return True


def backup_json_files():
    """备份原始 JSON 文件"""
    if os.environ.get('DB_TOOL_TEST_DB'):
        return
    backup_dir = os.path.join(BASE_DIR, 'data', 'json_backup')
    os.makedirs(backup_dir, exist_ok=True)

    for filepath in [CONFIG_FILE, DB_TYPES_FILE, TOPOLOGY_FILE, FAVORITES_FILE]:
        if os.path.exists(filepath):
            filename = os.path.basename(filepath)
            backup_path = os.path.join(backup_dir, filename)
            if not os.path.exists(backup_path):
                import shutil
                shutil.copy2(filepath, backup_path)
                print(f"  - 备份: {filename}")
