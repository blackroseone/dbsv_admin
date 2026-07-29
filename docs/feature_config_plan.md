# 功能配置开关实现计划

## 功能概述

在系统配置中新增"功能配置"页面,为7个模块(知识库、知识问答、SQL工具、运维手册、命令速查、集群拓扑、仪表盘)添加开关,默认全部开启,关闭后左侧导航栏隐藏该模块入口。

## 数据库设计

### 新增表: feature_config

```sql
CREATE TABLE feature_config (
    module_id TEXT PRIMARY KEY,
    module_name TEXT NOT NULL,
    module_icon TEXT DEFAULT '📦',
    is_enabled BOOLEAN DEFAULT 1,
    sort_order INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### 初始化数据

```sql
INSERT INTO feature_config (module_id, module_name, module_icon, sort_order) VALUES
('knowledge', '知识库', '📚', 1),
('qa', '知识问答', '💬', 2),
('sql_tools', 'SQL工具', '🔧', 3),
('manuals', '运维手册', '📖', 4),
('commands', '命令速查', '⌨️', 5),
('topology', '集群拓扑', '🗺️', 6),
('dashboard', '仪表盘', '📊', 7);
```

## API设计

### 1. 获取功能配置列表

```
GET /api/config/features
```

**响应:**
```json
{
    "features": [
        {
            "module_id": "knowledge",
            "module_name": "知识库",
            "module_icon": "📚",
            "is_enabled": true,
            "sort_order": 1
        }
    ]
}
```

### 2. 更新功能配置

```
PUT /api/config/features/<module_id>
```

**请求:**
```json
{
    "is_enabled": false
}
```

## 前端设计

### 1. 系统配置页面新增"功能配置"Tab

```
┌─────────────────────────────────────┐
│ 系统配置                              │
├──────────┬──────────────────────────┤
│ API配置   │ 功能配置                   │
│ 数据库类型 │                          │
│ 配置导入  │  知识库      [开关] ✅     │
│ 操作日志  │  知识问答    [开关] ✅     │
│ 功能配置  │  SQL工具     [开关] ✅     │
│          │  运维手册    [开关] ✅     │
│          │  命令速查    [开关] ✅     │
│          │  集群拓扑    [开关] ✅     │
│          │  仪表盘      [开关] ✅     │
│          │                          │
│          │  [保存配置]                │
└──────────┴──────────────────────────┘
```

### 2. 导航栏动态渲染

```javascript
// app.js 中初始化导航
async function initNavigation() {
    const features = await apiGet('/api/config/features');
    const navContainer = document.getElementById('nav-items');
    
    features.forEach(feature => {
        if (feature.is_enabled) {
            navContainer.innerHTML += `
                <div class="nav-item" data-module="${feature.module_id}">
                    <span class="nav-icon">${feature.module_icon}</span>
                    <span class="nav-text">${feature.module_name}</span>
                </div>
            `;
        }
    });
}
```

## 文件修改清单

### 后端
1. **db/database.py**
   - 新增 `feature_config` 表创建
   - 新增 CRUD 函数: `get_feature_config()`, `update_feature_config()`

2. **routes/config.py**
   - 新增路由: `/api/config/features` (GET, PUT)

### 前端
1. **static/js/config.js**
   - 新增 `loadFeatureConfig()` 函数
   - 新增 `toggleFeature(moduleId, isEnabled)` 函数
   - 新增 `saveFeatureConfig()` 函数

2. **static/js/app.js**
   - 修改 `initNavigation()` 函数,支持动态渲染

3. **templates/index.html**
   - 系统配置页面新增"功能配置"Tab

4. **static/css/style.css**
   - 新增功能配置页面样式

## 实现步骤

### 步骤1: 数据库层
- [ ] 在 `db/database.py` 中新增 `feature_config` 表定义
- [ ] 在 `init_db()` 中初始化默认数据
- [ ] 新增 `get_feature_config()` 函数
- [ ] 新增 `update_feature_config()` 函数

### 步骤2: API层
- [ ] 在 `routes/config.py` 中新增路由
- [ ] 实现 GET `/api/config/features`
- [ ] 实现 PUT `/api/config/features/<module_id>`

### 步骤3: 前端配置页面
- [ ] 在 `templates/index.html` 中新增"功能配置"Tab
- [ ] 在 `static/js/config.js` 中实现功能配置逻辑
- [ ] 在 `static/css/style.css` 中添加样式

### 步骤4: 导航栏动态渲染
- [ ] 修改 `static/js/app.js` 中的 `initNavigation()`
- [ ] 实现根据配置动态显示/隐藏导航项

### 步骤5: 测试验证
- [ ] 测试开关功能
- [ ] 测试页面刷新后状态保持
- [ ] 测试所有模块正常显示

## 注意事项

1. **默认行为**: 所有模块默认开启,不影响现有功能
2. **至少保留一个模块**: 建议至少保留"仪表盘"模块,避免页面空白
3. **权限控制**: 后续可扩展为仅管理员可修改
4. **缓存处理**: 前端需要处理配置缓存,避免频繁请求

## 预计工作量

- 数据库层: 30分钟
- API层: 30分钟
- 前端配置页面: 1小时
- 导航栏动态渲染: 30分钟
- 测试调试: 30分钟

**总计: 约3小时**
