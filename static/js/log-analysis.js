/**
 * 日志分析模块
 */

let currentAnalysisTaskId = null;
let currentAnalysisAbortController = null;

// 每个任务的步骤时间记录，格式: { taskId: { stepTimes: {}, stepStartTimes: {} } }
const taskStepData = {};

function getTaskStepData(taskId) {
    if (!taskStepData[taskId]) {
        taskStepData[taskId] = {
            stepTimes: {},
            stepStartTimes: {}
        };
    }
    return taskStepData[taskId];
}

function clearTaskStepData(taskId) {
    delete taskStepData[taskId];
}

// ==================== 任务列表 ====================

async function loadLogAnalysis() {
    try {
        const response = await fetch('/api/log-analysis/tasks');
        const data = await response.json();
        renderTaskList(data.tasks || []);
    } catch (error) {
        console.error('加载日志分析任务失败:', error);
        document.getElementById('log-analysis-list').innerHTML =
            '<div class="empty-message">加载失败，请刷新重试</div>';
    }
}

// 检查是否在查看进度或报告页面
function isViewingProgressOrReport() {
    const progressEl = document.getElementById('log-analysis-progress');
    const reportEl = document.getElementById('log-analysis-report');
    return (progressEl && progressEl.style.display === 'block') ||
           (reportEl && reportEl.style.display === 'block');
}

// 切换到列表视图（用于模块切换时重置状态）
function showLogAnalysisListView() {
    const listEl = document.getElementById('log-analysis-list');
    const progressEl = document.getElementById('log-analysis-progress');
    const reportEl = document.getElementById('log-analysis-report');
    const backBtn = document.getElementById('log-analysis-back-btn');
    const newBtn = document.getElementById('log-analysis-new-btn');
    const activeArea = document.getElementById('log-analysis-active-area');
    const historyTitle = document.getElementById('log-analysis-history-title');

    if (listEl) listEl.style.display = 'block';
    if (progressEl) progressEl.style.display = 'none';
    if (reportEl) reportEl.style.display = 'none';
    if (backBtn) backBtn.style.display = 'none';
    if (newBtn) newBtn.style.display = 'inline-block';
    if (activeArea) activeArea.style.display = 'block';
    if (historyTitle) historyTitle.style.display = 'block';

    // 刷新列表数据
    loadLogAnalysis();
}

function renderTaskList(tasks) {
    const container = document.getElementById('log-analysis-list');
    const activeContainer = document.getElementById('log-analysis-active-list');
    const activeArea = document.getElementById('log-analysis-active-area');
    const historyTitle = document.getElementById('log-analysis-history-title');

    // 如果正在查看进度或报告页面，不要显示列表区域
    if (isViewingProgressOrReport()) {
        return;
    }

    // 分离分析中和其他任务
    const activeTasks = tasks.filter(t => t.status === 'analyzing');
    const historyTasks = tasks.filter(t => t.status !== 'analyzing');

    // 渲染分析中区域（始终显示标题）
    if (activeArea) {
        activeArea.style.display = 'block';
    }
    if (activeContainer) {
        if (activeTasks.length > 0) {
            activeContainer.innerHTML = activeTasks.map(task => renderActiveTaskCard(task)).join('');
        } else {
            activeContainer.innerHTML = '<div class="empty-message" style="padding: 20px; text-align: center; color: var(--text-muted);">暂无分析中的任务</div>';
        }
    }

    // 渲染历史任务
    if (historyTitle) {
        historyTitle.style.display = 'block';
    }

    if (historyTasks.length === 0) {
        container.innerHTML = '<div class="empty-message">暂无历史分析报告</div>';
    } else {
        container.innerHTML = historyTasks.map(task => renderHistoryTaskCard(task)).join('');
    }
}

