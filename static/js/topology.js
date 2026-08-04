/**
 * 集群拓扑模块
 */

const TopologyModule = {
    currentServerId: null
};

// 节点类型配置
const nodeTypeConfig = {
    '计算节点': { icon: '🔲', color: '#2196F3', borderColor: '#1976D2' },
    '存储节点': { icon: '💾', color: '#4CAF50', borderColor: '#388E3C' },
    '监控节点': { icon: '📊', color: '#FF9800', borderColor: '#F57C00' },
    '虚拟机': { icon: '🔷', color: '#9C27B0', borderColor: '#7B1FA2' },
    '海光物理机': { icon: '🔶', color: '#00BCD4', borderColor: '#0097A7' },
    '海光虚拟机': { icon: '🔷', color: '#00BCD4', borderColor: '#0097A7' },
    '鲲鹏物理机': { icon: '🔶', color: '#E91E63', borderColor: '#C2185B' },
    '鲲鹏虚拟机': { icon: '🔷', color: '#E91E63', borderColor: '#C2185B' },
};

// 硬件类型配置
const hardwareTypeConfig = {
    '非信创物理机': '🔲',
    '信创物理机': '🔶',
    '非信创虚拟机': '🔷',
    '信创虚拟机': '🔷',
};

async function loadClusters() {
    try {
        const response = await fetch('/api/topology/resource-pools');
        const data = await response.json();

        // 处理返回的数据格式
        let resourcePools = [];
        if (Array.isArray(data)) {
            resourcePools = data;
        } else if (data.resource_pools) {
            resourcePools = data.resource_pools;
        }

        // 更新拓扑视图的资源池列表
        const listDiv = document.getElementById('topology-cluster-list');
        if (listDiv) {
            if (resourcePools && resourcePools.length > 0) {
                listDiv.innerHTML = resourcePools.map(pool => {
                    const dbType = dbTypes.find(t => t.id === pool.db_type);
                    const envMap = {
                        'production': '🟢',
                        'testing': '🟡',
                        'development': '🔵'
                    };

                    // 计算该资源池的统计数据
                    const clusterCount = pool.cluster_count || 0;
                    const serverCount = pool.server_count || 0;
                    const tenantCount = pool.tenant_count || 0;
                    const instanceCount = pool.instance_count || 0;

                    return `
                        <div class="cluster-item ${currentClusterId === pool.id ? 'active' : ''}"
                             onclick="selectCluster('${escapeHtml(pool.id)}')">
                            <div class="cluster-name">${dbType ? dbType.icon : ''} ${escapeHtml(pool.name)}</div>
                            <div class="cluster-info">${envMap[pool.environment] || ''} | ${serverCount}节点 | ${clusterCount}集群 | ${instanceCount}实例 | ${tenantCount}租户</div>
                        </div>
                    `;
                }).join('');
            } else {
                listDiv.innerHTML = '<div class="empty-message">暂无资源池，点击"添加资源池"开始</div>';
            }
        }
    } catch (error) {
        showToast('加载资源池列表失败', 'error');
    }
}

async function selectCluster(clusterId) {
    currentClusterId = clusterId;
    loadClusters();

    try {
        // 获取集群的完整数据（包含服务器、实例等）
        const response = await fetch(`/api/topology/clusters`);
        const data = await response.json();

        // 处理返回的数据格式
        let clusters = [];
        if (data.clusters) {
            clusters = data.clusters;
        } else if (Array.isArray(data)) {
            clusters = data;
        }

        // 找到对应的集群
        const cluster = clusters.find(c => c.id === clusterId);

        if (cluster) {
            renderTopology(cluster);
        } else {
            // 如果找不到集群数据，显示空状态
            const container = document.getElementById('topology-graph-view');
            container.innerHTML = `
                <div class="welcome-message">
                    <div class="welcome-icon">🖥️</div>
                    <h3>暂无物理机</h3>
                    <p>点击"➕ 添加节点"添加节点</p>
                </div>
            `;
        }
    } catch (error) {
        console.error('加载资源池详情失败:', error);
        showToast('加载资源池详情失败: ' + error.message, 'error');
    }
}

function _renderClusterHeader(cluster) {
    // 渲染集群头部
    return `
        <div class="topology-header">
            <div class="topology-title" onclick="editResourcePoolName('${escapeHtml(cluster.id)}', '${escapeJs(cluster.name)}')" title="点击重命名">${escapeHtml(cluster.name)}</div>
            <div class="topology-actions">
                <button class="btn btn-sm btn-primary" onclick="showAddServerDialog('${escapeHtml(cluster.id)}')">➕ 添加节点</button>
                <button class="btn btn-sm btn-secondary" onclick="showEditResourcePoolDialog('${escapeHtml(cluster.id)}')">✏️ 修改资源池</button>
                <button class="btn btn-sm btn-danger" onclick="deleteResourcePool('${escapeHtml(cluster.id)}')">删除资源池</button>
            </div>
        </div>
    `;
}


function _renderClusterSummary(cluster) {
    // 渲染集群概览信息
    let totalCpu = 0;
    let totalMem = 0;
    cluster.servers.forEach(s => {
        if (s.cpu) totalCpu += parseInt(s.cpu) || 0;
        if (s.memory) totalMem += parseInt(s.memory) || 0;
    });
    const totalInstances = cluster.servers.reduce((sum, s) => sum + (s.instances ? s.instances.length : 0), 0);

    return `
        <div class="cluster-summary">
            <span class="summary-item">🖥️ ${cluster.servers.length} 物理机</span>
            <span class="summary-item">⚡ ${totalCpu}C CPU</span>
            <span class="summary-item">💾 ${totalMem}G 内存</span>
            <span class="summary-item">📦 ${totalInstances} 实例</span>
            <span class="summary-item">📋 ${cluster.tenants ? cluster.tenants.length : 0} 租户</span>
        </div>
    `;
}


