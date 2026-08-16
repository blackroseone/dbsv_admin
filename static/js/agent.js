/**
 * 智能运维Agent模块（页签模式：每会话一个页签、独立视图，SSE 流只写所属会话视图）
 */

// ==================== Agent模块状态 ====================
let agentCurrentSession = null;      // 当前激活页签的会话 id
let agentSSHConnections = [];
let agentDBConnections = [];
let agentSessions = [];
let agentCurrentSSHConn = null;
let agentCurrentDBConn = null;
// 打开的页签（有序）
let agentOpenTabs = [];
// 每会话视图状态：{sid: {running, controller, thinkingText, conclusionText, lastPlan, loaded}}
let agentSessionViews = {};
// v4.0 操作范围：勾选的拓扑节点 targets + 解析结果缓存 + 拓扑树缓存
let agentScopeTargets = [];            // [{type:'ssh'|'db', topo_id, conn_id, name}]
let agentScopeTree = [];               // /api/topology/clusters 返回的池树
let agentScopeResolve = {};            // {`${type}:${topo_id}`: resolvedNode}
let agentScopeMixed = false;           // 勾选是否混型 db_type

// ==================== 模块初始化 ====================
function initAgentModule() {
    restoreAgentScopeTargets();
    loadAgentScopeTree();
    loadAgentSSHConnections();
    loadAgentDBConnections();
    loadAgentSessions();
    loadAgentSkills();
    loadAgentMemory();
}

// ==================== 操作范围面板（v4.0 多节点批量） ====================
function restoreAgentScopeTargets() {
    try {
        const saved = localStorage.getItem('agentScopeTargets');
        agentScopeTargets = saved ? (JSON.parse(saved) || []) : [];
    } catch (e) {
        agentScopeTargets = [];
    }
}

async function loadAgentScopeTree() {
    const panel = document.getElementById('agent-scope-panel');
    if (!panel) return;
    try {
        const resp = await fetch('/api/topology/clusters');
        const data = await resp.json();
        agentScopeTree = (data.clusters || []) || [];
    } catch (e) {
        console.error('加载拓扑资源池失败:', e);
        agentScopeTree = [];
    }
    renderAgentScopeTree();
    refreshAgentScopeResolve();
}

// 批量解析范围内所有拓扑节点的连接状态，刷新 ✅/⚠️ 徽标
async function refreshAgentScopeResolve() {
    const targets = [];
    (agentScopeTree || []).forEach(pool => {
        (pool.servers || []).forEach(s => {
            targets.push({ type: 'ssh', topo_id: s.id, name: s.name });
            (s.instances || []).forEach(i => targets.push({ type: 'db', topo_id: i.id, name: i.name }));
        });
    });
    if (targets.length === 0) return;
    try {
        const resp = await fetch('/api/agent/scope/resolve', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ targets })
        });
        const data = await resp.json();
        agentScopeResolve = {};
        (data.nodes || []).forEach(n => {
            if (n.topo_id) agentScopeResolve[n.type + ':' + n.topo_id] = n;
        });
        agentScopeMixed = !!data.mixed;
    } catch (e) {
        agentScopeResolve = {};
    }
    renderAgentScopeTree();
    updateAgentScopeCount();
}

function renderAgentScopeTree() {
    const panel = document.getElementById('agent-scope-panel');
    if (!panel) return;
    if (!agentScopeTree || agentScopeTree.length === 0) {
        panel.innerHTML = '<div class="empty-message">暂无资源池，请先在「拓扑」模块添加</div>';
        return;
    }

    panel.innerHTML = agentScopeTree.map(pool => {
        const servers = (pool.servers || []).map(s => {
            const sKey = 'ssh:' + s.id;
            const st = agentScopeTargets.find(t => t.type === 'ssh' && t.topo_id === s.id);
            const status = agentScopeResolve[sKey];
            const badge = scopeBadgeHtml(status);
            const cfg = badge && (!status || !status.resolved)
                ? `<button class="scope-config-btn" onclick="quickConfigAgentNode('${escapeJsAttr(s.id)}','ssh')">配置</button>` : '';
            const instances = (s.instances || []).map(i => {
                const iKey = 'db:' + i.id;
                const it = agentScopeTargets.find(t => t.type === 'db' && t.topo_id === i.id);
                const ist = agentScopeResolve[iKey];
                const ibadge = scopeBadgeHtml(ist);
                const icfg = ibadge && (!ist || !ist.resolved)
                    ? `<button class="scope-config-btn" onclick="quickConfigAgentNode('${escapeJsAttr(i.id)}','db')">配置</button>` : '';
                return `<label class="scope-node scope-instance">
                    <input type="checkbox" data-target-key="${iKey}" ${it ? 'checked' : ''}>
                    <span class="scope-node-name">${escapeHtml(i.name)}</span>
                    <span class="scope-node-meta">:${escapeHtml(i.port || '')}</span>${ibadge}${icfg}
                </label>`;
            }).join('');
            return `<div class="scope-server">
                <label class="scope-node scope-server-row">
                    <input type="checkbox" data-target-key="${sKey}" ${st ? 'checked' : ''}>
                    <span class="scope-node-name">${escapeHtml(s.name)}</span>
                    <span class="scope-node-meta">${escapeHtml(s.host || '')}</span>${badge}${cfg}
                </label>
                ${instances ? `<div class="scope-instances">${instances}</div>` : ''}
            </div>`;
        }).join('');

        const poolServers = (pool.servers || []);
        const checkedServers = poolServers.filter(s =>
            agentScopeTargets.find(t => t.type === 'ssh' && t.topo_id === s.id)).length;
        const poolAll = poolServers.length > 0 && checkedServers === poolServers.length;
        return `<div class="scope-pool">
            <label class="scope-pool-header">
                <input type="checkbox" data-pool-key="pool:${pool.id}" ${poolAll ? 'checked' : ''}>
                <span class="scope-pool-name">${escapeHtml(pool.name)}</span>
                <span class="scope-pool-dbtype">${escapeHtml(pool.db_type || '')}</span>
            </label>
            <div class="scope-servers">${servers}</div>
        </div>`;
    }).join('') + (agentScopeMixed
        ? '<div class="scope-mixed-warning">⚠️ 已选混合数据库类型，批量 SQL 需按各节点方言适配</div>'
        : '');

    panel.onchange = onAgentScopeChange;
}

// 根据解析状态生成徽标 HTML（resolved→✅；ambiguous→多匹配；未配置→未配置）
function scopeBadgeHtml(status) {
    if (!status) return '';
    if (status.resolved) return '<span class="scope-badge ok">✅</span>';
    return status.ambiguous
        ? '<span class="scope-badge warn">⚠️多匹配</span>'
        : '<span class="scope-badge warn">⚠️未配置</span>';
}

function onAgentScopeChange(e) {
    const cb = e.target;
    const poolKey = cb.dataset.poolKey;
    const targetKey = cb.dataset.targetKey;
    if (poolKey) {
        const poolId = poolKey.split(':')[1];
        const pool = (agentScopeTree || []).find(p => p.id === poolId);
        if (!pool) return;
        (pool.servers || []).forEach(s => {
            setScopeTarget('ssh:' + s.id, cb.checked);
            (s.instances || []).forEach(i => setScopeTarget('db:' + i.id, cb.checked));
        });
    } else if (targetKey) {
        setScopeTarget(targetKey, cb.checked);
    }
    persistAgentScopeTargets();
    renderAgentScopeTree();
    updateAgentScopeCount();
}

