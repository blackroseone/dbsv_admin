/**
 * 知识图谱可视化模块
 * 使用 vis.js 实现力导向图
 */

// ==================== 全局状态 ====================
let kgNetwork = null;
let kgNodes = new vis.DataSet([]);
let kgEdges = new vis.DataSet([]);
let kgSelectedNode = null;
let kgSearchTimeout = null;

// 实体类型颜色映射
const ENTITY_COLORS = {
    'database_product': '#e74c3c',  // 红色
    'version': '#e67e22',           // 橙色
    'parameter': '#f39c12',         // 黄色
    'sql_statement': '#2ecc71',    // 绿色
    'function': '#27ae60',         // 深绿
    'system_view': '#1abc9c',      // 青色
    'error_code': '#c0392b',       // 深红
    'command_tool': '#3498db',      // 蓝色
    'architecture': '#9b59b6',     // 紫色
    'performance_metric': '#e91e63', // 粉红
    'concept': '#00bcd4',          // 浅蓝
    'troubleshooting': '#ff5722',   // 橙红
    'operating_system': '#795548',  // 棕色
    'hardware': '#607d8b',          // 灰蓝
    'default': '#95a5a6'           // 灰色
};

// 关系类型颜色映射
const RELATION_COLORS = {
    'belongs_to': '#7f8c8d',
    'compatible_with': '#2ecc71',
    'incompatible_with': '#e74c3c',
    'alternative_to': '#3498db',
    'requires': '#f39c12',
    'has_parameter': '#9b59b6',
    'similar_to': '#1abc9c',
    'part_of': '#e67e22',
    'causes': '#c0392b',
    'solves': '#27ae60',
    'related_to': '#95a5a6',
    'default': '#bdc3c7'
};

// ==================== 模块初始化 ====================

function initKGModule() {
    console.log('[KG] 初始化知识图谱模块');
    loadKGStats();
    loadKGEntityTypes();
    loadKGRelationTypes();

    // 如果有选中节点，重新加载
    if (kgSelectedNode) {
        showKGNodeDetail(kgSelectedNode);
    }
}

// ==================== 图谱渲染 ====================

function renderKGGraph(nodes, edges, focusNodeId = null) {
    const container = document.getElementById('kg-graph-container');
    if (!container) return;

    // 清空容器
    container.innerHTML = '';

    // 创建 vis.js 数据集
    kgNodes = new vis.DataSet(nodes.map(n => ({
        id: n.id,
        label: n.name,
        title: `${n.name}\n类型: ${n.type}\n${n.description || ''}`,
        color: {
            background: ENTITY_COLORS[n.type] || ENTITY_COLORS['default'],
            border: '#2c3e50',
            highlight: {
                background: '#f39c12',
                border: '#e67e22'
            }
        },
        font: { color: '#2c3e50', size: 14 },
        shape: 'dot',
        size: 20 + (n.mention_count || 0) * 2,
        data: n
    })));

    kgEdges = new vis.DataSet(edges.map(e => ({
        id: e.id,
        from: e.source,
        to: e.target,
        label: e.relation_type,
        title: `${e.relation_type} (置信度: ${(e.confidence * 100).toFixed(0)}%)`,
        color: {
            color: RELATION_COLORS[e.relation_type] || RELATION_COLORS['default'],
            highlight: '#e74c3c'
        },
        font: { size: 10, align: 'middle' },
        arrows: { to: { enabled: true, scaleFactor: 0.5 } },
        smooth: { type: 'continuous' },
        data: e
    })));

    // 配置选项
    const options = {
        physics: {
            enabled: true,
            barnesHut: {
                gravitationalConstant: -3000,
                centralGravity: 0.3,
                springLength: 150,
                springConstant: 0.04,
                damping: 0.09,
                avoidOverlap: 0.5
            },
            stabilization: {
                enabled: true,
                iterations: 1000,
                updateInterval: 50
            }
        },
        interaction: {
            hover: true,
            tooltipDelay: 200,
            hideEdgesOnDrag: true,
            navigationButtons: true,
            keyboard: true
        },
        layout: {
            improvedLayout: true
        }
    };

    // 创建网络
    kgNetwork = new vis.Network(container, { nodes: kgNodes, edges: kgEdges }, options);

    // 事件监听
    kgNetwork.on('click', function(params) {
        if (params.nodes.length > 0) {
            const nodeId = params.nodes[0];
            kgSelectedNode = nodeId;
            showKGNodeDetail(nodeId);
        } else {
            kgSelectedNode = null;
            closeKGDetail();
        }
    });

    kgNetwork.on('doubleClick', function(params) {
        if (params.nodes.length > 0) {
            const nodeId = params.nodes[0];
            expandKGNodeNeighbors(nodeId);
        }
    });

    // 聚焦到指定节点
    if (focusNodeId) {
        setTimeout(() => {
            kgNetwork.focus(focusNodeId, {
                scale: 1.2,
                animation: { duration: 500, easingFunction: 'easeInOutQuad' }
            });
        }, 500);
    }
}

