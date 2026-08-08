/**
 * 系统配置模块
 */

let currentModels = [];
let editingModelId = null;

async function loadConfig() {
    try {
        // 先尝试获取多模型配置
        const response = await fetch('/api/config/llm/models');
        const data = await response.json();
        currentModels = data.models || [];

        // 如果没有模型配置，尝试兼容旧接口获取默认配置
        if (currentModels.length === 0) {
            try {
                const oldResponse = await fetch('/api/config/llm');
                const oldData = await oldResponse.json();
                if (oldData.api_url && oldData.api_key_masked) {
                    // 创建默认模型记录
                    currentModels = [{
                        id: 'default',
                        display_name: oldData.model_name || '默认模型',
                        model_name: oldData.model_name || '',
                        api_url: oldData.api_url,
                        api_key_masked: oldData.api_key_masked || '****',
                        is_default: true
                    }];
                }
            } catch (e) {
                // 忽略旧接口错误
            }
        }

        renderModelsList();
    } catch (error) {
        console.error('加载配置失败:', error);
    }
}

function renderModelsList() {
    const container = document.getElementById('models-list');
    if (!container) return;

    if (currentModels.length === 0) {
        container.innerHTML = `
            <div class="empty-message">
                暂无配置模型<br>
                <small>系统使用默认配置，点击上方按钮添加自定义模型</small>
            </div>`;
        return;
    }

    container.innerHTML = currentModels.map(model => `
        <div class="model-card ${model.is_default ? 'default' : ''}">
            <div class="model-info">
                <div class="model-name">${escapeHtml(model.display_name || model.model_name)}</div>
                <div class="model-detail">${escapeHtml(model.model_name)} | ${escapeHtml(model.api_url)}</div>
                ${model.is_default ? '<span class="model-badge default">默认</span>' : ''}
            </div>
            <div class="model-actions">
                <button class="btn btn-sm btn-primary" onclick="testModelConnection('${escapeJsAttr(model.id)}')">测试</button>
                <button class="btn btn-sm btn-secondary" onclick="editModel('${escapeJsAttr(model.id)}')">编辑</button>
                ${!model.is_default ? `<button class="btn btn-sm btn-success" onclick="setDefaultModel('${escapeJsAttr(model.id)}')">设为默认</button>` : ''}
                <button class="btn btn-sm btn-danger" onclick="deleteModel('${escapeJsAttr(model.id)}')">删除</button>
            </div>
        </div>
    `).join('');
}

function showAddModelDialog() {
    editingModelId = null;
    document.getElementById('model-form-title').textContent = '添加模型';
    document.getElementById('model-id').value = '';
    document.getElementById('model-display-name').value = '';
    document.getElementById('api-url').value = '';
    document.getElementById('api-key').value = '';
    document.getElementById('model-name').value = '';
    document.getElementById('model-form-container').style.display = 'block';
}

function hideModelForm() {
    document.getElementById('model-form-container').style.display = 'none';
    editingModelId = null;
}

function editModel(modelId) {
    const model = currentModels.find(m => m.id === modelId);
    if (!model) return;

    editingModelId = modelId;
    document.getElementById('model-form-title').textContent = '编辑模型';
    document.getElementById('model-id').value = modelId;
    document.getElementById('model-display-name').value = model.display_name || '';
    document.getElementById('api-url').value = model.api_url || '';
    document.getElementById('api-key').value = '';
    document.getElementById('api-key').placeholder = model.api_key_masked || '请输入新的API Key';
    document.getElementById('model-name').value = model.model_name || '';
    document.getElementById('model-form-container').style.display = 'block';
}

async function saveModelConfig() {
    const modelId = document.getElementById('model-id').value;
    const displayName = document.getElementById('model-display-name').value.trim();
    const apiUrl = document.getElementById('api-url').value.trim();
    const apiKey = document.getElementById('api-key').value.trim();
    const modelName = document.getElementById('model-name').value.trim();

    if (!displayName) {
        showToast('请输入显示名称', 'error');
        return;
    }
    if (!apiUrl) {
        showToast('请输入API地址', 'error');
        return;
    }
    if (!apiKey && !modelId) {
        showToast('请输入API Key', 'error');
        return;
    }
    if (!modelName) {
        showToast('请输入模型名称', 'error');
        return;
    }

    const body = {
        id: modelId || undefined,
        display_name: displayName,
        api_url: apiUrl,
        model_name: modelName
    };

    // 如果提供了api_key，则包含在请求中
    if (apiKey) {
        body.api_key = apiKey;
    }

    try {
        const response = await fetch('/api/config/llm/models', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body)
        });

        const data = await response.json();

        if (response.ok) {
            showToast(data.message || '保存成功', 'success');
            hideModelForm();
            loadConfig();
            // 刷新 QA 和 SQL 工具中的模型下拉框
            loadModelSelects();
        } else {
            showToast(data.error || '保存失败', 'error');
        }
    } catch (error) {
        showToast('保存失败', 'error');
    }
}