function renderActiveTaskCard(task) {
    const filesInfo = task.files_info || [];
    const dbTypeHtml = task.db_type ? `<span class="db-type-tag">🗄️ ${escapeHtml(task.db_type)}</span>` : '';
    const filesHtml = filesInfo.length > 0
        ? `<div class="task-files">
            <span class="file-count">📎 ${filesInfo.length}个文件:</span>
            <div class="file-names">
                ${filesInfo.map(f => `<span class="file-tag">📄 ${escapeHtml(f.filename)}</span>`).join('')}
            </div>
           </div>`
        : '';

    return `
        <div class="task-card active-task-card" data-task-id="${task.id}" onclick="viewTaskProgress('${task.id}')">
            <div class="task-header">
                <h4>${escapeHtml(task.name)}</h4>
                <span class="task-status status-analyzing">🔬 分析中</span>
            </div>
            <div class="task-meta">
                <span>💬 ${escapeHtml(task.question || '')}</span>
                <span>📅 ${formatDate(task.created_at)}</span>
            </div>
            <div class="task-db-type">${dbTypeHtml}</div>
            ${filesHtml}
            <div class="task-actions">
                <button class="btn btn-sm btn-primary" onclick="event.stopPropagation(); viewTaskProgress('${task.id}')">查看进度</button>
            </div>
        </div>
    `;
}

function renderHistoryTaskCard(task) {
    const statusIcon = getStatusIcon(task.status);
    const statusText = getStatusText(task.status);
    const filesInfo = task.files_info || [];
    const dbTypeHtml = task.db_type ? `<span class="db-type-tag">🗄️ ${escapeHtml(task.db_type)}</span>` : '';
    const filesHtml = filesInfo.length > 0
        ? `<div class="task-files">
            <span class="file-count">📎 ${filesInfo.length}个文件:</span>
            <div class="file-names">
                ${filesInfo.map(f => `<span class="file-tag">📄 ${escapeHtml(f.filename)}</span>`).join('')}
            </div>
           </div>`
        : '';

    let actionButton = '';
    if (task.status === 'analyzing') {
        actionButton = `<button class="btn btn-sm btn-primary" onclick="viewTaskProgress('${task.id}')">查看进度</button>`;
    } else if (task.status === 'completed') {
        actionButton = `<button class="btn btn-sm btn-primary" onclick="viewTaskReport('${task.id}')">查看报告</button>`;
    } else if (task.status === 'failed') {
        actionButton = `<button class="btn btn-sm btn-primary" onclick="viewTaskReport('${task.id}')">查看详情</button>`;
    } else {
        actionButton = `<button class="btn btn-sm btn-primary" onclick="viewTaskReport('${task.id}')">查看报告</button>`;
    }

    return `
        <div class="task-card" data-task-id="${task.id}">
            <div class="task-header">
                <h4>${escapeHtml(task.name)}</h4>
                <span class="task-status status-${task.status}">${statusIcon} ${statusText}</span>
            </div>
            <div class="task-meta">
                <span>💬 ${escapeHtml(task.question || '')}</span>
                <span>📅 ${formatDate(task.created_at)}</span>
            </div>
            <div class="task-db-type">${dbTypeHtml}</div>
            ${filesHtml}
            <div class="task-actions">
                ${actionButton}
                <button class="btn btn-sm btn-danger" onclick="deleteAnalysisTask('${task.id}')">删除</button>
            </div>
        </div>
    `;
}

function getStatusIcon(status) {
    const icons = {
        'pending': '⏳',
        'analyzing': '🔬',
        'completed': '✅',
        'failed': '❌'
    };
    return icons[status] || '📋';
}

function getStatusText(status) {
    const texts = {
        'pending': '待分析',
        'analyzing': '分析中',
        'completed': '已完成',
        'failed': '失败'
    };
    return texts[status] || status;
}

function formatDate(dateStr) {
    if (!dateStr) return '未知';
    const date = new Date(dateStr);
    return date.toLocaleString('zh-CN');
}

// ==================== 新建分析 ====================

function showNewAnalysisDialog() {
    const nameInput = document.getElementById('log-analysis-name');
    const questionInput = document.getElementById('log-analysis-question');
    const filesInput = document.getElementById('log-analysis-files');
    const dbTypeSelect = document.getElementById('log-analysis-db-type');
    const dialog = document.getElementById('log-analysis-new-dialog');

    if (nameInput) nameInput.value = '';
    if (questionInput) questionInput.value = '';
    if (filesInput) filesInput.value = '';
    if (dialog) dialog.style.display = 'flex';

    // 填充数据库类型下拉框
    if (dbTypeSelect) {
        dbTypeSelect.innerHTML = '<option value="">请选择数据库类型</option>';
        // dbTypes 是全局变量，在 app.js 中加载
        if (typeof dbTypes !== 'undefined' && dbTypes.length > 0) {
            dbTypes.forEach(type => {
                const option = document.createElement('option');
                option.value = type.id;
                option.textContent = `${type.icon || ''} ${type.name}`;
                dbTypeSelect.appendChild(option);
            });
        }
    }

    // 清空文件预览
    updateFilePreview();
}

