# DBSV Admin 代码结构文档

> 生成时间: 2026-08-05
> 版本: v3.0.1
> 用途: 快速了解项目代码结构和函数功能

> 📌 配套文档：
> - `project.md` — 项目概述、技术栈、功能模块
> - `tables_desc.md` — 数据库表结构
> - `version_update.md` — 版本更新记录
> - `deploy.md` — 部署指南

---

## 目录结构

```
dbsv_admin/
├── app.py                  # 应用工厂 + 启动入口
├── utils.py                # 工具函数（文件解析、LLM 调用）
├── deploy.md              # 部署指南（含依赖清单）
├── deploy.txt              # 部署指南
├── PROJECT.md              # 项目说明文档
│
├── db/                     # 数据库层
│   ├── __init__.py
│   ├── database.py         # SQLite 连接管理、表初始化、全部 CRUD
│   └── migration.py        # JSON → SQLite 自动迁移（首次启动执行）
│
├── utils/                  # 工具函数包
│   ├── __init__.py         # 通用工具函数（文件解析、LLM 调用）
│   └── topology_import.py  # 集群拓扑批量导入模块（Excel 解析、数据导入）
│
├── routes/                 # API 路由（Blueprint）
│   ├── __init__.py         # Blueprint 统一导出
│   ├── db_types.py         # 数据库类型管理
│   ├── knowledge.py        # 知识库文件管理 + 收藏夹
│   ├── qa.py               # 知识问答（支持向量检索 RAG）
│   ├── sql_tools.py        # SQL 审核 / 格式化 / 转换 / 执行计划分析
│   ├── log_analysis.py     # 日志分析（多轮 LLM 分析 + RAG 增强）
│   ├── manuals.py           # 运维手册上传下载
│   ├── commands.py          # 命令速查（按数据库类型）
│   ├── topology.py          # 集群拓扑 CRUD + 批量导入 API
│   ├── config.py            # LLM API 配置 + 导入导出
│   ├── dashboard.py         # 仪表盘统计 + 日志 + 快捷键
│   ├── agent.py             # 智能运维Agent核心引擎（ReAct循环 + SSE流式）
│   └── agent_connections.py # SSH/数据库连接管理
│
├── agent/                  # 智能运维Agent模块
│   ├── __init__.py
│   ├── harness.py           # 安全约束框架（SQL白名单 + 命令白名单 + 操作级别）
│   ├── connectors.py        # 工具连接器（DB/SSH连接加载解密 + 查询执行 + 指标/Schema生成）
│   ├── skills.py            # 领域知识与操作指南（6个内置技能）
│   ├── state.py             # Agent状态管理（ReAct状态机）
│   ├── tools.py             # MCP风格工具定义（5个真实工具 + ToolContext）
│   └── engine.py            # Agent核心引擎（ReAct循环 + 知识库/图谱增强 + 状态持久化）
│
├── rag/                    # 向量检索模块
│   ├── __init__.py
│   └── embedder.py          # 文本分块、向量嵌入、相似度检索
│
├── static/
│   ├── css/style.css        # 样式（含暗色主题 CSS 变量系统）
│   └── js/                  # 前端模块化 JS
│       ├── app.js           # 入口文件：主题、导航、初始化、仪表盘
│       ├── utils.js         # 通用工具函数
│       ├── api.js           # API 请求封装
│       ├── knowledge.js     # 知识库模块（**含知识图谱视图切换**）
│       ├── qa.js            # 知识问答模块
│       ├── sql-tools.js     # SQL 工具模块
│       ├── log-analysis.js  # 日志分析模块
│       ├── manuals.js       # 运维手册模块
│       ├── commands.js      # 命令速查模块
│       ├── topology.js      # 集群拓扑模块
│       ├── agent.js         # 智能运维Agent模块（ReAct循环可视化）
│       └── config.js        # 系统配置模块
│
├── templates/
│   └── index.html           # 单页应用 HTML
│
└── data/                   # 运行时数据（自动创建）
    ├── db_tool.db           # SQLite 数据库
    ├── knowledge/           # 按数据库类型分目录存储知识库文件
    ├── manuals/             # 运维手册文件
    ├── commands/            # 命令库 JSON 文件
    ├── models/              # sentence-transformers 模型缓存
    └── json_backup/         # 迁移前的 JSON 文件备份
```

---

## 后端文件详解

### app.py — 应用工厂 + 启动入口

**全局变量：**
| 变量 | 说明 |
|------|------|
| `BASE_DIR` | 项目根目录 |
| `DATA_DIR` | data 目录 |
| `KNOWLEDGE_DIR` | 知识库文件目录 `data/knowledge` |
| `MANUALS_DIR` | 运维手册目录 `data/manuals` |
| `COMMANDS_DIR` | 命令库目录 `data/commands` |

**函数：**

| 函数 | 参数 | 返回值 | 说明 |
|------|------|--------|------|
| `scan_knowledge_files()` | 无 | 无 | 启动时自动扫描 `data/knowledge/` 目录，将新增文件同步到数据库 |
| `_scan_directory(knowledge_dir)` | `str` | `list` | 扫描目录，返回需要处理的新文件列表 |
| `_process_single_file(db_type, filename, filepath)` | `str, str, str` | `(bool, str)` | 处理单个知识库文件：提取内容并入库 |
| `_generate_embeddings_for_file(db_type, filename, content_text)` | `str, str, str` | `bool` | 为单个文件生成向量索引 |
| `create_app()` | 无 | `Flask` | 应用工厂：初始化数据库 → 迁移旧数据 → 扫描知识库 → 注册 Blueprint → 注册关闭钩子 |
| `init_scheduler()` | 无 | 无 | 初始化 APScheduler 定时任务，同步间隔从环境变量 `DB_TOOL_SYNC_INTERVAL_HOURS` 读取（默认1小时） |

**启动流程：**
1. `init_db()` — 初始化 SQLite 表结构
2. `backup_json_files()` — 备份旧 JSON 文件
3. `migrate_json_to_sqlite()` — 迁移 JSON 数据到 SQLite（仅首次）
4. 确保各数据库类型的知识库目录存在
5. `scan_knowledge_files()` — 自动扫描目录中的新文件
6. 注册 Blueprint（9 个模块）
7. 注册 `teardown_appcontext(close_db)` 关闭钩子

---

### utils.py — 工具函数

**常量：**
| 常量 | 值 | 说明 |
|------|-----|------|
| `ALLOWED_EXTENSIONS` | `{'txt','md','pdf','docx','xlsx','xls','doc','html','htm'}` | 支持的文件扩展名 |

**文件解析函数：**

| 函数 | 参数 | 返回值 | 说明 |
|------|------|--------|------|
| `allowed_file(filename)` | `str` | `bool` | 检查文件扩展名是否在允许列表中 |
| `extract_content(filepath)` | `str` | `str` | 根据扩展名提取文件文本内容，失败返回错误信息 |
| `_extract_txt(filepath)` | `str` | `str` | 尝试 utf-8/gbk/gb2312/latin-1 编码读取文本 |
| `_extract_pdf(filepath)` | `str` | `str` | 使用 PyPDF2 提取 PDF 文本 |
| `_extract_docx(filepath)` | `str` | `str` | 使用 python-docx 提取 DOCX 文本 |
| `_extract_xlsx(filepath)` | `str` | `str` | 使用 openpyxl 提取 XLSX 文本 |

**LLM 调用函数：**

| 函数 | 参数 | 返回值 | 说明 |
|------|------|--------|------|
| `load_llm_config(model_id=None)` | `str` | `dict` | 从数据库加载 api_url, api_key, model_name，支持指定模型ID |
| `_build_api_url(config)` | `dict` | `str` | 自动补全 API URL（添加 /chat/completions） |
| `_build_api_headers(config)` | `dict` | `dict` | 构建 Authorization + Content-Type 请求头 |
| `_build_api_data(config, messages, stream)` | `dict, list, bool` | `dict` | 构建请求体（model, messages, temperature, stream），自动处理 Moonshot temperature=1 |
| `_check_llm_config(config)` | `dict` | `(bool, str)` | 检查 api_url 和 api_key 是否已配置 |
| `call_llm(messages, model_id=None)` | `list, str` | `(str, str)` | 非流式调用 LLM，支持指定模型ID，返回 (内容, 错误) |
| `call_llm_stream(messages, model_id=None)` | `list, str` | `generator` | 流式调用 LLM，支持指定模型ID，yield (内容片段, 错误) |
| `stream_llm_response(messages, model_id=None)` | `list, str` | `generator` | 通用 SSE 流式响应生成器，返回 SSE 格式数据行 |

---

### db/database.py — 数据库管理层

**全局变量：**
| 变量 | 说明 |
|------|------|
| `BASE_DIR` | 项目根目录（向上两级） |
| `DATA_DIR` | `data` 目录 |
| `DB_PATH` | 数据库文件路径，支持 `DB_TOOL_TEST_DB` 环境变量覆盖 |
| `_local` | `threading.local()`，线程安全的连接存储 |

**数据库连接函数：**

| 函数 | 参数 | 返回值 | 说明 |
|------|------|--------|------|
| `get_db()` | 无 | `sqlite3.Connection` | 获取当前线程的数据库连接（懒加载，WAL 模式，外键开启，busy_timeout=5000） |
| `close_db(exception=None)` | `Exception` | 无 | 关闭当前请求的数据库连接（Flask teardown 钩子调用） |
| `init_db()` | 无 | 无 | 初始化所有表结构和索引 |

**配置 CRUD：**

| 函数 | 参数 | 返回值 | 说明 |
|------|------|--------|------|
| `get_config(key, default=None)` | `str, any` | `any` | 获取配置值，自动 JSON 反序列化 |
| `set_config(key, value)` | `str, any` | 无 | 设置配置值，自动 JSON 序列化 |
| `get_all_config()` | 无 | `dict` | 获取所有配置 |

