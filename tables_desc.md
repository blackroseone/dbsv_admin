# DB Tool 数据库表结构文档

> 用途：记录所有表结构，开发和修改函数前先阅读此文档，确保操作与表结构吻合
> 版本：v3.0.1
> 更新时间：2026-08-05

---

## 表结构总览

| 表名 | 用途 | 关键字段 |
|------|------|----------|
| `config` | 键值对配置 | key, value |
| `db_types` | 数据库类型定义 | id, name, icon |
| `knowledge_files` | 知识库文件元数据 + 内容（**上传/重建时自动提取知识图谱**） | db_type, filename, file_path, file_size, content_text, tags |
| `qa_history` | 问答历史记录 | id, db_type, question, answer, created_at |
| `favorites` | 文件收藏 | db_type, filename |
| `resource_pools` | 资源池信息 | id, name, db_type, environment, description |
| `clusters` | 集群信息（属于某个资源池） | id, resource_pool_id, name, description |
| `servers` | 物理机/节点 | id, resource_pool_id, cluster_id, name, sn, host, datacenter, node_role, hardware_type, cpu, memory, description |
| `instances` | 实例 | id, server_id, tenant_id, name, port, cpu, memory, role, tenant_role, description |
| `tenants` | 租户（实例集群） | id, resource_pool_id, name, topology_type, spec, description |
| `instance_relations` | 实例间关系 | from_instance_id, to_instance_id, relation_type |
| `embeddings` | 文本块向量嵌入（**RAG + 知识图谱关联**） | file_id, chunk_index, chunk_text, embedding |
| `kg_entities` | **知识图谱实体表（44,467条）** | entity_type, name, normalized_name, confidence, source_file_id |
| `kg_relationships` | **知识图谱关系表（12,549条）** | from_entity_id, to_entity_id, relation_type, confidence |
| `kg_chunk_entities` | **chunk-实体关联表（209,053条）** | chunk_id, entity_id, mention_count |
| `operation_logs` | 操作日志 | id, timestamp, module, action, detail, status, ip |
| `feature_config` | 功能配置（模块开关） | module_id, module_name, module_icon, is_enabled, sort_order |
| `log_analysis_tasks` | 日志分析任务 | id, name, question, db_type, status, current_stage, stages, report, created_at, completed_at |
| `log_analysis_files` | 日志分析文件 | id, task_id, filename, file_path, file_size, content_text, is_key_log |
| `agent_ssh_connections` | SSH连接配置 | id, name, host, port, username, auth_type, db_type, os_type, status |
| `agent_db_connections` | 数据库连接配置 | id, name, ssh_connection_id, db_type, host, port, username, database, sid, service_name |
| `agent_sessions` | Agent会话 | id, title, ssh_connection_id, db_connection_id, status, current_step, max_steps |
| `agent_steps` | Agent执行步骤 | id, session_id, step_number, phase, thought, action, observation, knowledge_refs |
| `agent_skills` | Agent技能 | id, name, db_type, category, description, prompt_template, required_tools, knowledge_tags |

---

## 详细表结构

### 1. config — 键值对配置表

```sql
CREATE TABLE IF NOT EXISTS config (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
```

| 字段 | 类型 | 说明 |
|------|------|------|
| key | TEXT | 主键，配置项名称 |
| value | TEXT | 配置项值（JSON序列化存储） |

---

### 2. db_types — 数据库类型定义表

```sql
CREATE TABLE IF NOT EXISTS db_types (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    icon TEXT DEFAULT '📁'
);
```

| 字段 | 类型 | 说明 |
|------|------|------|
| id | TEXT | 主键，数据库类型ID（如 oracle, mysql） |
| name | TEXT | 显示名称（如 Oracle, MySQL） |
| icon | TEXT | 图标（Emoji） |

---

### 3. knowledge_files — 知识库文件表

```sql
CREATE TABLE IF NOT EXISTS knowledge_files (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    db_type TEXT NOT NULL,
    filename TEXT NOT NULL,
    file_path TEXT NOT NULL,
    file_size INTEGER,
    content_text TEXT,
    tags TEXT DEFAULT '[]',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(db_type, filename)
);
```

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER | 自增主键 |
| db_type | TEXT | 所属数据库类型 |
| filename | TEXT | 文件名 |
| file_path | TEXT | 文件路径 |
| file_size | INTEGER | 文件大小（字节） |
| content_text | TEXT | 文件内容文本 |
| tags | TEXT | 标签（JSON数组） |
| created_at | TIMESTAMP | 创建时间 |