function setScopeTarget(key, checked) {
    const [type, topoId] = key.split(':');
    const idx = agentScopeTargets.findIndex(t => t.type === type && t.topo_id === topoId);
    if (checked && idx === -1) {
        agentScopeTargets.push({ type, topo_id: topoId, conn_id: null, name: scopeTargetName(type, topoId) });
    } else if (!checked && idx !== -1) {
        agentScopeTargets.splice(idx, 1);
    }
}

function scopeTargetName(type, topoId) {
    for (const pool of agentScopeTree || []) {
        for (const s of pool.servers || []) {
            if (type === 'ssh' && s.id === topoId) return s.name;
            const i = (s.instances || []).find(x => x.id === topoId);
            if (type === 'db' && i) return i.name;
        }
    }
    return '';
}

function persistAgentScopeTargets() {
    try { localStorage.setItem('agentScopeTargets', JSON.stringify(agentScopeTargets)); } catch (e) {}
}

function updateAgentScopeCount() {
    const el = document.getElementById('agent-scope-count');
    if (!el) return;
    const ssh = agentScopeTargets.filter(t => t.type === 'ssh').length;
    const db = agentScopeTargets.filter(t => t.type === 'db').length;
    el.textContent = (ssh || db) ? `已选 ${ssh} 节点 · ${db} 实例` : '';
}

// 未配置连接的拓扑节点一键补配：预填 host/port/db_type/库，复用现有添加连接对话框
function quickConfigAgentNode(topoId, type) {
    const status = agentScopeResolve[type + ':' + topoId];
    const suggest = (status && status.suggest) || {};
    const nodeName = (status && status.name) || '';
    if (type === 'ssh') {
        if (suggest.host) document.getElementById('agent-ssh-host').value = suggest.host;
        if (suggest.port) document.getElementById('agent-ssh-port').value = suggest.port;
        if (suggest.db_type) document.getElementById('agent-ssh-db-type').value = suggest.db_type;
        document.getElementById('agent-ssh-name').value = nodeName ? nodeName + '-ssh' : '';
        showAddSSHDialog();
    } else {
        if (suggest.host) document.getElementById('agent-db-host').value = suggest.host;
        if (suggest.port) document.getElementById('agent-db-port').value = suggest.port;
        if (suggest.db_type) document.getElementById('agent-db-type').value = suggest.db_type;
        if (suggest.database) document.getElementById('agent-db-database').value = suggest.database || '';
        if (suggest.sid) document.getElementById('agent-db-sid').value = suggest.sid || '';
        if (suggest.service_name) document.getElementById('agent-db-service-name').value = suggest.service_name || '';
        document.getElementById('agent-db-name').value = nodeName || '';
        showAddDBDialog();
    }
}

// ==================== 收纳抽屉 + 管理页签（v4.0 信息层级精简） ====================
function toggleAgentHistoryDrawer() {
    const drawer = document.getElementById('agent-history-drawer');
    if (!drawer) return;
    const show = drawer.classList.toggle('open');
    const mgmt = document.getElementById('agent-manage-drawer');
    if (mgmt) mgmt.classList.remove('open');
    if (show) loadAgentSessions();
}

function toggleAgentManageDrawer() {
    const drawer = document.getElementById('agent-manage-drawer');
    if (!drawer) return;
    const show = drawer.classList.toggle('open');
    const hist = document.getElementById('agent-history-drawer');
    if (hist) hist.classList.remove('open');
    if (show) {
        loadAgentSSHConnections();
        loadAgentDBConnections();
        loadAgentSkills();
        loadAgentMemory();
    }
}

function switchManageTab(tab) {
    document.querySelectorAll('.manage-tabs .tab-btn').forEach(b => {
        b.classList.toggle('active', b.dataset.tab === tab);
    });
    ['conn', 'skill', 'memory'].forEach(t => {
        const el = document.getElementById(`agent-manage-${t}`);
        if (el) el.style.display = t === tab ? 'block' : 'none';
    });
}

// 工具栏范围徽标：当前激活会话是范围会话时显示「范围: N 节点 · M 实例」，否则回退 SSH/DB 状态
function updateAgentScopeBadge(sid) {
    const badge = document.getElementById('agent-scope-badge');
    const sshStatus = document.getElementById('agent-ssh-status');
    const dbStatus = document.getElementById('agent-db-status');
    if (!badge || !sshStatus || !dbStatus) return;
    const sc = sessionScopeCount(agentSessions.find(x => x.id === sid));
    if (sc.ssh + sc.db > 0) {
        badge.textContent = `🎯 范围: ${sc.ssh} 节点 · ${sc.db} 实例`;
        badge.style.display = '';
        sshStatus.style.display = 'none';
        dbStatus.style.display = 'none';
    } else {
        badge.style.display = 'none';
        sshStatus.style.display = '';
        dbStatus.style.display = '';
    }
}

function sessionScopeCount(session) {
    const out = { ssh: 0, db: 0 };
    if (!session || !session.scope_json) return out;
    try {
        (JSON.parse(session.scope_json) || []).forEach(t => {
            if (t.type === 'ssh') out.ssh++;
            else if (t.type === 'db') out.db++;
        });
    } catch (e) {}
    return out;
}

// ==================== 技能 chips（v4.0 手动技能选择） ====================
function sessionDbType(sid) {
    const s = agentSessions.find(x => x.id === sid);
    if (s && s.scope_json) {
        try {
            const targets = JSON.parse(s.scope_json) || [];
            const db = targets.find(t => t.type === 'db' && t.conn_id);
            if (db) {
                const c = agentDBConnections.find(x => x.id === db.conn_id);
                if (c) return c.db_type;
            }
        } catch (e) {}
    }
    const c = agentDBConnections.find(x => x.id === agentCurrentDBConn);
    return c ? c.db_type : '';
}

async function loadAgentSkillChips(sid) {
    const chips = document.getElementById(`agent-skill-chips-${sid}`);
    if (!chips) return;
    const dbType = sessionDbType(sid);
    let skills = [];
    try {
        const resp = await fetch(`/api/agent/skills${dbType ? '?db_type=' + encodeURIComponent(dbType) : ''}`);
        const data = await resp.json();
        skills = data.skills || [];
    } catch (e) {}
    const view = agentView(sid);
    const items = [{ name: '' }].concat(skills).map(sk => {
        const active = (view.selectedSkill || '') === (sk.name || '');
        return `<button class="skill-chip${active ? ' active' : ''}"
                onclick="selectAgentSkill('${escapeJsAttr(sid)}','${escapeJsAttr(sk.name || '')}')">${escapeHtml(sk.name || '自由对话')}</button>`;
    }).join('');
    chips.innerHTML = `<span class="chip-label">技能:</span>${items}`;
}

