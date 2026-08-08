# -*- coding: utf-8 -*-
"""日志分析 API"""
import json
import os
import time
import uuid
from flask import Blueprint, request, jsonify, Response
from db.database import (
    add_log_analysis_task, update_log_analysis_task,
    get_log_analysis_task, get_log_analysis_tasks,
    delete_log_analysis_task, add_log_analysis_file,
    get_log_analysis_files, delete_log_analysis_files,
    add_operation_log
)
from utils import allowed_file, extract_content, call_llm, call_llm_stream, safe_filename

log_analysis_bp = Blueprint('log_analysis', __name__)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG_ANALYSIS_DIR = os.path.join(BASE_DIR, 'data', 'log_analysis')


def _get_task_dir(task_id):
    """获取任务文件目录"""
    task_dir = os.path.join(LOG_ANALYSIS_DIR, task_id)
    os.makedirs(task_dir, exist_ok=True)
    return task_dir


@log_analysis_bp.route('/api/log-analysis/tasks', methods=['GET'])
def get_tasks():
    """获取日志分析任务列表"""
    tasks = get_log_analysis_tasks(limit=50)
    # 为每个任务获取文件信息
    for task in tasks:
        files = get_log_analysis_files(task['id'])
        task['files_info'] = [{'filename': f['filename'], 'file_size': f['file_size']} for f in files]
    return jsonify({'tasks': tasks})


@log_analysis_bp.route('/api/log-analysis/tasks', methods=['POST'])
def create_task():
    """创建日志分析任务"""
    data = request.get_json()
    if not data:
        return jsonify({'error': '请求数据为空'}), 400

    name = data.get('name', '').strip()
    question = data.get('question', '').strip()
    db_type = data.get('db_type', '').strip()

    if not name:
        return jsonify({'error': '请输入任务名称'}), 400
    if not question:
        return jsonify({'error': '请输入分析问题'}), 400

    task_id = str(uuid.uuid4())
    add_log_analysis_task(task_id, name, question, db_type)
    add_operation_log('日志分析', '创建任务', name)

    return jsonify({
        'message': '创建成功',
        'task': {
            'id': task_id,
            'name': name,
            'question': question,
            'db_type': db_type,
            'status': 'pending'
        }
    })


@log_analysis_bp.route('/api/log-analysis/tasks/<task_id>', methods=['GET'])
def get_task(task_id):
    """获取单个任务详情"""
    task = get_log_analysis_task(task_id)
    if not task:
        return jsonify({'error': '任务不存在'}), 404

    files = get_log_analysis_files(task_id)
    return jsonify({
        'task': task,
        'files': files
    })


@log_analysis_bp.route('/api/log-analysis/tasks/<task_id>', methods=['PUT'])
def update_task(task_id):
    """更新任务状态"""
    task = get_log_analysis_task(task_id)
    if not task:
        return jsonify({'error': '任务不存在'}), 404

    data = request.get_json() or {}
    status = data.get('status')
    current_stage = data.get('current_stage')

    update_log_analysis_task(task_id, status=status, current_stage=current_stage)
    return jsonify({'message': '更新成功'})


@log_analysis_bp.route('/api/log-analysis/tasks/<task_id>', methods=['DELETE'])
def delete_task(task_id):
    """删除日志分析任务"""
    task = get_log_analysis_task(task_id)
    if not task:
        return jsonify({'error': '任务不存在'}), 404

    # 删除关联文件
    files = get_log_analysis_files(task_id)
    for f in files:
        try:
            if os.path.exists(f['file_path']):
                os.remove(f['file_path'])
        except Exception:
            pass

    # 删除任务目录
    task_dir = os.path.join(LOG_ANALYSIS_DIR, task_id)
    try:
        if os.path.exists(task_dir):
            import shutil
            shutil.rmtree(task_dir)
    except Exception:
        pass

    delete_log_analysis_files(task_id)
    delete_log_analysis_task(task_id)
    add_operation_log('日志分析', '删除任务', task.get('name', task_id))

    return jsonify({'message': '删除成功'})


@log_analysis_bp.route('/api/log-analysis/upload/<task_id>', methods=['POST'])
def upload_files(task_id):
    """上传日志文件"""
    task = get_log_analysis_task(task_id)
    if not task:
        return jsonify({'error': '任务不存在'}), 404

    if 'files' not in request.files:
        return jsonify({'error': '没有文件'}), 400

    files = request.files.getlist('files')
    if not files or all(f.filename == '' for f in files):
        return jsonify({'error': '未选择文件'}), 400

    task_dir = _get_task_dir(task_id)
    uploaded = []
    failed = []

    for file in files:
        if file.filename == '':
            continue
        if not allowed_file(file.filename):
            failed.append({'filename': file.filename, 'reason': '不支持的文件格式'})
            continue

        filename = safe_filename(file.filename)
        filepath = os.path.join(task_dir, filename)
        file.save(filepath)

        # 提取内容
        content_text = extract_content(filepath)
        file_size = os.path.getsize(filepath)

        # 存入数据库
        file_id = str(uuid.uuid4())
        add_log_analysis_file(file_id, task_id, filename, filepath, file_size, content_text)
        uploaded.append({
            'id': file_id,
            'filename': filename,
            'file_size': file_size
        })

    add_operation_log('日志分析', '上传文件', f'{task["name"]}: {len(uploaded)}个文件')
    return jsonify({
        'message': f'上传成功 {len(uploaded)} 个文件',
        'uploaded': uploaded,
        'failed': failed
    })


