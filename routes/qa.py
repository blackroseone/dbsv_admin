# -*- coding: utf-8 -*-
"""知识问答 API"""
import json
import uuid
import re
from flask import Blueprint, request, jsonify, Response
from db.database import (
    get_db_types, search_knowledge_content, add_operation_log,
    create_conversation, get_conversations, get_conversation, delete_conversation,
    add_message, get_messages, update_conversation_time
)
from utils import call_llm, call_llm_stream, stream_llm_response

qa_bp = Blueprint('qa', __name__)


def detect_db_type_from_question(question):
    """从问题中自动识别数据库类型"""
    lower_question = question.lower()

    # 数据库类型关键词映射（按优先级排序）
    db_keywords = {
        'oracle': ['oracle', 'ora', 'oracle数据库', 'oracle数据库'],
        'mysql': ['mysql', 'my sql', 'mariadb'],
        'tdsql': ['tdsql', 'td sql', 'tencentdb', 'tencent db'],
        'oceanbase': ['oceanbase', 'ocean base', 'ob'],
        'goldendb': ['goldendb', 'golden db', 'golden'],
        'dm': ['达梦', '达梦数据库', 'dm', 'dameng'],
        'gaussdb': ['gaussdb', 'gauss db', 'gauss', '高斯']
    }

    # 遍历检测
    for db_type, keywords in db_keywords.items():
        for keyword in keywords:
            if keyword in lower_question:
                return db_type

    # 未识别到，返回空字符串
    return ''


# ==================== 会话管理 API ====================

@qa_bp.route('/api/qa/conversations', methods=['GET'])
def list_conversations():
    """获取会话列表"""
    conversations = get_conversations()
    return jsonify({'conversations': conversations})


@qa_bp.route('/api/qa/conversations', methods=['DELETE'])
def clear_all_conversations():
    """清空所有会话"""
    from db.database import clear_conversations
    clear_conversations()
    return jsonify({'message': '清空成功'})


@qa_bp.route('/api/qa/conversations', methods=['POST'])
def create_new_conversation():
    """创建新会话"""
    data = request.get_json()
    conv_id = str(uuid.uuid4())
    title = data.get('title', '新对话')
    db_type = data.get('db_type', '')
    model_id = data.get('model_id', '')

    create_conversation(conv_id, title, db_type, model_id)
    return jsonify({
        'message': '创建成功',
        'conversation': {
            'id': conv_id,
            'title': title,
            'db_type': db_type,
            'model_id': model_id
        }
    })


@qa_bp.route('/api/qa/conversations/<conv_id>', methods=['GET'])
def get_conversation_detail(conv_id):
    """获取会话详情及消息"""
    conversation = get_conversation(conv_id)
    if not conversation:
        return jsonify({'error': '会话不存在'}), 404

    messages = get_messages(conv_id)
    return jsonify({
        'conversation': conversation,
        'messages': messages
    })


@qa_bp.route('/api/qa/conversations/<conv_id>', methods=['DELETE'])
def delete_conversation_api(conv_id):
    """删除会话"""
    success = delete_conversation(conv_id)
    if success:
        return jsonify({'message': '删除成功', 'success': True})
    else:
        return jsonify({'message': '删除失败', 'success': False}), 500


@qa_bp.route('/api/qa/conversations/<conv_id>', methods=['PUT'])
def update_conversation_api(conv_id):
    """更新会话信息"""
    data = request.get_json()
    title = data.get('title')
    if title:
        from db.database import update_conversation_title
        update_conversation_title(conv_id, title)
    return jsonify({'message': '更新成功'})


@qa_bp.route('/api/qa/conversations/<conv_id>/messages', methods=['POST'])
def add_message_to_conversation(conv_id):
    """向会话添加消息"""
    data = request.get_json()
    role = data.get('role')
    content = data.get('content')

    if not role or not content:
        return jsonify({'error': 'role 和 content 不能为空'}), 400

    add_message(conv_id, role, content)
    update_conversation_time(conv_id)
    return jsonify({'message': '添加成功'})


@qa_bp.route('/api/qa/templates', methods=['GET'])
def get_qa_templates():
    templates = [
        {'id': 'error', 'name': '报错处理', 'template': '我在{db_type}执行{操作}时遇到以下错误：\n\n请帮我分析原因并提供解决方案'},
        {'id': 'syntax', 'name': '语法查询', 'template': '{db_type}中如何实现{功能}？请提供SQL示例'},
        {'id': 'performance', 'name': '性能问题', 'template': '{db_type}数据库{现象}，请帮我分析可能的原因和优化方案'},
        {'id': 'install', 'name': '安装问题', 'template': '在{系统}上安装{db_type}时遇到问题：\n\n请提供解决步骤'},
        {'id': 'backup', 'name': '备份恢复', 'template': '如何在{db_type}中实现{备份方式}？请提供详细步骤'}
    ]
    return jsonify({'templates': templates})