function updateFilePreview() {
    const filesInput = document.getElementById('log-analysis-files');
    const previewContainer = document.getElementById('log-analysis-file-list');

    if (!previewContainer || !filesInput) return;

    if (filesInput.files && filesInput.files.length > 0) {
        previewContainer.innerHTML = Array.from(filesInput.files).map(file => `
            <div class="file-preview-item">
                <span class="file-icon">📄</span>
                <span class="file-name">${escapeHtml(file.name)}</span>
                <span class="file-size">${formatFileSize(file.size)}</span>
            </div>
        `).join('');
    } else {
        previewContainer.innerHTML = '';
    }
}

async function createAnalysisTask() {
    const nameInput = document.getElementById('log-analysis-name');
    const questionInput = document.getElementById('log-analysis-question');
    const filesInput = document.getElementById('log-analysis-files');
    const dbTypeSelect = document.getElementById('log-analysis-db-type');

    const name = nameInput ? nameInput.value.trim() : '';
    const question = questionInput ? questionInput.value.trim() : '';
    const db_type = dbTypeSelect ? dbTypeSelect.value : '';

    if (!name) {
        showToast('请输入任务名称', 'error');
        return;
    }
    if (!question) {
        showToast('请输入分析问题描述', 'error');
        return;
    }

    // 创建任务
    try {
        const response = await fetch('/api/log-analysis/tasks', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name, question, db_type })
        });

        if (!response.ok) {
            const data = await response.json();
            showToast(data.error || '创建任务失败', 'error');
            return;
        }

        const data = await response.json();
        const taskId = data.task.id;

        // 上传文件
        if (filesInput && filesInput.files && filesInput.files.length > 0) {
            const formData = new FormData();
            for (const file of filesInput.files) {
                formData.append('files', file);
            }

            const uploadResponse = await fetch(`/api/log-analysis/upload/${taskId}`, {
                method: 'POST',
                body: formData
            });

            if (!uploadResponse.ok) {
                const uploadData = await uploadResponse.json();
                showToast(uploadData.error || '上传文件失败', 'error');
                return;
            }
        }

        const dialog = document.getElementById('log-analysis-new-dialog');
        if (dialog) dialog.style.display = 'none';
        showToast('任务创建成功，开始分析', 'success');

        // 立即更新任务状态为分析中，然后刷新列表
        // 这样任务会显示在【分析中】区域
        try {
            await fetch(`/api/log-analysis/tasks/${taskId}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ status: 'analyzing' })
            });
        } catch (e) {
            console.error('更新任务状态失败:', e);
        }

        // 刷新列表显示分析中任务（回到列表视图）
        loadLogAnalysis();

        // 自动跳转到进度视图，让用户实时看到分析进度
        viewTaskProgress(taskId);

    } catch (error) {
        console.error('创建任务失败:', error);
        showToast('创建任务失败', 'error');
    }
}

// ==================== 分析执行 ====================

async function startAnalysis(taskId) {
    currentAnalysisTaskId = taskId;

    // 获取或创建该任务的步骤数据
    const taskData = getTaskStepData(taskId);
    taskData.stepTimes = {};
    taskData.stepStartTimes = {};

    // 显示进度面板，隐藏所有列表区域
    const listEl = document.getElementById('log-analysis-list');
    const progressEl = document.getElementById('log-analysis-progress');
    const reportEl = document.getElementById('log-analysis-report');
    const backBtn = document.getElementById('log-analysis-back-btn');
    const newBtn = document.getElementById('log-analysis-new-btn');
    const activeArea = document.getElementById('log-analysis-active-area');
    const historyTitle = document.getElementById('log-analysis-history-title');

    if (listEl) listEl.style.display = 'none';
    if (progressEl) progressEl.style.display = 'block';
    if (reportEl) reportEl.style.display = 'none';
    if (backBtn) backBtn.style.display = 'inline-block';
    if (newBtn) newBtn.style.display = 'none';
    if (activeArea) activeArea.style.display = 'none';
    if (historyTitle) historyTitle.style.display = 'none';

    // 重置进度状态
    resetProgressSteps();

    // 创建 AbortController 用于取消请求
    currentAnalysisAbortController = new AbortController();

    try {
        const response = await fetch(`/api/log-analysis/analyze/${taskId}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ use_rag: true }),
            signal: currentAnalysisAbortController.signal
        });

        const reader = response.body.getReader();
        const decoder = new TextDecoder();

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            const chunk = decoder.decode(value);
            const lines = chunk.split('\n');

            for (const line of lines) {
                if (line.startsWith('data: ')) {
                    const data = line.slice(6).trim();
                    if (data === '[DONE]') continue;

                    try {
                        const parsed = JSON.parse(data);
                        handleAnalysisEvent(parsed, taskId);
                    } catch (e) {
                        // 忽略解析错误
                    }
                }
            }
        }

    } catch (error) {
        if (error.name === 'AbortError') {
            console.log('分析请求被取消');
        } else {
            console.error('分析过程出错:', error);
            showToast('分析过程出错: ' + error.message, 'error');
        }
    } finally {
        currentAnalysisAbortController = null;
    }
}

