# dbsv_admin 全项目代码审查报告（2026-08-07）

审查范围：后端全部 14 个路由 + 基础设施 + RAG/图谱 + 智能运维 Agent + 前端 13 个 JS 与模板，共 6 组并行审查。每组均有代码级依据，关键疑点经实际运行验证（clusters 表结构、Harness 绕过、正则行为均已实测）。

## 一、高危问题（须优先修复）

### 1. 路径穿越 → 任意文件读取/删除/写入（6 处）

最严重、影响面最广的缺陷。**共同根因：`<filename>`/`db_type`/上传文件名直接拼进 `os.path.join` 后读写，无净化、无 `realpath` 校验**。Windows 下反斜杠不是 URL 段分隔符，`..%5c..%5c..%5cconfig.py` 即可穿越。

| 位置 | 漏洞 | 后果 |
|---|---|---|
| `routes/knowledge.py:170-187` | 删除接口 `os.remove()` 未净化文件名，无扩展名白名单 | 删任意文件（含 `data/db_tool.db` 整个数据库） |
| `routes/knowledge.py:541-566` | 预览接口 `open()` 未净化 | 读任意 `.py/.json/...`（含 SECRET_KEY） |
| `routes/manuals.py:77-90` | 删除手册同型 | 删任意文件 |
| `routes/manuals.py:100-121` | 预览手册同型（且无 db_type 校验，更易利用） | 读任意文件 |
| `routes/log_analysis.py:159-161` | 上传用 `file.filename` 直接存盘，未用 `secure_filename` | 任意位置写文件 |
| `routes/topology.py:642,684,726` | 导入临时路径 `os.path.join(tempdir, file.filename)` | 任意写 + 并发同名互相覆盖 |
| `routes/commands.py:14,23` | `db_type` 未白名单拼 `f"{db_type}.json"` | `db_type=..\\..\\config` 读/写任意 JSON |

**建议**：统一用 `secure_filename` + `os.path.realpath` + `commonpath` 前缀校验落盘路径；预览/下载改用 `send_from_directory`（自带 safe_join）；`db_type` 与已知类型集合白名单。

### 2. 集群拓扑数据读写表分裂（已实测确认）

`clusters` 表只有 `id, resource_pool_id, name, description, created_at`，但 `add_cluster`/`update_cluster` 写 `db_type/environment` 列 → **实测 `OperationalError: table clusters has no column named db_type`，全新安装创建集群必 500**。同时主读取路径 `get_topology_data()` 读 `resource_pools`，而「clusters→resource_pools」重命名迁移因 `executescript` 已预建空表而永不触发 → 迁移的集群数据 UI 上不显示。**新装环境拓扑功能是坏的**。

### 3. Agent 安全防线可整体绕过（全部实测）

- `mysql -e` / `sqlplus / as sysdba` / `disql -e` 在命令白名单内，`validate_command` 不校验 `-e` 里的 SQL → `execute_command` 可执行任意写 SQL（`mysql -e "DROP TABLE t"` 实测通过）
- `DE/**/LETE` 注释拆分绕过 SQL 黑名单与 sqlparse DML 检测（实测通过，DB 词法会剥离注释后执行）
- READONLY 级别不约束命令工具：`srvctl start/stop`、`lsnrctl stop` 在只读级别实测通过，与系统提示"所有操作必须只读"矛盾
- 参数校验是子串黑名单，遗漏 `;`、换行、反引号、`$()` → `crsctl check crs\nwhoami` 实测通过
- SSH/DB 凭据明文入库（`password_encrypted`/`private_key_encrypted` 列名带 encrypted 但内容是明文，代码里还有 `# TODO: AES加密`）
- SSE 全链路无鉴权，`POST /api/agent/run` 可远程触发

> 当前 `agent/tools.py` 是桩（返回占位文本），故这些绕过是"潜伏"的；但一旦接入真实执行即全部生效。**该模块当前不可在生产接入真实执行**。

### 4. 全站无鉴权 + `0.0.0.0` + `debug=True` + 硬编码 SECRET_KEY