function selectAgentSkill(sid, name) {
    agentView(sid).selectedSkill = name || '';
    loadAgentSkillChips(sid);
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

// ==================== 会话列表（侧栏） ====================
async function loadAgentSessions() {
    try {
        const response = await fetch('/api/agent/sessions');
        const data = await response.json();
        agentSessions = data.sessions || [];
        renderAgentSessions();
        renderAgentTabs();  // 页签标题与会话列表同步（含自动命名后）
        // 首次进入且无页签时，自动打开最近一个会话
        if (agentOpenTabs.length === 0 && agentSessions.length > 0 && !agentCurrentSession) {
            openAgentTab(agentSessions[0].id);
        }
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

    container.innerHTML = agentSessions.map(session => {
        const sc = sessionScopeCount(session);
        const scBadge = (sc.ssh + sc.db > 0)
            ? `<span class="session-scope">范围:${sc.ssh}节点${sc.db ? `·${sc.db}实例` : ''}</span>` : '';
        return `
        <div class="session-item ${agentCurrentSession === session.id ? 'active' : ''}">
            <div class="session-main" onclick="openAgentTab('${escapeJsAttr(session.id)}')">
                <div class="session-title">${escapeHtml(session.title)}</div>
                <div class="session-meta">
                    <span class="session-status ${escapeHtml(session.status)}">${getStatusIcon(session.status)}</span>
                    ${scBadge}
                    <span class="session-time">${formatTime(session.created_at)}</span>
                </div>
            </div>
            <button class="session-delete" title="删除会话"
                    onclick="event.stopPropagation(); deleteAgentSession('${escapeJsAttr(session.id)}')">&times;</button>
        </div>`;
    }).join('');
}

async function deleteAgentSession(sessionId) {
    if (!confirm('确定删除该会话？该操作不可恢复。')) return;
    // 若已打开页签，先关闭（运行中会先停止）
    if (agentOpenTabs.includes(sessionId)) {
        await closeAgentTab(sessionId);
    }
    try {
        const response = await fetch(`/api/agent/sessions/${sessionId}`, { method: 'DELETE' });
        if (!response.ok) {
            const data = await response.json().catch(() => ({}));
            showToast(data.error || '删除失败', 'error');
            return;
        }
        loadAgentSessions();
        showToast('会话已删除', 'success');
    } catch (error) {
        console.error('删除会话失败:', error);
        showToast('删除失败', 'error');
    }
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

// ==================== 页签管理 ====================

function agentView(sid) {
    if (!agentSessionViews[sid]) {
        agentSessionViews[sid] = {
            running: false, controller: null,
            thinkingText: '', conclusionText: '',
            lastPlan: null, loaded: false,
            failedNodes: new Set(), selectedSkill: ''
        };
    }
    return agentSessionViews[sid];
}

function agentSessionTitle(sid) {
    const s = agentSessions.find(x => x.id === sid);
    return (s && s.title) || '会话';
}

// 打开会话页签（不存在则创建 pane + 加载历史），并激活
async function openAgentTab(sid) {
    const firstOpen = !agentSessionViews[sid] || !agentSessionViews[sid].loaded;
    if (!agentSessionViews[sid]) {
        createAgentPane(sid);
    }
    if (!agentOpenTabs.includes(sid)) {
        agentOpenTabs.push(sid);
    }
    activateAgentTab(sid);
    renderAgentTabs();
    if (firstOpen) {
        await loadAgentSessionHistory(sid);
        agentSessionViews[sid].loaded = true;
    }
}

function createAgentPane(sid) {
    const panes = document.getElementById('agent-tab-panes');
    if (!panes || document.querySelector(`.agent-tab-pane[data-session-id="${sid}"]`)) return;
    const pane = document.createElement('div');
    pane.className = 'agent-tab-pane';
    pane.dataset.sessionId = sid;
    pane.innerHTML = `
        <div class="agent-chat" id="agent-chat-${sid}"></div>
        <div class="agent-approval-slot" id="agent-approval-slot-${sid}"></div>
        <div class="agent-input-area" id="agent-input-area-${sid}">
            <div class="skill-chips" id="agent-skill-chips-${sid}"></div>
            <div class="input-wrapper">
                <input type="text" id="agent-input-${sid}" placeholder="输入指令，如：对所选节点批量查询参数"
                       onkeypress="if(event.key==='Enter')sendAgentQuestion('${escapeJsAttr(sid)}')">
                <button class="btn btn-primary" onclick="sendAgentQuestion('${escapeJsAttr(sid)}')">发送</button>
            </div>
            <div class="input-hints">
                <span>💡 试试：对所选节点批量查询 max_connections | 检查集群状态 | 分析慢 SQL</span>
            </div>
        </div>
    `;
    panes.appendChild(pane);
    clearAgentChat(sid);
    loadAgentSkillChips(sid);
}

async function loadAgentSessionHistory(sid) {
    try {
        const response = await fetch(`/api/agent/sessions/${sid}`);
        const data = await response.json();
        clearAgentChat(sid);
        if (data.steps && data.steps.length > 0) {
            data.steps.forEach(step => renderAgentStep(sid, step));
            const welcome = document.querySelector(`#agent-chat-${sid} .agent-welcome`);
            if (welcome) welcome.remove();
        }
    } catch (error) {
        console.error('加载会话失败:', error);
    }
}

function activateAgentTab(sid) {
    agentCurrentSession = sid;
    document.querySelectorAll('#agent-tab-panes .agent-tab-pane').forEach(p => {
        p.style.display = p.dataset.sessionId === sid ? 'flex' : 'none';
    });
    renderAgentTabs();
    renderAgentSessions();
    updateAgentStopButton();
    updateAgentScopeBadge(sid);
    loadAgentSkillChips(sid);
    const input = document.getElementById(`agent-input-${sid}`);
    if (input) input.focus();
}

async function closeAgentTab(sid) {
    const view = agentSessionViews[sid];
    if (view && view.running) {
        await stopAgent(sid);  // 运行中先停止
    }
    const pane = document.querySelector(`.agent-tab-pane[data-session-id="${sid}"]`);
    if (pane) pane.remove();
    agentOpenTabs = agentOpenTabs.filter(x => x !== sid);
    delete agentSessionViews[sid];
    if (agentCurrentSession === sid) {
        const next = agentOpenTabs[agentOpenTabs.length - 1] || null;
        if (next) {
            activateAgentTab(next);
        } else {
            agentCurrentSession = null;
            renderAgentTabs();
            renderAgentSessions();
            updateAgentStopButton();
        }
    }
    renderAgentTabs();
}

function renderAgentTabs() {
    const bar = document.getElementById('agent-tabs');
    if (!bar) return;
    bar.innerHTML = agentOpenTabs.map(sid => {
        const active = sid === agentCurrentSession ? ' active' : '';
        const sc = sessionScopeCount(agentSessions.find(x => x.id === sid));
        const scBadge = (sc.ssh + sc.db > 0) ? ` <span class="tab-scope">${sc.ssh + sc.db}</span>` : '';
        return `
            <div class="agent-tab${active}" title="${escapeHtml(agentSessionTitle(sid))}"
                 onclick="activateAgentTab('${escapeJsAttr(sid)}')">
                <span class="agent-tab-title">${escapeHtml(agentSessionTitle(sid))}${scBadge}</span>
                <span class="agent-tab-close" title="关闭页签"
                      onclick="event.stopPropagation(); closeAgentTab('${escapeJsAttr(sid)}')">&times;</span>
            </div>`;
    }).join('');
}

function updateAgentStopButton() {
    const stopBtn = document.getElementById('agent-stop-btn');
    if (!stopBtn) return;
    const view = agentSessionViews[agentCurrentSession];
    stopBtn.style.display = (view && view.running) ? 'inline-block' : 'none';
}

async function newAgentSession() {
    // v4.0：范围面板有勾选则建「范围会话」（多节点批量）；否则回退 legacy 单连接
    const body = { title: '新会话' };
    if (agentScopeTargets.length > 0) {
        body.scope = agentScopeTargets;
    } else {
        body.ssh_connection_id = agentCurrentSSHConn;
        body.db_connection_id = agentCurrentDBConn;
    }
    try {
        const response = await fetch('/api/agent/sessions', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body)
        });
        const data = await response.json();
        if (data.session) {
            await openAgentTab(data.session.id);
            loadAgentSessions();
            showToast('会话创建成功', 'success');
        } else {
            showToast('创建会话失败', 'error');
        }
    } catch (error) {
        console.error('创建会话失败:', error);
        showToast('创建会话失败', 'error');
    }
}

// ==================== 对话功能（按会话路由） ====================
async function sendAgentQuestion(sid) {
    const input = document.getElementById(`agent-input-${sid}`);
    if (!input) return;
    const question = input.value.trim();
    if (!question) return;
    const view = agentView(sid);
    if (view.running) {
        showToast('该会话正在执行中，请等待', 'warning');
        return;
    }

    // 开始对话后移除欢迎语
    const welcome = document.querySelector(`#agent-chat-${sid} .agent-welcome`);
    if (welcome) welcome.remove();

    addAgentMessage(sid, 'user', question);
    input.value = '';

    view.running = true;
    view.controller = new AbortController();
    view.failedNodes = new Set();   // 新一轮执行，重置失败节点收集
    updateAgentStopButton();

    try {
        const response = await fetch('/api/agent/run', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                session_id: sid,
                question,
                skill_name: view.selectedSkill || null   // v4.0 手动技能
            }),
            signal: view.controller.signal
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
                        handleAgentEvent(JSON.parse(data), sid);
                    } catch (e) {
                        console.error('解析SSE事件失败:', e);
                    }
                }
            }
        }
    } catch (error) {
        if (error.name === 'AbortError') {
            addAgentMessage(sid, 'error', '⏹ 已手动停止');
        } else {
            console.error('Agent执行失败:', error);
            addAgentMessage(sid, 'error', `执行失败: ${error.message}`);
        }
    } finally {
        const v = agentSessionViews[sid];
        if (v) { v.running = false; v.controller = null; }
        updateAgentStopButton();
        clearApprovalSlot(sid);  // 任何结束（done/取消/断开）都恢复输入框、清空审批槽
        loadAgentSessions();     // 刷新会话状态
    }
}

