# DBSV 版本更新记录

## 开发人：顾云波

> 📌 配套文档：
> - `README.md` — 项目概述、技术栈、功能模块
> - `version_update.md` — 版本更新记录
> - `code_desc.md` — 代码结构文档（函数/API 详细说明）
> - `tables_desc.md` — 数据库表结构
> - `deploy.md` — 部署指南

## 版本号规范（semver 约定）

> 自 2026-08-22 起执行，并同步完成一次**历史版本重编**：旧 2.x→1.x、3.x→2.0.x、4.x→2.1~2.5.x（原 4.4.3 即当前 2.5.3）。改造范围仅版本号文字，功能与日期不变；初始化 tarball 文件名仍沿用旧编号。

- **patch（如 2.5.x）**：仅修复 bug / 细节调整，不改行为语义。
- **minor（如 2.x）**：新增功能 / 非破坏性增强。
- **major（如 3.x）**：仅破坏性 / 架构级变更（数据库不兼容、模块级重构）。
- **铁律**：patch 计数到高位（≥10）时推进 minor（如 2.5.9 → 2.6.0），**绝不因位数不便而新起 major**（此前 3.0.22→4.0.0 即为此类误跳，现已于重编时折叠为 2.0.22→2.1.0）。

## v2.5.3（2026-08-21）

### Agent 智能化第一批 + 第二批

对应 glu 优化方案（quantum-forging-turing.md），第一批（已确认）与第二批均落地。

**技能生命周期**：
- P0-1 激活 Curator 淘汰：app.py 每日调度，`usage_count=0` 且超 30 天自动沉淀技能标 deprecated（只标不删）。
- P0-2 手动 SOP 沉淀设 `is_expert=1` + `priority=10`（`save_skill` 支持 is_expert）。
- P0-3 命中效果追踪：`agent_sessions` 加 `matched_skills`，会话按成功与否（completed/partial）落库；`/api/agent/skill-effect` 统计命中次数与成功率。

**鲁棒性与止损**：
- ① 工具临时错误重试：`_run_one_action` 对超时/连接类错误（`_is_transient_error`）重试 1 次，防抖动误判。
- ② 会话无进展止损：连续 3 步观察雷同或全空 → 主动建议换思路（`_obs_fingerprint` 归一化检测）。

**上下文与效率**：
- ⑤ 工具结果预处理：`_history_observation` 阈值降到 800，表格类结果结构化摘要。
- ⑥ 意图识别前置：简单事实查询短路到知识库直答（`_is_simple_fact_query`），省步数预算。
- P1-2 上下文压缩修复：截断阈值 120→300、摘要上限 2000，链式推理中间结论不丢失。
- P1-1 主动澄清：system prompt 增加"主动澄清原则"（诊断/变更缺对象先问一句）。

**知识库与审批闭环**：
- ③ 知识库反馈闭环：`kb_embeddings` 加 `weight`，检索按权重加权重排（`similarity_search`）；引用进结论的 chunk 加权并清矩阵缓存，越用越准。
- ④ 变更白名单自学习：`agent_plans` 加 `cmd_fingerprint`，批准时记录命令指纹（数字归一化）；`/api/agent/whitelist-candidates` + `/api/agent/whitelist`(POST) 供 DBA 查看/确认。**注**：`validate_command` 自动免审批降级未做（与"变更必须审批"安全底线冲突，保留 DBA 确认）。
- P1-3 step 资产激活：`/api/agent/failure-patterns`（失败工具/命令聚合）、`/api/agent/quality-stats`（完成率/步数/死循环率）。

**探索性**：P2-2 诊断类结论按性能/故障子类型自适应结构；P2-3 skill 遵循度评估（日志观察）。P2-1 trigger_keywords 语义匹配因性能风险未启用（需向量缓存方案另评）。

### 智能运维前端体验（版本号不变）

- **执行范围可视化**：范围徽标改为可点击按钮，点击弹出浮层，按「池→节点→实例」分组平面展示当前会话已提交的范围对象（只读可视化，与徽标同口径读 `scope_json`）；树内勾选的节点/实例/整池行加背景高亮（只高亮不自动展开，保留默认折叠与筛选）。
- **渐变遮罩钉底**：遮罩从滚动容器改定位到非滚动上下文（`.agent-tab-pane::after` / `.qa-main::after`），对齐交互窗口位置，不随内容滚动；高度由 ResizeObserver 同步交互窗口动态高度（`--agent-input-h` / `--qa-input-h`），textarea 多行增高时遮罩自适应；z-index 低于悬浮交互窗口，永不遮挡输入框。

## v2.5.1（2026-08-21）

### 操作模式弹框 + 发送按钮优化 + 问答按钮修复

**操作模式选择**（agent）：
- 模式按钮改为上弹选择框（normal / plan，复用 skill-palette 样式），当前模式带 ✓；按钮展示当前模式（plan 显示「📄 plan」、normal 显示「✋ normal」）。
- 移除原切换按钮的 active 高亮黑框样式（点击后不消失）；模式按钮移至发送按钮左侧、紧贴（`.send-group` 包裹）。

**发送按钮优化**：
- 纸飞机 SVG 旋转 `-45°` 使机头朝向正上方，并加 margin 微调垂直居中；停止按钮改空心方块 SVG。

**修复**（qa）：知识问答发送/停止按钮 display 切换时，`_doStreamResponse` 的 finally 块未恢复发送按钮 —— 回答结束后发送按钮消失。已在 finally 补回 `display:flex`。

## v2.5.0（2026-08-20）

### 知识库分块策略优化：句子边界优先分块

**分块算法（rag/embedder.py chunk_text）**：
- 切块点从「段落边界」改为「句子边界优先 + 段落兜底」：段落累积超 500 时在超限范围内回溯最后一个句末标点（中文。！？；!?;，英文句点需后随空白），在句界切块（块末完整句、不加 overlap）；无句末标点（表格/代码/列表行）或句界位置 < chunk_size/2 时退回原字符边界切（保留 50 overlap）。
- 解决 86% 块末非句末标点的语义切断问题（hy3 向量索引核查报告结论）。新增 `_rfind_sentence_end` 辅助函数；二次切分同样句界优先，保证块长 ≤500。
- 已全量重建索引（向量 + 知识图谱，87 文件处理、85 文件向量化）。

**块质量实测（temp_scripts/diag_chunk_tokens.py）**：
- 块末非句末标点比例：86% → 40%（残余主要来自表格/代码/短行段落，无句末标点无法句界切，属预期）
- token 分布：最大 497，超 512 上限 0 块

**检索阈值重校准（temp_scripts/qa_similarity_sampling.py 30 问采样）**：
- 新 top-1 分布：min 0.769 / P20 0.803 / 中位 0.838
- 阈值：维持 0.75/0.80（满足 min≥0.75 且 P20≥0.80 判据，未动；routes/qa.py 与 agent/engine.py 两处注释已更新实测分布）

### 发送/停止按钮 SVG 图标化
- agent 发送按钮 `↑` → Feather `send` 纸飞机、qa 停止 `⏹` → Feather `square`，内联 SVG（`stroke="currentColor"` 双主题自动适配），跨平台字形一致；按钮改方形适配纯图标；补 `prefers-reduced-motion` 无障碍降级。