// ==================== 节点详情 ====================

async function showKGNodeDetail(nodeId) {
    try {
        const response = await fetch(`/api/kg/entities/${nodeId}`);
        const data = await response.json();

        if (data.error) {
            console.error('[KG] 获取实体详情失败:', data.error);
            return;
        }

        const detailPanel = document.getElementById('kg-detail');
        const detailContent = document.getElementById('kg-detail-content');
        const detailTitle = document.getElementById('kg-detail-title');

        detailTitle.textContent = data.entity.name;

        // 构建详情 HTML
        let html = `
            <div class="kg-detail-section">
                <div class="kg-detail-type">
                    <span class="kg-type-badge" style="background: ${ENTITY_COLORS[data.entity.entity_type] || ENTITY_COLORS['default']}">
                        ${data.entity.entity_type}
                    </span>
                    <span class="kg-confidence">置信度: ${(data.entity.confidence * 100).toFixed(0)}%</span>
                </div>
                ${data.entity.description ? `<p class="kg-description">${data.entity.description}</p>` : ''}
                ${data.entity.aliases && data.entity.aliases.length > 0 ? `
                    <div class="kg-aliases">
                        <strong>别名:</strong> ${data.entity.aliases.join(', ')}
                    </div>
                ` : ''}
            </div>
        `;

        // 关系列表
        if (data.relationships && data.relationships.length > 0) {
            html += `
                <div class="kg-detail-section">
                    <h4>🔗 关系 (${data.relationships.length})</h4>
                    <div class="kg-relations-list">
            `;
            data.relationships.forEach(rel => {
                const targetName = rel.direction === 'outgoing' ? rel.to_name : rel.from_name;
                const targetType = rel.direction === 'outgoing' ? rel.to_type : rel.from_type;
                const arrow = rel.direction === 'outgoing' ? '→' : '←';
                html += `
                    <div class="kg-relation-item" onclick="navigateToKGNode(${rel.direction === 'outgoing' ? rel.to_entity_id : rel.from_entity_id})">
                        <span class="kg-relation-type">${rel.relation_type}</span>
                        <span class="kg-relation-arrow">${arrow}</span>
                        <span class="kg-relation-target">${targetName}</span>
                        <span class="kg-type-badge-sm" style="background: ${ENTITY_COLORS[targetType] || ENTITY_COLORS['default']}">${targetType}</span>
                    </div>
                `;
            });
            html += '</div></div>';
        }

        // 关联的 chunk
        if (data.chunks && data.chunks.length > 0) {
            html += `
                <div class="kg-detail-section">
                    <h4>📄 来源文档 (${data.chunks.length})</h4>
                    <div class="kg-chunks-list">
            `;
            data.chunks.slice(0, 5).forEach(chunk => {
                html += `
                    <div class="kg-chunk-item">
                        <div class="kg-chunk-file">${chunk.filename}</div>
                        <div class="kg-chunk-text">${chunk.chunk_text.substring(0, 150)}...</div>
                        <div class="kg-chunk-meta">提及次数: ${chunk.mention_count}</div>
                    </div>
                `;
            });
            if (data.chunks.length > 5) {
                html += `<div class="kg-more">... 还有 ${data.chunks.length - 5} 个来源</div>`;
            }
            html += '</div></div>';
        }

        // 操作按钮
        html += `
            <div class="kg-detail-actions">
                <button class="btn btn-sm btn-primary" onclick="expandKGNodeNeighbors(${nodeId})">展开邻居</button>
                <button class="btn btn-sm btn-secondary" onclick="useEntityInQA(${nodeId}, '${data.entity.name}')">在问答中使用</button>
            </div>
        `;

        detailContent.innerHTML = html;
        detailPanel.style.display = 'block';

        // 更新选择信息
        const info = document.getElementById('kg-selection-info');
        if (info) {
            info.textContent = `选中: ${data.entity.name}`;
        }

    } catch (error) {
        console.error('[KG] 加载实体详情失败:', error);
    }
}