async function deleteModel(modelId) {
    if (!confirm('确定要删除这个模型配置吗？')) {
        return;
    }

    try {
        const response = await fetch(`/api/config/llm/models/${modelId}`, {
            method: 'DELETE'
        });

        if (response.ok) {
            showToast('删除成功', 'success');
            loadConfig();
            // 刷新 QA 和 SQL 工具中的模型下拉框
            loadModelSelects();
        } else {
            showToast('删除失败', 'error');
        }
    } catch (error) {
        showToast('删除失败', 'error');
    }
}

async function setDefaultModel(modelId) {
    try {
        const response = await fetch(`/api/config/llm/models/${modelId}/default`, {
            method: 'POST'
        });

        if (response.ok) {
            showToast('设置默认模型成功', 'success');
            loadConfig();
            // 刷新 QA 和 SQL 工具中的模型下拉框
            loadModelSelects();
        } else {
            showToast('设置失败', 'error');
        }
    } catch (error) {
        showToast('设置失败', 'error');
    }
}

async function testModelConnection(modelId) {
    const resultDiv = document.getElementById('config-test-result');
    resultDiv.style.display = 'block';
    resultDiv.className = 'test-result';
    resultDiv.textContent = '测试中...';

    try {
        const response = await fetch('/api/config/test', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ model_id: modelId })
        });
        const data = await response.json();

        if (response.ok) {
            resultDiv.className = 'test-result success';
            resultDiv.textContent = '连接成功！模型回复: ' + data.response;
        } else {
            resultDiv.className = 'test-result error';
            resultDiv.textContent = data.error || '连接失败';
        }
    } catch (error) {
        resultDiv.className = 'test-result error';
        resultDiv.textContent = '测试失败: ' + error.message;
    }
}

// 兼容旧接口
async function saveConfig() {
    await saveModelConfig();
}

async function testConnection() {
    // 测试默认模型
    await testModelConnection();
}

// 数据库类型管理
async function loadDBTypesPage() {
    try {
        const response = await fetch('/api/db-types');
        const data = await response.json();
        const gridDiv = document.getElementById('dbtypes-grid');

        if (data.types && data.types.length > 0) {
            gridDiv.innerHTML = data.types.map(type => `
                <div class="dbtype-card">
                    <div class="dbtype-icon">${type.icon || '📁'}</div>
                    <div class="dbtype-info">
                        <div class="dbtype-name">${escapeHtml(type.name)}</div>
                        <div class="dbtype-id">${escapeHtml(type.id)}</div>
                    </div>
                    <button class="btn btn-sm btn-danger" onclick="deleteDBType('${escapeJsAttr(type.id)}')">
                        删除
                    </button>
                </div>
            `).join('');
        } else {
            gridDiv.innerHTML = '<div class="empty-message">暂无数据库类型</div>';
        }
    } catch (error) {
        showToast('加载数据库类型失败', 'error');
    }
}

function showAddDBTypeDialog() {
    document.getElementById('dbtype-id').value = '';
    document.getElementById('dbtype-name').value = '';
    document.getElementById('dbtype-icon').value = '📁';
    document.getElementById('modal-add-dbtype').style.display = 'flex';
}

async function addDBType() {
    const id = document.getElementById('dbtype-id').value.trim().toLowerCase();
    const name = document.getElementById('dbtype-name').value.trim();
    const icon = document.getElementById('dbtype-icon').value.trim() || '📁';

    if (!id || !name) {
        showToast('请填写数据库ID和名称', 'error');
        return;
    }

    if (!/^[a-z0-9_]+$/.test(id)) {
        showToast('ID只能包含字母、数字和下划线', 'error');
        return;
    }

    try {
        const response = await fetch('/api/db-types', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ id, name, icon })
        });

        const data = await response.json();

        if (response.ok) {
            showToast('添加成功', 'success');
            closeModal('modal-add-dbtype');
            loadDBTypesPage();
            loadDBTypes(); // 刷新下拉框
        } else {
            showToast(data.error || '添加失败', 'error');
        }
    } catch (error) {
        showToast('添加失败', 'error');
    }
}

async function deleteDBType(id) {
    if (!confirm(`确定要删除数据库类型 "${id}" 吗？`)) return;

    try {
        const response = await fetch(`/api/db-types/${id}`, { method: 'DELETE' });

        if (response.ok) {
            showToast('删除成功', 'success');
            loadDBTypesPage();
            loadDBTypes(); // 刷新下拉框
        } else {
            showToast('删除失败', 'error');
        }
    } catch (error) {
        showToast('删除失败', 'error');
    }
}

// 配置导入导出
async function exportConfig() {
    try {
        const response = await fetch('/api/config/export');
        const data = await response.json();

        const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `config_${new Date().toISOString().slice(0, 10)}.json`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);

        showToast('配置已导出', 'success');
    } catch (error) {
        showToast('导出失败', 'error');
    }
}

// 配置导入
document.getElementById('config-import-file').addEventListener('change', async function(e) {
    const file = e.target.files[0];
    if (!file) return;

    try {
        const text = await file.text();
        const data = JSON.parse(text);

        const response = await fetch('/api/config/import', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });

        if (response.ok) {
            showToast('导入成功', 'success');
            loadDBTypes(); // 刷新下拉框
        } else {
            showToast('导入失败', 'error');
        }
    } catch (error) {
        showToast('导入失败，请检查文件格式', 'error');
    }

    this.value = '';
});

