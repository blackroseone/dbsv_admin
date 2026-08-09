# DBSV 版本更新记录

## 开发人：顾云波

> 📌 配套文档：
> - `project.md` — 项目概述、技术栈、功能模块
> - `version_update.md` — 版本更新记录
> - `code_desc.md` — 代码结构文档（函数/API 详细说明）
> - `tables_desc.md` — 数据库表结构
> - `deploy.md` — 部署指南

## v3.0.2 (2026-08-08)

### 🤖 智能运维 Agent 全面接通（阶段1-4）
- **真实工具执行**：5 个工具从桩改为真实实现
  - `query_database`：按 db_type 连接目标库执行只读 SQL（新增 `agent/connectors.py`，支持 pymysql/oracledb/psycopg2/dmPython）
  - `execute_command`：通过 paramiko SSH 执行白名单数据库命令
  - `get_schema_info` / `get_performance_metrics`：按 db_type 生成只读查询
  - `retrieve_knowledge`：知识库向量检索
  - 工具执行双重安全校验 + 表名白名单防注入；新增 `ToolContext` 注入连接上下文
- **ReAct 链式推理**：观察结果回流对话历史，模型可基于工具结果继续推理
- **知识图谱接入**：检索 chunk 后注入图谱实体卡片/关系链（RAG + 图谱双增强）
- **会话持久化**：每步写入 `agent_steps`，会话状态更新到 `agent_sessions`，历史可回放
- **前端改版**：SSH/DB 连接配置弹窗、停止按钮（AbortController）、折叠式消息、结果表格化、完整 Agent 样式
- 检索阈值对齐 0.55/0.60

### 🎨 前端视觉优化
- **主题重构**：亮色主题现代化（侧边栏改中性深色、单强调色、中性阴影），明暗主题统一蓝色 accent，补齐 `--primary-color` 定义
- **统计卡片渐变收敛**：5 组随机鲜艳渐变改为冷色系蓝青 + 暖色琥珀点缀
- **导航 SVG 图标**：10 个导航项 + logo 从 emoji 换为 stroke 风格 SVG（当前色自适应主题）
- **字体层级**：中文字体栈 + 抗锯齿，标题字重/字距统一
- **模块样式均衡**：补齐 `btn-success`/`btn-xs`/`btn-icon` 按钮变体、Agent 知识引用块、tab-content、拓扑服务器标签等无样式组件
- **交互与可访问性**：模块切换淡入动画、`:focus-visible` 焦点环、按钮/表单禁用态
- **响应式**：侧边栏可折叠（图标栏模式，localStorage 记忆）+ 窄屏（<768px）自动收窄
- **侧边栏折叠稳定**：折叠/展开时导航项/暗色按钮/底部统计位置稳定不弹跳（flex 布局钉底、文字不换行、导航项高度由图标决定、展开过渡期无水平滚动条）
- **问答展示**：Markdown 表格渲染（修复多列分隔行识别）、行内/块级代码统一去边框、流式智能跟随滚动、空行直接删除（段落间只留一个普通换行）
- **智能运维模块**：补模块标题、连接配置弹窗、停止按钮、折叠式消息、完整样式

### 🛡️ 安全加固
- **路径净化**：新增 `safe_filename`/`safe_join`，修复 knowledge/manuals/log_analysis/topology/commands 多处路径穿越（任意文件读写）
- **Agent 防线**：`validate_sql` 剥离注释后逐语句校验 + 危险关键字 token 扫描；`validate_command` 按操作级别约束 + 动作词 + 危险特征；移除可内嵌 SQL 的客户端命令
- **凭据加密**：SSH/DB 连接密码/私钥 Fernet 加密存储（新增依赖 `cryptography`）
- **前端 XSS**：`escapeHtml` 补引号转义、新增 `escapeJsAttr`，全量替换 inline 事件处理器与未转义插入点
- 移除明文 api_key 返回、统一 clusters/resource_pools schema

### 🧠 RAG 与知识图谱正确性
- `\b` 词边界在中文语境失配（"使用MySQL数据库"）已修复，实体召回率提升
- 版本提取：多产品同版本各出实体、支持 Oracle 19c 字母后缀、通用版本前缀去重
- 函数提取过滤 SQL 关键字（IN/OVER/CASE）；共现关系按位置邻近收敛
- 模型不可用时 QA 自动回退关键词检索；分块参数统一到 config（2000/100）
- `find_shortest_path` 双向遍历；`search_entities` LIKE 通配符转义

> 完整审查结论见 `code_review_2026-08-07.md`。

## v3.0.1 (2026-08-05)

### 🗂️ 集群拓扑批量导入功能
- **Excel 导入模板**：新增 `cluster_topology_import_template_v2.xlsx`，支持两个工作表
  - 服务器清单：资源池 + 集群 + 服务器（按 IP 去重，ID 自动生成）
  - 实例清单：租户 + 实例（通过 IP 关联服务器，自动填入 server_id 和 resource_pool_id）
