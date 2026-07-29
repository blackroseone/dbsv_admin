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

// ==================== 模块初始化 ====================
function initAgentModule() {
    loadAgentSSHConnections();
    loadAgentDBConnections();
    loadAgentSessions();
}

// ==================== 连接管理 ====================
async function loadAgentSSHConnections() {
    try {
        const response = await fetch('/api/agent/ssh-connections');
        const data = await response.json();
        agentSSHConnections = data.connections || [];
        renderAgentSSHConnections();
    } catch (error) {
        console.error('加载SSH连接失败:', error);
    }
}

async function loadAgentDBConnections() {
    try {
        const response = await fetch('/api/agent/db-connections');
        const data = await response.json();
        agentDBConnections = data.connections || [];
        renderAgentDBConnections();
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
             onclick="selectSSHConnection('${conn.id}')">
            <div class="conn-name">${escapeHtml(conn.name)}</div>
            <div class="conn-info">
                <span class="conn-host">${escapeHtml(conn.host)}:${conn.port}</span>
                <span class="conn-type">${conn.db_type}</span>
                <span class="conn-status ${conn.status}">${conn.status === 'active' ? '🟢' : '🔴'}</span>
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
             onclick="selectDBConnection('${conn.id}')">
            <div class="conn-name">${escapeHtml(conn.name)}</div>
            <div class="conn-info">
                <span class="conn-host">${escapeHtml(conn.host)}</span>
                <span class="conn-type">${conn.db_type}</span>
                <span class="conn-status ${conn.status}">${conn.status === 'active' ? '🟢' : '🔴'}</span>
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
             onclick="loadAgentSession('${session.id}')">
            <div class="session-title">${escapeHtml(session.title)}</div>
            <div class="session-meta">
                <span class="session-status ${session.status}">${getStatusIcon(session.status)}</span>
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
        showToast('请先选择SSH或数据库连接', 'warning');
        return;
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
        if (data.steps) {
            data.steps.forEach(step => {
                renderAgentStep(step);
            });
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

    // 添加用户消息
    addAgentMessage('user', question);
    input.value = '';

    agentIsRunning = true;

    try {
        const response = await fetch('/api/agent/run', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                session_id: agentCurrentSession,
                question: question
            })
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
        console.error('Agent执行失败:', error);
        addAgentMessage('error', `执行失败: ${error.message}`);
    } finally {
        agentIsRunning = false;
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
                <span class="ref-similarity">相似度: ${ref.similarity}</span>
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
        <div class="message-header">
            <span class="icon">🤔</span>
            <span class="label">思考中</span>
            <span class="thinking-indicator"></span>
        </div>
        <div class="message-content">
            <pre class="thinking-content"></pre>
        </div>
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
        <div class="message-header">
            <span class="icon">🔧</span>
            <span class="label">执行: ${escapeHtml(tool)}</span>
        </div>
        <div class="message-content">
            <div class="tool-params">
                <pre><code>${escapeHtml(JSON.stringify(params, null, 2))}</code></pre>
            </div>
            <div class="tool-status">执行中...</div>
        </div>
    `;
    chat.appendChild(div);
    chat.scrollTop = chat.scrollHeight;
}

function renderAgentResult(result) {
    const toolDiv = document.querySelector('.agent-message.tool:last-child');
    if (toolDiv) {
        const statusDiv = toolDiv.querySelector('.tool-status');
        statusDiv.innerHTML = '<span class="status-success">✅ 完成</span>';

        if (result.rows && result.columns) {
            const resultDiv = document.createElement('div');
            resultDiv.className = 'tool-result';
            resultDiv.innerHTML = `
                <details>
                    <summary>查看结果 (${result.rows.length} 行)</summary>
                    <div class="result-table-wrapper">
                        <table class="result-table">
                            <thead>
                                <tr>${result.columns.map(c => `<th>${escapeHtml(c)}</th>`).join('')}</tr>
                            </thead>
                            <tbody>
                                ${result.rows.map(row => `
                                    <tr>${row.map(cell => `<td>${escapeHtml(String(cell))}</td>`).join('')}</tr>
                                `).join('')}
                            </tbody>
                        </table>
                    </div>
                </details>
            `;
            toolDiv.querySelector('.message-content').appendChild(resultDiv);
        }
    }
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
    // 渲染历史步骤
    switch (step.phase) {
        case 'thinking':
            showAgentThinking(step.step_number);
            appendAgentThinking(step.thought);
            finalizeAgentThinking();
            break;
        case 'executing':
            if (step.action) {
                renderAgentToolCall(step.action.tool, step.action.parameters);
            }
            if (step.observation) {
                renderAgentObservation(step.observation);
            }
            break;
        case 'concluding':
            showAgentConclusion();
            appendAgentConclusion(step.thought);
            finalizeAgentConclusion();
            break;
    }
}

function showAddSSHDialog() {
    // TODO: 实现添加SSH连接对话框
    showToast('添加SSH连接功能开发中', 'info');
}

function showAddDBDialog() {
    // TODO: 实现添加DB连接对话框
    showToast('添加DB连接功能开发中', 'info');
}

function formatTime(timestamp) {
    if (!timestamp) return '';
    const date = new Date(timestamp);
    return date.toLocaleString('zh-CN');
}
