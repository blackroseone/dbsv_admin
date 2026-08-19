# Agent 智能化与范围树交互修复任务清单

> 本文档是交给执行模型（ds-v4-flash）的工作订单。每个条目包含：问题描述、代码位置、具体修改方案、验收标准。
> 执行约束：
> - 位置以 **函数名 / 选择器 / CSS 类名** 为准定位，行号仅供参考（代码可能已漂移）。
> - 注释风格与所在文件保持一致（本仓库代码注释为中文，说明意图而非开发过程）。
> - 每完成一个条目跑一次对应语法检查（见文末验证清单），小步提交。
> - 禁止在注释 / commit message 中出现 FIXED、Step、Phase 等开发过程词与 AI 工具名。

---

## 第一部分：AI 工程（Agent 引擎）

### A-1【P0】前端结论块重复 ID，导致多轮会话【分析结论】空返回

**问题**：`showAgentConclusion` 每次运行都用固定 id `agent-conclusion-<sid>` 创建结论块；`appendAgentConclusion` / `finalizeAgentConclusion` 用 `chat.querySelector('#agent-conclusion-' + sid)` 取第一个匹配。同一会话第二次提问起，本次结论流全部追加进上一次的旧块，本次新建的结论块保持空。

**位置**：`static/js/agent.js`
- `showAgentConclusion`（约 1404-1421 行）
- `appendAgentConclusion`（约 1427 行）
- `finalizeAgentConclusion`（约 1440 行）
- 历史回放 `renderAgentStep` 中的结论块创建（约 2099-2107 行）

**方案**：
1. 在会话视图状态对象（view）中增加本次运行的引用缓存，例如 `view.conclusionDiv`；`showAgentConclusion` 创建块时同时写入 `view.conclusionDiv = div`。
2. `appendAgentConclusion` / `finalizeAgentConclusion` / 反馈按钮 / 重新生成按钮一律改用 `view.conclusionDiv` 引用，不再 `querySelector` 按 id 首匹配。
3. `concluding_start` 每次触发时旧引用置空，避免串块。
4. 历史回放路径同改为持有各自块的引用（或生成含递增序号的唯一 id：`agent-conclusion-<sid>-<runSeq>`，view 内维护 `runSeq` 计数）。

**验收**：同一会话连续提问两次以上，每次运行的【分析结论】块均正确填充本次内容，旧结论块保持不变。

### A-2【P0】流式解析未处理 `reasoning_content`，推理模型思考/结论整段丢失

**问题**：`call_llm_stream` 只累积 `delta['content']`。推理模型思考 token 走 `delta.reasoning_content`，`content` 可能长时间为空，导致 Agent 思考为空 -> 解析不出工具调用 -> 循环提前 break。

**位置**：`utils/__init__.py`，`call_llm_stream`（约 423-437 行，流式 delta 解析处）。

**方案**：
```python
delta = chunk['choices'][0].get('delta', {})
text = delta.get('content') or delta.get('reasoning_content') or ''
if text:
    yield text, None
```

**验收**：`python -m py_compile utils/__init__.py` 通过；配置一个推理型模型（reasoning_content 返回型）跑一次 Agent 会话，思考阶段不再空转。

### A-3【P0】变更操作执行后无强制验证（长链路不查日志的根因之一）

**问题**：系统提示中「答案即止」规则对诊断和变更一视同仁；计划批准执行完直接回下一轮 think，模型可拿 `exit_code=0` 直接收敛，不 tail 日志、不查状态。

**位置**：`agent/engine.py`
- `_build_system_prompt`（约 420 行「答案即止」规则、约 430 行变更类段落）
- 计划批准执行分支（`_handle_plan_approval` 返回 'approved' 处，约 792 行附近已有"操作计划已批准..."注入点）
- ReAct 主循环 think 分支（约 207-273 行）

**方案**（prompt + 引擎两层，配合使用）：

1. `_build_system_prompt` 变更类段落后新增规则（中文 prompt，与现有风格一致）：
```
## 变更操作执行后必须验证（覆盖"答案即止"）
每项已批准操作执行后、写结论前，必须用只读工具验证：
1. 服务/实例启停 -> systemctl status / ps / 实例状态查询，确认目标状态；
2. 有日志的操作（安装/备份/初始化/配置）-> tail -n 50 <日志路径>，
   确认无 ERROR 级错误、出现成功标记；
3. 验证输出必须写入结论（"已确认 xxx"），不得仅凭命令返回码下结论。
"答案即止"不适用于变更操作：验证完成才能结束。
```

