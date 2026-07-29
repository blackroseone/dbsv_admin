/**
 * SQL工具模块
 */

// 初始化 SQL 审核页面的联动逻辑
document.addEventListener('DOMContentLoaded', function() {
    initReviewModeEngine();
});

function initReviewModeEngine() {
    const reviewModeSelect = document.getElementById('sql-review-mode');
    const reviewEngineSelect = document.getElementById('sql-review-engine');

    if (!reviewModeSelect || !reviewEngineSelect) return;

    // 监听审核模式变化
    reviewModeSelect.addEventListener('change', function() {
        updateEngineOptions(this.value, reviewEngineSelect);
    });

    // 初始化时执行一次
    updateEngineOptions(reviewModeSelect.value, reviewEngineSelect);
}

function updateEngineOptions(mode, engineSelect) {
    const localOption = engineSelect.querySelector('option[value="local"]');
    const llmOption = engineSelect.querySelector('option[value="llm"]');

    if (mode === 'comprehensive') {
        // 综合审核模式下，禁用本地检查，强制使用 AI 审核
        if (localOption) {
            localOption.disabled = true;
            localOption.textContent = '⚡ 本地检查（综合审核不可用）';
        }
        // 如果当前选中的是本地检查，切换到 AI 审核
        if (engineSelect.value === 'local') {
            engineSelect.value = 'llm';
        }
    } else {
        // 语法审核模式下，启用所有选项
        if (localOption) {
            localOption.disabled = false;
            localOption.textContent = '⚡ 本地检查（极速）';
        }
    }
}

// 通用流式请求函数
async function streamRequest(url, body, contentDiv, isMarkdown = true) {
    let fullContent = '';
    contentDiv.innerHTML = '<span class="typing-cursor">▊</span>';

    try {
        const response = await fetch(url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body)
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
                        if (parsed.error) {
                            contentDiv.innerHTML = `<span style="color: #dc3545;">${escapeHtml(parsed.error)}</span>`;
                            return fullContent;
                        }
                        if (parsed.content) {
                            fullContent += parsed.content;
                            if (isMarkdown) {
                                contentDiv.innerHTML = formatMarkdown(fullContent) + '<span class="typing-cursor">▊</span>';
                            } else {
                                contentDiv.textContent = fullContent;
                            }
                        }
                    } catch (e) {
                        // 忽略解析错误
                    }
                }
            }
        }

        // 移除光标
        if (isMarkdown) {
            contentDiv.innerHTML = formatMarkdown(fullContent);
        } else {
            contentDiv.textContent = fullContent;
        }

        return fullContent;
    } catch (error) {
        contentDiv.innerHTML = '<span style="color: #dc3545;">请求失败，请检查网络连接</span>';
        return '';
    }
}

function switchSqlTab(tab) {
    // 更新标签按钮状态
    document.querySelectorAll('.tab-btn').forEach(btn => {
        btn.classList.remove('active');
    });
    event.target.classList.add('active');

    // 切换内容显示
    document.querySelectorAll('.sql-tab-content').forEach(content => {
        content.classList.remove('active');
    });
    document.getElementById(`sql-tab-${tab}`).classList.add('active');
}

async function reviewSQL() {
    const dbType = document.getElementById('sql-db-type').value;
    const sql = document.getElementById('sql-input').value.trim();
    const modelId = document.getElementById('sql-model-select').value;
    const reviewMode = document.getElementById('sql-review-mode').value;
    const reviewEngine = document.getElementById('sql-review-engine').value;

    if (!dbType) {
        showToast('请选择数据库类型', 'error');
        return;
    }

    if (!sql) {
        showToast('请输入SQL语句', 'error');
        return;
    }

    const resultDiv = document.getElementById('sql-result');
    const contentDiv = document.getElementById('sql-review-content');

    resultDiv.style.display = 'block';

    // 根据审核引擎选择不同的接口
    if (reviewEngine === 'local') {
        // 本地语法检查
        await streamRequest('/api/sql/check/stream', {
            db_type: dbType,
            sql: sql
        }, contentDiv, true);
    } else {
        // LLM 审核
        await streamRequest('/api/sql/review/stream', {
            db_type: dbType,
            sql: sql,
            model_id: modelId,
            review_mode: reviewMode
        }, contentDiv, true);
    }
}

function clearSQL() {
    document.getElementById('sql-input').value = '';
    document.getElementById('sql-result').style.display = 'none';
}

async function formatSQL() {
    const sql = document.getElementById('sql-format-input').value.trim();

    if (!sql) {
        showToast('请输入SQL语句', 'error');
        return;
    }

    const resultDiv = document.getElementById('sql-format-result');
    const contentDiv = document.getElementById('sql-format-content');

    resultDiv.style.display = 'block';
    await streamRequest('/api/sql/format/stream', { sql: sql }, contentDiv, false);
}

async function convertSQL() {
    const sourceDb = document.getElementById('sql-source-db').value;
    const targetDb = document.getElementById('sql-target-db').value;
    const sql = document.getElementById('sql-convert-input').value.trim();

    if (!sourceDb || !targetDb) {
        showToast('请选择源数据库和目标数据库', 'error');
        return;
    }

    if (!sql) {
        showToast('请输入SQL语句', 'error');
        return;
    }

    const resultDiv = document.getElementById('sql-convert-result');
    const contentDiv = document.getElementById('sql-convert-content');

    resultDiv.style.display = 'block';
    await streamRequest('/api/sql/convert/stream', {
        sql: sql,
        source_db: sourceDb,
        target_db: targetDb
    }, contentDiv, false);
}

async function analyzeExplain() {
    const dbType = document.getElementById('explain-db-type').value;
    const explainResult = document.getElementById('explain-input').value.trim();

    if (!dbType) {
        showToast('请选择数据库类型', 'error');
        return;
    }

    if (!explainResult) {
        showToast('请输入执行计划结果', 'error');
        return;
    }

    const resultDiv = document.getElementById('explain-result');
    const contentDiv = document.getElementById('explain-content');

    resultDiv.style.display = 'block';
    await streamRequest('/api/sql/explain/stream', {
        db_type: dbType,
        explain_result: explainResult
    }, contentDiv, true);
}