**数据库类型 CRUD：**

| 函数 | 参数 | 返回值 | 说明 |
|------|------|--------|------|
| `DEFAULT_DB_TYPES` | 常量 | `list` | 7 种默认数据库类型（oracle, mysql, tdsql, oceanbase, goldendb, dm, gaussdb） |
| `get_db_types()` | 无 | `list` | 获取数据库类型列表，首次自动初始化默认值 |
| `add_db_type(db_id, name, icon='📁')` | `str, str, str` | `(bool, str)` | 添加新数据库类型 |
| `delete_db_type(db_id)` | `str` | 无 | 删除数据库类型 |

**知识库文件 CRUD：**

| 函数 | 参数 | 返回值 | 说明 |
|------|------|--------|------|
| `get_knowledge_files(db_type, tag=None, keyword=None)` | `str, str, str` | `list` | 按条件获取知识库文件列表 |
| `search_knowledge_content(db_type, keyword)` | `str, str` | `list` | 搜索知识库内容，返回匹配上下文片段 |
| `add_knowledge_file(db_type, filename, file_path, file_size, content_text='', tags=None)` | ... | **`int`** | 添加/更新知识库文件记录，**返回 file_id** |
| `delete_knowledge_file(db_type, filename)` | `str, str` | 无 | 删除知识库文件记录 |
| `get_knowledge_file_path(db_type, filename)` | `str, str` | `str` | 获取文件路径 |
| `get_all_knowledge_files(db_type=None)` | `str` | `list` | 获取所有知识库文件（用于重建索引） |
| `update_knowledge_content(file_id, content_text)` | `int, str` | 无 | 更新文件内容 |

**收藏夹 CRUD：**

| 函数 | 参数 | 返回值 | 说明 |
|------|------|--------|------|
| `get_favorites()` | 无 | `dict` | 获取收藏文件列表 |
| `toggle_favorite(db_type, filename)` | `str, str` | `str` | 切换收藏状态，返回"已收藏"/"取消收藏" |

**问答历史 CRUD：**

| 函数 | 参数 | 返回值 | 说明 |
|------|------|--------|------|
| `get_qa_history(limit=100)` | `int` | `dict` | 获取问答历史 |
| `add_qa_conversation(conv_id, db_type, question, answer)` | ... | 无 | 添加问答记录 |
| `delete_qa_conversation(conv_id)` | `str` | 无 | 删除问答记录 |

**集群拓扑 CRUD：**

| 函数 | 参数 | 返回值 | 说明 |
|------|------|--------|------|
| `get_clusters()` | 无 | `dict` | 获取所有集群（含物理机、实例、租户、关系），使用 JOIN 查询优化 |
| `_fetch_servers_for_cluster(conn, resource_pool_id)` | `sqlite3.Connection, str` | `list` | 获取指定资源池下的所有物理机及其实例 |
| `_fetch_tenants_for_cluster(conn, resource_pool_id)` | `sqlite3.Connection, str` | `list` | 获取指定资源池下的所有租户 |
| `_build_cluster_data(conn, cluster_row)` | `sqlite3.Connection, sqlite3.Row` | `dict` | 构建单个集群的完整数据 |
| `add_resource_pool(pool_id, name, db_type, environment, description)` | `str, str, str, str, str` | 无 | 添加集群/资源池（GET /api/topology/clusters 的顶级实体） |
| `update_resource_pool(pool_id, **kwargs)` | `str, dict` | 无 | 更新集群/资源池信息 |
| `delete_resource_pool(pool_id)` | `str` | 无 | 删除集群/资源池（级联删除其下服务器、二级集群、租户、实例） |
| `add_server(server_id, resource_pool_id, name, host, description, datacenter='', node_role='计算节点', hardware_type='非信创物理机', cpu='', memory='', cluster_id='', sn='')` | ... | 无 | 添加物理机 |
| `delete_server(server_id)` | `str` | 无 | 删除物理机 |
| `add_instance(instance_id, server_id, name, port, cpu, memory, description)` | ... | 无 | 添加实例 |
| `delete_instance(instance_id)` | `str` | 无 | 删除实例 |
| `get_instance_detail(instance_id)` | `str` | `dict` | 获取实例详情（含所属租户） |
| `add_tenant(tenant_id, cluster_id, name, topology_type, description)` | ... | 无 | 添加租户 |
| `delete_tenant(tenant_id)` | `str` | 无 | 删除租户 |
| `add_tenant_instance(tenant_id, instance_id, role)` | ... | 无 | 关联租户和实例 |
| `remove_tenant_instance(tenant_id, instance_id)` | ... | 无 | 移除关联 |
| `add_instance_relation(from_id, to_id, relation_type='replication')` | ... | 无 | 添加实例关系 |
| `remove_instance_relation(from_id, to_id)` | ... | 无 | 移除实例关系 |

**嵌入向量 CRUD：**

| 函数 | 参数 | 返回值 | 说明 |
|------|------|--------|------|
| `save_embeddings(file_id, chunks_with_embeddings)` | `int, list` | 无 | 保存文件的嵌入向量（先删除旧数据） |
| `get_all_embeddings()` | 无 | `list` | 获取所有嵌入向量 |
| `get_embeddings_by_db_type(db_type)` | `str` | `list` | 按数据库类型获取嵌入向量 |
| `get_knowledge_file_by_id(file_id)` | `int` | `dict\|None` | 根据 ID 获取知识库文件信息 |

**操作日志 CRUD：**

| 函数 | 参数 | 返回值 | 说明 |
|------|------|--------|------|
| `add_operation_log(module, action, detail='', status='success', ip='')` | ... | 无 | 添加操作日志，自动保留最近 500 条 |
| `get_operation_logs(limit=50, module=None)` | `int, str` | `list` | 获取操作日志 |
| `clear_operation_logs()` | 无 | 无 | 清空日志 |
| `get_log_modules()` | 无 | `list` | 获取日志模块列表 |

---

### db/migration.py — 数据迁移

**常量：**
| 常量 | 说明 |
|------|------|
| `CONFIG_FILE` | `config.json` |
| `DB_TYPES_FILE` | `db_types.json` |
| `TOPOLOGY_FILE` | `topology.json` |
| `HISTORY_FILE` | `qa_history.json` |
| `FAVORITES_FILE` | `favorites.json` |
| `KNOWLEDGE_DIR` | `data/knowledge` |

**函数：**

| 函数 | 参数 | 返回值 | 说明 |
|------|------|--------|------|
| `_load_json(filepath, default=None)` | `str, any` | `any` | 加载 JSON 文件，不存在返回默认值 |
| `migrate_json_to_sqlite()` | 无 | `bool` | 将旧 JSON 数据迁移到 SQLite（仅首次，已有数据则跳过） |
| `backup_json_files()` | 无 | 无 | 备份原始 JSON 文件到 `data/json_backup/` |

**迁移内容：**
1. 配置（config.json）
2. 数据库类型（db_types.json）
3. 问答历史（qa_history.json）
4. 收藏夹（favorites.json）
5. 集群拓扑基本信息（topology.json）
6. 知识库文件元数据（扫描目录）

---

### routes/__init__.py — Blueprint 导出

导出所有 Blueprint：
- `db_types_bp`
- `knowledge_bp`
- `qa_bp`
- `sql_tools_bp`
- `manuals_bp`
- `commands_bp`
- `topology_bp`
- `config_bp`
- `dashboard_bp`

---

### routes/db_types.py — 数据库类型管理

**Blueprint：** `db_types_bp`

| 路由 | 方法 | 函数 | 说明 |
|------|------|------|------|
| `/api/db-types` | GET | `get_db_types_list()` | 获取数据库类型列表 |
| `/api/db-types` | POST | `add_db_type_api()` | 添加数据库类型 |
| `/api/db-types/<db_id>` | DELETE | `delete_db_type_api(db_id)` | 删除数据库类型 |

---

### routes/knowledge.py — 知识库文件管理

**Blueprint：** `knowledge_bp`

**常量：**
| 常量 | 说明 |
|------|------|
| `KNOWLEDGE_DIR` | `data/knowledge` |
| `PREVIEWABLE_EXTENSIONS` | 可预览的文件扩展名集合 |

**辅助函数：**

| 函数 | 参数 | 返回值 | 说明 |
|------|------|--------|------|
| `can_preview(filename)` | `str` | `bool` | 检查文件是否可预览 |
| `safe_filename(filename)` | `str` | `str` | 安全处理文件名，保留中文 |

**路由：**

| 路由 | 方法 | 函数 | 说明 |
|------|------|------|------|
| `/api/knowledge/files/<db_type>` | GET | `get_files(db_type)` | 获取文件列表，支持 tag/keyword 过滤 |
| `/api/knowledge/upload/<db_type>` | POST | `upload_file(db_type)` | 上传文件，自动解析内容、生成向量嵌入、**提取知识图谱** |
| `/api/knowledge/delete/<db_type>/<filename>` | DELETE | `delete_file(db_type, filename)` | 删除文件 |
| `/api/knowledge/download/<db_type>/<filename>` | GET | `download_file(db_type, filename)` | 下载文件 |
| `/api/knowledge/reindex` | POST | `reindex()` | 全量重建索引（重新解析 + 向量索引 + **知识图谱**） |
| `/api/knowledge/reindex/stream` | GET | `reindex_stream()` | 流式重建索引（逐个文件，SSE 实时进度，10分钟超时，**含知识图谱提取**） |
| `/api/knowledge/reindex/file` | POST | `reindex_single_file()` | 单个文件重建向量索引（**含知识图谱提取**） |
| `/api/knowledge/reindex/db-type` | POST | `reindex_by_db_type()` | 按数据库类型重建向量索引（**含知识图谱提取**） |
| `/api/favorites` | GET | `get_fav()` | 获取收藏夹 |
| `/api/favorites` | POST | `toggle_fav()` | 切换收藏状态 |
| `/api/knowledge/preview/<db_type>/<filename>` | GET | `preview_file(db_type, filename)` | 预览文件内容 |
| `/api/knowledge/tags/<db_type>/<filename>` | PUT | `update_file_tags(db_type, filename)` | 更新文件标签 |

