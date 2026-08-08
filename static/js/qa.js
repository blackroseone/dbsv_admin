/**
 * 知识问答模块 - 支持多轮对话和会话管理
 */

let isStreaming = false;
let currentAbortController = null;
let currentConversationId = null; // 当前会话ID

// 智能滚动：用户在底部附近时自动跟随新内容，手动上滚则暂停跟随
let qaAutoScroll = true;

// 监听聊天区滚动，判断是否处于底部附近
document.addEventListener('DOMContentLoaded', () => {
    const chatEl = document.getElementById('qa-chat');
    if (chatEl) {
        chatEl.addEventListener('scroll', () => {
            const nearBottom = chatEl.scrollTop + chatEl.clientHeight >= chatEl.scrollHeight - 60;
            qaAutoScroll = nearBottom;
        });
    }
});

function qaScrollIfNeeded() {
    if (!qaAutoScroll) return;
    const chatEl = document.getElementById('qa-chat');
    if (chatEl) {
        chatEl.scrollTop = chatEl.scrollHeight;
    }
}

// 页面加载完成后初始化
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initQA);
} else {
    initQA();
}

async function initQA() {
    await loadConversations();
}

// ==================== 会话管理 ====================

async function loadConversations() {
    // 加载会话列表
    try {
        console.log('DEBUG: loading conversations...');
        const response = await fetch('/api/qa/conversations');
        const data = await response.json();
        console.log('DEBUG: conversations data:', data);

        const listDiv = document.getElementById('qa-conversation-list');
        const conversations = data.conversations || [];
        console.log('DEBUG: conversations count:', conversations.length);

        if (conversations.length > 0) {
            listDiv.innerHTML = conversations.map(item => {
                let timeDisplay = item.updated_at || item.created_at || '';
                if (timeDisplay) {
                    const date = new Date(timeDisplay);
                    if (!isNaN(date.getTime())) {
                        timeDisplay = date.toLocaleString('zh-CN', {
                            month: '2-digit',
                            day: '2-digit',
                            hour: '2-digit',
                            minute: '2-digit'
                        });
                    }
                }
                const isActive = item.id === currentConversationId ? 'active' : '';
                return `
                <div class="qa-conversation-card ${isActive}" data-id="${escapeHtml(item.id)}" onclick="switchConversation('${escapeJsAttr(item.id)}')">
                    <div class="qa-conversation-content">
                        <div class="qa-conversation-title">${escapeHtml(item.title || '新对话')}</div>
                        <div class="qa-conversation-time">${timeDisplay}</div>
                    </div>
                    <button class="qa-conversation-delete" onclick="event.stopPropagation(); deleteConversation('${escapeJsAttr(item.id)}')">&times;</button>
                </div>
            `}).join('');
        } else {
            listDiv.innerHTML = '<div class="empty-message">暂无会话</div>';
        }
    } catch (error) {
        console.error('加载会话列表失败:', error);
    }
}

async function createNewConversation() {
    // 创建新会话，重置数据库类型为自动选择
    const dbType = 'auto';
    const modelId = document.getElementById('qa-model-select').value;

    // 重置下拉框为自动选择
    document.getElementById('qa-db-type').value = 'auto';

    try {
        const response = await fetch('/api/qa/conversations', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                title: '新对话',
                db_type: dbType,
                model_id: modelId
            })
        });
        const data = await response.json();

        if (data.conversation) {
            currentConversationId = data.conversation.id;
            // 清空聊天区域
            document.getElementById('qa-chat').innerHTML = `
                <div class="welcome-message">
                    <div class="welcome-icon">🤖</div>
                    <h3>数据库智能问答助手</h3>
                    <p>选择数据库类型，输入问题开始对话</p>
                </div>
            `;
            await loadConversations();
            showToast('新会话已创建', 'success');
        }
    } catch (error) {
        console.error('创建会话失败:', error);
        showToast('创建会话失败', 'error');
    }
}