def _build_qa_messages(db_type, question, use_rag, conversation_id=None, use_topology=True):
    """构建问答消息，支持多轮对话"""

    # 如果数据库类型为 auto，自动识别
    if db_type == 'auto':
        detected_db = detect_db_type_from_question(question)
        if detected_db:
            db_type = detected_db
        else:
            db_type = ''  # 未识别到，不指定数据库类型

    # 获取数据库类型名称
    db_types = get_db_types()
    db_name = db_type
    for t in db_types:
        if t['id'] == db_type:
            db_name = t['name']
            break

    # 辅助函数：从问题中提取关键词进行检索
    def _extract_keywords(text):
        """提取问题中的关键词（IP地址、主机名、集群名、中文名称等）"""
        import re
        keywords = []
        # 提取IP地址（支持中文前后缀）
        ip_pattern = r'(?:^|[^\d.])(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})(?:[^\d.]|$)'
        ips = re.findall(ip_pattern, text)
        keywords.extend(ips)
        # 提取英文主机名（字母数字组合，通常包含-或_）
        hostname_pattern = r'\b[a-zA-Z][a-zA-Z0-9_-]*[a-zA-Z0-9]\b'
        hostnames = re.findall(hostname_pattern, text)
        # 过滤掉常见的停用词
        stopwords = {'the', 'a', 'an', 'is', 'are', 'was', 'were', 'be', 'been',
                     'being', 'have', 'has', 'had', 'do', 'does', 'did', 'will',
                     'would', 'could', 'should', 'may', 'might', 'must', 'shall',
                     'can', 'need', 'dare', 'ought', 'used', 'get', 'got',
                     '什么', '哪个', '怎么', '为什么', '如何', '哪里', '谁',
                     '的', '了', '是', '在', '和', '与', '或', '等', '有', '个',
                     '台', '台服务器', '集群', '服务器', '实例', '节点'}
        for h in hostnames:
            if h.lower() not in stopwords and len(h) > 2:
                keywords.append(h)
        # 提取中文名称（2-20个汉字的连续词组，可能包含字母数字）
        # 匹配模式：中文+可能的字母数字组合，如"沃趣风控集群"、"MySQL实例"等
        # 使用Unicode中文范围：一-鿿 (U+4E00-U+9FFF)
        chinese_pattern = r'[一-鿿][一-鿿\w]{1,19}'
        chinese_names = re.findall(chinese_pattern, text)
        for name in chinese_names:
            # 过滤掉纯停用词的名称
            if name not in stopwords and len(name) > 2:
                keywords.append(name)
        # 如果以上都没提取到，返回原始问题
        if not keywords:
            keywords = [text]
        return keywords

    def _search_with_keywords(db_type, question):
        """使用关键词检索知识库"""
        keywords = _extract_keywords(question)
        all_results = []
        seen = set()
        for kw in keywords:
            results = search_knowledge_content(db_type, kw)
            for r in results:
                key = (r['filename'], r['context'])
                if key not in seen:
                    seen.add(key)
                    all_results.append(r)
        return all_results

    # RAG检索：优先使用向量检索，回退到关键词检索
    # 严格的检索阈值控制，防止LLM幻觉
    MIN_SIMILARITY_THRESHOLD = 0.55  # 最低相似度阈值（sentence-transformers 余弦相似度通常较低，0.55 是合理阈值）
    MIN_KNOWLEDGE_COVERAGE = 0.60    # 知识覆盖率要求

    context = ""
    knowledge_confidence = "low"  # 知识库置信度: low/medium/high
    knowledge_sources = []  # 知识库来源记录
    kg_context = ""  # 知识图谱上下文
    kg_entities = []  # 知识图谱实体列表
    use_kg = True  # 默认启用知识图谱增强

    if use_rag:
        search_results = []
        all_vector_results = []  # 用于计算最高相似度

        # 检索用户选择的数据库类型的知识库文件
        if db_type:
            from db.database import get_knowledge_files
            files = get_knowledge_files(db_type)
            if files:
                try:
                    from rag import Embedder
                    embedder = Embedder()
                    vector_results = embedder.similarity_search(question, db_type=db_type, top_k=5)
                    if vector_results:
                        # 过滤低相似度结果
                        filtered_results = [r for r in vector_results if r.get('similarity', 0) >= MIN_SIMILARITY_THRESHOLD]
                        if filtered_results:
                            search_results = [{
                                'filename': r['filename'],
                                'context': r['chunk_text'],
                                'similarity': r.get('similarity', 0)
                            } for r in filtered_results]
                            all_vector_results.extend(filtered_results)
                    elif not embedder.is_available():
                        # 模型不可用导致检索为空，回退到关键词检索（兜底）
                        search_results = _search_with_keywords(db_type, question)
                    # 模型可用但无命中：不回退（避免低质量结果）
                except Exception:
                    # 向量检索异常，回退到关键词检索（兜底）
                    search_results = _search_with_keywords(db_type, question)

        # 检索 _system 类型的知识库文件（拓扑 + 运维手册）
        system_results = []
        if use_topology:
            try:
                from db.database import get_knowledge_files
                system_files = get_knowledge_files('_system')
                if system_files:
                    try:
                        from rag import Embedder
                        embedder = Embedder()
                        vector_results = embedder.similarity_search(question, db_type='_system', top_k=5)
                        if vector_results:
                            # 过滤低相似度结果
                            filtered_results = [r for r in vector_results if r.get('similarity', 0) >= MIN_SIMILARITY_THRESHOLD]
                            if filtered_results:
                                system_results = [{
                                    'filename': r['filename'],
                                    'context': r['chunk_text'],
                                    'similarity': r.get('similarity', 0)
                                } for r in filtered_results]
                                all_vector_results.extend(filtered_results)
                        elif not embedder.is_available():
                            # 模型不可用导致检索为空，回退到关键词检索（兜底）
                            system_results = _search_with_keywords('_system', question)
                    except Exception:
                        # 向量检索异常，回退到关键词检索（兜底）
                        system_results = _search_with_keywords('_system', question)
            except Exception:
                pass

        # 知识图谱增强
        if use_kg and all_vector_results:
            try:
                from db.database import get_db
                from kg.graph import enhance_qa_context

                conn = get_db()
                chunk_ids = []
                # 获取 chunk IDs
                for result in all_vector_results[:5]:
                    # 查找 chunk ID
                    row = conn.execute(
                        """SELECT e.id FROM embeddings e
                        JOIN knowledge_files k ON e.file_id = k.id
                        WHERE k.filename=? AND e.chunk_text=?""",
                        (result['filename'], result['chunk_text'])
                    ).fetchone()
                    if row:
                        chunk_ids.append(row['id'])

                if chunk_ids:
                    # 获取图谱增强上下文
                    kg_enhance = enhance_qa_context(chunk_ids, question)

                    # 构建图谱上下文
                    if kg_enhance.get('entity_cards'):
                        kg_context += "\n\n【知识图谱实体】\n"
                        for card in kg_enhance['entity_cards'][:5]:
                            kg_context += f"\n• {card['name']} ({card['type']})"
                            if card.get('description'):
                                kg_context += f" - {card['description']}"
                            if card.get('relations'):
                                for rel in card['relations'][:3]:
                                    arrow = '→' if rel['direction'] == 'outgoing' else '←'
                                    kg_context += f"\n  {arrow} [{rel['relation_type']}] {rel['target_name']}"
                            kg_context += "\n"
                            kg_entities.append({
                                'name': card['name'],
                                'type': card['type'],
                                'relations': card.get('relations', [])
                            })

                    # 添加关系链
                    if kg_enhance.get('relation_chains'):
                        kg_context += "\n【实体关系链】\n"
                        for chain in kg_enhance['relation_chains'][:3]:
                            path_str = ' → '.join([
                                item['name'] if 'name' in item else item['relation_type']
                                for item in chain['path']
                                if isinstance(item, dict)
                            ])
                            kg_context += f"\n• {path_str}\n"

            except Exception as e:
                print(f"[QA] 知识图谱增强失败: {e}")

        # 计算知识库置信度
        if all_vector_results:
            max_similarity = max(r.get('similarity', 0) for r in all_vector_results)
            if max_similarity >= 0.85:
                knowledge_confidence = "high"
            elif max_similarity >= MIN_SIMILARITY_THRESHOLD:
                knowledge_confidence = "medium"
            else:
                knowledge_confidence = "low"

        # 记录知识库来源
        for result in search_results + system_results:
            knowledge_sources.append({
                'filename': result['filename'],
                'similarity': round(result.get('similarity', 0), 3)
            })

        # 合并结果，按来源分类
        if search_results or system_results:
            context = "\n\n参考知识库内容：\n"

            # 知识库文件结果
            if search_results:
                context += "\n【知识库文件】\n"
                for i, result in enumerate(search_results[:3], 1):
                    context += f"\n{i}. 文件：{result['filename']} (相似度: {result.get('similarity', 0):.3f})\n内容片段：{result['context']}\n"

            # 系统知识结果（拓扑 + 手册）
            if system_results:
                context += "\n【系统信息（集群拓扑 / 运维手册）】\n"
                for i, result in enumerate(system_results[:3], 1):
                    context += f"\n{i}. 来源：{result['filename']} (相似度: {result.get('similarity', 0):.3f})\n内容片段：{result['context']}\n"
        else:
            # 知识库检索结果为空或相似度过低
            context = "\n\n⚠️ 知识库检索结果：未找到与该问题直接相关的高置信度文档。\n"
            context += f"（检索阈值: 相似度 ≥ {MIN_SIMILARITY_THRESHOLD}）\n"

    # 构建提示词
    confidence_warning = ""
    if knowledge_confidence == "low":
        confidence_warning = """
⚠️ 重要警告：知识库中未找到与该问题直接相关的高置信度文档。
以下回答可能基于模型的一般知识，存在错误风险（幻觉）。
请谨慎对待，建议：
1. 核实回答中的具体参数和命令
2. 参考官方文档进行确认
3. 在生产环境操作前进行测试"""
    elif knowledge_confidence == "medium":
        confidence_warning = """
🟡 注意：知识库检索结果置信度为中等。
回答部分基于知识库内容，部分基于模型推断。
关键操作建议核实。"""

    system_prompt = f"""你是一个{db_name}数据库专家。请根据用户的问题提供详细、准确的回答。
回答要求：
1. 使用中文回答
2. 如果涉及SQL语句，请提供示例
3. 解释清晰，适合初中级开发者理解
4. 如果有参考知识库内容，请优先使用其中的信息
5. 你也可以根据集群拓扑信息回答关于服务器归属、实例分布等问题
6. 你也可以根据运维手册内容回答操作步骤和流程问题
7. **重要**：如果知识库中没有足够信息，请明确说明，不要编造不确定的内容
8. 如果知识图谱提供了实体关系信息，请优先使用结构化关系进行推理
{confidence_warning}"""

    user_message = question
    if context:
        user_message = f"{question}\n{context}"

    # 添加知识图谱上下文
    if kg_context:
        user_message += kg_context

    # 构建消息列表
    messages = [
        {"role": "system", "content": system_prompt},
    ]

    # 如果有会话历史，添加历史消息
    if conversation_id:
        try:
            from db.database import get_messages
            history_messages = get_messages(conversation_id)
            for msg in history_messages:
                messages.append({
                    "role": msg['role'],
                    "content": msg['content']
                })
        except Exception:
            pass

    messages.append({"role": "user", "content": user_message})

    # 构建元数据（用于前端展示知识库引用信息）
    metadata = {
        'confidence': knowledge_confidence,
        'knowledge_sources': knowledge_sources,
        'has_sufficient_knowledge': knowledge_confidence in ('high', 'medium'),
        'kg_entities': kg_entities  # 知识图谱实体信息
    }

    return messages, metadata