- **下拉框数据验证**：模板中关键字段支持下拉选择
  - 数据库类型：Oracle, PostgreSQL, MongoDB, GoldenDB, OceanBase, GaussDB, DM, TDSQL, MySQL
  - 环境：production, dev-test, uat-prod
  - 节点角色：计算节点, 存储节点, 管理节点
  - 硬件类型：非信创物理机, 非信创虚拟机, 海光物理机, 海光虚拟机, 鲲鹏物理机, 鲲鹏虚拟机
  - 租户拓扑类型：master-slave, single, mha, paxos/raft, rac
  - 租户规格：macro-1c4g, macro-2c8g, macro-4c16g, small-8c16g, small-16c64g, medium-32C128G, large-64c256g, exlu-128c512g
  - 实例角色：master, slave, single
- **示例数据自动跳过**：识别斜体字体或灰色背景的行作为示例数据，导入时自动忽略
- **导入 API**：新增 3 个批量导入接口
  - `POST /api/topology/import/servers` — 导入服务器清单
  - `POST /api/topology/import/instances` — 导入实例清单
  - `POST /api/topology/import` — 一键导入完整拓扑

### 🔧 前端修复
- **添加资源池按钮修复**：将 `showAddResourcePoolDialog()` 改为 `showAddClusterDialog()`，解决按钮无响应问题
- **节点角色统一**："监控节点" 统一改为 "管理节点"
  - 前端下拉框选项更新（templates/index.html）
  - 拓扑图渲染逻辑更新（static/js/topology.js）
  - 数据库数据迁移：更新 9 条服务器记录

### 🔧 数据库修复
- **数据库路径修复**：`db/database.py` 的 `BASE_DIR` 从 `db/` 目录改为项目根目录
  - 修复前：`D:\claude\dbsv_admin\db\data\db_tool.db`
  - 修复后：`D:\claude\dbsv_admin\data\db_tool.db`
  - 解决向量索引显示为 0 的问题

### 🔧 代码结构优化
- **utils 目录重构**：将 `utils.py` 改为 `utils/` 包，新增 `utils/topology_import.py` 模块

---

## v3.0.0 (2026-07-29)

### 🕸️ 知识图谱模块（重大更新）

#### 核心架构
- **Chunk-Entity 混合图谱**：复用现有 13,153 个 chunk 作为文档层，增量添加 **44,963** 个实体节点
- **SQLite 存储**：3 张核心表（kg_entities、kg_relationships、kg_chunk_entities）+ 7 个索引
- **混合提取策略**：规则匹配（正则+词典）+ LLM 提取（深度提取）

#### 实体提取（14 种类型）
- **规则提取**：数据库产品（21）、版本号（**14,107**）、错误码（**2,522**）、参数（**17,675**）、函数（**8,409**）、系统视图（**2,126**）、SQL 语句（**30**）、操作系统（12）、硬件（5）、性能指标（12）、架构（10）、概念（**17**）、命令工具（**17**）
- **LLM 提取**：复杂概念、架构模式、故障场景、跨产品关系

#### 知识图谱数据规模（截至 v3.0.1）
| 指标 | 数值 |
|------|------|
| 实体总数 | **44,963** |
| 关系总数 | **12,790** |
| chunk 关联 | **211,510** |

#### 可视化浏览
- **vis.js 力导向图**：支持拖拽平移、滚轮缩放、点击展开邻居
- **实体搜索**：模糊搜索 + 邻居子图展示
- **类型筛选**：实体类型和关系类型筛选面板
- **详情面板**：实体属性、关系列表、来源文档

#### QA 增强
- **自动实体识别**：从检索到的 chunk 中提取关联实体
- **上下文注入**：将实体卡片和关系链注入 LLM prompt
- **关系链推理**：展示实体间的路径（如 MySQL → has_parameter → innodb_buffer_pool_size）

#### API 接口
- `/api/kg/entities/search` - 实体搜索
- `/api/kg/entities/<id>` - 实体详情
- `/api/kg/entities/<id>/neighbors` - 邻居查询
- `/api/kg/path` - 最短路径
- `/api/kg/subgraph` - 子图提取
- `/api/kg/qa-enhance` - QA 增强上下文
- `/api/kg/stats` - 图谱统计
- `/api/kg/entity-types` - 实体类型分布

#### 前端模块
- **导航栏**：知识图谱**已合并到知识库模块**，不再作为独立导航项
- **快捷键**：~~Ctrl+9~~ 已移除（知识图谱合并到知识库）
- **工具栏**：重置视图、展开邻居、清除选择按钮位于图谱上方（**在知识库图谱视图中展示**）

### 🔧 新增文件
| 文件 | 功能 |
|------|------|
| `kg/rules.py` | 规则实体提取器（14 种实体类型） |
| `kg/llm_extractor.py` | LLM 实体/关系提取（prompt 模板） |
| `kg/graph.py` | 图谱查询引擎（邻居、路径、子图、QA 增强） |
| `db/kg_database.py` | 知识图谱 CRUD 操作 |
| `routes/kg.py` | 知识图谱 REST API（12 个接口） |
| `static/js/kg.js` | 前端可视化（vis.js 力导向图，**已合并到知识库模块**） |

