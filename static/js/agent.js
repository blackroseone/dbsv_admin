/**
 * 智能运维Agent模块
 */

// ==================== Agent模块状态 ====================
let agentCurrentSession = null;
let agentSSHConnections = [];
let agentDBConnections = [];
let agentSessions = [];
let agentIsRunning = false;
let agentCurrentSSHConn = null;
let agentCurrentDBConn = null;
let agentAbortController = null;

// ==================== 模块初始化 ====================
function initAgentModule() {
    loadAgentSSHConnections();
    loadAgentDBConnections();
    loadAgentSessions();
    loadAgentSkills();
    loadAgentMemory();
}

// ==================== 连接管理 ====================
async function loadAgentSSHConnections() {
    try {
        const response = await fetch('/api/agent/ssh-connections');
        const data = await response.json();
        agentSSHConnections = data.connections || [];
        // 未选中时自动选中第一个，避免配置后还需手动点选才能开会话
        if (!agentCurrentSSHConn && agentSSHConnections.length > 0) {
            agentCurrentSSHConn = agentSSHConnections[0].id;
        }
        renderAgentSSHConnections();
        updateAgentConnectionStatus();
    } catch (error) {
        console.error('加载SSH连接失败:', error);
    }
}

async function loadAgentDBConnections() {
    try {
        const response = await fetch('/api/agent/db-connections');
        const data = await response.json();
        agentDBConnections = data.connections || [];
        // 未选中时自动选中第一个
        if (!agentCurrentDBConn && agentDBConnections.length > 0) {
            agentCurrentDBConn = agentDBConnections[0].id;
        }
        renderAgentDBConnections();
        updateAgentConnectionStatus();
    } catch (error) {
        console.error('加载DB连接失败:', error);
    }
}

function renderAgentSSHConnections() {
    const container = document.getElementById('agent-ssh-conn-list');
    if (!container) return;

    if (agentSSHConnections.length === 0) {
        container.innerHTML = '<div class="empty-message">暂无SSH连接</div>';
        return;
    }

    container.innerHTML = agentSSHConnections.map(conn => `
        <div class="connection-item ${agentCurrentSSHConn === conn.id ? 'active' : ''}"
             onclick="selectSSHConnection('${escapeJsAttr(conn.id)}')">
            <div class="conn-name">${escapeHtml(conn.name)}</div>
            <div class="conn-info">
                <span class="conn-host">${escapeHtml(conn.host)}:${escapeHtml(conn.port)}</span>
                <span class="conn-type">${escapeHtml(conn.db_type)}</span>
                <span class="conn-status ${escapeHtml(conn.status)}">${conn.status === 'active' ? '🟢' : '🔴'}</span>
            </div>
        </div>
    `).join('');
}

function renderAgentDBConnections() {
    const container = document.getElementById('agent-db-conn-list');
    if (!container) return;

    if (agentDBConnections.length === 0) {
        container.innerHTML = '<div class="empty-message">暂无数据库连接</div>';
        return;
    }

    container.innerHTML = agentDBConnections.map(conn => `
        <div class="connection-item ${agentCurrentDBConn === conn.id ? 'active' : ''}"
             onclick="selectDBConnection('${escapeJsAttr(conn.id)}')">
            <div class="conn-name">${escapeHtml(conn.name)}</div>
            <div class="conn-info">
                <span class="conn-host">${escapeHtml(conn.host)}</span>
                <span class="conn-type">${escapeHtml(conn.db_type)}</span>
                <span class="conn-status ${escapeHtml(conn.status)}">${conn.status === 'active' ? '🟢' : '🔴'}</span>
            </div>
        </div>
    `).join('');
}

function selectSSHConnection(connId) {
    agentCurrentSSHConn = connId;
    renderAgentSSHConnections();
    updateAgentConnectionStatus();
}

function selectDBConnection(connId) {
    agentCurrentDBConn = connId;
    renderAgentDBConnections();
    updateAgentConnectionStatus();
}

function updateAgentConnectionStatus() {
    const sshStatus = document.getElementById('agent-ssh-status');
    const dbStatus = document.getElementById('agent-db-status');

    if (sshStatus) {
        const sshConn = agentSSHConnections.find(c => c.id === agentCurrentSSHConn);
        sshStatus.textContent = sshConn ? `🟢 ${sshConn.name}` : '🔴 SSH未连接';
    }

    if (dbStatus) {
        const dbConn = agentDBConnections.find(c => c.id === agentCurrentDBConn);
        dbStatus.textContent = dbConn ? `🟢 ${dbConn.name}` : '🔴 DB未连接';
    }
}

function switchAgentTab(tab) {
    document.querySelectorAll('.connection-tabs .tab-btn').forEach(btn => {
        btn.classList.remove('active');
    });
    document.querySelector(`.connection-tabs .tab-btn[data-tab="${tab}"]`).classList.add('active');

    document.querySelectorAll('.tab-content').forEach(content => {
        content.style.display = 'none';
    });
    document.getElementById(`agent-${tab}-connections`).style.display = 'block';
}