function _renderServerCard(server) {
    // 渲染单个服务器卡片
    const nodeRole = server.node_role || '计算节点';
    const hardwareType = server.hardware_type || '非信创物理机';
    let nodeConfig = nodeTypeConfig[nodeRole] || nodeTypeConfig['计算节点'];

    // 解析多IP
    let ipInfo = '';
    if (server.description) {
        const vipMatch = server.description.match(/VIP:\s*([^|]+)/);
        const scanMatch = server.description.match(/ScanIP:\s*([^|]+)/);

        if (vipMatch && vipMatch[1].trim() !== 'None') {
            ipInfo += `<span class="ip-tag vip">VIP:${escapeHtml(vipMatch[1].trim())}</span>`;
        }
        if (scanMatch && scanMatch[1].trim() !== 'None') {
            ipInfo += `<span class="ip-tag scan">Scan:${escapeHtml(scanMatch[1].trim())}</span>`;
        }
    }

    const cpu = server.cpu || '';
    const memory = server.memory || '';

    let serverHtml = `
        <div class="topology-server" style="border-color: ${nodeConfig.borderColor}; border-width: 2px;" onclick="showServerDetail('${escapeHtml(server.id)}')">
            <div class="server-header" style="border-bottom-color: ${nodeConfig.borderColor};">
                <div class="server-header-top">
                    <span class="server-icon" style="color: ${nodeConfig.color};">${hardwareTypeConfig[hardwareType] || '🔲'}</span>
                    <div class="server-info">
                        <span class="server-name">${escapeHtml(server.name)}</span>
                        <span class="server-type">${escapeHtml(nodeRole)} | ${escapeHtml(hardwareType)}</span>
                        ${server.datacenter ? `<span class="server-datacenter">📍 ${escapeHtml(server.datacenter)}</span>` : ''}
                    </div>
                </div>
                <div class="server-header-bottom">
                    <span class="server-host">${escapeHtml(server.host || '')}</span>
                    <div class="server-actions">
                        <button class="btn-icon btn-add" onclick="event.stopPropagation(); showAddInstanceDialog('${escapeHtml(server.id)}')" title="添加实例">➕</button>
                        <button class="btn-icon btn-edit" onclick="event.stopPropagation(); showEditServerDialog('${escapeHtml(server.id)}', '${escapeJs(server.name)}', '${escapeJs(server.host || '')}', '${escapeJs(server.datacenter || '')}', '${escapeJs(server.cluster_id || '')}', '${escapeJs(server.cluster_name || '')}', '${escapeJs(cpu)}', '${escapeJs(memory)}', '${escapeJs(server.description || '')}', '${escapeJs(server.node_role || '计算节点')}', '${escapeJs(server.hardware_type || '非信创物理机')}', '${escapeJs(server.sn || '')}')" title="编辑节点">✏️</button>
                        <button class="btn-icon btn-delete" onclick="event.stopPropagation(); deleteServer('${escapeHtml(server.id)}')" title="删除节点">🗑️</button>
                    </div>
                </div>
            </div>
            <div class="server-ips">
                ${ipInfo}
            </div>
            <div class="server-specs">
                ${cpu ? `<span class="spec-tag">⚡ ${escapeHtml(cpu)}C</span>` : ''}
                ${memory ? `<span class="spec-tag">🧠 ${escapeHtml(memory)}G</span>` : ''}
            </div>
            <div class="server-instances">
    `;

    if (server.instances && server.instances.length > 0) {
        server.instances.forEach(instance => {
            const tenantName = instance.tenant_name || '';
            serverHtml += `
                <div class="topology-instance" onclick="event.stopPropagation(); showInstanceDetail('${escapeHtml(instance.id)}')">
                    <div class="instance-header">
                        <span class="instance-name">${escapeHtml(instance.name)}</span>
                        <span class="instance-port">:${escapeHtml(instance.port)}</span>
                        <span class="instance-actions">
                            <button class="btn-icon btn-edit" onclick="event.stopPropagation(); showEditInstanceDialog('${escapeHtml(instance.id)}', '${escapeJs(instance.name)}', '${escapeJs(instance.port)}', '${escapeJs(instance.cpu || '')}','${escapeJs(instance.memory || '')}', '${escapeJs(instance.description || '')}', '${escapeJs(instance.role || 'slave')}')" title="编辑">✏️</button>
                            <button class="btn-icon btn-delete" onclick="event.stopPropagation(); deleteInstance('${escapeHtml(instance.id)}')" title="删除">🗑️</button>
                        </span>
                    </div>
                    <div class="instance-meta">
                        <span class="instance-role-tag" style="background-color: ${getNodeColor(instance.role || 'slave')}">${instance.role === 'master' ? '主' : instance.role === 'standalone' ? '独' : '从'}</span>
                        ${tenantName ? `<span class="instance-tenant-tag">${escapeHtml(tenantName)}</span>` : ''}
                    </div>
                    <div class="instance-spec">${escapeHtml(instance.cpu || '-')}C / ${escapeHtml(instance.memory|| '-')}G</div>
                </div>
            `;
        });
    } else {
        serverHtml += `<div class="no-instances">暂无实例</div>`;
    }

    serverHtml += `
            </div>
        </div>
    `;

    return serverHtml;
}


function _groupServersByDatacenterAndCluster(servers) {
    // 按机房和集群分组服务器
    const datacenterGroups = {};

    servers.forEach(server => {
        const dc = server.datacenter || '默认机房';
        let clusterName = server.cluster_name || '默认集群';

        if (!datacenterGroups[dc]) {
            datacenterGroups[dc] = {};
        }
        if (!datacenterGroups[dc][clusterName]) {
            datacenterGroups[dc][clusterName] = { compute: [], storage: [], monitor: [], other: [] };
        }

        const nodeRole = server.node_role || '计算节点';

        if (nodeRole === '存储节点') {
            datacenterGroups[dc][clusterName].storage.push(server);
        } else if (nodeRole === '监控节点') {
            datacenterGroups[dc][clusterName].monitor.push(server);
        } else if (nodeRole === '计算节点') {
            datacenterGroups[dc][clusterName].compute.push(server);
        } else {
            datacenterGroups[dc][clusterName].other.push(server);
        }
    });

    return datacenterGroups;
}


function _renderDatacenterSection(dcName, clusterGroups) {
    // 渲染单个机房区域
    let dcServerCount = 0;
    Object.values(clusterGroups).forEach(groups => {
        dcServerCount += groups.compute.length + groups.storage.length + groups.monitor.length + groups.other.length;
    });

    let html = `<div class="topology-datacenter">`;
    html += `<div class="datacenter-title">📍 ${escapeHtml(dcName)} (${dcServerCount} 节点)</div>`;

    Object.entries(clusterGroups).forEach(([clusterName, groups]) => {
        const clusterServerCount = groups.compute.length + groups.storage.length + groups.monitor.length + groups.other.length;
        html += `<div class="topology-cluster-group">`;
        html += `<div class="cluster-group-title">🔹 ${escapeHtml(clusterName)} (${clusterServerCount} 节点)</div>`;

        // 按角色顺序渲染：监控 → 计算 → 存储 → 其他
        const roleOrder = [
            { key: 'monitor', label: '📊 监控节点' },
            { key: 'compute', label: '🔲 计算节点' },
            { key: 'storage', label: '💾 存储节点' },
            { key: 'other', label: '🔧 其他节点' }
        ];

        roleOrder.forEach(({ key, label }) => {
            const servers = groups[key];
            if (servers.length > 0) {
                html += `<div class="topology-section-title">${label} (${servers.length})</div>`;
                html += `<div class="topology-servers">`;
                servers.forEach(server => {
                    html += _renderServerCard(server);
                });
                html += `</div>`;
            }
        });

        html += `</div>`;
    });

    html += `</div>`;
    return html;
}