@log_analysis_bp.route('/api/log-analysis/analyze/<task_id>', methods=['POST'])
def analyze_logs(task_id):
    """执行日志分析（SSE 流式输出）"""
    task = get_log_analysis_task(task_id)
    if not task:
        return jsonify({'error': '任务不存在'}), 404

    data = request.get_json() or {}
    model_id = data.get('model_id', '')
    use_rag = data.get('use_rag', True)

    # 获取任务文件
    files = get_log_analysis_files(task_id)
    if not files:
        return jsonify({'error': '请先上传日志文件'}), 400

    # 更新任务状态
    update_log_analysis_task(task_id, status='analyzing', current_stage='intent')

    def generate():
        # 记录各阶段耗时
        stage_timings = {}

        try:
            # 构建文件信息
            file_list = []
            log_contents = []
            for f in files:
                file_list.append({
                    'filename': f['filename'],
                    'size': f['file_size'],
                    'content_preview': (f['content_text'] or '')[:500]
                })
                log_contents.append(f"=== {f['filename']} ===\n{f['content_text'] or ''}")

            full_logs = '\n\n'.join(log_contents)
            # 限制日志长度，避免超出 LLM 上下文
            max_log_length = 50000
            if len(full_logs) > max_log_length:
                full_logs = full_logs[:max_log_length] + '\n\n[日志内容过长，已截断...]'

            question = task.get('question', '')
            db_type = task.get('db_type', '')

            # ===== 第一轮：意图识别 =====
            intent_start = time.time()
            yield _sse_data({
                'stage': 'intent',
                'status': 'analyzing',
                'message': '正在理解问题意图...'
            })

            # RAG 增强：查询知识库（根据数据库类型过滤）
            rag_context = ''
            if use_rag:
                try:
                    from rag import Embedder
                    embedder = Embedder()
                    # 如果有指定数据库类型，查询对应知识库；否则查询系统知识库
                    search_db_type = db_type if db_type else '_system'
                    rag_results = embedder.similarity_search(
                        f"日志分析 {question} 问题排查",
                        db_type=search_db_type,
                        top_k=3
                    )
                    if rag_results:
                        rag_context = '\n\n参考知识库内容：\n'
                        for i, r in enumerate(rag_results, 1):
                            rag_context += f"{i}. {r['filename']}: {r['chunk_text'][:300]}\n"
                except Exception as e:
                    print(f"[日志分析] RAG 查询失败: {e}")
                    pass

            # 构建数据库类型上下文
            db_type_context = ''
            if db_type:
                db_type_context = f"\n数据库类型：{db_type}\n请针对 {db_type} 数据库的特性和日志格式进行分析。"

            intent_messages = [
                {"role": "system", "content": "你是一个数据库运维专家，擅长分析日志文件。请根据用户的问题和日志文件信息，确定分析方向。"},
                {"role": "user", "content": f"""用户问题：{question}

日志文件列表：
{json.dumps(file_list, ensure_ascii=False, indent=2)}

{rag_context}
{db_type_context}

请分析：
1. 这个问题的分析方向是什么？（错误排查/性能分析/安全审计/其他）
2. 需要重点关注哪些日志文件？
3. 关键时间范围是什么？（如果有）
4. 建议的分析步骤是什么？

请以 JSON 格式返回：
{{
    "direction": "分析方向",
    "focus_files": ["重点文件1", "重点文件2"],
    "time_range": "关键时间范围或null",
    "analysis_steps": ["步骤1", "步骤2", "步骤3"]
}}"""}
            ]

            intent_result = ''
            print(f"[日志分析] 开始意图识别，任务ID: {task_id}")
            for content, error in call_llm_stream(intent_messages, model_id=model_id):
                if error:
                    print(f"[日志分析] 意图识别失败: {error}")
                    yield _sse_data({'stage': 'intent', 'status': 'error', 'message': f'意图识别失败: {error}'})
                    update_log_analysis_task(task_id, status='failed', current_stage='intent')
                    yield "data: [DONE]\n\n"
                    return
                if content:
                    intent_result += content

            # 解析意图结果
            try:
                intent_json = _extract_json(intent_result)
                print(f"[日志分析] 意图识别完成: {intent_json.get('direction', '未知')}")
            except Exception as e:
                print(f"[日志分析] 意图识别结果解析失败: {e}, 结果: {intent_result[:200]}")
                intent_json = {
                    'direction': '综合排查',
                    'focus_files': [f['filename'] for f in file_list],
                    'time_range': None,
                    'analysis_steps': ['筛选关键日志', '定位异常', '分析根因']
                }

            yield _sse_data({
                'stage': 'intent',
                'status': 'complete',
                'result': intent_json
            })
            stage_timings['intent'] = int((time.time() - intent_start) * 1000)

            # ===== 第二轮：日志筛选 =====
            filter_start = time.time()
            yield _sse_data({
                'stage': 'filter',
                'status': 'analyzing',
                'message': '正在筛选关键日志...'
            })

            filter_messages = [
                {"role": "system", "content": "你是一个数据库运维专家，擅长从大量日志中筛选关键信息。"},
                {"role": "user", "content": f"""用户问题：{question}

分析方向：{intent_json.get('direction', '综合排查')}
重点文件：{json.dumps(intent_json.get('focus_files', []), ensure_ascii=False)}

完整日志内容：
{full_logs}

请从上述日志中筛选出最关键的日志片段（最多10条），按优先级排序。
对每条关键日志，请说明：
1. 日志内容（原文摘录）
2. 来源文件
3. 严重程度（ERROR/WARN/INFO）
4. 为什么这条日志重要

请以 JSON 格式返回：
{{
    "key_logs": [
        {{
            "content": "日志原文",
            "source": "文件名",
            "severity": "ERROR",
            "reason": "重要性说明"
        }}
    ],
    "summary": "筛选总结"
}}"""}
            ]

            filter_result = ''
            print(f"[日志分析] 开始日志筛选")
            for content, error in call_llm_stream(filter_messages, model_id=model_id):
                if error:
                    print(f"[日志分析] 日志筛选失败: {error}")
                    yield _sse_data({'stage': 'filter', 'status': 'error', 'message': f'日志筛选失败: {error}'})
                    update_log_analysis_task(task_id, status='failed', current_stage='filter')
                    yield "data: [DONE]\n\n"
                    return
                if content:
                    filter_result += content

            try:
                filter_json = _extract_json(filter_result)
                print(f"[日志分析] 日志筛选完成，找到 {len(filter_json.get('key_logs', []))} 条关键日志")
            except Exception as e:
                print(f"[日志分析] 日志筛选结果解析失败: {e}")
                filter_json = {
                    'key_logs': [],
                    'summary': '日志筛选完成，未提取到结构化结果'
                }

            yield _sse_data({
                'stage': 'filter',
                'status': 'complete',
                'result': filter_json
            })
            stage_timings['filter'] = int((time.time() - filter_start) * 1000)

            # ===== 第三轮：根因分析 =====
            analysis_start = time.time()
            yield _sse_data({
                'stage': 'analysis',
                'status': 'analyzing',
                'message': '正在进行根因分析...'
            })

            # RAG 增强：查询故障处理方案
            rag_context2 = ''
            if use_rag:
                try:
                    from rag import Embedder
                    embedder = Embedder()
                    # 根据分析方向查询相关知识
                    search_query = f"{intent_json.get('direction', '')} {question} 故障处理 解决方案"
                    rag_results2 = embedder.similarity_search(search_query, db_type='_system', top_k=3)
                    if rag_results2:
                        rag_context2 = '\n\n参考知识库内容：\n'
                        for i, r in enumerate(rag_results2, 1):
                            rag_context2 += f"{i}. {r['filename']}: {r['chunk_text'][:300]}\n"
                except Exception:
                    pass

            key_logs_text = ''
            for log in filter_json.get('key_logs', [])[:5]:
                key_logs_text += f"\n[{log.get('severity', 'INFO')}] {log.get('source', '未知')}\n{log.get('content', '')}\n原因：{log.get('reason', '')}\n"

            analysis_messages = [
                {"role": "system", "content": "你是一个资深数据库运维专家，擅长根因分析和故障排查。"},
                {"role": "user", "content": f"""用户问题：{question}

分析方向：{intent_json.get('direction', '综合排查')}

关键日志片段：
{key_logs_text}

{rag_context2}

请进行深入的根因分析，回答：
1. 问题根因是什么？
2. 影响范围有多大？
3. 解决方案和修复步骤？
4. 预防措施？
5. 需要关注的相关指标？

请以 JSON 格式返回：
{{
    "root_cause": "根因分析",
    "impact": "影响范围",
    "solution": "解决方案",
    "prevention": "预防措施",
    "metrics": ["关注指标1", "关注指标2"]
}}"""}
            ]

            analysis_result = ''
            print(f"[日志分析] 开始根因分析")
            for content, error in call_llm_stream(analysis_messages, model_id=model_id):
                if error:
                    print(f"[日志分析] 根因分析失败: {error}")
                    yield _sse_data({'stage': 'analysis', 'status': 'error', 'message': f'根因分析失败: {error}'})
                    update_log_analysis_task(task_id, status='failed', current_stage='analysis')
                    yield "data: [DONE]\n\n"
                    return
                if content:
                    analysis_result += content

            try:
                analysis_json = _extract_json(analysis_result)
                print(f"[日志分析] 根因分析完成")
            except Exception as e:
                print(f"[日志分析] 根因分析结果解析失败: {e}")
                analysis_json = {
                    'root_cause': analysis_result[:500] if analysis_result else '分析完成，未提取到结构化结果',
                    'impact': '未知',
                    'solution': '请查看详细分析内容',
                    'prevention': '建议定期巡检',
                    'metrics': []
                }

            yield _sse_data({
                'stage': 'analysis',
                'status': 'complete',
                'result': analysis_json
            })
            stage_timings['analysis'] = int((time.time() - analysis_start) * 1000)

            # ===== 生成最终报告 =====
            report_start = time.time()
            report = _generate_report(task, intent_json, filter_json, analysis_json)
            stage_timings['report'] = int((time.time() - report_start) * 1000)

            # 保存结果
            stages = {
                'intent': {**intent_json, 'duration': stage_timings.get('intent', 0)},
                'filter': {**filter_json, 'duration': stage_timings.get('filter', 0)},
                'analysis': {**analysis_json, 'duration': stage_timings.get('analysis', 0)},
                'report': {'duration': stage_timings.get('report', 0)}
            }
            from datetime import datetime
            update_log_analysis_task(
                task_id,
                status='completed',
                current_stage='report',
                stages=json.dumps(stages, ensure_ascii=False),
                report=report,
                completed_at=datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            )

            yield _sse_data({
                'stage': 'report',
                'status': 'complete',
                'report': report
            })

            print(f"[日志分析] 分析完成，任务ID: {task_id}")
            add_operation_log('日志分析', '完成分析', task.get('name', task_id))

        except Exception as e:
            print(f"[日志分析] 分析过程出错: {e}")
            yield _sse_data({
                'stage': 'error',
                'status': 'error',
                'message': f'分析过程出错: {str(e)}'
            })
            update_log_analysis_task(task_id, status='failed', current_stage='error')

        yield "data: [DONE]\n\n"

    return Response(generate(), mimetype='text/event-stream', headers={
        'Cache-Control': 'no-cache',
        'X-Accel-Buffering': 'no'
    })