// ==================== 会话管理 ====================
async function loadAgentSessions() {
    try {
        const response = await fetch('/api/agent/sessions');
        const data = await response.json();
        agentSessions = data.sessions || [];
        renderAgentSessions();
    } catch (error) {
        console.error('加载会话失败:', error);
    }
}

function renderAgentSessions() {
    const container = document.getElementById('agent-session-list');
    if (!container) return;

    if (agentSessions.length === 0) {
        container.innerHTML = '<div class="empty-message">暂无会话</div>';
        return;
    }

    container.innerHTML = agentSessions.map(session => `
        <div class="session-item ${agentCurrentSession === session.id ? 'active' : ''}"
             onclick="loadAgentSession('${escapeJsAttr(session.id)}')">
            <div class="session-title">${escapeHtml(session.title)}</div>
            <div class="session-meta">
                <span class="session-status ${escapeHtml(session.status)}">${getStatusIcon(session.status)}</span>
                <span class="session-time">${formatTime(session.created_at)}</span>
            </div>
        </div>
    `).join('');
}

function getStatusIcon(status) {
    const icons = {
        'idle': '⏸️',
        'running': '🔄',
        'completed': '✅',
        'error': '❌'
    };
    return icons[status] || '⏸️';
}

async function newAgentSession() {
    if (!agentCurrentSSHConn && !agentCurrentDBConn) {
        // 无连接也允许建会话：知识问答/检查项检索等无需连接的能力可先用；
        // 需要查询/执行时 Agent 会提示缺少对应连接
        showToast('未选连接：知识问答可用，查询/执行类操作需先配置连接', 'info');
    }

    try {
        const response = await fetch('/api/agent/sessions', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                title: '新会话',
                ssh_connection_id: agentCurrentSSHConn,
                db_connection_id: agentCurrentDBConn
            })
        });

        const data = await response.json();
        if (data.session) {
            agentCurrentSession = data.session.id;
            loadAgentSessions();
            clearAgentChat();
            showToast('会话创建成功', 'success');
        }
    } catch (error) {
        console.error('创建会话失败:', error);
        showToast('创建会话失败', 'error');
    }
}

async function loadAgentSession(sessionId) {
    agentCurrentSession = sessionId;
    renderAgentSessions();

    try {
        const response = await fetch(`/api/agent/sessions/${sessionId}`);
        const data = await response.json();

        // 渲染历史消息
        clearAgentChat();
        if (data.steps && data.steps.length > 0) {
            data.steps.forEach(step => {
                renderAgentStep(step);
            });
            // 有历史消息则不展示欢迎语（与知识问答模块一致）
            const welcome = document.querySelector('#agent-chat .agent-welcome');
            if (welcome) welcome.remove();
        }
    } catch (error) {
        console.error('加载会话失败:', error);
    }
}

// ==================== 对话功能 ====================
async function sendAgentQuestion() {
    const input = document.getElementById('agent-input');
    const question = input.value.trim();

    if (!question) return;
    if (!agentCurrentSession) {
        showToast('请先创建会话', 'warning');
        return;
    }
    if (agentIsRunning) {
        showToast('Agent正在执行中，请等待', 'warning');
        return;
    }

    // 开始对话后移除欢迎语（参考知识问答模块：有消息即不再展示欢迎页）
    const agentWelcome = document.querySelector('#agent-chat .agent-welcome');
    if (agentWelcome) agentWelcome.remove();

    // 添加用户消息
    addAgentMessage('user', question);
    input.value = '';

    agentIsRunning = true;
    agentAbortController = new AbortController();
    const stopBtn = document.getElementById('agent-stop-btn');
    if (stopBtn) stopBtn.style.display = 'inline-block';

    try {
        const response = await fetch('/api/agent/run', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                session_id: agentCurrentSession,
                question: question
            }),
            signal: agentAbortController.signal
        });

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split('\n');
            buffer = lines.pop();

            for (const line of lines) {
                if (line.startsWith('data: ')) {
                    const data = line.slice(6);
                    if (data === '[DONE]') continue;

                    try {
                        const event = JSON.parse(data);
                        handleAgentEvent(event);
                    } catch (e) {
                        console.error('解析SSE事件失败:', e);
                    }
                }
            }
        }
    } catch (error) {
        if (error.name === 'AbortError') {
            addAgentMessage('error', '⏹ 已手动停止');
        } else {
            console.error('Agent执行失败:', error);
            addAgentMessage('error', `执行失败: ${error.message}`);
        }
    } finally {
        agentIsRunning = false;
        agentAbortController = null;
        if (stopBtn) stopBtn.style.display = 'none';
        loadAgentSessions();  // 刷新会话状态
    }
}

// 停止Agent执行
function stopAgent() {
    if (agentAbortController) {
        agentAbortController.abort();
    }
}