@qa_bp.route('/api/qa/ask', methods=['POST'])
def ask_question():
    """数据库知识问答（支持RAG）"""
    data = request.get_json()
    if not data:
        return jsonify({'error': '请求数据为空'}), 400

    db_type = data.get('db_type', '')
    question = data.get('question', '')
    use_rag = data.get('use_rag', True)
    use_topology = data.get('use_topology', True)

    if not question:
        return jsonify({'error': '请输入问题'}), 400

    messages, metadata = _build_qa_messages(db_type, question, use_rag, use_topology=use_topology)

    answer, error = call_llm(messages)
    if error:
        return jsonify({'error': error}), 500

    add_operation_log('知识问答', '发送问题', question[:50])
    return jsonify({'answer': answer, 'metadata': metadata})


@qa_bp.route('/api/qa/ask/stream', methods=['POST'])
def ask_question_stream():
    """数据库知识问答（流式输出，支持多轮对话）"""
    data = request.get_json()
    if not data:
        return jsonify({'error': '请求数据为空'}), 400

    db_type = data.get('db_type', '')
    question = data.get('question', '')
    use_rag = data.get('use_rag', True)
    use_topology = data.get('use_topology', True)
    model_id = data.get('model_id', '')
    conversation_id = data.get('conversation_id', '')

    if not question:
        return jsonify({'error': '请输入问题'}), 400

    messages, metadata = _build_qa_messages(db_type, question, use_rag, conversation_id, use_topology)

    def generate():
        """生成SSE流，包含知识库元数据"""
        # 首先发送知识库检索元数据
        if metadata:
            yield f"data: {json.dumps({'type': 'metadata', 'metadata': metadata}, ensure_ascii=False)}\n\n"

        # 然后发送LLM流式输出
        for content, error in call_llm_stream(messages, model_id=model_id):
            if error:
                yield f"data: {json.dumps({'error': error}, ensure_ascii=False)}\n\n"
                break
            if content:
                yield f"data: {json.dumps({'content': content}, ensure_ascii=False)}\n\n"

        yield "data: [DONE]\n\n"

    return Response(generate(), mimetype='text/event-stream')
