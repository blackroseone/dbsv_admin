# -*- coding: utf-8 -*-
"""集群拓扑 API"""
import uuid
from flask import Blueprint, request, jsonify
from db.database import (
    get_topology_data, add_cluster, update_cluster, delete_cluster,
    get_resource_pools, add_resource_pool, update_resource_pool, delete_resource_pool,
    add_server, delete_server,
    add_instance, delete_instance, get_instance_detail,
    add_tenant, delete_tenant,
    add_instance_relation, remove_instance_relation,
    add_operation_log
)

topology_bp = Blueprint('topology', __name__)


# ==================== 资源池 API ====================

@topology_bp.route('/api/topology/resource-pools', methods=['GET'])
def get_resource_pools_list():
    """获取所有资源池"""
    return jsonify(get_resource_pools())


@topology_bp.route('/api/topology/resource-pools', methods=['POST'])
def create_resource_pool():
    """添加资源池"""
    data = request.get_json()
    pool_id = str(uuid.uuid4())
    add_resource_pool(
        pool_id,
        data.get('name', ''),
        data.get('db_type', ''),
        data.get('environment', 'production'),
        data.get('description', '')
    )
    add_operation_log('集群拓扑', '添加资源池', data.get('name', ''))
    return jsonify({
        'message': '添加成功',
        'resource_pool': {
            'id': pool_id,
            'name': data.get('name', ''),
            'db_type': data.get('db_type', ''),
            'environment': data.get('environment', 'production'),
            'description': data.get('description', '')
        }
    })


@topology_bp.route('/api/topology/resource-pools/<pool_id>', methods=['PUT'])
def update_resource_pool_info(pool_id):
    """更新资源池"""
    data = request.get_json()
    update_resource_pool(
        pool_id,
        name=data.get('name'),
        db_type=data.get('db_type'),
        environment=data.get('environment'),
        description=data.get('description')
    )
    return jsonify({'message': '更新成功'})


@topology_bp.route('/api/topology/resource-pools/<pool_id>', methods=['DELETE'])
def delete_resource_pool_info(pool_id):
    """删除资源池"""
    delete_resource_pool(pool_id)
    add_operation_log('集群拓扑', '删除资源池', pool_id)
    return jsonify({'message': '删除成功'})


# ==================== 物理集群 API ====================

@topology_bp.route('/api/topology/clusters', methods=['GET'])
def get_clusters_list():
    """获取所有集群"""
    return jsonify(get_topology_data())


@topology_bp.route('/api/topology/clusters', methods=['POST'])
def create_cluster():
    """添加物理集群"""
    data = request.get_json()
    cluster_id = str(uuid.uuid4())
    add_cluster(
        cluster_id,
        data.get('name', ''),
        data.get('db_type', ''),
        data.get('environment', 'production'),
        data.get('description', '')
    )
    add_operation_log('集群拓扑', '添加集群', data.get('name', ''))
    return jsonify({
        'message': '添加成功',
        'cluster': {
            'id': cluster_id,
            'name': data.get('name', ''),
            'db_type': data.get('db_type', ''),
            'environment': data.get('environment', 'production'),
            'description': data.get('description', '')
        }
    })


@topology_bp.route('/api/topology/clusters/<cluster_id>', methods=['PUT'])
def update_cluster_info(cluster_id):
    """更新物理集群"""
    data = request.get_json()
    update_cluster(
        cluster_id,
        name=data.get('name'),
        db_type=data.get('db_type'),
        environment=data.get('environment'),
        description=data.get('description')
    )
    return jsonify({'message': '更新成功'})


@topology_bp.route('/api/topology/clusters/<cluster_id>', methods=['DELETE'])
def delete_cluster_info(cluster_id):
    """删除物理集群"""
    delete_cluster(cluster_id)
    add_operation_log('集群拓扑', '删除集群', cluster_id)
    return jsonify({'message': '删除成功'})


# ==================== 物理机 API ====================

