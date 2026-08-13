# DBSV 数据库运维工具（DBSV Admin）

## 开发人：顾云波

> 📌 **配套文档（比本文件更细）**：
> - `version_update.md` — 版本更新记录
> - `code_desc.md` — 代码结构文档（函数/API 详细说明）
> - `tables_desc.md` — 数据库表结构
> - `deploy.md` — 部署指南与依赖清单

## 项目概述

DBSV 数据库运维工具是一套面向 DBA 的 Web 端数据库运维平台。平台采用先进的 RAG（检索增强生成）技术，结合大语言模型能力，集成知识库管理、智能问答、SQL 工具、运维手册、命令速查、集群拓扑、日志分析以及智能运维 Agent 等核心功能模块，旨在为数据库管理员和运维人员提供一站式的数据库管理解决方案。基于 Flask + 原生 HTML/CSS/JS 构建，UI 为中文。

平台通过直观的 Web 界面，用户可以轻松管理多种类型的数据库，执行日常运维操作，并获取 AI 驱动的智能运维建议。智能运维 Agent 能自动执行数据库诊断、优化和建议等复杂任务。

## 技术栈

| 层级 | 技术 |
|------|------|
| 后端 | Python Flask，应用工厂模式，Blueprint 分模块 |
| 数据库 | SQLite（WAL 模式，支持并发读，线程本地连接） |
| 前端 | 原生 HTML/CSS/JS，单页应用，模块化 JS 架构 |
| AI | OpenAI 兼容 API（支持多模型配置管理） |
| RAG | sentence-transformers（moka-ai/m3e-base）+ numpy 向量化矩阵检索（带缓存） |
| 知识图谱 | Chunk-Entity 混合图谱，SQLite 存储，**已合并到知识库模块** |
| 主题 | CSS 变量系统，支持亮色/暗色主题切换，localStorage 持久化 |
| 外部监控 | 蓝鲸监控数据中间脚本（mon_metric_data 落库，供 Agent 查询） |

核心依赖：`requests`（LLM API）、`sentence-transformers`（向量嵌入）、`sqlglot`（本地 SQL 解析）、`cryptography`（凭据加密），以及 Agent 真实执行所需的 `pymysql`/`oracledb`/`psycopg2-binary`/`paramiko`（见 `deploy.md`）。

## 目录结构