function handleAgentEvent(event) {
    switch (event.type) {
        case 'retrieving_start':
            showAgentLoading('正在检索知识库...');
            break;
        case 'knowledge_refs':
            renderKnowledgeRefs(event.refs);
            break;
        case 'knowledge_warning':
            renderKnowledgeWarning(event.message);
            break;
        case 'thinking_start':
            showAgentThinking(event.step);
            break;
        case 'thinking_chunk':
            appendAgentThinking(event.content);
            break;
        case 'thinking_end':
            finalizeAgentThinking();
            break;
        case 'planning':
            renderAgentPlan(event.action);
            break;
        case 'executing_start':
            renderAgentToolCall(event.tool, event.parameters);
            break;
        case 'executing_end':
            renderAgentResult(event.result);
            break;
        case 'executing_error':
            renderAgentError(event.error);
            break;
        case 'executing_warning':
            renderAgentWarning(event.warning);
            break;
        case 'observing':
            renderAgentObservation(event.observation);
            break;
        case 'approval_required':
            renderAgentApproval(event);
            break;
        case 'approval_granted':
            renderAgentApprovalGranted(event);
            break;
        case 'approval_rejected':
            renderAgentApprovalRejected(event);
            break;
        case 'approval_expired':
            renderAgentApprovalExpired(event);
            break;
        case 'plan_operation_result':
            renderPlanOperationResult(event);
            break;
        case 'concluding_start':
            showAgentConclusion();
            break;
        case 'concluding_chunk':
            appendAgentConclusion(event.content);
            break;
        case 'concluding_end':
            finalizeAgentConclusion();
            break;
        case 'error':
            renderAgentError(event.message);
            break;
        case 'done':
            removeAgentLoading();
            break;
    }
}

// ==================== 消息渲染 ====================
function addAgentMessage(role, content) {
    const chat = document.getElementById('agent-chat');
    const messageDiv = document.createElement('div');
    messageDiv.className = `agent-message ${role}`;

    const icons = {
        'user': '👤',
        'assistant': '🤖',
        'error': '❌'
    };

    messageDiv.innerHTML = `
        <div class="message-header">
            <span class="icon">${icons[role] || '🤖'}</span>
            <span class="label">${role === 'user' ? '用户' : role === 'error' ? '错误' : 'Agent'}</span>
        </div>
        <div class="message-content">${escapeHtml(content)}</div>
    `;

    chat.appendChild(messageDiv);
    chat.scrollTop = chat.scrollHeight;
}

function renderKnowledgeRefs(refs) {
    const chat = document.getElementById('agent-chat');
    const div = document.createElement('div');
    div.className = 'agent-message knowledge';

    const refsHtml = refs.map((ref, i) => `
        <div class="knowledge-ref">
            <div class="ref-header">
                <span class="ref-num">[${i+1}]</span>
                <span class="ref-file">${escapeHtml(ref.file)}</span>
                <span class="ref-similarity">相似度: ${escapeHtml(ref.similarity)}</span>
            </div>
            <div class="ref-content">${escapeHtml(ref.chunk)}</div>
        </div>
    `).join('');

    div.innerHTML = `
        <div class="message-header">
            <span class="icon">📚</span>
            <span class="label">参考知识库</span>
        </div>
        <div class="message-content">
            ${refsHtml}
        </div>
    `;

    chat.appendChild(div);
    chat.scrollTop = chat.scrollHeight;
}

function renderKnowledgeWarning(message) {
    const chat = document.getElementById('agent-chat');
    const div = document.createElement('div');
    div.className = 'agent-message warning';
    div.innerHTML = `
        <div class="message-header">
            <span class="icon">⚠️</span>
            <span class="label">知识库警告</span>
        </div>
        <div class="message-content">
            <div class="warning-box">
                <strong>⚠️ 警告</strong>：${escapeHtml(message)}<br>
                <span class="warning-detail">此回答可能基于模型的一般知识，存在错误风险</span>
            </div>
        </div>
    `;
    chat.appendChild(div);
    chat.scrollTop = chat.scrollHeight;
}

function showAgentThinking(step) {
    const chat = document.getElementById('agent-chat');
    const div = document.createElement('div');
    div.className = 'agent-message thinking';
    div.id = `agent-thinking-${step}`;
    div.innerHTML = `
        <details class="agent-collapse" open>
            <summary class="message-header">
                <span class="icon">🤔</span>
                <span class="label">思考中</span>
                <span class="thinking-indicator"></span>
            </summary>
            <div class="message-content">
                <pre class="thinking-content"></pre>
            </div>
        </details>
    `;
    chat.appendChild(div);
    chat.scrollTop = chat.scrollHeight;
}

function appendAgentThinking(content) {
    const thinkingDiv = document.querySelector('.agent-message.thinking:last-child .thinking-content');
    if (thinkingDiv) {
        thinkingDiv.textContent += content;
    }
}

function finalizeAgentThinking() {
    const thinkingDiv = document.querySelector('.agent-message.thinking:last-child');
    if (thinkingDiv) {
        thinkingDiv.querySelector('.thinking-indicator').style.display = 'none';
    }
}

function renderAgentToolCall(tool, params) {
    const chat = document.getElementById('agent-chat');
    const div = document.createElement('div');
    div.className = 'agent-message tool';
    div.innerHTML = `
        <details class="agent-collapse" open>
            <summary class="message-header">
                <span class="icon">🔧</span>
                <span class="label">执行: ${escapeHtml(tool)}</span>
                <span class="tool-status">执行中...</span>
            </summary>
            <div class="message-content">
                <div class="tool-params">
                    <pre><code>${escapeHtml(JSON.stringify(params, null, 2))}</code></pre>
                </div>
            </div>
        </details>
    `;
    chat.appendChild(div);
    chat.scrollTop = chat.scrollHeight;
}