function handleAnalysisEvent(data, taskId) {
    if (data.stage && data.status) {
        // 获取该任务的步骤数据
        const taskData = getTaskStepData(taskId);

        // 记录步骤开始时间
        if (data.status === 'analyzing' && !taskData.stepStartTimes[data.stage]) {
            taskData.stepStartTimes[data.stage] = Date.now();
        }

        // 记录步骤完成时间
        if (data.status === 'complete' && taskData.stepStartTimes[data.stage]) {
            const endTime = Date.now();
            taskData.stepTimes[data.stage] = endTime - taskData.stepStartTimes[data.stage];
        }

        updateProgressStep(data.stage, data.status, data.message, taskId);

        if (data.status === 'complete' && data.stage === 'report') {
            // 分析完成，如果用户仍在查看进度页面，则自动切换到报告
            const progressEl = document.getElementById('log-analysis-progress');
            if (progressEl && progressEl.style.display === 'block') {
                setTimeout(() => {
                    viewTaskReport(taskId);
                }, 500);
            }
            // 重置当前分析任务ID
            currentAnalysisTaskId = null;

            // 刷新列表（延迟执行，确保数据库已更新）
            setTimeout(() => {
                loadLogAnalysis();
            }, 1000);
        }
    }
}

function resetProgressSteps() {
    const steps = ['intent', 'filter', 'analysis', 'report'];
    steps.forEach(step => {
        const stepEl = document.getElementById(`step-${step}`);
        if (stepEl) {
            stepEl.className = 'progress-step';
            const statusSpan = stepEl.querySelector('.step-status');
            if (statusSpan) {
                statusSpan.textContent = '等待中';
            }
        }
        // 重置时间显示
        const timeEl = document.getElementById(`step-time-${step}`);
        if (timeEl) {
            timeEl.textContent = '';
        }
    });
    const statusEl = document.getElementById('log-analysis-status');
    if (statusEl) {
        statusEl.textContent = '准备中...';
    }
    const infoDiv = document.getElementById('log-analysis-current-info');
    if (infoDiv) {
        infoDiv.innerHTML = '';
    }
}

