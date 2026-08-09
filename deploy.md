# 数据库运维工具 - 部署指南

> 📌 配套文档：
> - `project.md` — 项目概述、技术栈、功能模块
> - `version_update.md` — 版本更新记录
> - `code_desc.md` — 代码结构文档
> - `tables_desc.md` — 数据库表结构
> - `deploy.md` — 部署指南

---

## 一、环境要求

- **Python**: 3.8+（推荐 3.10+）
- **操作系统**: Linux / Windows Server 均可
- **内存**: 建议 2GB+（sentence-transformers 模型首次加载约需 500MB）
- **磁盘**: 至少 1GB 可用空间（含模型缓存）

---

## 二、安装依赖

```bash
cd /path/to/db-tool

# 创建虚拟环境（推荐）
python -m venv venv
source venv/bin/activate        # Linux
# venv\Scripts\activate         # Windows

# 安装依赖（见下方依赖清单）
pip install flask requests python-docx openpyxl PyPDF2 python-multipart sentence-transformers numpy sqlglot cryptography pymysql oracledb psycopg2-binary paramiko
```

### 依赖清单

| 包名 | 版本 | 用途 |
|------|------|------|
| `flask` | >=2.3.0 | Web 框架 |
| `requests` | >=2.31.0 | HTTP 客户端（调用 LLM API） |
| `python-docx` | >=0.8.11 | DOCX 文件解析 |
| `openpyxl` | >=3.1.0 | XLSX 文件解析 |
| `PyPDF2` | >=3.0.0 | PDF 文件解析 |
| `python-multipart` | >=0.0.6 | 文件上传支持 |
| `sentence-transformers` | >=2.2.0 | 向量嵌入模型（RAG 语义检索） |
| `numpy` | >=1.24.0 | 数值计算（向量相似度） |
| `sqlglot` | >=20.0.0 | SQL 语法解析（本地 SQL 审核） |
| `cryptography` | >=3.0.0 | 凭据加密（Agent SSH/DB 连接配置落库加密） |
| `pymysql` | >=1.0.0 | Agent 查询 MySQL 系数据库（mysql/tdsql/oceanbase/goldendb） |
| `oracledb` | >=1.0.0 | Agent 查询 Oracle 数据库（thin 模式，无需客户端） |
| `psycopg2-binary` | >=2.9.0 | Agent 查询 GaussDB/PostgreSQL |
| `paramiko` | >=2.0.0 | Agent 通过 SSH 执行数据库命令 |
| `dmPython` | 可选 | Agent 查询达梦数据库（社区驱动，按需安装） |

> **注意**：sentence-transformers 首次运行会自动下载多语言模型（约 500MB），需要网络访问 HuggingFace。如服务器无法访问外网，可提前在有网络的机器下载后拷贝到 `data/models/` 目录。

---

## 三、启动方式

### 1) 开发模式（调试用）

```bash
python app.py
```

默认监听 `0.0.0.0:5000`

### 2) 生产模式 - Linux + Gunicorn

```bash
pip install gunicorn
gunicorn -w 4 -b 0.0.0.0:5000 "app:create_app()"
```

### 3) 生产模式 - Windows + Waitress

```bash
pip install waitress
python wsgi.py  # 需创建 wsgi.py，见下方示例
```

**wsgi.py 示例：**

```python
from app import create_app
from waitress import serve

app = create_app()
serve(app, host='0.0.0.0', port=5000)
```

---

## 四、Linux systemd 服务（开机自启）

创建 `/etc/systemd/system/db-tool.service`：

```ini
[Unit]
Description=DB Tool Service
After=network.target

[Service]
User=www-data
WorkingDirectory=/path/to/db-tool
ExecStart=/path/to/db-tool/venv/bin/gunicorn -w 4 -b 0.0.0.0:5000 "app:create_app()"
Restart=always

[Install]
WantedBy=multi-user.target
```

执行：

```bash
sudo systemctl daemon-reload
sudo systemctl enable db-tool
sudo systemctl start db-tool
sudo systemctl status db-tool
```

---

## 五、Nginx 反向代理（推荐）

```nginx
server {
    listen 80;
    server_name db-tool.yourcompany.com;

    client_max_body_size 100m;

    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_read_timeout 300s;
    }

    location /static/ {
        alias /path/to/db-tool/static/;
        expires 7d;
    }
}
```

---

## 六、防火墙

```bash
sudo firewall-cmd --add-port=5000/tcp --permanent   # 直接访问
# 或
sudo firewall-cmd --add-port=80/tcp --permanent      # Nginx 代理
sudo firewall-cmd --reload
```

---

## 七、目录权限

确保运行用户对以下目录有读写权限：

| 目录 | 用途 |
|------|------|
| `data/` | SQLite 数据库、上传文件、模型缓存 |
| `static/` | 前端静态资源 |
| `templates/` | HTML 模板 |

---

## 八、首次启动说明

首次启动时系统会自动：

1. 创建 SQLite 数据库 `data/db_tool.db`
2. 创建所有必要的目录
3. 如果存在旧 JSON 文件（config.json 等），自动迁移到 SQLite，并备份到 `data/json_backup/`
4. 初始化默认数据库类型（MySQL、Oracle、达梦等 7 种）

---

## 九、数据库迁移说明

### v2.3.1 版本迁移

从 v2.3.0 升级到 v2.3.1 需要进行数据库迁移:

**clusters 表新增字段:**
- `resource_pool_id`: 关联 resource_pools 表的外键

**迁移步骤:**
1. 备份数据库: `cp data/db_tool.db data/db_tool.db.backup`
2. 运行迁移脚本(如需要)
3. 验证数据完整性

**迁移脚本示例:**
```python
import sqlite3

conn = sqlite3.connect('data/db_tool.db')

# 检查 clusters 表是否有 resource_pool_id 字段
cursor = conn.execute("PRAGMA table_info(clusters)")
columns = [col[1] for col in cursor.fetchall()]

if 'resource_pool_id' not in columns:
    # 添加字段
    conn.execute("ALTER TABLE clusters ADD COLUMN resource_pool_id TEXT")
    # 更新现有数据
    conn.execute("UPDATE clusters SET resource_pool_id = id WHERE resource_pool_id IS NULL")
    conn.commit()
    print("迁移完成")

conn.close()
```

---

## 十、集群拓扑统计视图

集群拓扑模块提供两种视图：

### 1. 统计视图

宏观聚合数据展示：

- **总览卡片**：集群/服务器/实例/租户总数
- **分布图表**：硬件类型、节点角色、数据中心
- **筛选功能**：按集群/数据中心/数据库类型/环境筛选
- **详细表格**：集群统计表、服务器列表

### 2. 拓扑视图

微观拓扑图展示：

- 左侧集群列表
- 中间拓扑图（按机房层级分组）
- 右侧实例详情面板

---

## 十一、备份与恢复

### 备份

```bash
tar -czf db-tool-backup-$(date +%Y%m%d).tar.gz data/
```

### 恢复

```bash
tar -xzf db-tool-backup-YYYYMMDD.tar.gz -C /path/to/db-tool/
```

---

## 十二、配置 LLM API

首次使用需要配置大模型 API：

1. 访问 http://服务器IP:5000
2. 点击左侧 **"API配置"**
3. 填写 API 地址、API Key、模型名称（支持 OpenAI 兼容格式）
4. 点击 **"测试连接"** 确认可用
