

# DBSV 数据库运维工具

## 项目概述

DBSV 数据库运维工具是由顾云波开发的一套智能化数据库运维管理平台。该平台集成了知识库管理、智能问答、SQL工具、运维手册、命令速查、集群拓扑、系统配置、日志分析以及智能运维Agent等核心功能模块，旨在为数据库管理员和运维人员提供一站式的数据库管理解决方案。

平台采用先进的 RAG（检索增强生成）技术，结合大语言模型能力，能够智能理解用户需求，自动执行数据库诊断、优化和建议等复杂任务。通过直观的 Web 界面，用户可以轻松管理多种类型的数据库，执行日常运维操作，并获取 AI 驱动的智能运维建议。

## 核心功能模块

### 知识库管理（Knowledge Base）

知识库模块提供文档的集中管理和智能检索功能。支持多种文档格式（包括 PDF、Word、Excel、CHM、TXT 等），系统会自动提取文档内容并进行向量化和索引。用户可以根据数据库类型过滤知识文档，通过关键词快速检索相关资料，实现运维经验的积累和传承。

### 知识问答（Q&A）

基于 RAG 的智能问答系统能够理解用户的自然语言问题，自动从知识库中检索相关内容，并结合大语言模型生成准确、详细的回答。系统支持多轮对话，保持对话上下文连贯性，同时记录问答历史以便后续查询和分析。

### SQL 工具箱（SQL Tools）

SQL 工具模块提供全面的 SQL 操作支持，包括 SQL 语法检查、格式化、方言转换、执行计划和性能审查等功能。系统支持多种数据库方言（如 MySQL、PostgreSQL、Oracle、SQL Server、OceanBase 等），并通过大语言模型提供智能化的 SQL 优化建议和潜在问题诊断。

### 运维手册（Manuals）

运维手册模块用于管理各类数据库运维操作手册和最佳实践文档。文档采用 Markdown 格式渲染，支持在线预览和全文搜索，帮助运维人员快速查阅和遵循标准操作流程。

### 命令速查（Commands）

命令速查模块提供常用数据库命令的快速检索和参考功能。命令按数据库类型和分类组织，支持搜索和快速复制，帮助运维人员快速执行日常数据库操作。

### 集群拓扑（Topology）

集群拓扑模块可视化展示数据库集群的层级结构，包括资源池、集群、服务器、实例和租户等组件。用户可以直观地查看集群中各节点的分布关系、硬件配置和运行状态，支持统计视图和拓扑视图两种展示模式。

### 系统配置（Config）

系统配置模块提供全局参数设置和多模型配置管理功能。支持配置大语言模型的 API 地址、密钥和参数，可添加和切换多个 AI 模型，满足不同场景的智能分析需求。此外还提供导入导出配置、日志管理和功能开关配置等功能。

### 日志分析（Log Analysis）

日志分析模块支持数据库日志的批量上传和智能分析。系统通过多轮分析流程（意图识别、日志筛选、根因分析）自动诊断日志中的问题，生成结构化的分析报告，帮助运维人员快速定位和解决故障。

### 智能运维 Agent（Intelligent Agent）

智能运维 Agent 是平台的 AI 核心引擎，能够自主理解和执行复杂的数据库运维任务。Agent 通过规划、执行、验证的循环流程，结合知识库检索和多种工具调用，实现端到端的自动化运维。用户可以通过自然语言描述需求，Agent 会自动分解任务并生成可执行的解决方案。

## 技术架构

### 后端技术栈

后端采用 Python Flask 框架构建，提供 RESTful API 服务。核心依赖包括：SQLAlchemy 作为 ORM 层处理数据库操作；SQLAlchemy-Utils 提供类型和函数支持；Flask-CORS 处理跨域请求；python-LLMSample-sdk 或类似 SDK 用于大语言模型调用。数据持久化使用轻量级 SQLite 数据库，通过迁移脚本管理数据库结构变更。

### 前端技术栈

前端采用原生 HTML/CSS/JavaScript 构建单页应用，实现模块化的页面切换和交互。CSS 采用 CSS 变量实现暗色主题支持，响应式布局适配不同屏幕尺寸。JavaScript 模块按功能划分，包括应用初始化、API 请求封装、各功能模块的控制器等，通过事件驱动实现组件间通信。

### RAG 向量检索

知识检索采用基于向量的语义搜索方案。使用预训练的语言模型将文本片段转换为高维向量，存储在向量数据库中。查询时将用户问题同样转换为向量，通过余弦相似度计算进行语义匹配，返回最相关的知识片段供大语言模型参考。