// 停止指定会话的执行：先通知后端取消（生成器下一轮收敛、会话置 cancelled），再断开流
async function stopAgent(sid) {
    const view = agentSessionViews[sid];
    if (!view || !view.controller) return;
    try {
        await fetch(`/api/agent/sessions/${sid}/stop`, { method: 'POST' });
    } catch (e) {
        // 后端通知失败不阻断前端断开
    }
    view.controller.abort();
}

function handleAgentEvent(event, sid) {
    switch (event.type) {
        case 'retrieving_start':
            showAgentLoading(sid, '正在检索知识库...');
            break;
        case 'knowledge_refs':
            renderKnowledgeRefs(sid, event.refs);
            break;
        case 'knowledge_warning':
            renderKnowledgeWarning(sid, event.message);
            break;
        case 'thinking_start':
            showAgentThinking(sid, event.step);
            break;
        case 'thinking_chunk':
            appendAgentThinking(sid, event.content);
            break;
        case 'thinking_end':
            finalizeAgentThinking(sid);
            break;
        case 'executing_start':
            renderAgentToolCall(sid, event.tool, event.parameters);
            break;
        case 'executing_end':
            renderAgentResult(sid, event.result);
            break;
        case 'executing_error':
            renderAgentError(sid, event.error);
            break;
        case 'executing_warning':
            renderAgentWarning(sid, event.warning);
            break;
        case 'observing':
            renderAgentObservation(sid, event.observation);
            break;
        case 'approval_required':
            renderAgentApproval(event, sid);
            break;
        case 'approval_granted':
            renderAgentApprovalGranted(event, sid);
            break;
        case 'approval_rejected':
            renderAgentApprovalRejected(event, sid);
            break;
        case 'approval_revised':
            renderAgentApprovalRevised(event, sid);
            break;
        case 'approval_expired':
            renderAgentApprovalExpired(event, sid);
            break;
        case 'plan_operation_result':
            renderPlanOperationResult(event, sid);
            break;
        case 'cancelled':
            removeAgentLoading(sid);
            clearApprovalSlot(sid);
            addAgentMessage(sid, 'error', '⏹ 已取消');
            break;
        case 'concluding_start':
            showAgentConclusion(sid);
            break;
        case 'concluding_chunk':
            appendAgentConclusion(sid, event.content);
            break;
        case 'concluding_end':
            finalizeAgentConclusion(sid);
            break;
        case 'final_thinking':
            // 未执行任何工具：最后的思考块即对用户的回应，展开为可见回复
            showAgentFinalThinking(sid);
            break;
        case 'error':
            renderAgentError(sid, event.message);
            break;
        case 'scope_extended':
            renderScopeExtended(sid, event.targets);
            break;
        case 'done':
            removeAgentLoading(sid);
            clearApprovalSlot(sid);
            maybeRenderRetryButton(sid);
            updateAgentScopeBadge(sid);
            break;
    }
}

// v4.0 范围扩展：审批通过后引擎发 scope_extended，前端提示 + 刷新范围徽标
function renderScopeExtended(sid, targets) {
    const names = (targets || []).map(t => t.name || t).filter(Boolean);
    if (names.length) {
        addAgentMessage(sid, 'assistant', `🎯 操作范围已扩展: +${names.join(', ')}`);
    }
    loadAgentSessions();   // 刷新会话列表/页签的范围徽标（范围已持久化）
    updateAgentScopeBadge(sid);
}

// ==================== 消息渲染（均按会话路由） ====================
function addAgentMessage(sid, role, content) {
    const chat = document.getElementById(`agent-chat-${sid}`);
    if (!chat) return;
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
    scrollAgentChatIfNearBottom(sid);
}

function renderKnowledgeRefs(sid, refs) {
    const chat = document.getElementById(`agent-chat-${sid}`);
    if (!chat) return;
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
    scrollAgentChatIfNearBottom(sid);
}

function renderKnowledgeWarning(sid, message) {
    const chat = document.getElementById(`agent-chat-${sid}`);
    if (!chat) return;
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
    scrollAgentChatIfNearBottom(sid);
}