---

### routes/qa.py — 知识问答

**Blueprint：** `qa_bp`

**辅助函数：**

| 函数 | 参数 | 返回值 | 说明 |
|------|------|--------|------|
| `_build_qa_messages(db_type, question, use_rag)` | `str, str, bool` | `list` | 构建 LLM 消息，含 RAG 上下文检索 |

**RAG 流程：**
1. 检查知识库是否有文件
2. 尝试向量检索（sentence-transformers）
3. 向量失败则回退到关键词检索
4. 拼接 top-3 结果作为上下文

**路由：**

| 路由 | 方法 | 函数 | 说明 |
|------|------|------|------|
| `/api/qa/templates` | GET | `get_qa_templates()` | 获取问题模板列表 |
| `/api/qa/history` | GET | `get_history()` | 获取问答历史 |
| `/api/qa/history` | POST | `save_conversation()` | 保存问答记录 |
| `/api/qa/history/<conversation_id>` | DELETE | `delete_conversation(conversation_id)` | 删除单条记录 |
| `/api/qa/history` | DELETE | `clear_history()` | 清空全部历史 |
| `/api/qa/ask` | POST | `ask_question()` | 非流式问答 |
| `/api/qa/ask/stream` | POST | `ask_question_stream()` | 流式问答（SSE），支持 model_id 参数 |

---

### routes/sql_tools.py — SQL 工具

**Blueprint：** `sql_tools_bp`

**辅助函数：**

| 函数 | 参数 | 返回值 | 说明 |
|------|------|--------|------|
| `_stream_response(messages, model_id=None)` | `list, str` | `generator` | 通用流式响应生成器，支持指定模型ID |

**路由（每个功能都有普通和流式两个接口）：**

| 路由 | 方法 | 函数 | 说明 |
|------|------|------|------|
| `/api/sql/format` | POST | `format_sql()` | SQL 格式化 |
| `/api/sql/format/stream` | POST | `format_sql_stream()` | SQL 格式化（流式） |
| `/api/sql/convert` | POST | `convert_sql()` | SQL 方言转换 |
| `/api/sql/convert/stream` | POST | `convert_sql_stream()` | SQL 转换（流式） |
| `/api/sql/explain` | POST | `explain_sql()` | 执行计划分析 |
| `/api/sql/explain/stream` | POST | `explain_sql_stream()` | 执行计划分析（流式） |
| `/api/sql/review` | POST | `review_sql()` | SQL 审核 |
| `/api/sql/review/stream` | POST | `review_sql_stream()` | SQL 审核（流式），支持 model_id 参数 |

---

### routes/log_analysis.py — 日志分析

**Blueprint：** `log_analysis_bp`

**辅助函数：**

| 函数 | 参数 | 返回值 | 说明 |
|------|------|--------|------|
| `_sse_data(data)` | `dict` | `str` | 构建 SSE 数据行 |
| `_extract_json(text)` | `str` | `dict` | 从文本中提取 JSON 对象 |
| `_generate_report(task, intent, filter_result, analysis)` | `dict, dict, dict, dict` | `str` | 生成结构化分析报告（Markdown 格式） |

**分析流程：**
1. **意图识别**：输入用户问题 + 日志文件信息，输出分析方向、重点文件、关键时间范围
2. **日志筛选**：输入完整日志内容 + 意图结果，输出关键日志片段（最多10条）
3. **根因分析**：输入关键日志 + 前两轮结果，输出根因、影响、解决方案
4. **报告生成**：整合所有结果，生成结构化 Markdown 报告

**RAG 增强：**
- 根据任务的数据库类型（`db_type`）查询对应知识库
- 如果没有指定数据库类型，查询系统知识库（`_system`）
- 每轮分析前查询知识库获取参考信息

**路由：**

| 路由 | 方法 | 函数 | 说明 |
|------|------|------|------|
| `/api/log-analysis/tasks` | GET | `get_tasks()` | 获取分析任务列表 |
| `/api/log-analysis/tasks` | POST | `create_task()` | 创建分析任务（支持 db_type 参数） |
| `/api/log-analysis/tasks/<task_id>` | GET | `get_task(task_id)` | 获取单个任务详情 |
| `/api/log-analysis/tasks/<task_id>` | PUT | `update_task(task_id)` | 更新任务状态 |
| `/api/log-analysis/tasks/<task_id>` | DELETE | `delete_task(task_id)` | 删除任务（级联删除关联文件） |
| `/api/log-analysis/upload/<task_id>` | POST | `upload_files(task_id)` | 上传日志文件 |
| `/api/log-analysis/analyze/<task_id>` | POST | `analyze_logs(task_id)` | 执行日志分析（SSE 流式输出） |

**SSE 消息格式：**
```
data: {"stage": "intent", "status": "analyzing", "message": "正在理解问题意图..."}
data: {"stage": "intent", "status": "complete", "result": {...}}
data: {"stage": "filter", "status": "analyzing", "message": "正在筛选关键日志..."}
data: {"stage": "filter", "status": "complete", "result": {...}}
data: {"stage": "analysis", "status": "analyzing", "message": "正在进行根因分析..."}
data: {"stage": "analysis", "status": "complete", "result": {...}}
data: {"stage": "report", "status": "complete", "report": "# 日志分析报告..."}
data: [DONE]
```

---

### routes/manuals.py — 运维手册

**Blueprint：** `manuals_bp`

**常量：**
| 常量 | 说明 |
|------|------|
| `MANUALS_DIR` | `data/manuals` |
| `PREVIEWABLE_EXTENSIONS` | 可预览的文件扩展名集合 |

**路由：**

| 路由 | 方法 | 函数 | 说明 |
|------|------|------|------|
| `/api/manuals` | GET | `get_manuals()` | 获取手册列表 |
| `/api/manuals` | POST | `upload_manual()` | 上传手册 |
| `/api/manuals/<filename>` | DELETE | `delete_manual(filename)` | 删除手册 |
| `/api/manuals/<filename>` | GET | `download_manual(filename)` | 下载手册 |
| `/api/manuals/preview/<filename>` | GET | `preview_manual(filename)` | 预览手册内容 |

---

### routes/commands.py — 命令速查

**Blueprint：** `commands_bp`

**常量：** 默认命令模板（MySQL、Oracle、达梦、OceanBase、GoldenDB、TDSQL、GaussDB）

**辅助函数：**

| 函数 | 参数 | 返回值 | 说明 |
|------|------|--------|------|
| `_load_commands_file(db_type)` | `str` | `dict` | 加载自定义命令 JSON 文件 |
| `_save_commands_file(db_type, data)` | `str, dict` | 无 | 保存自定义命令 |
| `get_default_commands(db_type)` | `str` | `list` | 获取默认命令模板 |

**路由：**

| 路由 | 方法 | 函数 | 说明 |
|------|------|------|------|
| `/api/commands` | GET | `get_commands()` | 获取命令列表（优先自定义，其次默认） |
| `/api/commands` | POST | `save_commands()` | 保存自定义命令 |
| `/api/commands/category` | POST | `add_category()` | 添加命令分类 |
| `/api/commands/command` | POST | `add_command()` | 添加命令 |
| `/api/commands/command` | DELETE | `delete_command()` | 删除命令 |
| `/api/commands/search` | GET | `search_commands()` | 跨库搜索命令 |

---

### routes/topology.py — 集群拓扑

**Blueprint：** `topology_bp`

**路由：**

| 路由 | 方法 | 函数 | 说明 |
|------|------|------|------|
| `/api/topology/clusters` | GET | `get_clusters_list()` | 获取所有集群 |
| `/api/topology/stats` | GET | `get_topology_stats()` | 获取集群拓扑统计聚合数据 |
| `/api/topology/clusters` | POST | `create_cluster()` | 添加集群 |
| `/api/topology/clusters/<cluster_id>` | PUT | `update_cluster_info(cluster_id)` | 更新集群 |
| `/api/topology/clusters/<cluster_id>` | DELETE | `delete_cluster_info(cluster_id)` | 删除集群 |
| `/api/topology/clusters/<cluster_id>/servers` | POST | `create_server(cluster_id)` | 添加物理机 |
| `/api/topology/servers/<server_id>` | DELETE | `delete_server_info(server_id)` | 删除物理机 |
| `/api/topology/servers/<server_id>` | PUT | `update_server_info(server_id)` | 更新物理机 |
| `/api/topology/servers/<server_id>/instances` | POST | `create_instance(server_id)` | 添加实例 |
| `/api/topology/instances/<instance_id>` | DELETE | `delete_instance_info(instance_id)` | 删除实例 |
| `/api/topology/instances/<instance_id>` | GET | `get_instance_info(instance_id)` | 获取实例详情 |
| `/api/topology/instances/<instance_id>` | PUT | `update_instance_info(instance_id)` | 更新实例 |
| `/api/topology/clusters/<cluster_id>/tenants` | POST | `create_tenant(cluster_id)` | 添加租户 |
| `/api/topology/tenants/<tenant_id>` | DELETE | `delete_tenant_info(tenant_id)` | 删除租户 |
| `/api/topology/tenants/<tenant_id>` | PUT | `update_tenant_info(tenant_id)` | 更新租户 |
| `/api/topology/instances/relations` | POST | `create_instance_relation()` | 添加实例关系 |
| `/api/topology/instances/relations` | DELETE | `delete_instance_relation()` | 删除实例关系 |
| `/api/topology/export` | GET | `export_topology()` | 导出拓扑配置 |
| `/api/topology/import/servers` | POST | `import_servers()` | 批量导入服务器清单 |
| `/api/topology/import/instances` | POST | `import_instances()` | 批量导入实例清单 |
| `/api/topology/import` | POST | `import_topology()` | 一键导入完整拓扑 |