function renderAgentResult(result) {
    const toolDiv = document.querySelector('.agent-message.tool:last-child');
    if (!toolDiv) return;

    const statusDiv = toolDiv.querySelector('.tool-status');
    if (result.error) {
        statusDiv.innerHTML = '<span class="status-error">❌ 失败</span>';
    } else {
        statusDiv.innerHTML = '<span class="status-success">✅ 完成</span>';
    }

    const contentDiv = toolDiv.querySelector('.message-content');
    if (!contentDiv) return;

    // 表格：查询 / schema / 性能指标
    if (result.rows && result.columns) {
        contentDiv.appendChild(buildResultTable(result.columns, result.rows));
    } else if (result.tables && result.columns) {
        contentDiv.appendChild(buildResultTable(result.columns, result.tables));
    } else if (result.metrics && result.columns) {
        contentDiv.appendChild(buildResultTable(result.columns, result.metrics));
    }
    // 命令输出
    if (result.stdout !== undefined) {
        const pre = document.createElement('pre');
        pre.className = 'tool-output';
        pre.textContent = (result.stdout || '(无输出)') + (result.stderr ? `\n[stderr] ${result.stderr}` : '');
        contentDiv.appendChild(pre);
    }
    // 知识检索结果
    if (result.results && Array.isArray(result.results)) {
        const list = document.createElement('div');
        list.className = 'tool-result';
        list.innerHTML = result.results.length
            ? result.results.map(r =>
                `<div class="kg-ref-item"><span class="kg-ref-file">${escapeHtml(r.filename || '未知')}</span> <span class="kg-ref-sim">相似度: ${escapeHtml(r.similarity)}</span></div>`
              ).join('')
            : '<div class="empty-message">无检索结果</div>';
        contentDiv.appendChild(list);
    }
}

function buildResultTable(columns, rows) {
    const div = document.createElement('div');
    div.className = 'tool-result';
    div.innerHTML = `
        <details>
            <summary>查看结果 (${rows.length} 行)</summary>
            <div class="result-table-wrapper">
                <table class="result-table">
                    <thead>
                        <tr>${columns.map(c => `<th>${escapeHtml(String(c))}</th>`).join('')}</tr>
                    </thead>
                    <tbody>
                        ${rows.map(row => `
                            <tr>${row.map(cell => `<td>${escapeHtml(String(cell))}</td>`).join('')}</tr>
                        `).join('')}
                    </tbody>
                </table>
            </div>
        </details>
    `;
    return div;
}

function renderAgentObservation(observation) {
    const chat = document.getElementById('agent-chat');
    const div = document.createElement('div');
    div.className = 'agent-message observation';
    div.innerHTML = `
        <div class="message-header">
            <span class="icon">👁️</span>
            <span class="label">观察结果</span>
        </div>
        <div class="message-content">
            <pre>${escapeHtml(observation)}</pre>
        </div>
    `;
    chat.appendChild(div);
    chat.scrollTop = chat.scrollHeight;
}

function showAgentConclusion() {
    const chat = document.getElementById('agent-chat');
    const div = document.createElement('div');
    div.className = 'agent-message conclusion';
    div.id = 'agent-conclusion';
    div.innerHTML = `
        <div class="message-header">
            <span class="icon">📝</span>
            <span class="label">分析结论</span>
        </div>
        <div class="message-content markdown-content"></div>
    `;
    chat.appendChild(div);
    chat.scrollTop = chat.scrollHeight;
}

function appendAgentConclusion(content) {
    const conclusionDiv = document.getElementById('agent-conclusion');
    if (conclusionDiv) {
        conclusionDiv.querySelector('.markdown-content').innerHTML += formatMarkdown(content);
    }
}

function finalizeAgentConclusion() {
    const conclusionDiv = document.getElementById('agent-conclusion');
    if (conclusionDiv) {
        conclusionDiv.id = '';
        showAgentFeedback();
    }
}

// ==================== 变更类操作审批 ====================

function renderAgentApproval(event) {
    const chat = document.getElementById('agent-chat');
    const plan = event.plan || {};
    const ops = plan.operations || [];

    const div = document.createElement('div');
    div.className = 'agent-message approval';
    div.id = `agent-approval-${event.plan_id}`;
    div.dataset.planId = event.plan_id;

    const opsHtml = ops.map((op, i) => {
        const params = op.parameters || {};
        const paramText = op.tool === 'execute_command'
            ? (params.command || '')
            : (params.sql || '');
        const riskClass = `risk-${(op.risk || 'low').toLowerCase()}`;
        return `
            <div class="plan-op" data-op="${i + 1}">
                <span class="op-index">${i + 1}</span>
                <span class="op-tool">${escapeHtml(op.tool || '')}</span>
                <code class="op-params">${escapeHtml(paramText)}</code>
                <div class="op-meta">
                    <span class="op-impact">${escapeHtml(op.impact || '')}</span>
                    <span class="op-risk ${riskClass}">${escapeHtml(op.risk || 'low')}</span>
                </div>
                <span class="op-status"></span>
            </div>`;
    }).join('');

    div.innerHTML = `
        <div class="message-header">
            <span class="icon">🧾</span>
            <span class="label">操作计划待审批</span>
        </div>
        <div class="message-content">
            <div class="plan-title">${escapeHtml(plan.title || '操作计划')}</div>
            ${plan.scope ? `<div class="plan-scope">🎯 影响范围：${escapeHtml(plan.scope)}</div>` : ''}
            <div class="plan-ops">${opsHtml || '<div class="empty-message">计划无操作项</div>'}</div>
            ${plan.rollback ? `<div class="plan-rollback">↩️ 回滚：${escapeHtml(plan.rollback)}</div>` : ''}
            <div class="plan-actions">
                <button class="btn btn-primary" onclick="approvePlan(${event.plan_id}, 'approve')">✅ 批准</button>
                <button class="btn btn-danger" onclick="approvePlan(${event.plan_id}, 'reject')">❌ 拒绝</button>
            </div>
        </div>
    `;
    chat.appendChild(div);
    chat.scrollTop = chat.scrollHeight;
}