// 系统配置 Tab 切换
function switchConfigTab(tab) {
    // 更新标签按钮状态
    document.querySelectorAll('.config-tabs .tab-btn').forEach(btn => {
        btn.classList.remove('active');
    });
    event.target.classList.add('active');

    // 切换内容显示
    document.querySelectorAll('.config-tab-content').forEach(content => {
        content.classList.remove('active');
    });
    document.getElementById(`config-tab-${tab}`).classList.add('active');

    // 加载对应数据
    if (tab === 'logs') {
        loadLogs();
    } else if (tab === 'dbtypes') {
        loadDBTypesPage();
    } else if (tab === 'features') {
        loadFeatureConfig();
    } else if (tab === 'project') {
        loadDoc('PROJECT.md', 'project-doc-content');
    } else if (tab === 'changelog') {
        loadDoc('version_update.md', 'changelog-content');
    }
}

// 操作日志
async function loadLogs() {
    const module = document.getElementById('log-module-filter').value;

    try {
        const url = `/api/logs?limit=100${module ? `&module=${module}` : ''}`;
        const response = await fetch(url);
        const data = await response.json();
        const tbody = document.getElementById('logs-list');

        if (data.logs && data.logs.length > 0) {
            tbody.innerHTML = data.logs.map(log => `
                <tr>
                    <td>${escapeHtml(log.timestamp)}</td>
                    <td>${escapeHtml(log.module)}</td>
                    <td>${escapeHtml(log.action)}</td>
                    <td>${escapeHtml(log.detail || '-')}</td>
                    <td><span class="status-${escapeHtml(log.status)}">${escapeHtml(log.status)}</span></td>
                </tr>
            `).join('');
        } else {
            tbody.innerHTML = '<tr><td colspan="5" class="empty-message">暂无操作记录</td></tr>';
        }

        // 加载模块列表
        loadLogModules();
    } catch (error) {
        showToast('加载日志失败', 'error');
    }
}

async function loadLogModules() {
    try {
        const response = await fetch('/api/logs/modules');
        const data = await response.json();
        const select = document.getElementById('log-module-filter');

        // 保留第一个选项
        const firstOption = select.options[0];
        select.innerHTML = '';
        select.appendChild(firstOption);

        if (data.modules) {
            data.modules.forEach(module => {
                const option = document.createElement('option');
                option.value = module;
                option.textContent = module;
                select.appendChild(option);
            });
        }
    } catch (error) {
        console.error('加载日志模块失败:', error);
    }
}

async function clearLogs() {
    if (!confirm('确定要清空所有操作日志吗？')) return;

    try {
        const response = await fetch('/api/logs', { method: 'DELETE' });

        if (response.ok) {
            showToast('日志已清空', 'success');
            loadLogs();
        } else {
            showToast('清空失败', 'error');
        }
    } catch (error) {
        showToast('清空失败', 'error');
    }
}

// ==================== 功能配置 ====================

async function loadFeatureConfig() {
    const container = document.getElementById('feature-config-list');
    if (!container) return;

    try {
        const response = await fetch('/api/config/features');
        const data = await response.json();

        if (data.features) {
            container.innerHTML = data.features.map(feature => `
                <div class="feature-config-item">
                    <div class="feature-config-info">
                        <div class="feature-config-icon">${escapeHtml(feature.module_icon)}</div>
                        <div class="feature-config-name">${escapeHtml(feature.module_name)}</div>
                    </div>
                    <label class="toggle-switch">
                        <input type="checkbox"
                               ${feature.is_enabled ? 'checked' : ''}
                               onchange="toggleFeature('${escapeJsAttr(feature.module_id)}', this.checked)">
                        <span class="toggle-slider"></span>
                    </label>
                </div>
            `).join('');
        }
    } catch (error) {
        console.error('加载功能配置失败:', error);
        container.innerHTML = '<div class="empty-message">加载失败</div>';
    }
}

async function toggleFeature(moduleId, isEnabled) {
    try {
        const response = await fetch(`/api/config/features/${moduleId}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ is_enabled: isEnabled })
        });

        if (response.ok) {
            showToast(isEnabled ? '已启用' : '已禁用', 'success');
            // 刷新导航栏
            await refreshNavigation();
        } else {
            showToast('更新失败', 'error');
        }
    } catch (error) {
        showToast('更新失败', 'error');
    }
}

async function refreshNavigation() {
    try {
        const response = await fetch('/api/config/features');
        const data = await response.json();

        if (data.features) {
            // 更新左侧导航栏显示
            data.features.forEach(feature => {
                const navItem = document.querySelector(`.nav-item[data-module="${feature.module_id}"]`);
                if (navItem) {
                    navItem.style.display = feature.is_enabled ? 'flex' : 'none';
                }
            });
        }
    } catch (error) {
        console.error('刷新导航栏失败:', error);
    }
}