`app.run(host='0.0.0.0', port=5000, debug=True)`，无任何 `before_request`/session 校验 → 局域网任何人可直接利用上述全部漏洞；`debug=True` 开启 Werkzeug 交互式调试器（远程 RCE 向量）。`SECRET_KEY` 缺省为固定字符串。

### 5. LLM API Key 明文返回

`routes/config.py:50,67` `GET /api/config/llm` 完整返回明文 `api_key`（同文件 98 行 `get_llm_models` 却正确 `pop` 掉了）。可盗刷第三方 LLM 计费。

### 6. 前端存储型 XSS

**共同根因：`escapeHtml` 用 `textContent` 序列化不转义引号；`escapeJs` 转义成 `&#x27;` 会被浏览器 HTML 实体解码还原成 `'` → inline onclick 拼接全部失效**。已确认的可触发点：

- `kg.js:196-254` 图谱详情（描述/别名/关系/chunk 文本/`onclick` 实体名）未转义
- `topology.js:122,205,229,361` inline onclick 服务器名 → `x');alert(1);//` 生效
- `knowledge.js:121-123`、`manuals.js:22` 上传文件名注入 inline onclick
- `commands.js:37,245` 命令文本（含引号正常命令即坏）
- `kg.js:476-483,503-510` 实体/关系类型筛选项

**建议**：系统性改为 `data-*` 属性 + 事件委托；文本上下文用 `escapeHtml`，事件参数用 `encodeURIComponent`。

## 二、中危问题

- **向量模型不可用时 QA 不回退关键词**：`similarity_search` 返回 `[]` 不抛异常，关键词回退只在 `except` 分支 → 模型加载失败时**静默无上下文回答**，与 CLAUDE.md 声明的降级行为矛盾
- **kg/rules.py `\b` 词边界 Unicode 失配**（高影响正确性）：`\bMySQL\b` 在"使用MySQL数据库"中不匹配（汉字与字母都是 `\w`）→ 中文运维文档实体召回率大幅下降，实测确认
- **RAG 分块死配置**：config 的 `CHUNK_SIZE=500/OVERLAP=50` 无引用，实际生效 2000/100
- **迁移后知识文件内容为空**、被扫描跳过永不提取正文/向量
- **`_topology.txt` file_path 指向已删除的临时文件**，依赖 file_path 的功能失效
- **线程本地连接仅随请求 teardown 关闭**，APScheduler 后台线程连接泄漏
- **SSE 并发竞态**：qa.js 回车绕过禁用按钮开第二条流 → 回答截断；log-analysis.js 多任务流写共享 DOM
- **kg.js 重新定义 `showToast` 覆盖全站版本**，破坏错误提示样式
- **版本提取去重丢产品归属**（`MySQL 8.0 和 Oracle 8.0` 只出 MySQL）、Oracle 19c 版本号丢 `c`
- **`find_shortest_path` 只沿 outgoing**，反向路径查不到
- **图谱同文本共现生成 n×m 笛卡尔积关系**污染图谱
- **`_extract_knowledge_graph` 逐实体单事务**，大文件性能差
- **`extract_functions` 把 IN/OVER/CASE 等 SQL 关键字当函数**
- 上传无大小/数量限制、`load_workbook` 非 read_only（zip 炸弹 DoS 面）
- `db_types.py` 可注册 `db_id='.'` 破坏目录隔离
- `print()` 记录错误 + 静默吞异常多处

## 三、已验证为安全（正向结论）

- **SQL 层全部参数化**，未发现 SQL 注入（6 组一致确认）；动态 WHERE 用占位符、动态 SET 基于白名单键
- **图谱遍历无死循环**：visited 集合正确维护、BFS 深度有界
- **向量检索正确**：normalize 后点积即余弦、float32 BLOB 往返一致
- **`transaction` 上下文**异常回滚语义正确
- 命令执行（7z、拓扑导入）用参数数组，无 `shell=True`，未发现命令注入

## 四、建议修复顺序