async function approvePlan(planId, action) {
    let comment = '';
    if (action === 'reject') {
        comment = prompt('请输入拒绝原因（可选）：') || '';
    }
    const box = document.getElementById(`agent-approval-${planId}`);
    try {
        const response = await fetch('/api/agent/approve', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ plan_id: planId, action, comment })
        });
        const data = await response.json();
        if (!response.ok) {
            showToast(data.error || '审批提交失败', 'error');
            return;
        }
        showToast(data.message || '审批已提交', 'success');
        if (box) {
            const header = box.querySelector('.message-header .label');
            const actions = box.querySelector('.plan-actions');
            if (actions) actions.innerHTML = '<span class="approval-waiting">⏳ 等待执行...</span>';
            if (header) header.textContent = action === 'approve' ? '✅ 已批准，执行中' : '❌ 已拒绝';
        }
    } catch (error) {
        showToast('审批提交失败', 'error');
    }
}

function renderAgentApprovalGranted(event) {
    const box = document.getElementById(`agent-approval-${event.plan_id}`);
    if (!box) return;
    const header = box.querySelector('.message-header .label');
    if (header) header.textContent = '✅ 已批准，开始执行';
    const actions = box.querySelector('.plan-actions');
    if (actions) actions.remove();
}

function renderAgentApprovalRejected(event) {
    const box = document.getElementById(`agent-approval-${event.plan_id}`);
    if (!box) return;
    const header = box.querySelector('.message-header .label');
    if (header) header.textContent = '❌ 已拒绝';
    const actions = box.querySelector('.plan-actions');
    if (actions) actions.remove();
    const content = box.querySelector('.message-content');
    if (content && event.comment) {
        content.insertAdjacentHTML('beforeend', `<div class="plan-reject-comment">拒绝原因：${escapeHtml(event.comment)}</div>`);
    }
}

function renderAgentApprovalExpired(event) {
    const box = document.getElementById(`agent-approval-${event.plan_id}`);
    if (!box) return;
    const header = box.querySelector('.message-header .label');
    if (header) header.textContent = '⏰ 审批超时';
    const actions = box.querySelector('.plan-actions');
    if (actions) actions.remove();
}

function renderPlanOperationResult(event) {
    const box = document.getElementById(`agent-approval-${event.plan_id}`);
    if (!box) return;
    const opRow = box.querySelector(`.plan-op[data-op="${event.index}"]`);
    if (!opRow) return;
    const statusEl = opRow.querySelector('.op-status');
    const result = event.result || {};

    if (event.status === 'success') {
        opRow.classList.add('op-success');
        if (statusEl) statusEl.textContent = '✅';
        let summary = '';
        if (result.row_count !== undefined) summary = `${result.row_count} 行`;
        else if (result.stdout !== undefined) summary = '已执行';
        if (summary && statusEl) statusEl.textContent = `✅ ${summary}`;
    } else if (event.status === 'error') {
        opRow.classList.add('op-error');
        if (statusEl) statusEl.textContent = '❌';
        const errMsg = (result.error || '') || (event.error || '');
        if (errMsg) {
            opRow.insertAdjacentHTML('beforeend', `<div class="op-error-msg">${escapeHtml(errMsg)}</div>`);
        }
    } else if (event.status === 'rejected') {
        opRow.classList.add('op-error');
        if (statusEl) statusEl.textContent = '⛔';
        if (event.error) {
            opRow.insertAdjacentHTML('beforeend', `<div class="op-error-msg">${escapeHtml(event.error)}</div>`);
        }
    }
}

// ==================== DBA 反馈闭环 ====================