function showAgentThinking(sid, step) {
    const chat = document.getElementById(`agent-chat-${sid}`);
    if (!chat) return;
    const view = agentView(sid);
    view.thinkingText = '';
    const div = document.createElement('div');
    div.className = 'agent-message thinking';
    div.id = `agent-thinking-${sid}-${step}`;
    div.innerHTML = `
        <details class="agent-collapse">
            <summary class="message-header">
                <span class="icon">🤔</span>
                <span class="label">思考中</span>
                <span class="thinking-indicator"></span>
            </summary>
            <div class="message-content">
                <div class="thinking-content markdown-content"></div>
            </div>
        </details>
    `;
    chat.appendChild(div);
    scrollAgentChatIfNearBottom(sid);
}

function appendAgentThinking(sid, content) {
    const chat = document.getElementById(`agent-chat-${sid}`);
    const view = agentSessionViews[sid];
    if (!chat || !view) return;
    const thinkingDiv = chat.querySelector('.agent-message.thinking:last-child .thinking-content');
    if (thinkingDiv) {
        view.thinkingText += content;
        // 逐 token 重渲染 markdown（流式输出，表格/代码可渐进渲染）
        thinkingDiv.innerHTML = formatMarkdown(view.thinkingText) + '<span class="typing-cursor">▊</span>';
    }
}

function finalizeAgentThinking(sid) {
    const chat = document.getElementById(`agent-chat-${sid}`);
    const view = agentSessionViews[sid];
    if (!chat || !view) return;
    const thinkingDiv = chat.querySelector('.agent-message.thinking:last-child');
    if (thinkingDiv) {
        thinkingDiv.querySelector('.thinking-indicator').style.display = 'none';
        const content = thinkingDiv.querySelector('.thinking-content');
        if (content) content.innerHTML = formatMarkdown(view.thinkingText);  // 移除光标
    }
}

function renderAgentToolCall(sid, tool, params) {
    const chat = document.getElementById(`agent-chat-${sid}`);
    if (!chat) return;
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
    scrollAgentChatIfNearBottom(sid);
}