### 🔧 修改文件
| 文件 | 修改内容 |
|------|---------|
| `rag/embedder.py` | 重建索引时自动提取知识图谱实体 |
| `routes/knowledge.py` | 上传/重建/扫描流程中集成知识图谱提取；`add_knowledge_file()` 返回 file_id |
| `db/database.py` | 新增 kg_entities、kg_relationships、kg_chunk_entities 表；`add_knowledge_file()` 返回 file_id |
| `routes/qa.py` | 问答中融合知识图谱上下文（实体卡片 + 关系链） |
| `templates/index.html` | 添加知识图谱导航和模块 HTML（**v3.0.1 已合并到知识库**） |
| `static/js/app.js` | 添加 Ctrl+9 快捷键和 kg 模块切换（**v3.0.1 已移除，合并到知识库**） |
| `static/css/style.css` | 添加知识图谱样式（~300 行，**v3.0.1 新增知识库视图切换样式**） |

---

## v3.0.1 (2026-07-30)

### 🕸️ 知识图谱模块重构

#### 知识图谱合并到知识库
- **移除独立导航入口**：知识图谱不再作为独立模块存在，从导航栏移除
- **视图切换功能**：知识库页面右上角添加"文件视图/图谱视图"切换按钮
  - 参考集群拓扑模块的视图切换按钮样式
  - 文件视图：展示文件列表（原有功能）
  - 图谱视图：展示知识图谱可视化（vis.js 力导向图）
- **快捷键调整**：移除 `Ctrl+9` 知识图谱快捷键

#### 知识图谱自动提取增强
- **上传流程集成**：`routes/knowledge.py` `upload_file()` 上传文件后自动提取知识图谱实体
- **重建索引集成**：所有重建索引入口（流式重建、单文件重建、按类型重建）均自动提取知识图谱
- **扫描流程集成**：`scan_files()` 扫描新文件时自动提取知识图谱
- **数据库层优化**：`add_knowledge_file()` 返回 `file_id`，支持后续知识图谱关联

#### 前端修改
| 文件 | 修改内容 |
|------|---------|
| `templates/index.html` | 移除知识图谱独立模块 HTML，在知识库模块添加视图切换按钮和图谱容器 |
| `static/css/style.css` | 添加 `.knowledge-header-row`、`.knowledge-view-switch`、`.knowledge-view` 样式 |
| `static/js/knowledge.js` | 添加 `switchKnowledgeView()` 函数，支持文件视图/图谱视图切换 |
| `static/js/app.js` | 移除 `kg` 模块切换逻辑和快捷键，知识库加载时根据当前视图初始化图谱 |

#### 后端修改
| 文件 | 修改内容 |
|------|---------|
| `routes/knowledge.py` | 上传/重建/扫描流程中集成知识图谱提取；`add_knowledge_file()` 返回 file_id |
| `db/database.py` | `add_knowledge_file()` 返回插入的文件 ID |
| `rag/embedder.py` | `rebuild_all()` 和 `rebuild_single()` 已包含知识图谱提取（原有功能） |

---

## v2.5.1 (2026-07-28)

### 🎯 知识库 RAG 优化
- **分块策略优化**：`chunk_size` 从 500 提升到 **2000**，`overlap` 从 50 提升到 **100**
- **移除 chunks 数量限制**：删除 100 chunks 截断限制，确保大文件内容完整索引
- **相似度阈值调整**：从 0.75 降低到 **0.55**，提高知识库召回率
- **向量索引重建**：达梦（26 文件，1,799 embeddings）、GoldenDB（10 文件，698 embeddings）、GaussDB（**8 文件，352 embeddings，496+ 实体**）、OceanBase（**14 文件，5,556 embeddings**）全部重建

### 🎯 知识问答前端优化
- **置信度位置调整**：从消息气泡内移至消息容器外部左侧，避免遮挡内容
- **输出速度优化**：添加节流渲染（16ms），提升流式输出流畅度
- **滚动行为修复**：删除强制滚动逻辑，用户可自由滑动查看历史内容

### 🎯 仪表盘改进
- **四列布局**：统计卡片改为 4 列展示，信息密度提升
- **向量索引统计**：新增 `embeddings_by_db_type` 统计，展示各数据库类型向量索引数量
- **前端图表**：新增 `renderEmbeddingChart()` 渲染向量索引分布饼图

### 🎯 重建索引接口重构
- **流式重建**：`/api/knowledge/reindex/stream` 改为逐个文件处理，SSE 实时返回进度
- **单文件重建**：新增 `/api/knowledge/reindex/file` 接口，支持单个文件重建
- **按类型重建**：新增 `/api/knowledge/reindex/db-type` 接口，支持按数据库类型批量重建
- **超时优化**：流式接口设置 10 分钟超时，避免大文件重建超时