---

### routes/config.py — 系统配置

**Blueprint：** `config_bp`

**路由：**

| 路由 | 方法 | 函数 | 说明 |
|------|------|------|------|
| `/api/config/llm` | GET | `get_llm_config()` | 获取 LLM 配置（api_key 掩码显示） |
| `/api/config/llm` | POST | `save_llm_config()` | 保存 LLM 配置 |
| `/api/config/test` | POST | `test_connection()` | 测试 LLM 连接 |
| `/api/config/features` | GET | `get_features()` | 获取功能配置列表 |
| `/api/config/features/<module_id>` | PUT | `update_feature(module_id)` | 更新功能配置（启用/禁用模块） |
| `/api/config/export` | GET | `export_config()` | 导出配置（类型、拓扑、收藏夹） |
| `/api/config/import` | POST | `import_config()` | 导入配置 |
| `/api/config/docs/<filename>` | GET | `get_doc_content(filename)` | 读取项目文档（PROJECT.md / version_update.md） |

---

### routes/dashboard.py — 仪表盘

**Blueprint：** `dashboard_bp`

**常量：**
| 常量 | 说明 |
|------|------|
| `KNOWLEDGE_TAGS` | 8 种知识库标签定义（id, name, color, icon） |
| `SHORTCUTS` | 12 个快捷键定义 |

**路由：**

| 路由 | 方法 | 函数 | 说明 |
|------|------|------|------|
| `/api/stats` | GET | `get_stats()` | 获取系统统计数据（含 embeddings_by_db_type 向量索引统计） |
| `/api/health` | GET | `health_check()` | 系统健康检查 |
| `/api/shortcuts` | GET | `get_shortcuts()` | 获取快捷键列表 |
| `/api/tags` | GET | `get_tags()` | 获取知识库标签列表 |
| `/api/logs` | GET | `get_logs()` | 获取操作日志 |
| `/api/logs` | DELETE | `clear_logs()` | 清空日志 |
| `/api/logs/modules` | GET | `get_log_modules()` | 获取日志模块列表 |

---

### agent/harness.py — 安全约束框架

**类：** `Harness`

| 方法 | 参数 | 返回值 | 说明 |
|------|------|--------|------|
| `validate_sql(sql, level)` | `str, OperationLevel` | `(bool, str)` | 验证SQL安全性（剥离注释后逐语句白名单+危险关键字扫描） |
| `validate_command(command, db_type, level)` | `str, str, OperationLevel` | `(bool, str)` | 验证命令安全性（级别门槛+动作词+危险特征） |
| `get_allowed_commands(db_type)` | `str` | `Dict` | 获取命令策略（命令名 → 级别/动作词） |
| `get_allowed_sql_types(level)` | `OperationLevel` | `set` | 获取允许的SQL类型 |

**安全级别：**
- `READONLY`: 只读查询（SELECT, EXPLAIN, DESCRIBE, SHOW）
- `DIAGNOSIS`: 诊断级（+ ALTER SESSION, SET）
- `MAINTENANCE`: 维护级（+ ANALYZE）
- `DANGEROUS`: 危险操作（DROP, DELETE, UPDATE, INSERT 等）

---

### agent/skills.py — 领域知识与操作指南

**类：** `SkillManager`

| 方法 | 参数 | 返回值 | 说明 |
|------|------|--------|------|
| `get_skill(name)` | `str` | `Dict\|None` | 获取指定技能 |
| `find_skills(db_type, category)` | `str, str` | `List[Dict]` | 按条件查找技能 |
| `match_skills_by_intent(question, db_type)` | `str, str` | `List[Dict]` | 根据用户意图匹配技能 |
| `get_all_skills()` | 无 | `List[Dict]` | 获取所有技能 |
| `add_skill(skill)` | `Dict` | 无 | 添加自定义技能 |
| `remove_skill(name)` | `str` | `bool` | 移除技能 |

**内置技能（6个）：**
1. 慢查询诊断（MySQL）
2. Oracle集群状态检查
3. 数据库备份检查
4. MySQL性能分析
5. Oracle AWR报告分析
6. 达梦数据库状态检查

---

### agent/state.py — Agent状态管理

**枚举：** `AgentStatus`（idle/running/completed/error/cancelled）
**枚举：** `AgentPhase`（thinking/retrieving/planning/executing/observing/concluding）

**类：** `AgentState`

| 方法 | 说明 |
|------|------|
| `add_step(phase, thought, action, observation, knowledge_refs)` | 添加执行步骤 |
| `next_step()` | 进入下一步 |
| `set_status(status)` | 设置状态 |
| `set_error(error)` | 设置错误 |
| `add_message(role, content)` | 添加对话历史 |
| `to_dict()` | 序列化为字典 |
| `get_summary()` | 获取执行摘要 |

---

### agent/tools.py — MCP风格工具定义

**装饰器：** `register_tool(name, description, parameters)`

**已注册工具（5个，真实执行）：**
1. `query_database` — 执行SQL查询（只读，需 DB 连接，双重安全校验）
2. `execute_command` — 通过SSH执行白名单数据库命令（需 SSH 连接）
3. `get_schema_info` — 获取数据库Schema信息（表清单/表结构，按 db_type 生成查询）
4. `get_performance_metrics` — 获取性能指标（sessions/locks/waits/sql_stats/table_stats）
5. `retrieve_knowledge` — 从知识库检索相关文档（向量相似度）

**工具执行上下文：** `ToolContext(db_conn_id, ssh_conn_id, db_type, operation_level)`，由引擎 `_execute_action` 注入，`execute_tool(tool_name, parameters, ctx)`。

**连接器 `agent/connectors.py`：**
| 函数 | 说明 |
|------|------|
| `load_db_conn(db_conn_id)` | 加载 DB 连接配置并解密密码 |
| `load_ssh_conn(ssh_conn_id)` | 加载 SSH 连接配置并解密凭据 |
| `run_sql(conn_info, sql, max_rows, timeout)` | 按 db_type 分发到 pymysql/oracledb/psycopg2/dmPython 执行 |
| `run_ssh_command(conn_info, command, timeout)` | paramiko 执行命令，返回 stdout/stderr/exit_code |
| `build_schema_query(db_type, table_name)` | 生成只读 schema 查询（表名经 `_safe_identifier` 白名单校验） |
| `build_metric_query(db_type, metric_type)` | 生成只读性能指标查询 |

> 驱动依赖（deploy.md）：pymysql / oracledb / psycopg2-binary / paramiko；dmPython 可选。缺失时工具返回提示而非崩溃。

| 函数 | 说明 |
|------|------|
| `get_tool_schemas()` | 获取所有工具的JSON Schema |
| `execute_tool(tool_name, parameters, ctx=None)` | 执行指定工具（ctx 为 ToolContext） |
| `get_tool_names()` | 获取所有工具名称 |

---

### agent/engine.py — Agent核心引擎

**类：** `SmartOpsAgent`

| 方法 | 说明 |
|------|------|
| `run_stream(user_question)` | ReAct主循环（流式输出Generator，观察结果经对话历史回流实现链式推理） |
| `_retrieve_knowledge_strict(query)` | 严格检索知识库（阈值 0.55/0.60，返回含 chunk_ids） |
| `_retrieve_kg_context(query, chunk_ids)` | 基于检索 chunk 获取知识图谱上下文（enhance_qa_context） |
| `_build_system_prompt(knowledge_refs, skills, kg_context)` | 构建system prompt（注入知识库+知识图谱+Skills） |
| `_think(system_prompt)` | LLM思考（基于完整对话历史） |
| `_decide_action(thought)` | 提取工具调用 JSON（容错代码围栏/嵌套括号/字符串内大括号） |
| `_validate_action(action)` | 验证动作安全性 |
| `_verify_knowledge_support(action, knowledge_refs)` | 验证操作是否有知识库支撑 |
| `_execute_action(action)` | 执行工具（注入 ToolContext） |
| `_format_result(result)` | 格式化执行结果 |
| `_is_complete(observation)` | 判断任务是否完成 |
| `_conclude(knowledge_refs)` | 生成最终结论 |
| `get_state()` | 获取Agent状态 |

**ReAct事件类型：**
- `retrieving_start` — 开始检索知识库
- `knowledge_refs` — 知识库引用
- `knowledge_warning` — 知识库不足警告
- `thinking_start/thinking_chunk/thinking_end` — 思考过程
- `planning` — 制定计划
- `executing_start/executing_end/executing_error/executing_warning` — 执行过程
- `observing` — 观察结果
- `concluding_start/concluding_chunk/concluding_end` — 总结结论
- `done` — 完成

---

### routes/agent.py — Agent核心API

**Blueprint：** `agent_bp`

| 路由 | 方法 | 函数 | 说明 |
|------|------|------|------|
| `/api/agent/sessions` | GET | `list_sessions()` | 获取会话列表 |
| `/api/agent/sessions` | POST | `create_session()` | 创建会话 |
| `/api/agent/sessions/<session_id>` | GET | `get_session(session_id)` | 获取会话详情 |
| `/api/agent/sessions/<session_id>` | DELETE | `delete_session(session_id)` | 删除会话 |
| `/api/agent/run` | POST | `run_agent()` | 启动Agent任务（SSE流式） |
| `/api/agent/sessions/<session_id>/steps` | GET | `get_session_steps(session_id)` | 获取执行步骤 |
| `/api/agent/skills` | GET | `list_skills()` | 获取Skills列表 |
| `/api/agent/skills/<skill_name>` | GET | `get_skill(skill_name)` | 获取Skill详情 |
| `/api/agent/tools` | GET | `list_tools()` | 获取可用工具列表 |

