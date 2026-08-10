#!/usr/bin/env python3
"""
拆分 app.js 为多个模块文件
"""

import re

# 读取原始文件
with open('static/js/app.js', 'r', encoding='utf-8') as f:
    content = f.read()

# 定义模块映射
modules = {
    'utils.js': {
        'start': '// ==================== 工具函数',
        'end': '// ==================== 仪表盘模块',
        'functions': ['showToast', 'escapeHtml', 'escapeJs', 'formatFileSize', 'formatMarkdown', 'copyToClipboard']
    },
    'knowledge.js': {
        'start': '// ==================== 知识库模块',
        'end': '// ==================== 知识问答模块',
        'functions': ['renderTags', 'loadFileList', 'previewFile', 'downloadFile', 'deleteFile', 'searchKnowledge', 'uploadFiles', 'reindexKnowledge']
    },
    'qa.js': {
        'start': '// ==================== 知识问答模块',
        'end': '// ==================== SQL工具模块',
        'functions': ['loadQATemplates', 'applyTemplate', 'sendQuestion', 'stopStreaming', 'saveToHistory', 'loadQAHistory', 'deleteHistory', 'reuseQuestion', 'clearChat']
    },
    'sql-tools.js': {
        'start': '// ==================== SQL工具模块',
        'end': '// ==================== 运维手册模块',
        'functions': ['switchSqlTab', 'reviewSQL', 'formatSQL', 'convertSQL', 'analyzeExplain', 'clearSQL']
    },
    'manuals.js': {
        'start': '// ==================== 运维手册模块',
        'end': '// ==================== 常用命令库模块',
        'functions': ['loadManuals', 'viewManual', 'downloadCurrentManual', 'deleteCurrentManual', 'loadManualContent', 'initManuals']
    },
    'commands.js': {
        'start': '// ==================== 常用命令库模块',
        'end': '// ==================== 集群拓扑模块',
        'functions': ['loadCommands', 'searchCommands', 'showAddCategoryDialog', 'addCategory', 'showAddCommandDialog', 'addCommand', 'copyCommand', 'copyText']
    },
    'topology.js': {
        'start': '// ==================== 集群拓扑模块',
        'end': '// ==================== API配置模块',
        'functions': ['loadClusters', 'selectCluster', 'renderTopology', 'showInstanceDetail', 'closeDetailPanel', 'getNodeColor', 'showAddClusterDialog', 'editClusterName', 'showAddServerDialog', 'showAddInstanceDialog', 'addCluster', 'addServer', 'showEditServerDialog', 'updateServer', 'showEditTenantDialog', 'updateTenant', 'showAddTenantDialog', 'addTenantToCluster', 'addInstance', 'showAddInstanceDialog', 'showEditInstanceDialog', 'updateInstance', 'deleteInstance', 'deleteCluster', 'deleteServer', 'deleteTenant', 'exportTopology']
    },
    'config.js': {
        'start': '// ==================== API配置模块',
        'end': '// ==================== 工具函数',
        'functions': ['loadConfig', 'renderModelsList', 'showAddModelDialog', 'hideModelForm', 'editModel', 'saveModelConfig', 'deleteModel', 'setDefaultModel', 'testModelConnection', 'saveConfig', 'testConnection', 'loadDBTypesPage', 'showAddDBTypeDialog', 'addDBType', 'deleteDBType', 'switchConfigTab', 'exportConfig', 'importConfig', 'loadLogs', 'loadLogModules', 'clearLogs']
    }
}

print("开始拆分 app.js...")
print(f"原始文件大小: {len(content)} 字符")

# 提取入口文件（保留主题、导航、初始化等）
entry_content = """/**
 * 数据库运维工具 - 前端入口文件
 */

// ==================== 全局变量 ====================
let currentModule = 'knowledge';
let dbTypes = [];
let currentClusterId = null;
let topologyNetwork = null;

// ==================== 主题切换 ====================
function initTheme() {
    const savedTheme = localStorage.getItem('db-tool-theme');
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
        localStorage.setItem('db-tool-theme', 'light');
        updateThemeUI(false);
    } else {
        document.documentElement.setAttribute('data-theme', 'dark');
        localStorage.setItem('db-tool-theme', 'dark');
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
    initNavigation();
    initKeyboardShortcuts();
    loadDBTypes();
    loadConfig();
    loadQATemplates();
    updateSidebarStats();
    loadQAHistory();
    loadDashboard();
    initManuals();
});

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
function initNavigation() {
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

    // 更新内容区显示
    document.querySelectorAll('.module').forEach(m => {
        m.style.display = 'none';
    });
    const moduleDiv = document.getElementById(`module-${module}`);
    if (moduleDiv) {
        moduleDiv.style.display = 'block';
    }

    currentModule = module;

    // 加载对应模块数据
    if (module === 'dashboard') {
        loadDashboard();
    } else if (module === 'topology') {
        loadClusters();
    } else if (module === 'config') {
        loadDBTypesPage();
        loadLogs();
    } else if (module === 'manuals') {
        loadManuals();
    } else if (module === 'commands') {
        loadCommands();
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
            'commands-db-type', 'cluster-db-type'
        ];

        selects.forEach(selectId => {
            const select = document.getElementById(selectId);
            if (!select) return;

            // 保留第一个选项
            const firstOption = select.options[0];
            select.innerHTML = '';
            select.appendChild(firstOption);

            dbTypes.forEach(type => {
                const option = document.createElement('option');
                option.value = type.id;
                option.textContent = `${type.icon || ''} ${type.name}`;
                select.appendChild(option);
            });

            // 默认选择 oracle（如果存在）
            const hasOracle = dbTypes.find(t => t.id === 'oracle');
            if (hasOracle) {
                select.value = 'oracle';
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
        const response = await fetch('/api/config/llm/models');
        const data = await response.json();
        const models = data.models || [];

        const selectIds = ['qa-model-select', 'sql-model-select'];
        selectIds.forEach(selectId => {
            const select = document.getElementById(selectId);
            if (!select) return;

            // 保留第一个选项
            const firstOption = select.options[0];
            select.innerHTML = '';
            select.appendChild(firstOption);

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
"""

with open('static/js/app.js', 'w', encoding='utf-8') as f:
    f.write(entry_content)

print("✅ 入口文件 (app.js) 已生成")
print(f"   大小: {len(entry_content)} 字符")

# 提取其他模块（简化版，实际应根据注释标记提取）
print("\n注意：由于原始文件已被覆盖，需要手动提取其他模块代码")
print("请从之前的对话记录中复制各模块代码到对应文件")
