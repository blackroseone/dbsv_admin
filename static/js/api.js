/**
 * API 封装模块
 * 提供通用的 HTTP 请求封装和错误处理
 */

/**
 * 发送 GET 请求
 * @param {string} url - 请求地址
 * @returns {Promise<any>} 解析后的 JSON 数据
 */
async function apiGet(url) {
    try {
        const response = await fetch(url);
        const contentType = response.headers.get('content-type');

        // 检查响应是否为 JSON
        if (!contentType || !contentType.includes('application/json')) {
            const text = await response.text();
            console.warn(`GET ${url} 返回非 JSON:`, text.substring(0, 200));
            return { error: '服务器返回非 JSON 数据' };
        }

        const data = await response.json();

        if (!response.ok) {
            throw new Error(data.error || `HTTP ${response.status}`);
        }

        return data;
    } catch (error) {
        console.error(`GET ${url} 失败:`, error);
        throw error;
    }
}

/**
 * 发送 POST 请求
 * @param {string} url - 请求地址
 * @param {object} body - 请求体
 * @returns {Promise<any>} 解析后的 JSON 数据
 */
async function apiPost(url, body = null) {
    try {
        const options = {
            method: 'POST',
            headers: {}
        };

        if (body) {
            if (body instanceof FormData) {
                options.body = body;
            } else {
                options.headers['Content-Type'] = 'application/json';
                options.body = JSON.stringify(body);
            }
        }

        const response = await fetch(url, options);
        const data = await response.json();

        if (!response.ok) {
            throw new Error(data.error || `HTTP ${response.status}`);
        }

        return data;
    } catch (error) {
        console.error(`POST ${url} 失败:`, error);
        throw error;
    }
}

/**
 * 发送 PUT 请求
 * @param {string} url - 请求地址
 * @param {object} body - 请求体
 * @returns {Promise<any>} 解析后的 JSON 数据
 */
async function apiPut(url, body) {
    try {
        const response = await fetch(url, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body)
        });

        const data = await response.json();

        if (!response.ok) {
            throw new Error(data.error || `HTTP ${response.status}`);
        }

        return data;
    } catch (error) {
        console.error(`PUT ${url} 失败:`, error);
        throw error;
    }
}

/**
 * 发送 DELETE 请求
 * @param {string} url - 请求地址
 * @returns {Promise<any>} 解析后的 JSON 数据
 */
async function apiDelete(url) {
    try {
        const response = await fetch(url, { method: 'DELETE' });
        const data = await response.json();

        if (!response.ok) {
            throw new Error(data.error || `HTTP ${response.status}`);
        }

        return data;
    } catch (error) {
        console.error(`DELETE ${url} 失败:`, error);
        throw error;
    }
}

/**
 * 发送流式 POST 请求（SSE）
 * @param {string} url - 请求地址
 * @param {object} body - 请求体
 * @param {AbortSignal} signal - 取消信号
 * @returns {Promise<ReadableStreamDefaultReader>} 流读取器
 */
async function apiPostStream(url, body, signal = null) {
    try {
        const options = {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body)
        };

        if (signal) {
            options.signal = signal;
        }

        const response = await fetch(url, options);

        if (!response.ok) {
            const data = await response.json().catch(() => ({}));
            throw new Error(data.error || `HTTP ${response.status}`);
        }

        return response.body.getReader();
    } catch (error) {
        console.error(`Stream POST ${url} 失败:`, error);
        throw error;
    }
}

/**
 * 解析 SSE 数据行
 * @param {string} line - SSE 数据行
 * @returns {object|null} 解析后的数据对象，解析失败返回 null
 */
function parseSSEData(line) {
    if (!line.startsWith('data: ')) {
        return null;
    }

    const data = line.slice(6).trim();
    if (data === '[DONE]') {
        return { done: true };
    }

    try {
        return JSON.parse(data);
    } catch (e) {
        return null;
    }
}

/**
 * 读取 SSE 流并逐行处理
 * @param {ReadableStreamDefaultReader} reader - 流读取器
 * @param {function} onData - 数据回调函数 (data) => void
 * @param {function} onError - 错误回调函数 (error) => void
 * @param {function} onDone - 完成回调函数 () => void
 */
async function readSSEStream(reader, onData, onError, onDone) {
    const decoder = new TextDecoder();

    try {
        while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            const chunk = decoder.decode(value);
            const lines = chunk.split('\n');

            for (const line of lines) {
                if (!line.startsWith('data: ')) continue;

                const data = line.slice(6).trim();
                if (data === '[DONE]') continue;

                try {
                    const parsed = JSON.parse(data);
                    if (parsed.error) {
                        if (onError) onError(parsed.error);
                        return;
                    }
                    if (onData) onData(parsed);
                } catch (e) {
                    // 忽略解析错误
                }
            }
        }

        if (onDone) onDone();
    } catch (error) {
        if (onError) onError(error.message);
    }
}

/**
 * 处理 API 错误并显示 Toast
 * @param {Error} error - 错误对象
 * @param {string} defaultMessage - 默认错误消息
 */
function handleApiError(error, defaultMessage = '操作失败') {
    console.error(error);
    showToast(error.message || defaultMessage, 'error');
}

/**
 * 检查响应是否成功
 * @param {Response} response - fetch 响应对象
 * @returns {Promise<boolean>} 是否成功
 */
async function checkResponse(response) {
    if (!response.ok) {
        const data = await response.json().catch(() => ({}));
        showToast(data.error || `请求失败 (${response.status})`, 'error');
        return false;
    }
    return true;
}