function showAgentFeedback() {
    const conclusionDiv = document.getElementById('agent-conclusion');
    if (!conclusionDiv || !agentCurrentSession) return;
    if (conclusionDiv.querySelector('.agent-feedback')) return;

    const row = document.createElement('div');
    row.className = 'agent-feedback';
    row.innerHTML = `
        <div class="feedback-actions">
            <span class="feedback-label">这个结论对你有帮助吗？</span>
            <button class="feedback-btn" onclick="submitAgentFeedback('up')">👍 有帮助</button>
            <button class="feedback-btn" onclick="showAgentFeedbackCorrection()">👎 有误/需纠正</button>
        </div>
        <div class="feedback-correction" style="display:none;">
            <input type="text" id="agent-feedback-correction-input" placeholder="补充或纠正（可选），写入长期记忆">
            <button class="feedback-btn primary" onclick="submitAgentFeedback('down')">提交</button>
        </div>
    `;
    conclusionDiv.appendChild(row);
    conclusionDiv.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

function showAgentFeedbackCorrection() {
    const correction = document.querySelector('.agent-feedback .feedback-correction');
    if (correction) correction.style.display = 'flex';
}

async function submitAgentFeedback(feedback) {
    const input = document.getElementById('agent-feedback-correction-input');
    const correction = input ? input.value.trim() : '';
    try {
        const response = await fetch('/api/agent/feedback', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ session_id: agentCurrentSession, feedback, correction })
        });
        const data = await response.json();
        if (response.ok) {
            showToast(data.message || '反馈已记录', 'success');
            document.querySelectorAll('.agent-feedback .feedback-btn').forEach(b => b.disabled = true);
        } else {
            showToast(data.error || '反馈失败', 'error');
        }
    } catch (error) {
        showToast('反馈失败', 'error');
    }
}

function renderAgentError(error) {
    const chat = document.getElementById('agent-chat');
    const div = document.createElement('div');
    div.className = 'agent-message error';
    div.innerHTML = `
        <div class="message-header">
            <span class="icon">❌</span>
            <span class="label">错误</span>
        </div>
        <div class="message-content">
            <div class="error-box">${escapeHtml(error)}</div>
        </div>
    `;
    chat.appendChild(div);
    chat.scrollTop = chat.scrollHeight;
}

function renderAgentWarning(warning) {
    const chat = document.getElementById('agent-chat');
    const div = document.createElement('div');
    div.className = 'agent-message warning';
    div.innerHTML = `
        <div class="message-header">
            <span class="icon">⚠️</span>
            <span class="label">警告</span>
        </div>
        <div class="message-content">
            <div class="warning-box">${escapeHtml(warning)}</div>
        </div>
    `;
    chat.appendChild(div);
    chat.scrollTop = chat.scrollHeight;
}

function showAgentLoading(message) {
    const chat = document.getElementById('agent-chat');
    const div = document.createElement('div');
    div.className = 'agent-message loading';
    div.innerHTML = `
        <div class="message-content">
            <div class="loading-spinner"></div>
            <span>${escapeHtml(message)}</span>
        </div>
    `;
    chat.appendChild(div);
    chat.scrollTop = chat.scrollHeight;
}

function removeAgentLoading() {
    const chat = document.getElementById('agent-chat');
    chat.querySelectorAll('.agent-message.loading').forEach(el => el.remove());
}

// ==================== 工具函数 ====================
function clearAgentChat() {
    const chat = document.getElementById('agent-chat');
    chat.innerHTML = `
        <div class="agent-welcome">
            <div class="welcome-icon">🤖</div>
            <div class="welcome-title">智能运维Agent</div>
            <div class="welcome-desc">
                我可以帮你执行数据库运维任务，包括：<br>
                • 查询数据库状态<br>
                • 分析性能问题<br>
                • 检查集群健康<br>
                • 诊断慢查询<br><br>
                <span class="welcome-warning">⚠️ 所有操作均为只读，不会修改数据</span>
            </div>
        </div>
    `;
}

function renderAgentStep(step) {
    // 持久化的 action 是 JSON 字符串，先解析
    if (typeof step.action === 'string' && step.action) {
        try {
            step.action = JSON.parse(step.action);
        } catch (e) {
            step.action = null;
        }
    }

    // 渲染历史步骤
    switch (step.phase) {
        case 'thinking':
            showAgentThinking(step.step_number);
            appendAgentThinking(step.thought || '');
            finalizeAgentThinking();
            break;
        case 'executing':
            if (step.action) {
                renderAgentToolCall(step.action.tool, step.action.parameters || {});
            }
            if (step.observation) {
                renderAgentObservation(step.observation);
            }
            break;
        case 'concluding':
            showAgentConclusion();
            appendAgentConclusion(step.thought || '');
            finalizeAgentConclusion();
            break;
    }
}

function showAddSSHDialog() {
    document.getElementById('modal-add-ssh').style.display = 'flex';
}

function showAddDBDialog() {
    document.getElementById('modal-add-db').style.display = 'flex';
}

