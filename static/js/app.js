/**
 * 数据库运维工具 - 前端入口文件
 */

// ==================== 全局命名空间 ====================
const DBTool = {
    currentModule: 'knowledge',
    dbTypes: [],
    currentClusterId: null,
    topologyNetwork: null,

    // 模块切换
    setCurrentModule(module) {
        this.currentModule = module;
    },

    // 数据库类型管理
    setDBTypes(types) {
        this.dbTypes = types;
    },
    getDBTypes() {
        return this.dbTypes;
    },
    findDBType(id) {
        return this.dbTypes.find(t => t.id === id);
    },

    // 集群ID管理
    setCurrentClusterId(id) {
        this.currentClusterId = id;
    },
    getCurrentClusterId() {
        return this.currentClusterId;
    },

    // 拓扑网络管理
    setTopologyNetwork(network) {
        this.topologyNetwork = network;
    },
    getTopologyNetwork() {
        return this.topologyNetwork;
    }
};

// 兼容旧代码的全局变量（逐步迁移）
let currentModule = DBTool.currentModule;
let dbTypes = DBTool.dbTypes;
let currentClusterId = DBTool.currentClusterId;
let topologyNetwork = DBTool.topologyNetwork;

// ==================== 主题切换 ====================
function initTheme() {
    const savedTheme = localStorage.getItem('dbsv-admin-theme');
    if (savedTheme === 'dark') {
        document.documentElement.setAttribute('data-theme', 'dark');
        updateThemeUI(true);
    } else {
        document.documentElement.removeAttribute('data-theme');
        updateThemeUI(false);
    }
}

function toggleTheme() {
    const isDark = document.documentElement.getAttribute('data-theme') === 'dark';
    if (isDark) {
        document.documentElement.removeAttribute('data-theme');
        localStorage.setItem('dbsv-admin-theme', 'light');
        updateThemeUI(false);
    } else {
        document.documentElement.setAttribute('data-theme', 'dark');
        localStorage.setItem('dbsv-admin-theme', 'dark');
        updateThemeUI(true);
    }
}

function updateThemeUI(isDark) {
    const themeIcon = document.getElementById('theme-icon');
    const themeText = document.getElementById('theme-text');
    if (themeIcon && themeText) {
        themeIcon.textContent = isDark ? '☀️' : '🌙';
        themeText.textContent = isDark ? '亮色模式' : '暗色模式';
    }
}

// ==================== 初始化 ====================
document.addEventListener('DOMContentLoaded', function() {
    initTheme();
    initSidebar();
    initNavigation();
    initKeyboardShortcuts();
    loadDBTypes();
    loadConfig();
    loadQATemplates();
    updateSidebarStats();
    loadDashboard();
    initManuals();
    // loadQAHistory 在 qa.js 加载后调用

    // 绑定文件上传事件（确保 DOM 已加载）
    const fileInput = document.getElementById('file-input');
    const folderInput = document.getElementById('folder-input');

    if (fileInput) {
        fileInput.addEventListener('change', async function(e) {
            const files = Array.from(e.target.files);
            if (files.length === 0) return;
            await uploadFiles(files);
            this.value = '';
        });
    }

    if (folderInput) {
        folderInput.addEventListener('change', async function(e) {
            const files = Array.from(e.target.files);
            if (files.length === 0) return;
            await uploadFiles(files);
            this.value = '';
        });
    }
});

// ==================== 侧边栏折叠 ====================
function toggleSidebar() {
    const sidebar = document.getElementById('sidebar');
    const content = document.querySelector('.content');
    if (!sidebar || !content) return;
    const collapsed = sidebar.classList.toggle('collapsed');
    content.classList.toggle('sidebar-collapsed', collapsed);
    localStorage.setItem('sidebar_collapsed', collapsed ? '1' : '0');
}

function initSidebar() {
    if (localStorage.getItem('sidebar_collapsed') === '1') {
        document.getElementById('sidebar')?.classList.add('collapsed');
        document.querySelector('.content')?.classList.add('sidebar-collapsed');
    }
}