### 🔧 代码修复
- **修复流式输出 bug**：`routes/qa.py` 添加缺失的 `call_llm_stream` 导入
- **修复强制 UTF-8 输出**：PowerShell 中执行 Python 时添加 `sys.stdout.reconfigure(encoding='utf-8')`

---

## v2.5.0 (2026-07-24)

### 🤖 智能运维Agent模块
- **ReAct 循环引擎**：Thought → Action → Observation → Conclusion 自主决策模式
- **Harness 安全约束框架**：SQL 白名单 + 命令白名单，禁止危险操作（DROP/DELETE/UPDATE/INSERT等）
- **Skills 领域知识**：6 个内置技能（慢查询诊断、Oracle RAC 检查、备份检查、MySQL 性能分析、AWR 分析、达梦状态检查）
- **知识库增强**：执行前自动检索知识库，无足够知识时发出警告，三级置信度标注（🟢高/🟡中/🔴低）
- **MCP 风格工具定义**：5 个标准化工具（query_database、execute_command、get_schema_info、get_performance_metrics、retrieve_knowledge）
- **SSE 流式输出**：实时展示思考过程、工具执行、观察结果、分析结论
- **SSH/数据库连接管理**：支持配置多个目标服务器和数据库连接（密码/密钥认证）
- **只读模式**：默认只读，禁止任何修改数据的操作

### 🔧 数据库变更
- 新增 `agent_ssh_connections` 表：SSH连接配置
- 新增 `agent_db_connections` 表：数据库连接配置
- 新增 `agent_sessions` 表：Agent会话
- 新增 `agent_steps` 表：Agent执行步骤（ReAct过程记录）
- 新增 `agent_skills` 表：Agent Skills（操作指南/领域知识）

### 📝 代码优化
- 新增 `agent/` 目录：harness.py、skills.py、state.py、tools.py、engine.py
- 新增 `routes/agent.py`：Agent核心API路由
- 新增 `routes/agent_connections.py`：SSH/DB连接管理API
- 新增 `static/js/agent.js`：Agent前端交互模块
- 更新 `templates/index.html`：Agent模块UI布局

---

## v2.4.2 (2026-07-16)

### 🔒 安全漏洞修复
- **修复路径遍历漏洞**: `routes/knowledge.py` 添加 `_validate_db_type()` 函数，校验 `db_type` 参数，禁止路径遍历字符
- **修复 XSS 漏洞**: `static/js/utils.js` 增强 `escapeJs()` 函数，添加 HTML 特殊字符转义（`& < > " '`）
- **移除 Base64 伪加密**: `routes/topology.py` 移除未使用的 `encrypt_password`、`decrypt_password`、`mask_password` 函数
- **SQL 注入防护**: 审查所有动态 SQL 拼接点，确认均使用参数化查询

### ⚡ 性能优化
- **消除 N+1 查询**: `db/database.py` 重构 `get_resource_pools()`，使用 JOIN 和 GROUP BY 一次性获取统计信息
- **重构过长函数**:
  - `app.py`: `scan_knowledge_files` 拆分为 `_scan_directory`、`_process_single_file`、`_generate_embeddings_for_file`
  - `db/database.py`: `get_clusters` 拆分为 `_fetch_servers_for_cluster`、`_fetch_tenants_for_cluster`、`_build_cluster_data`
  - `static/js/topology.js`: `renderTopology` 拆分为 `_renderClusterHeader`、`_renderClusterSummary`、`_renderServerCard`、`_renderDatacenterSection`、`_renderTenantSection`

### 🔧 代码质量优化
- **提取重复代码**: `utils.py` 添加 `stream_llm_response()` 通用 SSE 流式响应生成器，供 `routes/qa.py` 和 `routes/sql_tools.py` 复用
- **优化异常处理**: `app.py` 将宽泛的 `except Exception` 改为捕获具体异常类型（`ImportError`、`RuntimeError`、`OSError` 等）
- **修复线程安全**: `db/database.py` 添加 `PRAGMA busy_timeout=5000`，优化 `close_db()` 异常处理
- **修复内存泄漏**: `static/js/qa.js` 在 finally 中释放 `reader` 引用
- **优化 DOM 操作**: `static/js/qa.js` `switchConversation` 使用 `DocumentFragment` 批量插入消息
- **封装全局变量**: `static/js/app.js` 使用 `DBTool` 命名空间封装全局变量
- **增强 API 错误处理**: `static/js/api.js` `apiGet` 添加 Content-Type 检查，非 JSON 响应返回友好错误
- **统一 JSON 导入**: `db/database.py` 将 `import json` 移到模块顶部
- **添加类型注解**: `db/database.py` `get_db_types()` 添加 `list[dict]` 返回类型注解
- **消除硬编码配置**: `app.py` 定时任务间隔从环境变量 `DB_TOOL_SYNC_INTERVAL_HOURS` 读取
- **添加数据库复合索引**: `db/database.py` 为 `knowledge_files` 表添加 `idx_knowledge_files_db_type_created` 复合索引
- **添加事务上下文管理器**: `db/database.py` 新增 `transaction` 类，支持显式事务管理
- **创建 requirements.txt**: 列出所有 Python 依赖并锁定版本
- **动态版本号注入**: `app.py` 添加 `APP_VERSION` 变量，模板通过 Jinja2 注入 CSS/JS 版本号
- **搜索输入防抖**: `static/js/knowledge.js` 添加 `debounce()` 函数和 `debouncedSearchKnowledge`
- **提取配置文件**: 新增 `config.py` 集中管理配置项
- **规范化日志记录**: `app.py` 将 `print()` 替换为 `logging` 模块
- **清理未使用变量**: `static/js/topology.js` 移除未使用的 `currentTopologyData` 变量
- **添加函数别名**: `db/database.py` `get_clusters()` 添加 `get_topology_data()` 别名，更准确反映返回资源池拓扑数据的语义