2. `_handle_plan_approval` 执行完返回 'approved' 后，追加注入一条 user 消息：
```python
self.state.add_message('user',
    "已批准的操作已全部执行。写结论前请先用只读工具验证执行结果"
    "（tail 日志 / 检查进程 / 查询状态），确认无报错后再给最终结论。")
```

3. ReAct 主循环加 `pending_verification` 标志：上一步执行了变更类操作时置位；当前步模型未产出任何工具调用（想直接给结论）且标志仍置位时，注入"请先验证执行结果"提示并重试本轮；二次仍无验证动作才放行收敛。重试后记得清标志，避免死循环。

**验收**：`python -m py_compile agent/engine.py` 通过；用一个已批准的备份/安装类计划跑一次，确认结论前出现 tail 日志或状态检查的只读工具步骤。

### A-4【P1】LLM 调用失败被静默吞掉，整轮无反馈

**问题**：`_stream_llm` 流式失败回退非流式，非流式再失败时只 print 到控制台，不向 SSE 产出事件；空文本不抛异常，前端无任何可见反馈。

**位置**：`agent/engine.py`，`_stream_llm`（约 547-576 行，fallback 与异常分支）。

**方案**：`full` 为空且 fallback 结果也为空时，产出可感知事件而非静默返回：
```python
if not full:
    yield {"type": "executing_warning",
           "warning": "⚠️ LLM 调用失败或返回空，本次步骤无输出"}
```
（事件类型若与 SSE 协议不符，改用现有的 warning 类事件名，前端已能渲染。）

**验收**：临时把 LLM API 地址改错跑一次会话，前端能看到明确警告而非静默空转。

### A-5【P1】execute_command 返回体给假成功信号，且超时无引导

**问题**：
1. `nohup ... &` 后台命令立即返回 exit_code=0，实际安装/备份可能稍后失败；
2. 默认 30s 超时，安装/备份必超时，模型无从查进度；
3. 工具 description 无"执行后应验证"指引。

**位置**：
- `agent/tools.py`，`execute_command`（约 228-282 行，timeout 默认值约 235 行，输出截断 `out.strip()[:3000]` 约 272 行，description 约 174 行）
- `agent/connectors.py`，`run_ssh_command`（约 274-278 行）

**方案**：
1. 节点执行返回体扩展字段：
```python
return {"node": ..., "ok": exit_code == 0 and not timed_out,
        "exit_code": exit_code,
        "timed_out": timed_out,
        "truncated": truncated,
        "output": <头+尾截断后的输出>}
```
2. 超时时在 output 内直接内嵌提示（模型无需推理就知道下一步）：
   `"命令执行超时，可能仍在运行，请用 ps / tail 检查进程与日志。"`
3. `execute_command` 的 description 追加：
   `"执行变更类/长耗时命令后，应随后用只读命令（tail / ps / systemctl status）确认结果再结束。"`
4. 计划操作执行处（`agent/engine.py` `_execute_plan_operations`，约 875 行）的 timeout 默认值从 30 提到 300。

**验收**：`python -m py_compile agent/tools.py agent/connectors.py` 通过；跑一条 sleep 60 的命令确认返回体含 `timed_out: true` 与内嵌提示。

### A-6【P1】输出截断丢尾部判定信息

**问题**：命令输出只保留前 3000 字符，成功/失败标记（`[ OK ]`、`ERROR:`、`ORA-`）常在尾部被切掉；batch 摘要每节点只留 120 字符。

**位置**：
- `agent/tools.py`（约 272 行，`out.strip()[:3000]`）
- `agent/engine.py`（约 1130 行，batch 摘要 `output[:120]`）

**方案**：
1. 长输出改为「头+尾」保留：`out[:1500] + '\n... [中间省略] ...\n' + out[-1500:]`，返回体标注 `truncated: true`。
2. batch 摘要（`_format_result`）对变更类节点至少保留 exit_code 与尾部 200 字符。

**验收**：构造一条输出超 3000 字符且错误在尾部的命令（如 `echo start; seq 1 500; echo 'ERROR: x'`），确认返回体尾部包含 ERROR 行。

### A-7【P1】大结果进 history 导致上下文爆炸、提前强制收敛

**问题**：多节点批量观察动辄数千字符直接 add_message 进 history；叠加 `HISTORY_COMPRESS_THRESHOLD=10`（每条中间消息压缩时硬截 120 字符）与 `AGENT_MAX_HISTORY_CHARS=12000`，长链路任务 1-2 步就触发"对话历史过长，停止继续执行"。这是 v4.0 范围特性下长任务做不完的根因之一。

