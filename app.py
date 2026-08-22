#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据库工具 - Flask后端API
功能：知识库文件管理、数据库知识问答、SQL审核、运维手册、命令库、集群拓扑、大模型API配置
"""

import os
import logging
from flask import Flask, render_template
from flask import session
from datetime import timedelta
from db.database import init_db, close_db, DB_PATH, get_db_types
from db.migration import migrate_json_to_sqlite, backup_json_files
from config import (
    APP_VERSION, SECRET_KEY, SESSION_CONFIG, CORS_ORIGINS,
    SYNC_INTERVAL_HOURS, KNOWLEDGE_DIR, MANUALS_DIR, COMMANDS_DIR,
    LOG_LEVEL, LOG_FORMAT
)

# 初始化日志
logging.basicConfig(level=getattr(logging, LOG_LEVEL), format=LOG_FORMAT)
logger = logging.getLogger(__name__)

# 初始化目录
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

for d in [KNOWLEDGE_DIR, MANUALS_DIR, COMMANDS_DIR]:
    os.makedirs(d, exist_ok=True)


def _scan_directory(knowledge_dir):
    """扫描知识库目录，返回需要处理的新文件列表"""
    from utils import allowed_file
    from db.database import get_all_knowledge_files

    existing_files = get_all_knowledge_files()
    existing_set = set()
    for f in existing_files:
        existing_set.add((f['db_type'], f['filename']))

    new_files = []
    if not os.path.exists(knowledge_dir):
        return new_files

    for db_type_dir in os.listdir(knowledge_dir):
        db_type_path = os.path.join(knowledge_dir, db_type_dir)
        if not os.path.isdir(db_type_path):
            continue

        for filename in os.listdir(db_type_path):
            filepath = os.path.join(db_type_path, filename)
            if not os.path.isfile(filepath):
                continue
            if (db_type_dir, filename) in existing_set:
                continue
            if not allowed_file(filename):
                continue
            new_files.append((db_type_dir, filename, filepath))

    return new_files


def _process_single_file(db_type, filename, filepath):
    """处理单个知识库文件：提取内容并入库，返回文件ID"""
    from utils import extract_content
    from db.database import add_knowledge_file

    try:
        content_text = extract_content(filepath)
        file_size = os.path.getsize(filepath)
        add_knowledge_file(db_type, filename, filepath, file_size, content_text, [])
        return True, content_text
    except Exception as e:
        logger.warning(f"[扫描] 文件入库失败: {filepath} - {e}")
        return False, None


def _generate_embeddings_for_file(db_type, filename, content_text):
    """为单个文件生成向量索引"""
    from db.database import get_all_knowledge_files, save_embeddings
    from rag.embedder import chunk_text, Embedder

    try:
        embedder = Embedder()
        chunks = chunk_text(content_text)
        if not chunks:
            return False

        files = get_all_knowledge_files(db_type)
        file_id = None
        for f in files:
            if f['filename'] == filename:
                file_id = f['id']
                break

        if file_id:
            embeddings = embedder.embed_chunks(chunks)
            save_embeddings(file_id, embeddings)
            return True
    except Exception as e:
        logger.warning(f"[扫描] 向量索引生成失败: {db_type}/{filename} - {e}")
    return False


def scan_knowledge_files():
    """扫描知识库目录，将新增的文件自动同步到数据库，并生成向量索引"""
    new_files = _scan_directory(KNOWLEDGE_DIR)
    if not new_files:
        return

    scanned_count = 0
    vector_count = 0

    for db_type, filename, filepath in new_files:
        success, content_text = _process_single_file(db_type, filename, filepath)
        if success:
            scanned_count += 1
            if content_text and _generate_embeddings_for_file(db_type, filename, content_text):
                vector_count += 1

    if scanned_count > 0:
        msg = f"[扫描] 自动发现 {scanned_count} 个新文件并已入库"
        if vector_count > 0:
            msg += f"，其中 {vector_count} 个文件已生成向量索引"
        logger.info(msg)


def create_app():
    """应用工厂"""
    app = Flask(__name__)

    # 配置 secret key（用于 session 和 CSRF）
    app.secret_key = SECRET_KEY

    # 配置 session cookie 安全
    app.config.update(
        SESSION_COOKIE_SECURE=SESSION_CONFIG['SESSION_COOKIE_SECURE'],
        SESSION_COOKIE_HTTPONLY=SESSION_CONFIG['SESSION_COOKIE_HTTPONLY'],
        SESSION_COOKIE_SAMESITE=SESSION_CONFIG['SESSION_COOKIE_SAMESITE'],
        PERMANENT_SESSION_LIFETIME=timedelta(seconds=SESSION_CONFIG['PERMANENT_SESSION_LIFETIME'])
    )

    # 尝试添加 CORS 支持（如果已安装 flask-cors）
    try:
        from flask_cors import CORS
        CORS(app, supports_credentials=True, origins=CORS_ORIGINS)
    except ImportError:
        pass  # flask-cors 未安装，跳过

    # 初始化数据库
    init_db()

    # 迁移旧 JSON 数据（仅首次）
    backup_json_files()
    migrate_json_to_sqlite()

    # 确保默认数据库类型的目录存在
    for db_type in get_db_types():
        os.makedirs(os.path.join(KNOWLEDGE_DIR, db_type['id']), exist_ok=True)

    # 自动扫描知识库目录，同步新增的文件到数据库
    scan_knowledge_files()

    # 注册关闭钩子
    app.teardown_appcontext(close_db)

    # 注册 Blueprint
    from routes import (
        db_types_bp, knowledge_bp, qa_bp, sql_tools_bp,
        manuals_bp, commands_bp, topology_bp, config_bp,
        dashboard_bp, log_analysis_bp, agent_bp, agent_conn_bp,
        kg_bp
    )
    app.register_blueprint(db_types_bp)
    app.register_blueprint(knowledge_bp)
    app.register_blueprint(qa_bp)
    app.register_blueprint(sql_tools_bp)
    app.register_blueprint(manuals_bp)
    app.register_blueprint(commands_bp)
    app.register_blueprint(topology_bp)
    app.register_blueprint(config_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(log_analysis_bp)
    app.register_blueprint(agent_bp)
    app.register_blueprint(agent_conn_bp)
    app.register_blueprint(kg_bp)

    # 主页路由
    @app.route('/')
    def index():
        return render_template('index.html', version=APP_VERSION)

    # 初始化定时任务
    init_scheduler()

    return app


def init_scheduler():
    """初始化APScheduler定时任务：自动同步拓扑和手册到知识库"""
    try:
        from apscheduler.schedulers.background import BackgroundScheduler
        from apscheduler.triggers.interval import IntervalTrigger

        def auto_sync_job():
            """定时同步任务"""
            logger.info("[自动同步] 开始执行定时同步任务...")
            try:
                # 同步集群拓扑
                sync_topology_to_knowledge()
            except (ImportError, RuntimeError, OSError) as e:
                logger.warning(f"[自动同步] 拓扑同步失败: {e}")

            try:
                # 同步运维手册
                from routes.manuals import sync_manuals_to_knowledge
                sync_manuals_to_knowledge()
            except (ImportError, RuntimeError, OSError) as e:
                logger.warning(f"[自动同步] 手册同步失败: {e}")

            logger.info("[自动同步] 定时同步任务完成")

        scheduler = BackgroundScheduler()
        scheduler.add_job(
            auto_sync_job,
            trigger=IntervalTrigger(hours=SYNC_INTERVAL_HOURS),
            id='auto_sync_knowledge',
            replace_existing=True
        )

        # v2.5 每日技能库淘汰：usage_count=0 且超 30 天的自动沉淀技能标 deprecated，防止技能库只增不减
        def skill_curator_job():
            try:
                from agent.skills import SkillManager
                sm = SkillManager()
                deprecated = sm.curator_deprecate_stale(days=30)
                if deprecated:
                    logger.info(f"[Skill Curator] 淘汰 {len(deprecated)} 个过期技能: {deprecated}")
            except Exception as e:
                logger.warning(f"[Skill Curator] 淘汰任务失败: {e}")

        scheduler.add_job(
            skill_curator_job,
            trigger=IntervalTrigger(days=1),
            id='skill_curator_deprecate',
            replace_existing=True
        )

        scheduler.start()
        logger.info(f"[自动同步] APScheduler 已启动，每{SYNC_INTERVAL_HOURS}小时自动同步一次")

        # 启动时立即执行一次同步
        logger.info("[自动同步] 启动时立即执行首次同步...")
        auto_sync_job()

    except ImportError:
        logger.info("[自动同步] APScheduler 未安装，跳过定时同步功能")
        logger.info("[自动同步] 如需启用，请执行: pip install apscheduler")
    except (ImportError, ModuleNotFoundError) as e:
        logger.error(f"[自动同步] 初始化定时任务失败: {e}")


def sync_topology_to_knowledge():
    """将集群拓扑数据同步到知识库（_system 类型），供RAG检索"""
    from db.database import get_topology_text, add_knowledge_file, get_knowledge_files, delete_knowledge_file
    from rag.embedder import chunk_text
    from rag import Embedder

    try:
        topology_text = get_topology_text()
        if not topology_text:
            logger.info("[自动同步] 集群拓扑为空，跳过同步")
            return

        # 删除旧的拓扑记录（只删除 _topology.txt，保留运维手册）
        try:
            files = get_knowledge_files('_system')
            for f in files:
                if f['filename'] == '_topology.txt':
                    delete_knowledge_file('_system', '_topology.txt')
                    break
        except (OSError, RuntimeError):
            pass

        # 写入临时文件
        import tempfile
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False, encoding='utf-8') as f:
            f.write(topology_text)
            temp_path = f.name

        # 存入知识库
        file_id = add_knowledge_file('_system', '_topology.txt', temp_path, len(topology_text), topology_text, ['topology'])

        # 生成向量嵌入
        try:
            if file_id:
                chunks = chunk_text(topology_text)
                if chunks:
                    embedder = Embedder()
                    embeddings = embedder.embed_chunks(chunks)
                    from db.database import save_embeddings
                    save_embeddings(file_id, embeddings)
        except (ImportError, RuntimeError, OSError) as e:
            logger.warning(f"[自动同步] 拓扑向量嵌入生成失败: {e}")

        # 清理临时文件
        try:
            os.remove(temp_path)
        except (OSError, FileNotFoundError):
            pass

        logger.info("[自动同步] 集群拓扑同步完成")
    except (OSError, RuntimeError, ImportError) as e:
        logger.error(f"[自动同步] 集群拓扑同步失败: {e}")


# ==================== 启动 ====================

if __name__ == '__main__':
    app = create_app()
    logger.info("=" * 60)
    logger.info("数据库工具启动中...")
    logger.info(f"SQLite 数据库: {DB_PATH}")
    logger.info("访问地址: http://localhost:5000")
    logger.info("=" * 60)
    app.run(host='0.0.0.0', port=5000, debug=True)