---

### routes/agent_connections.py — 连接管理API

**Blueprint：** `agent_conn_bp`

| 路由 | 方法 | 函数 | 说明 |
|------|------|------|------|
| `/api/agent/ssh-connections` | GET | `list_ssh_connections()` | 获取SSH连接列表 |
| `/api/agent/ssh-connections` | POST | `create_ssh_connection()` | 创建SSH连接 |
| `/api/agent/ssh-connections/<conn_id>` | DELETE | `delete_ssh_connection(conn_id)` | 删除SSH连接 |
| `/api/agent/ssh-connections/<conn_id>/test` | POST | `test_ssh_connection(conn_id)` | 测试SSH连接 |
| `/api/agent/db-connections` | GET | `list_db_connections()` | 获取数据库连接列表 |
| `/api/agent/db-connections` | POST | `create_db_connection()` | 创建数据库连接 |
| `/api/agent/db-connections/<conn_id>` | DELETE | `delete_db_connection(conn_id)` | 删除数据库连接 |
| `/api/agent/db-connections/<conn_id>/test` | POST | `test_db_connection(conn_id)` | 测试数据库连接 |

---

### rag/embedder.py — 向量检索

**全局变量：**
| 变量 | 说明 |
|------|------|
| `_model` | 懒加载的 sentence-transformers 模型 |
| `_model_lock` | 线程锁，防止并发加载 |
| `_model_load_failed` | 标记模型加载是否失败 |
| `MODEL_NAME` | `'moka-ai/m3e-base'` | 默认嵌入模型（中文语义理解更优） |

**辅助函数：**

| 函数 | 参数 | 返回值 | 说明 |
|------|------|--------|------|
| `_check_model_cached(cache_dir)` | `str` | `bool` | 检查模型是否已在本地缓存中存在 |
| `_get_model()` | 无 | `SentenceTransformer` | 懒加载模型，检测到本地缓存时跳过网络下载，失败返回 None |
| `chunk_text(text, chunk_size=2000, overlap=100)` | `str, int, int` | `list` | 将文本分块（段落优先，超长二次切分） |
| `_embedding_to_bytes(embedding)` | `np.ndarray` | `bytes` | numpy 数组转 bytes（float32） |
| `_bytes_to_embedding(data)` | `bytes` | `np.ndarray` | bytes 还原 numpy 数组 |

**Embedder 类：**

| 方法 | 参数 | 返回值 | 说明 |
|------|------|--------|------|
| `embed_chunks(chunks)` | `list` | `list` | 批量计算文本块嵌入向量 |
| `embed_query(query)` | `str` | `np.ndarray` | 计算查询文本的嵌入向量 |
| `similarity_search(query, db_type=None, top_k=5)` | `str, str, int` | `list` | 向量相似度搜索，返回 top_k 结果 |
| `rebuild_all(db_type=None, extract_kg=True)` | `str, bool` | `int` | 重建所有知识库文件的向量索引，**默认同时提取知识图谱** |
| `rebuild_single(file_id, db_type, filepath, extract_kg=True)` | `int, str, str, bool` | `bool` | 重建单个文件的向量索引，**默认同时提取知识图谱** |

---

## 前端文件详解

### templates/index.html — 单页应用

**结构：**
- 左侧导航栏（8 个模块 + 主题切换按钮 + 统计信息）
- 右侧内容区（8 个 module div，通过 `style="display: none"` 控制显示）
- 多个模态框（添加集群/物理机/实例/命令/数据库类型等）
- Toast 消息提示

**引入的 JS 文件（按依赖顺序）：**
```html
<script src="/static/js/utils.js"></script>      <!-- 通用工具 -->
<script src="/static/js/api.js"></script>         <!-- API 封装 -->
<script src="/static/js/knowledge.js"></script>  <!-- 知识库 -->
<script src="/static/js/qa.js"></script>        <!-- 问答 -->
<script src="/static/js/sql-tools.js"></script>  <!-- SQL 工具 -->
<script src="/static/js/manuals.js"></script>   <!-- 运维手册 -->
<script src="/static/js/commands.js"></script>   <!-- 命令速查 -->
<script src="/static/js/topology.js"></script>   <!-- 集群拓扑 -->
<script src="/static/js/config.js"></script>     <!-- 系统配置 -->
<script src="/static/js/app.js"></script>        <!-- 入口文件 -->
```

**主题切换按钮：**
```html
<div class="theme-toggle">
    <button class="theme-toggle-btn" id="theme-toggle-btn" onclick="toggleTheme()">
        <span id="theme-icon">🌙</span>
        <span id="theme-text">暗色模式</span>
    </button>
</div>
```

**版本号：**
- CSS: `v2.2.0`
- JS: `v2.2.0`

---

### static/css/style.css — 样式

**CSS 变量系统：**
- `:root` — 亮色主题变量（默认）
- `[data-theme="dark"]` — 暗色主题变量覆盖

**变量类别：**
| 类别 | 前缀 | 说明 |
|------|------|------|
| 背景色 | `--bg-*` | body、module、card、input 等 |
| 文字色 | `--text-*` | primary、secondary、muted、heading 等 |
| 边框色 | `--border-*` | color、focus、light 等 |
| 阴影 | `--shadow-*` | module、card、btn、hover 等 |
| 按钮 | `--btn-*` | primary、secondary、danger 背景色 |
| 统计卡片 | `--stat-card-*` | 5 种渐变配色 |

**关键特性：**
- 所有颜色通过 CSS 变量定义
- `transition: ... 0.3s ease` 实现平滑主题切换
- 暗色主题采用 GitHub Dark 风格配色

---

### static/js/app.js — 前端入口文件

**全局命名空间：**

| 对象 | 说明 |
|------|------|
| `DBTool` | 全局命名空间，封装所有全局状态和方法 |

**DBTool 属性：**

| 属性 | 类型 | 说明 |
|------|------|------|
| `currentModule` | `string` | 当前激活的模块（默认 'knowledge'） |
| `dbTypes` | `array` | 数据库类型列表 |
| `currentClusterId` | `string|null` | 当前选中的集群 ID |
| `topologyNetwork` | `object|null` | vis-network 拓扑图实例 |

**初始化函数：**

| 函数 | 说明 |
|------|------|
| `initTheme()` | 从 localStorage 加载保存的主题 |
| `toggleTheme()` | 切换亮色/暗色主题，保存到 localStorage |
| `updateThemeUI(isDark)` | 更新主题切换按钮的图标和文字 |
| `initNavigation()` | 初始化导航栏点击事件 |
| `switchModule(module)` | 切换模块，加载对应数据 |
| `loadDBTypes()` | 加载数据库类型，填充所有下拉框 |
| `loadModelSelects()` | 加载模型列表到知识问答和 SQL 工具的下拉框 |

**仪表盘模块函数：**

| 函数 | 说明 |
|------|------|
| `loadDashboard()` | 加载仪表盘数据 |
| `renderDBChart(byDbType)` | 渲染知识库分布图表 |
| `loadRecentLogs()` | 加载最近操作日志 |
| `loadSystemHealth()` | 加载系统健康状态 |

**通用函数：**

| 函数 | 说明 |
|------|------|
| `showToast(message, type)` | 显示消息提示 |
| `closeModal(modalId)` | 关闭模态框 |
| `escapeHtml(text)` | HTML 特殊字符转义 |
| `escapeJs(text)` | JS 字符串转义 + HTML 特殊字符转义（用于内联事件参数） |
| `formatFileSize(bytes)` | 将字节数格式化为 KB/MB/GB |

---

### static/js/utils.js — 通用工具函数

| 函数 | 说明 |
|------|------|
| `showToast(message, type)` | 显示 Toast 消息提示 |
| `escapeHtml(text)` | HTML 特殊字符转义 |
| `escapeJs(text)` | JS 字符串转义 + HTML 特殊字符转义 |
| `formatFileSize(bytes)` | 格式化文件大小 |
| `copyText(text)` | 复制文本到剪贴板 |

---

### static/js/api.js — API 请求封装

| 函数 | 参数 | 返回值 | 说明 |
|------|------|--------|------|
| `apiGet(url)` | `str` | `Promise<json>` | GET 请求，支持非 JSON 响应处理 |
| `apiPost(url, data)` | `str, object` | `Promise<json>` | POST 请求 |
| `apiPut(url, data)` | `str, object` | `Promise<json>` | PUT 请求 |
| `apiDelete(url, data)` | `str, object` | `Promise<json>` | DELETE 请求 |
| `apiPostStream(url, body, signal)` | `str, object, AbortSignal` | `Promise<ReadableStreamDefaultReader>` | 发送流式 POST 请求 |
| `parseSSEData(line)` | `str` | `object|null` | 解析 SSE 数据行 |
| `readSSEStream(reader, onData, onError, onDone)` | `ReadableStreamDefaultReader, function, function, function` | `Promise<void>` | 读取 SSE 流并逐行处理 |

---

### static/js/knowledge.js — 知识库模块