// 保存SSH连接
async function saveSSHConnection() {
    const name = document.getElementById('agent-ssh-name').value.trim();
    const host = document.getElementById('agent-ssh-host').value.trim();
    const port = document.getElementById('agent-ssh-port').value;
    const username = document.getElementById('agent-ssh-username').value.trim();
    const authType = document.getElementById('agent-ssh-auth-type').value;
    const password = document.getElementById('agent-ssh-password').value;
    const privateKey = document.getElementById('agent-ssh-private-key').value;
    const passphrase = document.getElementById('agent-ssh-passphrase').value;
    const dbType = document.getElementById('agent-ssh-db-type').value;

    if (!name || !host || !username) {
        showToast('请填写名称、主机和用户名', 'warning');
        return;
    }
    if (authType === 'password' && !password) {
        showToast('密码认证需要填写密码', 'warning');
        return;
    }
    if (authType === 'key' && !privateKey) {
        showToast('密钥认证需要填写私钥', 'warning');
        return;
    }

    try {
        const response = await fetch('/api/agent/ssh-connections', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                name, host, port: parseInt(port) || 22, username,
                auth_type: authType, password, private_key: privateKey,
                passphrase, db_type: dbType, os_type: 'linux'
            })
        });
        const data = await response.json();
        if (response.ok) {
            showToast('SSH连接添加成功', 'success');
            closeModal('modal-add-ssh');
            loadAgentSSHConnections();
        } else {
            showToast(data.error || '添加失败', 'error');
        }
    } catch (error) {
        showToast('添加失败', 'error');
    }
}

// 保存数据库连接
async function saveDBConnection() {
    const name = document.getElementById('agent-db-name').value.trim();
    const dbType = document.getElementById('agent-db-type').value;
    const host = document.getElementById('agent-db-host').value.trim();
    const port = document.getElementById('agent-db-port').value;
    const username = document.getElementById('agent-db-username').value.trim();
    const password = document.getElementById('agent-db-password').value;
    const database = document.getElementById('agent-db-database').value.trim();
    const sid = document.getElementById('agent-db-sid').value.trim();
    const serviceName = document.getElementById('agent-db-service-name').value.trim();

    if (!name || !dbType || !host) {
        showToast('请填写名称、数据库类型和主机', 'warning');
        return;
    }

    try {
        const response = await fetch('/api/agent/db-connections', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                name, db_type: dbType, host, port: parseInt(port) || 3306,
                username, password, database, sid, service_name: serviceName
            })
        });
        const data = await response.json();
        if (response.ok) {
            showToast('数据库连接添加成功', 'success');
            closeModal('modal-add-db');
            loadAgentDBConnections();
        } else {
            showToast(data.error || '添加失败', 'error');
        }
    } catch (error) {
        showToast('添加失败', 'error');
    }
}

function formatTime(timestamp) {
    if (!timestamp) return '';
    const date = new Date(timestamp);
    return date.toLocaleString('zh-CN');
}

// ==================== 知识沉淀（技能库 + 长期记忆） ====================

function switchKnowledgeTab(tab) {
    document.querySelectorAll('.knowledge-tabs .tab-btn').forEach(btn => {
        btn.classList.remove('active');
    });
    document.querySelector(`.knowledge-tabs .tab-btn[data-tab="${tab}"]`)?.classList.add('active');
    document.getElementById('agent-skill-panel').style.display = tab === 'skill' ? 'block' : 'none';
    document.getElementById('agent-memory-panel').style.display = tab === 'memory' ? 'block' : 'none';
    if (tab === 'skill') {
        loadAgentSkills();
    } else {
        loadAgentMemory();
    }
}

// ---- 技能库 ----

async function loadAgentSkills() {
    const container = document.getElementById('agent-skill-list');
    if (!container) return;
    try {
        const response = await fetch('/api/agent/skills');
        const data = await response.json();
        // 只展示 DB 沉淀/维护技能（内置技能无 usage_count 字段，不可删改）
        const skills = (data.skills || []).filter(s => s.usage_count !== undefined);
        renderAgentSkills(skills);
    } catch (error) {
        container.innerHTML = '<div class="empty-message">技能加载失败</div>';
    }
}

function renderAgentSkills(skills) {
    const container = document.getElementById('agent-skill-list');
    if (skills.length === 0) {
        container.innerHTML = '<div class="empty-message">暂无沉淀技能，成功诊断后会自动生成</div>';
        return;
    }
    container.innerHTML = skills.map(s => `
        <div class="connection-item">
            <div class="conn-name">${escapeHtml(s.name)}
                <span class="conn-type">${escapeHtml(s.db_type || '通用')}</span>
                <span class="tag-badge">${escapeHtml(s.category || 'diagnosis')}</span>
            </div>
            <div class="conn-info">
                <span class="conn-host">${escapeHtml((s.description || '').slice(0, 24))}</span>
                <span class="conn-type">使用${s.usage_count || 0}次</span>
                <span class="conn-status">${s.status === 'deprecated' ? '⚪已停用' : '🟢'}</span>
            </div>
            <div class="conn-info">
                <span class="conn-host" style="color:#e74c3c;cursor:pointer" onclick="deleteAgentSkill('${escapeJsAttr(s.name)}')">🗑 删除</span>
            </div>
        </div>
    `).join('');
}

async function deleteAgentSkill(name) {
    if (!confirm(`确定删除技能「${name}」？`)) return;
    try {
        const response = await fetch(`/api/agent/skills/${encodeURIComponent(name)}`, { method: 'DELETE' });
        const data = await response.json();
        if (response.ok) {
            showToast(data.message || '删除成功', 'success');
            loadAgentSkills();
        } else {
            showToast(data.error || '删除失败', 'error');
        }
    } catch (error) {
        showToast('删除失败', 'error');
    }
}