### 专家功能 = skill 轻量扩展
- 内置技能补 PostgreSQL 性能诊断 / Redis 状态检查（含关键词映射 postgres/pg/redis）；`agent_skills` 表加 `is_expert` 列（专家技能优先匹配，前端技能栏 ⚡ 标记）。
- 激活死字段 `required_tools`：技能声明的工具白名单注入「工具使用约束」prompt；激活 `knowledge_tags`：技能标签对检索结果重排序（含 tag 的块优先）。

### Plan 模式（先整体方案再执行）
- 会话级开关：输入框工具栏「📋 Plan」按钮（active 高亮 + 输入外框变色），`/api/agent/run` 传 `plan_mode`。
- 引擎 plan 模式：system prompt 引导先输出整体方案（探查/变更两步、desc+phase、变更需逐项审批），复用现有 plan 审批流确认后执行；`_execute_plan_operations` 扩展只读探查工具（get_schema_info/get_performance_metrics/retrieve_knowledge/retrieve_check/get_monitor_metrics 单次执行不 fan-out）。
- `agent_plans` 表加 `kind` 列（overall_plan / change_approval），`create_plan` 透传。

## v2.4.0（2026-08-19）

### 输入框悬浮化 + 模型选择 + 检索增强

**输入框悬浮化（agent + qa，VSCode Claude Code 样式）**：
- 输入框改为对话区底部悬浮居中（max-width 720px 左右留白），不顶到两侧；对话区底部 padding 留白 + absolute 渐淡 overlay（固定在滚动容器底部，内容滚入渐隐），最后一条消息不被遮挡、形成"内容沉入输入框下方"视觉。
- textarea 自适应增高（最多 8 行约 200px，超过滚动）。
- 输入时外框边缘橙色高亮（`input-frame:focus-within`，包住输入行 + 工具栏行整体）。
- skill chip 内嵌输入框最左侧；历史记忆由 checkbox 改 toggle 按钮（active 高亮态）。
- 审批槽悬浮输入框上方、宽度跟随输入框。
- **布局微调（2026-08-20）**：输入行与工具栏行合并为同一外框（`.input-frame`），中间以 1px 细灰线分隔；发送按钮改圆角矩形、移至工具栏行最右侧；橙色高亮由"仅输入框"改为"外框整体"。

**模型选择按钮化**：
- agent 新增会话级模型选择：输入框左下方「🤖 模型」按钮 + 上弹列表（复用 skill-palette 样式），`sendAgentQuestion` 携带 `model_id`（后端已支持）。
- qa 移除顶部 `#qa-model-select` 下拉框，改同款按钮 + 上弹列表；`sendQuestion`/`createNewConversation` 读 `qaSelectedModelId`。

**前端修复**：
- `escapeHtml` 删除 `'`→`&#39;` 多余转义（文本内容中单引号合法，二次转义会暴露 `&amp;#39;` 实体；双引号属性上下文转义保留）。

**后端检索增强**：
- 长期记忆召回阈值/上限配置化：`MEMORY_MIN_SIMILARITY=0.55`、`MEMORY_INJECT_TOP_K=6`（`db/database.py` `search_memory_semantic` 过滤弱相关记忆）。
- 知识库检索补相邻块：`get_chunk_neighbors` 拼接命中块前后相邻 chunk；chunk 注入截断放宽到 `KNOWLEDGE_CHUNK_INJECT_LIMIT=1500`（容纳"命中块 + 相邻块"整块编码），解决块内后半段丢失 + 跨块后续内容丢弃。

## v2.3.1（2026-08-19）

### Agent 范围交互与状态刷新修复

**操作范围栏加宽**：`.agent-sidebar` 260->320px（历史抽屉同宽），池/节点名加悬浮 title 提示，长名称不再无法辨认。

**会话级历史记忆开关**：`/api/agent/run` 新增 `disable_memory` 参数；会话输入区加「历史记忆」开关（默认开）。关闭后该会话不再召回跨会话长期记忆（环境上下文），完全独立。会话间对话历史本就不共享（每次 run 新建引擎）。

**范围徽标不刷新修复**：管理抽屉补配 SSH/DB 连接保存成功后追加 `refreshAgentScopeResolve()`，徽标立即更新（此前停留在页面加载时的"未配置"）。

**连接卡片去选中**：管理抽屉连接卡片不再可点选（纯管理展示），移除自动选中首个连接与 legacy 单连接会话静默回退；新会话强制要求左侧范围面板先勾选节点（无勾选 toast 提示）。历史 legacy 会话后端逻辑保留可继续执行。

## v2.3.0（2026-08-18）

### Agent 智能化 + 范围树交互修复

**结论空返回修复（多轮会话）**：
- 前端结论块改为会话视图缓存引用（`view.conclusionDiv`），多轮/多循环不再因固定 id 首匹配把本次结论串进旧块；新增 `agentLatestConclusionDiv` 统一取最新实时结论块（反馈/重新生成/历史回放同源）。
- 流式解析兼容推理模型：`call_llm_stream` 同时累积 `reasoning_content`（`content` 为空时），思考/结论不再整段丢失（`utils/__init__.py`）。
- LLM 流式+非流式双失败时产出 `executing_warning`，不再静默空转；流中断残留的空结论块自动填占位。

**变更操作执行后强制验证（长链路日志检查）**：
- 系统提示新增「变更操作执行后必须验证」规则（覆盖"答案即止"）：启停查状态、有日志的操作 tail 确认无 ERROR、验证输出写入结论。
- 引擎加 `_pending_verification` 拦截：批准计划执行后，模型若想直接收敛会被拦一次，注入验证引导强制先做只读验证。
- `execute_command` 返回体扩展 `exit_code/timed_out/truncated`；SSH 超时不再当纯错误（分块读取保留部分输出 + `timed_out` 标记 + "请用 ps/tail 复查"内嵌引导）；计划操作超时默认 30→300s。
- 输出截断改「头+尾」保留（`_truncate_head_tail`），成功/失败标记不再被切；批量结果摘要保留尾部 200 字符；失败节点 observation 追加排查引导。

**上下文与鲁棒性**：
- 大结果不进 history：新增 `_history_observation`（头尾各半 1500 字符摘要），全量仅经 SSE 展示；`AGENT_MAX_HISTORY_CHARS` 12000→20000。
- 工具调用 JSON 解析失败回喂纠正一次（`_looks_like_tool_json` 检测）；代码围栏剥离改两步删除，多分段 JSON 不再丢后续调用。
- 并行工具异常兜底（`_run_one_action` try/except）；死循环指纹归一化为「工具名+参数键集合」。
- 主循环墙钟超时（`AGENT_MAX_WALL_CLOCK_SECONDS` 默认 300s，超时优雅收敛给结论）；思考/结论显式 `max_tokens=4096`。

**操作范围树交互修复**（`static/js/agent.js` + `static/css/style.css` + `templates/index.html`）：
- 修复根因：`.scope-panel > * { flex-shrink: 0 }`（与 `.agent-chat` 同款防线），多节点池展开不再挤扁其它树、面板出现滚动条。
- 折叠初始化判据改一次性标志：全部展开后勾选不再塌回折叠态。
- 新增节点搜索过滤（池/服务器/实例/端口三层剪枝，命中自动展开 + 匹配计数）；全部展开/折叠按钮；折叠状态 localStorage 持久化。
- 重渲染保留滚动位置与焦点（勾选/折叠后不跳回顶部）。

## v2.2.0（2026-08-17）

### 智能运维 Agent 模块体验优化

