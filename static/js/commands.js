/**
 * 命令速查模块
 */

// 模块级状态
const CommandsModule = {
    currentCommandCategory: ''
};

async function loadCommands() {
    const dbType = document.getElementById('commands-db-type').value;
    const container = document.getElementById('commands-container');

    if (!dbType) {
        container.innerHTML = '<div class="empty-message">请选择数据库类型查看常用命令</div>';
        return;
    }

    try {
        const response = await fetch(`/api/commands?db_type=${dbType}`);
        const data = await response.json();

        if (data.commands && data.commands.length > 0) {
            container.innerHTML = data.commands.map(category => `
                <div class="command-category">
                    <div class="command-category-header">
                        <h4>${escapeHtml(category.category)}</h4>
                        <button class="btn btn-sm btn-secondary" onclick="showAddCommandDialog('${escapeHtml(category.category)}')">➕ 添加命令</button>
                    </div>
                    ${category.commands.map((cmd, index) => `
                        <div class="command-item">
                            <div class="cmd-info">
                                <div class="cmd-name">${escapeHtml(cmd.name)}</div>
                                <div class="cmd-desc">${escapeHtml(cmd.desc)}</div>
                            </div>
                            <div class="cmd-actions">
                                <code class="cmd-text" onclick="copyText('${escapeHtml(cmd.cmd)}')" title="点击复制">
                                    ${escapeHtml(cmd.cmd)}
                                </code>
                                <button class="btn-icon btn-delete cmd-delete-btn" style="opacity:0;" onclick="event.stopPropagation(); deleteCommand('${escapeHtml(category.category)}', ${index})" title="删除命令">×</button>
                            </div>
                        </div>
                    `).join('')}
                </div>
            `).join('');

            // 绑定事件委托
            bindCommandItemEvents(container);
        } else {
            container.innerHTML = '<div class="empty-message">暂无命令数据，点击"添加分类"开始</div>';
        }
    } catch (error) {
        showToast('加载命令失败', 'error');
    }
}

function copyText(text) {
    navigator.clipboard.writeText(text).then(() => {
        showToast('已复制到剪贴板', 'success');
    }).catch(() => {
        showToast('复制失败', 'error');
    });
}

// 使用事件委托绑定命令项的悬停事件
function bindCommandItemEvents(container) {
    container.addEventListener('mouseenter', function(e) {
        const item = e.target.closest('.command-item');
        if (item) {
            const deleteBtn = item.querySelector('.cmd-delete-btn');
            if (deleteBtn) deleteBtn.style.opacity = '1';
        }
    }, true);

    container.addEventListener('mouseleave', function(e) {
        const item = e.target.closest('.command-item');
        if (item) {
            const deleteBtn = item.querySelector('.cmd-delete-btn');
            if (deleteBtn) deleteBtn.style.opacity = '0';
        }
    }, true);
}

// 删除命令
async function deleteCommand(category, index) {
    if (!confirm('确定要删除这个命令吗？')) return;

    const dbType = document.getElementById('commands-db-type').value;

    try {
        const response = await fetch('/api/commands/command', {
            method: 'DELETE',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                db_type: dbType,
                category: category,
                index: index
            })
        });

        const data = await response.json();
        if (response.ok) {
            showToast('删除成功', 'success');
            loadCommands();
        } else {
            showToast(data.error || '删除失败', 'error');
        }
    } catch (error) {
        showToast('删除失败', 'error');
    }
}

// 显示添加分类对话框
function showAddCategoryDialog() {
    const dbType = document.getElementById('commands-db-type').value;
    if (!dbType) {
        showToast('请先选择数据库类型', 'error');
        return;
    }
    document.getElementById('category-name').value = '';
    document.getElementById('modal-add-category').style.display = 'flex';
}

// 添加分类
async function addCategory() {
    const dbType = document.getElementById('commands-db-type').value;
    const categoryName = document.getElementById('category-name').value.trim();

    if (!categoryName) {
        showToast('请输入分类名称', 'error');
        return;
    }

    try {
        const response = await fetch('/api/commands/category', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                db_type: dbType,
                category_name: categoryName
            })
        });

        const data = await response.json();
        if (response.ok) {
            showToast('分类添加成功', 'success');
            closeModal('modal-add-category');
            loadCommands();
        } else {
            showToast(data.error || '添加失败', 'error');
        }
    } catch (error) {
        showToast('添加失败', 'error');
    }
}

// 显示添加命令对话框
function showAddCommandDialog(category) {
    const dbType = document.getElementById('commands-db-type').value;
    if (!dbType) {
        showToast('请先选择数据库类型', 'error');
        return;
    }
    CommandsModule.currentCommandCategory = category;
    document.getElementById('command-name').value = '';
    document.getElementById('command-cmd').value = '';
    document.getElementById('command-desc').value = '';
    document.getElementById('modal-add-command').style.display = 'flex';
}

// 添加命令
async function addCommand() {
    const dbType = document.getElementById('commands-db-type').value;
    const category = CommandsModule.currentCommandCategory;
    const name = document.getElementById('command-name').value.trim();
    const cmd = document.getElementById('command-cmd').value.trim();
    const desc = document.getElementById('command-desc').value.trim();

    if (!name || !cmd) {
        showToast('请输入命令名称和内容', 'error');
        return;
    }

    try {
        const response = await fetch('/api/commands/command', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                db_type: dbType,
                category: category,
                name: name,
                cmd: cmd,
                desc: desc
            })
        });

        const data = await response.json();
        if (response.ok) {
            showToast('命令添加成功', 'success');
            closeModal('modal-add-command');
            loadCommands();
        } else {
            showToast(data.error || '添加失败', 'error');
        }
    } catch (error) {
        showToast('添加失败', 'error');
    }
}

// 命令跨库搜索（带防抖）
let searchDebounceTimer = null;

function debouncedSearchCommands() {
    clearTimeout(searchDebounceTimer);
    searchDebounceTimer = setTimeout(() => {
        searchCommands();
    }, 300);
}

async function searchCommands() {
    const keyword = document.getElementById('command-search').value.trim();
    const resultsDiv = document.getElementById('command-search-results');
    const resultsList = document.getElementById('command-search-results-list');

    if (!keyword) {
        resultsDiv.style.display = 'none';
        return;
    }

    try {
        const response = await fetch(`/api/commands/search?keyword=${encodeURIComponent(keyword)}`);
        const data = await response.json();

        if (data.results && data.results.length > 0) {
            resultsDiv.style.display = 'block';
            resultsList.innerHTML = data.results.map(cmd => `
                <div class="command-item">
                    <div class="cmd-info">
                        <div class="cmd-name">
                            <span class="cmd-db-type">${escapeHtml(cmd.db_name)}</span>
                            ${escapeHtml(cmd.name)}
                        </div>
                        <div class="cmd-desc">[${escapeHtml(cmd.category)}] ${escapeHtml(cmd.desc)}</div>
                    </div>
                    <code class="cmd-text" onclick="copyText('${escapeHtml(cmd.cmd)}')" title="点击复制">
                        ${escapeHtml(cmd.cmd)}
                    </code>
                </div>
            `).join('');
        } else {
            resultsDiv.style.display = 'block';
            resultsList.innerHTML = '<div class="empty-message">未找到匹配的命令</div>';
        }
    } catch (error) {
        showToast('搜索失败', 'error');
    }
}