// 恢复之前记录的进度状态（用于重新进入进度视图时）
function restoreProgressSteps(taskId) {
    const taskData = getTaskStepData(taskId);
    const steps = ['intent', 'filter', 'analysis', 'report'];

    steps.forEach(step => {
        const stepEl = document.getElementById(`step-${step}`);
        if (!stepEl) return;

        // 根据是否有完成时间来确定状态
        if (taskData.stepTimes[step]) {
            // 已完成
            stepEl.className = 'progress-step completed';
            const statusSpan = stepEl.querySelector('.step-status');
            if (statusSpan) {
                statusSpan.textContent = '已完成';
            }
            // 恢复时间显示
            const timeEl = document.getElementById(`step-time-${step}`);
            if (timeEl) {
                const seconds = (taskData.stepTimes[step] / 1000).toFixed(1);
                timeEl.textContent = `⏱️ ${seconds}s`;
            }
        } else if (taskData.stepStartTimes[step]) {
            // 正在进行中
            stepEl.className = 'progress-step active';
            const statusSpan = stepEl.querySelector('.step-status');
            if (statusSpan) {
                statusSpan.textContent = '分析中...';
            }
        } else {
            // 等待中
            stepEl.className = 'progress-step';
            const statusSpan = stepEl.querySelector('.step-status');
            if (statusSpan) {
                statusSpan.textContent = '等待中';
            }
        }
    });

    // 恢复状态文本
    const statusEl = document.getElementById('log-analysis-status');
    if (statusEl) {
        // 找到最后一个已完成的步骤
        const completedSteps = steps.filter(step => taskData.stepTimes[step]);
        if (completedSteps.length > 0) {
            const lastStep = completedSteps[completedSteps.length - 1];
            const stageNames = {
                'intent': '意图识别',
                'filter': '日志筛选',
                'analysis': '根因分析',
                'report': '报告生成'
            };
            statusEl.textContent = `${stageNames[lastStep]} 已完成...`;
        } else if (Object.keys(taskData.stepStartTimes).length > 0) {
            statusEl.textContent = '分析进行中...';
        } else {
            statusEl.textContent = '准备中...';
        }
    }

    // 恢复详细信息区域
    const infoDiv = document.getElementById('log-analysis-current-info');
    if (infoDiv) {
        infoDiv.innerHTML = '';
        steps.forEach(step => {
            if (taskData.stepTimes[step] && step !== 'report') {
                const stageNames = {
                    'intent': '意图识别',
                    'filter': '日志筛选',
                    'analysis': '根因分析'
                };
                const timeStr = ` (${(taskData.stepTimes[step] / 1000).toFixed(1)}s)`;
                infoDiv.innerHTML += `<div class="info-item">✅ ${stageNames[step]} 完成${timeStr}</div>`;
            }
        });
    }
}

function updateProgressStep(stage, status, message, taskId) {
    const stepEl = document.getElementById(`step-${stage}`);
    if (!stepEl) {
        console.warn(`Progress step element not found: step-${stage}`);
        return;
    }

    const statusMap = {
        'analyzing': { className: 'progress-step active', text: '分析中...' },
        'complete': { className: 'progress-step completed', text: '已完成' },
        'error': { className: 'progress-step error', text: '失败' }
    };

    const statusInfo = statusMap[status] || statusMap['analyzing'];
    stepEl.className = statusInfo.className;

    const statusSpan = stepEl.querySelector('.step-status');
    if (statusSpan) {
        statusSpan.textContent = statusInfo.text;
    }

    // 更新时间显示 - 使用任务特定的步骤数据
    const timeEl = document.getElementById(`step-time-${stage}`);
    if (timeEl && taskId) {
        const taskData = getTaskStepData(taskId);
        if (taskData.stepTimes[stage]) {
            const seconds = (taskData.stepTimes[stage] / 1000).toFixed(1);
            timeEl.textContent = `⏱️ ${seconds}s`;
        }
    }

    if (message) {
        const statusEl = document.getElementById('log-analysis-status');
        if (statusEl) {
            statusEl.textContent = message;
        }
    }

    // 显示当前阶段的详细信息
    if (status === 'complete' && stage !== 'report' && taskId) {
        const infoDiv = document.getElementById('log-analysis-current-info');
        if (infoDiv) {
            const taskData = getTaskStepData(taskId);
            const timeStr = taskData.stepTimes[stage] ? ` (${(taskData.stepTimes[stage] / 1000).toFixed(1)}s)` : '';
            infoDiv.innerHTML += `<div class="info-item">✅ ${message || stage + ' 完成'}${timeStr}</div>`;
        }
    }
}

// ==================== 查看进度 ====================