**位置**：`agent/engine.py`
- 工具结果入 history 处（并行执行结果 add_message，约 278-295 行）
- `_build_messages` 上下文压缩（约 590-619 行）
- `config.py` Agent 常量（约 46-49 行）

**方案**：
1. 大型结构化结果（多行 rows / metrics / batch 结果）不整段进 history，改为短摘要（如 `[query_database] 5行: <前2行>`）；全量结果仅通过 SSE `executing_end.result` 给前端展示。
2. 压缩中间消息时按类型结构化保留关键信息（exit_code / row_count / 失败节点列表），而非统一 120 字符截断。
3. 评估将 `AGENT_MAX_HISTORY_CHARS` 适当上调（如 12000 -> 20000），配合摘要化改造后 token 增量可控。

**验收**：`python -m py_compile agent/engine.py` 通过；跑一个 4+ 节点的批量查询任务，不再在第 2-3 步触发"对话历史过长"强制收敛，且结论仍引用到早期步骤的关键信息。

### A-8【P2】工具调用解析失败静默丢弃，无纠正回喂

**问题**：工具以纯文本 JSON 列在 prompt，`_extract_tool_calls` 用正则扫描解析；解析失败仅 `pass` 静默丢弃 -> 无工具执行直接 break -> 会话空转/提前收敛。另外 fence 正则用第一个 ``` 代码块整体替换全文，模型分段各包一个 JSON 时后续段落全丢。

**位置**：`agent/engine.py`，`_extract_tool_calls`（约 621-681 行；fence 替换约 631-633 行，静默丢弃约 667-677 行）。

**方案**（分两档，先做低风险档）：
1. 低风险档（先做）：
   - 解析失败时把错误回喂模型而非静默 break：`self.state.add_message('user', "你的工具调用 JSON 无法解析（<片段前200字符>），请只输出合法 JSON")`，让下一轮重试；
   - fence 处理改为只剥离 fence 标记、保留全文：`re.sub(r'```(?:json)?\s*|\s*```', '', thought, flags=re.DOTALL)`，不再整体替换。
2. 高风险档（可选，单独评估）：平台模型均为 OpenAI 兼容时，传 `tools` 参数（`get_tool_schemas()` 已有 OpenAI function 格式）走原生 function calling，解析 `message.tool_calls`；文本 JSON 解析保留为 fallback。此项改动面大，建议独立提交并充分回归。

**验收**：低风险档：`python -m py_compile agent/engine.py` 通过；手动构造一个会输出非法 JSON 的场景（或临时在解析处打断点注入坏 JSON），确认模型下一轮收到纠正提示而非静默结束。

### A-9【P2】并行工具执行无异常兜底

**问题**：`_run_one_action` 未包 try/except，ThreadPoolExecutor 中工具抛未捕获异常会让整个 `_execute_actions` 抛异常中断循环。

**位置**：`agent/engine.py`，`_run_one_action`（并行执行处，约 692-723 行）。

**方案**：`_run_one_action` 内兜底：
```python
try:
    ...
except Exception as e:
    return {..., 'observation': f"❌ 执行出错: {e}"}