function closeKGDetail() {
    const detailPanel = document.getElementById('kg-detail');
    if (detailPanel) {
        detailPanel.style.display = 'none';
    }
    kgSelectedNode = null;

    const info = document.getElementById('kg-selection-info');
    if (info) {
        info.textContent = '';
    }
}

function clearKGSelection() {
    kgSelectedNode = null;
    closeKGDetail();
    if (kgNetwork) {
        kgNetwork.unselectAll();
    }
}

// ==================== 邻居扩展 ====================

async function expandKGNodeNeighbors(nodeId) {
    try {
        const response = await fetch(`/api/kg/entities/${nodeId}/neighbors?depth=1`);
        const data = await response.json();

        if (data.error) {
            console.error('[KG] 获取邻居失败:', data.error);
            return;
        }

        // 合并新节点和边
        const existingNodeIds = new Set(kgNodes.getIds());
        const existingEdgeIds = new Set(kgEdges.getIds());

        const newNodes = data.nodes.filter(n => !existingNodeIds.has(n.id));
        const newEdges = data.edges.filter(e => !existingEdgeIds.has(e.id));

        if (newNodes.length > 0) {
            kgNodes.add(newNodes.map(n => ({
                id: n.id,
                label: n.name,
                title: `${n.name}\n类型: ${n.type}`,
                color: {
                    background: ENTITY_COLORS[n.type] || ENTITY_COLORS['default'],
                    border: '#2c3e50'
                },
                font: { color: '#2c3e50', size: 14 },
                shape: 'dot',
                size: 20,
                data: n
            })));
        }

        if (newEdges.length > 0) {
            kgEdges.add(newEdges.map(e => ({
                id: e.id,
                from: e.source,
                to: e.target,
                label: e.relation_type,
                color: {
                    color: RELATION_COLORS[e.relation_type] || RELATION_COLORS['default']
                },
                arrows: { to: { enabled: true, scaleFactor: 0.5 } },
                data: e
            })));
        }

        // 聚焦到中心节点
        if (kgNetwork) {
            kgNetwork.focus(nodeId, {
                scale: 1.0,
                animation: { duration: 300 }
            });
        }

        showToast(`已展开 ${newNodes.length} 个邻居节点`);

    } catch (error) {
        console.error('[KG] 展开邻居失败:', error);
    }
}

function expandAllNeighbors() {
    if (!kgSelectedNode) {
        showToast('请先选择一个节点');
        return;
    }
    expandKGNodeNeighbors(kgSelectedNode);
}

function navigateToKGNode(nodeId) {
    kgSelectedNode = nodeId;
    showKGNodeDetail(nodeId);

    if (kgNetwork) {
        kgNetwork.focus(nodeId, {
            scale: 1.2,
            animation: { duration: 300 }
        });
        kgNetwork.selectNodes([nodeId]);
    }
}

// ==================== 搜索功能 ====================

async function kgSearch() {
    const input = document.getElementById('kg-search-input');
    const keyword = input ? input.value.trim() : '';

    if (!keyword) {
        showToast('请输入搜索关键词');
        return;
    }

    try {
        const response = await fetch(`/api/kg/entities/search?q=${encodeURIComponent(keyword)}&neighbors=true&depth=1`);
        const data = await response.json();

        if (data.error) {
            showToast('搜索失败: ' + data.error);
            return;
        }

        if (data.subgraph) {
            renderKGGraph(data.subgraph.nodes, data.subgraph.edges);
            if (data.entities && data.entities.length > 0) {
                kgSelectedNode = data.entities[0].id;
                showKGNodeDetail(data.entities[0].id);
            }
        } else if (data.entities && data.entities.length > 0) {
            // 只显示搜索结果
            const nodes = data.entities.map(e => ({
                id: e.id,
                name: e.name,
                type: e.entity_type,
                description: e.description,
                confidence: e.confidence
            }));
            renderKGGraph(nodes, []);
        } else {
            showToast('未找到匹配的实体');
        }

    } catch (error) {
        console.error('[KG] 搜索失败:', error);
        showToast('搜索失败');
    }
}

function debouncedKGSearch() {
    if (kgSearchTimeout) {
        clearTimeout(kgSearchTimeout);
    }
    kgSearchTimeout = setTimeout(() => {
        kgSearch();
    }, 500);
}

// ==================== 统计和筛选 ====================