```
dbsv_admin/
    app.py                  # 应用工厂 + 启动入口
    config.py               # 全局配置（路径、RAG 分块、LLM、版本）
    README.md               # 本文件（项目介绍）
    deploy.md               # 部署指南（含依赖清单）
    version_update.md       # 版本更新记录
    code_desc.md            # 代码结构文档
    tables_desc.md          # 数据库表结构
    wecom_qa_integration.md # 企业微信接入知识问答接口文档

    deploy/                 # 离线部署配套
        deploy.sh           # 服务器自动化部署脚本
        dbsv-admin.service  # systemd 单元模板
        prepare_requirements.py  # 离线依赖打包脚本
        check_wheelhouse.py # wheelhouse 完整性校验
        DEPLOY_CENTOS7.md   # CentOS 7 离线部署文档

    requirements/           # Linux 离线依赖（wheelhouse）
        requirements-linux.txt  # 锁定版依赖清单
        wheelhouse/             # 全部离线 wheel 包
        README.md               # 使用说明

    db/                     # 数据库层
        __init__.py
        database.py         # SQLite 连接管理、表初始化、全部 CRUD
        kg_database.py      # 知识图谱 CRUD（实体、关系、chunk关联）
        migration.py        # JSON → SQLite 自动迁移（首次启动执行）

    utils/                  # 工具函数包
        __init__.py         # 通用工具函数（文件解析、LLM 调用、凭据加密）
        sql_checker.py      # 本地 SQL 语法检查模块（sqlglot 解析/格式化）
        topology_import.py  # 集群拓扑批量导入模块（Excel 解析、数据导入）
        create_import_template.py  # 集群拓扑导入模板生成脚本

    tools/                  # 运维工具脚本
        monitor_blueking.py # 蓝鲸监控数据中间脚本（拉取监控指标落库）

    routes/                 # API 路由（Blueprint）
        __init__.py         # Blueprint 统一导出
        knowledge.py        # 知识库文件管理 + 收藏夹
        qa.py               # 知识问答（向量检索 RAG + 知识图谱增强）
        kg.py               # 知识图谱 API（实体搜索、邻居、路径、子图）
        sql_tools.py        # SQL 审核 / 格式化 / 转换 / 执行计划分析
        log_analysis.py     # 日志分析（多轮 LLM 分析 + RAG 增强）
        manuals.py          # 操作手册上传下载
        commands.py         # 命令速查（按数据库类型）
        topology.py         # 集群拓扑 CRUD
        config.py           # LLM API 配置 + 项目介绍（多模型管理）
        dashboard.py        # 仪表盘统计 + 日志 + 快捷键
        db_types.py         # 数据库类型管理
        agent.py            # 智能运维Agent核心引擎（ReAct循环 + SSE流式）
        agent_connections.py # SSH/数据库连接管理

    agent/                  # 智能运维Agent模块
        __init__.py
        harness.py           # 安全约束框架（SQL白名单 + 命令白名单 + 操作级别）
        connectors.py        # 工具连接器（DB/SSH连接加载解密 + 查询执行 + 指标/Schema生成）
        skills.py            # 领域知识与操作指南（内置6技能 + DB自动沉淀技能 + Curator去重/淘汰）
        state.py             # Agent状态管理（ReAct状态机）
        tools.py             # MCP风格工具定义（7个工具 + ToolContext）
        engine.py            # Agent核心引擎（ReAct循环 + 知识库/图谱增强 + 技能沉淀/记忆闭环 + 状态持久化）

    kg/                     # 知识图谱模块
        __init__.py
        rules.py             # 规则实体提取器（正则+词典匹配）
        llm_extractor.py     # LLM实体/关系提取（prompt模板）
        graph.py             # 图谱查询引擎（邻居、路径、子图、QA增强）

    rag/                    # 向量检索模块
        __init__.py
        embedder.py          # 文本分块、向量嵌入、相似度检索、知识图谱自动提取

    static/
        css/style.css        # 样式（含暗色主题 CSS 变量系统）
        vendor/              # 前端第三方库（vis-network 本地化，离线可用）
        js/                  # 前端模块化 JS
            app.js           # 入口文件：主题、导航、初始化、仪表盘
            utils.js         # 通用工具函数（showToast、escapeHtml 等）
            api.js           # API 封装（apiGet、apiPost、apiPut、apiDelete）
            knowledge.js     # 知识库模块（含知识图谱视图切换）
            qa.js            # 知识问答模块（含流式输出）
            kg.js            # 知识图谱可视化模块（vis.js 力导向图，已合并到知识库）
            sql-tools.js     # SQL 工具模块
            log-analysis.js  # 日志分析模块
            manuals.js       # 操作手册模块
            commands.js      # 命令速查模块
            topology.js      # 集群拓扑模块
            config.js        # 系统配置模块（模型管理、项目介绍、日志）
            agent.js         # 智能运维Agent模块（ReAct循环可视化）

    templates/
        index.html           # 单页应用 HTML
        cluster_topology_import_template_v2.xlsx  # 集群拓扑批量导入模板

    data/                   # 运行时数据（自动创建）
        db_tool.db           # SQLite 数据库
        knowledge/           # 按数据库类型分目录存储知识库文件
        manuals/             # 操作手册文件
        commands/            # 命令库 JSON 文件
        models/              # sentence-transformers 模型缓存
        json_backup/         # 迁移前的 JSON 文件备份
```

## 数据库表结构