| 函数 | 说明 |
|------|------|
| `loadFileList()` | 加载文件列表 |
| `searchKnowledge()` | 搜索知识库内容 |
| `uploadFile()` | 上传文件 |
| `deleteFile(db_type, filename)` | 删除文件 |
| `downloadFile(db_type, filename)` | 下载文件 |
| `previewFile(db_type, filename)` | 预览文件 |
| `editFileTags(index)` | 编辑文件标签 |
| `reindexKnowledge()` | 重建索引（**流式进度，含知识图谱提取**） |
| `switchKnowledgeView(view)` | **切换知识库视图（files/graph）** |
| `renderTags(tags)` | 渲染标签徽章 |
| `getFavorites()` | 获取收藏夹 |
| `toggleFavorite(db_type, filename)` | 切换收藏 |

---

### static/js/qa.js — 知识问答模块

| 函数 | 说明 |
|------|------|
| `loadQAHistory()` | 加载问答历史 |
| `loadQATemplates()` | 加载问题模板 |
| `applyTemplate()` | 应用问题模板 |
| `sendQuestion()` | 发送问题（支持流式输出和模型切换） |
| `stopStreaming()` | 停止流式输出 |
| `clearChat()` | 清空聊天记录 |
| `renderMarkdown(text)` | 渲染 Markdown |

---

### static/js/sql-tools.js — SQL 工具模块

| 函数 | 说明 |
|------|------|
| `switchSqlTab(tab)` | 切换 SQL 工具标签 |
| `reviewSQL()` | SQL 审核（支持模型切换） |
| `formatSQL()` | SQL 格式化 |
| `convertSQL()` | SQL 方言转换 |
| `analyzeExplain()` | 执行计划分析 |
| `clearSQL()` | 清空 SQL 输入 |
| `copyToClipboard(elementId)` | 复制到剪贴板 |

---

### static/js/manuals.js — 运维手册模块

| 函数 | 说明 |
|------|------|
| `loadManuals()` | 加载手册列表 |
| `uploadManual()` | 上传手册 |
| `deleteManual(filename)` | 删除手册 |
| `downloadCurrentManual()` | 下载当前手册 |
| `deleteCurrentManual()` | 删除当前手册 |
| `loadManualContent(filename)` | 加载手册内容 |

---

### static/js/commands.js — 命令速查模块

| 函数 | 说明 |
|------|------|
| `loadCommands()` | 加载命令列表 |
| `searchCommands()` | 搜索命令 |
| `showAddCategoryDialog()` | 显示添加分类对话框 |
| `addCategory()` | 添加分类 |
| `showAddCommandDialog()` | 显示添加命令对话框 |
| `addCommand()` | 添加命令 |
| `deleteCommand(category, index)` | 删除命令 |
| `showDeleteBtn(element)` | 显示删除按钮（鼠标移入） |
| `hideDeleteBtn(element)` | 隐藏删除按钮（鼠标移出） |
| `copyCommand(cmd)` | 复制命令到剪贴板 |

---

### static/js/topology.js — 集群拓扑模块

| 函数 | 说明 |
|------|------|
| `loadClusters()` | 加载集群列表（拓扑视图） |
| `selectCluster(clusterId)` | 选中集群并渲染拓扑图 |
| `renderTopology(cluster)` | 渲染拓扑图（HTML 渲染，按机房分组），支持空集群显示操作按钮 |
| `switchTopologyTab(tab)` | 切换统计视图/拓扑视图 |
| `loadTopologyStats()` | 加载统计视图数据 |
| `renderOverviewCards(overview)` | 渲染总览卡片 |
| `renderHardwareChart(hardwareStats)` | 渲染硬件类型分布图 |
| `renderNodeRoleChart(nodeRoleStats)` | 渲染节点角色分布图 |
| `renderDatacenterChart(datacenterStats)` | 渲染数据中心分布图 |
| `renderClusterStatsTable(clusterStats)` | 渲染集群统计表格 |
| `renderServerTable(servers)` | 渲染服务器列表表格 |
| `updateStatsFilterOptions(data)` | 更新筛选下拉框选项 |
| `resetStatsFilter()` | 重置筛选条件 |
| `showAddResourcePoolDialog()` | 显示添加资源池对话框 |
| `addCluster()` | 添加集群 |
| `deleteCluster(clusterId)` | 删除集群 |
| `editClusterName(clusterId, currentName)` | 编辑集群名称 |
| `showAddServerDialog()` | 显示添加物理机对话框 |
| `addServer()` | 添加物理机 |
| `deleteServer(serverId)` | 删除物理机 |
| `showEditServerDialog(...)` | 显示编辑物理机对话框（支持 SN 序列号） |
| `updateServer()` | 更新物理机（支持 cluster_name 自动创建/查找集群） |
| `showAddInstanceDialog()` | 显示添加实例对话框 |
| `addInstance()` | 添加实例 |
| `deleteInstance(instanceId)` | 删除实例 |
| `showEditInstanceDialog(...)` | 显示编辑实例对话框 |
| `updateInstance()` | 更新实例 |
| `loadTenantSelectForInstance(instanceId)` | 加载租户选择下拉框 |
| `exportTopology()` | 导出拓扑配置 |
| `closeDetailPanel()` | 关闭详情面板 |

**全局配置对象：**

| 对象 | 说明 |
|------|------|
| `nodeTypeConfig` | 节点类型配置（计算节点/存储节点/监控节点/虚拟机/海光/鲲鹏） |
| `hardwareTypeConfig` | 硬件类型配置（非信创物理机/信创物理机/非信创虚拟机/信创虚拟机） |

---

### static/js/agent.js — 智能运维Agent模块

| 函数 | 说明 |
|------|------|
| `initAgentModule()` | 初始化Agent模块 |
| `loadAgentSSHConnections()` | 加载SSH连接列表 |
| `loadAgentDBConnections()` | 加载数据库连接列表 |
| `renderAgentSSHConnections()` | 渲染SSH连接列表 |
| `renderAgentDBConnections()` | 渲染数据库连接列表 |
| `selectSSHConnection(connId)` | 选择SSH连接 |
| `selectDBConnection(connId)` | 选择数据库连接 |
| `updateAgentConnectionStatus()` | 更新连接状态显示 |
| `switchAgentTab(tab)` | 切换SSH/DB标签 |
| `loadAgentSessions()` | 加载Agent会话列表 |
| `renderAgentSessions()` | 渲染会话列表 |
| `newAgentSession()` | 创建新会话 |
| `loadAgentSession(sessionId)` | 加载会话详情 |
| `sendAgentQuestion()` | 发送问题（SSE流式） |
| `handleAgentEvent(event)` | 处理SSE事件 |
| `addAgentMessage(role, content)` | 添加消息到聊天区 |
| `renderKnowledgeRefs(refs)` | 渲染知识库引用 |
| `renderKnowledgeWarning(message)` | 渲染知识库警告 |
| `showAgentThinking(step)` | 显示思考中指示器 |
| `appendAgentThinking(content)` | 追加思考内容 |
| `finalizeAgentThinking()` | 完成思考 |
| `renderAgentToolCall(tool, params)` | 渲染工具调用 |
| `renderAgentResult(result)` | 渲染执行结果 |
| `renderAgentObservation(observation)` | 渲染观察结果 |
| `showAgentConclusion()` | 显示结论区域 |
| `appendAgentConclusion(content)` | 追加结论内容 |
| `finalizeAgentConclusion()` | 完成结论 |
| `renderAgentError(error)` | 渲染错误信息 |
| `renderAgentWarning(warning)` | 渲染警告信息 |
| `clearAgentChat()` | 清空聊天区 |
| `renderAgentStep(step)` | 渲染历史步骤 |

**全局变量：**
| 变量 | 说明 |
|------|------|
| `agentCurrentSession` | 当前会话ID |
| `agentSSHConnections` | SSH连接列表 |
| `agentDBConnections` | 数据库连接列表 |
| `agentSessions` | 会话列表 |
| `agentIsRunning` | 是否正在执行 |
| `agentCurrentSSHConn` | 当前选中的SSH连接 |
| `agentCurrentDBConn` | 当前选中的数据库连接 |

---

### static/js/config.js — 系统配置模块

| 函数 | 说明 |
|------|------|
| `switchConfigTab(tab)` | 切换配置标签 |
| `loadConfig()` | 加载模型配置列表 |
| `renderModelsList()` | 渲染模型配置卡片列表 |
| `showAddModelDialog()` | 显示添加模型对话框 |
| `hideModelForm()` | 隐藏模型表单 |
| `editModel(modelId)` | 编辑模型配置 |
| `saveModelConfig()` | 保存模型配置 |
| `deleteModel(modelId)` | 删除模型配置 |
| `setDefaultModel(modelId)` | 设置默认模型 |
| `testModelConnection(modelId)` | 测试指定模型的连接 |
| `loadDBTypesPage()` | 加载数据库类型管理页 |
| `showAddDBTypeDialog()` | 显示添加数据库类型对话框 |
| `addDBType()` | 添加数据库类型 |
| `deleteDBType(dbId)` | 删除数据库类型 |
| `exportConfig()` | 导出配置 |
| `importConfig()` | 导入配置 |
| `loadLogs()` | 加载操作日志 |
| `clearLogs()` | 清空日志 |
| `loadProjectDoc()` | 加载项目说明文档 |
| `loadChangelog()` | 加载更新日志 |

---

### static/js/log-analysis.js — 日志分析模块

| 函数 | 说明 |
|------|------|
| `loadLogAnalysis()` | 加载日志分析任务列表 |
| `showNewAnalysisDialog()` | 显示新建分析对话框（含数据库类型选择） |
| `createAnalysisTask()` | 创建分析任务（传递 db_type 参数） |
| `startAnalysis(taskId)` | 启动 SSE 连接，实时显示分析进度 |
| `handleAnalysisEvent(data, taskId)` | 处理 SSE 事件，更新进度步骤和时间 |
| `updateProgressStep(stage, status, message, taskId)` | 更新单个步骤的进度状态和时间 |
| `resetProgressSteps()` | 重置所有进度步骤为初始状态 |
| `restoreProgressSteps(taskId)` | 恢复之前记录的进度状态 |
| `viewTaskProgress(taskId)` | 查看任务进度（支持重新进入时恢复状态） |
| `viewTaskReport(taskId)` | 查看分析报告 |
| `generateTimingHtml(task)` | 生成耗时统计 HTML |
| `deleteAnalysisTask(taskId)` | 删除分析任务 |
| `isViewingProgressOrReport()` | 检查当前是否在查看进度或报告页面 |
| `getTaskStepData(taskId)` | 获取任务独立的步骤数据 |
| `clearTaskStepData(taskId)` | 清除任务的步骤数据 |

