/**
 * 知识库模块
 */

// 模块级状态
const KnowledgeModule = {
    currentFileList: [],
    currentDbType: null,
    currentView: 'files'
};

const TAG_MAP = {
    'install': { name: '安装部署', icon: '📦', color: '#4CAF50' },
    'maintain': { name: '日常运维', icon: '🔧', color: '#2196F3' },
    'troubleshoot': { name: '故障处理', icon: '🚨', color: '#f44336' },
    'performance': { name: '性能优化', icon: '⚡', color: '#FF9800' },
    'backup': { name: '备份恢复', icon: '💾', color: '#9C27B0' },
    'security': { name: '安全管理', icon: '🔒', color: '#607D8B' },
    'upgrade': { name: '升级迁移', icon: '🔄', color: '#795548' },
    'case': { name: '故障案例', icon: '📋', color: '#E91E63' }
};

// ==================== 视图切换 ====================

function switchKnowledgeView(view) {
    console.log('[Knowledge] 切换到视图:', view);
    KnowledgeModule.currentView = view;

    // 更新按钮状态
    document.querySelectorAll('.knowledge-view-switch .view-switch-btn').forEach(btn => {
        btn.classList.remove('active');
        if (btn.dataset.view === view) {
            btn.classList.add('active');
        }
    });

    // 切换视图显示
    document.querySelectorAll('.knowledge-view').forEach(v => {
        v.classList.remove('active');
        v.style.display = 'none';
    });

    const targetView = document.getElementById(`knowledge-${view}-view`);
    if (targetView) {
        targetView.classList.add('active');
        targetView.style.display = 'block';
    }

    // 如果切换到图谱视图，初始化知识图谱
    if (view === 'graph') {
        initKGModule();
    }
}

// 防抖函数：延迟执行，避免频繁触发
function debounce(func, wait) {
    let timeout;
    return function (...args) {
        clearTimeout(timeout);
        timeout = setTimeout(() => func.apply(this, args), wait);
    };
}

// 带防抖的搜索函数
const debouncedSearchKnowledge = debounce(searchKnowledge, 300);

function renderTags(tags) {
    let tagsArray = tags;
    if (typeof tags === 'string') {
        try {
            tagsArray = JSON.parse(tags);
        } catch (e) {
            tagsArray = [];
        }
    }
    if (!tagsArray || !Array.isArray(tagsArray) || tagsArray.length === 0) {
        return '<span class="tag-empty">未分类</span>';
    }
    return tagsArray.map(tag => {
        const info = TAG_MAP[tag] || { name: tag, icon: '🏷️', color: '#999' };
        return `<span class="tag-badge" style="background-color: ${info.color}20; color: ${info.color}; border: 1px solid ${info.color}40;">${escapeHtml(info.icon)} ${escapeHtml(info.name)}</span>`;
    }).join(' ');
}

async function loadFileList() {
    const dbType = document.getElementById('knowledge-db-type').value;
    const tag = document.getElementById('knowledge-tag').value;
    const tbody = document.getElementById('file-list');

    if (!dbType) {
        tbody.innerHTML = '<tr><td colspan="5" class="empty-message">请选择数据库类型查看文件</td></tr>';
        return;
    }

    try {
        const url = `/api/knowledge/files/${dbType}?tag=${tag}`;
        const response = await fetch(url);
        const data = await response.json();

        if (data.files.length === 0) {
            tbody.innerHTML = '<tr><td colspan="5" class="empty-message">暂无文件</td></tr>';
            return;
        }

        tbody.innerHTML = data.files.map((file, index) => {
            // 确保 tags 是数组
            let tags = file.tags;
            if (typeof tags === 'string') {
                try { tags = JSON.parse(tags); } catch(e) { tags = []; }
            }
            if (!Array.isArray(tags)) tags = [];

            return `
            <tr>
                <td>${escapeHtml(file.name)}</td>
                <td>${formatFileSize(file.size)}</td>
                <td>${renderTags(tags)}</td>
                <td>${escapeHtml(file.modified || '')}</td>
                <td class="actions">
                    <button class="btn btn-sm btn-secondary" onclick="editFileTags(${index})">🏷️ 标签</button>
                    ${file.can_preview ? `<button class="btn btn-sm btn-secondary" onclick="previewFile('${escapeJsAttr(dbType)}', '${escapeJsAttr(file.name)}')">预览</button>` : ''}
                    <button class="btn btn-sm btn-primary" onclick="downloadFile('${escapeJsAttr(dbType)}', '${escapeJsAttr(file.name)}')">下载</button>
                    <button class="btn btn-sm btn-danger" onclick="deleteFile('${escapeJsAttr(dbType)}', '${escapeJsAttr(file.name)}')">删除</button>
                </td>
            </tr>
            `;
        }).join('');

        // 保存文件列表数据供编辑使用
        KnowledgeModule.currentFileList = data.files;
        KnowledgeModule.currentDbType = dbType;
    } catch (error) {
        showToast('加载文件列表失败', 'error');
    }
}