| 表名 | 用途 |
|------|------|
| sys_config | 键值对配置（API 地址、密钥、模型名、多模型配置等） |
| sys_db_types | 数据库类型定义（MySQL、Oracle 等） |
| kb_files | 知识库文件元数据 + 解析后的文本内容 |
| qa_conversations | 问答会话 |
| qa_messages | 问答消息（多轮对话） |
| kb_favorites | 文件收藏 |
| log_analysis_tasks | 日志分析任务 |
| log_analysis_files | 日志分析文件 |
| topo_resource_pools | 资源池信息 |
| topo_clusters | 集群信息（属于某个资源池） |
| topo_servers | 物理机（含 CPU、内存、机房等字段） |
| topo_instances | 实例 |
| topo_tenants | 租户（实例集群） |
| topo_instance_relations | 实例间关系 |
| kb_embeddings | 文本块向量嵌入（RAG 用） |
| mon_metric_data | 外部监控平台指标落库（蓝鲸等，供 Agent 查询） |
| kg_entities | 知识图谱实体表 |
| kg_relationships | 知识图谱关系表 |
| kg_chunk_entities | chunk-实体关联表 |
| audit_operation_logs | 操作日志 |
| sys_feature_config | 功能配置开关 |
| agent_ssh_connections | SSH连接配置（目标服务器） |
| agent_db_connections | 数据库连接配置（用于SQL查询） |
| agent_sessions | Agent会话 |
| agent_steps | Agent执行步骤（ReAct过程记录） |
| agent_skills | Agent Skills（内置 + 自动沉淀技能，含 trigger_keywords/usage_count/status） |
| agent_memory | Agent长期记忆（跨会话环境事实，含向量列供语义召回；诊断自动写 + DBA 反馈写） |
| agent_plans | Agent操作计划（变更类审批流，status: pending/approved/rejected/expired） |

## 功能模块

### 1. 知识库（/api/knowledge/*）
- 按数据库类型组织文件
- 支持上传 txt/md/pdf/docx/xlsx/html/chm 等格式
- 上传时自动解析文件正文内容存入数据库
- 全文搜索 + 标签过滤
- 收藏夹功能
- **知识图谱自动提取**：上传/重建索引时自动提取实体和关系
- **知识图谱可视化**：知识库页面支持文件视图/图谱视图切换

### 2. 知识问答（/api/qa/*）
- 对话式界面，调用 LLM 回答数据库问题
- RAG 增强：优先用向量检索知识库内容作为上下文
- **知识图谱增强**：自动识别问题中的实体，注入图谱上下文（实体卡片、关系链）
- **数据库类型自动识别**：选择"自动选择"时，系统会从问题中自动识别数据库类型
- 问题模板（报错处理、语法查询、性能问题等）
- 对话历史持久化
- **支持模型切换**：可在多个已配置模型中选择

### 3. SQL 工具（/api/sql/*）
- SQL 审核：检查语法、性能、安全性、最佳实践
- SQL 格式化：美化 SQL 语句
- SQL 转换：跨数据库方言翻译（如 MySQL → Oracle）
- 执行计划分析：粘贴 EXPLAIN 结果，AI 分析瓶颈和索引建议
- **支持模型切换**

### 4. 操作手册（/api/manuals/*）
- 上传管理 SOP 文档
- 支持下载和删除
- 支持 txt/log/sql/py/sh 等文本文件预览

### 5. 命令速查（/api/commands）
- 按数据库类型的命令速查表
- 内置 MySQL、Oracle、达梦、OceanBase 默认命令
- 支持添加自定义分类和命令、删除自定义命令、点击复制、跨库搜索

### 6. 集群拓扑（/api/topology/*）
- 资源池/集群/节点/实例/租户管理
- **统计视图**：聚合展示集群宏观数据，支持多维度筛选
- **拓扑视图**：HTML 渲染拓扑图，按机房层级分组展示
- **批量导入**：从 Excel 批量导入服务器和实例数据
- 支持单机/主从/双主/集群/分布式拓扑类型，节点设备类型与角色管理