async function switchConversation(convId) {
    // 切换到指定会话
    currentConversationId = convId;

    try {
        const response = await fetch(`/api/qa/conversations/${convId}`);
        const data = await response.json();

        if (data.conversation) {
            // 更新数据库类型选择
            if (data.conversation.db_type) {
                document.getElementById('qa-db-type').value = data.conversation.db_type;
            } else {
                // 如果会话没有数据库类型，默认为自动选择
                document.getElementById('qa-db-type').value = 'auto';
            }

            // 渲染会话消息
            const chatContainer = document.getElementById('qa-chat');
            chatContainer.innerHTML = '';

            const messages = data.messages || [];
            if (messages.length === 0) {
                chatContainer.innerHTML = `
                    <div class="welcome-message">
                        <div class="welcome-icon">🤖</div>
                        <h3>数据库智能问答助手</h3>
                        <p>选择数据库类型，输入问题开始对话</p>
                    </div>
                `;
            } else {
                // 使用 DocumentFragment 批量插入，提升性能
                const fragment = document.createDocumentFragment();
                messages.forEach(msg => {
                    const msgDiv = document.createElement('div');
                    if (msg.role === 'user') {
                        msgDiv.className = 'chat-message user';
                        msgDiv.innerHTML = `<div class="chat-bubble">${escapeHtml(msg.content)}</div>`;
                    } else if (msg.role === 'assistant') {
                        msgDiv.className = 'chat-message assistant';
                        msgDiv.innerHTML = `<div class="chat-bubble markdown-content">${formatMarkdown(msg.content)}</div>`;
                    }
                    fragment.appendChild(msgDiv);
                });
                chatContainer.appendChild(fragment);
            }

            chatContainer.scrollTop = chatContainer.scrollHeight;
            await loadConversations(); // 刷新列表高亮
        }
    } catch (error) {
        console.error('切换会话失败:', error);
        showToast('切换会话失败', 'error');
    }
}

async function deleteConversation(convId) {
    // 删除会话
    if (!confirm('确定要删除这个会话吗？')) return;

    const card = document.querySelector(`.qa-conversation-card[data-id="${convId}"]`);

    try {
        const response = await fetch(`/api/qa/conversations/${convId}`, { method: 'DELETE' });
        const data = await response.json();

        if (response.ok && data.success) {
            showToast('删除成功', 'success');
            // 从DOM中移除该会话卡片
            if (card) {
                card.remove();
            }
            // 如果删除的是当前会话，清空当前会话ID和聊天区域
            if (currentConversationId === convId) {
                currentConversationId = null;
                document.getElementById('qa-chat').innerHTML = `
                    <div class="welcome-message">
                        <div class="welcome-icon">🤖</div>
                        <h3>数据库智能问答助手</h3>
                        <p>选择数据库类型，输入问题开始对话</p>
                    </div>
                `;
            }
        } else {
            showToast(data.error || '删除失败', 'error');
        }
    } catch (error) {
        showToast('删除失败: ' + error.message, 'error');
    }
}

async function clearAllConversations() {
    // 清空所有会话
    if (!confirm('确定要清空所有会话吗？此操作不可恢复！')) return;

    try {
        const response = await fetch('/api/qa/conversations', { method: 'DELETE' });
        if (response.ok) {
            showToast('已清空所有会话', 'success');
            currentConversationId = null;
            document.getElementById('qa-chat').innerHTML = `
                <div class="welcome-message">
                    <div class="welcome-icon">🤖</div>
                    <h3>数据库智能问答助手</h3>
                    <p>选择数据库类型，输入问题开始对话</p>
                </div>
            `;
            await loadConversations();
        } else {
            showToast('清空失败', 'error');
        }
    } catch (error) {
        showToast('清空失败', 'error');
    }
}

// ==================== 问答功能 ====================

async function loadQATemplates() {
    try {
        const response = await fetch('/api/qa/templates');
        const data = await response.json();

        const select = document.getElementById('qa-template');
        select.innerHTML = '<option value="">问题模板</option>';

        if (data.templates) {
            data.templates.forEach(template => {
                const option = document.createElement('option');
                option.value = template.content;
                option.textContent = template.name;
                select.appendChild(option);
            });
        }
    } catch (error) {
        console.error('加载问题模板失败:', error);
    }
}