// 更新侧边栏统计信息
async function updateSidebarStats() {
    try {
        const response = await fetch('/api/stats');
        const stats = await response.json();

        const knowledgeCount = document.getElementById('sidebar-knowledge-count');
        const clusterCount = document.getElementById('sidebar-cluster-count');

        if (knowledgeCount) {
            knowledgeCount.textContent = stats.knowledge_files || 0;
        }
        if (clusterCount) {
            clusterCount.textContent = stats.clusters_count || 0;
        }
    } catch (error) {
        console.error('更新侧边栏统计失败:', error);
    }
}

// ==================== 导航功能 ====================
async function initNavigation() {
    // 加载功能配置
    try {
        const response = await fetch('/api/config/features');
        const data = await response.json();

        if (data.features) {
            data.features.forEach(feature => {
                const navItem = document.querySelector(`.nav-item[data-module="${feature.module_id}"]`);
                if (navItem) {
                    navItem.style.display = feature.is_enabled ? 'flex' : 'none';
                }
            });
        }
    } catch (error) {
        console.error('加载功能配置失败:', error);
    }

    const navItems = document.querySelectorAll('.nav-item');
    navItems.forEach(item => {
        item.addEventListener('click', function() {
            const module = this.dataset.module;
            switchModule(module);
        });
    });
}

function switchModule(module) {
    // 更新导航状态
    document.querySelectorAll('.nav-item').forEach(item => {
        item.classList.remove('active');
    });
    const navItem = document.querySelector(`[data-module="${module}"]`);
    if (navItem) {
        navItem.classList.add('active');
    }

    // 更新内容区显示（切换 .active 以触发入场动画，display 用内联保证覆盖初始 none）
    document.querySelectorAll('.module').forEach(m => {
        m.style.display = 'none';
        m.classList.remove('active');
    });
    const moduleDiv = document.getElementById(`module-${module}`);
    if (moduleDiv) {
        moduleDiv.style.display = 'block';
        moduleDiv.classList.add('active');
    }

    currentModule = module;

    // 加载对应模块数据
    if (module === 'dashboard') {
        loadDashboard();
    } else if (module === 'topology') {
        loadTopologyStats();
        loadClusters();
    } else if (module === 'config') {
        loadDBTypesPage();
        loadLogs();
    } else if (module === 'knowledge') {
        loadFileList();
        // 如果当前是图谱视图，初始化知识图谱
        if (KnowledgeModule.currentView === 'graph') {
            initKGModule();
        }
    } else if (module === 'manuals') {
        loadManuals();
    } else if (module === 'commands') {
        loadCommands();
    } else if (module === 'log_analysis') {
        showLogAnalysisListView();
    } else if (module === 'qa') {
        loadConversations();
    } else if (module === 'agent') {
        initAgentModule();
    }
}

// ==================== 数据库类型加载 ====================
async function loadDBTypes() {
    try {
        const response = await fetch('/api/db-types');
        const data = await response.json();
        dbTypes = data.types;

        // 填充所有下拉框
        const selects = [
            'knowledge-db-type', 'qa-db-type', 'sql-db-type',
            'sql-source-db', 'sql-target-db', 'explain-db-type',
            'commands-db-type', 'cluster-db-type', 'edit-cluster-db-type',
            'agent-ssh-db-type', 'agent-db-type'
        ];

        selects.forEach(selectId => {
            const select = document.getElementById(selectId);
            if (!select) return;

            // 保留第一个选项（兼容 Firefox）
            const firstOption = select.options[0];
            select.replaceChildren();
            if (firstOption) {
                select.appendChild(firstOption);
            }

            dbTypes.forEach(type => {
                const option = document.createElement('option');
                option.value = type.id;
                option.textContent = `${type.icon || ''} ${type.name}`;
                select.appendChild(option);
            });

            // 默认选择 oracle（如果存在），但 qa-db-type 保持 auto
            const hasOracle = dbTypes.find(t => t.id === 'oracle');
            if (hasOracle) {
                if (selectId === 'qa-db-type') {
                    select.value = 'auto';
                } else {
                    select.value = 'oracle';
                }
            }
        });

        // 加载模型列表到下拉框
        await loadModelSelects();

        // 绑定事件
        document.getElementById('knowledge-db-type').addEventListener('change', loadFileList);
        document.getElementById('knowledge-tag').addEventListener('change', loadFileList);
        document.getElementById('commands-db-type').addEventListener('change', loadCommands);

        // 默认加载知识库和命令速查
        loadFileList();
        loadCommands();
    } catch (error) {
        console.error('加载数据库类型失败:', error);
    }
}

