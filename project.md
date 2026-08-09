# 数据库运维工具（DBSV Admin）

## 开发人：顾云波

> 📌 **阅读提示**：阅读本文件时，请同时阅读以下四个文件以获取完整信息：
> - `version_update.md` — 版本更新记录
> - `code_desc.md` — 代码结构文档
> - `tables_desc.md` — 数据库表结构
> - `deploy.md` — 部署指南

## 项目概述

面向 DBA 的 Web 端数据库运维平台，集成知识库管理、AI 问答、SQL 工具、操作手册、命令速查、集群拓扑可视化、日志分析等功能。基于 Flask + 原生 HTML/CSS/JS 构建，UI 为中文。

## 技术栈

| 层级 | 技术 |
|------|------|
| 后端 | Python Flask，应用工厂模式，Blueprint 分模块 |
| 数据库 | SQLite（WAL 模式，支持并发读） |
| 前端 | 原生 HTML/CSS/JS，单页应用，模块化 JS 架构 |
| AI | OpenAI 兼容 API（支持多模型配置管理） |
| RAG | sentence-transformers（moka-ai/m3e-base）+ numpy 余弦相似度 |
| 知识图谱 | Chunk-Entity 混合图谱，SQLite 存储，**已合并到知识库模块** |
| 主题 | CSS 变量系统，支持亮色/暗色主题切换，localStorage 持久化 |

## 目录结构

> 📌 配套文档：
> - `version_update.md` — 版本更新记录
> - `code_desc.md` — 代码结构文档（函数/API 详细说明）
> - `tables_desc.md` — 数据库表结构
> - `deploy.md` — 部署指南（含依赖清单）

```
dbsv_admin/
    app.py                  # 应用工厂 + 启动入口
    utils.py                # 工具函数（文件解析、LLM 调用）
    deploy.md               # 部署指南（含依赖清单）
    PROJECT.md              # 本文件

    db/                     # 数据库层
        __init__.py
        database.py         # SQLite 连接管理、表初始化、全部 CRUD
        kg_database.py      # 知识图谱 CRUD（实体、关系、chunk关联）
        migration.py        # JSON → SQLite 自动迁移（首次启动执行）

    utils/                  # 工具函数包
        __init__.py         # 通用工具函数（文件解析、LLM 调用）
        topology_import.py  # 集群拓扑批量导入模块（Excel 解析、数据导入）

    routes/                 # API 路由（Blueprint）
        __init__.py         # Blueprint 统一导出
        knowledge.py        # 知识库文件管理 + 收藏夹
        qa.py               # 知识问答（支持向量检索 RAG + 知识图谱增强）
        kg.py               # 知识图谱 API（实体搜索、邻居查询、路径查找、子图提取）
        sql_tools.py        # SQL 审核 / 格式化 / 转换 / 执行计划分析
        log_analysis.py     # 日志分析（多轮 LLM 分析 + RAG 增强）
        manuals.py           # 操作手册上传下载
        commands.py          # 命令速查（按数据库类型）
        topology.py          # 集群拓扑 CRUD
        config.py            # LLM API 配置（支持多模型管理）
        dashboard.py         # 仪表盘统计 + 日志 + 快捷键
        agent.py             # 智能运维Agent核心引擎（ReAct循环 + SSE流式）
        agent_connections.py # SSH/数据库连接管理
        kg.py                # 知识图谱 API（实体搜索、邻居查询、路径查找、子图提取）

    agent/                  # 智能运维Agent模块
        __init__.py
        harness.py           # 安全约束框架（SQL白名单 + 命令白名单 + 操作级别）
        connectors.py        # 工具连接器（DB/SSH连接加载解密 + 查询执行 + 指标/Schema生成）
        skills.py            # 领域知识与操作指南（6个内置技能）
        state.py             # Agent状态管理（ReAct状态机）
        tools.py             # MCP风格工具定义（5个真实工具 + ToolContext）
        engine.py            # Agent核心引擎（ReAct循环 + 知识库/图谱增强 + 状态持久化）

    kg/                     # 知识图谱模块
        __init__.py
        rules.py             # 规则实体提取器（正则+词典匹配）
        llm_extractor.py     # LLM实体/关系提取（prompt模板）
        graph.py             # 图谱查询引擎（邻居、路径、子图、QA增强）

    rag/                    # 向量检索模块
        __init__.py
        embedder.py          # 文本分块、向量嵌入、相似度检索、**知识图谱自动提取**

    static/
        css/style.css        # 样式（含暗色主题 CSS 变量系统）
        js/                  # 前端模块化 JS
            app.js           # 入口文件：主题、导航、初始化、仪表盘
            utils.js         # 通用工具函数（showToast、escapeHtml 等）
            api.js           # API 封装（apiGet、apiPost、apiPut、apiDelete）
            knowledge.js     # 知识库模块（**含知识图谱视图切换**）
            qa.js            # 知识问答模块（含流式输出）
            kg.js            # 知识图谱可视化模块（vis.js 力导向图，**已合并到知识库**）
            sql-tools.js     # SQL 工具模块
            log-analysis.js  # 日志分析模块
            manuals.js       # 操作手册模块
            commands.js      # 命令速查模块
            topology.js      # 集群拓扑模块
            agent.js         # 智能运维Agent模块（ReAct循环可视化）

    templates/
        index.html           # 单页应用 HTML

    data/                   # 运行时数据（自动创建）
        db_tool.db           # SQLite 数据库
        knowledge/           # 按数据库类型分目录存储知识库文件
        manuals/             # 操作手册文件
        commands/            # 命令库 JSON 文件
        models/              # sentence-transformers 模型缓存
        json_backup/         # 迁移前的 JSON 文件备份

    create_import_template.py  # Excel 导入模板生成脚本
    cluster_topology_import_template_v2.xlsx  # 集群拓扑批量导入模板
```

