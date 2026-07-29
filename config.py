# -*- coding: utf-8 -*-
"""
应用配置模块
集中管理所有配置项，避免硬编码
"""
import os

# ==================== 基础路径配置 ====================

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, 'data')
KNOWLEDGE_DIR = os.path.join(DATA_DIR, 'knowledge')
MANUALS_DIR = os.path.join(DATA_DIR, 'manuals')
COMMANDS_DIR = os.path.join(DATA_DIR, 'commands')

# ==================== 应用配置 ====================

# 版本号
APP_VERSION = '2.4.2'

# Secret Key（生产环境应从环境变量读取）
SECRET_KEY = os.environ.get('FLASK_SECRET_KEY', 'db-tool-dev-secret-key-change-in-production')

# Session 配置
SESSION_CONFIG = {
    'PERMANENT_SESSION_LIFETIME': 24 * 60 * 60,  # 24小时（秒）
    'SESSION_COOKIE_SECURE': False,  # 生产环境设为 True（HTTPS）
    'SESSION_COOKIE_HTTPONLY': True,
    'SESSION_COOKIE_SAMESITE': 'Lax',
}

# CORS 配置
CORS_ORIGINS = [
    'http://localhost:5000',
    'http://127.0.0.1:5000',
]

# ==================== 定时任务配置 ====================

# 自动同步间隔（小时）
SYNC_INTERVAL_HOURS = int(os.environ.get('DB_TOOL_SYNC_INTERVAL_HOURS', '1'))

# ==================== RAG 配置 ====================

# 嵌入模型名称
EMBED_MODEL_NAME = os.environ.get('DB_TOOL_EMBED_MODEL', 'moka-ai/m3e-base')

# 文本分块配置
CHUNK_SIZE = 500
CHUNK_OVERLAP = 50

# ==================== LLM 配置 ====================

# 默认 LLM 配置
DEFAULT_LLM_CONFIG = {
    'api_url': 'https://api.openai.com/v1/chat/completions',
    'api_key': '',
    'model': 'gpt-3.5-turbo',
    'temperature': 0.7,
    'max_tokens': 2048,
}

# ==================== 文件上传配置 ====================

# 允许的文件扩展名
ALLOWED_EXTENSIONS = {'txt', 'md', 'html', 'sql', 'json', 'pdf', 'docx', 'xlsx'}

# 最大文件大小（MB）
MAX_FILE_SIZE_MB = 50

# ==================== 日志配置 ====================

# 日志级别
LOG_LEVEL = os.environ.get('DB_TOOL_LOG_LEVEL', 'INFO')

# 日志格式
LOG_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
