/**
 * 操作手册模块
 */

// 模块级状态
const ManualsModule = {
    currentManual: ''
};

async function loadManuals() {
    try {
        const response = await fetch('/api/manuals');
        const data = await response.json();
        const listDiv = document.getElementById('manual-list');

        if (data.manuals.length === 0) {
            listDiv.innerHTML = '<div class="empty-message">暂无手册，点击"上传"开始</div>';
            return;
        }

        listDiv.innerHTML = data.manuals.map(file => `
            <div class="manual-item ${ManualsModule.currentManual === file.name ? 'active' : ''}" onclick="viewManual('${escapeJsAttr(file.name)}')">
                <div class="manual-name">${escapeHtml(file.name)}</div>
                <div class="manual-size">${formatFileSize(file.size)}</div>
            </div>
        `).join('');
    } catch (error) {
        showToast('加载手册列表失败', 'error');
    }
}

// 从当前手册生成运维技能（工具栏按钮）
async function genSkillFromManual() {
    const filename = ManualsModule.currentManual;
    if (!filename) {
        showToast('请先选择一篇手册', 'error');
        return;
    }
    if (!confirm(`从手册「${filename}」生成运维技能？`)) return;
    const btn = document.querySelector('.gen-skill-btn');
    const oldText = btn ? btn.textContent : '';
    if (btn) {
        btn.textContent = '⏳ 生成中...';
        btn.disabled = true;
    }
    try {
        const formData = new FormData();
        formData.append('filename', filename);
        formData.append('category', 'diagnosis');
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
        if (btn) {
            btn.textContent = oldText;
            btn.disabled = false;
        }
    }
}

// 查看手册内容
async function viewManual(filename) {
    ManualsModule.currentManual = filename;
    const contentDiv = document.getElementById('manual-content');
    const toolbar = document.getElementById('manual-toolbar');
    const toolbarTitle = document.getElementById('manual-toolbar-title');

    // 更新选中状态
    document.querySelectorAll('.manual-item').forEach(item => {
        item.classList.remove('active');
    });
    if (event && event.currentTarget) {
        event.currentTarget.classList.add('active');
    }

    // 显示工具栏
    toolbar.style.display = 'flex';
    toolbarTitle.textContent = filename;

    // 检查文件类型
    const lowerFilename = filename.toLowerCase();
    const isMarkdown = lowerFilename.endsWith('.md');
    const isText = lowerFilename.endsWith('.txt') || lowerFilename.endsWith('.log') || lowerFilename.endsWith('.sql') || lowerFilename.endsWith('.py') || lowerFilename.endsWith('.sh');

    if (isMarkdown || isText) {
        // 尝试预览文件
        try {
            const response = await fetch(`/api/manuals/preview/${encodeURIComponent(filename)}`);
            const data = await response.json();

            if (response.ok) {
                if (isMarkdown) {
                    contentDiv.innerHTML = `<div class="markdown-content">${formatMarkdown(data.content)}</div>`;
                } else {
                    // 纯文本文件，使用预格式化文本显示
                    contentDiv.innerHTML = `<div class="text-content"><pre style="white-space: pre-wrap; word-wrap: break-word; font-family: 'Consolas', 'Monaco', monospace; line-height: 1.6;">${escapeHtml(data.content)}</pre></div>`;
                }
            } else {
                contentDiv.innerHTML = `<div class="empty-message">无法加载文件内容</div>`;
            }
        } catch (error) {
            contentDiv.innerHTML = `<div class="empty-message">加载失败</div>`;
        }
    } else {
        // 不支持预览的文件格式
        contentDiv.innerHTML = `
            <div class="welcome-message">
                <div class="welcome-icon">📄</div>
                <h3>${escapeHtml(filename)}</h3>
                <p>该文件格式不支持在线预览</p>
                <p>请点击上方"下载"按钮查看文件</p>
            </div>
        `;
    }
}

// 下载当前手册
function downloadCurrentManual() {
    if (ManualsModule.currentManual) {
        window.open(`/api/manuals/${encodeURIComponent(ManualsModule.currentManual)}`);
    }
}

// 删除当前手册
async function deleteCurrentManual() {
    if (!ManualsModule.currentManual) return;
    if (!confirm(`确定要删除 "${ManualsModule.currentManual}" 吗？`)) return;

    try {
        const response = await fetch(`/api/manuals/${encodeURIComponent(ManualsModule.currentManual)}`, { method: 'DELETE' });
        if (response.ok) {
            showToast('删除成功', 'success');
            ManualsModule.currentManual = '';
            document.getElementById('manual-toolbar').style.display = 'none';
            document.getElementById('manual-content').innerHTML = `
                <div class="welcome-message">
                    <div class="welcome-icon">📋</div>
                    <h3>操作手册</h3>
                    <p>选择左侧的手册查看内容</p>
                    <p>支持 Markdown 格式渲染</p>
                </div>
            `;
            loadManuals();
        } else {
            showToast('删除失败', 'error');
        }
    } catch (error) {
        showToast('删除失败', 'error');
    }
}

// 初始化操作手册
function initManuals() {
    loadManuals();
}