```

**验收**：`python -m py_compile agent/engine.py` 通过。

### A-10【P2】continue-on-error 失败节点无排查引导

**问题**：批量变更失败节点只记入 observation，无引导，模型倾向直接下"部分节点失败"的结论完事。

**位置**：`agent/engine.py`，`_execute_plan_operations`（约 893-900 行，失败节点 observation 写入处）。

**方案**：失败节点的 observation 末尾追加：
`"请用只读工具检查失败节点的日志/状态，定位原因后再决定下一步。"`

**验收**：`python -m py_compile agent/engine.py` 通过。

### A-11【P3】死循环检测指纹过严 + 触发后提示不被消费

**位置**：`agent/engine.py`（约 197-204、683-686 行）。

**方案**：指纹归一化为「工具名 + 参数键集合」（参数值微变不重复计数）；触发死循环时改为引导收敛到 conclusion，而非写一条不会被消费的 history 消息后立即 break。

**验收**：`python -m py_compile agent/engine.py` 通过。

### A-12【P3】其他低优先级（可最后做或暂缓）

- **流中断残留空结论块**：`static/js/agent.js` 约 1020-1028 行；done/error/cancelled 事件处理时，若本次结论块内容为空则移除或填"未生成结论"占位。
- **墙钟超时**：`agent/engine.py` 主循环加总墙钟上限（如 5 分钟），超时优雅收敛并给出部分结论。
- **max_tokens 未设置**：`utils/__init__.py` `_build_api_data`（约 320-335 行）增加可配置 max_tokens（结论类 2048~4096），防弱模型默认上限截断。
- **取消机制多 worker 失效**：`agent/engine.py` `_cancel_flags`（约 21-35 行）为进程内 dict，gunicorn 多 worker 部署时 stop 失效；改 DB 标记位或共享存储。单进程部署可暂缓。
- **知识检索阈值校准**：`agent/engine.py` `_retrieve_knowledge_strict` 阈值 0.75/0.80 对短中文问句偏高，频繁触发 knowledge_warning；统计实际相似度分布后再调。

---

## 第二部分：前端（智能运维模块范围树）

### B-1【P0/必须】范围面板 flex 压缩，树挤在一起且无法滚动（两个痛点共根）

**问题**：`.scope-panel` 是「列方向 flex + overflow-y:auto」滚动容器；直接子项 `.scope-pool` 默认 `flex-shrink: 1` 且 `overflow: hidden`（自动最小高度归零），内容超高时所有池被等比压扁塞进面板而非出现滚动条。聊天区 `.agent-chat > * { flex-shrink: 0; }` 已修过同款问题，范围面板漏掉了。

**位置**：`static/css/style.css`
- `.scope-panel`（约 5224-5232 行）
- `.scope-pool`（约 5248-5252 行）
- 参考已有修复：`.agent-chat > *`（约 5930-5945 行）

**方案**（一行 CSS，加在 `.scope-panel` 规则块之后）：
```css
.scope-panel > * { flex-shrink: 0; }
```
注意：不要试图改 `.scope-pool` 的 `overflow:hidden` 为 `clip` 来解决——clip 同样令自动最小高度归零，无效。

**验收**：浏览器展开一个 50+ 节点的池：面板出现滚动条；其余池不被压扁；滚动到底可看到并勾选最后一个节点。

### B-2【P0/必须】全部展开后勾选任意节点，所有树塌回折叠态

**问题**：`renderAgentScopeTree` 用 `agentScopeCollapsed.size === 0` 判断"首次初始化"。用户展开全部池（集合为空）后任何勾选触发重渲染，被误判为未初始化，所有池重新折叠。

**位置**：`static/js/agent.js`
- `agentScopeCollapsed` 定义（约 21 行）
- `renderAgentScopeTree` 内初始化判断（约 96-99 行）

**方案**：新增模块级一次性标志，与集合是否为空解耦：
```js
let agentScopeCollapsedInit = false;
// renderAgentScopeTree 内：
if (!agentScopeCollapsedInit) {
    agentScopeCollapsedInit = true;
    agentScopeTree.forEach(p => agentScopeCollapsed.add('pool:' + p.id));
}
```

**验收**：展开全部池后勾选列表深处节点，所有树保持展开态。

### B-3【建议】重渲染丢失滚动位置与焦点

**问题**：`renderAgentScopeTree` 每次全量 `innerHTML` 重建（折叠/勾选/连接刷新都触发），滚动被拽回顶部、焦点丢失。

**位置**：`static/js/agent.js`，`renderAgentScopeTree`（约 89-163 行）。

**方案**：渲染前保存 `panel.scrollTop` 与当前焦点元素的 `data-target-key`（或按钮的池 key），渲染后恢复 scrollTop 并按 key 找回焦点（`panel.querySelector` + `.focus()`）。不改渲染方式，几行代码。

**验收**：滚动到列表中部勾选一个节点，页面不跳回顶部，焦点仍在该节点上。

### B-4【建议】节点搜索/过滤（当前约 500 节点无任何检索手段）

**位置**：
- `templates/index.html` 范围区块（约 436-444 行，h3 与面板之间加输入框）
- `static/js/agent.js`：新增 `agentScopeFilter` 状态；`renderAgentScopeTree` 渲染时剪枝

**方案**：
1. h3 与面板间加 `<input class="scope-filter" placeholder="搜索池/服务器/实例...">`。
2. 渲染三层剪枝：池名/db_type 命中或含命中后代才显示；服务器名/host 命中或含命中实例才显示；实例名/端口命中才显示。
3. 过滤激活时自动展开所有命中池；显示"匹配 N 节点"计数（复用现有 `.scope-count` / `updateAgentScopeCount`）。
4. 输入防抖 200ms 后重渲染；清空输入恢复全量。

**验收**：输入某实例端口，仅相关池/服务器/实例显示且自动展开，计数正确；清空后恢复。

### B-5【建议】全部展开 / 全部折叠按钮

**位置**：`static/js/agent.js`（`agentScopeCollapsed` 操作处，约 21、166-173 行）；`templates/index.html` 范围区 h3 右侧。

**方案**：两个小按钮，批量把所有 `pool:*` / `ssh:*` 键加入/移出 `agentScopeCollapsed` 后重渲染。按钮样式复用批量结果区 `expandAllBatchResults`（约 1357 行）的风格保持统一。

**验收**：一键展开/折叠全部池，且与 B-2 修复后勾选不触发重折叠。

### B-6【建议】折叠状态持久化（与勾选状态行为对齐）

**位置**：`static/js/agent.js`（`agentScopeCollapsed` 约 21 行；`agentScopeTargets` 已持久化的写法参考约 225-227 行；`initAgentModule` 恢复）。

**方案**：`agentScopeCollapsed` 序列化为数组存 localStorage（键 `agentScopeCollapsed`），初始化时恢复；恢复结果为空数组时再走"默认全折叠"逻辑。

**验收**：展开部分池后刷新页面，展开状态保留。

### B-7【可选】池 checkbox 半选态与判定修正

**问题**：池勾选判定只统计 ssh 服务器、忽略实例，且无半选态，易"看似全选实为部分、点击即清空"。

**位置**：`static/js/agent.js`，池 checkbox 渲染（约 143-146 行）、`onAgentScopeChange`（约 188-195 行）。

**方案**：池判定改为"所有服务器且所有实例均选中"才算 checked；部分选中时渲染后遍历 `panel.querySelectorAll('input[data-pool-key]')` 设置 `cb.indeterminate = true`（不改 DOM 结构）。

**验收**：勾选池下部分实例，池框呈半选态；全选后呈全选态。

### B-8【可选】滚动条可见性（Firefox 对齐 + 浅色主题可见）

**位置**：`static/css/style.css`，`.scope-panel` 滚动条样式（约 5361-5362 行）。

**方案**：补 `scrollbar-width: thin; scrollbar-color: var(--border-color) transparent;`（`.agent-tabs` 约 5869 行已用同款，保持一致）；webkit 滚动条加 hover 增亮态。

### B-9【可选】「配置」按钮 hover 显示（0 连接场景约 500 个按钮同屏）

**位置**：`static/js/agent.js`（按钮渲染约 110-111、121-122 行）；`static/css/style.css`。

**方案**：
```css
.scope-node .scope-config-btn { visibility: hidden; }
.scope-node:hover .scope-config-btn,
.scope-node:focus-within .scope-config-btn { visibility: visible; }
```
⚠️ 徽标保持常显作为"未配置"提示；不破坏现有 `quickConfigAgentNode`（约 238 行）入口。

### B-10【可选】折叠按钮 aria-expanded

**位置**：`static/js/agent.js`，折叠按钮渲染（约 131、149 行）。

**方案**：原生 `<button>` 补 `aria-expanded="${!collapsed}"`；给服务器/实例容器补 id 并加 `aria-controls` 关联。不必上完整 `role="tree"`。

---

## 执行顺序建议

1. **第一批（P0，改动小收益大）**：B-1 → B-2 → A-1 → A-2 → A-3
2. **第二批（P1）**：A-4 → A-5 → A-6 → A-7 → B-3
3. **第三批（建议级前端）**：B-4 → B-5 → B-6
4. **第四批（P2/P3）**：A-8（低风险档）→ A-9 → A-10 → A-11 → A-12 → B-7/B-8/B-9/B-10

每批独立提交，便于回滚。

## 验证清单（每批完成时执行）

```bash
# Python 语法检查
python -m py_compile app.py agent/engine.py agent/tools.py agent/connectors.py utils/__init__.py

# JS 语法检查
node --check static/js/agent.js

# 应用工厂可构建
python -c "from app import create_app; app = create_app(); print('OK')"
```

功能验证场景：
- 痛点一复现验证：同一 Agent 会话连续提问 2+ 次，每次【分析结论】均正常填充（A-1）。
- 痛点二复现验证：执行一个已批准的安装/备份类计划，确认结论前出现 tail 日志 / 状态检查步骤（A-3/A-5）。
- 范围树验证：展开多节点池出现滚动条、其余池不压缩（B-1）；展开全部后勾选深层节点不塌回（B-2/B-3）。