**全局变量：**
| 变量 | 说明 |
|------|------|
| `currentAnalysisTaskId` | 当前正在分析的任务 ID |
| `currentAnalysisAbortController` | AbortController 实例，用于取消 SSE 请求 |
| `taskStepData` | 每个任务的步骤时间记录（独立存储，避免多任务冲突） |

---

## 数据库表结构

> 📌 **开发前必读：** 修改涉及数据库的代码前，请先阅读 `tables_desc.md` 确认表结构。

| 表名 | 用途 | 关键字段 |
|------|------|----------|
| `config` | 键值对配置 | key, value |
| `db_types` | 数据库类型定义 | id, name, icon |
| `knowledge_files` | 知识库文件元数据 + 内容 | db_type, filename, file_path, file_size, content_text, tags |
| `qa_history` | 问答历史记录 | id, db_type, question, answer, created_at |
| `favorites` | 文件收藏 | db_type, filename |
| `resource_pools` | 资源池信息 | id, name, db_type, environment, description |
| `clusters` | 集群信息（属于某个资源池） | id, **resource_pool_id**, name, db_type, environment, description |
| `servers` | 物理机/节点（含 CPU、内存、机房等） | id, resource_pool_id, cluster_id, name, host, datacenter, node_role, hardware_type, cpu, memory, description |
| `instances` | 实例 | id, server_id, tenant_id, name, port, cpu, memory, role, tenant_role, description |
| `tenants` | 租户（实例集群） | id, resource_pool_id, cluster_id, name, topology_type, spec, description |
| `instance_relations` | 实例间关系 | from_instance_id, to_instance_id, relation_type |
| `embeddings` | 文本块向量嵌入 | file_id, chunk_index, chunk_text, embedding |
| `operation_logs` | 操作日志 | id, timestamp, module, action, detail, status, ip |
| `feature_config` | 功能配置（模块开关） | module_id, module_name, module_icon, is_enabled, sort_order |
| `log_analysis_tasks` | 日志分析任务 | id, name, question, db_type, status, current_stage, stages, report, created_at, completed_at |
| `log_analysis_files` | 日志分析文件 | id, task_id, filename, file_path, file_size, content_text, is_key_log |
| `agent_ssh_connections` | SSH连接配置 | id, name, host, port, username, auth_type, db_type, os_type, status |
| `agent_db_connections` | 数据库连接配置 | id, name, ssh_connection_id, db_type, host, port, username, database, sid, service_name |
| `agent_sessions` | Agent会话 | id, title, ssh_connection_id, db_connection_id, status, current_step, max_steps |
| `agent_steps` | Agent执行步骤 | id, session_id, step_number, phase, thought, action, observation, knowledge_refs |
| `agent_skills` | Agent技能 | id, name, db_type, category, description, prompt_template, required_tools, knowledge_tags |

---

## API 路由总览

### 数据库类型
- `GET /api/db-types` — 获取类型列表
- `POST /api/db-types` — 添加类型
- `DELETE /api/db-types/<db_id>` — 删除类型

### 知识库
- `GET /api/knowledge/files/<db_type>?tag=&keyword=` — 获取文件列表
- `POST /api/knowledge/upload/<db_type>` — 上传文件
- `DELETE /api/knowledge/delete/<db_type>/<filename>` — 删除文件
- `GET /api/knowledge/download/<db_type>/<filename>` — 下载文件
- `POST /api/knowledge/reindex` — 重建索引
- `GET /api/knowledge/preview/<db_type>/<filename>` — 预览文件
- `PUT /api/knowledge/tags/<db_type>/<filename>` — 更新标签

### 收藏夹
- `GET /api/favorites` — 获取收藏
- `POST /api/favorites` — 切换收藏

### 知识问答
- `GET /api/qa/templates` — 获取模板
- `GET /api/qa/history` — 获取历史
- `POST /api/qa/history` — 保存记录
- `DELETE /api/qa/history/<id>` — 删除记录
- `DELETE /api/qa/history` — 清空历史
- `POST /api/qa/ask` — 非流式问答
- `POST /api/qa/ask/stream` — 流式问答（SSE）

### SQL 工具
- `POST /api/sql/format` — SQL 格式化
- `POST /api/sql/format/stream` — 格式化（流式）
- `POST /api/sql/convert` — SQL 转换
- `POST /api/sql/convert/stream` — 转换（流式）
- `POST /api/sql/explain` — 执行计划分析
- `POST /api/sql/explain/stream` — 分析（流式）
- `POST /api/sql/review` — SQL 审核
- `POST /api/sql/review/stream` — 审核（流式）

### 日志分析
- `GET /api/log-analysis/tasks` — 获取分析任务列表
- `POST /api/log-analysis/tasks` — 创建分析任务（支持 db_type 参数）
- `GET /api/log-analysis/tasks/<task_id>` — 获取任务详情
- `PUT /api/log-analysis/tasks/<task_id>` — 更新任务状态
- `DELETE /api/log-analysis/tasks/<task_id>` — 删除任务
- `POST /api/log-analysis/upload/<task_id>` — 上传日志文件
- `POST /api/log-analysis/analyze/<task_id>` — 执行分析（SSE 流式输出）

### 运维手册
- `GET /api/manuals` — 获取手册列表
- `POST /api/manuals` — 上传手册
- `DELETE /api/manuals/<filename>` — 删除手册
- `GET /api/manuals/<filename>` — 下载手册
- `GET /api/manuals/preview/<filename>` — 预览手册

### 命令速查
- `GET /api/commands?db_type=` — 获取命令列表
- `POST /api/commands` — 保存自定义命令
- `POST /api/commands/category` — 添加分类
- `POST /api/commands/command` — 添加命令
- `DELETE /api/commands/command` — 删除命令
- `GET /api/commands/search?keyword=` — 跨库搜索命令

### 集群拓扑
- `GET /api/topology/clusters` — 获取集群列表
- `GET /api/topology/stats` — 获取集群拓扑统计聚合数据（支持 cluster/datacenter/db_type/environment 筛选）
- `POST /api/topology/clusters` — 添加集群
- `PUT /api/topology/clusters/<id>` — 更新集群
- `DELETE /api/topology/clusters/<id>` — 删除集群
- `POST /api/topology/clusters/<id>/servers` — 添加物理机
- `DELETE /api/topology/servers/<id>` — 删除物理机
- `PUT /api/topology/servers/<id>` — 更新物理机
- `POST /api/topology/servers/<id>/instances` — 添加实例
- `DELETE /api/topology/instances/<id>` — 删除实例
- `GET /api/topology/instances/<id>` — 获取实例详情
- `PUT /api/topology/instances/<id>` — 更新实例
- `POST /api/topology/clusters/<id>/tenants` — 添加租户
- `DELETE /api/topology/tenants/<id>` — 删除租户
- `PUT /api/topology/tenants/<id>` — 更新租户
- `POST /api/topology/instances/relations` — 添加关系
- `DELETE /api/topology/instances/relations` — 删除关系
- `GET /api/topology/export` — 导出拓扑

### 系统配置（多模型）
- `GET /api/config/llm` — 获取当前默认模型配置（兼容旧接口）
- `GET /api/config/llm/models` — 获取所有模型配置列表
- `POST /api/config/llm/models` — 保存模型配置（新增或更新）
- `DELETE /api/config/llm/models/<model_id>` — 删除模型配置
- `POST /api/config/llm/models/<model_id>/default` — 设置默认模型
- `POST /api/config/test` — 测试连接，支持 model_id 参数
- `GET /api/config/features` — 获取功能配置列表
- `PUT /api/config/features/<module_id>` — 更新功能配置（启用/禁用模块）
- `GET /api/config/export` — 导出配置
- `POST /api/config/import` — 导入配置
- `GET /api/config/docs/<filename>` — 读取文档

### 仪表盘
- `GET /api/stats` — 统计数据
- `GET /api/health` — 健康检查
- `GET /api/shortcuts` — 快捷键列表
- `GET /api/tags` — 知识库标签
- `GET /api/logs?limit=&module=` — 操作日志
- `DELETE /api/logs` — 清空日志
- `GET /api/logs/modules` — 日志模块列表

### 智能运维Agent
- `GET /api/agent/sessions` — 获取Agent会话列表
- `POST /api/agent/sessions` — 创建Agent会话
- `GET /api/agent/sessions/<session_id>` — 获取会话详情
- `DELETE /api/agent/sessions/<session_id>` — 删除会话
- `POST /api/agent/run` — 启动Agent任务（SSE流式）
- `GET /api/agent/sessions/<session_id>/steps` — 获取执行步骤
- `GET /api/agent/skills` — 获取Skills列表
- `GET /api/agent/skills/<skill_name>` — 获取Skill详情
- `GET /api/agent/tools` — 获取可用工具列表
- `GET /api/agent/ssh-connections` — 获取SSH连接列表
- `POST /api/agent/ssh-connections` — 创建SSH连接
- `DELETE /api/agent/ssh-connections/<conn_id>` — 删除SSH连接
- `POST /api/agent/ssh-connections/<conn_id>/test` — 测试SSH连接
- `GET /api/agent/db-connections` — 获取数据库连接列表
- `POST /api/agent/db-connections` — 创建数据库连接
- `DELETE /api/agent/db-connections/<conn_id>` — 删除数据库连接
- `POST /api/agent/db-connections/<conn_id>/test` — 测试数据库连接