def _sse_data(data):
    """构建 SSE 数据行"""
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


def _extract_json(text):
    """从文本中提取 JSON 对象"""
    import re
    # 尝试找到 JSON 代码块
    match = re.search(r'```json\s*(.*?)\s*```', text, re.DOTALL)
    if match:
        return json.loads(match.group(1))

    # 尝试找到花括号包裹的内容
    match = re.search(r'\{.*\}', text, re.DOTALL)
    if match:
        return json.loads(match.group(0))

    raise ValueError('未找到 JSON 内容')


def _generate_report(task, intent, filter_result, analysis):
    """生成结构化分析报告"""
    report = f"""# 📋 日志分析报告

## 任务信息
- **任务名称**：{task.get('name', '未命名')}
- **分析问题**：{task.get('question', '')}
- **分析时间**：{task.get('created_at', '')}

---

## 一、分析方向

**方向**：{intent.get('direction', '综合排查')}

**重点文件**：
{chr(10).join(['- ' + f for f in intent.get('focus_files', [])])}

**建议步骤**：
{chr(10).join([str(i+1) + '. ' + step for i, step in enumerate(intent.get('analysis_steps', []))])}

---

## 二、关键日志

**筛选总结**：{filter_result.get('summary', '')}

| 来源文件 | 严重程度 | 日志内容 | 重要性 |
|---------|---------|---------|--------|
"""
    for log in filter_result.get('key_logs', [])[:10]:
        content = log.get('content', '')[:100] + '...' if len(log.get('content', '')) > 100 else log.get('content', '')
        report += f"| {log.get('source', '')} | {log.get('severity', '')} | {content} | {log.get('reason', '')} |\n"

    report += f"""
---

## 三、根因分析

### 问题根因
{analysis.get('root_cause', '未确定')}

### 影响范围
{analysis.get('impact', '未知')}

### 解决方案
{analysis.get('solution', '暂无')}

### 预防措施
{analysis.get('prevention', '暂无')}

### 关注指标
{chr(10).join(['- ' + m for m in analysis.get('metrics', [])])}

---

*报告由 AI 自动生成，仅供参考*
"""
    return report