- **布局修复**：模块高度对齐（`calc(100vh - 220px)`）消除右侧恒滚动条；历史抽屉覆盖操作范围栏（同宽 260px 打开不位移）；管理抽屉加宽至 380px；抽屉收起完全隐藏（`.agent-layout` 裁剪）。
- **操作范围树**：默认全部折叠、节点分两行展示（名称 + meta）、实例层级引导线、细滚动条。
- **Markdown 渲染升级**：引入 marked.js + highlight.js（本地 `static/vendor/`，离线可用），全站 7 模块（问答/Agent/SQL工具/日志分析/手册/项目介绍）渲染增强——支持嵌套列表/任务列表/代码高亮，亮暗主题联动 hljs 样式表。**安全**：先 `escapeHtml` 再 marked 解析，保留注入防护（marked 默认放行 raw HTML）。
- **功能增强**：多行输入框（回车发送 / Shift+回车换行，自动增高上限 120px）、消息复制按钮（结论/观察/工具参数，hover 显示）、会话标题即时命名（后端命名 + 前端兜底）、工具结果小表格（≤10 行）默认展开、批量结果「展开/折叠全部」、输入历史 ↑↓ 导航、结论「重新生成」（限 1 次，带上下文提示）。
- **修复**：kg.js 删除重复 `showToast` 定义（复用 utils 全局版，统一提示样式）；会话搜索输入防抖（150ms）。

## v2.1.1 (2026-08-17)

### 🐛 Agent 前端细节修复（实测反馈）

**范围面板**（`static/js/agent.js` + `static/css/style.css`）：树形列表改为面板内滚动（`flex:1 + overflow-y:auto`）；资源池/服务器加 ▾/▸ 折叠按钮，可树形展开/收起（折叠按钮与复选框分离，互不干扰）。

**抽屉定位**（`templates/index.html` + `static/css/style.css`）：`.agent-layout` 设 `position: relative`，历史/管理抽屉改为相对模块定位——历史抽屉从侧栏右侧滑出（不再贴屏幕左缘被侧栏遮挡）、管理抽屉关闭按钮可点（此前相对 body 定位，顶部按钮被全局头部遮挡）。抽屉内容包进 `.drawer-body`（`flex:1 + overflow-y:auto`）独立滚动，不再落到页面滚动条。

**管理抽屉**：技能/记忆删除按钮改为卡片右侧 × 关闭按钮（复用 `.session-delete` 样式，与历史会话一致）。

**技能栏改为 `/` 召唤**：移除输入框上方常驻技能栏；输入以 `/` 开头时输入框上方弹出可上下滚动的技能栏（按会话 db_type 过滤、支持 `/关键字` 过滤），选中后清空前缀并显示「⚡ 技能名 ✕」已选标签（可取消）；输入提示改为「💡 / 调用技能与指令」。

## v2.1.0 (2026-08-16)

### 🎯 Agent 会话范围化 + 多节点批量执行 + 前端重构

> 里程碑版本：Agent 从「一次会话 = 单一 SSH/DB 连接」升级为「一次会话 = 拓扑资源池内的多节点范围」，
> 支持跨节点批量查询与批量变更。方案经高能力模型批判性重审（v4-pro），承重设计已并入实现。

**范围模型**（`db/database.py` + `agent/scope.py` + `routes/agent.py`）：
- `agent_sessions` 新增 `scope_type`/`scope_json`（targets: `[{type:'ssh'|'db', topo_id, conn_id, name}]`），`set_session_scope` 写范围并同步 `ssh_connection_id`/`db_connection_id` 旧列（兼容所有只读单连接的旧消费方）；既有会话自动回填为 legacy 单连接范围（`WHERE scope_json IS NULL` 幂等守卫）。
- `agent_ssh_connections`/`agent_db_connections` 新增 `topo_server_id`/`topo_instance_id` 钉定列；`topo_instances` 补 `database`/`sid`/`service_name`（同机同端口多库解析消歧）。
- 新增 `agent/scope.py`：拓扑节点 → 连接的解析（钉定优先 → 主机[+端口+db_type+库]自动匹配 → ambiguous 置多匹配，绝不随意取）；`POST /api/agent/scope/resolve` 供前端渲染 ✅/⚠️ + 混型警示。
- 会话 API：`create_session` 接受 `scope` payload；`GET/PUT /api/agent/sessions/<id>/scope`（running 时 PUT 409）。

**批量执行（引擎 fan-out，`agent/tools.py` + `agent/engine.py`）**：
- 模型**只写一次**命令/SQL，引擎并发（上限 4）fan-out 到范围内该类型已解析节点：`query_database`/`get_schema_info`/`get_performance_metrics` 只跑 db 节点、`execute_command` 只跑 ssh 节点，按 conn_id 去重，节点间感知停止（M5）。
- **逐节点用该节点 db_type 重新过 Harness 校验**（H1）；`get_schema_info`/`get_performance_metrics` 按各节点 db_type 构造 SQL；混型范围 prompt 注入逐节点 db_type（H2）。
- 占位符替换 `{host}/{port}/{instance}/{node}`（值仅来自拓扑白名单，**替换后重新校验**，H5）。
- 批量结果结构化经 `executing_end.result`（`batch_result`）传前端渲染表格；`observing` 只带紧凑摘要（防历史爆炸）。

**批量变更 + 范围扩展审批（H4/M1）**：
- 计划 op 支持可选 `targets`，`_execute_plan_operations` 逐 op 按 targets fan-out、逐节点 `plan_operation_result`（含 node+status）、**continue-on-error 收集**；失败节点记入 `_plan_failed_nodes`，结论列出失败节点，前端给「仅重试失败节点」入口。
- **范围扩展审批**：工具 `target` 指向范围外节点 → 自动生成 `kind:'scope'` 审批计划（DBA 批准后扩展范围并持久化，原动作本回合重投续跑，M1）；目标未配置连接则不弹审批、发 `executing_warning` 指引一键补配。
- 手动技能：`run` 携带 `skill_name`，引擎注入**完整** `prompt_template`（绕开自动匹配 200 字截断；同名自动匹配去重，M7）。

**前端重构（`templates/index.html` + `static/js/agent.js` + `static/css/style.css`）**：
- **范围面板**取代连接列表成为主侧栏：拓扑资源池树（池→服务器→实例）复选框，节点显示连接状态 ✅/⚠️，未配置一键补配（host/端口/db_type 预填）；勾选 localStorage 持久化，勾选结果 = 新会话默认范围（无勾选回退 legacy 单连接）。
- **收纳**：会话历史收进「🗂 历史」抽屉，连接/技能/记忆收进「⚙️ 管理」抽屉（子标签），主视图只留范围面板 + 会话区。
- **范围徽标**：工具栏/页签/会话列表显示「范围: N 节点 · M 实例」。
- **技能 chips**：输入框上方按会话 db_type 过滤，选中注入完整操作指南。
- **批量结果表格**：多节点结果渲染为逐节点卡片（错误在前、成功折叠、可展开全部）。
- 审批条：范围会话显示「将应用到 N 节点」；`kind:'scope'` 范围扩展计划用专用卡；`scope_extended` 事件更新徽标。

**修复（H3）**：`get_topology_text()` 四处键名错位（`topo_clusters`/`topo_servers`/`topo_instances`/`topo_tenants` → `clusters`/`servers`/`instances`/`tenants`），拓扑→知识库同步此前永远为空。

**安全边界不变**：批量只扩大「作用域」，不扩大「权限」——DML/DCL 硬拒、注入硬拒、命令白名单分级、变更审批全部保留；fan-out 逐节点校验。

## v2.0.22 (2026-08-16)