function renderAgentResult(sid, result) {
    const chat = document.getElementById(`agent-chat-${sid}`);
    if (!chat) return;
    const toolDiv = chat.querySelector('.agent-message.tool:last-child');
    if (!toolDiv) return;

    const statusDiv = toolDiv.querySelector('.tool-status');
    if (result.error) {
        statusDiv.innerHTML = '<span class="status-error">❌ 失败</span>';
    } else {
        statusDiv.innerHTML = '<span class="status-success">✅ 完成</span>';
    }

    const contentDiv = toolDiv.querySelector('.message-content');
    if (!contentDiv) return;

    // v4.0 批量结果（多节点）：逐节点卡片（错误在前、成功折叠、可展开全部）
    if (result.type === 'batch_result') {
        renderBatchResult(sid, contentDiv, result);
        return;
    }

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

// v4.0 批量执行结果：错误在前、成功折叠的逐节点卡片
function renderBatchResult(sid, container, result) {
    const results = result.results || [];
    const okCount = results.filter(r => r.ok).length;
    const failCount = results.length - okCount;
    const wrap = document.createElement('div');
    wrap.className = 'batch-result';

    const errors = results.filter(r => !r.ok);
    const oks = results.filter(r => r.ok);

    const nodeHtml = node => {
        const isErr = !node.ok;
        const cls = isErr ? 'batch-node error' : 'batch-node ok';
        let body;
        if (isErr) {
            body = `<div class="batch-node-error">${escapeHtml(node.error || '失败')}</div>`;
        } else if (node.columns && node.rows) {
            body = buildResultTable(node.columns, node.rows).outerHTML;
        } else {
            body = `<pre class="tool-output">${escapeHtml(node.output || '(无输出)')}</pre>`;
        }
        return `<div class="${cls}">
            <div class="batch-node-head">${isErr ? '❌' : '✅'} <span class="batch-node-name">${escapeHtml(node.node || '?')}</span></div>
            ${body}
        </div>`;
    };

    wrap.innerHTML = `<div class="batch-summary">📡 批量执行结果（${results.length} 节点，✅${okCount} / ❌${failCount}）</div>`;
    errors.concat(oks).forEach(n => {
        const temp = document.createElement('div');
        temp.innerHTML = nodeHtml(n);
        wrap.appendChild(temp.firstChild);
    });
    container.appendChild(wrap);
    scrollAgentChatIfNearBottom(sid);
}

function buildResultTable(columns, rows) {
    const div = document.createElement('div');
    div.className = 'tool-result';
    // 构建 markdown 表格字符串，走 formatMarkdown 渲染（与知识问答模块的 md-table 一致）
    const esc = v => String(v).replace(/\|/g, '｜').replace(/[\r\n]+/g, ' ');
    const header = '| ' + columns.map(c => esc(c)).join(' | ') + ' |';
    const sep = '| ' + columns.map(() => '---').join(' | ') + ' |';
    const body = rows.slice(0, 50)
        .map(r => '| ' + r.map(c => esc(c)).join(' | ') + ' |')
        .join('\n');
    const md = [header, sep, body].join('\n');
    div.innerHTML = `
        <details>
            <summary>查看结果 (${rows.length} 行)</summary>
            <div class="result-table-wrapper markdown-content">
                ${formatMarkdown(md)}
            </div>
        </details>
    `;
    return div;
}

function renderAgentObservation(sid, observation) {
    const chat = document.getElementById(`agent-chat-${sid}`);
    if (!chat) return;
    const div = document.createElement('div');
    div.className = 'agent-message observation';
    div.innerHTML = `
        <div class="message-header">
            <span class="icon">👁️</span>
            <span class="label">观察结果</span>
        </div>
        <div class="message-content markdown-content">
            ${formatMarkdown(observation)}
        </div>
    `;
    chat.appendChild(div);
    scrollAgentChatIfNearBottom(sid);
}

function showAgentConclusion(sid) {
    const chat = document.getElementById(`agent-chat-${sid}`);
    if (!chat) return;
    const view = agentView(sid);
    view.conclusionText = '';
    const div = document.createElement('div');
    div.className = 'agent-message conclusion';
    div.id = `agent-conclusion-${sid}`;
    div.innerHTML = `
        <div class="message-header">
            <span class="icon">📝</span>
            <span class="label">分析结论</span>
        </div>
        <div class="message-content markdown-content"></div>
    `;
    chat.appendChild(div);
    scrollAgentChatIfNearBottom(sid);
}

function appendAgentConclusion(sid, content) {
    const chat = document.getElementById(`agent-chat-${sid}`);
    const view = agentSessionViews[sid];
    if (!chat || !view) return;
    let conclusionDiv = chat.querySelector(`#agent-conclusion-${sid}`);
    if (!conclusionDiv) conclusionDiv = chat.querySelector('.agent-message.conclusion:last-child');
    if (conclusionDiv) {
        view.conclusionText += content;
        const md = conclusionDiv.querySelector('.markdown-content');
        if (md) md.innerHTML = formatMarkdown(view.conclusionText) + '<span class="typing-cursor">▊</span>';
    }
}

function finalizeAgentConclusion(sid) {
    const chat = document.getElementById(`agent-chat-${sid}`);
    const view = agentSessionViews[sid];
    if (!chat || !view) return;
    let conclusionDiv = chat.querySelector(`#agent-conclusion-${sid}`);
    if (!conclusionDiv) conclusionDiv = chat.querySelector('.agent-message.conclusion:last-child');
    if (conclusionDiv) {
        // 保留 sid 作用域的 id（供 showAgentFeedback 查询；sid 唯一，无冲突）
        const md = conclusionDiv.querySelector('.markdown-content');
        if (md) md.innerHTML = formatMarkdown(view.conclusionText);  // 移除光标
        showAgentFeedback(sid);
    }
}

function showAgentFinalThinking(sid) {
    // 未执行任何工具时，最后一步思考即对用户的回应（回答/提问）：
    // 展开使其直接可见，并把「思考中」标签改为「Agent 回复」
    const chat = document.getElementById(`agent-chat-${sid}`);
    if (!chat) return;
    const thinking = chat.querySelector('.agent-message.thinking:last-child');
    if (!thinking) return;
    const details = thinking.querySelector('details.agent-collapse');
    if (details) details.open = true;
    const label = thinking.querySelector('.label');
    if (label) label.textContent = 'Agent 回复';
    const indicator = thinking.querySelector('.thinking-indicator');
    if (indicator) indicator.style.display = 'none';
}

// ==================== 变更类操作审批（Claude Code 形态：审批槽 + 竖向选项 + 批准即收起） ====================

function renderAgentApproval(event, sid) {
    // 渲染进该会话贴近输入框的固定审批槽，审批期间隐藏该会话输入框——
    // 审批框与输入框互斥；批准后审批槽即刻收起、输入框恢复，执行结果以 chat 记录呈现。
    const slot = document.getElementById(`agent-approval-slot-${sid}`);
    if (!slot) return;
    const view = agentView(sid);
    const plan = event.plan || {};
    view.lastPlan = plan;
    const ops = plan.operations || [];

    const riskOrder = { 'high': 3, 'medium': 2, 'low': 1 };
    let maxRisk = 'low';
    ops.forEach(op => {
        const r = (op.risk || 'medium').toLowerCase();
        if ((riskOrder[r] || 2) > (riskOrder[maxRisk] || 1)) maxRisk = r;
    });

    const target = agentApprovalTarget(sid);

    // v4.0 范围扩展计划（kind:'scope'）：专用卡片，无命令/SQL
    if (plan.kind === 'scope') {
        const tgt = (plan.targets || []).map(t => t.name || t).join(', ');
        slot.innerHTML = `
            <div class="approval-bar" id="agent-approval-${event.plan_id}" data-planId="${event.plan_id}">
                <div class="approval-header">
                    <span class="approval-title">🎯 ${escapeHtml(plan.title || '扩展操作范围')}</span>
                </div>
                ${plan.scope ? `<div class="approval-scope">${escapeHtml(plan.scope)}</div>` : ''}
                <div class="scope-extension-target">将纳入范围：<strong>${escapeHtml(tgt)}</strong></div>
                <div class="approval-actions">
                    <button class="btn btn-primary approval-btn" onclick="approvePlan('${escapeJsAttr(sid)}', ${event.plan_id})">✅ 批准</button>
                    <button class="btn btn-danger approval-btn" onclick="rejectPlan('${escapeJsAttr(sid)}', ${event.plan_id})">❌ 拒绝</button>
                </div>
                <div class="approval-status" id="approval-status-${event.plan_id}"></div>
            </div>`;
        const inputArea = document.getElementById(`agent-input-area-${sid}`);
        if (inputArea) inputArea.style.display = 'none';
        return;
    }
    const riskBadge = ops.length
        ? `<span class="risk-badge risk-${maxRisk}">${riskLabel(maxRisk)}</span>`
        : '';
    const opsHtml = ops.map((op, i) => {
        const params = op.parameters || {};
        const paramText = op.tool === 'execute_command'
            ? (params.command || '')
            : (params.sql || '');
        const riskClass = `risk-${(op.risk || 'medium').toLowerCase()}`;
        return `
            <div class="plan-op" data-op="${i + 1}">
                <span class="op-index">${i + 1}</span>
                <span class="op-tool">${escapeHtml(op.tool || '')}</span>
                <code class="op-params">${escapeHtml(paramText)}</code>
                <div class="op-meta">
                    <span class="op-impact">${escapeHtml(op.impact || '')}</span>
                    <span class="op-risk ${riskClass}">${riskText(op.risk)}</span>
                </div>
                <span class="op-status"></span>
            </div>`;
    }).join('');

    slot.innerHTML = `
        <div class="approval-bar" id="agent-approval-${event.plan_id}" data-planId="${event.plan_id}">
            <div class="approval-header">
                <span class="approval-title">🧾 ${escapeHtml(plan.title || '操作计划')}</span>
                ${target ? `<span class="approval-target">${target}</span>` : ''}
            </div>
            ${plan.scope ? `<div class="approval-scope">${escapeHtml(plan.scope)}</div>` : ''}
            ${ops.length ? `<div class="plan-op-count">📋 ${ops.length} 项操作${riskBadge}</div>` : ''}
            <div class="plan-ops">${opsHtml || '<div class="empty-message">计划无操作项</div>'}</div>
            ${plan.rollback ? `<div class="plan-rollback">↩️ 回滚：${escapeHtml(plan.rollback)}</div>` : ''}
            <div class="approval-actions">
                <button class="btn btn-primary approval-btn" onclick="approvePlan('${escapeJsAttr(sid)}', ${event.plan_id})">✅ 批准</button>
                <button class="btn btn-danger approval-btn" onclick="rejectPlan('${escapeJsAttr(sid)}', ${event.plan_id})">❌ 拒绝</button>
                <button class="btn btn-secondary approval-btn" onclick="toggleRevisePanel(${event.plan_id})">✏️ 修改并重新提供方案</button>
                <div class="approval-revise-panel" id="revise-panel-${event.plan_id}" style="display:none;">
                    <textarea id="revise-comment-${event.plan_id}" rows="2"
                              placeholder="描述希望修改的地方，Agent 将据此重新提供方案..."></textarea>
                    <button class="btn btn-primary" onclick="revisePlan('${escapeJsAttr(sid)}', ${event.plan_id})">提交修改</button>
                    <button class="btn btn-secondary" onclick="toggleRevisePanel(${event.plan_id})">取消</button>
                </div>
            </div>
            <div class="approval-status" id="approval-status-${event.plan_id}"></div>
        </div>
    `;

    // 审批进行中：隐藏该会话输入框（审批框与输入框互斥）
    const inputArea = document.getElementById(`agent-input-area-${sid}`);
    if (inputArea) inputArea.style.display = 'none';
}

function agentApprovalTarget(sid) {
    // 审批留痕：v4.0 范围会话显示「范围: N 节点 · M 实例」；legacy 回退连接名
    const sc = sessionScopeCount(agentSessions.find(x => x.id === sid));
    if (sc.ssh + sc.db > 0) {
        return `🎯 范围: ${sc.ssh} 节点 · ${sc.db} 实例`;
    }
    const parts = [];
    if (agentCurrentSSHConn) {
        const c = agentSSHConnections.find(x => x.id === agentCurrentSSHConn);
        if (c) parts.push(`SSH: ${c.name}`);
    }
    if (agentCurrentDBConn) {
        const c = agentDBConnections.find(x => x.id === agentCurrentDBConn);
        if (c) parts.push(`DB: ${c.name}`);
    }
    return parts.length ? `🎯 ${parts.join(' / ')}` : '';
}

function riskLabel(risk) {
    const map = { 'high': '⚠️ 高风险', 'medium': '⚡ 中风险', 'low': '低风险' };
    return map[(risk || 'medium').toLowerCase()] || '⚡ 中风险';
}

function riskText(risk) {
    const map = { 'high': '高风险', 'medium': '中风险', 'low': '低风险' };
    return map[(risk || 'medium').toLowerCase()] || '中风险';
}

function toggleRevisePanel(planId) {
    const panel = document.getElementById(`revise-panel-${planId}`);
    if (!panel) return;
    const show = panel.style.display === 'none';
    panel.style.display = show ? 'flex' : 'none';
    if (show) {
        const input = document.getElementById(`revise-comment-${planId}`);
        if (input) input.focus();
    }
}

async function approvePlan(sid, planId) {
    await submitPlanDecision(sid, planId, 'approve', '');
}

async function rejectPlan(sid, planId) {
    await submitPlanDecision(sid, planId, 'reject', '');
}

async function revisePlan(sid, planId) {
    const input = document.getElementById(`revise-comment-${planId}`);
    const comment = input ? input.value.trim() : '';
    if (!comment) {
        showToast('请先描述希望修改的地方', 'warning');
        return;
    }
    await submitPlanDecision(sid, planId, 'revise', comment);
}

async function submitPlanDecision(sid, planId, action, comment) {
    const view = agentSessionViews[sid];
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
        if (action === 'approve') {
            // 批准：审批框即刻消失、返回输入框；执行结果以 chat 记录呈现
            clearApprovalSlot(sid);
            if (view && view.lastPlan) {
                if (view.lastPlan.kind === 'scope') {
                    // 范围扩展计划：无命令/SQL，仅提示
                    const t = (view.lastPlan.targets || []).map(x => x.name || x).join(', ');
                    addAgentMessage(sid, 'assistant', `✅ 已批准，扩展操作范围至节点 ${t}，继续执行中...`);
                } else {
                    renderPlanExecRecord(sid, planId, view.lastPlan);
                }
            }
        } else {
            const bar = document.getElementById(`agent-approval-${planId}`);
            if (bar) {
                const status = bar.querySelector('.approval-status');
                const actions = bar.querySelector('.approval-actions');
                if (actions) actions.remove();
                if (status) {
                    status.textContent = action === 'reject'
                        ? '❌ 已拒绝'
                        : '✏️ 已要求修改，等待重新提供方案...';
                }
            }
        }
    } catch (error) {
        showToast('审批提交失败', 'error');
    }
}