// 加载模型列表到所有模型选择下拉框
async function loadModelSelects() {
    try {
        // 禁用缓存，避免 Firefox 缓存空响应导致下拉框不显示模型
        const response = await fetch('/api/config/llm/models', { cache: 'no-cache' });
        const data = await response.json();
        const models = data.models || [];

        const selectIds = ['qa-model-select', 'sql-model-select'];
        selectIds.forEach(selectId => {
            const select = document.getElementById(selectId);
            if (!select) return;

            // 保存第一个选项的 DOM 引用（兼容 Firefox：innerHTML 清空 select 后，
            // 新创建的 option 在某些 Firefox 版本上可能无法正常渲染，保留原始节点引用更可靠）
            const firstOption = select.options[0];
            const fallbackText = selectId === 'qa-model-select' ? '使用默认模型' : '使用默认模型';
            const fallbackValue = select.options[0] ? select.options[0].value : '';

            // 清空下拉框（用 replaceChildren 替代 innerHTML，兼容性更好）
            select.replaceChildren();

            // 恢复默认选项（保留原始 DOM 节点引用进行 re-append）
            if (firstOption) {
                select.appendChild(firstOption);
            } else {
                // 兜底：如果原始节点丢失，创建新的
                const defaultOption = document.createElement('option');
                defaultOption.value = fallbackValue;
                defaultOption.textContent = fallbackText;
                select.appendChild(defaultOption);
            }

            // 添加模型选项
            models.forEach(model => {
                const option = document.createElement('option');
                option.value = model.id;
                option.textContent = model.display_name || model.model_name;
                if (model.is_default) {
                    option.textContent += ' (默认)';
                    option.selected = true;
                }
                select.appendChild(option);
            });
        });
    } catch (error) {
        console.error('加载模型列表失败:', error);
    }
}

// ==================== 快捷键系统 ====================
function initKeyboardShortcuts() {
    document.addEventListener('keydown', function(e) {
        // Ctrl/Cmd + 1~9 切换模块
        if ((e.ctrlKey || e.metaKey) && e.key >= '0' && e.key <= '9') {
            e.preventDefault();
            const moduleMap = {
                '1': 'dashboard',
                '2': 'knowledge',
                '3': 'qa',
                '4': 'log_analysis',
                '5': 'sql',
                '6': 'manuals',
                '7': 'commands',
                '8': 'topology',
                '9': 'config'
            };
            const module = moduleMap[e.key];
            if (module) {
                switchModule(module);
            }
        }

        // Ctrl/Cmd + K 搜索命令
        if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
            e.preventDefault();
            switchModule('commands');
            setTimeout(() => {
                const searchInput = document.getElementById('command-search');
                if (searchInput) {
                    searchInput.focus();
                }
            }, 100);
        }

        // ESC 关闭对话框
        if (e.key === 'Escape') {
            document.querySelectorAll('.modal').forEach(modal => {
                modal.style.display = 'none';
            });
        }
    });
}

// ==================== 文档加载 ====================
async function loadDoc(filename, elementId) {
    try {
        const response = await fetch(`/api/config/docs/${filename}`);
        const data = await response.json();
        const element = document.getElementById(elementId);

        if (response.ok) {
            element.innerHTML = formatMarkdown(data.content);
        } else {
            element.innerHTML = `<div class="empty-message">${data.error || '加载失败'}</div>`;
        }
    } catch (error) {
        document.getElementById(elementId).innerHTML = '<div class="empty-message">加载失败</div>';
    }
}

// ==================== 仪表盘模块 ====================
async function loadDashboard() {
    try {
        // 加载统计数据
        const statsResponse = await fetch('/api/stats');
        const stats = await statsResponse.json();

        document.getElementById('stat-db-types').textContent = stats.db_types_count || 0;
        document.getElementById('stat-knowledge').textContent = stats.knowledge_files || 0;
        document.getElementById('stat-manuals').textContent = stats.manuals_count || 0;
        document.getElementById('stat-clusters').textContent = stats.clusters_count || 0;

        // 渲染知识库分布图
        renderDBChart(stats.by_db_type || {});

        // 渲染向量索引数量图
        renderEmbeddingChart(stats.embeddings_by_db_type || {});

        // 加载最近操作日志
        loadRecentLogs();

        // 加载系统状态
        loadSystemHealth();
    } catch (error) {
        console.error('加载仪表盘失败:', error);
    }
}