### 📝 结论按需生成 + 审批框自适应高度

**结论按需生成**（`agent/engine.py` + `static/js/agent.js`）：
- **未执行任何工具时**（Agent 直接回答/向你征求意见）：思考即对用户的回应，**不再发起独立结论调用**（根治「思考里问了问题、分析结论却空白」）——发 `final_thinking` 事件，前端把最后思考块展开为可见的「Agent 回复」。
- **执行过诊断/变更**：仍生成「分析结论」汇总结果（工具/变更才有汇总价值）。
- 顺带加固：结论为空（LLM 失败/空响应）时用最近一次观察兜底，保证结论永不为空；`_stream_llm` 失败时打服务器日志 `[Agent] LLM …失败`，便于区分「LLM 失败」与「前端未渲染」。

**审批框自适应高度**（`static/css/style.css`）：`.agent-approval-slot` 移除 `max-height:45%` 与内部滚动，多条命令全量可见、无需上下滚动。

## v2.0.21 (2026-08-16)

### 📑 Agent 会话页签化 + 审批即时收起

**页签模式**（`templates/index.html` + `static/js/agent.js` + `static/css/style.css`）：
- **每会话一个页签**，页签内嵌在标题栏那一行（连接状态 | 页签 | 操作按钮，复用顶部空间、不挤占对话窗口）。
- 侧栏会话历史保留：点击记录打开页签；「新会话」自动打开页签；页签可增删、来回切换。
- **各会话视图完全隔离**：SSE 流事件按所属会话 id 路由到该会话的 pane（chat / 审批槽 / 输入框独立），运行中切换会话不再串扰、切回完整可见（含审批面板/执行记录）——修复「切换会话后历史展示错乱」与「审批流中切走丢审批交互」。
- running 状态按会话独立（每会话独立 AbortController），多会话可并发执行；关闭运行中的页签会先停止该会话。

**审批即时收起**：
- 批准后审批框**即刻消失、返回输入框**；已批准的计划以 chat 记录「✅ 已批准，开始执行」呈现（含全量命令 + 风险徽标），执行结果逐项回填到该记录。

## v2.0.20 (2026-08-15)

### 🧾 审批交互改 Claude Code 形态 + 停止真停 + 会话命名 + 滚动

**审批交互（`static/js/agent.js` + `templates/index.html` + `static/css/style.css`）**：
- 审批条从对话流移入**贴近输入框的固定审批槽**（`#agent-approval-slot`），不随对话滚动。
- **审批框与主输入框互斥**：审批进行中隐藏输入框与提示行（Claude Code 等待权限决策形态），审批解决、会话收尾后恢复。
- **选项竖向排列**：【✅ 批准】【❌ 拒绝】【✏️ 修改并重新提供方案】——第三个展开输入框，DBA 输入希望修改的地方后提交，Agent 据此**重新输出操作计划**再走审批。
- 保留 ② 的全量命令展开 + 危险徽标；审批条头部展示 **🎯 目标主机**（SSH/DB 连接名）留痕。

**后端（`routes/agent.py` + `agent/engine.py`）**：
- `POST /api/agent/approve` 支持 `action='revise'`（要求附修改内容）→ 计划状态 `revised` → 引擎把修改要求回流给模型重新出计划（`approval_revised` 事件）。
- 新增 `POST /api/agent/sessions/<id>/stop`：进程内取消标志，引擎 ReAct 循环在下一轮收敛、**跳过结论、会话置 `cancelled`**，SSE 发 `cancelled` 事件——停止按钮从「只断前端流」变为「真停」。
- `run` 时默认「新会话」标题用首问句自动命名（≤24 字），会话列表可区分。

**滚动**：对话区自动滚动改为**距底 <60px 才跟随**，用户上翻看历史时不再被拉回底部。

## v2.0.19 (2026-08-15)

### ✂️ Agent 简洁优先：简单任务不再想得多

**根因**：system prompt 只教 ReAct 多步思考，没有「简单任务直接答/单工具即止」规则；`AGENT_MAX_STEPS` 默认 10 助长连续工具调用；结论模板对单次查询也套「诊断结论+建议」；前端「思考中」默认展开放大感知。

**改动**（`agent/engine.py` + `config.py` + `static/js/agent.js`）：
- system prompt 核心原则新增 **0. 简洁优先**：单条查询/直接回答/问候 → 一句话答或一次工具后立即结束，禁止多步思考、检索知识库、章节标题、置信度、建议清单。
- ReAct 工作模式新增 **5. 答案即止**：拿到足够信息立即停止给结论，单条查询能解决就不多步。
- 结论模板（执行过诊断）加收口：只执行了单次查询且答案在结果中 → 一两句话回答，不展开分析/建议。
- `AGENT_MAX_STEPS` 默认 10 → 6（步数预算后盾，`DB_TOOL_AGENT_MAX_STEPS` 可覆盖）。
- 前端「思考中」块**默认折叠**（点击展开），结论块仍默认可见。

## v2.0.18 (2026-08-15)

### 🛡️ 审批覆盖：DBA 已批准的变更操作真正可执行

**根因**：审批后执行阶段（`_execute_plan_operations`）仍用只读三态分类器二次校验，把「这是变更」误当「这是危险」——`rm`（T1 硬拒）、`su -c 'disql -e "ALTER SYSTEM SET ..."'`（受控 su 只读门拒）等在 DBA 批准后仍被拦下；LLM 判读器对「任何写入」一律 `allow=false`，使「reject → 降级审批（DBA 决定）」的逃生通道失效。