async function viewTaskProgress(taskId) {
    try {
        const response = await fetch(`/api/log-analysis/tasks/${taskId}`);
        if (!response.ok) {
            showToast('获取任务失败', 'error');
            return;
        }

        const data = await response.json();
        const task = data.task;

        if (!task) {
            showToast('任务不存在', 'error');
            return;
        }

        // 显示进度面板，隐藏列表区域
        const listEl = document.getElementById('log-analysis-list');
        const progressEl = document.getElementById('log-analysis-progress');
        const reportEl = document.getElementById('log-analysis-report');
        const backBtn = document.getElementById('log-analysis-back-btn');
        const newBtn = document.getElementById('log-analysis-new-btn');
        const activeArea = document.getElementById('log-analysis-active-area');
        const historyTitle = document.getElementById('log-analysis-history-title');

        if (listEl) listEl.style.display = 'none';
        if (progressEl) progressEl.style.display = 'block';
        if (reportEl) reportEl.style.display = 'none';
        if (backBtn) backBtn.style.display = 'inline-block';
        if (newBtn) newBtn.style.display = 'none';
        if (activeArea) activeArea.style.display = 'none';
        if (historyTitle) historyTitle.style.display = 'none';

        // 如果任务正在分析中，启动SSE连接实时显示进度
        if (task.status === 'analyzing') {
            // 只有在没有正在运行的分析时才启动
            if (currentAnalysisTaskId !== taskId || !currentAnalysisAbortController) {
                startAnalysis(taskId);
            } else {
                // 已经在分析这个任务，恢复之前的进度显示
                restoreProgressSteps(taskId);
            }
        } else {
            // 渲染分析进度（已完成或失败）
            const reportContent = document.getElementById('log-analysis-report-content');
            if (reportContent) {
                reportContent.innerHTML = renderAnalyzingProgress(task);
            }
        }

    } catch (error) {
        console.error('查看进度失败:', error);
        showToast('查看进度失败', 'error');
    }
}

// ==================== 报告查看 ====================

async function viewTaskReport(taskId) {
    try {
        const response = await fetch(`/api/log-analysis/tasks/${taskId}`);
        if (!response.ok) {
            showToast('获取报告失败', 'error');
            return;
        }

        const data = await response.json();
        const task = data.task;

        if (!task) {
            showToast('任务不存在', 'error');
            return;
        }

        // 如果任务正在分析中，显示进度页面
        if (task.status === 'analyzing') {
            // 避免重复启动分析
            if (currentAnalysisTaskId !== taskId) {
                viewTaskProgress(taskId);
            } else {
                // 已经在分析这个任务，直接显示进度页面
                const listEl = document.getElementById('log-analysis-list');
                const progressEl = document.getElementById('log-analysis-progress');
                const reportEl = document.getElementById('log-analysis-report');
                const backBtn = document.getElementById('log-analysis-back-btn');
                const newBtn = document.getElementById('log-analysis-new-btn');
                const activeArea = document.getElementById('log-analysis-active-area');
                const historyTitle = document.getElementById('log-analysis-history-title');

                if (listEl) listEl.style.display = 'none';
                if (progressEl) progressEl.style.display = 'block';
                if (reportEl) reportEl.style.display = 'none';
                if (backBtn) backBtn.style.display = 'inline-block';
                if (newBtn) newBtn.style.display = 'none';
                if (activeArea) activeArea.style.display = 'none';
                if (historyTitle) historyTitle.style.display = 'none';
            }
            return;
        }

        // 显示报告面板
        const listEl = document.getElementById('log-analysis-list');
        const progressEl = document.getElementById('log-analysis-progress');
        const reportEl = document.getElementById('log-analysis-report');
        const backBtn = document.getElementById('log-analysis-back-btn');
        const newBtn = document.getElementById('log-analysis-new-btn');
        const activeArea = document.getElementById('log-analysis-active-area');
        const historyTitle = document.getElementById('log-analysis-history-title');

        if (listEl) listEl.style.display = 'none';
        if (progressEl) progressEl.style.display = 'none';
        if (reportEl) reportEl.style.display = 'block';
        if (backBtn) backBtn.style.display = 'inline-block';
        if (newBtn) newBtn.style.display = 'none';
        if (activeArea) activeArea.style.display = 'none';
        if (historyTitle) historyTitle.style.display = 'none';

        // 渲染报告
        const reportContent = document.getElementById('log-analysis-report-content');
        if (reportContent) {
            if (task.report) {
                // 添加耗时统计到报告开头
                const timingHtml = generateTimingHtml(task);
                reportContent.innerHTML = timingHtml + formatMarkdown(task.report);
            } else {
                reportContent.innerHTML = '<div class="empty-message">暂无报告</div>';
            }
        }

    } catch (error) {
        console.error('查看报告失败:', error);
        showToast('查看报告失败', 'error');
    }
}