### AI Agent 引擎

智能 Agent 引擎采用 ReAct（Reasoning and Acting）模式实现。Agent 在接收到用户问题后，首先从知识库检索相关背景知识，然后在思维链中分析问题并规划执行步骤，最后通过调用工具（如数据库查询、命令执行、知识检索等）完成具体任务。系统内置多重安全验证机制，确保操作不超出预设权限范围。

## 目录结构

```
dbsv_admin/
├── app.py                  # 应用工厂函数和启动入口
├── config.py               # 配置文件
├── sql_checker.py          # SQL 语法检查器
├── utils.py                # 工具函数集合
├── deploy.md               # 部署指南
├── version_update.md       # 版本更新记录
├── code_desc.md            # 代码结构文档
├── tables_desc.md          # 数据库表结构文档
├── db/
│   ├── __init__.py         # 数据库模块初始化
│   ├── database.py         # 数据库管理层（连接、配置、操作函数）
│   └── migration.py        # 数据迁移脚本
├── rag/
│   ├── __init__.py         # RAG 模块初始化
│   └── embedder.py         # 向量嵌入和检索实现
├── agent/
│   ├── __init__.py         # Agent 模块初始化
│   ├── engine.py           # Agent 核心引擎（SmartOpsAgent）
│   ├── harness.py          # 安全约束框架
│   ├── skills.py           # 领域知识和操作技能
│   ├── state.py            # Agent 状态管理
│   └── tools.py            # MCP 风格工具定义
├── routes/
│   ├── __init__.py         # Blueprint 路由导出
│   ├── agent.py            # Agent 核心 API
│   ├── agent_connections.py # Agent 连接管理 API
│   ├── commands.py         # 命令速查 API
│   ├── config.py           # 系统配置 API
│   ├── dashboard.py        # 仪表盘 API
│   ├── db_types.py         # 数据库类型管理 API
│   ├── knowledge.py        # 知识库文件管理 API
│   ├── log_analysis.py     # 日志分析 API
│   ├── manuals.py          # 运维手册 API
│   ├── qa.py               # 知识问答 API
│   ├── sql_tools.py        # SQL 工具 API
│   └── topology.py         # 集群拓扑 API
├── static/
│   ├── css/
│   │   └── style.css       # 前端样式表
│   └── js/
│       ├── api.js          # API 请求封装
│       ├── app.js          # 前端入口和全局控制器
│       ├── agent.js        # 智能运维 Agent 模块
│       ├── commands.js     # 命令速查模块
│       ├── config.js       # 系统配置模块
│       ├── knowledge.js    # 知识库模块
│       ├── log-analysis.js # 日志分析模块
│       ├── manuals.js      # 运维手册模块
│       ├── qa.js           # 知识问答模块
│       ├── sql-tools.js    # SQL 工具模块
│       ├── topology.js     # 集群拓扑模块
│       └── utils.js        # 通用工具函数
├── templates/
│   └── index.html          # 单页应用主页面
└── docs/
    ├── feature_config_plan.md  # 功能配置开关实现计划
    └── log_analysis_design.md  # 日志分析功能设计方案
```

## 部署指南

### 环境要求

部署环境需满足以下要求：操作系统支持 Linux（推荐）、Windows 和 macOS；Python 版本 3.8 及以上；建议内存 4GB 以上，磁盘空间 10GB 以上；需联网以下载依赖包和模型文件。

### 安装依赖

推荐使用虚拟环境隔离项目依赖。首先创建并激活虚拟环境，在项目根目录下执行以下命令安装依赖包：

```bash
# 创建虚拟环境（Windows）
python -m venv venv
venv\Scripts\activate

# 创建虚拟环境（Linux/macOS）
python -m venv venv
source venv/bin/activate

# 安装依赖
pip install -r requirements.txt
```

### 启动方式

开发模式适用于调试和开发测试，使用 Flask 内置服务器启动：

```bash
# Windows
python app.py

# Linux/macOS
python3 app.py
```

生产环境建议使用 Gunicorn（Linux）或 Waitress（Windows）作为 WSGI 服务器：

```bash
# Linux 生产模式
gunicorn -w 4 -b 0.0.0.0:5000 app:app

# Windows 生产模式
waitress-serve --host=0.0.0.0 --port=5000 app:app
```

### 首次启动

首次启动时，系统会自动创建 SQLite 数据库文件（dbsv.db）并执行数据迁移。如需配置 LLM API，请参考部署指南中的配置说明。

