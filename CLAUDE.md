# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

DBSV 数据库运维工具（DB Tool）：面向 DBA 的 Web 端数据库运维平台。Flask 后端 + 原生 HTML/CSS/JS 单页前端，SQLite 存储，集成知识库、RAG 问答、SQL 工具、集群拓扑、日志分析、智能运维 Agent 等 9 大模块。UI 与代码注释均为中文，开发人：顾云波。

**配套文档（优先阅读，比本文件更详细）**：
- `project.md` — 项目概述、模块功能
- `code_desc.md` — 函数/API 级代码说明
- `tables_desc.md` — 数据库表结构
- `deploy.md` — 部署指南与依赖清单
- `version_update.md` — 版本更新记录

## 常用命令

```bash
# 启动开发服务（默认监听 0.0.0.0:5000，debug=True）
python app.py

# 无测试框架；仓库无 requirements.txt。依赖按 deploy.md 安装：
pip install flask requests python-docx openpyxl PyPDF2 python-multipart sentence-transformers numpy sqlglot
# 可选：flask-cors、apscheduler（未安装时相关功能自动跳过）

# Python 语法检查（项目实际使用的验证方式）
python -m py_compile app.py db/database.py routes/*.py

# JS 语法检查（前端无构建工具，直接用 node 校验）
node --check static/js/app.js

# 快速验证应用工厂可构建
python -c "from app import create_app; app = create_app(); print('OK')"
```

- 首次启动会自动建库（`data/db_tool.db`）、执行 JSON→SQLite 迁移、扫描 `data/knowledge/` 同步新文件。
- `temp_scripts/` 下是历史一次性调试脚本（`test_*.py`、`check_*.py` 等），**不是**正式测试，不要当测试套件使用。
- 版本号以 `config.py` 的 `APP_VERSION` 为准（当前 3.0.1），README 里的版本号可能过期。

## 架构总览

### 后端（Flask 应用工厂）

- `app.py`：`create_app()` 工厂。注册 13 个 Blueprint，初始化 DB、执行迁移、扫描知识库目录、启动 APScheduler 定时同步（拓扑/手册 → `_system` 知识类型）。
- `config.py`：全部配置集中于此（路径、secret、RAG 分块、LLM 默认配置、日志）。`SECRET_KEY` 支持环境变量 `FLASK_SECRET_KEY`。
- `routes/__init__.py`：Blueprint 统一导出；每个 `routes/*.py` 对应一个功能模块的 REST API。
- `utils/` 包（注意：是 `utils/__init__.py`，不是根目录 `utils.py`）：`extract_content`（多格式文件解析）、`call_llm`（LLM 调用）、`allowed_file`。

### 数据层（db/）

- `db/database.py`：**原生 sqlite3，不是 SQLAlchemy**（README 中的 SQLAlchemy 描述已过时）。线程本地连接（threading.local），WAL 模式、外键开启、busy_timeout 5s。`transaction` 上下文管理器处理显式事务。`init_db()` 内联建全部表。`DB_PATH` 可用环境变量 `DB_TOOL_TEST_DB` 覆盖（用于测试隔离）。
- `db/kg_database.py`：知识图谱表 CRUD。
- `db/migration.py`：旧 JSON 文件 → SQLite 自动迁移。

### RAG（rag/embedder.py）

- sentence-transformers `moka-ai/m3e-base`，单例懒加载（首次调用才下载/加载，失败则标记 `_model_load_failed` 并回退关键词匹配）。模型缓存在 `data/models/`，检测到缓存时设 `TRANSFORMERS_OFFLINE=1` 跳过网络；设置 `HF_ENDPOINT=https://hf-mirror.com` 镜像。
- `chunk_text()` 默认分块参数统一从 `config.py` 的 `CHUNK_SIZE`/`CHUNK_OVERLAP` 读取（当前 2000/100），改动分块行为时只需改 config.py。
- 向量存 `embeddings` 表（BLOB），余弦相似度检索，阈值 0.55。`rebuild_all()`/`rebuild_single()` 重建索引时**同时提取知识图谱**。

### 知识图谱（kg/）

- 混合提取：`kg/rules.py`（正则+词典规则匹配，主力）、`kg/llm_extractor.py`（LLM 提取，可选）。
- `kg/graph.py`：图谱查询引擎（邻居、路径、子图、QA 增强）。
- 已并入知识库模块（`routes/kg.py` + `static/js/kg.js`），前端在知识库页做文件视图/图谱视图切换。实体 14 类、关系 5 类；数据规模见 project.md。

### 智能运维 Agent（agent/）

- `agent/engine.py`：`SmartOpsAgent`，ReAct 循环（Thought→Action→Observation），SSE 流式输出思考/工具执行/观察。
- `agent/harness.py`：安全约束框架，**核心安全机制**。SQL 白名单（按 OperationLevel 分级，默认 READONLY：仅 SELECT/EXPLAIN/DESCRIBE/SHOW）+ 命令白名单（按数据库类型）+ 危险模式黑名单（DROP/DELETE/UPDATE/INSERT 等）。改 Agent 行为时必须经过 Harness 校验。
- `agent/tools.py`：MCP 风格工具注册表（`register_tool` 装饰器 + `TOOLS` 字典），5 个标准工具。
- `agent/skills.py`：6 个内置技能（慢查询诊断、Oracle RAC、备份检查等）；`agent/state.py`：ReAct 状态机。
- 连接配置存 `agent_ssh_connections` / `agent_db_connections` 表，由 `routes/agent_connections.py` 管理。

### 本地 SQL 检查（sql_checker.py）

- 用 sqlglot 本地解析 SQL（语法检查/格式化），走 LLM 仅用于审核/转换/执行计划分析。
- **国产数据库兼容性映射**（改这个文件时会用到）：dm→oracle、goldendb/oceanbase/tdsql→mysql、gaussdb→postgres。

### 前端（static/js/ + templates/index.html）

- 单页应用，无构建工具、无框架。`app.js` 入口（主题、导航、初始化）；`api.js` 封装 apiGet/apiPost/apiPut/apiDelete；各模块一个 JS 文件（`qa.js`、`topology.js` 等）。
- 主题用 CSS 变量（`static/css/style.css`），暗色/亮色切换，localStorage 持久化。
- 新增模块时需要同时：在 `routes/` 建 Blueprint、`routes/__init__.py` 导出并注册、`static/js/` 加模块文件、`templates/index.html` 加导航。

## 注意事项

- 数据/运行期状态都在 `data/`：`db_tool.db`、知识文件、手册、模型缓存、命令 JSON。删除即丢失全部数据。
- LLM 配置（API 地址/密钥/多模型）存 `config` 表，首次使用需在「API配置」页配置并测试连接；RAG 与 QA 均可在多个模型间切换。
- 功能开关存 `feature_config` 表，控制导航栏各模块显隐。
- 知识库按 `db_type` 目录组织（`data/knowledge/<db_type>/`）；`_system` 是内部类型，存拓扑/手册自动同步内容，勿手动删。
- 平台为 Windows；常规验证流程是 `python -m py_compile` + `node --check`，改前端后至少对改动文件跑一次 node 语法检查。