### 🐛 知识问答功能修复
- **恢复清空会话按钮**: `templates/index.html` 在新增会话按钮旁添加清空按钮，支持一键清空所有会话
- **自动更新会话标题**: `static/js/qa.js` 新建会话第一次提问后，自动将问题内容截取前20字作为会话标题
- **修复删除会话刷新问题**: `static/js/qa.js` 删除会话后添加 `await` 确保列表正确刷新

### 📝 文档更新
- **更新 `project.md`**: 修正"七大功能模块"为"八大功能模块"，更新 API 配置模块描述
- **更新 `code_desc.md`**: 版本号 v2.4.2，更新函数说明，添加开发规范

---

## v2.4.1 (2026-07-16)

### 🎯 模型加载优化
- **本地模型缓存检测**: 启动时自动检测 sentence-transformers 模型是否已在本地缓存
- **跳过网络下载**: 检测到本地缓存时直接加载，避免重复连接 HuggingFace
- **离线模式支持**: 设置 `TRANSFORMERS_OFFLINE=1` 环境变量可完全离线运行

### 🎯 编码规范强化
- **新增编码规范章节**: 在 `code_desc.md` 中添加编码规范说明
- **强制 UTF-8 编码**: 所有文本文件必须使用 UTF-8 编码，禁止 GBK/GB2312
- **文件操作规范**: Python 文件操作必须显式指定 `encoding='utf-8'`
- **乱码恢复指南**: 提供编码问题排查和恢复方法

### 🐛 问答模块修复
- **修复 qa.js 语法错误**: 将 Python 风格文档字符串改为 JavaScript 注释
- **修复会话列表不显示**: 添加 `switchModule('qa')` 时调用 `loadConversations()`
- **修复浏览器缓存**: 更新 `qa.js` 版本号强制刷新缓存

### 🔧 代码优化
- `rag/embedder.py`: 添加 `_check_model_cached()` 函数检测本地模型
- `static/js/app.js`: 添加 `qa` 模块切换时加载会话列表
- `static/js/qa.js`: 修复 4 处 Python 风格注释为 JavaScript 注释
- `templates/index.html`: 更新 `qa.js` 缓存版本号

---

## v2.4.0 (2026-07-14)

### 🎯 日志分析模块
- **多轮渐进式 LLM 分析**：支持意图识别 → 日志筛选 → 根因分析 → 报告生成
- **SSE 流式输出**：实时展示分析进度，每个步骤显示耗时
- **知识库 RAG 增强**：分析过程中自动查询知识库获取参考信息
- **分析任务历史**：支持查看历史分析报告，任务卡片展示数据库类型和文件列表
- **分析进度恢复**：返回列表后重新进入进度视图，保留已完成的步骤状态
- **结构化报告生成**：包含问题根因、影响范围、解决方案、预防措施等

### 🎯 数据库类型选择
- **日志分析支持数据库类型选择**：新建分析时可选择目标数据库类型
- **RAG 按类型过滤**：根据选择的数据库类型查询对应知识库
- **LLM 上下文增强**：分析提示词中加入数据库类型上下文，提高分析准确性
- **任务卡片展示数据库类型标签**

### 🔧 数据库变更
- `log_analysis_tasks` 表新增 `db_type` 字段
- `log_analysis_files` 表存储日志文件元数据和内容

### 📝 代码优化
- 新增 `log_analysis.py` 后端路由模块
- 新增 `log-analysis.js` 前端模块
- 新增日志分析进度展示 UI（意图识别、日志筛选、根因分析、报告生成）
- 新增分析耗时统计展示
- 新增数据库类型标签样式

---

## v2.3.2 (2026-07-13)

### 🎯 功能配置开关
- **新增功能配置页面**: 在系统配置中新增"功能配置"标签页
- **模块开关控制**: 为7个模块(知识库、知识问答、SQL工具、运维手册、命令速查、集群拓扑、仪表盘)添加开关
- **默认全部开启**: 所有模块默认开启，关闭后左侧导航栏隐藏该模块入口
- **iOS风格开关**: 开关采用iOS风格设计，开启状态为绿色
- **实时生效**: 修改开关后导航栏实时更新，无需刷新页面