## 数据库表结构

| 表名 | 用途 |
|------|------|
| config | 键值对配置（API 地址、密钥、模型名、多模型配置等） |
| db_types | 数据库类型定义（MySQL、Oracle 等） |
| knowledge_files | 知识库文件元数据 + 解析后的文本内容 |
| qa_history | 问答历史记录 |
| favorites | 文件收藏 |
| log_analysis_tasks | 日志分析任务 |
| log_analysis_files | 日志分析文件 |
| resource_pools | 资源池信息 |
| clusters | 集群信息（属于某个资源池） |
| servers | 物理机（含 CPU、内存、机房等字段） |
| instances | 实例 |
| tenants | 租户（实例集群） |
| tenant_instances | 租户实例关联 |
| instance_relations | 实例间关系 |
| embeddings | 文本块向量嵌入（RAG 用） |
| kg_entities | 知识图谱实体表 |
| kg_relationships | 知识图谱关系表 |
| kg_chunk_entities | chunk-实体关联表 |
| operation_logs | 操作日志 |
| feature_config | 功能配置开关 |
| agent_ssh_connections | SSH连接配置（目标服务器） |
| agent_db_connections | 数据库连接配置（用于SQL查询） |
| agent_sessions | Agent会话 |
| agent_steps | Agent执行步骤（ReAct过程记录） |
| agent_skills | Agent Skills（操作指南/领域知识） |

## 九大功能模块

### 1. 知识库（/api/knowledge/*）
- 按数据库类型组织文件
- 支持上传 txt/md/pdf/docx/xlsx/html 等格式
- 上传时自动解析文件正文内容存入数据库
- 全文搜索 + 标签过滤
- 收藏夹功能
- **知识图谱自动提取**：上传/重建索引时自动提取实体和关系
- **知识图谱可视化**：知识库页面支持文件视图/图谱视图切换

### 2. 知识问答（/api/qa/*）
- 对话式界面，调用 LLM 回答数据库问题
- RAG 增强：优先用向量检索知识库内容作为上下文
- **知识图谱增强**：自动识别问题中的实体，注入图谱上下文（实体卡片、关系链）
- **数据库类型自动识别**：选择"自动选择"时，系统会从问题中自动识别数据库类型并切换到对应知识库
- 问题模板（报错处理、语法查询、性能问题等）
- 对话历史持久化
- **支持模型切换**：可在多个已配置模型中选择

### 3. SQL 工具（/api/sql/*）
- SQL 审核：检查语法、性能、安全性、最佳实践
- SQL 格式化：美化 SQL 语句
- SQL 转换：跨数据库方言翻译（如 MySQL → Oracle）
- 执行计划分析：粘贴 EXPLAIN 结果，AI 分析瓶颈和索引建议
- **支持模型切换**：可在多个已配置模型中选择

### 4. 操作手册（/api/manuals/*）
- 上传管理 SOP 文档
- 支持下载和删除
- 支持 txt/log/sql/py/sh 等文本文件预览