详细部署步骤、systemd 服务配置、Nginx 反向代理和防火墙设置等内容，请参阅 `deploy.md` 文件。

## API 文档

### 知识库接口

知识库模块提供文件管理、检索和索引重建等接口。上传文件使用 `POST /api/knowledge/upload/<db_type>`，获取文件列表使用 `GET /api/knowledge/files/<db_type>`，检索知识使用 `POST /api/knowledge/search`。索引管理接口包括重建全部索引 `POST /api/knowledge/reindex` 和重建单个文件索引 `POST /api/knowledge/reindex/file`。

### 知识问答接口

问答模块支持会话管理和消息交互。创建会话使用 `POST /api/qa/conversations`，发送问题使用 `POST /api/qa/ask`，流式响应使用 `POST /api/qa/ask/stream`。历史记录查询支持按会话 ID 获取消息和获取所有会话列表。

### SQL 工具接口

SQL 工具模块提供多种操作接口。SQL 格式化使用 `POST /api/sql/format`，SQL 转换使用 `POST /api/sql/convert`，SQL 解释使用 `POST /api/sql/explain`，SQL 审查使用 `POST /api/sql/review`。所有接口均支持流式响应模式。

### 集群拓扑接口

拓扑模块提供资源池、集群、服务器、实例和租户的管理接口。资源池管理使用 `GET/POST /api/topology/resource-pools`，集群管理使用 `GET/POST /api/topology/clusters`。统计视图接口 `GET /api/topology/stats` 返回集群概览数据，导出接口 `GET /api/topology/export` 支持导出拓扑结构。

### 系统配置接口

配置模块管理 LLM 模型和系统参数。获取模型列表使用 `GET /api/config/llm/models`，保存模型使用 `POST /api/config/llm/models`，设置默认模型使用 `POST /api/config/llm/models/<model_id>/default`。功能配置使用 `GET /api/config/features` 和 `PUT /api/config/features/<module_id>`。

### Agent 接口

Agent 模块提供会话管理和任务执行接口。创建会话使用 `POST /api/agent/sessions`，执行任务使用 `POST /api/agent/run`，获取会话步骤使用 `GET /api/agent/sessions/<session_id>/steps`。工具列表使用 `GET /api/agent/tools` 获取，技能列表使用 `GET /api/agent/skills` 获取。

## 使用说明

### 快速开始

1. 启动应用后，在浏览器中访问 `http://localhost:5000`
2. 进入「系统配置」页面，配置至少一个 LLM 模型连接
3. 在「数据库类型」中添加需要管理的数据库类型
4. 上传知识文档到「知识库」并执行索引重建
5. 开始使用各功能模块进行数据库运维工作

### 知识库使用

在知识库模块中，选择数据库类型后可以查看该类型的所有知识文档。上传新文档后系统会自动提取内容并进行预处理。搜索功能支持关键词检索，检索结果会显示相关度分数。管理员可以管理文件标签、收藏常用文档，以及执行批量索引重建。

### 智能问答使用

在问答模块中，可以选择已有会话或创建新会话。输入问题后选择是否使用知识库增强（RAG）、是否参考集群拓扑信息。系统支持流式输出，回答中会标注参考的知识来源。历史会话保存在侧边栏，可随时回溯查看。

### SQL 工具使用

SQL 工具模块提供四个功能标签页。格式化标签页可将 SQL 代码标准化；转换标签页支持不同数据库方言之间的 SQL 转换；解释标签页展示执行计划和优化建议；审查标签页提供全面的 SQL 质量检查和性能优化建议。

### 集群拓扑使用

拓扑模块支持统计视图和图形视图两种展示模式。统计视图以表格和图表形式展示集群整体状况，支持多维度筛选；图形视图以树形结构展示资源池、集群、服务器的层级关系，支持展开收起和节点详情查看。

### 智能 Agent 使用

在 Agent 模块中，首先需要配置 SSH 连接（用于执行命令）和数据库连接（用于执行 SQL）。创建会话后，选择连接并输入运维需求。Agent 会自动分析问题、执行操作并返回结果，支持查看执行步骤、中间的思考过程和工具调用详情。

## 版本记录

当前版本：v2.5.1（2026-07-28）

最新版本更新包括知识库 RAG 优化、知识问答前端优化、仪表盘改进以及重建索引接口重构。主要功能更新历史请参阅 `version_update.md` 文件。

## 许可证

本项目为开源软件，请遵守相关开源协议使用。

## 贡献者

开发人：顾云波