### 🔧 数据库变更
- 新增 `feature_config` 表，存储模块功能配置
- 表字段: module_id, module_name, module_icon, is_enabled, sort_order

### 📝 代码优化
- 优化代码块样式，提高暗色主题下代码可读性
- 添加代码块边框和阴影效果
- 优化内联代码样式

---

## v2.3.1 (2026-07-08)

### 🎯 集群拓扑修复
- **clusters 表新增 resource_pool_id 字段**: 支持集群归属资源池,实现资源池与集群的一对多关系
- **集群名称显示修复**: 拓扑视图右侧显示集群名称而非 ID,提升可读性
- **自动集群创建**: 编辑节点时输入集群名称,后端自动查找或创建对应集群
- **统计视图修复**: 修复集群数量统计为 0 的问题,正确显示集群总数
- **服务器列表修复**: 修复服务器列表中集群列显示为空的问题
- **资源池合并**: 支持将多个 Woqu 系列资源池合并到同一资源池下
- **拓扑视图空状态修复**: 资源池无服务器时仍显示操作按钮(添加节点/修改资源池/删除资源池)
- **节点类型配置修复**: 修复 `nodeTypeConfig` 和 `hardwareTypeConfig` 未定义导致的拓扑图加载失败
- **HTML 结构修复**: 修复 `renderTopology` 函数中多余的 `</div>` 标签

### 🔧 数据库变更
- clusters 表新增 `resource_pool_id` 字段(外键关联 resource_pools 表)
- 使用数据库迁移脚本自动重建 clusters 表并保留原有数据

---

## v2.3.0 (2026-07-03)

### 🎯 集群拓扑统计视图
- 新增统计视图标签页，与拓扑视图切换展示
- 总览卡片：集群/服务器/实例/租户总数
- 分布图表：硬件类型、节点角色、数据中心
- 筛选功能：按集群/数据中心/数据库类型/环境筛选
- 详细表格：集群统计表、服务器列表
- 筛选栏固定，内容区域独立滚动

### 🎯 节点字段重构
- 节点类型拆分为节点角色 + 硬件类型
- 节点角色：计算节点/存储节点/监控节点
- 硬件类型：非信创物理机/虚拟机、海光物理机/虚拟机、鲲鹏物理机/虚拟机
- CPU 和内存字段从 description 中提取，独立展示

### 🎯 视图切换优化
- 统计视图和拓扑视图使用 iOS 风格切换按钮
- 切换按钮位于标题右侧，圆角设计
- 统计视图筛选栏固定，内容区域可滚动

### 🔧 其他优化
- 拓扑视图集群列表修复 ID 冲突问题
- 统计视图支持 flex 布局，切换视图时保持正确显示

---

## v2.2.0 (2026-06-30)

### 🎯 前端 JS 模块化重构
- 将 2900+ 行的 `app.js` 拆分为 10 个模块化文件
- 新增 `utils.js`：通用工具函数（showToast、escapeHtml、formatFileSize、escapeJs）
- 新增 `api.js`：API 请求封装（apiGet、apiPost、apiPut、apiDelete）
- 新增 `knowledge.js`：知识库模块独立
- 新增 `qa.js`：知识问答模块独立（含流式输出）
- 新增 `sql-tools.js`：SQL 工具模块独立
- 新增 `manuals.js`：运维手册模块独立
- 新增 `commands.js`：命令速查模块独立
- 新增 `topology.js`：集群拓扑模块独立
- 新增 `config.js`：系统配置模块独立
- `app.js` 保留为入口文件：主题切换、导航、初始化、仪表盘、通用函数

### 🎯 命令速查增强
- 支持删除自定义命令（鼠标悬停浮现删除按钮）
- 删除按钮位于命令右侧空白区域，不引起布局偏移
- 后端新增 DELETE `/api/commands/command` 接口

### 🎯 集群拓扑优化
- 集群列表移除删除按钮（避免误操作）
- 集群删除功能移至右侧详情头部
- 删除按钮与"添加节点"按钮并排展示

### 🎯 模型选择优化
- 修复模型下拉框加载逻辑，避免 `undefined` 错误
- 默认选项正确保留"使用默认模型"提示

### 🔧 其他优化
- 前端代码结构清晰，便于后续维护和扩展
- 各模块职责单一，降低耦合度

---

## v2.1.5 (2026-06-30)

### 🎯 多模型配置管理
- 支持添加、编辑、删除多个 LLM 模型配置
- 每个模型独立配置 API 地址、API Key、模型名称、显示名称
- 支持设置默认模型
- 模型列表卡片展示，带默认标识
- 兼容旧配置自动迁移