// 批准后：在会话 chat 渲染「已批准，开始执行」记录（全量命令 + risk），plan_operation_result 逐项更新
function renderPlanExecRecord(sid, planId, plan) {
    const chat = document.getElementById(`agent-chat-${sid}`);
    if (!chat) return;
    const ops = plan.operations || [];
    const riskOrder = { 'high': 3, 'medium': 2, 'low': 1 };
    let maxRisk = 'low';
    ops.forEach(op => {
        const r = (op.risk || 'medium').toLowerCase();
        if ((riskOrder[r] || 2) > (riskOrder[maxRisk] || 1)) maxRisk = r;
    });
    const riskBadge = ops.length
        ? `<span class="risk-badge risk-${maxRisk}">${riskLabel(maxRisk)}</span>`
        : '';
    const opsHtml = ops.map((op, i) => {
        const params = op.parameters || {};
        const paramText = op.tool === 'execute_command'
            ? (params.command || '')
            : (params.sql || '');
        const riskClass = `risk-${(op.risk || 'medium').toLowerCase()}`;
        return `
            <div class="plan-op" data-op="${i + 1}">
                <span class="op-index">${i + 1}</span>
                <span class="op-tool">${escapeHtml(op.tool || '')}</span>
                <code class="op-params">${escapeHtml(paramText)}</code>
                <div class="op-meta">
                    <span class="op-impact">${escapeHtml(op.impact || '')}</span>
                    <span class="op-risk ${riskClass}">${riskText(op.risk)}</span>
                </div>
                <span class="op-status"></span>
            </div>`;
    }).join('');

    const div = document.createElement('div');
    div.className = 'agent-message plan-exec';
    div.id = `plan-exec-${planId}`;
    div.innerHTML = `
        <div class="message-header">
            <span class="icon">🧾</span>
            <span class="label">✅ 已批准，开始执行</span>
        </div>
        <div class="message-content">
            <div class="plan-title">${escapeHtml(plan.title || '操作计划')}</div>
            ${ops.length ? `<div class="plan-op-count">📋 ${ops.length} 项操作${riskBadge}</div>` : ''}
            <div class="plan-ops">${opsHtml || '<div class="empty-message">计划无操作项</div>'}</div>
            ${plan.rollback ? `<div class="plan-rollback">↩️ 回滚：${escapeHtml(plan.rollback)}</div>` : ''}
        </div>
    `;
    chat.appendChild(div);
    scrollAgentChatIfNearBottom(sid);
}

function renderAgentApprovalGranted(event, sid) {
    // 前端批准时已即时收起审批槽；此处兜底（如经 API 批准/其他端触发）
    const bar = document.getElementById(`agent-approval-${event.plan_id}`);
    if (!bar) return;
    const status = bar.querySelector('.approval-status');
    if (status) status.textContent = '✅ 已批准，开始执行';
    const actions = bar.querySelector('.approval-actions');
    if (actions) actions.remove();
}

function renderAgentApprovalRejected(event, sid) {
    const bar = document.getElementById(`agent-approval-${event.plan_id}`);
    if (!bar) return;
    const status = bar.querySelector('.approval-status');
    if (status) status.textContent = '❌ 已拒绝' + (event.comment ? `（${event.comment}）` : '');
    const actions = bar.querySelector('.approval-actions');
    if (actions) actions.remove();
}

function renderAgentApprovalRevised(event, sid) {
    const bar = document.getElementById(`agent-approval-${event.plan_id}`);
    if (!bar) return;
    const status = bar.querySelector('.approval-status');
    if (status) status.textContent = '✏️ 已要求修改，等待 Agent 重新提供方案';
    const actions = bar.querySelector('.approval-actions');
    if (actions) actions.remove();
}

function renderAgentApprovalExpired(event, sid) {
    const bar = document.getElementById(`agent-approval-${event.plan_id}`);
    if (!bar) return;
    const status = bar.querySelector('.approval-status');
    if (status) status.textContent = '⏰ 审批超时';
    const actions = bar.querySelector('.approval-actions');
    if (actions) actions.remove();
}

function clearApprovalSlot(sid) {
    // 审批结束/会话收尾：清空该会话审批槽并恢复输入框显示
    const slot = document.getElementById(`agent-approval-slot-${sid}`);
    const inputArea = document.getElementById(`agent-input-area-${sid}`);
    if (slot) slot.innerHTML = '';
    if (inputArea) inputArea.style.display = '';
}

