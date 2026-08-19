# -*- coding: utf-8 -*-
"""
应用配置模块
集中管理所有配置项，避免硬编码
"""
import os

# ==================== 基础路径配置 ====================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, 'data')
KNOWLEDGE_DIR = os.path.join(DATA_DIR, 'knowledge')
MANUALS_DIR = os.path.join(DATA_DIR, 'manuals')
COMMANDS_DIR = os.path.join(DATA_DIR, 'commands')

# ==================== 应用配置 ====================

# 版本号
APP_VERSION = '4.2.1'

# Secret Key（生产环境应从环境变量读取）
SECRET_KEY = os.environ.get('FLASK_SECRET_KEY', 'dbsv-admin-dev-secret-key-change-in-production')

# Session 配置
SESSION_CONFIG = {
    'PERMANENT_SESSION_LIFETIME': 24 * 60 * 60,  # 24小时（秒）
    'SESSION_COOKIE_SECURE': False,  # 生产环境设为 True（HTTPS）
    'SESSION_COOKIE_HTTPONLY': True,
    'SESSION_COOKIE_SAMESITE': 'Lax',
}

# CORS 配置
CORS_ORIGINS = [
    'http://localhost:9163',
    'http://127.0.0.1:9163',
]

# ==================== 定时任务配置 ====================

# 自动同步间隔（小时）
SYNC_INTERVAL_HOURS = int(os.environ.get('DB_TOOL_SYNC_INTERVAL_HOURS', '1'))

# ==================== Agent 配置 ====================

# ReAct 最大执行步数（迭代预算；默认 6：收敛步数，防简单任务跑满步数，可用 env 覆盖）
AGENT_MAX_STEPS = int(os.environ.get('DB_TOOL_AGENT_MAX_STEPS', '6'))

# 对话历史字符预算：超过则强制收敛到结论（防超长 prompt）；
# 大观察已改摘要化入历史（engine._history_observation），预算可放宽以支持更长链路
AGENT_MAX_HISTORY_CHARS = int(os.environ.get('DB_TOOL_AGENT_MAX_HISTORY_CHARS', '20000'))

# 变更类操作计划审批超时（分钟）：DBA 未在时限内审批则计划置 expired
AGENT_PLAN_TIMEOUT_MINUTES = int(os.environ.get('DB_TOOL_AGENT_PLAN_TIMEOUT_MINUTES', '15'))

# ReAct 主循环总墙钟超时（秒）：LLM 慢或某步阻塞时 SSE 不会无限挂起，超时优雅收敛并给结论
AGENT_MAX_WALL_CLOCK_SECONDS = int(os.environ.get('DB_TOOL_AGENT_MAX_WALL_CLOCK_SECONDS', '300'))

# 命令安全融合判定：静态脚本判拒绝/未知的命令，是否额外发起独立 LLM 审查作第二意见。
# 关闭时命令校验退化为纯静态（离线可用，未知命令走审批）。
COMMAND_LLM_JUDGE = os.environ.get('DB_TOOL_LLM_COMMAND_JUDGE', '1') == '1'
# 命令 LLM 审查超时（秒）：判读是执行路径上的同步闸门，超时即放弃审查、保持静态判定
COMMAND_JUDGE_TIMEOUT = int(os.environ.get('DB_TOOL_COMMAND_JUDGE_TIMEOUT', '20'))
# 命令 LLM 审查结果缓存时长（秒）：同一命令复用判读，避免重复调用
COMMAND_JUDGE_CACHE_TTL = int(os.environ.get('DB_TOOL_COMMAND_JUDGE_CACHE_TTL', '600'))

# ==================== RAG 配置 ====================

# 嵌入模型名称
EMBED_MODEL_NAME = os.environ.get('DB_TOOL_EMBED_MODEL', 'moka-ai/m3e-base')

# 文本分块配置（rag/embedder.chunk_text 默认值从此处读取）
# 注意：m3e-base 为 BERT，max_position_embeddings=512 token。2000 字符会被截断到前
# ~512 token，块尾部对检索不可见；500 字符（overlap 10%）可整块编码，检索精度更高。
# 改动此值后需全量重建索引并重调检索阈值（详见 version_update / rag_tuning.md）。
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