// 编辑文件标签（通过索引）
function editFileTags(index) {
    const file = KnowledgeModule.currentFileList[index];
    if (!file) return;
    showTagDialog(KnowledgeModule.currentDbType, file.name, file.tags || []);
}

// 显示标签编辑对话框
function showTagDialog(dbType, filename, currentTags) {
    const tagOptions = Object.entries(TAG_MAP).map(([id, info]) => {
        const checked = currentTags.includes(id) ? 'checked' : '';
        return `<label class="tag-option">
            <input type="checkbox" value="${escapeHtml(id)}" ${checked}> ${escapeHtml(info.icon)} ${escapeHtml(info.name)}
        </label>`;
    }).join('');

    const dialogHtml = `
        <div class="modal" id="modal-tags" style="display: flex">
            <div class="modal-content">
                <div class="modal-header">
                    <h3>编辑标签 - ${escapeHtml(filename)}</h3>
                    <button class="modal-close" onclick="closeModal('modal-tags')">&times;</button>
                </div>
                <div class="modal-body">
                    <div class="tag-checkboxes">
                        ${tagOptions}
                    </div>
                </div>
                <div class="modal-footer">
                    <button class="btn btn-secondary" onclick="closeModal('modal-tags')">取消</button>
                    <button class="btn btn-primary" onclick="saveFileTags('${escapeJsAttr(dbType)}', '${escapeJsAttr(filename)}')">保存</button>
                </div>
            </div>
        </div>
    `;

    // 移除旧对话框（如果有）
    const oldModal = document.getElementById('modal-tags');
    if (oldModal) oldModal.remove();

    // 添加新对话框
    document.body.insertAdjacentHTML('beforeend', dialogHtml);
}