function _renderTenantSection(cluster) {
    // 渲染租户信息区域
    const typeMap = {
        'master-slave': '主从复制',
        'master-master': '双主复制',
        'rac': 'RAC集群',
        'cluster': '集群'
    };

    const specMap = {
        'micro-4c16g': '微型-4C16G',
        'small-8c32g': '小型-8C32G',
        'small-16c64g': '小型-16C64G',
        'medium-32c128g': '中型-32C128G',
        'large-64c256g': '大型-64C256G',
        'dedicated-128c512g': '独享-128C512G'
    };

    let html = `<div class="topology-tenants">`;
    html += `<div class="tenants-title">📋 租户（实例集群）<button class="btn btn-sm btn-primary" onclick="showAddTenantDialog('${escapeHtml(cluster.id)}')">➕ 添加租户</button></div>`;

    if (cluster.tenants && cluster.tenants.length > 0) {
        cluster.tenants.forEach(tenant => {
            const tenantInstanceCount = tenant.instances ? tenant.instances.length : 0;

            html += `
                <div class="topology-tenant">
                    <div class="tenant-header">
                        <span class="tenant-name">${escapeHtml(tenant.name)}</span>
                        <span class="tenant-type">${typeMap[tenant.topology_type] || tenant.topology_type}</span>
                        <span class="tenant-spec">${specMap[tenant.spec] || tenant.spec || '小型-8C32G'}</span>
                        <span class="tenant-count">${tenantInstanceCount} 实例</span>
                        <button class="btn btn-xs btn-secondary" onclick="event.stopPropagation(); showEditTenantDialog('${escapeHtml(tenant.id)}', '${escapeJs(tenant.name)}', '${escapeJs(tenant.topology_type)}', '${escapeJs(tenant.spec || 'small-8c32g')}', '${escapeJs(tenant.description || '')}')">编辑</button>
                        <button class="btn btn-xs btn-danger" onclick="event.stopPropagation(); deleteTenant('${escapeHtml(tenant.id)}')">删除</button>
                    </div>
                    <div class="tenant-instances">
            `;

            if (tenant.instances && tenant.instances.length > 0) {
                tenant.instances.forEach(ti => {
                    const roleIcon = ti.role === 'master' ? '🟢' : '🔵';
                    html += `<span class="tenant-instance">${roleIcon} ${escapeHtml(ti.host)}:${escapeHtml(ti.port)}</span>`;
                });
            }

            html += `</div></div>`;
        });
    }

    html += `</div>`;
    return html;
}


function renderTopology(cluster) {
    const container = document.getElementById('topology-graph-view');

    // 如果cluster为null,显示空状态
    if (!cluster) {
        container.innerHTML = `
            <div class="welcome-message">
                <div class="welcome-icon">🖥️</div>
                <h3>暂无数据</h3>
                <p>请选择资源池</p>
            </div>
        `;
        return;
    }

    // 构建HTML拓扑图
    let html = `<div class="topology-canvas">`;
    html += _renderClusterHeader(cluster);

    if (!cluster.servers || cluster.servers.length === 0) {
        html += `
            <div class="welcome-message">
                <div class="welcome-icon">🖥️</div>
                <h3>暂无物理机</h3>
                <p>点击"➕ 添加节点"添加节点</p>
            </div>
        `;
        html += `</div>`;
        container.innerHTML = html;
        return;
    }

    // 集群概览
    html += _renderClusterSummary(cluster);

    // 按机房和集群分组渲染
    const datacenterGroups = _groupServersByDatacenterAndCluster(cluster.servers);
    Object.entries(datacenterGroups).forEach(([dcName, clusterGroups]) => {
        html += _renderDatacenterSection(dcName, clusterGroups);
    });

    // 租户信息
    html += _renderTenantSection(cluster);

    html += `</div>`;
    container.innerHTML = html;
}

// 显示节点详情（点击节点时展示）
async function showServerDetail(serverId) {
    try {
        // 从当前集群数据中找到该节点
        const response = await fetch('/api/topology/clusters');
        const data = await response.json();
        const cluster = data.clusters.find(c => c.id === currentClusterId);

        if (!cluster) return;

        const server = cluster.servers.find(s => s.id === serverId);
        if (!server) return;

        const detailPanel = document.getElementById('topology-detail');
        const detailContent = document.getElementById('detail-content');

        // 使用新的字段
        const nodeRole = server.node_role || '计算节点';
        const hardwareType = server.hardware_type || '非信创物理机';

        // 解析VIP和ScanIP
        let vip = '-', scanIp = '-';
        if (server.description) {
            const vipMatch = server.description.match(/VIP:\s*([^|]+)/);
            const scanMatch = server.description.match(/ScanIP:\s*([^|]+)/);
            if (vipMatch) vip = vipMatch[1].trim();
            if (scanMatch) scanIp = scanMatch[1].trim();
        }

        // 解析CPU和内存 - 直接从字段获取
        const cpu = server.cpu || '';
        const memory = server.memory || '';

        detailContent.innerHTML = `
            <div class="detail-item">
                <div class="detail-label">节点名称</div>
                <div class="detail-value">${escapeHtml(server.name)}</div>
            </div>
            <div class="detail-item">
                <div class="detail-label">SN 序列号</div>
                <div class="detail-value">${escapeHtml(server.sn || '-')}</div>
            </div>
            <div class="detail-item">
                <div class="detail-label">IP 地址</div>
                <div class="detail-value">${escapeHtml(server.host || '-')}</div>
            </div>
            <div class="detail-item">
                <div class="detail-label">节点角色</div>
                <div class="detail-value">${escapeHtml(nodeRole)}</div>
            </div>
            <div class="detail-item">
                <div class="detail-label">节点设备</div>
                <div class="detail-value">${escapeHtml(hardwareType)}</div>
            </div>
            <div class="detail-item">
                <div class="detail-label">机房</div>
                <div class="detail-value">${escapeHtml(server.datacenter || '-')}</div>
            </div>
            <div class="detail-item">
                <div class="detail-label">CPU</div>
                <div class="detail-value">${escapeHtml(cpu || '-')} 核</div>
            </div>
            <div class="detail-item">
                <div class="detail-label">内存</div>
                <div class="detail-value">${escapeHtml(memory || '-')} GB</div>
            </div>
            <div class="detail-item">
                <div class="detail-label">VIP</div>
                <div class="detail-value">${escapeHtml(vip)}</div>
            </div>
            <div class="detail-item">
                <div class="detail-label">Scan IP</div>
                <div class="detail-value">${escapeHtml(scanIp)}</div>
            </div>
            <div class="detail-item">
                <div class="detail-label">实例数</div>
                <div class="detail-value">${server.instances ? server.instances.length : 0} 个</div>
            </div>
            ${server.description ? `
            <div class="detail-item">
                <div class="detail-label">描述</div>
                <div class="detail-value">${escapeHtml(server.description)}</div>
            </div>
            ` : ''}
        `;

        detailPanel.style.display = 'flex';
    } catch (error) {
        showToast('获取节点详情失败', 'error');
    }
}

// 显示实例详情
async function showInstanceDetail(instanceId) {
    try {
        const response = await fetch(`/api/topology/instances/${instanceId}`);
        const data = await response.json();

        if (response.ok) {
            const detailPanel = document.getElementById('topology-detail');
            const detailContent = document.getElementById('detail-content');

            detailContent.innerHTML = `
                <div class="detail-item">
                    <div class="detail-label">实例名称</div>
                    <div class="detail-value">${escapeHtml(data.name)}</div>
                </div>
                <div class="detail-item">
                    <div class="detail-label">IP 地址</div>
                    <div class="detail-value">${escapeHtml(data.server_host || '-')}</div>
                </div>
                <div class="detail-item">
                    <div class="detail-label">端口</div>
                    <div class="detail-value">${escapeHtml(data.port)}</div>
                </div>
                <div class="detail-item">
                    <div class="detail-label">CPU</div>
                    <div class="detail-value">${escapeHtml(data.cpu || '-')} 核</div>
                </div>
                <div class="detail-item">
                    <div class="detail-label">内存</div>
                    <div class="detail-value">${escapeHtml(data.memory || '-')} GB</div>
                </div>
                <div class="detail-item">
                    <div class="detail-label">所属物理机</div>
                    <div class="detail-value">${escapeHtml(data.server_name || '-')}</div>
                </div>
                <div class="detail-item">
                    <div class="detail-label">所属集群</div>
                    <div class="detail-value">${escapeHtml(data.cluster_name || '-')}</div>
                </div>
                ${data.description ? `
                <div class="detail-item">
                    <div class="detail-label">描述</div>
                    <div class="detail-value">${escapeHtml(data.description)}</div>
                </div>
                ` : ''}
                ${data.tenants && data.tenants.length > 0 ? `
                <div class="detail-section">
                    <h4>所属租户</h4>
                    ${data.tenants.map(t => `
                        <div class="tenant-item">
                            <div class="tenant-name">${escapeHtml(t.name)}</div>
                            <div class="tenant-role">角色: ${t.role === 'master' ? '🟢 主节点' : '🔵 从节点'}</div>
                        </div>
                    `).join('')}
                </div>
                ` : ''}
            `;

            detailPanel.style.display = 'flex';
        } else {
            showToast('获取实例详情失败', 'error');
        }
    } catch (error) {
        showToast('获取实例详情失败', 'error');
    }
}

