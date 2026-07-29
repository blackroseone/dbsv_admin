# 日志分析功能设计方案

## 功能概述

渐进式日志分析模块,支持上传多份日志文件,通过多轮LLM调用进行深度分析,结合知识库RAG增强,最终生成结构化分析报告。

## 核心流程

```
用户提交 → 第一轮LLM(问题理解) → 第二轮LLM(日志筛选) → 第三轮LLM(深度分析) → 生成报告
    ↑                                                              ↓
    └──────────────── 知识库RAG增强(贯穿全程) ←─────────────────────┘
```

## 详细流程设计

### 第一轮：意图识别与方向确定
- **输入**: 用户问题 + 日志文件列表(文件名、大小、时间)
- **输出**: 分析方向(错误/性能/安全)、关键时间范围、需要重点关注的日志
- **RAG**: 查询知识库中"日志分析方法论"、"常见问题排查流程"

### 第二轮：日志筛选与预处理
- **输入**: 第一轮结果 + 完整日志内容
- **输出**: 提取的关键日志片段(按优先级排序)
- **RAG**: 查询知识库中"日志关键字含义"、"错误码对照"

### 第三轮：根因分析与建议
- **输入**: 关键日志 + 前两轮分析结果
- **输出**: 问题根因、影响范围、解决方案
- **RAG**: 查询知识库中"故障处理方案"、"最佳实践"

### 最终报告生成
- 整合三轮分析结果
- 生成结构化报告

## 技术实现方案

### 后端SSE流式输出

```python
@app.route('/api/log-analysis/analyze', methods=['POST'])
def analyze_logs():
    def generate():
        # 第一轮
        yield json.dumps({"stage": "intent", "status": "analyzing", "message": "正在理解问题意图..."})
        intent_result = analyze_intent(question, log_files)
        yield json.dumps({"stage": "intent", "status": "complete", "result": intent_result})
        
        # 第二轮
        yield json.dumps({"stage": "filter", "status": "analyzing", "message": "正在筛选关键日志..."})
        filtered_logs = filter_logs(intent_result, log_contents)
        yield json.dumps({"stage": "filter", "status": "complete", "result": filtered_logs})
        
        # 第三轮
        yield json.dumps({"stage": "analysis", "status": "analyzing", "message": "正在进行根因分析..."})
        analysis = root_cause_analysis(filtered_logs, intent_result)
        yield json.dumps({"stage": "analysis", "status": "complete", "result": analysis})
        
        # 报告生成
        yield json.dumps({"stage": "report", "status": "complete", "report": generate_report()})
    
    return Response(generate(), mimetype='text/event-stream')
```

### 前端展示设计

```
┌─────────────────────────────────────┐
│ 日志分析                              │
├─────────────────────────────────────┤
│ 问题描述: [用户输入的问题]              │
│                                      │
│ 分析进度:                              │
│ [✓] 理解问题意图                       │
│ [✓] 筛选关键日志 (发现3处异常)          │
│ [▶] 根因分析中...                     │
│ [ ] 生成报告                           │
│                                      │
│ 当前分析: 正在分析数据库连接超时问题...   │
│                                      │
│ [已发现] 2024-01-15 14:23:05          │
│   ERROR: connection timeout           │
│                                      │
│ [已发现] 2024-01-15 14:25:12          │
│   WARN: slow query detected           │
└─────────────────────────────────────┘
```

## 数据库表设计

```sql
-- 日志分析任务
CREATE TABLE log_analysis_tasks (
    id TEXT PRIMARY KEY,
    name TEXT,                    -- 任务名称
    question TEXT,                -- 用户问题
    status TEXT,                  -- pending/analyzing/completed/failed
    current_stage TEXT,          -- 当前阶段
    stages TEXT,                 -- JSON: 各阶段结果
    report TEXT,                 -- 最终报告
    created_at TIMESTAMP,
    completed_at TIMESTAMP
);

-- 上传的日志文件
CREATE TABLE log_analysis_files (
    id TEXT PRIMARY KEY,
    task_id TEXT,
    filename TEXT,
    file_path TEXT,
    file_size INTEGER,
    content_text TEXT,            -- 提取的文本内容
    is_key_log BOOLEAN,           -- 是否是关键日志
    FOREIGN KEY (task_id) REFERENCES log_analysis_tasks(id)
);
```

## 实现优先级

1. **第一阶段**: 功能配置开关
2. **第二阶段**: 日志分析基础功能(单轮分析)
3. **第三阶段**: 渐进式分析(多轮LLM、SSE流式)
4. **第四阶段**: RAG增强(知识库集成)

## 备注

- 该功能为独立模块,与功能配置开关无依赖关系
- 模块ID: `log_analysis`
- 建议在功能配置开关完成后开发