### 7. 系统配置（/api/config/*）
- **多模型配置管理**：添加、编辑、删除多个 LLM 模型
- **项目介绍**：展示 README.md 项目文档
- **功能配置开关**：控制导航栏各模块显隐
- 模型切换、连接测试、日志查看

### 8. 日志分析（/api/log-analysis/*）
- 多轮渐进式 LLM 分析：意图识别 → 日志筛选 → 根因分析 → 报告生成
- SSE 流式输出：实时展示分析进度和每步耗时
- 知识库 RAG 增强：按数据库类型查询对应知识库
- 支持上传多份日志文件，分析任务历史记录

### 9. 智能运维Agent（/api/agent/*）
- **ReAct 循环引擎**：Thought → Action → Observation → Conclusion 自主决策，观察结果回流对话历史实现链式推理
- **并行只读工具（v3.0.9）**：一次思考可输出多个工具调用（JSON 数组），只读工具线程池并行执行（最多 4 并发/次 5 个），多指标诊断提速；每个动作独立过 Harness 校验
- **上下文压缩（v3.0.9）**：对话历史过长时头尾保护 + 中间摘要，控制超长 prompt
- **迭代预算（v3.0.9）**：max_steps 配置化 + 重复动作死循环检测 + 历史字符预算，超限强制收敛
- **真实工具执行**：7 个工具均为真实实现
  - `query_database` — 按 db_type 连接目标库执行只读 SQL
  - `execute_command` — 通过 paramiko SSH 执行白名单数据库命令
  - `get_schema_info` — 表清单/表结构查询
  - `get_performance_metrics` — 会话/锁/等待/Top SQL/表占用指标
  - `retrieve_knowledge` — 知识库向量检索
  - `retrieve_check` — 检索运维检查项（专家检查知识库，SQL/命令/建议）
  - `get_monitor_metrics` — 查询外部监控平台落库的监控指标（蓝鲸等，CPU/内存/磁盘）
  - 工具执行双重安全校验（引擎 + 工具自身），表名白名单防注入
- **Harness 安全约束框架**：SQL 白名单 + 命令白名单（按操作级别），剥离注释校验，禁止危险操作
- **知识库 + 知识图谱双增强**：执行前检索知识库，并注入图谱实体卡片/关系链上下文
- **Skills 领域知识**：6 个内置技能（慢查询诊断、Oracle RAC 检查、备份检查等）+ 自动沉淀技能
- **文档生成技能（v3.0.9）**：上传操作手册或从手册页直接「生成技能」，LLM 提炼为可复用技能（离线回退 + Curator 去重）
- **学习闭环（v3.0.8）**：成功诊断后自动沉淀技能（LLM 提炼/离线回退 + Curator 去重淘汰），诊断结论与 DBA 反馈自动写入长期记忆，下次诊断按关键词召回注入环境上下文
- **记忆语义召回（v3.0.9）**：记忆写入时自动编码向量，召回时语义检索 top-K（模型不可用回退关键词），并对主机/实例/集群记忆补图谱上下文
- **记忆事实校验（v3.0.9）**：写前与图谱实体/监控对象/知识库支撑交叉验证，无支撑结论跳过不写，防污染
- **DBA 反馈闭环（v3.0.9）**：结论后 👍/👎 + 纠正，反向修正该会话技能置信度/状态与记忆
- **变更类审批流（v3.0.10）**：运维操作分查询类（只读，不变）与变更类（修改参数/配置/变更命令）。变更类走通用流程：确认范围 → 创建操作计划 → DBA 审批 → 引擎按计划执行 → 遇错自分析自查询 → 追加新计划再审批，迭代直至完成。模型工具永远只读，写操作唯一通道 = 计划 + DBA 审批 + 引擎执行（Harness 变更白名单二次校验）。审批面板展示操作项临时列表 + 批准/拒绝。
- **SSE 流式输出**：实时展示思考过程、工具执行、观察结果、最终结论
- **SSH/数据库连接管理**：前端表单配置多个目标服务器和数据库连接（凭据加密存储）
- **会话持久化**：每步写入 `agent_steps`，会话状态更新到 `agent_sessions`
- **只读模式**：默认只读，禁止任何修改数据的操作
- **置信度标注**：🟢高/🟡中/🔴低 三级置信度标识