async function uploadDocSkill(input) {
    const file = input.files[0];
    if (!file) return;
    const btn = document.querySelector('#agent-skill-panel .btn-add[onclick*="doc-input"]');
    if (btn) btn.textContent = '⏳ 生成中...';
    const formData = new FormData();
    formData.append('file', file);
    formData.append('category', 'diagnosis');
    try {
        const response = await fetch('/api/agent/skills/from-doc', {
            method: 'POST',
            body: formData
        });
        const data = await response.json();
        if (response.ok) {
            showToast(`${data.message}：${data.skill_name}`, 'success');
        } else {
            showToast(data.error || '生成失败', 'error');
        }
    } catch (error) {
        showToast('生成失败', 'error');
    } finally {
        if (btn) btn.textContent = '📄 从手册生成';
        input.value = '';
        loadAgentSkills();
    }
}

function showAddSkillDialog() {
    document.getElementById('agent-skill-name').value = '';
    document.getElementById('agent-skill-dbtype').value = '';
    document.getElementById('agent-skill-category').value = 'diagnosis';
    document.getElementById('agent-skill-desc').value = '';
    document.getElementById('agent-skill-keywords').value = '';
    document.getElementById('agent-skill-template').value = '';
    document.getElementById('modal-add-skill').style.display = 'flex';
}

async function saveAgentSkill() {
    const name = document.getElementById('agent-skill-name').value.trim();
    if (!name) {
        showToast('技能名称不能为空', 'error');
        return;
    }
    const keywords = document.getElementById('agent-skill-keywords').value
        .split(/[,，]/).map(k => k.trim()).filter(Boolean);
    const payload = {
        name,
        db_type: document.getElementById('agent-skill-dbtype').value.trim() || null,
        category: document.getElementById('agent-skill-category').value,
        description: document.getElementById('agent-skill-desc').value.trim(),
        trigger_keywords: keywords,
        prompt_template: document.getElementById('agent-skill-template').value.trim(),
        status: 'active'
    };
    try {
        const response = await fetch('/api/agent/skills', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        const data = await response.json();
        if (response.ok) {
            showToast(data.message || '保存成功', 'success');
            closeModal('modal-add-skill');
            loadAgentSkills();
        } else {
            showToast(data.error || '保存失败', 'error');
        }
    } catch (error) {
        showToast('保存失败', 'error');
    }
}

// ---- 长期记忆 ----

async function loadAgentMemory() {
    const container = document.getElementById('agent-memory-list');
    if (!container) return;
    try {
        const response = await fetch('/api/agent/memory');
        const data = await response.json();
        renderAgentMemory(data.memory || []);
    } catch (error) {
        container.innerHTML = '<div class="empty-message">记忆加载失败</div>';
    }
}

function renderAgentMemory(memory) {
    const container = document.getElementById('agent-memory-list');
    if (memory.length === 0) {
        container.innerHTML = '<div class="empty-message">暂无长期记忆</div>';
        return;
    }
    container.innerHTML = memory.map(m => `
        <div class="connection-item">
            <div class="conn-name">${escapeHtml(m.entity_name || '通用')}
                <span class="conn-type">${escapeHtml(m.entity_type || 'general')}</span>
                <span class="tag-badge">${Math.round((m.confidence || 0) * 100)}%</span>
            </div>
            <div class="conn-info">
                <span class="conn-host">${escapeHtml((m.fact || '').slice(0, 30))}</span>
            </div>
            <div class="conn-info">
                <span class="conn-host" style="opacity:0.6">${escapeHtml(m.source || '')}</span>
                <span class="conn-type">使用${m.usage_count || 0}次</span>
                <span class="conn-host" style="color:#e74c3c;cursor:pointer" onclick="deleteAgentMemory(${m.id})">🗑 删除</span>
            </div>
        </div>
    `).join('');
}

async function deleteAgentMemory(id) {
    if (!confirm('确定删除这条记忆？')) return;
    try {
        const response = await fetch(`/api/agent/memory/${id}`, { method: 'DELETE' });
        const data = await response.json();
        if (response.ok) {
            showToast(data.message || '删除成功', 'success');
            loadAgentMemory();
        } else {
            showToast(data.error || '删除失败', 'error');
        }
    } catch (error) {
        showToast('删除失败', 'error');
    }
}

function showAddMemoryDialog() {
    document.getElementById('agent-memory-etype').value = 'db_instance';
    document.getElementById('agent-memory-ename').value = '';
    document.getElementById('agent-memory-fact').value = '';
    document.getElementById('modal-add-memory').style.display = 'flex';
}

async function saveAgentMemory() {
    const fact = document.getElementById('agent-memory-fact').value.trim();
    if (!fact) {
        showToast('记忆内容不能为空', 'error');
        return;
    }
    const payload = {
        entity_type: document.getElementById('agent-memory-etype').value,
        entity_name: document.getElementById('agent-memory-ename').value.trim(),
        fact
    };
    try {
        const response = await fetch('/api/agent/memory', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        const data = await response.json();
        if (response.ok) {
            showToast(data.message || '记录成功', 'success');
            closeModal('modal-add-memory');
            loadAgentMemory();
        } else {
            showToast(data.error || '记录失败', 'error');
        }
    } catch (error) {
        showToast('记录失败', 'error');
    }
}