@topology_bp.route('/api/topology/resource-pools/<resource_pool_id>/servers', methods=['POST'])
def create_server(resource_pool_id):
    """添加物理机"""
    data = request.get_json()
    server_id = str(uuid.uuid4())
    add_server(
        server_id,
        resource_pool_id,
        data.get('name', ''),
        data.get('host', ''),
        data.get('description', ''),
        data.get('datacenter', ''),
        data.get('node_role', '计算节点'),
        data.get('hardware_type', '非信创物理机'),
        data.get('cpu', ''),
        data.get('memory', ''),
        data.get('cluster_id', '')
    )
    add_operation_log('集群拓扑', '添加物理机', data.get('name', ''))
    return jsonify({
        'message': '添加成功',
        'server': {
            'id': server_id,
            'name': data.get('name', ''),
            'host': data.get('host', ''),
            'datacenter': data.get('datacenter', ''),
            'cluster_id': data.get('cluster_id', ''),
            'node_role': data.get('node_role', '计算节点'),
            'hardware_type': data.get('hardware_type', '非信创物理机'),
            'cpu': data.get('cpu', ''),
            'memory': data.get('memory', ''),
            'description': data.get('description', '')
        }
    })


@topology_bp.route('/api/topology/servers/<server_id>', methods=['PUT'])
def update_server_info(server_id):
    """更新物理机/虚拟机信息"""
    data = request.get_json()
    from db.database import get_db
    import uuid
    conn = get_db()

    # 处理集群名称：如果提供了 cluster_name，则查找或创建集群
    cluster_id = data.get('cluster_id', '')
    cluster_name = data.get('cluster_name', '')

    if cluster_name:
        # 根据名称查找集群
        row = conn.execute(
            "SELECT id FROM clusters WHERE name=?",
            (cluster_name,)
        ).fetchone()

        if row:
            # 集群已存在，使用现有集群ID
            cluster_id = row['id']
        else:
            # 集群不存在，创建新集群
            new_cluster_id = str(uuid.uuid4())
            # 获取当前服务器的 resource_pool_id
            server_row = conn.execute(
                "SELECT resource_pool_id FROM servers WHERE id=?",
                (server_id,)
            ).fetchone()
            resource_pool_id = server_row['resource_pool_id'] if server_row else ''

            conn.execute(
                "INSERT INTO clusters (id, resource_pool_id, name, description) VALUES (?, ?, ?, ?)",
                (new_cluster_id, resource_pool_id, cluster_name, '')
            )
            cluster_id = new_cluster_id

    conn.execute(
        "UPDATE servers SET name=?, host=?, datacenter=?, cluster_id=?, node_role=?, hardware_type=?, cpu=?, memory=?, description=? WHERE id=?",
        (data.get('name', ''), data.get('host', ''), data.get('datacenter', ''), cluster_id, data.get('node_role', '计算节点'), data.get('hardware_type', '非信创物理机'), data.get('cpu', ''), data.get('memory', ''), data.get('description', ''), server_id)
    )
    conn.commit()
    add_operation_log('集群拓扑', '更新节点', data.get('name', server_id))
    return jsonify({'message': '更新成功'})


@topology_bp.route('/api/topology/instances/<instance_id>', methods=['PUT'])
def update_instance_info(instance_id):
    """更新实例信息"""
    data = request.get_json()
    from db.database import get_db
    conn = get_db()

    # 处理租户关联变更
    tenant_id = data.get('tenant_id', '')
    tenant_role = data.get('tenant_role', 'slave')

    if tenant_id:
        # 关联到租户
        conn.execute(
            "UPDATE instances SET name=?, port=?, cpu=?, memory=?, role=?, tenant_id=?, tenant_role=?, description=? WHERE id=?",
            (data.get('name', ''), data.get('port', ''), data.get('cpu', ''), data.get('memory', ''), data.get('role', 'slave'), tenant_id, tenant_role, data.get('description', ''), instance_id)
        )
    else:
        # 移除租户关联
        conn.execute(
            "UPDATE instances SET name=?, port=?, cpu=?, memory=?, role=?, tenant_id=NULL, tenant_role='slave', description=? WHERE id=?",
            (data.get('name', ''), data.get('port', ''), data.get('cpu', ''), data.get('memory', ''), data.get('role', 'slave'), data.get('description', ''), instance_id)
        )
    conn.commit()

    add_operation_log('集群拓扑', '更新实例', data.get('name', instance_id))
    return jsonify({'message': '更新成功'})