function closeDetailPanel() {
    document.getElementById('topology-detail').style.display = 'none';
}

function getNodeColor(role) {
    const colors = {
        'master': '#4CAF50',
        'slave': '#2196F3',
        'standalone': '#9E9E9E'
    };
    return colors[role] || '#607D8B';
}

// ==================== 对话框函数 ====================

let currentEditClusterId = null;

function showAddClusterDialog() {
    document.getElementById('modal-add-cluster').style.display = 'flex';
}

// 显示编辑集群对话框
async function showEditClusterDialog(clusterId) {
    currentEditClusterId = clusterId;

    try {
        const response = await fetch('/api/topology/clusters');
        const data = await response.json();
        const cluster = data.clusters.find(c => c.id === clusterId);

        if (!cluster) {
            showToast('集群不存在', 'error');
            return;
        }

        document.getElementById('edit-cluster-name').value = cluster.name || '';
        document.getElementById('edit-cluster-db-type').value = cluster.db_type || '';
        document.getElementById('edit-cluster-environment').value = cluster.environment || 'production';
        document.getElementById('edit-cluster-description').value = cluster.description || '';

        document.getElementById('modal-edit-cluster').style.display = 'flex';
    } catch (error) {
        showToast('加载集群信息失败', 'error');
    }
}

// 更新集群信息
async function updateCluster() {
    const name = document.getElementById('edit-cluster-name').value.trim();
    const dbType = document.getElementById('edit-cluster-db-type').value;
    const environment = document.getElementById('edit-cluster-environment').value;
    const description = document.getElementById('edit-cluster-description').value.trim();

    if (!name || !dbType) {
        showToast('请填写资源池名称和数据库类型', 'error');
        return;
    }

    try {
        const response = await fetch(`/api/topology/resource-pools/${currentEditClusterId}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                name: name,
                db_type: dbType,
                environment: environment,
                description: description
            })
        });

        if (response.ok) {
            showToast('修改成功', 'success');
            closeModal('modal-edit-cluster');
            loadClusters();
            // 如果当前选中的资源池被修改，刷新拓扑图
            if (currentClusterId === currentEditClusterId) {
                const clustersResponse = await fetch('/api/topology/clusters');
                const data = await clustersResponse.json();
                let clusters = [];
                if (data.clusters) {
                    clusters = data.clusters;
                } else if (Array.isArray(data)) {
                    clusters = data;
                }
                const cluster = clusters.find(c => c.id === currentEditClusterId);
                if (cluster) {
                    renderTopology(cluster);
                }
            }
        } else {
            showToast('修改失败', 'error');
        }
    } catch (error) {
        showToast('修改失败', 'error');
    }
}

// 编辑集群名称
async function editClusterName(clusterId, currentName) {
    const newName = prompt('请输入新的集群名称:', currentName);
    if (!newName || newName.trim() === '' || newName.trim() === currentName) {
        return;
    }

    try {
        const response = await fetch(`/api/topology/clusters/${clusterId}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name: newName.trim() })
        });

        if (response.ok) {
            showToast('集群名称修改成功', 'success');
            loadClusters();
            // 如果当前选中的集群被重命名，刷新拓扑图
            if (currentClusterId === clusterId) {
                const clustersResponse = await fetch('/api/topology/clusters');
                const data = await clustersResponse.json();
                const cluster = data.clusters.find(c => c.id === clusterId);
                if (cluster) {
                    renderTopology(cluster);
                }
            }
        } else {
            showToast('修改失败', 'error');
        }
    } catch (error) {
        showToast('修改失败', 'error');
    }
}

// 资源池相关函数
async function showEditResourcePoolDialog(resourcePoolId) {
    currentEditClusterId = resourcePoolId;

    try {
        const response = await fetch('/api/topology/resource-pools');
        const data = await response.json();

        // 处理返回的数据格式
        let resourcePools = [];
        if (Array.isArray(data)) {
            resourcePools = data;
        } else if (data.resource_pools) {
            resourcePools = data.resource_pools;
        }

        const resourcePool = resourcePools.find(p => p.id === resourcePoolId);

        if (!resourcePool) {
            showToast('资源池不存在', 'error');
            return;
        }

        document.getElementById('edit-cluster-name').value = resourcePool.name || '';
        document.getElementById('edit-cluster-db-type').value = resourcePool.db_type || '';
        document.getElementById('edit-cluster-environment').value = resourcePool.environment || 'production';
        document.getElementById('edit-cluster-description').value = resourcePool.description || '';

        document.getElementById('modal-edit-cluster').style.display = 'flex';
    } catch (error) {
        showToast('加载资源池信息失败', 'error');
    }
}