### 🎯 模型切换功能
- 知识问答模块增加模型选择下拉框
- SQL 工具模块增加模型选择下拉框
- 可选择使用默认模型或指定模型
- 模型名称在下拉框中展示显示名称

### 🎯 集群拓扑增强
- 节点卡片展示 CPU 和内存信息（⚡ CPU / 💾 内存）
- 添加/编辑节点对话框支持填写 CPU 和内存
- 服务器表新增 cpu、memory 字段

### 🎯 机房层级支持
- 集群拓扑支持机房（datacenter）层级分组
- 节点卡片显示 📍 机房标签
- 按机房分组展示拓扑图

### 🎯 集群名称重命名
- 点击右侧拓扑图顶部的集群名称可直接重命名
- 使用 prompt 输入框，无需额外编辑按钮

### 🔧 其他优化
- 操作日志页签展示区域加宽
- 运维手册支持中文文件名展示
- 修复 Oracle 图标显示（🏛️）
- 修复达梦（🐉）和 GaussDB（🦢）图标
- 修复 API 连接测试 temperature 兼容问题（Moonshot kimi-k2.6 只支持 temperature=1）
- 修复节点编辑窗口不显示问题（escapeJs 替代 escapeHtml）
- 修复实例编辑按钮无反应问题

---

## v2.1.0 (2026-06-29)

### 🌙 暗色主题
- 完整的暗色主题支持，基于 CSS 变量系统
- 亮色/暗色主题平滑切换，带过渡动画
- 主题设置自动保存到 localStorage，刷新后保持
- 采用 GitHub Dark 风格配色方案
- 侧边栏添加主题切换按钮（🌙/☀️）

### 📂 知识库自动扫描
- 应用启动时自动扫描 `data/knowledge/<db_type>/` 目录
- 直接放入目录的文件自动识别并入库
- 已入库文件不会重复扫描
- 不支持的文件格式自动跳过
- 扫描失败打印日志但不影响启动

### 🔧 代码质量优化
- 修复数据库索引错误（`idx_nodes_cluster` → `idx_servers_cluster` 等）
- 重构 LLM 调用代码，提取公共辅助函数减少重复
- 修复下拉框箭头在暗色主题下消失的问题
- CSS 版本号更新为 v2.1.0

---

## v2.1 (2026-06-27)

### 🎯 集群拓扑重构
- 重新设计数据结构，支持物理集群 → 物理机 → 实例的层级关系
- 新增租户（实例集群）概念，支持实例的逻辑分组
- 新增物理机管理功能
- 新增实例管理功能，支持记录 CPU、内存等资源规格
- 新增实例详情面板，点击实例可查看完整信息
- 拓扑图改为 HTML 渲染，物理机显示为虚线框

### ✨ 命令速查增强
- 新增添加分类功能，可自定义命令分类
- 新增添加命令功能，可为每个分类添加自定义命令
- 分类和命令支持持久化存储

### ✨ 运维手册改版
- 改为左侧列表、右侧内容的布局
- 支持 Markdown 文件自动渲染
- 新增工具栏，显示当前文件名和操作按钮
- 简化左侧列表，只显示文件名和大小

### 🔧 数据库顺序调整
- 调整默认数据库类型顺序：Oracle → MySQL → TDSQL → OceanBase → GoldenDB → 达梦 → GaussDB

### 📝 数据库表结构
- 新增 `servers` 表（物理机）
- 新增 `instances` 表（实例）
- 新增 `tenants` 表（租户）
- 新增 `tenant_instances` 表（租户实例关联）
- 新增 `instance_relations` 表（实例关系）
- 移除旧的 `nodes` 和 `node_connections` 表

---

## v2.0 (2026-06-19)

### 🎯 架构升级
- 从 db-tool-home 单体架构迁移到 db-tool 模块化架构
- 使用 SQLite 数据库替代 JSON 文件存储
- 采用 Blueprint 模块化设计
- 集成 RAG 向量检索能力（sentence-transformers）

### ✨ 新增功能

#### 仪表盘模块
- 系统统计数据总览（数据库类型数、知识库文件数、集群数等）
- 知识库文件分布图表
- 系统健康状态检查
- 快捷键说明面板

#### 知识库增强
- 文件在线预览功能（支持 txt, md, html, sql, json 等文本格式）
- 标签分类系统（安装部署、日常运维、故障处理、性能优化、备份恢复、安全管理、升级迁移、故障案例）
- 上传时可选择分类标签
- 文件列表显示标签信息
- 支持批量上传和文件夹上传
- 中文文件名支持

#### 运维手册增强
- 手册在线预览功能
- 手册列表显示预览状态

#### 命令速查增强
- 跨库搜索功能（一键搜索所有数据库的命令）
- 完整的 7 种数据库命令模板（MySQL、Oracle、达梦、OceanBase、GoldenDB、TDSQL、GaussDB）
- 实时搜索（输入即搜索）

#### 集群拓扑增强
- 拓扑配置导出功能
- 环境分组支持（生产、测试、开发）
- 密码加密存储（Base64 编码）