### 10. 知识图谱（已合并到知识库模块）
- **Chunk-Entity 混合图谱**：复用知识库 chunk 作为文档层，增量添加实体节点
- **实体类型**：数据库产品、版本、参数、错误码、SQL 语句、函数、系统视图、命令工具、架构、性能指标、概念、故障场景、操作系统、硬件等
- **关系类型**：belongs_to、compatible_with、requires、has_parameter、similar_to 等
- **混合提取策略**：规则匹配（正则+词典）+ LLM 提取
- **可视化浏览**：vis.js 力导向图，支持拖拽、缩放、点击展开邻居
- **QA 增强**：从检索到的 chunk 中提取关联实体，构建图谱上下文注入 prompt
- **关系推理**：版本归属、参数归属、跨产品映射等规则推理

## 支持的数据库类型

默认：MySQL、Oracle、达梦(DM)、GoldenDB、OceanBase、TDSQL、GaussDB、PostgreSQL、MongoDB
可通过 API 自定义添加更多类型。

## RAG + 知识图谱增强工作流程

```
用户提问 → Embedder 计算查询向量
         → 从 embeddings 表检索最相似的 top-N 文本块
         → 从 chunk 关联的 kg_entities 提取实体卡片和关系链
         → 拼接为上下文（知识库内容 + 图谱实体/关系）
         → 发送给 LLM 生成回答
```

如果 sentence-transformers 未安装或向量索引为空，自动回退到关键词匹配检索。

### RAG 分块策略

| 参数 | 值 | 说明 |
|------|-----|------|
| chunk_size | 500 | 每块目标字符数（m3e-base 为 BERT，max_position_embeddings=512，超过则编码截断） |
| overlap | 50 | 相邻块重叠字符数 |
| 相似度阈值 | 0.75 | 余弦相似度过滤阈值（过滤单个 chunk） |
| 知识覆盖率 | 0.80 | 判定"知识充分"的门限 |
| 模型 | moka-ai/m3e-base | 中文语义理解更优；运行设备由 `DB_TOOL_EMBED_DEVICE` 控制（auto/cuda/cpu） |

> 分块 500 后阈值 0.55/0.60 → 0.75/0.80（实测 30 个真实问答 top-1 相似度 0.766~0.869，详见 version_update v3.0.5）。

### 知识图谱数据规模

> 数据规模随知识库重建动态变化，以下为最近一次全量重建（分块 500）后的数量。

| 指标 | 数值 |
|------|------|
| 实体总数 | ~46,000+ |
| 关系总数 | ~17,000+ |
| chunk 关联 | ~329,000 |
| embedding 总数 | ~58,000 |

## 部署指南

### 环境要求

部署环境需满足：操作系统支持 Linux（推荐）、Windows 和 macOS；Python 3.8 及以上；建议内存 4GB 以上，磁盘空间 10GB 以上；需联网以下载依赖包和模型文件（离线部署方案见 `deploy/DEPLOY_CENTOS7.md`）。

### 安装依赖

```bash
# 创建虚拟环境（Windows）
python -m venv venv
venv\Scripts\activate

# 安装依赖（无 requirements.txt，按 deploy.md 安装）
pip install flask requests python-docx openpyxl PyPDF2 python-multipart sentence-transformers numpy sqlglot cryptography
# Agent 真实执行（可选）：
pip install pymysql oracledb psycopg2-binary paramiko
# 可选：flask-cors、apscheduler（未安装时相关功能自动跳过）
```

### 启动方式