async function editResourcePoolName(resourcePoolId, currentName) {
    const newName = prompt('请输入新的资源池名称:', currentName);
    if (!newName || newName.trim() === '' || newName.trim() === currentName) {
        return;
    }

    try {
        const response = await fetch(`/api/topology/resource-pools/${resourcePoolId}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name: newName.trim() })
        });

        if (response.ok) {
            showToast('资源池名称修改成功', 'success');
            loadClusters();
            // 如果当前选中的资源池被重命名，刷新拓扑图
            if (currentClusterId === resourcePoolId) {
                const clustersResponse = await fetch('/api/topology/clusters');
                const data = await clustersResponse.json();
                let clusters = [];
                if (data.clusters) {
                    clusters = data.clusters;
                } else if (Array.isArray(data)) {
                    clusters = data;
                }
                const cluster = clusters.find(c => c.id === resourcePoolId);
                if (cluster) {
                    renderTopology(cluster);
                }
            }
        } else {
            showToast('修改失败', 'error');
        }
    } catch (error) {
        showToast('修改失败', 'error');
    }
}

async function deleteResourcePool(resourcePoolId) {
    if (!confirm('确定要删除该资源池吗？')) return;

    try {
        const response = await fetch(`/api/topology/resource-pools/${resourcePoolId}`, { method: 'DELETE' });
        if (response.ok) {
            showToast('删除成功', 'success');
            if (currentClusterId === resourcePoolId) {
                currentClusterId = null;
                const graphView = document.getElementById('topology-graph-view');
                if (graphView) {
                    graphView.innerHTML = `
                    <div class="welcome-message">
                        <div class="welcome-icon">🗺️</div>
                        <h3>集群拓扑</h3>
                        <p>选择左侧的资源池查看拓扑图</p>
                    </div>
                `;
                }
            }
            loadClusters();
        } else {
            showToast('删除失败', 'error');
        }
    } catch (error) {
        showToast('删除失败', 'error');
    }
}

function showAddServerDialog(clusterId) {
    currentClusterId = clusterId;
    document.getElementById('modal-add-server').style.display = 'flex';
}

// 添加集群
async function addCluster() {
    const name = document.getElementById('cluster-name').value.trim();
    const dbType = document.getElementById('cluster-db-type').value;
    const environment = document.getElementById('cluster-environment').value;
    const description = document.getElementById('cluster-description').value.trim();

    if (!name || !dbType) {
        showToast('请填写资源池名称和数据库类型', 'error');
        return;
    }

    try {
        const response = await fetch('/api/topology/resource-pools', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                name: name,
                db_type: dbType,
                environment: environment,
                description: description
            })
        });

        if (response.ok) {
            showToast('添加成功', 'success');
            closeModal('modal-add-cluster');
            loadClusters();
            document.getElementById('cluster-name').value = '';
            document.getElementById('cluster-description').value = '';
        } else {
            showToast('添加失败', 'error');
        }
    } catch (error) {
        showToast('添加失败', 'error');
    }
}

// 添加节点
async function addServer() {
    const name = document.getElementById('server-name').value.trim();
    const sn = document.getElementById('server-sn').value.trim();
    const host = document.getElementById('server-host').value.trim();
    const datacenter = document.getElementById('server-datacenter').value.trim();
    const cluster = document.getElementById('server-cluster').value.trim();
    const cpu = document.getElementById('server-cpu').value.trim();
    const memory = document.getElementById('server-memory').value.trim();
    const nodeRole = document.getElementById('server-node-role').value;
    const hardwareType = document.getElementById('server-hardware-type').value;
    const description = document.getElementById('server-description').value.trim();

    if (!name || !host) {
        showToast('请填写节点名称和IP地址', 'error');
        return;
    }

    try {
        const response = await fetch(`/api/topology/clusters/${currentClusterId}/servers`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                name: name,
                sn: sn,
                host: host,
                datacenter: datacenter,
                cluster_id: cluster,
                cpu: cpu,
                memory: memory,
                node_role: nodeRole,
                hardware_type: hardwareType,
                description: description
            })
        });

        if (response.ok) {
            showToast('添加成功', 'success');
            closeModal('modal-add-server');
            selectCluster(currentClusterId);
            document.getElementById('server-name').value = '';
            document.getElementById('server-sn').value = '';
            document.getElementById('server-host').value = '';
            document.getElementById('server-datacenter').value = '';
            document.getElementById('server-cluster').value = '';
            document.getElementById('server-cpu').value = '';
            document.getElementById('server-memory').value = '';
            document.getElementById('server-description').value = '';
        } else {
            showToast('添加失败', 'error');
        }
    } catch (error) {
        showToast('添加失败', 'error');
    }
}

// 编辑节点
let currentEditServerId = null;

async function showEditServerDialog(serverId, serverName, serverHost, serverDatacenter, serverClusterId, serverClusterName, serverCpu, serverMemory, serverDescription, nodeRole, hardwareType, serverSn) {
    currentEditServerId = serverId;
    document.getElementById('edit-server-name').value = serverName || '';
    document.getElementById('edit-server-sn').value = serverSn || '';
    document.getElementById('edit-server-host').value = serverHost || '';
    document.getElementById('edit-server-datacenter').value = serverDatacenter || '';

    // 如果提供了集群名称，显示集群名称；否则显示集群ID
    const clusterDisplay = serverClusterName || serverClusterId || '';
    document.getElementById('edit-server-cluster').value = clusterDisplay;

    // 设置节点角色和设备类型
    document.getElementById('edit-server-node-role').value = nodeRole || '计算节点';
    document.getElementById('edit-server-hardware-type').value = hardwareType || '非信创物理机';

    // CPU和内存直接从字段获取，描述直接展示
    document.getElementById('edit-server-cpu').value = serverCpu || '';
    document.getElementById('edit-server-memory').value = serverMemory || '';
    document.getElementById('edit-server-description').value = serverDescription || '';

    document.getElementById('modal-edit-server').style.display = 'flex';
}

async function updateServer() {
    const name = document.getElementById('edit-server-name').value.trim();
    const sn = document.getElementById('edit-server-sn').value.trim();
    const host = document.getElementById('edit-server-host').value.trim();
    const datacenter = document.getElementById('edit-server-datacenter').value.trim();
    const cluster = document.getElementById('edit-server-cluster').value.trim();
    const cpu = document.getElementById('edit-server-cpu').value.trim();
    const memory = document.getElementById('edit-server-memory').value.trim();
    const nodeRole = document.getElementById('edit-server-node-role').value;
    const hardwareType = document.getElementById('edit-server-hardware-type').value;
    const description = document.getElementById('edit-server-description').value.trim();

    if (!name || !host) {
        showToast('请填写节点名称和IP地址', 'error');
        return;
    }

    try {
        const response = await fetch(`/api/topology/servers/${currentEditServerId}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                name: name,
                sn: sn,
                host: host,
                datacenter: datacenter,
                cluster_name: cluster,
                cpu: cpu,
                memory: memory,
                node_role: nodeRole,
                hardware_type: hardwareType,
                description: description
            })
        });

        if (response.ok) {
            showToast('更新成功', 'success');
            closeModal('modal-edit-server');
            selectCluster(currentClusterId);
        } else {
            showToast('更新失败', 'error');
        }
    } catch (error) {
        showToast('更新失败', 'error');
    }
}

// 编辑租户
let currentEditTenantId = null;

function showEditTenantDialog(tenantId, tenantName, topologyType, tenantSpec, tenantDescription) {
    currentEditTenantId = tenantId;
    document.getElementById('edit-tenant-name').value = tenantName || '';
    document.getElementById('edit-tenant-topology').value = topologyType || 'master-slave';
    document.getElementById('edit-tenant-spec').value = tenantSpec || 'small-8c32g';
    document.getElementById('edit-tenant-description').value = tenantDescription || '';
    document.getElementById('modal-edit-tenant').style.display = 'flex';
}