// 保存文件标签
async function saveFileTags(dbType, filename) {
    const checkboxes = document.querySelectorAll('#modal-tags input[type="checkbox"]:checked');
    const tags = Array.from(checkboxes).map(cb => cb.value);

    try {
        const response = await fetch(`/api/knowledge/tags/${dbType}/${encodeURIComponent(filename)}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ tags })
        });

        if (response.ok) {
            showToast('标签更新成功', 'success');
            closeModal('modal-tags');
            loadFileList();
        } else {
            showToast('标签更新失败', 'error');
        }
    } catch (error) {
        showToast('标签更新失败', 'error');
    }
}

async function searchKnowledge() {
    const dbType = document.getElementById('knowledge-db-type').value;
    const keyword = document.getElementById('knowledge-search').value.trim();

    if (!dbType) {
        showToast('请先选择数据库类型', 'error');
        return;
    }

    if (!keyword) {
        document.getElementById('search-results').style.display = 'none';
        loadFileList();
        return;
    }

    try {
        const response = await fetch(`/api/knowledge/files/${dbType}?keyword=${encodeURIComponent(keyword)}`);
        const data = await response.json();

        const resultsDiv = document.getElementById('search-results');
        const resultsList = document.getElementById('search-results-list');

        if (data.search_results && data.search_results.length > 0) {
            resultsDiv.style.display = 'block';
            resultsList.innerHTML = data.search_results.map(result => `
                <div class="search-result-item">
                    <div class="filename">📄 ${escapeHtml(result.filename)}</div>
                    <div class="context">${escapeHtml(result.context)}</div>
                </div>
            `).join('');
        } else {
            resultsDiv.style.display = 'block';
            resultsList.innerHTML = '<div class="empty-message">未找到匹配内容</div>';
        }
    } catch (error) {
        showToast('搜索失败', 'error');
    }
}

// 文件上传（支持多文件和文件夹）
async function uploadFiles(files) {
    const dbType = document.getElementById('knowledge-db-type').value;
    if (!dbType) {
        showToast('请先选择数据库类型', 'error');
        return;
    }

    let successCount = 0;
    let failCount = 0;

    for (const file of files) {
        // 检查文件类型
        const ext = file.name.split('.').pop().toLowerCase();
        const allowedExts = ['txt', 'md', 'pdf', 'docx', 'xlsx', 'xls', 'doc', 'html', 'htm', 'chm'];
        if (!allowedExts.includes(ext)) {
            failCount++;
            continue;
        }

        const formData = new FormData();
        formData.append('file', file);

        try {
            const response = await fetch(`/api/knowledge/upload/${dbType}`, {
                method: 'POST',
                body: formData
            });

            if (response.ok) {
                successCount++;
            } else {
                failCount++;
            }
        } catch (error) {
            failCount++;
        }
    }

    if (successCount > 0) {
        showToast(`成功上传 ${successCount} 个文件${failCount > 0 ? `，${failCount} 个失败` : ''}`, 'success');
        loadFileList();
        updateSidebarStats();
    } else if (failCount > 0) {
        showToast(`上传失败，${failCount} 个文件不支持`, 'error');
    }
}

// 扫描知识库目录中的新文件
async function scanKnowledgeFiles() {
    try {
        showToast('正在扫描知识库目录...', 'info');
        const response = await fetch('/api/knowledge/scan', {
            method: 'POST'
        });
        const data = await response.json();
        if (response.ok) {
            showToast(data.message, 'success');
            loadFileList();
            updateSidebarStats();
        } else {
            showToast(data.error || '扫描失败', 'error');
        }
    } catch (error) {
        showToast('扫描失败', 'error');
    }
}

// 重建知识库索引（带进度条）
function reindexKnowledge() {
    const progressDiv = document.getElementById('reindex-progress');
    const progressBar = document.getElementById('progress-bar');
    const progressStatus = document.getElementById('progress-status');
    const progressText = document.getElementById('progress-text');

    // 显示进度条
    progressDiv.style.display = 'block';
    progressBar.style.width = '0%';
    progressStatus.textContent = '正在重建索引...';
    progressText.textContent = '0/0';

    // 使用 EventSource 接收流式进度（GET 请求）
    const eventSource = new EventSource('/api/knowledge/reindex/stream');
    let reindexTimeout = null;
    let isCompleted = false;

    // 设置超时保护（5分钟）
    reindexTimeout = setTimeout(() => {
        if (!isCompleted) {
            eventSource.close();
            progressDiv.style.display = 'none';
            showToast('重建索引超时，请稍后重试', 'error');
        }
    }, 300000);

    eventSource.onmessage = function(event) {
        if (event.data === '[DONE]') {
            isCompleted = true;
            clearTimeout(reindexTimeout);
            eventSource.close();
            // 3秒后隐藏进度条
            setTimeout(() => {
                progressDiv.style.display = 'none';
            }, 3000);
            return;
        }

        try {
            const data = JSON.parse(event.data);

            if (data.total > 0) {
                const percent = Math.round((data.processed / data.total) * 100);
                progressBar.style.width = percent + '%';
                progressText.textContent = `${data.processed}/${data.total}`;
            }

            if (data.status) {
                progressStatus.textContent = data.status;
            }

            if (data.done) {
                isCompleted = true;
                clearTimeout(reindexTimeout);
                showToast(data.message, 'success');
                eventSource.close();
                // 完成后更新文件列表
                loadFileList();
                setTimeout(() => {
                    progressDiv.style.display = 'none';
                }, 3000);
            }
        } catch (e) {
            console.error('解析进度数据失败:', e);
        }
    };

    eventSource.onerror = function(error) {
        console.error('SSE 连接错误:', error);
        clearTimeout(reindexTimeout);
        eventSource.close();
        progressDiv.style.display = 'none';
        if (!isCompleted) {
            showToast('重建索引失败', 'error');
        }
    };

    // 页面卸载时清理
    const cleanupOnUnload = function() {
        clearTimeout(reindexTimeout);
        eventSource.close();
    };
    window.addEventListener('beforeunload', cleanupOnUnload, { once: true });
}

async function downloadFile(dbType, filename) {
    window.open(`/api/knowledge/download/${dbType}/${filename}`);
}

async function deleteFile(dbType, filename) {
    if (!confirm(`确定要删除文件 "${filename}" 吗？`)) {
        return;
    }

    try {
        const response = await fetch(`/api/knowledge/delete/${dbType}/${filename}`, {
            method: 'DELETE'
        });

        const data = await response.json();
        if (response.ok) {
            showToast('删除成功', 'success');
            loadFileList();
        } else {
            showToast(data.error || '删除失败', 'error');
        }
    } catch (error) {
        showToast('删除失败', 'error');
    }
}

// 文件预览
async function previewFile(dbType, filename) {
    try {
        const response = await fetch(`/api/knowledge/preview/${dbType}/${encodeURIComponent(filename)}`);
        const data = await response.json();

        if (response.ok) {
            document.getElementById('preview-title').textContent = `文件预览: ${filename}`;
            document.getElementById('preview-content').textContent = data.content;
            document.getElementById('modal-preview').style.display = 'flex';
        } else {
            showToast(data.error || '预览失败', 'error');
        }
    } catch (error) {
        showToast('预览失败', 'error');
    }
}