---

## 开发规范

### 数据库操作规范

1. **开发前必读文档**：修改涉及数据库的代码前，先阅读 `tables_desc.md` 确认表结构
2. **字段变更流程**：新增/修改字段时，同时更新：
   - `db/database.py` 中的表定义和迁移代码
   - `tables_desc.md` 表结构文档
   - `code_desc.md` 相关函数说明
3. **外键约束**：注意外键约束和级联操作
4. **数据迁移**：使用 `ALTER TABLE` 兼容旧数据库
5. **查询优化**：避免 N+1 查询，使用 JOIN 和 GROUP BY 一次性获取关联数据
6. **线程安全**：使用 `threading.local()` 管理数据库连接，设置 `busy_timeout` 防止锁冲突

### API 开发规范

1. **路由命名**：使用 RESTful 风格，复数名词
2. **参数校验**：必填参数必须校验，特别是路径参数（如 `db_type`）需防止路径遍历
3. **错误处理**：返回标准错误格式，捕获具体异常类型而非 `except Exception`
4. **日志记录**：重要操作记录到 operation_logs
5. **流式响应**：使用 `stream_llm_response()` 通用函数生成 SSE 响应

### 前端开发规范

1. **模块化**：每个功能模块独立文件
2. **命名规范**：函数名使用驼峰命名
3. **事件处理**：防止事件冒泡
4. **DOM 操作**：使用 id 选择器，避免复杂选择器；批量插入使用 DocumentFragment
5. **内存管理**：流式请求完成后清理 AbortController 和 reader 引用
6. **XSS 防护**：使用 `escapeHtml()` 和 `escapeJs()` 转义用户输入，HTML 属性上下文需同时转义 HTML 特殊字符

---

## 编码规范（重要！）

> ⚠️ **警告**：项目中的中文文件曾多次因编码问题导致乱码，请务必遵守以下规范。

### 文件编码要求

1. **所有文本文件必须使用 UTF-8 编码**，包括：
   - Python 文件（`.py`）
   - HTML 模板（`.html`）
   - JavaScript 文件（`.js`）
   - CSS 文件（`.css`）
   - Markdown 文档（`.md`）
   - JSON 文件（`.json`）

2. **禁止行为**：
   - ❌ **禁止使用 GBK/GB2312 编码打开或保存文件**
   - ❌ 禁止使用记事本直接编辑包含中文的文件（记事本默认保存为 UTF-8 BOM 或 ANSI）
   - ❌ 禁止在 PowerShell 中使用 `Get-Content` 或 `Set-Content` 处理中文文件（默认使用系统编码）

3. **正确做法**：
   - ✅ 使用支持 UTF-8 编码的编辑器（VS Code、PyCharm、Notepad++ 等）
   - ✅ 在编辑器中明确设置编码为 UTF-8
   - ✅ Python 文件开头添加 `# -*- coding: utf-8 -*-`
   - ✅ HTML 文件包含 `<meta charset="UTF-8">`

### Python 文件操作编码规范

```python
# ✅ 正确：明确指定编码
with open('file.txt', 'r', encoding='utf-8') as f:
    content = f.read()

with open('file.txt', 'w', encoding='utf-8') as f:
    f.write(content)

# ❌ 错误：不指定编码（在 Windows 上默认使用 GBK）
with open('file.txt', 'r') as f:  # 不要这样做！
    content = f.read()
```

### 编码检查命令

```bash
# 检查文件是否为 UTF-8 编码
file -i filename.py

# 转换文件编码（Linux/Mac）
iconv -f GBK -t UTF-8 input.txt > output.txt
```

### 乱码恢复方法

如果文件已出现乱码，可尝试以下方法恢复：

```python
# 尝试用不同编码读取
def try_decode(filepath):
    for enc in ['utf-8', 'gbk', 'gb2312', 'latin-1']:
        try:
            with open(filepath, 'r', encoding=enc) as f:
                content = f.read()
            print(f"成功用 {enc} 解码")
            return content
        except:
            continue
    return None
```

---

## AI 辅助开发规范

> 本规范用于指导 AI 助手（如 Claude）在修改代码时避免陷入重复读取的死循环，提高协作效率。

### 核心原则

1. **信任编辑工具**：`Edit` 工具会精确替换目标文本，修改后无需立即读取验证
2. **批量修改**：同一文件的多个修改点，一次性完成后再统一验证
3. **功能验证优先**：修改完成后通过测试验证，而非反复读取代码确认

### 修改前：明确目标，一次规划

- [ ] 完整阅读相关代码，理解业务逻辑
- [ ] 明确修改点和影响范围
- [ ] 确定修改方案后再动手，不边改边看

### 修改时：高效执行，避免循环

- [ ] **不重复读取**：修改后不要立即读取同一文件验证
- [ ] **批量处理**：同一文件的多个修改，一次性完成
- [ ] **相信工具**：`Edit` 失败会报错，成功即表示替换完成

### 修改后：功能验证，问题驱动

- [ ] 修改完成后直接测试功能是否正常
- [ ] 有问题再针对性修复，不反复检查代码
- [ ] 通过浏览器控制台、日志、测试用例验证，而非肉眼检查代码

### 反模式：重复读取死循环

```
❌ 错误示范：
   修改 A → 读取 A 验证 → 修改 B → 读取 B 验证 → 修改 A → ...

✅ 正确示范：
   读取所有相关文件 → 修改 A、B、C → 测试功能 → 有问题再修复
```

### 前端调试技巧

- 使用浏览器 DevTools 的 Console 查看 `console.log` 输出
- 使用 Network 面板查看 API 请求和响应
- 使用 Elements 面板检查 DOM 结构
- 在关键位置添加 `console.log` 而非反复读取代码

---

## 依赖清单

| 包名 | 版本 | 用途 |
|------|------|------|
| flask | >=2.3.0 | Web 框架 |
| requests | >=2.31.0 | HTTP 请求（LLM API） |
| python-docx | >=0.8.11 | DOCX 文件解析 |
| openpyxl | >=3.1.0 | XLSX 文件解析 |
| PyPDF2 | >=3.0.0 | PDF 文件解析 |
| python-multipart | >=0.0.6 | 文件上传 |
| sentence-transformers | >=2.2.0 | 向量嵌入模型 |
| numpy | >=1.24.0 | 向量计算 |
| sqlglot | >=20.0.0 | SQL 语法解析（本地 SQL 审核） |

---

## 暗色主题实现

**切换方式：**
1. 点击侧边栏 🌙/☀️ 按钮
2. 通过 `data-theme="dark"` 属性切换
3. 设置保存到 `localStorage`
4. 刷新页面后自动恢复

**CSS 变量系统：**
- 亮色主题：`:root` 定义变量
- 暗色主题：`[data-theme="dark"]` 覆盖变量
- 所有颜色、背景、边框、阴影均通过变量控制
- `transition` 实现平滑切换动画

---

## 自动扫描功能

**触发时机：** 应用启动时（`create_app()` 中调用）

**扫描逻辑：**
1. 遍历 `data/knowledge/<db_type>/` 各子目录
2. 检查文件是否已在数据库中（避免重复）
3. 检查文件格式是否支持（`allowed_file`）
4. 提取文件内容（`extract_content`）
5. 入库（`add_knowledge_file`）

**使用场景：**
- 直接将文件放入知识库目录
- 重启应用后自动识别
- 无需手动上传

---

## 多模型配置管理

**数据存储：**
- `llm_models` 键：存储所有模型配置的 JSON 数组
- `default_model_id` 键：存储默认模型的 ID

**模型配置字段：**
| 字段 | 说明 |
|------|------|
| `id` | 模型唯一标识（UUID） |
| `display_name` | 显示名称（用于下拉框展示） |
| `api_url` | API 地址 |
| `api_key` | API Key（加密存储） |
| `model_name` | 模型名称（如 kimi-k2.6, gpt-4） |

**前端交互：**
1. 系统配置页面展示模型卡片列表
2. 每个模型卡片显示：名称、API地址、默认标识
3. 操作按钮：测试、编辑、设为默认、删除
4. 添加模型时填写：显示名称、API地址、API Key、模型名称

**模型切换：**
- 知识问答和 SQL 工具页面增加模型选择下拉框
- 下拉框加载所有已配置模型
- 默认选中默认模型
- 留空则使用默认模型

---

## 前端模块化架构

重构后的 JS 采用模块化设计，每个模块职责单一：

| 文件 | 职责 |
|------|------|
| `app.js` | 入口文件：主题切换、导航、初始化、仪表盘、通用函数 |
| `utils.js` | 通用工具函数（showToast、escapeHtml、formatFileSize 等） |
| `api.js` | API 请求封装（apiGet、apiPost、apiPut、apiDelete） |
| `knowledge.js` | 知识库模块（文件列表、上传、搜索、收藏） |
| `qa.js` | 知识问答模块（对话、流式输出、历史记录） |
| `sql-tools.js` | SQL 工具模块（审核、格式化、转换、执行计划） |
| `manuals.js` | 运维手册模块（列表、上传、预览） |
| `commands.js` | 命令速查模块（分类、命令、删除、搜索） |
| `topology.js` | 集群拓扑模块（集群、节点、实例、租户管理） |
| `config.js` | 系统配置模块（模型管理、数据库类型、日志） |

**模块化优势：**
- 代码结构清晰，便于维护
- 各模块职责单一，降低耦合度
- 便于多人协作开发
- 易于单元测试
- 新功能开发更快定位代码位置