---

### 4. qa_history — 问答历史表

```sql
CREATE TABLE IF NOT EXISTS qa_history (
    id TEXT PRIMARY KEY,
    db_type TEXT,
    question TEXT,
    answer TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

| 字段 | 类型 | 说明 |
|------|------|------|
| id | TEXT | 主键，问答记录ID |
| db_type | TEXT | 数据库类型 |
| question | TEXT | 问题 |
| answer | TEXT | 回答 |
| created_at | TIMESTAMP | 创建时间 |

---

### 5. favorites — 收藏夹表

```sql
CREATE TABLE IF NOT EXISTS favorites (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    db_type TEXT NOT NULL,
    filename TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(db_type, filename)
);
```

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER | 自增主键 |
| db_type | TEXT | 数据库类型 |
| filename | TEXT | 文件名 |
| created_at | TIMESTAMP | 创建时间 |

---

### 6. resource_pools — 资源池表

```sql
CREATE TABLE IF NOT EXISTS resource_pools (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    db_type TEXT,
    environment TEXT DEFAULT 'production',
    description TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

| 字段 | 类型 | 说明 |
|------|------|------|
| id | TEXT | 主键，资源池ID |
| name | TEXT | 资源池名称 |
| db_type | TEXT | 数据库类型 |
| environment | TEXT | 环境（production/testing/development） |
| description | TEXT | 描述 |
| created_at | TIMESTAMP | 创建时间 |

---

### 7. clusters — 集群表（属于某个资源池）

```sql
CREATE TABLE IF NOT EXISTS clusters (
    id TEXT PRIMARY KEY,
    resource_pool_id TEXT NOT NULL,
    name TEXT NOT NULL,
    description TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (resource_pool_id) REFERENCES resource_pools(id) ON DELETE CASCADE
);
```

| 字段 | 类型 | 说明 |
|------|------|------|
| id | TEXT | 主键，集群ID |
| resource_pool_id | TEXT | 所属资源池ID（外键） |
| name | TEXT | 集群名称 |
| description | TEXT | 描述 |
| created_at | TIMESTAMP | 创建时间 |

**注意：** clusters 表只保留核心字段，数据库类型、环境等信息通过 resource_pool_id 关联到 resource_pools 表获取。

---

### 8. servers — 物理机/节点表

```sql
CREATE TABLE IF NOT EXISTS servers (
    id TEXT PRIMARY KEY,
    resource_pool_id TEXT NOT NULL,
    cluster_id TEXT DEFAULT '',
    name TEXT NOT NULL,
    sn TEXT DEFAULT '',
    host TEXT,
    datacenter TEXT DEFAULT '',
    node_role TEXT DEFAULT '计算节点',
    hardware_type TEXT DEFAULT '非信创物理机',
    cpu TEXT,
    memory TEXT,
    description TEXT,
    FOREIGN KEY (resource_pool_id) REFERENCES resource_pools(id) ON DELETE CASCADE
);
```

| 字段 | 类型 | 说明 |
|------|------|------|
| id | TEXT | 主键，节点ID |
| resource_pool_id | TEXT | 所属资源池ID（外键） |
| cluster_id | TEXT | 所属集群ID（逻辑关联，非外键） |
| name | TEXT | 节点名称 |
| sn | TEXT | SN序列号（2026-08-03添加） |
| host | TEXT | IP地址 |
| datacenter | TEXT | 所属机房 |
| node_role | TEXT | 节点角色（计算节点/存储节点/管理节点） |
| hardware_type | TEXT | 硬件类型 |
| cpu | TEXT | CPU核数 |
| memory | TEXT | 内存大小 |
| description | TEXT | 描述 |

**重要说明：**
- `cluster_id` 是逻辑关联，不是外键，存储的是集群名称或ID
- `cpu` 和 `memory` 字段在2026-07-07添加
- `node_role` 和 `hardware_type` 字段在2026-07-07添加
- `sn` 字段在2026-08-03添加

---

### 9. instances — 实例表

```sql
CREATE TABLE IF NOT EXISTS instances (
    id TEXT PRIMARY KEY,
    server_id TEXT NOT NULL,
    tenant_id TEXT,
    name TEXT NOT NULL,
    port TEXT DEFAULT '3306',
    cpu TEXT,
    memory TEXT,
    role TEXT DEFAULT 'slave',
    tenant_role TEXT DEFAULT 'slave',
    description TEXT,
    FOREIGN KEY (server_id) REFERENCES servers(id) ON DELETE CASCADE,
    FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE SET NULL
);
```

| 字段 | 类型 | 说明 |
|------|------|------|
| id | TEXT | 主键，实例ID |
| server_id | TEXT | 所属节点ID（外键） |
| tenant_id | TEXT | 所属租户ID（外键，可为空） |
| name | TEXT | 实例名称 |
| port | TEXT | 端口 |
| cpu | TEXT | CPU核数 |
| memory | TEXT | 内存大小 |
| role | TEXT | 角色（master/slave/standalone） |
| tenant_role | TEXT | 在租户中的角色 |
| description | TEXT | 描述 |

---

### 10. tenants — 租户表

```sql
CREATE TABLE IF NOT EXISTS tenants (
    id TEXT PRIMARY KEY,
    resource_pool_id TEXT NOT NULL,
    name TEXT NOT NULL,
    topology_type TEXT DEFAULT 'master-slave',
    spec TEXT DEFAULT 'small-8c32g',
    description TEXT,
    FOREIGN KEY (resource_pool_id) REFERENCES resource_pools(id) ON DELETE CASCADE
);
```

| 字段 | 类型 | 说明 |
|------|------|------|
| id | TEXT | 主键，租户ID |
| resource_pool_id | TEXT | 所属资源池ID（外键） |
| name | TEXT | 租户名称 |
| topology_type | TEXT | 拓扑类型（master-slave, single, mha, paxos/raft, rac） |
| spec | TEXT | 规格 |
| description | TEXT | 描述 |

---

### 11. instance_relations — 实例关系表

```sql
CREATE TABLE IF NOT EXISTS instance_relations (
    from_instance_id TEXT NOT NULL,
    to_instance_id TEXT NOT NULL,
    relation_type TEXT DEFAULT 'replication',
    PRIMARY KEY (from_instance_id, to_instance_id),
    FOREIGN KEY (from_instance_id) REFERENCES instances(id) ON DELETE CASCADE,
    FOREIGN KEY (to_instance_id) REFERENCES instances(id) ON DELETE CASCADE
);
```

| 字段 | 类型 | 说明 |
|------|------|------|
| from_instance_id | TEXT | 源实例ID |
| to_instance_id | TEXT | 目标实例ID |
| relation_type | TEXT | 关系类型 |

---

### 12. embeddings — 向量嵌入表

```sql
CREATE TABLE IF NOT EXISTS embeddings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_id INTEGER,
    chunk_index INTEGER,
    chunk_text TEXT,
    embedding BLOB,
    FOREIGN KEY (file_id) REFERENCES knowledge_files(id) ON DELETE CASCADE
);
```

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER | 自增主键 |
| file_id | INTEGER | 所属文件ID（外键） |
| chunk_index | INTEGER | 文本块索引 |
| chunk_text | TEXT | 文本块内容 |
| embedding | BLOB | 向量嵌入数据 |

---

### 13. operation_logs — 操作日志表

```sql
CREATE TABLE IF NOT EXISTS operation_logs (
    id TEXT PRIMARY KEY,
    timestamp TEXT NOT NULL,
    module TEXT NOT NULL,
    action TEXT NOT NULL,
    detail TEXT DEFAULT '',
    status TEXT DEFAULT 'success',
    ip TEXT DEFAULT ''
);
```

| 字段 | 类型 | 说明 |
|------|------|------|
| id | TEXT | 主键，日志ID |
| timestamp | TEXT | 时间戳 |
| module | TEXT | 模块名称 |
| action | TEXT | 操作名称 |
| detail | TEXT | 详情 |
| status | TEXT | 状态（success/error） |
| ip | TEXT | IP地址 |

---

### 14. feature_config — 功能配置表

```sql
CREATE TABLE IF NOT EXISTS feature_config (
    module_id TEXT PRIMARY KEY,
    module_name TEXT NOT NULL,
    module_icon TEXT DEFAULT '📦',
    is_enabled BOOLEAN DEFAULT 1,
    sort_order INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

| 字段 | 类型 | 说明 |
|------|------|------|
| module_id | TEXT | 主键，模块唯一标识 |
| module_name | TEXT | 模块显示名称 |
| module_icon | TEXT | 模块图标 |
| is_enabled | BOOLEAN | 是否启用（1=启用，0=禁用） |
| sort_order | INTEGER | 排序顺序 |
| created_at | TIMESTAMP | 创建时间 |

**默认数据：**

| module_id | module_name | module_icon | sort_order |
|-----------|-------------|-------------|------------|
| knowledge | 知识库 | 📚 | 1 |
| qa | 知识问答 | 💬 | 2 |
| sql_tools | SQL工具 | 🔧 | 3 |
| manuals | 运维手册 | 📖 | 4 |
| commands | 命令速查 | ⌨️ | 5 |
| topology | 集群拓扑 | 🗺️ | 6 |
| dashboard | 仪表盘 | 📊 | 7 |

---

### 15. log_analysis_tasks — 日志分析任务表

```sql
CREATE TABLE IF NOT EXISTS log_analysis_tasks (
    id TEXT PRIMARY KEY,
    name TEXT,
    question TEXT,
    db_type TEXT DEFAULT '',
    status TEXT DEFAULT 'pending',
    current_stage TEXT DEFAULT '',
    stages TEXT DEFAULT '{}',
    report TEXT DEFAULT '',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP
);
```

| 字段 | 类型 | 说明 |
|------|------|------|
| id | TEXT | 主键，任务ID（UUID） |
| name | TEXT | 任务名称 |
| question | TEXT | 分析问题描述 |
| db_type | TEXT | 数据库类型（关联 db_types 表） |
| status | TEXT | 状态：pending/analyzing/completed/failed |
| current_stage | TEXT | 当前分析阶段 |
| stages | TEXT | 各阶段结果（JSON格式，含耗时） |
| report | TEXT | 最终分析报告（Markdown格式） |
| created_at | TIMESTAMP | 创建时间 |
| completed_at | TIMESTAMP | 完成时间 |

**stages JSON 格式：**
```json
{
    "intent": {"direction": "...", "focus_files": [...], "duration": 8700},
    "filter": {"key_logs": [...], "summary": "...", "duration": 12300},
    "analysis": {"root_cause": "...", "impact": "...", "duration": 15600},
    "report": {"duration": 500}
}
```

---

### 16. log_analysis_files — 日志分析文件表

```sql
CREATE TABLE IF NOT EXISTS log_analysis_files (
    id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL,
    filename TEXT NOT NULL,
    file_path TEXT NOT NULL,
    file_size INTEGER,
    content_text TEXT,
    is_key_log BOOLEAN DEFAULT 0,
    FOREIGN KEY (task_id) REFERENCES log_analysis_tasks(id) ON DELETE CASCADE
);
```

| 字段 | 类型 | 说明 |
|------|------|------|
| id | TEXT | 主键，文件ID（UUID） |
| task_id | TEXT | 所属任务ID（外键） |
| filename | TEXT | 文件名 |
| file_path | TEXT | 文件存储路径 |
| file_size | INTEGER | 文件大小（字节） |
| content_text | TEXT | 文件内容文本 |
| is_key_log | BOOLEAN | 是否标记为关键日志 |

---

## 索引列表

| 索引名 | 表名 | 字段 | 用途 |
|--------|------|------|------|
| idx_knowledge_files_db_type | knowledge_files | db_type | 按数据库类型查询 |
| idx_qa_history_db_type | qa_history | db_type | 按数据库类型查询 |
| idx_qa_history_created | qa_history | created_at DESC | 按时间排序 |
| idx_servers_cluster | servers | cluster_id | 按集群查询 |
| idx_instances_server | instances | server_id | 按节点查询 |
| idx_tenants_cluster | tenants | cluster_id | 按集群查询 |
| idx_embeddings_file | embeddings | file_id | 按文件查询 |
| idx_operation_logs_timestamp | operation_logs | timestamp DESC | 按时间排序 |
| idx_operation_logs_module | operation_logs | module | 按模块查询 |
| idx_log_analysis_tasks_status | log_analysis_tasks | status | 按状态查询 |
| idx_log_analysis_tasks_db_type | log_analysis_tasks | db_type | 按数据库类型查询 |
| idx_log_analysis_files_task | log_analysis_files | task_id | 按任务查询 |
| idx_kg_entities_type | kg_entities | entity_type | 按实体类型查询 |
| idx_kg_entities_name | kg_entities | normalized_name | 按规范化名称查询 |
| idx_kg_rel_from | kg_relationships | from_entity_id | 按源实体查询 |
| idx_kg_rel_to | kg_relationships | to_entity_id | 按目标实体查询 |
| idx_kg_rel_type | kg_relationships | relation_type | 按关系类型查询 |
| idx_kg_chunk_e | kg_chunk_entities | chunk_id | 按 chunk 查询 |
| idx_kg_chunk_eid | kg_chunk_entities | entity_id | 按实体查询 |
| idx_agent_steps_session | agent_steps | session_id | 按会话查询 |
| idx_agent_skills_db_type | agent_skills | db_type | 按数据库类型查询 |
| idx_agent_skills_category | agent_skills | category | 按分类查询 |

---

## 开发注意事项

### 1. 新增字段流程

当需要给表新增字段时：

1. 修改 `init_db()` 函数中的 CREATE TABLE 语句
2. 添加 ALTER TABLE 迁移代码（兼容旧数据库）
3. 更新 `tables_desc.md` 文档
4. 更新 `code_desc.md` 文档
5. 检查所有相关 CRUD 函数是否需要更新

### 2. 当前已知字段变更

| 表名 | 字段 | 变更时间 | 说明 |
|------|------|----------|------|
| knowledge_files | content_text | 2026-07-30 | 更新逻辑（`add_knowledge_file` 返回 file_id，支持知识图谱关联） |
| knowledge_files | file_path | 2026-07-30 | 新增 GaussDB 巡检文件（2个PDF，已提取496个实体） |
| clusters | environment | 2026-07-07 | 移除（冗余字段，通过 resource_pool_id 关联获取） |
| clusters | topology_type | 2026-07-07 | 移除（冗余字段） |
| servers | cpu | 2026-07-07 | 新增 |
| servers | memory | 2026-07-07 | 新增 |
| servers | node_role | 2026-07-07 | 新增 |
| servers | hardware_type | 2026-07-07 | 新增 |
| servers | datacenter | 2026-07-07 | 新增 |
| instances | role | 2026-07-07 | 新增 |
| instances | tenant_id | 2026-07-07 | 新增 |
| instances | tenant_role | 2026-07-07 | 新增 |
| tenants | spec | 2026-07-07 | 新增 |
| log_analysis_tasks | db_type | 2026-07-14 | 新增（支持按数据库类型进行RAG查询） |
| log_analysis_files | task_id | 2026-07-14 | 外键关联 log_analysis_tasks |
| agent_ssh_connections | 全部 | 2026-07-24 | 新增（Agent SSH连接配置） |
| agent_db_connections | 全部 | 2026-07-24 | 新增（Agent数据库连接配置） |
| agent_sessions | 全部 | 2026-07-24 | 新增（Agent会话管理） |
| agent_steps | 全部 | 2026-07-24 | 新增（Agent执行步骤记录） |
| agent_skills | 全部 | 2026-07-24 | 新增（Agent领域技能） |
| kg_entities | 全部 | 2026-07-29 | 新增（知识图谱实体表，**44,467条实体**） |
| kg_relationships | 全部 | 2026-07-29 | 新增（知识图谱关系表，**12,549条关系**） |
| kg_chunk_entities | 全部 | 2026-07-29 | 新增（chunk-实体关联表，**209,053条关联**） |

### 3. 外键约束

| 子表 | 字段 | 父表 | 约束 |
|------|------|------|------|
| clusters | resource_pool_id | resource_pools | ON DELETE CASCADE |
| servers | resource_pool_id | resource_pools | ON DELETE CASCADE |
| instances | server_id | servers | ON DELETE CASCADE |
| instances | tenant_id | tenants | ON DELETE SET NULL |
| instance_relations | from_instance_id | instances | ON DELETE CASCADE |
| instance_relations | to_instance_id | instances | ON DELETE CASCADE |
| embeddings | file_id | knowledge_files | ON DELETE CASCADE |
| kg_relationships | from_entity_id | kg_entities | ON DELETE CASCADE |
| kg_relationships | to_entity_id | kg_entities | ON DELETE CASCADE |
| kg_chunk_entities | chunk_id | embeddings | ON DELETE CASCADE |
| kg_chunk_entities | entity_id | kg_entities | ON DELETE CASCADE |
| tenants | resource_pool_id | resource_pools | ON DELETE CASCADE |
| log_analysis_files | task_id | log_analysis_tasks | ON DELETE CASCADE |
| agent_db_connections | ssh_connection_id | agent_ssh_connections | ON DELETE SET NULL |
| agent_steps | session_id | agent_sessions | ON DELETE CASCADE |

### 17. kg_entities — 知识图谱实体表

```sql
CREATE TABLE IF NOT EXISTS kg_entities (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_type TEXT NOT NULL,
    name TEXT NOT NULL,
    normalized_name TEXT NOT NULL,
    aliases TEXT DEFAULT '[]',
    description TEXT,
    properties TEXT DEFAULT '{}',
    source_file_id INTEGER,
    source_chunk_id INTEGER,
    confidence REAL DEFAULT 1.0,
    extract_method TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(normalized_name, entity_type)
);
```

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER | 自增主键 |
| entity_type | TEXT | 实体类型（database_product, version, parameter 等） |
| name | TEXT | 实体名称 |
| normalized_name | TEXT | 规范化名称（小写、去空格） |
| aliases | TEXT | 别名数组（JSON格式） |
| description | TEXT | 描述 |
| properties | TEXT | 扩展属性（JSON格式） |
| source_file_id | INTEGER | 来源文件ID |
| source_chunk_id | INTEGER | 来源chunk ID |
| confidence | REAL | 提取置信度（0-1） |
| extract_method | TEXT | 提取方式（rule/llm） |
| created_at | TIMESTAMP | 创建时间 |
| updated_at | TIMESTAMP | 更新时间 |

---

### 18. kg_relationships — 知识图谱关系表

```sql
CREATE TABLE IF NOT EXISTS kg_relationships (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    from_entity_id INTEGER NOT NULL,
    to_entity_id INTEGER NOT NULL,
    relation_type TEXT NOT NULL,
    confidence REAL DEFAULT 1.0,
    properties TEXT DEFAULT '{}',
    source_chunk_id INTEGER,
    source_file_id INTEGER,
    extract_method TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (from_entity_id) REFERENCES kg_entities(id) ON DELETE CASCADE,
    FOREIGN KEY (to_entity_id) REFERENCES kg_entities(id) ON DELETE CASCADE
);
```

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER | 自增主键 |
| from_entity_id | INTEGER | 源实体ID（外键） |
| to_entity_id | INTEGER | 目标实体ID（外键） |
| relation_type | TEXT | 关系类型（has_version, has_parameter 等） |
| confidence | REAL | 关系置信度（0-1） |
| properties | TEXT | 扩展属性（JSON格式） |
| source_chunk_id | INTEGER | 来源chunk ID |
| source_file_id | INTEGER | 来源文件ID |
| extract_method | TEXT | 提取方式（rule/llm） |
| created_at | TIMESTAMP | 创建时间 |

---

### 19. kg_chunk_entities — chunk-实体关联表

```sql
CREATE TABLE IF NOT EXISTS kg_chunk_entities (
    chunk_id INTEGER NOT NULL,
    entity_id INTEGER NOT NULL,
    mention_count INTEGER DEFAULT 1,
    PRIMARY KEY (chunk_id, entity_id),
    FOREIGN KEY (chunk_id) REFERENCES embeddings(id) ON DELETE CASCADE,
    FOREIGN KEY (entity_id) REFERENCES kg_entities(id) ON DELETE CASCADE
);
```

| 字段 | 类型 | 说明 |
|------|------|------|
| chunk_id | INTEGER | chunk ID（外键，关联 embeddings 表） |
| entity_id | INTEGER | 实体ID（外键，关联 kg_entities 表） |
| mention_count | INTEGER | 该chunk中提及次数 |

---

在修改涉及数据库的代码前，请确认：

- [ ] 已阅读 `tables_desc.md` 了解表结构
- [ ] 已确认操作的表和字段存在
- [ ] 已检查外键约束
- [ ] 已考虑数据库迁移（新增字段时）
- [ ] 已更新相关文档