1. 先堵任意文件读写：knowledge/manuals/log_analysis/topology/commands 五处路径净化（一次统一封装）
2. 关 debug、改 127.0.0.1、引入基础鉴权（全漏洞的放大器）
3. 删明文 api_key 返回
4. 统一 clusters/resource_pools schema 与迁移条件
5. Agent 安全加固：剥离注释后校验 SQL、命令参数逐 token 精确允许、凭据 AES-GCM 加密、SSE 鉴权限流 —— 未完成前不接真实执行
6. 前端改事件委托渲染，替换全部 inline onclick 拼接
7. 补 RAG 中文语境测试、关键词回退、资源限制

---

# 五、修复进展与剩余待办（2026-08-08 更新）

## 已完成修复

| 批次 | 内容 | 验证 |
|---|---|---|
| 修复顺序 #1#3#4 | 路径净化封装（safe_filename/safe_join）、删明文 api_key、统一 clusters/resource_pools | 单测通过 |
| 高危 A | Agent 防线：validate_sql 剥离注释+token 扫描、validate_command 级别/动作词/危险特征、移除 SQL 客户端、凭据 Fernet 加密 | 60/60 |
| 高危 C | 前端 XSS：escapeHtml 引号转义、escapeJsAttr、~64 处调用点替换 | 13/13 |
| RAG 正确性 | \b 边界、版本去重/19c、函数停用表、共现收敛、关键词回退、分块参数、双向路径、LIKE 转义等 | 11/11 + 12/12 |
| Agent 阶段1-4 | 见下方「Agent 模块改造」 | 60/60+26/26+15/15+5/5 |

## Agent 模块改造（阶段1-4，2026-08-08）

背景：Agent 原为"骨架完整、四肢未接"——5 个工具全是桩、ReAct 链断裂、知识图谱未接入、会话不落库、前端无样式。按用户目标（基于 RAG+知识图谱的自动化运维）分四阶段改造：

**阶段1 — 真实工具执行**
- 新增 `agent/connectors.py`：`load_db_conn`/`load_ssh_conn`（解密凭据）、`run_sql`（按 db_type 分发 pymysql/oracledb/psycopg2/dmPython）、`run_ssh_command`（paramiko）、`build_schema_query`/`build_metric_query`（只读查询生成）、`_safe_identifier`（表名白名单防注入）
- `agent/tools.py` 5 工具真实化 + `ToolContext` 注入 + `execute_tool(tool, params, ctx)`
- `agent/engine.py` `_execute_action` 构造 ToolContext、`_format_result` 适配真实返回
- deploy.md 补依赖：pymysql / oracledb / psycopg2-binary / paramiko（dmPython 可选）
- 顺带修 harness 误报：SHOW/EXPLAIN/DESCRIBE 语句跳过危险关键字扫描（`SHOW CREATE TABLE` 不再被拦）

**阶段2 — ReAct 链 + 知识图谱 + 阈值**
- 观察结果经 `add_message` 回流对话历史 → 链式推理；移除 `_is_complete` 启发式（靠模型停止调用工具自然结束）
- `_decide_action` 改平衡大括号 JSON 提取（容错代码围栏/嵌套/字符串内大括号）
- 知识图谱接入：`similarity_search` 补 `chunk_id` → `_retrieve_kg_context` 调 `enhance_qa_context` → `_build_system_prompt` 注入实体卡片/关系链（实现"RAG+图谱"双增强）
- 阈值对齐 0.55/0.60

**阶段3 — 状态持久化**
- `run_stream` 外包异常兜底（ERROR 状态）→ `_react_loop` 主循环
- 每步 `_persist_step` 写 `agent_steps`（action/observation/knowledge_refs JSON），结束 `_persist_session` 更新状态
- 前端 `renderAgentStep` 解析持久化 action JSON → 历史会话可回放

**阶段4 — 前端改版**
- 停止按钮（AbortController）、SSH/DB 连接配置弹窗（补齐"添加连接开发中"缺口）
- thinking/工具调用改折叠式 `<details>`；`renderAgentResult` 增强（表格/stdout/metrics/检索结果）
- **补整套 Agent 模块 CSS**（原聊天/连接/会话几乎零样式，为界面丑的根因）