### 5. 命令速查（/api/commands）
- 按数据库类型的命令速查表
- 内置 MySQL、Oracle、达梦、OceanBase 默认命令
- 支持添加自定义分类和命令
- 支持删除自定义命令（鼠标悬停浮现删除按钮）
- 点击复制到剪贴板
- 跨库搜索命令

### 6. 集群拓扑（/api/topology/*）
- 资源池管理（增删改查）
- 集群管理（属于某个资源池）
- 节点管理（支持 CPU、内存、机房信息展示）
- 实例管理（主/从/CN/DN/GTM 角色）
- 租户管理（实例集群的逻辑分组）
- **统计视图**：聚合展示所有集群的宏观数据（集群数、服务器数、实例数、租户数），支持按集群/数据中心/数据库类型/环境筛选
- **拓扑视图**：HTML 渲染拓扑图，按机房层级分组展示
- **批量导入**：支持从 Excel 文件批量导入服务器和实例数据
- 支持单机/主从/双主/集群/分布式拓扑类型
- **机房层级分组展示**
- 集群名称点击重命名
- 节点设备类型：非信创物理机/非信创虚拟机/海光物理机/海光虚拟机/鲲鹏物理机/鲲鹏虚拟机
- 节点角色：计算节点/存储节点/管理节点

### 7. API 配置（/api/config/*）
- **多模型配置管理**：支持添加、编辑、删除多个 LLM 模型
- **功能配置开关**：为8个模块添加开关，控制导航栏显示/隐藏
- 模型切换：知识问答和 SQL 工具中可选择不同模型
- 连接测试

### 8. 日志分析（/api/log-analysis/*）
- 多轮渐进式 LLM 分析：意图识别 → 日志筛选 → 根因分析 → 报告生成
- SSE 流式输出：实时展示分析进度和每个步骤的耗时
- 知识库 RAG 增强：根据选择的数据库类型查询对应知识库
- 支持上传多份日志文件（.txt, .log, .md, .csv 等格式）
- 分析任务历史记录，支持查看历史报告
- 支持数据库类型选择，提高分析准确性
- 结构化报告：包含问题根因、影响范围、解决方案、预防措施、关注指标

### 9. 智能运维Agent（/api/agent/*）
- **ReAct 循环引擎**：Thought → Action → Observation → Conclusion 自主决策，观察结果回流对话历史实现链式推理
- **真实工具执行**：5 个工具均为真实实现
  - `query_database` — 按 db_type 连接目标库执行只读 SQL（pymysql/oracledb/psycopg2/dmPython）
  - `execute_command` — 通过 paramiko SSH 执行白名单数据库命令
  - `get_schema_info` — 表清单/表结构查询（按 db_type 生成）
  - `get_performance_metrics` — 会话/锁/等待/Top SQL/表占用指标
  - `retrieve_knowledge` — 知识库向量检索
  - 工具执行双重安全校验（引擎 + 工具自身），表名经白名单校验防注入
- **Harness 安全约束框架**：SQL 白名单 + 命令白名单（按操作级别），剥离注释校验、移除 SQL 客户端直通，禁止危险操作
- **知识库 + 知识图谱双增强**：执行前检索知识库（阈值 0.55/0.60），并注入图谱实体卡片/关系链上下文
- **Skills 领域知识**：6 个内置技能（慢查询诊断、Oracle RAC 检查、备份检查、MySQL 性能分析、AWR 分析、达梦状态检查）
- **SSE 流式输出**：实时展示思考过程、工具执行、观察结果、最终结论
- **SSH/数据库连接管理**：前端表单配置多个目标服务器和数据库连接（凭据加密存储）
- **会话持久化**：每步写入 `agent_steps`，会话状态更新到 `agent_sessions`，历史可回放
- **前端交互**：停止按钮（可中断 SSE）、折叠式思考/工具消息、结果表格化渲染
- **只读模式**：默认只读，禁止任何修改数据的操作
- **置信度标注**：🟢高/🟡中/🔴低 三级置信度标识