async function updateTenant() {
    const name = document.getElementById('edit-tenant-name').value.trim();
    const topologyType = document.getElementById('edit-tenant-topology').value;
    const spec = document.getElementById('edit-tenant-spec').value;
    const description = document.getElementById('edit-tenant-description').value.trim();

    if (!name) {
        showToast('请填写租户名称', 'error');
        return;
    }

    try {
        const response = await fetch(`/api/topology/tenants/${currentEditTenantId}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                name: name,
                topology_type: topologyType,
                spec: spec,
                description: description
            })
        });

        if (response.ok) {
            showToast('更新成功', 'success');
            closeModal('modal-edit-tenant');
            selectCluster(currentClusterId);
        } else {
            showToast('更新失败', 'error');
        }
    } catch (error) {
        showToast('更新失败', 'error');
    }
}

// 添加租户到集群
function showAddTenantDialog(clusterId) {
    currentClusterId = clusterId;
    document.getElementById('new-tenant-name').value = '';
    document.getElementById('new-tenant-topology').value = 'master-slave';
    document.getElementById('new-tenant-spec').value = 'small-8c32g';
    document.getElementById('new-tenant-description').value = '';
    document.getElementById('modal-add-tenant').style.display = 'flex';
}

async function addTenantToCluster() {
    const name = document.getElementById('new-tenant-name').value.trim();
    const topologyType = document.getElementById('new-tenant-topology').value;
    const spec = document.getElementById('new-tenant-spec').value;
    const description = document.getElementById('new-tenant-description').value.trim();

    if (!name) {
        showToast('请填写租户名称', 'error');
        return;
    }

    try {
        const response = await fetch(`/api/topology/clusters/${currentClusterId}/tenants`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                name: name,
                topology_type: topologyType,
                spec: spec,
                description: description
            })
        });

        if (response.ok) {
            showToast('添加成功', 'success');
            closeModal('modal-add-tenant');
            selectCluster(currentClusterId);
            document.getElementById('new-tenant-name').value = '';
            document.getElementById('new-tenant-description').value = '';
        } else {
            showToast('添加失败', 'error');
        }
    } catch (error) {
        showToast('添加失败', 'error');
    }
}

// 添加实例
async function addInstance() {
    const name = document.getElementById('instance-name').value.trim();
    const port = document.getElementById('instance-port').value.trim();
    const role = document.getElementById('instance-role').value;
    const cpu = document.getElementById('instance-cpu').value.trim();
    const memory = document.getElementById('instance-memory').value.trim();
    const tenantId = document.getElementById('instance-tenant').value;
    const description = document.getElementById('instance-description').value.trim();

    if (!name || !port) {
        showToast('请填写实例名称和端口', 'error');
        return;
    }

    try {
        const response = await fetch(`/api/topology/servers/${TopologyModule.currentServerId}/instances`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                name: name,
                port: port,
                role: role,
                cpu: cpu,
                memory: memory,
                tenant_id: tenantId,
                description: description
            })
        });

        if (response.ok) {
            showToast('添加成功', 'success');
            closeModal('modal-add-instance');
            selectCluster(currentClusterId);
            document.getElementById('instance-name').value = '';
            document.getElementById('instance-port').value = '1521';
            document.getElementById('instance-role').value = 'slave';
            document.getElementById('instance-cpu').value = '';
            document.getElementById('instance-memory').value = '';
            document.getElementById('instance-description').value = '';
        } else {
            showToast('添加失败', 'error');
        }
    } catch (error) {
        showToast('添加失败', 'error');
    }
}

// 实例操作
let currentEditInstanceId = null;

function showAddInstanceDialog(serverId) {
    TopologyModule.currentServerId = serverId;
    document.getElementById('instance-name').value = '';
    document.getElementById('instance-port').value = '1521';
    document.getElementById('instance-cpu').value = '';
    document.getElementById('instance-memory').value = '';
    document.getElementById('instance-description').value = '';
    // 加载租户选择下拉框
    loadTenantSelectForInstanceAdd();
    document.getElementById('modal-add-instance').style.display = 'flex';
}

function showEditInstanceDialog(instanceId, name, port, cpu, memory, description, role) {
    currentEditInstanceId = instanceId;
    document.getElementById('edit-instance-name').value = name || '';
    document.getElementById('edit-instance-port').value = port || '';
    document.getElementById('edit-instance-role').value = role || 'slave';
    document.getElementById('edit-instance-cpu').value = cpu || '';
    document.getElementById('edit-instance-memory').value = memory || '';
    document.getElementById('edit-instance-description').value = description || '';

    // 加载租户选择下拉框
    loadTenantSelectForInstance(instanceId);

    document.getElementById('modal-edit-instance').style.display = 'flex';
}

// 加载租户选择下拉框
async function loadTenantSelectForInstance(instanceId) {
    try {
        const response = await fetch('/api/topology/clusters');
        const data = await response.json();
        const cluster = data.clusters.find(c => c.id === currentClusterId);

        const select = document.getElementById('edit-instance-tenant');
        if (!select) return;

        select.innerHTML = '<option value="">无</option>';

        if (cluster && cluster.tenants) {
            cluster.tenants.forEach(tenant => {
                const option = document.createElement('option');
                option.value = tenant.id;
                option.textContent = tenant.name;
                select.appendChild(option);
            });
        }

        // 如果有实例ID，查询该实例当前所属的租户并选中
        if (instanceId) {
            const detailResponse = await fetch(`/api/topology/instances/${instanceId}`);
            if (detailResponse.ok) {
                const detail = await detailResponse.json();
                if (detail.tenants && detail.tenants.length > 0) {
                    select.value = detail.tenants[0].id;
                }
            }
        }
    } catch (error) {
        console.error('加载租户列表失败:', error);
    }
}

// 加载添加实例时的租户选择下拉框
async function loadTenantSelectForInstanceAdd() {
    try {
        const response = await fetch('/api/topology/clusters');
        const data = await response.json();
        const cluster = data.clusters.find(c => c.id === currentClusterId);

        const select = document.getElementById('instance-tenant');
        if (!select) return;

        select.innerHTML = '<option value="">无</option>';

        if (cluster && cluster.tenants) {
            cluster.tenants.forEach(tenant => {
                const option = document.createElement('option');
                option.value = tenant.id;
                option.textContent = tenant.name;
                select.appendChild(option);
            });
        }
    } catch (error) {
        console.error('加载租户列表失败:', error);
    }
}

async function updateInstance() {
    const name = document.getElementById('edit-instance-name').value.trim();
    const port = document.getElementById('edit-instance-port').value.trim();
    const role = document.getElementById('edit-instance-role').value;
    const cpu = document.getElementById('edit-instance-cpu').value.trim();
    const memory = document.getElementById('edit-instance-memory').value.trim();
    const description = document.getElementById('edit-instance-description').value.trim();
    const tenantId = document.getElementById('edit-instance-tenant').value;

    if (!name || !port) {
        showToast('请填写实例名称和端口', 'error');
        return;
    }

    try {
        const response = await fetch(`/api/topology/instances/${currentEditInstanceId}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                name: name,
                port: port,
                role: role,
                cpu: cpu,
                memory: memory,
                description: description,
                tenant_id: tenantId,
                tenant_role: role  // 实例在租户中的角色与实例角色一致
            })
        });

        if (response.ok) {
            showToast('更新成功', 'success');
            closeModal('modal-edit-instance');
            selectCluster(currentClusterId);
        } else {
            showToast('更新失败', 'error');
        }
    } catch (error) {
        showToast('更新失败', 'error');
    }
}

async function deleteInstance(instanceId) {
    if (!confirm('确定要删除该实例吗？')) return;

    try {
        const response = await fetch(`/api/topology/instances/${instanceId}`, { method: 'DELETE' });
        if (response.ok) {
            showToast('删除成功', 'success');
            selectCluster(currentClusterId);
        } else {
            showToast('删除失败', 'error');
        }
    } catch (error) {
        showToast('删除失败', 'error');
    }
}

// 删除操作
async function deleteCluster(clusterId) {
    if (!confirm('确定要删除该集群吗？')) return;

    try {
        const response = await fetch(`/api/topology/clusters/${clusterId}`, { method: 'DELETE' });
        if (response.ok) {
            showToast('删除成功', 'success');
            if (currentClusterId === clusterId) {
                currentClusterId = null;
                const graphView = document.getElementById('topology-graph-view');
                if (graphView) {
                    graphView.innerHTML = `
                    <div class="welcome-message">
                        <div class="welcome-icon">🗺️</div>
                        <h3>集群拓扑</h3>
                        <p>选择左侧的集群查看拓扑图</p>
                    </div>
                `;
                }
            }
            loadClusters();
        } else {
            showToast('删除失败', 'error');
        }
    } catch (error) {
        showToast('删除失败', 'error');
    }
}

async function deleteServer(serverId) {
    if (!confirm('确定要删除该物理机吗？')) return;

    try {
        const response = await fetch(`/api/topology/servers/${serverId}`, { method: 'DELETE' });
        if (response.ok) {
            showToast('删除成功', 'success');
            selectCluster(currentClusterId);
        } else {
            showToast('删除失败', 'error');
        }
    } catch (error) {
        showToast('删除失败', 'error');
    }
}