function renderPlanOperationResult(event, sid) {
    // 批准后执行结果更新 chat 中的执行记录（审批槽已收起）
    const record = document.getElementById(`plan-exec-${event.plan_id}`);
    const host = record || document.getElementById(`agent-approval-${event.plan_id}`);
    if (!host) return;
    const opRow = host.querySelector(`.plan-op[data-op="${event.index}"]`);
    if (!opRow) return;
    const statusEl = opRow.querySelector('.op-status');
    const result = event.result || {};

    // v4.0 批量变更：逐节点结果追加在 op 行内（同一 index 多条）
    if (event.node) {
        const view = agentView(sid);
        if (event.status === 'error') {
            if (view && view.failedNodes) view.failedNodes.add(event.node);
        }
        const line = document.createElement('div');
        line.className = 'op-node-result ' + (event.status === 'success' ? 'ok' : 'error');
        let detail = '';
        if (event.status === 'success') {
            if (result.row_count !== undefined) detail = `（${result.row_count} 行）`;
            else if (result.stdout !== undefined) detail = ' 已执行';
        } else {
            detail = event.error ? `：${event.error}` : '';
        }
        line.textContent = `${event.status === 'success' ? '✅' : '❌'} ${event.node}${detail}`;
        opRow.insertAdjacentElement('beforeend', line);
        return;
    }

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

// v4.0 批量变更失败节点：会话结束（done）时若有失败节点，给出「仅重试失败节点」入口
function maybeRenderRetryButton(sid) {
    const view = agentView(sid);
    if (!view || !view.failedNodes || view.failedNodes.size === 0) return;
    const chat = document.getElementById(`agent-chat-${sid}`);
    if (!chat) return;
    const names = [...view.failedNodes].join(', ');
    const div = document.createElement('div');
    div.className = 'agent-message retry-block';
    div.innerHTML = `
        <div class="message-header">
            <span class="icon">🔁</span>
            <span class="label">批量变更部分失败</span>
        </div>
        <div class="message-content">失败节点: <strong>${escapeHtml(names)}</strong></div>
        <button class="btn btn-primary retry-btn" onclick="retryFailedNodes('${escapeJsAttr(sid)}')">🔁 仅重试失败节点</button>`;
    chat.appendChild(div);
    scrollAgentChatIfNearBottom(sid);
}

function retryFailedNodes(sid) {
    const view = agentView(sid);
    if (!view || !view.failedNodes || view.failedNodes.size === 0) return;
    const names = [...view.failedNodes].join('、');
    const input = document.getElementById(`agent-input-${sid}`);
    if (!input) return;
    input.value = `仅对失败节点 ${names} 重试上一个已批准计划的相同操作，其他节点不要重复执行`;
    input.focus();
}

// ==================== DBA 反馈闭环 ====================

function showAgentFeedback(sid) {
    const conclusionDiv = document.getElementById(`agent-conclusion-${sid}`);
    if (!conclusionDiv) return;
    if (conclusionDiv.querySelector('.agent-feedback')) return;

    const row = document.createElement('div');
    row.className = 'agent-feedback';
    row.innerHTML = `
        <div class="feedback-actions">
            <span class="feedback-label">这个结论对你有帮助吗？</span>
            <button class="feedback-btn" onclick="submitAgentFeedback('${escapeJsAttr(sid)}', 'up')">👍 有帮助</button>
            <button class="feedback-btn" onclick="showAgentFeedbackCorrection('${escapeJsAttr(sid)}')">👎 有误/需纠正</button>
        </div>
        <div class="feedback-correction" style="display:none;">
            <input type="text" id="agent-feedback-correction-input-${sid}" placeholder="补充或纠正（可选），写入长期记忆">
            <button class="feedback-btn primary" onclick="submitAgentFeedback('${escapeJsAttr(sid)}', 'down')">提交</button>
        </div>
    `;
    conclusionDiv.appendChild(row);
    conclusionDiv.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

function showAgentFeedbackCorrection(sid) {
    const conclusionDiv = document.getElementById(`agent-conclusion-${sid}`);
    if (!conclusionDiv) return;
    const correction = conclusionDiv.querySelector('.agent-feedback .feedback-correction');
    if (correction) correction.style.display = 'flex';
}

async function submitAgentFeedback(sid, feedback) {
    const input = document.getElementById(`agent-feedback-correction-input-${sid}`);
    const correction = input ? input.value.trim() : '';
    try {
        const response = await fetch('/api/agent/feedback', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ session_id: sid, feedback, correction })
        });
        const data = await response.json();
        if (response.ok) {
            showToast(data.message || '反馈已记录', 'success');
            const conclusionDiv = document.getElementById(`agent-conclusion-${sid}`);
            if (conclusionDiv) {
                conclusionDiv.querySelectorAll('.agent-feedback .feedback-btn').forEach(b => b.disabled = true);
            }
        } else {
            showToast(data.error || '反馈失败', 'error');
        }
    } catch (error) {
        showToast('反馈失败', 'error');
    }
}

function renderAgentError(sid, error) {
    const chat = document.getElementById(`agent-chat-${sid}`);
    if (!chat) return;
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
    scrollAgentChatIfNearBottom(sid);
}

function renderAgentWarning(sid, warning) {
    const chat = document.getElementById(`agent-chat-${sid}`);
    if (!chat) return;
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
    scrollAgentChatIfNearBottom(sid);
}

function showAgentLoading(sid, message) {
    const chat = document.getElementById(`agent-chat-${sid}`);
    if (!chat) return;
    const div = document.createElement('div');
    div.className = 'agent-message loading';
    div.innerHTML = `
        <div class="message-content">
            <div class="loading-spinner"></div>
            <span>${escapeHtml(message)}</span>
        </div>
    `;
    chat.appendChild(div);
    scrollAgentChatIfNearBottom(sid);
}

function removeAgentLoading(sid) {
    const chat = document.getElementById(`agent-chat-${sid}`);
    if (!chat) return;
    chat.querySelectorAll('.agent-message.loading').forEach(el => el.remove());
}

// ==================== 工具函数 ====================

// 仅当用户接近底部时才自动滚动到底（用户上翻看历史时不被拉回）
function scrollAgentChatIfNearBottom(sid) {
    const chat = document.getElementById(`agent-chat-${sid}`);
    if (!chat) return;
    const threshold = 60;
    if (chat.scrollHeight - chat.scrollTop - chat.clientHeight < threshold) {
        chat.scrollTop = chat.scrollHeight;
    }
}

function clearAgentChat(sid) {
    const chat = document.getElementById(`agent-chat-${sid}`);
    if (!chat) return;
    clearApprovalSlot(sid);  // 清掉该会话残留审批槽，恢复输入框
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

function renderAgentStep(sid, step) {
    // 持久化的 action 是 JSON 字符串，先解析
    if (typeof step.action === 'string' && step.action) {
        try {
            step.action = JSON.parse(step.action);
        } catch (e) {
            step.action = null;
        }
    }

    // 渲染历史步骤（按会话路由）
    switch (step.phase) {
        case 'thinking':
            showAgentThinking(sid, step.step_number);
            appendAgentThinking(sid, step.thought || '');
            finalizeAgentThinking(sid);
            break;
        case 'executing':
            if (step.action) {
                renderAgentToolCall(sid, step.action.tool, step.action.parameters || {});
            }
            if (step.observation) {
                renderAgentObservation(sid, step.observation);
            }
            break;
        case 'concluding':
            showAgentConclusion(sid);
            appendAgentConclusion(sid, step.thought || '');
            finalizeAgentConclusion(sid);
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