### 10. 知识图谱（已合并到知识库模块）
- **Chunk-Entity 混合图谱**：复用现有 13,153 个 chunk 作为文档层，增量添加 44,467 个实体节点
- **14 种实体类型**：数据库产品、版本、参数、错误码、SQL 语句、函数、系统视图、命令工具、架构、性能指标、概念、故障场景、操作系统、硬件
- **11 种关系类型**：belongs_to、compatible_with、requires、has_parameter、similar_to 等
- **混合提取策略**：规则匹配（正则+词典）+ LLM 提取
- **可视化浏览**：vis.js 力导向图，支持拖拽、缩放、点击展开邻居
- **QA 增强**：从检索到的 chunk 中提取关联实体，构建图谱上下文注入 prompt
- **实体搜索**：支持模糊搜索和邻居子图展示
- **关系推理**：版本归属、参数归属、跨产品映射等规则推理
- **前端集成**：知识库页面支持文件视图/图谱视图切换（参考集群拓扑视图切换样式）

## 支持的数据库类型

默认：MySQL、Oracle、达梦(DM)、GoldenDB、OceanBase、TDSQL、GaussDB、PostgreSQL、MongoDB
可通过 API 自定义添加更多类型。

## RAG + 知识图谱增强工作流程

```
用户提问 → Embedder 计算查询向量
         → 从 embeddings 表检索最相似的 top-5 文本块
         → 从 chunk 关联的 kg_entities 提取实体卡片和关系链
         → 拼接为上下文（知识库内容 + 图谱实体/关系）
         → 发送给 LLM 生成回答
```

如果 sentence-transformers 未安装或向量索引为空，自动回退到关键词匹配检索。

### RAG 分块策略

| 参数 | 值 | 说明 |
|------|-----|------|
| chunk_size | 2000 | 每块目标字符数 |
| overlap | 100 | 相邻块重叠字符数 |
| chunks 限制 | 无限制 | 不截断，确保大文件完整索引 |
| 相似度阈值 | 0.55 | 余弦相似度阈值 |
| 模型 | moka-ai/m3e-base | 中文语义理解更优 |

### 知识图谱数据规模

| 指标 | 数值 |
|------|------|
| 实体总数 | **44,963** |
| 关系总数 | **12,790** |
| chunk 关联 | **211,510** |
| 实体类型 | 14 种 |
| 关系类型 | 5 种 |

**实体类型分布：**
| 类型 | 数量 | 说明 |
|------|------|------|
| parameter | 17,675 | 数据库参数 |
| version | 14,107 | 版本号 |
| function | 8,409 | 函数 |
| error_code | 2,522 | 错误码 |
| system_view | 2,126 | 系统视图 |
| sql_statement | 30 | SQL语句 |
| database_product | 21 | 数据库产品 |
| command_tool | 17 | 命令工具 |
| concept | 17 | 概念 |
| operating_system | 12 | 操作系统 |
| performance_metric | 12 | 性能指标 |
| architecture | 10 | 架构 |
| hardware | 5 | 硬件 |

**关系类型分布：**
| 类型 | 数量 | 说明 |
|------|------|------|
| has_version | 9,785 | 产品→版本 |
| has_parameter | 1,783 | 产品→参数 |
| has_error_code | 1,068 | 产品→错误码 |
| has_architecture | 97 | 产品→架构 |
| requires | 57 | 产品→操作系统 |

## 开发注意事项

重构后的 JS 采用模块化设计，每个模块职责单一：

| 文件 | 职责 |
|------|------|
| `app.js` | 入口文件：主题切换、导航、初始化、仪表盘、通用函数 |
| `utils.js` | 通用工具函数（showToast、escapeHtml、formatFileSize 等） |
| `api.js` | API 请求封装（apiGet、apiPost、apiPut、apiDelete） |
| `knowledge.js` | 知识库模块（文件列表、上传、搜索、收藏，**含知识图谱视图切换**） |
| `qa.js` | 知识问答模块（对话、流式输出、历史记录） |
| `sql-tools.js` | SQL 工具模块（审核、格式化、转换、执行计划） |
| `log-analysis.js` | 日志分析模块（多轮 LLM 分析、SSE 流式输出） |
| `manuals.js` | 操作手册模块（列表、上传、预览） |
| `commands.js` | 命令速查模块（分类、命令、删除、搜索） |
| `topology.js` | 集群拓扑模块（集群、节点、实例、租户管理） |
| `agent.js` | 智能运维Agent模块（ReAct循环可视化、SSH/DB连接管理） |
| `kg.js` | 知识图谱可视化模块（vis.js 力导向图、实体搜索、邻居展开，**已合并到知识库**） |
| `config.js` | 系统配置模块（模型管理、数据库类型、日志） |