async function deleteTenant(tenantId) {
    if (!confirm('确定要删除该租户吗？')) return;

    try {
        const response = await fetch(`/api/topology/tenants/${tenantId}`, { method: 'DELETE' });
        if (response.ok) {
            showToast('删除成功', 'success');
            selectCluster(currentClusterId);
        } else {
            showToast('删除失败', 'error');
        }
    } catch (error) {
        showToast('删除失败', 'error');
    }
}

// 导出拓扑
async function exportTopology() {
    try {
        const response = await fetch('/api/topology/export');
        const data = await response.json();

        const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `topology_${new Date().toISOString().slice(0, 10)}.json`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);

        showToast('拓扑配置已导出', 'success');
    } catch (error) {
        showToast('导出失败', 'error');
    }
}

// ==================== 统计视图 ====================

let currentTopologyStats = null;

function switchTopologyTab(tab) {
    // 更新视图切换按钮状态
    document.querySelectorAll('.view-switch-btn').forEach(btn => {
        btn.classList.remove('active');
    });
    document.querySelector(`.view-switch-btn[data-view="${tab}"]`).classList.add('active');

    // 切换内容显示
    document.querySelectorAll('.topology-tab-content').forEach(content => {
        content.classList.remove('active');
        content.style.display = 'none';
    });
    const activeContent = document.getElementById(`topology-tab-${tab}`);
    activeContent.classList.add('active');

    // 统计视图需要 flex 布局，拓扑视图需要 block
    if (tab === 'stats') {
        activeContent.style.display = 'flex';
    } else {
        activeContent.style.display = 'block';
    }

    // 如果切换到统计视图，加载数据
    if (tab === 'stats') {
        loadTopologyStats();
    }
}

async function loadTopologyStats() {
    try {
        // 获取筛选参数
        const resourcePool = document.getElementById('stats-filter-resource-pool').value;
        const cluster = document.getElementById('stats-filter-cluster').value;
        const datacenter = document.getElementById('stats-filter-datacenter').value;
        const dbType = document.getElementById('stats-filter-dbtype').value;
        const env = document.getElementById('stats-filter-env').value;

        // 构建查询参数
        const params = new URLSearchParams();
        if (resourcePool) params.append('resource_pool', resourcePool);
        if (cluster) params.append('cluster', cluster);
        if (datacenter) params.append('datacenter', datacenter);
        if (dbType) params.append('db_type', dbType);
        if (env) params.append('environment', env);

        const response = await fetch(`/api/topology/stats?${params.toString()}`);
        const data = await response.json();
        currentTopologyStats = data;

        // 更新筛选下拉框选项（只在首次加载时）
        updateStatsFilterOptions(data);

        // 渲染总览卡片
        renderOverviewCards(data.overview);

        // 渲染图表
        renderHardwareChart(data.hardware_stats);
        renderNodeRoleChart(data.node_role_stats);
        renderDatacenterChart(data.datacenter_stats);
        renderClusterChart(data.cluster_stats);
        renderNewClusterChart(data.cluster_distribution);

        // 渲染表格
        renderClusterStatsTable(data.cluster_stats);
        renderServerTable(data.servers);

    } catch (error) {
        console.error('加载统计视图失败:', error);
        showToast('加载统计视图失败', 'error');
    }
}

function updateStatsFilterOptions(data) {
    // 更新资源池下拉框
    const resourcePoolSelect = document.getElementById('stats-filter-resource-pool');
    const currentResourcePool = resourcePoolSelect.value;
    if (resourcePoolSelect.options.length <= 1) {
        resourcePoolSelect.innerHTML = '<option value="">全部资源池</option>';
        if (data.resource_pools) {
            data.resource_pools.forEach(p => {
                const option = document.createElement('option');
                option.value = p.id;
                option.textContent = p.name;
                resourcePoolSelect.appendChild(option);
            });
        }
        resourcePoolSelect.value = currentResourcePool;
    }

    // 更新集群下拉框
    const clusterSelect = document.getElementById('stats-filter-cluster');
    const currentCluster = clusterSelect.value;
    if (clusterSelect.options.length <= 1) {
        clusterSelect.innerHTML = '<option value="">全部资源池</option>';
        if (data.resource_pools) {
            data.resource_pools.forEach(c => {
                const option = document.createElement('option');
                option.value = c.id;
                option.textContent = c.name;
                clusterSelect.appendChild(option);
            });
        }
        clusterSelect.value = currentCluster;
    }

    // 更新数据中心下拉框
    const dcSelect = document.getElementById('stats-filter-datacenter');
    const currentDc = dcSelect.value;
    if (dcSelect.options.length <= 1 && data.datacenter_stats) {
        dcSelect.innerHTML = '<option value="">全部数据中心</option>';
        const dcs = [...new Set(data.datacenter_stats.map(d => d.datacenter))];
        dcs.forEach(dc => {
            if (dc) {
                const option = document.createElement('option');
                option.value = dc;
                option.textContent = dc;
                dcSelect.appendChild(option);
            }
        });
        dcSelect.value = currentDc;
    }

    // 更新数据库类型下拉框
    const dbTypeSelect = document.getElementById('stats-filter-dbtype');
    const currentDbType = dbTypeSelect.value;
    if (dbTypeSelect.options.length <= 1 && data.clusters) {
        dbTypeSelect.innerHTML = '<option value="">全部类型</option>';
        const dbTypes = [...new Set(data.clusters.map(c => c.db_type).filter(Boolean))];
        dbTypes.forEach(dt => {
            const option = document.createElement('option');
            option.value = dt;
            option.textContent = dt;
            dbTypeSelect.appendChild(option);
        });
        dbTypeSelect.value = currentDbType;
    }
}

function renderOverviewCards(overview) {
    document.getElementById('stats-resource-pool-count').textContent = overview.resource_pools || 0;
    document.getElementById('stats-cluster-count').textContent = overview.clusters || 0;
    document.getElementById('stats-server-count').textContent = overview.servers || 0;
    document.getElementById('stats-instance-count').textContent = overview.instances || 0;
    document.getElementById('stats-tenant-count').textContent = overview.tenants || 0;
}

function renderHardwareChart(hardwareStats) {
    const container = document.getElementById('stats-hardware-chart');
    if (!hardwareStats || hardwareStats.length === 0) {
        container.innerHTML = '<div class="empty-message">暂无数据</div>';
        return;
    }

    const total = hardwareStats.reduce((sum, h) => sum + h.count, 0);
    const colors = ['#2196F3', '#4CAF50', '#FF9800', '#9C27B0', '#F44336', '#00BCD4'];

    let html = '<div class="stats-bar-chart">';
    hardwareStats.forEach((item, index) => {
        const percentage = total > 0 ? (item.count / total * 100).toFixed(1) : 0;
        const color = colors[index % colors.length];
        html += `
            <div class="stats-bar-item">
                <div class="stats-bar-label">
                    <span class="stats-bar-color" style="background-color: ${color}"></span>
                    <span class="stats-bar-name">${escapeHtml(item.hardware_type)}</span>
                    <span class="stats-bar-count">${item.count}台</span>
                </div>
                <div class="stats-bar-track">
                    <div class="stats-bar-fill" style="width: ${percentage}%; background-color: ${color}"></div>
                </div>
                <div class="stats-bar-percentage">${percentage}%</div>
            </div>
        `;
    });
    html += '</div>';
    container.innerHTML = html;
}

