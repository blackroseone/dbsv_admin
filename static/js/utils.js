/**
 * 工具函数
 */

function showToast(message, type = 'info') {
    const toast = document.getElementById('toast');
    toast.textContent = message;
    toast.className = `toast ${type} show`;

    setTimeout(() => {
        toast.className = 'toast';
    }, 3000);
}

function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    // 补充引号转义：文本内容与双引号属性上下文均安全
    return div.innerHTML
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}

function escapeJsAttr(text) {
    // 用于 inline 事件处理器（onclick 等）内的 JS 字符串字面量。
    // 该上下文经过「HTML 属性实体解码 → JS 引擎解析」两道处理，
    // 因此必须用反斜杠转义（HTML 解码不触碰反斜杠），且先转义反斜杠
    // 再插入 \x.. 序列，避免产物被二次转义。转义后不含裸 ' " & 。
    if (!text) return '';
    return String(text)
        .replace(/\\/g, '\\\\')
        .replace(/&/g, '\\x26')
        .replace(/'/g, '\\x27')
        .replace(/"/g, '\\x22')
        .replace(/\n/g, '\\n')
        .replace(/\r/g, '\\r')
        .replace(/\t/g, '\\t');
}

function formatFileSize(bytes) {
    if (bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
}

// marked + highlight.js 版 Markdown 渲染（v4.1.0，全站通用）。
// 安全：marked 默认原样放行 raw HTML，故先 escapeHtml 再解析，保持与旧实现一致的注入防护。
function formatMarkdown(text) {
    if (!text) return '';
    if (typeof marked !== 'undefined') {
        try {
            marked.setOptions({ headerIds: false, breaks: true, gfm: true });
            // 先转义再解析：模型输出/文档中的 <script>、<img onerror> 等原样转义，不注入
            let html = marked.parse(escapeHtml(text));
            // 兼容现有表格样式
            html = html.replace(/<table>/g, '<table class="md-table">');
            // 代码高亮（rAF 异步，避免阻塞流式渲染）
            if (typeof hljs !== 'undefined') {
                requestAnimationFrame(() => {
                    document.querySelectorAll('pre code:not([data-hl])').forEach(el => {
                        try { hljs.highlightElement(el); el.dataset.hl = '1'; } catch (e) {}
                    });
                });
            }
            return html;
        } catch (e) {
            console.warn('marked 解析失败，回退正则实现:', e);
        }
    }
    return formatMarkdownLegacy(text);
}

function formatMarkdownLegacy(text) {
    if (!text) return '';

    let html = escapeHtml(text);

    // 标题
    html = html.replace(/^### (.*$)/gm, '<h3>$1</h3>');
    html = html.replace(/^## (.*$)/gm, '<h2>$1</h2>');
    html = html.replace(/^# (.*$)/gm, '<h1>$1</h1>');

    // 粗体和斜体
    html = html.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
    html = html.replace(/\*(.*?)\*/g, '<em>$1</em>');

    // 代码块
    html = html.replace(/```(\w*)\n([\s\S]*?)```/g, '<pre><code>$2</code></pre>');
    html = html.replace(/`([^`]+)`/g, '<code>$1</code>');

    // 列表
    html = html.replace(/^\s*[-*]\s(.*$)/gm, '<li>$1</li>');
    html = html.replace(/(<li>.*<\/li>)/s, '<ul>$1</ul>');

    // 表格：连续以 | 开头结尾的行（含 |---| 分隔行）渲染为 HTML 表格
    html = html.replace(/((?:^\|[^\n]*\|\s*\n)+)/gm, function(block) {
        const lines = block.trim().split('\n').map(l => l.trim());
        const sepIdx = lines.findIndex(l => /^\|[\s\-|:]+\|$/.test(l));
        if (sepIdx <= 0) return block;  // 无分隔行，视为普通文本
        const headerCells = lines[0].replace(/^\||\|$/g, '').split('|').map(c => c.trim());
        const bodyLines = lines.slice(sepIdx + 1).filter(l => /^\|.*\|$/.test(l));
        let tableHtml = '<table class="md-table"><thead><tr>';
        tableHtml += headerCells.map(c => `<th>${c}</th>`).join('');
        tableHtml += '</tr></thead><tbody>';
        for (const line of bodyLines) {
            const cells = line.replace(/^\||\|$/g, '').split('|').map(c => c.trim());
            tableHtml += `<tr>${cells.map(c => `<td>${c}</td>`).join('')}</tr>`;
        }
        tableHtml += '</tbody></table>';
        return tableHtml;
    });

    // 保护代码块与表格内的换行，避免被换行处理破坏
    const mdProtected = [];
    html = html.replace(/<pre[\s\S]*?<\/pre>|<table[\s\S]*?<\/table>/g, function(m) {
        mdProtected.push(m);
        return '@@MD_BLOCK' + (mdProtected.length - 1) + '@@';
    });

    // 统一换行符
    html = html.replace(/\r\n/g, '\n').replace(/\r/g, '\n');
    // 删除空行（一个或多个，含仅空白字符的行）：折叠为单个换行，段落间只留一个普通换行
    html = html.replace(/\n(?:[ \t]*\n)+/g, '\n');
    html = html.replace(/\n/g, '<br>');

    // 还原被保护的代码块/表格
    html = html.replace(/@@MD_BLOCK(\d+)@@/g, function(_, i) {
        return mdProtected[+i];
    });

    // 去掉紧邻块级元素（标题/列表/代码/表格）的 <br>，
    // 避免标题前出现整行空行（标题自带 margin 负责间距）
    html = html.replace(/<br>\s*(?=<h[1-3]|<ul|<ol|<pre|<table)/g, '');
    html = html.replace(/(<\/h[1-3]>|<\/ul>|<\/ol>|<\/pre>|<\/table>)\s*<br>/g, '$1');

    return html;
}

function copyToClipboard(elementId) {
    const element = document.getElementById(elementId);
    const text = element.textContent;
    navigator.clipboard.writeText(text).then(() => {
        showToast('已复制到剪贴板', 'success');
    }).catch(() => {
        showToast('复制失败', 'error');
    });
}