```bash
# 开发模式（默认监听 0.0.0.0:5000，debug=True）
python app.py

# 生产环境（Linux 用 Gunicorn / Windows 用 Waitress）
gunicorn -w 4 -b 0.0.0.0:5000 app:app
waitress-serve --host=0.0.0.0 --port=5000 app:app
```

### 首次启动

首次启动自动创建 SQLite 数据库（`data/db_tool.db`）、执行 JSON→SQLite 迁移、扫描 `data/knowledge/` 同步新文件并生成向量索引。如需配置 LLM API，请参考 `deploy.md`。

## API 文档

### 知识库接口

`POST /api/knowledge/upload/<db_type>` 上传文件，`GET /api/knowledge/files/<db_type>` 获取文件列表，`POST /api/knowledge/search` 检索知识。索引管理：`POST /api/knowledge/reindex`（全量）、`POST /api/knowledge/reindex/stream`（SSE 流式）、`POST /api/knowledge/reindex/file`（单文件）、`POST /api/knowledge/reindex/db-type`（按类型）。

### 知识问答接口

`POST /api/qa/conversations` 创建会话，`POST /api/qa/ask` 非流式问答，`POST /api/qa/ask/stream` 流式响应，`GET /api/qa/conversations` 会话列表。

### SQL 工具接口

`POST /api/sql/format`、`/api/sql/convert`、`/api/sql/explain`、`/api/sql/review`，均支持流式（`/stream` 后缀）。

### 集群拓扑接口

`GET/POST /api/topology/resource-pools`、`GET/POST /api/topology/clusters`，`GET /api/topology/stats` 统计视图，`GET /api/topology/export` 导出。

### 系统配置接口

`GET/POST /api/config/llm/models` 模型列表/保存，`POST /api/config/llm/models/<id>/default` 设默认，`GET /api/config/features`、`PUT /api/config/features/<module_id>` 功能开关。项目介绍文档：`GET /api/config/doc/<filename>`。

### Agent 接口

`POST /api/agent/sessions` 创建会话，`POST /api/agent/run` 执行任务，`GET /api/agent/sessions/<id>/steps` 会话步骤，`GET /api/agent/tools` 工具列表，`GET /api/agent/skills` 技能列表，`POST/DELETE /api/agent/skills[/<name>]` 技能维护，`GET/POST /api/agent/memory` 与 `DELETE /api/agent/memory/<id>` 长期记忆查看/记录/删除。

## 使用说明

### 快速开始

1. 启动应用后，浏览器访问 `http://localhost:5000`
2. 进入「系统配置」页面，配置至少一个 LLM 模型连接
3. 在「数据库类型」中添加需要管理的数据库类型
4. 上传知识文档到「知识库」并执行索引重建
5. 开始使用各功能模块进行数据库运维工作

### 智能 Agent 使用

在 Agent 模块中，先配置 SSH 连接（执行命令）和数据库连接（执行 SQL）。创建会话后选择连接并输入运维需求，Agent 自动分析、执行并返回结果，支持查看执行步骤、思考过程和工具调用详情。Agent 也可查询落库的监控指标（`get_monitor_metrics`，需先运行 `tools/monitor_blueking.py` 拉取蓝鲸监控数据）。

每次成功诊断后，Agent 会自动把诊断轨迹沉淀为可复用技能并写入长期记忆（学习闭环），后续同类问题会被技能指导、并注入环境上下文。沉淀的技能可在 Agent 页面查看/停用/删除，也可通过 `POST /api/agent/memory` 显式记录拓扑事实与 DBA 偏好。

## 开发注意事项

重构后的 JS 采用模块化设计，每个模块职责单一（见目录结构中 `static/js/` 注释）。新增模块需同时：在 `routes/` 建 Blueprint、`routes/__init__.py` 导出并注册、`static/js/` 加模块文件、`templates/index.html` 加导航。

## 版本

当前版本：v3.0.11。完整更新记录见 `version_update.md`。

## 贡献者

开发人：顾云波