function renderNodeRoleChart(nodeRoleStats) {
    const container = document.getElementById('stats-noderole-chart');
    if (!nodeRoleStats || nodeRoleStats.length === 0) {
        container.innerHTML = '<div class="empty-message">暂无数据</div>';
        return;
    }

    const total = nodeRoleStats.reduce((sum, n) => sum + n.count, 0);
    const colors = ['#2196F3', '#4CAF50', '#FF9800', '#9C27B0'];

    let html = '<div class="stats-bar-chart">';
    nodeRoleStats.forEach((item, index) => {
        const percentage = total > 0 ? (item.count / total * 100).toFixed(1) : 0;
        const color = colors[index % colors.length];
        html += `
            <div class="stats-bar-item">
                <div class="stats-bar-label">
                    <span class="stats-bar-color" style="background-color: ${color}"></span>
                    <span class="stats-bar-name">${escapeHtml(item.node_role)}</span>
                    <span class="stats-bar-count">${item.count}台</span>
                </div>
                <div class="stats-bar-track">
                    <div class="stats-bar-fill" style="width: ${percentage}%; background-color: ${color}"></div>
                </div>
                <div class="stats-bar-percentage">${percentage}%</div>
            </div>
        `;
    });
    html += '</div>';
    container.innerHTML = html;
}

function renderDatacenterChart(datacenterStats) {
    const container = document.getElementById('stats-datacenter-chart');
    if (!datacenterStats || datacenterStats.length === 0) {
        container.innerHTML = '<div class="empty-message">暂无数据</div>';
        return;
    }

    const total = datacenterStats.reduce((sum, d) => sum + d.count, 0);
    const colors = ['#4CAF50', '#2196F3', '#FF9800', '#9C27B0', '#F44336', '#00BCD4', '#795548'];

    let html = '<div class="stats-bar-chart">';
    datacenterStats.forEach((item, index) => {
        const percentage = total > 0 ? (item.count / total * 100).toFixed(1) : 0;
        const color = colors[index % colors.length];
        html += `
            <div class="stats-bar-item">
                <div class="stats-bar-label">
                    <span class="stats-bar-color" style="background-color: ${color}"></span>
                    <span class="stats-bar-name">${escapeHtml(item.datacenter)}</span>
                    <span class="stats-bar-count">${item.count}台</span>
                </div>
                <div class="stats-bar-track">
                    <div class="stats-bar-fill" style="width: ${percentage}%; background-color: ${color}"></div>
                </div>
                <div class="stats-bar-percentage">${percentage}%</div>
            </div>
        `;
    });
    html += '</div>';
    container.innerHTML = html;
}

function renderClusterChart(clusterStats) {
    const container = document.getElementById('stats-cluster-chart');
    if (!clusterStats || clusterStats.length === 0) {
        container.innerHTML = '<div class="empty-message">暂无数据</div>';
        return;
    }

    const total = clusterStats.reduce((sum, c) => sum + (c.server_count || 0), 0);
    const colors = ['#2196F3', '#4CAF50', '#FF9800', '#9C27B0', '#F44336', '#00BCD4', '#795548'];

    let html = '<div class="stats-bar-chart">';
    clusterStats.forEach((item, index) => {
        const count = item.server_count || 0;
        const percentage = total > 0 ? (count / total * 100).toFixed(1) : 0;
        const color = colors[index % colors.length];
        html += `
            <div class="stats-bar-item">
                <div class="stats-bar-label">
                    <span class="stats-bar-color" style="background-color: ${color}"></span>
                    <span class="stats-bar-name">${escapeHtml(item.name)}</span>
                    <span class="stats-bar-count">${count}台</span>
                </div>
                <div class="stats-bar-track">
                    <div class="stats-bar-fill" style="width: ${percentage}%; background-color: ${color}"></div>
                </div>
                <div class="stats-bar-percentage">${percentage}%</div>
            </div>
        `;
    });
    html += '</div>';
    container.innerHTML = html;
}

function renderNewClusterChart(clusterDistribution) {
    const container = document.getElementById('stats-new-cluster-chart');
    if (!clusterDistribution || clusterDistribution.length === 0) {
        container.innerHTML = '<div class="empty-message">暂无数据</div>';
        return;
    }

    const total = clusterDistribution.reduce((sum, c) => sum + (c.count || 0), 0);
    const colors = ['#FF5722', '#795548', '#607D8B', '#E91E63', '#3F51B5', '#009688', '#FFC107'];

    let html = '<div class="stats-bar-chart">';
    clusterDistribution.forEach((item, index) => {
        const count = item.count || 0;
        const percentage = total > 0 ? (count / total * 100).toFixed(1) : 0;
        const color = colors[index % colors.length];
        html += `
            <div class="stats-bar-item">
                <div class="stats-bar-label">
                    <span class="stats-bar-color" style="background-color: ${color}"></span>
                    <span class="stats-bar-name">${escapeHtml(item.cluster_name || '默认集群')}</span>
                    <span class="stats-bar-count">${count}台</span>
                </div>
                <div class="stats-bar-track">
                    <div class="stats-bar-fill" style="width: ${percentage}%; background-color: ${color}"></div>
                </div>
                <div class="stats-bar-percentage">${percentage}%</div>
            </div>
        `;
    });
    html += '</div>';
    container.innerHTML = html;
}

function renderClusterStatsTable(clusterStats) {
    const tbody = document.querySelector('#stats-cluster-table tbody');
    if (!clusterStats || clusterStats.length === 0) {
        tbody.innerHTML = '<tr><td colspan="6" class="empty-cell">暂无数据</td></tr>';
        return;
    }

    const envMap = {
        'production': '🟢 生产',
        'testing': '🟡 测试',
        'development': '🔵 开发'
    };

    tbody.innerHTML = clusterStats.map(c => `
        <tr>
            <td><strong>${escapeHtml(c.name)}</strong></td>
            <td>${escapeHtml(c.db_type || '-')}</td>
            <td>${envMap[c.environment] || c.environment || '-'}</td>
            <td>${c.server_count || 0}</td>
            <td>${c.instance_count || 0}</td>
            <td>${c.tenant_count || 0}</td>
        </tr>
    `).join('');
}

function renderServerTable(servers) {
    const tbody = document.querySelector('#stats-server-table tbody');
    if (!servers || servers.length === 0) {
        tbody.innerHTML = '<tr><td colspan="6" class="empty-cell">暂无数据</td></tr>';
        return;
    }

    tbody.innerHTML = servers.map(s => `
        <tr>
            <td><strong>${escapeHtml(s.name)}</strong></td>
            <td><code>${escapeHtml(s.host || '-')}</code></td>
            <td>${escapeHtml(s.cluster_name || '-')}</td>
            <td>${escapeHtml(s.datacenter || '-')}</td>
            <td><span class="stats-tag stats-tag-role">${escapeHtml(s.node_role)}</span></td>
            <td><span class="stats-tag stats-tag-hardware">${escapeHtml(s.hardware_type)}</span></td>
        </tr>
    `).join('');
}

function resetStatsFilter() {
    document.getElementById('stats-filter-cluster').value = '';
    document.getElementById('stats-filter-datacenter').value = '';
    document.getElementById('stats-filter-dbtype').value = '';
    document.getElementById('stats-filter-env').value = '';
    loadTopologyStats();
}