#### 系统配置增强
- 配置导入导出功能
- 操作日志系统（记录、查看、清空）
- 数据库类型管理（动态添加/删除）
- 多 Tab 布局（大模型配置、数据库类型、配置导入导出、操作日志）

#### 知识问答增强
- 流式输出（实时显示大模型回答）
- 停止功能（可中途停止输出）
- 历史记录左侧展示
- 单条历史记录删除
- 清空对话功能

#### SQL 工具增强
- 流式输出（审核、格式化、转换、执行计划分析）
- 更详细的审核 prompt

#### UI/UX 改进
- 深色主题侧边栏
- 版本号显示
- Emoji 图标丰富
- 快捷键系统（Ctrl+1~9 切换模块，Ctrl+K 搜索命令）
- 下拉选框样式优化
- 打字光标动画

### 🔧 问题修复
- 修复文件上传时中文文件名丢失问题
- 修复知识库增强检索在无文件时卡住问题
- 修复标签显示和编辑问题
- 修复 API URL 自动补全问题
- 优化 RAG 模型加载失败时的快速失败机制

### 📝 技术细节
- 后端：Flask + SQLite + sentence-transformers
- 前端：原生 HTML/CSS/JavaScript
- 流式输出：Server-Sent Events (SSE)
- 数据库：9 张表（config, db_types, knowledge_files, qa_history, favorites, clusters, nodes, node_connections, embeddings, operation_logs）

---

## v1.0 (2026-06-10)

### 初始版本
- 知识库文件管理
- 数据库知识问答
- SQL 审核工具
- 运维手册管理
- 常用命令速查
- 集群拓扑管理
- 大模型 API 配置

---

## 当前版本状态

已完成的优化：
- [x] SQLite 替代 JSON 文件存储
- [x] app.py 拆分为 Blueprint 模块
- [x] PDF/DOCX/XLSX 文件内容解析入库
- [x] sentence-transformers 向量检索升级 RAG
- [x] **暗色主题（v2.1.0）**
- [x] **知识库自动扫描（v2.1.0）**
- [x] **代码质量优化（v2.1.0）**
- [x] **多模型配置管理（v2.1.5）**
- [x] **集群拓扑节点展示 CPU/内存（v2.1.5）**
- [x] **机房层级分组（v2.1.5）**
- [x] **前端 JS 模块化重构（v2.2.0）**
- [x] **集群拓扑统计视图（v2.3.0）**
- [x] **节点设备类型和角色拆分（v2.3.0）**
- [x] **功能配置开关（v2.3.2）**
- [x] **代码块样式优化（v2.3.2）**
- [x] **clusters 表 resource_pool_id 字段（v2.3.1）**
- [x] **集群名称显示修复（v2.3.1）**
- [x] **自动集群创建（v2.3.1）**
- [x] **日志分析模块（v2.4.0）**
- [x] **数据库类型选择（v2.4.0）**
- [x] **模型本地缓存检测（v2.4.1）**
- [x] **编码规范强化（v2.4.1）**
- [x] **问答模块修复（v2.4.1）**
- [x] **安全漏洞修复（v2.4.2）**：SQL注入防护、Base64伪加密移除、XSS漏洞修复、路径遍历防护
- [x] **性能优化（v2.4.2）**：N+1查询消除、函数重构、代码质量提升
- [x] **智能运维Agent模块（v2.5.0）**：ReAct循环引擎、Harness安全约束框架、Skills领域知识、MCP工具定义、SSE流式输出、SSH/DB连接管理

---

## 后续规划和可优化方向

### 集群拓扑增强
- 租户管理功能完善
- 实例之间的连线（主从关系）
- 主从节点颜色区分
- 拓扑图导出为图片
- **容灾视图（跨机房复制关系可视化）**：支持展示实例间的同步/异步复制关系，横向排列机房，用连线表示复制链路

### 其他优化方向
- 用户认证与权限管理
- 慢查询日志解析分析
- 索引优化自动建议
- SQL 变更工单流程（提交→审核→执行→回滚）
- 对接 Prometheus/Grafana 监控指标
- 批量操作支持
- 故障知识图谱
- 巡检报告自动生成
- **SQL 注入防护增强**：定期审查所有 SQL 拼接点
- **密码安全存储**：引入 bcrypt/argon2 哈希方案
- **单元测试覆盖**：为核心业务逻辑添加 pytest 测试

## 开发注意事项

1. 所有 API 路由在 routes/ 下的 Blueprint 中定义，路径前无统一前缀
2. 数据库操作统一在 db/database.py 中，通过 get_db() 获取线程安全的连接
3. 文件内容解析在 utils.py 的 extract_content() 中，按扩展名分发
4. 前端模块化 JS 通过 `<script>` 标签按依赖顺序引入
5. 向量嵌入模型懒加载，首次调用 RAG 时才加载到内存
6. **多模型配置**：使用 llm_models 键存储模型列表，default_model_id 存储默认模型 ID