**改动**（`agent/harness.py` + `agent/engine.py`）：
- 新增 `Harness.validate_plan_operation`：审批后计划执行二次校验改为**计划级语义**——DBA 已批准即授权。只读链 / 已知变更命令放行；策略级拒绝（T1/su 门控/白名单外，无注入向量）放行；**注入/扩展向量**（命令链 `; && ||`、子 shell `` ` ``/`$()`/`${}`、后台 `&`、su 内层命令链、`find -exec/-delete`、`awk system(`、路径穿越 `..`）保持硬拒，但保留「LLM 判读 allow → 放行」出口。
- 重构 `Harness.classify_command` 的 reject 分支：
  - 无注入向量的**策略级拒绝** → 直接 `approval`（DBA 决定，不再被判读器否决）；
  - **注入向量** → 判读 allow → `approval`；判读拒绝/不可用 → `reject`（保留第二意见）。
- 重定向 `>`/`<` 不再视为注入向量（是已批准命令的可见组成部分，否则误杀 `mysqldump > backup.sql`、`mysql < change.sql` 等备份/导入）。
- `query_database` 工具的 DML/DCL（DROP/UPDATE/INSERT/GRANT/CREATE）仍硬拒——结构性安全边界，不在本通道放开。

### 🧾 审批条全量展开 + 危险标注

- 新增 `Harness.estimate_command_risk`：按命令真实危险性估算 `high/medium/low`（T1/su/注入 → high，普通变更 → medium，只读 → low），审批标注用，不参与放行决策。
- 引擎审批前**重算每个 op 的 risk**（不信任模型自填），直接命令降级审批也用真实风险。
- 前端审批条**全量展开所有待批命令、不可折叠**（DBA 决定前必须看到每条命令）；摘要区显示最高风险徽标（⚠️ 高风险/⚡ 中风险/低风险），每条命令旁有 risk 徽标。
- 行为基准 `temp_scripts/bench_command_gate.py` 随语义更新，并新增 `validate_plan_operation` / `estimate_command_risk` 矩阵（109 项全绿）。

## v2.0.17 (2026-08-15)

### 🎛️ 会话删除按钮统一 × 样式
- Agent 会话删除按钮改为与知识问答模块一致的红色 ×（悬停会话项显示、hover 红底）。

### 🤖 变更类操作执行原则强化
- 系统提示词调整：**用户明确要求变更（重启/启停/改参）时，直接进入计划审批流程**——不再拒绝、不要求先诊断、不复述风险与置信度，风险写进计划 risk 字段由 DBA 审批把关。
- **目标对象推断**：优先用当前会话的数据库/SSH 连接指向的实例，或会话历史/长期记忆中的明确实例；确实无法确定时只问一个简短问题（如"重启哪个实例？"），得到答复后立即输出计划，不再向用户索要主机IP/端口。
- 知识库优先/禁止编造/置信度原则仅约束分析类回答，不再卡变更计划（正确性由 DBA 审批把关）。
- **结论收敛**：最终结论按执行情况分三档——变更操作简洁、未执行任何工具（仅澄清/等补充信息）极简收尾（不再套四段式诊断报告）、执行过诊断的分析结论收敛篇幅（禁止泛泛建议/置信度长篇）。

## v2.0.16 (2026-08-15)

### 🎛️ Agent 前端：会话管理与内联审批

**会话管理**：
- **新会话按钮**：改为强制新建（不复用当前会话），点击后清空对话区回到欢迎页并选中新会话——修复原来已有会话时点击"新会话"无响应的问题。
- **会话删除**：会话历史每项悬停显示 🗑 删除按钮（带确认）；删除当前会话时清空对话区回欢迎页；后端删除时级联清理该会话的 `agent_steps` 与 `agent_plans`。

**审批交互（贴近 Claude Code 内联权限提示）**：
- 审批默认只展示标题 + 影响范围 + 操作数，操作明细折叠在「详情 ▾」里，视觉更紧凑、不再是大卡片。
- 批准后**自动展开详情**，逐项操作结果（成功/失败/错误）直接可见。

## v2.0.15 (2026-08-15)

### 🛡️ 引号感知元字符检查 + 受控 su 支持二次 `-c` SQL 与内层只读管道

**引号感知元字符检查**（`_strip_quoted`）：命令分隔符/管道/重定向只在**引号外**检测——引号内是数据而非 shell 元字符。修复两类误拒：
- `su - dmdba -c 'disql' -c "SELECT ...;"` —— SQL 末尾分号在引号内，不再误判注入；
- `su - dmdba -c 'cat dm.ini | grep -E "^PORT_NUM|^DB_NAME"'` —— grep 正则里的 `|` 在引号内，不再误判管道。

**受控 su 扩展**：
- 支持 **二次 `-c` 传 SQL**（`su -c 'disql 连接串' -c "SQL;"`，DM disql 命令串写法）；
- 支持 **内层只读管道**（`su -c 'cat x | grep y'`，内层整体走只读链校验）；
- `_extract_sql` 增加 SQL 关键字兜底（`-e/--execute/<<<` 之外的 `-c "SELECT..."` 也能识别）。

**绕过封堵**（对抗用例验证）：`su -c 'cat /etc/passwd | rm -rf /'`（内层管道含危险命令）、`su -c 'echo "SELECT 1" > /tmp/x'`（内层写文件）、`su -c 'disql -e "SELECT 1"; rm -rf /'`（内层分隔符）一律拒绝。

## v2.0.14 (2026-08-15)

### 🛡️ 受控 su + SQL 客户端只读门 + 移除知识库支撑噪音

**受控 `su`（DM/Oracle 需 `su - dmdba` 跑 disql 的真实场景）**：
- `su` 从硬拒绝改为**受控门控**：仅放行 `su [-lm] <非root用户> -c '<只读命令>'`——目标用户非 root（`su - root` 仍拒绝）、内层命令只读、外层仅允许 `/dev/null` 重定向与 `<<< 'SQL'` heredoc。
- **SQL 客户端只读门**：`disql/mysql/sqlplus/psql/gsql` 等命令（含 `su -c` 内层）内嵌 SQL（`-e/--execute` 或 `<<<` heredoc，支持 DM 风格 `''` 转义引号）通过 `validate_sql` 只读校验才放行，写 SQL（DROP/UPDATE 等）走审批。
- **注入绕过防护**：`su -c 'disql -e "SELECT 1"; rm -rf /'`、`su ... <<< 'SELECT 1'; rm ...`、heredoc 写 SQL 一律拒绝；`sudo` 保持硬拒绝。
- 已知边界：嵌套引号过于复杂的命令（模型输出的残缺引号）无法静态提取 SQL 时，静态判拒后交 LLM 审查（放行则审批）。

**移除「缺乏知识库支撑」噪音警告**：`_verify_knowledge_support` 启发式对 OS 级/诊断命令几乎必然误报（命令首词不在检索知识块就告警），噪音大于价值，已移除。

## v2.0.13 (2026-08-14)

### 🛡️ 命令安全校验重构：参数级甄别 + 融合判定矩阵（脚本 + LLM 双意见）

**静态命令目录分级**（替代原扁平白名单）：
- **T1 硬拒绝**：不可逆破坏（rm/dd/mkfs.*/mkfifo/mknod/truncate/unlink）、磁盘分区（fdisk/parted/LVM 等）、系统关停（shutdown/reboot/init 等）、代码执行与提权外联（sh/bash/python/perl/gcc/nc/wget/curl/sudo/su/scp/rsync 等）。
- **T2 纯只读**：ps/grep/cat/ls/top/ss/df/du/lsof 等（参数视为数据，仅路径穿越检查）。
- **T3 参数门控**：按参数甄别只读/变更/硬拒——sed（无 `-i` 只读，`-i` 审批）、find（`-delete/-exec` 硬拒）、tar/gzip/unzip（`-t/-l/-c` 列出/解压到 stdout 只读，其余审批）、systemctl/service（status/show 只读，start/stop 审批）、ip（show/裸子命令只读，add/del/set 审批）、sysctl/dmesg（`-w`/`-c` 变更，其余只读）、kill 族（审批）。
- **变更写操作**：cp/mv/mkdir/chmod 及包管理命令一律审批。

**融合判定矩阵**：脚本判 `safe` → 直接执行（不调 LLM）；脚本判 `approval`（变更）→ 审批；脚本判 `reject`/`unknown` → 发起一次独立 LLM 审查（temperature=0、短超时、TTL 缓存）：
- 脚本拒绝 + LLM 拒绝 → 拒绝；脚本拒绝 + LLM 放行 → **审批**（DBA 决策，避免安全命令被脚本误拒）
- 未知 + LLM 只读 → 执行；未知 + LLM 危险 → 拒绝；未知 + 无法判断 → 审批

**通用语义收紧**：路径穿越检查改为"像路径才查"（`/`/`.`/`~` 开头或含 `/`），避免 `grep -E 'a..b'` 正则误伤；`$(date +%Y%m)` 只读命令替换、引号感知管道切分、`/dev/null` 重定向保留。
- LLM 审查钩子在 Harness 内部可插拔（默认关闭=纯静态离线可用），引擎与工具双重校验共用同一目标与缓存。
- 配置：`COMMAND_LLM_JUDGE`（env `DB_TOOL_LLM_COMMAND_JUDGE`）、`COMMAND_JUDGE_TIMEOUT`、`COMMAND_JUDGE_CACHE_TTL`。

## v2.0.12 (2026-08-14)

### 🛡️ 命令校验：只读诊断命令链放行

- **纯只读诊断命令链**：`ps -ef | grep x`、`which dmserver 2>/dev/null; find / -name dmserver | head`、`cat a 2>/dev/null || cat b` 等由只读诊断命令通过 `;`/`&&`/`||`/`|` 分隔、可带 `/dev/null` 重定向的命令链，直接执行免审批。
- 诊断命令白名单补充 `which`/`find`/`echo`。
- **安全兜底**：`find` 破坏性参数（`-delete/-exec/-ok/-execdir/-okdir`）拦截；危险命令名（rm/dd/mkfs/sh/bash/sudo/su/wget/curl/nc/python/perl）硬拒绝；重定向到非 `/dev/null`、背景执行、命令替换、控制字符仍拒绝；非只读命令用管道拒绝。
- 三态分类：`safe`（只读诊断链/白名单）/ `approval`（变更命令 dminit/dmserver 等、blocked 动作 start/stop、非注入未知命令）/ `reject`（注入特征、危险命令、破坏性参数）。

### ⚡ Agent 输出流式化 + 表格 Markdown 渲染

- **流式输出**：`_think`/`_conclude` 改用 `call_llm_stream`，思考/结论逐 token 输出（失败自动回退非流式），与知识问答模块体验一致。
- **Markdown 渲染**：思考内容、观察结果、工具结果表格统一走 `formatMarkdown`（md-table），不再显示原始管道文本；流式逐 token 重渲染 + 打字光标。

## v2.0.11 (2026-08-13)

### 🏷️ 表名模块前缀标准化（全量重命名）

- 15 张无前缀表统一加模块前缀：`topo_`（集群拓扑 resource_pools/clusters/servers/instances/tenants/instance_relations）、`kb_`（知识库 knowledge_files/favorites/embeddings）、`sys_`（config/db_types/feature_config）、`audit_`（operation_logs）。
- **迁移**：init_db 幂等 `ALTER TABLE RENAME`（旧表存在且新表不存在才改名，先于建表脚本执行避免新旧并存冲突），自动更新 FK 引用；旧索引名 DROP 后按新名重建。新库直接按新名建表。
- **代码**：9 个 py 文件全部 SQL 引用改新名（db/database.py、routes/topology.py、utils/topology_import.py、db/kg_database.py、routes/dashboard.py、routes/qa.py、routes/knowledge.py、rag/embedder.py、db/migration.py）；**API 响应字段名不变**（前端零改动）；Python 函数/模块名不变。
- **清理**：移除遗留空表 `nodes`/`node_connections`（旧版拓扑遗留，无代码引用）。
- 文档：tables_desc.md / code_desc.md 表名与索引名同步。

## v2.0.10 (2026-08-12)

### 🧾 运维操作两分法 + 变更类审批闭环

**运维操作统一为两类**：
- **查询类**：从指定节点/数据库获取信息（只读，现有 ReAct 行为不变）。
- **变更类**：修改参数/配置/执行变更命令，走通用审批流程，可迭代自愈：
  `确认操作范围 → 创建操作计划 → DBA 审批 → 引擎执行 → 遇问题 → agent 自分析自查询（只读）→ 追加新计划 → 再审批 → 再执行 → …直至完成`

- **操作计划**：模型输出 `{"type":"plan","plan":{title, scope, operations[{tool, parameters, impact, risk}], rollback}}`，引擎持久化到新增 `agent_plans` 表（status: pending/approved/rejected/expired）并发 `approval_required` SSE 事件暂停等待审批（超时 `AGENT_PLAN_TIMEOUT_MINUTES` 默认 15 分钟置 expired）。
- **引擎按计划确定性执行**：审批通过后引擎逐项执行计划内已批准的 SQL/命令（会话现有连接），流式返回 `plan_operation_result`；**遇错即停**，报错交给模型自分析后追加新计划继续，直至任务完成。
- **安全模型**：模型工具永远只读（Harness 拦截写调用）；写操作唯一通道 = 计划 → DBA 审批 → 引擎执行，无需提升操作级别。
- **变更白名单**：`Harness.validate_change_sql` 仅放行参数/配置变更（ALTER SYSTEM SET / SET GLOBAL / ALTER SESSION SET / ALTER DATABASE ... SET），拦截 DROP/UPDATE/INSERT/GRANT 等；`validate_change_command` 仅放行 COMMAND_POLICY 内需 MAINTENANCE 的变更动作（srvctl start/stop 等），杜绝只读命令冒充变更。
- **审批接口**：`POST /api/agent/approve`（approve/reject + 原因）。
- **前端**：审批面板展示计划标题/影响范围/**临时操作项列表**（tool+SQL+影响+风险）+ 批准/拒绝按钮，引擎执行时逐项打勾/叉显示结果。

## v2.0.9 (2026-08-12)

### ⚡ Agent 强化（并行只读 + 上下文压缩 + 迭代预算）

- **并行只读工具**：一次思考可输出多个工具调用（JSON 数组），只读工具（query_database/get_schema_info/get_performance_metrics/get_monitor_metrics/retrieve_check/retrieve_knowledge）在线程池并行执行（最多 4 并发、单次最多 5 个），多指标诊断显著提速；`execute_command` 一律串行。每个动作仍独立过 Harness 安全校验。
- **上下文压缩**：对话历史超过 10 条时做头尾保护 + 中间摘要（中间消息各截断后拼成历史摘要，保留用户问题与最近 6 条逐字），控制超长 prompt。
- **迭代预算形式化**：`AGENT_MAX_STEPS`（默认 10，环境变量 `DB_TOOL_AGENT_MAX_STEPS`）注入 AgentState；连续相同动作指纹 ≥3 次判定死循环强制收敛；对话历史字符超 `AGENT_MAX_HISTORY_CHARS`（默认 12000）强制收敛到结论。

### 🧠 记忆完善（语义召回 + 事实校验 + DBA 反馈闭环）

- **记忆语义召回**：`agent_memory` 加 embedding 列，写入记忆时自动编码 fact 向量；召回时向量余弦 top-K，模型不可用自动回退关键词。对主机/实例/集群类记忆补知识图谱上下文（实体描述 + 邻居关系）注入环境上下文。
- **记忆写入事实校验**：写前与知识图谱实体/监控对象/本次知识库支撑交叉验证打分；有支撑按置信度落库，无任何支撑且无实体的结论跳过不写，防记忆污染。
- **DBA 反馈闭环**：结论后前端提供 👍/👎 + 纠正输入；up → 该会话技能置信度 +0.05、记忆 +0.1；down → 该会话技能 deprecated、记忆删除；纠正文本写入高置信度偏好记忆（source=dba_feedback）。只影响该会话自己沉淀的数据，不误伤其他技能/记忆。

### ⚡ RAG 检索性能优化

- **向量化检索**：`similarity_search` 从逐行 Python 循环改为 numpy 矩阵乘（`matrix @ query_emb` 一次 BLAS 运算）+ `argpartition` 取 top-k；新增 `db.get_embeddings_matrix` 一次加载全量向量为 `(N, dim)` 矩阵。
- **矩阵缓存**：`Embedder` 按 `(db_type, count, max_id)` 缓存检索矩阵，先用轻量 `get_embeddings_stats` 判失效（重建索引后 id 变化自动失效 + `rebuild_all` 显式清缓存）；命中后单次检索约 **7 倍提速**（59K 向量下 0.2s → 0.03s），矩阵加载首次一次性 ~0.5s 摊薄。
- **记忆语义检索同步向量化**：`search_memory_semantic` 改 `np.stack` + `argsort`。
- 检索路径纯 numpy/BLAS，与嵌入模型运行设备（CPU/GPU）无关，纯 CPU 部署同样生效。

### 📄 操作手册 → 生成技能

- **文档沉淀技能**：`SkillManager.crystallize_from_document(text, db_type, category)`——LLM 从手册提炼技能 JSON（步骤指南/触发词），LLM 不可用离线回退文档摘录模板；同样过 Curator 写时去重合并。
- **接口**：`POST /api/agent/skills/from-doc`（multipart 上传文件，或 `filename` 读取 `data/manuals/` 已有手册；可选 db_type/category）。
- **前端**：Agent 页「知识沉淀」技能库面板新增「📄 从手册生成」按钮；运维手册页每篇手册新增「📄 生成技能」入口。
- 关键词提取增强：错误码/SQL 表名/数据库参数名（snake_case）/症状词，支持离线回退技能的意图匹配。

## v2.0.8 (2026-08-12)

### 🧠 运维 Agent 学习闭环（技能自动沉淀 + 长期记忆）

**目标**：让 Agent "越用越好用"——成功诊断自动沉淀为可复用技能、跨会话记住环境事实（Observe → Execute → Reflect → Crystallize → Reuse）。

- **技能自动沉淀**：Agent 完成一次成功诊断（≥2 次工具调用且无执行出错）后，自动把诊断轨迹提炼为可复用技能写入 `agent_skills` 表（name/db_type/category/prompt_template/trigger_keywords），下次命中同类问题（按 trigger_keywords 意图匹配）优先加载指导诊断。技能生成优先走 LLM 提炼步骤指南，LLM 不可用时离线回退拼接轨迹模板，闭环不依赖模型可用性。
- **Curator 写时去重**：同 db_type+category 且触发词重叠 ≥50% 视为同技能合并更新（保留原名与使用计数），防止技能库漂移。
- **Curator 淘汰**：长期未使用（usage_count=0）且创建超 30 天的技能自动标记 deprecated，保留可查可删，防自污染。
- **长期记忆**：新增 `agent_memory` 表（跨会话环境事实：主机/实例已知问题、DBA 偏好）。诊断成功后自动写入本次结论（低置信度标记），DBA 也可通过接口显式记录（高置信度）；诊断开始时按关键词召回注入 system prompt 的「环境上下文」段。
- **SkillManager 双层技能池**：内置 6 技能 + DB 自动沉淀技能统一匹配/注入；自动技能全文注入（≤2 个），内置技能 200 字预览；注入时累加使用计数。
- **接口**：`POST/DELETE /api/agent/skills`（技能人工维护/停用/删除）、`GET/POST /api/agent/memory` 与 `DELETE /api/agent/memory/<id>`（记忆查看/显式记录/删除）。
- **数据层**：`agent_skills` 表迁移加列（trigger_keywords/source_session/confidence/usage_count/status），新增 `agent_memory` 表；迁移采用 try-SELECT/ALTER 模式，旧库平滑升级不破坏既有数据。

## v2.0.7 (2026-08-11)

### 🧩 运维检查项纳入知识图谱 + Agent 能力
- 新增知识图谱实体类型 **check_item**（检查项）：把部分运维检查知识导入图谱，实体属性含 category/db_type/functions/sql/commands/knowledge_text/thresholds。
- **关系**：`applies_to`（检查项→数据库产品，1071 条）+ `diagnoses`（检查项→错误码，73 条），支持"查某错误码相关的检查项"。
- **导入脚本** `tools/import_check_items.py`：批量建实体与关系，幂等可重跑；错误码追加进描述便于关键词检索。
- **Agent 新工具 `retrieve_check`**：按关键词/db_type/类别检索检查项，返回 SQL/命令/建议，指导诊断。已注册进工具表 + system prompt。
- 前端图谱视图：check_item 实体与 applies_to/diagnoses 关系颜色映射。

## v2.0.6 (2026-08-11)

### 📡 外部监控数据接入（蓝鲸）
- 新增 `mon_metric_data` 表（`db/database.py`）：外部监控平台指标落库（source/object_type/object_name/metric/value/unit/record_time），索引按 对象+指标+时间。
- 新增 `tools/monitor_blueking.py`：蓝鲸监控数据中间脚本（配置驱动，支持 mysql/pg），从蓝鲸库拉指标 → 规范化 → 写入 `mon_metric_data`。**当前为框架**，蓝鲸表结构待提供后填 `BlueKingMetrics.QUERIES`；连接凭据走环境变量，不硬编码。
- Agent 新增工具 `get_monitor_metrics`（`agent/tools.py`）：查询落库监控指标（CPU/内存/磁盘等），返回 `{columns, metrics}` 同构结构，引擎/前端零改动即可渲染；已加入 system prompt 工具声明。
- 数据用途：供运维 Agent 诊断引用 + 后续展示/健康评分。

### 🔧 工具
- `tools/monitor_blueking.py`：`--pull` 拉取落库、`--dry-run` 试跑、`--list-metrics` 列出查询
- `db/database.py` 新增 `save_mon_metrics` / `get_mon_metrics` / `get_mon_metric_names` / `get_mon_objects`

## v2.0.5 (2026-08-11)

### 🔍 RAG 分块调整：2000 → 500
- **根因**：嵌入模型 m3e-base 是 BERT（`max_position_embeddings=512`），2000 字符编码时被截断到前 ~512 token，块尾部对检索不可见，导致检索命中率下降、知识图谱实体-chunk 关联粒度粗糙。
- `config.py`：`CHUNK_SIZE=500`、`CHUNK_OVERLAP=50`（overlap 10%）。改动后已全量重建索引（向量 + 知识图谱）。
- 检索阈值随新块长重调（见下，旧值 0.55/0.60 保留备回滚）。

### ⚡ 索引重建性能优化
- `kg/rules.py`：词典提取器（产品/OS/参数/架构/概念/性能指标/硬件）正则**模块级预编译缓存**（`lru_cache`），消除每次按 chunk 提取时的 ~500 次重复编译——块 500 后按 chunk 调用次数约 ×4 的编译放大被抹平。
- `db/kg_database.py`：`save_entities_batch`/`save_relationships_batch` 改为单事务真批量（此前是逐条调 `save_entity`/`save_relationship`、各自 commit 的"假批量"死代码）；`rag/embedder.py` 的 `_extract_knowledge_graph` 改用批量保存。
- `routes/knowledge.py`：`/api/knowledge/reindex` 去掉双重 extract（路由一遍 + `rebuild_all` 内又一遍）。
- `static/js/knowledge.js`：重建超时 5 分钟 → 30 分钟（块 500 后重建更慢）。

### 🎯 检索阈值重调（分块 500 实测）
- 旧值（分块 2000 时代）：`MIN_SIMILARITY_THRESHOLD=0.55`、`MIN_KNOWLEDGE_COVERAGE=0.60`、置信度 0.85/0.55（`routes/qa.py` + `agent/engine.py`）
- 新值（分块 500 实测，30 个真实问答采样 top-1 分布 min 0.766 / P20 0.802 / 中位 0.839）：`MIN_SIMILARITY_THRESHOLD=0.75`、`MIN_KNOWLEDGE_COVERAGE=0.80`、置信度高线 0.85 不变

### 🔧 工具
- `temp_scripts/rebuild_index_full.py`：全量重建（含图谱提取 + 计时），支持按 db_type
- `temp_scripts/qa_similarity_sampling.py`：真实问答相似度分布采样（阈值重调依据）

## v2.0.4 (2026-08-09)

### 🌐 企业微信接入
- 新增 `wecom_qa_integration.md`：知识问答接口接入文档（非流式 `POST /api/qa/ask`，默认开启知识库增强 + 集群拓扑增强），企微后台可据此开发问答调用代码
- 问答接口每次为独立无状态请求，响应含 `answer` + `metadata`（置信度/知识来源/图谱实体）

### 📊 集群拓扑统计视图优化
- 分布列表（资源池/集群/数据中心/硬件/节点角色）默认展示约 6 项，超出部分容器内滚动
- 顶部总数卡片顺序调整为：资源池 → 集群 → 租户 → 服务器 → 实例

### 🐛 修复
- 知识库模块首次进入时文件视图空白：文件视图容器补充初始 `active` 类，与"文件视图"按钮状态一致
- `routes/knowledge.py` 流式重建索引的多行嵌套 f-string 改为 Python 3.9 兼容写法（兼容本地 3.9 开发环境）

### ⚙️ 功能配置
- 新增"智能运维"模块开关：`feature_config` 增加 agent 记录，可在系统配置-功能配置页控制该模块显隐

### 📦 离线化
- vis-network 本地化到 `static/vendor/`（离线环境不再依赖 unpkg CDN），知识图谱可视化离线可用

### 🧹 代码整理
- `sql_checker.py` 移至 `utils/sql_checker.py`（本地 SQL 语法检查模块，sqlglot 解析）
- `create_import_template.py` 移至 `utils/`；`cluster_topology_import_template_v2.xlsx` 移至 `templates/`（下载接口文件缺失时自动重新生成）
- 删除根目录无引用的废弃 xlsx（dm/ob/oracle/其它）

### 🚀 离线部署配套
- 新增 `deploy/`：自动化部署脚本（`deploy.sh`）、systemd 单元（`dbsv-admin.service`）、离线依赖打包/校验脚本
- 新增 `requirements/`：Linux 离线依赖清单 + wheelhouse 离线 wheel 包
- CentOS 7 全离线部署方案（Python 3.12 + torch 2.5.1+cpu + m3e-base 模型本地缓存），详见 `deploy/DEPLOY_CENTOS7.md`

## v2.0.3 (2026-08-08)

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

## v2.0.2 (2026-08-05)

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

## v2.0.1 (2026-07-30)

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

## v2.0.0 (2026-07-29)

### 🕸️ 知识图谱模块（重大更新）

#### 核心架构
- **Chunk-Entity 混合图谱**：复用现有 13,153 个 chunk 作为文档层，增量添加 **44,963** 个实体节点
- **SQLite 存储**：3 张核心表（kg_entities、kg_relationships、kg_chunk_entities）+ 7 个索引
- **混合提取策略**：规则匹配（正则+词典）+ LLM 提取（深度提取）

#### 实体提取（14 种类型）
- **规则提取**：数据库产品（21）、版本号（**14,107**）、错误码（**2,522**）、参数（**17,675**）、函数（**8,409**）、系统视图（**2,126**）、SQL 语句（**30**）、操作系统（12）、硬件（5）、性能指标（12）、架构（10）、概念（**17**）、命令工具（**17**）
- **LLM 提取**：复杂概念、架构模式、故障场景、跨产品关系

#### 知识图谱数据规模（截至 v2.0.1）
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
| `templates/index.html` | 添加知识图谱导航和模块 HTML（**v2.0.1 已合并到知识库**） |
| `static/js/app.js` | 添加 Ctrl+9 快捷键和 kg 模块切换（**v2.0.1 已移除，合并到知识库**） |
| `static/css/style.css` | 添加知识图谱样式（~300 行，**v2.0.1 新增知识库视图切换样式**） |

---

## v1.6.1 (2026-07-28)

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

## v1.6.0 (2026-07-24)

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

## v1.5.2 (2026-07-16)

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
- **更新 `code_desc.md`**: 版本号 v1.5.2，更新函数说明，添加开发规范

---

## v1.5.1 (2026-07-16)

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

## v1.5.0 (2026-07-14)

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

## v1.4.2 (2026-07-13)

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

## v1.4.1 (2026-07-08)

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

## v1.4.0 (2026-07-03)

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

## v1.3.0 (2026-06-30)

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

## v1.2.5 (2026-06-30)

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

## v1.2.0 (2026-06-29)

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
- CSS 版本号更新为 v1.2.0

---

## v1.2 (2026-06-27)

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

## v1.1 (2026-06-19)

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
- [x] **暗色主题（v1.2.0）**
- [x] **知识库自动扫描（v1.2.0）**
- [x] **代码质量优化（v1.2.0）**
- [x] **多模型配置管理（v1.2.5）**
- [x] **集群拓扑节点展示 CPU/内存（v1.2.5）**
- [x] **机房层级分组（v1.2.5）**
- [x] **前端 JS 模块化重构（v1.3.0）**
- [x] **集群拓扑统计视图（v1.4.0）**
- [x] **节点设备类型和角色拆分（v1.4.0）**
- [x] **功能配置开关（v1.4.2）**
- [x] **代码块样式优化（v1.4.2）**
- [x] **clusters 表 resource_pool_id 字段（v1.4.1）**
- [x] **集群名称显示修复（v1.4.1）**
- [x] **自动集群创建（v1.4.1）**
- [x] **日志分析模块（v1.5.0）**
- [x] **数据库类型选择（v1.5.0）**
- [x] **模型本地缓存检测（v1.5.1）**
- [x] **编码规范强化（v1.5.1）**
- [x] **问答模块修复（v1.5.1）**
- [x] **安全漏洞修复（v1.5.2）**：SQL注入防护、Base64伪加密移除、XSS漏洞修复、路径遍历防护
- [x] **性能优化（v1.5.2）**：N+1查询消除、函数重构、代码质量提升
- [x] **智能运维Agent模块（v1.6.0）**：ReAct循环引擎、Harness安全约束框架、Skills领域知识、MCP工具定义、SSE流式输出、SSH/DB连接管理

---

## 后续规划和可优化方向

### 集群拓扑增强
- 租户管理功能完善
- 实例之间的连线（主从关系）
- 主从节点颜色区分
- 拓扑图导出为图片
- **容灾视图（跨机房复制关系可视化）**：支持展示实例间的同步/异步复制关系，横向排列机房，用连线表示复制链路

### 运维智能化（Agent）
- **变更审批流的集群多实例扩展**：get_cluster_info 拓扑枚举（集群→租户→实例）+ 全局只读/高权凭据对（加密存储）+ 按实例 host/port 动态建连，接入现有变更审批流程支持跨实例批量变更；多节点 SSH 批量执行、计划回滚自动执行、审批通知/历史审计页
- **蓝鲸监控表结构接入**：用户提供蓝鲸库建表语句/字段清单后，填 `tools/monitor_blueking.py` 的 `BlueKingMetrics.QUERIES` 后端到端拉数据
- **Hermes 后续**：技能多模型竞争/自修复、记忆定期重嵌入与去重归档、并行工具前端逐结果实时流
- **表名前缀标准化**：无前缀表（集群拓扑 resource_pools/clusters/servers/instances/tenants/instance_relations 等）统一加模块前缀（topo_*），方向待定（全量重命名 / 仅新表前缀 / 只读视图别名）

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