@topology_bp.route('/api/topology/tenants/<tenant_id>', methods=['PUT'])
def update_tenant_info(tenant_id):
    """更新租户信息"""
    data = request.get_json()
    from db.database import get_db
    conn = get_db()
    conn.execute(
        "UPDATE tenants SET name=?, topology_type=?, spec=?, description=? WHERE id=?",
        (data.get('name', ''), data.get('topology_type', 'master-slave'), data.get('spec', 'small-8c32g'), data.get('description', ''), tenant_id)
    )
    conn.commit()
    add_operation_log('集群拓扑', '更新租户', data.get('name', tenant_id))
    return jsonify({'message': '更新成功'})


@topology_bp.route('/api/topology/servers/<server_id>', methods=['DELETE'])
def delete_server_info(server_id):
    """删除物理机"""
    delete_server(server_id)
    add_operation_log('集群拓扑', '删除物理机', server_id)
    return jsonify({'message': '删除成功'})


# ==================== 实例 API ====================

@topology_bp.route('/api/topology/servers/<server_id>/instances', methods=['POST'])
def create_instance(server_id):
    """添加实例"""
    data = request.get_json()
    instance_id = str(uuid.uuid4())
    add_instance(
        instance_id,
        server_id,
        data.get('name', ''),
        data.get('port', '3306'),
        data.get('cpu', ''),
        data.get('memory', ''),
        data.get('role', 'slave'),
        data.get('tenant_id', ''),
        data.get('tenant_role', 'slave'),
        data.get('description', '')
    )
    add_operation_log('集群拓扑', '添加实例', data.get('name', ''))
    return jsonify({
        'message': '添加成功',
        'instance': {
            'id': instance_id,
            'name': data.get('name', ''),
            'port': data.get('port', '3306'),
            'role': data.get('role', 'slave'),
            'cpu': data.get('cpu', ''),
            'memory': data.get('memory', ''),
            'description': data.get('description', '')
        }
    })


@topology_bp.route('/api/topology/instances/<instance_id>', methods=['DELETE'])
def delete_instance_info(instance_id):
    """删除实例"""
    delete_instance(instance_id)
    add_operation_log('集群拓扑', '删除实例', instance_id)
    return jsonify({'message': '删除成功'})


@topology_bp.route('/api/topology/instances/<instance_id>', methods=['GET'])
def get_instance_info(instance_id):
    """获取实例详情"""
    detail = get_instance_detail(instance_id)
    if not detail:
        return jsonify({'error': '实例不存在'}), 404
    return jsonify(detail)


# ==================== 租户 API ====================

@topology_bp.route('/api/topology/clusters/<cluster_id>/tenants', methods=['POST'])
def create_tenant(cluster_id):
    """添加租户"""
    data = request.get_json()
    tenant_id = str(uuid.uuid4())
    add_tenant(
        tenant_id,
        cluster_id,
        data.get('name', ''),
        data.get('topology_type', 'master-slave'),
        data.get('spec', 'small-8c32g'),
        data.get('description', '')
    )
    return jsonify({
        'message': '添加成功',
        'tenant': {
            'id': tenant_id,
            'name': data.get('name', ''),
            'topology_type': data.get('topology_type', 'master-slave'),
            'spec': data.get('spec', 'small-8c32g'),
            'description': data.get('description', '')
        }
    })


@topology_bp.route('/api/topology/tenants/<tenant_id>', methods=['DELETE'])
def delete_tenant_info(tenant_id):
    """删除租户"""
    delete_tenant(tenant_id)
    return jsonify({'message': '删除成功'})


# ==================== 实例关系 API ====================

@topology_bp.route('/api/topology/instances/relations', methods=['POST'])
def create_instance_relation():
    """添加实例关系"""
    data = request.get_json()
    add_instance_relation(
        data.get('from_instance_id', ''),
        data.get('to_instance_id', ''),
        data.get('relation_type', 'replication')
    )
    return jsonify({'message': '添加成功'})


@topology_bp.route('/api/topology/instances/relations', methods=['DELETE'])
def delete_instance_relation():
    """删除实例关系"""
    data = request.get_json()
    remove_instance_relation(
        data.get('from_instance_id', ''),
        data.get('to_instance_id', '')
    )
    return jsonify({'message': '删除成功'})


# ==================== 统计视图 API ====================