function renderDBChart(byDbType) {
    const chartDiv = document.getElementById('db-chart');
    const entries = Object.entries(byDbType);

    if (entries.length === 0) {
        chartDiv.innerHTML = '<div class="empty-message">暂无数据</div>';
        return;
    }

    const maxCount = Math.max(...entries.map(([_, count]) => count), 1);

    chartDiv.innerHTML = entries.map(([dbType, count]) => {
        const dbInfo = dbTypes.find(t => t.id === dbType);
        const icon = dbInfo ? dbInfo.icon : '📁';
        const name = dbInfo ? dbInfo.name : dbType;
        const percentage = (count / maxCount) * 100;

        return `
            <div class="chart-bar-item">
                <div class="chart-label">${escapeHtml(icon)} ${escapeHtml(name)}</div>
                <div class="chart-bar-container">
                    <div class="chart-bar" style="width: ${percentage}%"></div>
                    <span class="chart-value">${count}</span>
                </div>
            </div>
        `;
    }).join('');
}

function renderEmbeddingChart(embeddingsByDbType) {
    const chartDiv = document.getElementById('embedding-chart');
    const entries = Object.entries(embeddingsByDbType);

    if (entries.length === 0) {
        chartDiv.innerHTML = '<div class="empty-message">暂无数据</div>';
        return;
    }

    const maxCount = Math.max(...entries.map(([_, count]) => count), 1);

    chartDiv.innerHTML = entries.map(([dbType, count]) => {
        const dbInfo = dbTypes.find(t => t.id === dbType);
        const icon = dbInfo ? dbInfo.icon : '📁';
        const name = dbInfo ? dbInfo.name : dbType;
        const percentage = (count / maxCount) * 100;

        return `
            <div class="chart-bar-item">
                <div class="chart-label">${escapeHtml(icon)} ${escapeHtml(name)}</div>
                <div class="chart-bar-container">
                    <div class="chart-bar chart-bar-embedding" style="width: ${percentage}%"></div>
                    <span class="chart-value">${count}</span>
                </div>
            </div>
        `;
    }).join('');
}

async function loadRecentLogs() {
    try {
        const response = await fetch('/api/logs?limit=5');
        const data = await response.json();
        const logsDiv = document.getElementById('recent-logs');

        if (data.logs && data.logs.length > 0) {
            logsDiv.innerHTML = data.logs.map(log => `
                <div class="log-item">
                    <span class="log-time">${escapeHtml(log.timestamp)}</span>
                    <span class="log-module">[${escapeHtml(log.module)}]</span>
                    <span class="log-action">${escapeHtml(log.action)}</span>
                </div>
            `).join('');
        } else {
            logsDiv.innerHTML = '<div class="empty-message">暂无操作记录</div>';
        }
    } catch (error) {
        console.error('加载日志失败:', error);
    }
}

async function loadSystemHealth() {
    try {
        const response = await fetch('/api/health');
        const health = await response.json();
        const healthDiv = document.getElementById('system-health');

        const statusIcon = health.status === 'healthy' ? '✅' : '⚠️';
        let checksHtml = '';

        if (health.checks) {
            for (const [key, check] of Object.entries(health.checks)) {
                const checkIcon = check.status === 'ok' ? '✅' : check.status === 'warning' ? '⚠️' : '❌';
                checksHtml += `<div class="health-check">${checkIcon} ${escapeHtml(check.message)}</div>`;
            }
        }

        healthDiv.innerHTML = `
            <div class="health-status">${statusIcon} 系统状态: ${health.status === 'healthy' ? '正常' : '异常'}</div>
            ${checksHtml}
        `;
    } catch (error) {
        document.getElementById('system-health').innerHTML = '<div class="health-check">❌ 无法获取系统状态</div>';
    }
}

// ==================== 通用对话框 ====================
function closeModal(modalId) {
    document.getElementById(modalId).style.display = 'none';
}