function renderAnalyzingProgress(task) {
    return `
        <div class="loading" style="text-align: center; padding: 40px;">
            <div style="font-size: 3rem; margin-bottom: 20px;">🔬</div>
            <h3>分析进行中...</h3>
            <p style="color: var(--text-secondary); margin-top: 10px;">
                当前阶段: ${task.current_stage || '意图识别'}
            </p>
            <p style="color: var(--text-muted); font-size: 0.85rem; margin-top: 10px;">
                分析可能需要几分钟时间，请稍候...
            </p>
            <div style="margin-top: 20px;">
                <div class="progress-bar-container" style="width: 100%; height: 8px; background-color: var(--border-color); border-radius: 4px; overflow: hidden;">
                    <div class="progress-bar" style="width: 60%; height: 100%; background: linear-gradient(135deg, #1e3c72 0%, #2a5298 100%); border-radius: 4px; animation: pulse 2s infinite;"></div>
                </div>
            </div>
        </div>
    `;
}

function generateTimingHtml(task) {
    try {
        // 从后端 stages 字段获取耗时数据（每个任务独立的持久化数据）
        let timingSource = {};

        // 解析 stages JSON
        const stages = JSON.parse(task.stages || '{}');
        if (stages && typeof stages === 'object') {
            // 从 stages 对象中提取每个阶段的耗时信息
            Object.keys(stages).forEach(stage => {
                const stageData = stages[stage];
                if (stageData && stageData.duration) {
                    // 后端存储的 duration 是毫秒数
                    timingSource[stage] = stageData.duration;
                }
            });
        }

        // 如果 stages 中没有数据，尝试使用前端当前会话的数据（仅用于当前正在分析的任务）
        if (Object.keys(timingSource).length === 0 && currentAnalysisTaskId === task.id) {
            const taskData = getTaskStepData(task.id);
            if (taskData && Object.keys(taskData.stepTimes).length > 0) {
                timingSource = taskData.stepTimes;
            }
        }

        if (!timingSource || Object.keys(timingSource).length === 0) return '';

        const timingData = [];
        let totalTime = 0;

        const stageNames = {
            'intent': '意图识别',
            'filter': '日志筛选',
            'analysis': '根因分析',
            'report': '报告生成'
        };

        Object.keys(stageNames).forEach(stage => {
            if (timingSource[stage]) {
                timingData.push({
                    stage: stageNames[stage],
                    time: timingSource[stage]
                });
                totalTime += timingSource[stage];
            }
        });

        if (timingData.length === 0) return '';

        const rows = timingData.map(item => `
            <tr>
                <td>${item.stage}</td>
                <td class="time-value">${(item.time / 1000).toFixed(1)}s</td>
            </tr>
        `).join('');

        return `
            <div class="report-timing">
                <h4>⏱️ 分析耗时统计</h4>
                <table>
                    <thead>
                        <tr>
                            <th>分析步骤</th>
                            <th>耗时</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${rows}
                        <tr>
                            <td class="time-total">总计</td>
                            <td class="time-value time-total">${(totalTime / 1000).toFixed(1)}s</td>
                        </tr>
                    </tbody>
                </table>
            </div>
        `;
    } catch (e) {
        console.error('生成耗时统计失败:', e);
        return '';
    }
}

function hideReport() {
    showLogAnalysisListView();
}

// ==================== 删除任务 ====================

async function deleteAnalysisTask(taskId) {
    if (!confirm('确定要删除这个分析任务吗？')) {
        return;
    }

    try {
        const response = await fetch(`/api/log-analysis/tasks/${taskId}`, {
            method: 'DELETE'
        });

        if (response.ok) {
            showToast('删除成功', 'success');
            loadLogAnalysis();
        } else {
            showToast('删除失败', 'error');
        }
    } catch (error) {
        console.error('删除任务失败:', error);
        showToast('删除失败', 'error');
    }
}