function applyTemplate() {
    const select = document.getElementById('qa-template');
    const content = select.value;
    if (content) {
        document.getElementById('qa-question').value = content;
    }
}

function stopStreaming() {
    isStreaming = false;
    if (currentAbortController) {
        currentAbortController.abort();
    }
    document.getElementById('qa-send-btn').disabled = false;
    document.getElementById('qa-stop-btn').style.display = 'none';
}

async function sendQuestion() {
    let dbType = document.getElementById('qa-db-type').value;
    const question = document.getElementById('qa-question').value.trim();
    const useRag = document.getElementById('qa-use-rag').checked;
    const useTopology = document.getElementById('qa-use-topology').checked;
    const modelId = document.getElementById('qa-model-select').value;

    if (!question) {
        showToast('请输入问题', 'error');
        return;
    }

    // 如果是自动选择，从问题中识别数据库类型
    if (dbType === 'auto') {
        dbType = detectDBTypeFromQuestion(question);
        console.log('自动识别数据库类型:', dbType || '未识别');
    }

    // 如果没有当前会话，自动创建一个新会话
    if (!currentConversationId) {
        await createNewConversation();
        if (!currentConversationId) {
            showToast('创建会话失败', 'error');
            return;
        }
    }

    const chatContainer = document.getElementById('qa-chat');

    // 移除欢迎消息
    const welcomeMsg = chatContainer.querySelector('.welcome-message');
    if (welcomeMsg) {
        welcomeMsg.remove();
    }

    // 添加用户消息到界面
    chatContainer.innerHTML += `
        <div class="chat-message user">
            <div class="chat-bubble">${escapeHtml(question)}</div>
        </div>
    `;

    // 添加助手消息容器（流式更新）
    const msgId = 'msg-' + Date.now();
    chatContainer.innerHTML += `
        <div class="chat-message assistant" id="${msgId}">
            <div class="chat-bubble markdown-content"><span class="typing-cursor">▊</span></div>
        </div>
    `;

    // 清空输入框
    document.getElementById('qa-question').value = '';
    chatContainer.scrollTop = chatContainer.scrollHeight;

    // 禁用发送按钮，显示停止按钮
    document.getElementById('qa-send-btn').disabled = true;
    document.getElementById('qa-stop-btn').style.display = 'inline-block';
    isStreaming = true;

    // 创建 AbortController
    currentAbortController = new AbortController();

    try {
        // 先保存用户消息到数据库
        await fetch(`/api/qa/conversations/${currentConversationId}/messages`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                role: 'user',
                content: question
            })
        });

        // 更新会话标题（如果标题还是"新对话"）
        const currentTitle = document.querySelector(`.qa-conversation-card[data-id="${currentConversationId}"] .qa-conversation-title`)?.textContent;
        if (currentTitle === '新对话') {
            const newTitle = question.length > 20 ? question.substring(0, 20) + '...' : question;
            await fetch(`/api/qa/conversations/${currentConversationId}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ title: newTitle })
            });
            // 刷新列表以显示新标题
            await loadConversations();
        }

        // 后台执行流式输出，不阻塞用户操作
        const conversationId = currentConversationId;
        _doStreamResponse(conversationId, dbType, question, useRag, useTopology, modelId, msgId, chatContainer);

    } catch (error) {
        console.error('发送问题失败:', error);
        showToast('发送失败: ' + error.message, 'error');
        document.getElementById('qa-send-btn').disabled = false;
        document.getElementById('qa-stop-btn').style.display = 'none';
        isStreaming = false;
        currentAbortController = null;
    }
}

// 后台执行流式输出
async function _doStreamResponse(conversationId, dbType, question, useRag, useTopology, modelId, msgId, chatContainer) {
    let fullAnswer = '';
    let reader = null;
    let knowledgeRefs = [];  // 知识库引用
    let confidenceLevel = 'low';  // 置信度级别
    let lastRenderTime = 0;  // 上次渲染时间
    const RENDER_INTERVAL = 50; // 最小渲染间隔(ms)，避免过于频繁的DOM操作

    try {
        const response = await fetch('/api/qa/ask/stream', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                db_type: dbType,
                question: question,
                use_rag: useRag,
                use_topology: useTopology,
                model_id: modelId,
                conversation_id: conversationId
            }),
            signal: currentAbortController.signal
        });

        reader = response.body.getReader();
        const decoder = new TextDecoder();
        let pendingContent = ''; // 待渲染的内容缓冲区

        while (isStreaming) {
            const { done, value } = await reader.read();
            if (done) break;

            const chunk = decoder.decode(value);
            const lines = chunk.split('\n');

            for (const line of lines) {
                if (!isStreaming) break;
                if (line.startsWith('data: ')) {
                    const data = line.slice(6).trim();
                    if (data === '[DONE]') continue;

                    try {
                        const parsed = JSON.parse(data);
                        if (parsed.error) {
                            const bubble = document.getElementById(msgId)?.querySelector('.chat-bubble');
                            if (bubble) {
                                bubble.innerHTML = `<span style="color: #dc3545;">${escapeHtml(parsed.error)}</span>`;
                            }
                            break;
                        }
                        // 处理知识库元数据
                        if (parsed.type === 'metadata' && parsed.metadata) {
                            renderKnowledgeMetadata(msgId, parsed.metadata);
                            continue;
                        }
                        if (parsed.content) {
                            fullAnswer += parsed.content;
                            pendingContent += parsed.content;

                            // 节流渲染：每50ms或累积超过20个字符才渲染一次
                            const now = Date.now();
                            if (now - lastRenderTime > RENDER_INTERVAL || pendingContent.length > 20) {
                                const bubble = document.getElementById(msgId)?.querySelector('.chat-bubble');
                                if (bubble) {
                                    bubble.innerHTML = formatMarkdown(fullAnswer) + '<span class="typing-cursor">▊</span>';
                                    qaScrollIfNeeded();
                                }
                                pendingContent = '';
                                lastRenderTime = now;
                            }
                        }
                    } catch (e) {
                        // 忽略解析错误
                    }
                }
            }
        }

        // 渲染剩余内容
        if (pendingContent) {
            const bubble = document.getElementById(msgId)?.querySelector('.chat-bubble');
            if (bubble) {
                bubble.innerHTML = formatMarkdown(fullAnswer) + '<span class="typing-cursor">▊</span>';
            }
        }

        // 移除打字光标
        const bubble = document.getElementById(msgId)?.querySelector('.chat-bubble');
        if (bubble) {
            bubble.innerHTML = formatMarkdown(fullAnswer);
        }
        qaScrollIfNeeded();

        // 保存助手回答到数据库
        await fetch(`/api/qa/conversations/${conversationId}/messages`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                role: 'assistant',
                content: fullAnswer
            })
        });

    } catch (error) {
        if (error.name !== 'AbortError') {
            const bubble = document.getElementById(msgId)?.querySelector('.chat-bubble');
            if (bubble) {
                bubble.innerHTML = `<span style="color: #dc3545;">请求失败: ${escapeHtml(error.message)}</span>`;
            }
        }
    } finally {
        // 释放 reader，避免内存泄漏
        if (reader) {
            try {
                reader.cancel();
            } catch (e) {
                // 忽略取消错误
            }
        }
        document.getElementById('qa-send-btn').disabled = false;
        document.getElementById('qa-stop-btn').style.display = 'none';
        isStreaming = false;
        currentAbortController = null;
    }
}

// ==================== 知识库元数据展示 ====================
function renderKnowledgeMetadata(msgId, metadata) {
    const messageDiv = document.getElementById(msgId);
    if (!messageDiv) return;

    // 查找或创建元数据展示区域（放在消息容器之前，而不是内部）
    let metaDiv = document.getElementById(msgId + '-meta');
    if (!metaDiv) {
        metaDiv = document.createElement('div');
        metaDiv.id = msgId + '-meta';
        metaDiv.className = 'knowledge-metadata';
        // 插入到消息容器之前，而不是消息容器内部
        messageDiv.parentNode.insertBefore(metaDiv, messageDiv);
    }

    const confidence = metadata.confidence || 'low';
    const sources = metadata.knowledge_sources || [];
    const hasSufficient = metadata.has_sufficient_knowledge || false;

    // 置信度样式
    const confidenceConfig = {
        'high': { icon: '🟢', label: '高置信度', class: 'confidence-high', desc: '基于知识库原文' },
        'medium': { icon: '🟡', label: '中置信度', class: 'confidence-medium', desc: '部分基于知识库' },
        'low': { icon: '🔴', label: '低置信度', class: 'confidence-low', desc: '可能存在幻觉' }
    };

    const conf = confidenceConfig[confidence] || confidenceConfig['low'];

    // 构建来源列表HTML（限制最多显示3个来源，避免过长）
    let sourcesHtml = '';
    if (sources.length > 0) {
        const displaySources = sources.slice(0, 3); // 最多显示3个来源
        sourcesHtml = `
            <div class="knowledge-sources">
                <div class="sources-title">📚 参考来源：</div>
                ${displaySources.map((s, i) => `
                    <div class="source-item">
                        <span class="source-num">[${i+1}]</span>
                        <span class="source-file">${escapeHtml(s.filename)}</span>
                        <span class="source-similarity">相似度: ${escapeHtml(s.similarity)}</span>
                    </div>
                `).join('')}
                ${sources.length > 3 ? `<div class="source-more">...还有 ${sources.length - 3} 个来源</div>` : ''}
            </div>
        `;
    } else {
        sourcesHtml = `
            <div class="knowledge-warning">
                ⚠️ 未检索到相关知识库文档
            </div>
        `;
    }

    // 警告信息
    let warningHtml = '';
    if (!hasSufficient) {
        warningHtml = `
            <div class="knowledge-warning-box">
                <strong>⚠️ 注意</strong>：知识库中未找到与该问题直接相关的高置信度文档。
                以下回答可能基于模型的一般知识，存在错误风险。
            </div>
        `;
    }

    metaDiv.innerHTML = `
        <div class="knowledge-confidence ${conf.class}">
            <span class="confidence-icon">${conf.icon}</span>
            <span class="confidence-label">${conf.label}</span>
            <span class="confidence-desc">(${conf.desc})</span>
        </div>
        ${warningHtml}
        ${sourcesHtml}
    `;
}

// ==================== 兼容旧版历史记录 API ====================

async function loadQAHistory() {
    // 新版使用会话列表替代历史记录
    await loadConversations();
}

async function clearChat() {
    if (!confirm('确定要清空当前对话吗？')) return;

    if (currentConversationId) {
        await deleteConversation(currentConversationId);
    } else {
        document.getElementById('qa-chat').innerHTML = `
            <div class="welcome-message">
                <div class="welcome-icon">🤖</div>
                <h3>数据库智能问答助手</h3>
                <p>选择数据库类型，输入问题开始对话</p>
            </div>
        `;
    }
}

// 从问题中自动识别数据库类型
function detectDBTypeFromQuestion(question) {
    const lowerQuestion = question.toLowerCase();

    // 数据库类型关键词映射
    const dbKeywords = {
        'oracle': ['oracle', 'ora', 'oracle数据库'],
        'mysql': ['mysql', 'my sql', 'mariadb'],
        'tdsql': ['tdsql', 'td sql', 'tencentdb'],
        'oceanbase': ['oceanbase', 'ocean base', 'ob'],
        'goldendb': ['goldendb', 'golden db', 'golden'],
        'dm': ['达梦', '达梦数据库', 'dm', 'dameng'],
        'gaussdb': ['gaussdb', 'gauss db', 'gauss', '高斯']
    };

    // 遍历检测
    for (const [dbType, keywords] of Object.entries(dbKeywords)) {
        for (const keyword of keywords) {
            if (lowerQuestion.includes(keyword)) {
                return dbType;
            }
        }
    }

    // 未识别到，返回空字符串
    return '';
}

// 回车发送
document.getElementById('qa-question').addEventListener('keydown', function(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        sendQuestion();
    }
});