@topology_bp.route('/api/topology/stats', methods=['GET'])
def get_topology_stats():
    """获取集群拓扑统计聚合数据"""
    from db.database import get_db
    conn = get_db()


    # 获取筛选参数
    resource_pool_filter = request.args.get('resource_pool', '')
    cluster_filter = request.args.get('cluster', '')
    datacenter_filter = request.args.get('datacenter', '')
    db_type_filter = request.args.get('db_type', '')
    env_filter = request.args.get('environment', '')

    # 构建基础查询条件
    conditions = []
    params = []
    if resource_pool_filter:
        conditions.append("rp.id = ?")
        params.append(resource_pool_filter)
    if db_type_filter:
        conditions.append("rp.db_type = ?")
        params.append(db_type_filter)
    if env_filter:
        conditions.append("rp.environment = ?")
        params.append(env_filter)

    where_clause = " AND ".join(conditions) if conditions else "1=1"

    # 1. 资源池列表（用于筛选）
    resource_pools_rows = conn.execute(
        "SELECT id, name, db_type, environment FROM resource_pools ORDER BY name"
    ).fetchall()
    resource_pools = [dict(r) for r in resource_pools_rows]

    # 2. 总览数据
    # 物理机/虚拟机总数
    server_sql = f"""
        SELECT COUNT(*) as count FROM servers s
        JOIN resource_pools rp ON s.resource_pool_id = rp.id
        WHERE {where_clause}
    """
    server_count = conn.execute(server_sql, params).fetchone()['count']

    # 实例总数
    instance_sql = f"""
        SELECT COUNT(*) as count FROM instances i
        JOIN servers s ON i.server_id = s.id
        JOIN resource_pools rp ON s.resource_pool_id = rp.id
        WHERE {where_clause}
    """
    instance_count = conn.execute(instance_sql, params).fetchone()['count']

    # 租户总数
    tenant_sql = f"""
        SELECT COUNT(*) as count FROM tenants t
        JOIN resource_pools rp ON t.resource_pool_id = rp.id
        WHERE {where_clause}
    """
    tenant_count = conn.execute(tenant_sql, params).fetchone()['count']

    # 资源池总数
    resource_pool_sql = f"""
        SELECT COUNT(*) as count FROM resource_pools rp
        WHERE {where_clause}
    """
    resource_pool_count = conn.execute(resource_pool_sql, params).fetchone()['count']

    # 集群总数（基于 clusters 表）
    cluster_sql = f"""
        SELECT COUNT(DISTINCT c.id) as count FROM clusters c
        JOIN resource_pools rp ON c.resource_pool_id = rp.id
        WHERE {where_clause}
    """
    cluster_count = conn.execute(cluster_sql, params).fetchone()['count']

    # 3. 按硬件类型统计（区分物理机/虚拟机）
    hardware_sql = f"""
        SELECT s.hardware_type, COUNT(*) as count FROM servers s
        JOIN resource_pools rp ON s.resource_pool_id = rp.id
        WHERE {where_clause}
        GROUP BY s.hardware_type
        ORDER BY count DESC
    """
    hardware_rows = conn.execute(hardware_sql, params).fetchall()
    hardware_stats = [dict(r) for r in hardware_rows]

    # 4. 按节点角色统计
    node_role_sql = f"""
        SELECT s.node_role, COUNT(*) as count FROM servers s
        JOIN resource_pools rp ON s.resource_pool_id = rp.id
        WHERE {where_clause}
        GROUP BY s.node_role
        ORDER BY count DESC
    """
    node_role_rows = conn.execute(node_role_sql, params).fetchall()
    node_role_stats = [dict(r) for r in node_role_rows]

    # 5. 按资源池统计
    resource_pool_stats_sql = f"""
        SELECT
            rp.id,
            rp.name,
            rp.db_type,
            rp.environment,
            COUNT(DISTINCT s.id) as server_count,
            COUNT(DISTINCT i.id) as instance_count,
            COUNT(DISTINCT t.id) as tenant_count
        FROM resource_pools rp
        LEFT JOIN servers s ON rp.id = s.resource_pool_id
        LEFT JOIN instances i ON s.id = i.server_id
        LEFT JOIN tenants t ON rp.id = t.resource_pool_id
        WHERE {where_clause}
        GROUP BY rp.id, rp.name, rp.db_type, rp.environment
        ORDER BY rp.name
    """
    resource_pool_stats_rows = conn.execute(resource_pool_stats_sql, params).fetchall()
    resource_pool_stats = [dict(r) for r in resource_pool_stats_rows]

    # 6. 按数据中心统计
    datacenter_sql = f"""
        SELECT s.datacenter, COUNT(*) as count FROM servers s
        JOIN resource_pools rp ON s.resource_pool_id = rp.id
        WHERE {where_clause} AND s.datacenter != ''
        GROUP BY s.datacenter
        ORDER BY count DESC
    """
    datacenter_rows = conn.execute(datacenter_sql, params).fetchall()
    datacenter_stats = [dict(r) for r in datacenter_rows]

    # 7. 服务器详细列表
    server_list_sql = f"""
        SELECT
            s.id,
            s.name,
            s.host,
            s.datacenter,
            s.node_role,
            s.hardware_type,
            rp.id as resource_pool_id,
            rp.name as resource_pool_name,
            rp.db_type,
            COALESCE(c.name, s.cluster_id) as cluster_name
        FROM servers s
        JOIN resource_pools rp ON s.resource_pool_id = rp.id
        LEFT JOIN clusters c ON s.cluster_id = c.id
        WHERE {where_clause}
        ORDER BY rp.name, s.name
    """
    server_list_rows = conn.execute(server_list_sql, params).fetchall()
    server_list = [dict(r) for r in server_list_rows]

    # 8. 实例详细列表
    instance_list_sql = f"""
        SELECT
            i.id,
            i.name,
            i.port,
            i.cpu,
            i.memory,
            i.role,
            i.tenant_role,
            s.name as server_name,
            s.host as server_host,
            rp.name as resource_pool_name
        FROM instances i
        JOIN servers s ON i.server_id = s.id
        JOIN resource_pools rp ON s.resource_pool_id = rp.id
        WHERE {where_clause}
        ORDER BY rp.name, s.name, i.name
    """
    instance_list_rows = conn.execute(instance_list_sql, params).fetchall()
    instance_list = [dict(r) for r in instance_list_rows]

    # 9. 按集群统计（基于 servers 表的 cluster_id 字段，关联 clusters 表获取名称）
    cluster_dist_sql = f"""
        SELECT
            COALESCE(c.name, '默认集群') as cluster_name,
            COUNT(*) as count
        FROM servers s
        JOIN resource_pools rp ON s.resource_pool_id = rp.id
        LEFT JOIN clusters c ON s.cluster_id = c.id
        WHERE {where_clause}
        GROUP BY c.name, s.cluster_id
        ORDER BY count DESC
    """
    cluster_dist_rows = conn.execute(cluster_dist_sql, params).fetchall()
    cluster_distribution = [dict(r) for r in cluster_dist_rows]

    # 10. 按租户统计
    tenant_stats_sql = f"""
        SELECT
            t.name as tenant_name,
            COUNT(i.id) as count
        FROM tenants t
        JOIN resource_pools rp ON t.resource_pool_id = rp.id
        LEFT JOIN instances i ON t.id = i.tenant_id
        WHERE {where_clause}
        GROUP BY t.id, t.name
        ORDER BY count DESC
    """
    tenant_stats_rows = conn.execute(tenant_stats_sql, params).fetchall()
    tenant_stats = [dict(r) for r in tenant_stats_rows]

    return jsonify({
        'overview': {
            'resource_pools': resource_pool_count,
            'clusters': cluster_count,
            'servers': server_count,
            'instances': instance_count,
            'tenants': tenant_count
        },
        'resource_pools': resource_pools,
        'clusters': [],  # 暂时没有真正的集群数据
        'hardware_stats': hardware_stats,
        'node_role_stats': node_role_stats,
        'cluster_stats': resource_pool_stats,
        'datacenter_stats': datacenter_stats,
        'cluster_distribution': cluster_distribution,
        'tenant_stats': tenant_stats,
        'servers': server_list,
        'instances': instance_list
    })

@topology_bp.route('/api/topology/export', methods=['GET'])
def export_topology():
    """导出拓扑配置"""
    topology = get_topology_data()
    return jsonify(topology)