async function loadKGStats() {
    try {
        const response = await fetch('/api/kg/stats');
        const data = await response.json();

        const container = document.getElementById('kg-stats-content');
        if (!container) return;

        container.innerHTML = `
            <div class="kg-stat-item">
                <span class="kg-stat-value">${data.entity_count || 0}</span>
                <span class="kg-stat-label">实体</span>
            </div>
            <div class="kg-stat-item">
                <span class="kg-stat-value">${data.relation_count || 0}</span>
                <span class="kg-stat-label">关系</span>
            </div>
            <div class="kg-stat-item">
                <span class="kg-stat-value">${data.chunk_link_count || 0}</span>
                <span class="kg-stat-label">文档关联</span>
            </div>
        `;

    } catch (error) {
        console.error('[KG] 加载统计失败:', error);
    }
}

async function loadKGEntityTypes() {
    try {
        const response = await fetch('/api/kg/entity-types');
        const data = await response.json();

        const container = document.getElementById('kg-entity-types');
        if (!container) return;

        if (!data.types || data.types.length === 0) {
            container.innerHTML = '<div class="empty-message">暂无实体</div>';
            return;
        }

        container.innerHTML = data.types.map(t => `
            <label class="kg-filter-item">
                <input type="checkbox" value="${t.entity_type}" checked onchange="filterKGByType()">
                <span class="kg-filter-color" style="background: ${ENTITY_COLORS[t.entity_type] || ENTITY_COLORS['default']}"></span>
                <span class="kg-filter-name">${t.entity_type}</span>
                <span class="kg-filter-count">${t.count}</span>
            </label>
        `).join('');

    } catch (error) {
        console.error('[KG] 加载实体类型失败:', error);
    }
}

async function loadKGRelationTypes() {
    try {
        const response = await fetch('/api/kg/stats');
        const data = await response.json();

        const container = document.getElementById('kg-relation-types');
        if (!container) return;

        if (!data.relation_types || data.relation_types.length === 0) {
            container.innerHTML = '<div class="empty-message">暂无关系</div>';
            return;
        }

        container.innerHTML = data.relation_types.map(t => `
            <label class="kg-filter-item">
                <input type="checkbox" value="${t.relation_type}" checked onchange="filterKGByRelation()">
                <span class="kg-filter-color" style="background: ${RELATION_COLORS[t.relation_type] || RELATION_COLORS['default']}"></span>
                <span class="kg-filter-name">${t.relation_type}</span>
                <span class="kg-filter-count">${t.count}</span>
            </label>
        `).join('');

    } catch (error) {
        console.error('[KG] 加载关系类型失败:', error);
    }
}

function filterKGByType() {
    const checkboxes = document.querySelectorAll('#kg-entity-types input[type="checkbox"]');
    const selectedTypes = Array.from(checkboxes)
        .filter(cb => cb.checked)
        .map(cb => cb.value);

    if (kgNodes.length === 0) return;

    const allNodes = kgNodes.get();
    const nodesToHide = allNodes.filter(n => !selectedTypes.includes(n.data.type));
    const nodesToShow = allNodes.filter(n => selectedTypes.includes(n.data.type));

    kgNodes.update(nodesToHide.map(n => ({ id: n.id, hidden: true })));
    kgNodes.update(nodesToShow.map(n => ({ id: n.id, hidden: false })));
}

function filterKGByRelation() {
    const checkboxes = document.querySelectorAll('#kg-relation-types input[type="checkbox"]');
    const selectedTypes = Array.from(checkboxes)
        .filter(cb => cb.checked)
        .map(cb => cb.value);

    if (kgEdges.length === 0) return;

    const allEdges = kgEdges.get();
    const edgesToHide = allEdges.filter(e => !selectedTypes.includes(e.data.relation_type));
    const edgesToShow = allEdges.filter(e => selectedTypes.includes(e.data.relation_type));

    kgEdges.update(edgesToHide.map(e => ({ id: e.id, hidden: true })));
    kgEdges.update(edgesToShow.map(e => ({ id: e.id, hidden: false })));
}

// ==================== 视图控制 ====================

function resetKGView() {
    if (kgNetwork) {
        kgNetwork.fit({
            animation: { duration: 500, easingFunction: 'easeInOutQuad' }
        });
    }
}

function useEntityInQA(entityId, entityName) {
    switchModule('qa');
    setTimeout(() => {
        const input = document.getElementById('qa-question');
        if (input) {
            input.value = `关于 ${entityName} 的详细信息`;
            input.focus();
        }
    }, 300);
}

// ==================== 辅助函数 ====================

function showToast(message) {
    const toast = document.getElementById('toast');
    if (toast) {
        toast.textContent = message;
        toast.style.display = 'block';
        setTimeout(() => {
            toast.style.display = 'none';
        }, 3000);
    }
}