> 注：Agent 高危 A 中「SSE 鉴权」因用户决定内网部署、暂缓加鉴权而未做；`agent/tools.py` 仍为桩，未接入真实执行（符合"未完成前不接真实执行"）。

## 剩余未处理项

### 高危
- **B. 全站无鉴权 + 0.0.0.0 监听 + debug=True + 硬编码 SECRET_KEY** —— 用户明确暂缓（内网轻量化定位），后续若上外网/多用户需补。`app.py:308`、`config.py:22`。

### Agent 模块（中危，接入真实执行前需处理）
- **ReAct 观察未回传模型**（`agent/engine.py:70,227`）：`conversation_history` 全程未追加 observation，思考-执行-观察链是断的
- **无请求级总超时**：max_steps=10 × 每步 LLM 120s，SSE 长连接可被并发滥用
- **工具输出无大小上限**（`agent/engine.py:301-375`）：stdout/metrics 直接灌入后续 LLM 上下文
- **异常细节经 SSE 外泄** + `_decide_action` 裸 `except: pass` 吞异常（`routes/agent.py`、`agent/engine.py:246`）
- **host/port 无校验**：工具接入后构成 SSRF 潜伏入口（`routes/agent_connections.py`）
- **连接测试端点返回假成功**（`routes/agent_connections.py:87-105,183-201`，TODO 桩）
- **"知识库支撑验证"不构成任何阻断**（`agent/engine.py:268-291`，误导性护栏）
- **凭据已加密但无解密消费方**：工具桩未实现，解密函数已就绪

### RAG/图谱（中低危）
- **`_extract_knowledge_graph` 实体/关系仍逐事务**：已做 chunk-id 批量查询，但 `save_entity`/`save_relationship` 仍是每实体一事务
- **LLM 提取链路死代码**（`kg/llm_extractor.py`）：CLAUDE.md 声称"可选"但从未接入
- **图谱逐实体单事务**、**`enhance_qa_context` 未按置信度排序** —— 已修复（RAG 批）

### 路由/功能（中低危）
- **上传无大小/数量限制** + `load_workbook` 非 read_only（zip 炸弹/超大文件 DoS）—— `utils/topology_import.py`、各上传接口，建议 `MAX_CONTENT_LENGTH` + 单文件上限
- **日志分析大文件全量读内存入库**、analyze 先拼全长再截断（`routes/log_analysis.py`）
- **topology 统计接口 `cluster`/`datacenter` 筛选参数被读但未生效**（`routes/topology.py:402-419`）
- **`delete_command` index 参数类型未校验**（字符串可打挂接口，`routes/commands.py:126`）
- **manuals 上传无扩展名白名单**（`routes/manuals.py:41`，纯点文件名已由 safe_filename 修复）
- **reindex 向量重建失败被吞但返回"完成"**（误报，`routes/knowledge.py:201-225`）
- **`get_doc_content` 白名单大小写不匹配**（`PROJECT.md` vs `project.md`）
- **download 接口存在性探测**（404 差异泄露文件是否存在）
- **拓扑导入细节**：示例行误判、按 host 全局去重会"移动"服务器、重导入不更新已有字段

### 前端（中低危）
- **SSE 并发竞态**：qa.js 回车绕过禁用按钮开第二条流（回答截断）；log-analysis.js 多任务流写共享 DOM
- **kg.js 顶层重新定义 `showToast` 覆盖全站版本**（错误提示样式失效）
- **api.js 对非 JSON 响应直接 `response.json()` 抛错**（丢失状态码）
- **键盘快捷键绕过功能开关**
- **`formatMarkdown` 代码块内换行被替换 `<br>`**（渲染 bug）
- **beforeunload 监听器累积**

### 环境/兼容
- **`routes/knowledge.py` 含 Python 3.12+ 多行嵌套 f-string**，本机默认 Python 3.9.7 无法启动；部署副本在 `D:\claude\db-tool`（start.bat），需确认其 Python ≥ 3.12
