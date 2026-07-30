# -*- coding: utf-8 -*-
"""知识库文件管理 + 收藏夹 API"""
import os
import json
from datetime import datetime
from flask import Blueprint, request, jsonify, send_from_directory
from werkzeug.utils import secure_filename
from db.database import (
    get_db_types, get_knowledge_files, add_knowledge_file,
    delete_knowledge_file, get_knowledge_file_path, search_knowledge_content,
    get_all_knowledge_files, update_knowledge_content,
    get_favorites, toggle_favorite, add_operation_log
)
from utils import allowed_file, extract_content

knowledge_bp = Blueprint('knowledge', __name__)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KNOWLEDGE_DIR = os.path.join(BASE_DIR, 'data', 'knowledge')

# 可预览的文件类型
PREVIEWABLE_EXTENSIONS = {'txt', 'md', 'html', 'htm', 'json', 'xml', 'sql', 'py', 'sh', 'log', 'chm'}


def _validate_db_type(db_type):
    """校验数据库类型是否合法，防止路径遍历"""
    if not db_type:
        return False
    # 禁止路径遍历字符
    if '..' in db_type or '/' in db_type or '\\' in db_type:
        return False
    # 校验是否为已注册的数据库类型
    valid_types = {t['id'] for t in get_db_types()}
    return db_type in valid_types


def can_preview(filename):
    """检查文件是否可预览"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in PREVIEWABLE_EXTENSIONS


@knowledge_bp.route('/api/knowledge/files/<db_type>', methods=['GET'])
def get_files(db_type):
    if not _validate_db_type(db_type):
        return jsonify({'error': '无效的数据库类型'}), 400

    tag = request.args.get('tag', '')
    keyword = request.args.get('keyword', '')

    # 确保目录存在
    db_dir = os.path.join(KNOWLEDGE_DIR, db_type)
    os.makedirs(db_dir, exist_ok=True)

    files = get_knowledge_files(db_type, tag=tag or None, keyword=keyword or None)

    # 格式化文件信息
    file_list = []
    for f in files:
        tags = json.loads(f['tags']) if isinstance(f['tags'], str) else f.get('tags', [])
        file_list.append({
            'name': f['filename'],
            'size': f['file_size'],
            'modified': f['created_at'],
            'tags': tags,
            'can_preview': can_preview(f['filename'])
        })

    # 如果有关键词，搜索内容上下文
    search_results = []
    if keyword:
        search_results = search_knowledge_content(db_type, keyword)

    return jsonify({'files': file_list, 'search_results': search_results})


def safe_filename(filename):
    """安全处理文件名，保留中文字符"""
    import re
    # 移除路径部分
    if '/' in filename:
        filename = filename.split('/')[-1]
    if '\\' in filename:
        filename = filename.split('\\')[-1]

    # 只保留字母、数字、中文、下划线、连字符、点号
    filename = re.sub(r'[^\w一-鿿\-\.]', '_', filename)

    # 移除连续的下划线
    filename = re.sub(r'_+', '_', filename)

    # 移除首尾下划线
    filename = filename.strip('_')

    return filename if filename else 'unnamed_file'


@knowledge_bp.route('/api/knowledge/upload/<db_type>', methods=['POST'])
def upload_file(db_type):
    if not _validate_db_type(db_type):
        return jsonify({'error': '无效的数据库类型'}), 400

    if 'file' not in request.files:
        return jsonify({'error': '没有文件'}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': '未选择文件'}), 400

    if not allowed_file(file.filename):
        return jsonify({'error': f'不支持的文件格式，支持: txt, md, pdf, docx, xlsx, xls, doc, html, htm, chm'}), 400

    # 使用安全文件名处理，保留中文
    filename = safe_filename(file.filename)

    db_dir = os.path.join(KNOWLEDGE_DIR, db_type)
    os.makedirs(db_dir, exist_ok=True)

    # 如果文件已存在，添加时间戳
    filepath = os.path.join(db_dir, filename)
    if os.path.exists(filepath):
        name, ext = os.path.splitext(filename)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"{name}_{timestamp}{ext}"
        filepath = os.path.join(db_dir, filename)

    file.save(filepath)
    file_size = os.path.getsize(filepath)

    # 提取文件内容
    content_text = extract_content(filepath)

    # 获取前端传来的标签
    tags_str = request.form.get('tags', '')
    tags = [t.strip() for t in tags_str.split(',') if t.strip()] if tags_str else []

    # 自动标签检测
    if '[案例]' in filename or '故障' in filename:
        if 'case' not in tags:
            tags.append('case')

    # 存入数据库
    file_id = add_knowledge_file(db_type, filename, filepath, file_size, content_text, tags)

    # 记录操作日志
    add_operation_log('知识库', '上传文件', f'{db_type}/{filename}')

    # 异步生成向量嵌入和知识图谱实体
    try:
        from rag import Embedder
        from rag.embedder import chunk_text
        from db.database import save_embeddings

        chunks = chunk_text(content_text)
        if chunks:
            embedder = Embedder()
            embeddings = embedder.embed_chunks(chunks)
            save_embeddings(file_id, embeddings)

            # 提取知识图谱实体
            try:
                embedder._extract_knowledge_graph(file_id, db_type, content_text, chunks, embeddings)
            except Exception as e:
                print(f"[Knowledge] 知识图谱提取失败 [{filename}]: {e}")
    except Exception:
        pass  # 向量嵌入/知识图谱生成失败不影响上传

    return jsonify({'message': '上传成功', 'filename': filename})


@knowledge_bp.route('/api/knowledge/delete/<db_type>/<filename>', methods=['DELETE'])
def delete_file(db_type, filename):
    if not _validate_db_type(db_type):
        return jsonify({'error': '无效的数据库类型'}), 400

    import time
    filepath = os.path.join(KNOWLEDGE_DIR, db_type, filename)
    if os.path.exists(filepath):
        for _ in range(3):
            try:
                os.remove(filepath)
                break
            except PermissionError:
                time.sleep(0.1)

    delete_knowledge_file(db_type, filename)
    add_operation_log('知识库', '删除文件', f'{db_type}/{filename}')
    return jsonify({'message': '删除成功'})


@knowledge_bp.route('/api/knowledge/download/<db_type>/<filename>', methods=['GET'])
def download_file(db_type, filename):
    if not _validate_db_type(db_type):
        return jsonify({'error': '无效的数据库类型'}), 400

    db_dir = os.path.join(KNOWLEDGE_DIR, db_type)
    if not os.path.exists(os.path.join(db_dir, filename)):
        return jsonify({'error': '文件不存在'}), 404
    return send_from_directory(db_dir, filename, as_attachment=True)


@knowledge_bp.route('/api/knowledge/reindex', methods=['POST'])
def reindex():
    """全量重建知识库索引（重新解析文件内容 + 重建向量索引）"""
    files = get_all_knowledge_files()
    count = 0
    for f in files:
        filepath = f['file_path']
        if os.path.exists(filepath):
            content = extract_content(filepath)
            update_knowledge_content(f['id'], content)
            count += 1

    # 重建向量索引
    vector_count = 0
    try:
        from rag import Embedder
        embedder = Embedder()
        vector_count = embedder.rebuild_all()
    except Exception:
        pass  # 向量索引重建失败不影响文本索引

    msg = f'重建索引完成，处理 {count} 个文件'
    if vector_count:
        msg += f'，向量索引 {vector_count} 个文件'
    return jsonify({'message': msg})


@knowledge_bp.route('/api/knowledge/reindex/stream', methods=['GET'])
def reindex_stream():
    """流式重建知识库索引，逐个文件处理，实时返回进度"""
    from flask import Response
    import json

    def generate():
        files = get_all_knowledge_files()
        total = len(files)
        processed = 0
        vector_count = 0

        # 发送总数
        yield f"data: {json.dumps({'total': total, 'processed': 0, 'status': '开始重建索引'})}\n\n"

        # 逐个文件处理：解析内容 + 生成向量索引
        for f in files:
            file_id = f['id']
            filepath = f['file_path']
            filename = f['filename']
            db_type = f['db_type']
            file_processed = False
            vector_generated = False

            if os.path.exists(filepath):
                try:
                    # 1. 解析文件内容
                    content = extract_content(filepath)
                    if content:
                        update_knowledge_content(file_id, content)
                        processed += 1
                        file_processed = True

                        # 2. 生成向量索引（逐个文件）
                        try:
                            from rag.embedder import chunk_text, Embedder
                            embedder = Embedder()
                            chunks = chunk_text(content)
                            if chunks:
                                embeddings = embedder.embed_chunks(chunks)
                                if embeddings:
                                    from db.database import save_embeddings
                                    save_embeddings(file_id, embeddings)
                                    vector_count += 1
                                    vector_generated = True

                                    # 3. 提取知识图谱实体
                                    try:
                                        embedder._extract_knowledge_graph(file_id, db_type, content, chunks, embeddings)
                                    except Exception as e:
                                        print(f"[重建索引] 知识图谱提取失败: {filepath} - {e}")
                        except Exception as e:
                            print(f"[重建索引] 向量索引生成失败: {filepath} - {e}")
                except Exception as e:
                    print(f"[重建索引] 解析失败: {filepath} - {e}")

            # 每处理一个文件都发送进度
            yield f"data: {json.dumps({
                'total': total,
                'processed': processed,
                'vector_count': vector_count,
                'current_file': filename,
                'db_type': db_type,
                'file_processed': file_processed,
                'vector_generated': vector_generated,
                'status': f'正在处理: {filename}'
            })}\n\n"

        # 发送完成消息
        msg = f'重建索引完成，处理 {processed} 个文件'
        if vector_count:
            msg += f'，向量索引 {vector_count} 个文件'

        yield f"data: {json.dumps({
            'total': total,
            'processed': processed,
            'vector_count': vector_count,
            'status': '完成',
            'message': msg,
            'done': True
        })}\n\n"
        yield "data: [DONE]\n\n"

    # 设置较长的超时时间（10分钟）
    response = Response(generate(), mimetype='text/event-stream')
    response.headers['Cache-Control'] = 'no-cache'
    response.headers['X-Accel-Buffering'] = 'no'
    return response


@knowledge_bp.route('/api/knowledge/reindex/file', methods=['POST'])
def reindex_single_file():
    """为单个文件重建向量索引"""
    data = request.get_json()
    file_id = data.get('file_id')

    if not file_id:
        return jsonify({'error': '缺少 file_id 参数'}), 400

    try:
        from db.database import get_knowledge_file_by_id
        file_info = get_knowledge_file_by_id(file_id)
        if not file_info:
            return jsonify({'error': '文件不存在'}), 404

        filepath = file_info['file_path']
        if not os.path.exists(filepath):
            return jsonify({'error': '文件在磁盘上不存在'}), 404

        # 解析内容
        content = extract_content(filepath)
        if not content:
            return jsonify({'error': '无法提取文件内容'}), 500

        update_knowledge_content(file_id, content)

        # 生成向量索引
        from rag.embedder import chunk_text, Embedder
        from db.database import save_embeddings

        embedder = Embedder()
        chunks = chunk_text(content)
        if not chunks:
            return jsonify({'error': '无法分块文件内容'}), 500

        embeddings = embedder.embed_chunks(chunks)
        if not embeddings:
            return jsonify({'error': '无法生成嵌入向量'}), 500

        save_embeddings(file_id, embeddings)

        # 提取知识图谱实体
        try:
            embedder._extract_knowledge_graph(file_id, file_info['db_type'], content, chunks, embeddings)
        except Exception as e:
            print(f"[Knowledge] 知识图谱提取失败 [reindex {file_info['filename']}]: {e}")

        return jsonify({
            'message': f'文件 {file_info["filename"]} 索引重建成功',
            'file_id': file_id,
            'chunks': len(chunks),
            'embeddings': len(embeddings)
        })

    except Exception as e:
        return jsonify({'error': f'重建失败: {str(e)}'}), 500


@knowledge_bp.route('/api/knowledge/reindex/db-type', methods=['POST'])
def reindex_by_db_type():
    """按数据库类型重建向量索引，逐个文件处理"""
    data = request.get_json()
    db_type = data.get('db_type')

    if not db_type:
        return jsonify({'error': '缺少 db_type 参数'}), 400

    try:
        files = get_knowledge_files(db_type)
        total = len(files)
        processed = 0
        vector_count = 0
        errors = []

        for f in files:
            file_id = f['id']
            filepath = f['file_path']

            if not os.path.exists(filepath):
                errors.append(f'{f["filename"]}: 文件不存在')
                continue

            try:
                # 解析内容
                content = extract_content(filepath)
                if not content:
                    errors.append(f'{f["filename"]}: 无法提取内容')
                    continue

                update_knowledge_content(file_id, content)
                processed += 1

                # 生成向量索引
                from rag.embedder import chunk_text, Embedder
                from db.database import save_embeddings

                embedder = Embedder()
                chunks = chunk_text(content)
                if not chunks:
                    errors.append(f'{f["filename"]}: 无法分块')
                    continue

                embeddings = embedder.embed_chunks(chunks)
                if embeddings:
                    save_embeddings(file_id, embeddings)
                    vector_count += 1

                    # 提取知识图谱实体
                    try:
                        embedder._extract_knowledge_graph(file_id, db_type, content, chunks, embeddings)
                    except Exception as e:
                        print(f"[Knowledge] 知识图谱提取失败 [reindex {f['filename']}]: {e}")

            except Exception as e:
                errors.append(f'{f["filename"]}: {str(e)}')

        return jsonify({
            'message': f'{db_type} 索引重建完成',
            'total': total,
            'processed': processed,
            'vector_count': vector_count,
            'errors': errors
        })

    except Exception as e:
        return jsonify({'error': f'重建失败: {str(e)}'}), 500


@knowledge_bp.route('/api/knowledge/scan', methods=['POST'])
def scan_files():
    """扫描知识库目录，将新增的文件自动同步到数据库，并生成向量索引"""
    from db.database import get_all_knowledge_files as _get_all_files, save_embeddings
    from rag.embedder import chunk_text, Embedder

    existing_files = _get_all_files()
    existing_set = set()
    for f in existing_files:
        existing_set.add((f['db_type'], f['filename']))

    scanned_count = 0
    vector_count = 0
    embedder = None

    if os.path.exists(KNOWLEDGE_DIR):
        for db_type_dir in os.listdir(KNOWLEDGE_DIR):
            db_type_path = os.path.join(KNOWLEDGE_DIR, db_type_dir)
            if not os.path.isdir(db_type_path):
                continue

            for filename in os.listdir(db_type_path):
                filepath = os.path.join(db_type_path, filename)
                if not os.path.isfile(filepath):
                    continue

                if (db_type_dir, filename) in existing_set:
                    continue

                if not allowed_file(filename):
                    continue

                try:
                    content_text = extract_content(filepath)
                    file_size = os.path.getsize(filepath)
                    add_knowledge_file(
                        db_type_dir, filename, filepath,
                        file_size, content_text, []
                    )
                    scanned_count += 1

                    # 生成向量索引
                    try:
                        if embedder is None:
                            embedder = Embedder()
                        chunks = chunk_text(content_text)
                        if chunks:
                            files = get_knowledge_files(db_type_dir)
                            file_id = None
                            for f in files:
                                if f['filename'] == filename:
                                    file_id = f['id']
                                    break
                            if file_id:
                                embeddings = embedder.embed_chunks(chunks)
                                save_embeddings(file_id, embeddings)
                                vector_count += 1

                                # 提取知识图谱实体
                                try:
                                    embedder._extract_knowledge_graph(file_id, db_type_dir, content_text, chunks, embeddings)
                                except Exception as e:
                                    print(f"[Knowledge] 知识图谱提取失败 [scan {filename}]: {e}")
                    except Exception as e:
                        print(f"[扫描] 向量索引生成失败: {filepath} - {e}")

                except Exception as e:
                    print(f"[扫描] 文件入库失败: {filepath} - {e}")

    add_operation_log('知识库', '扫描文件', f'发现 {scanned_count} 个新文件')

    msg = f'扫描完成，发现 {scanned_count} 个新文件'
    if vector_count > 0:
        msg += f'，其中 {vector_count} 个文件已生成向量索引'
    return jsonify({'message': msg, 'scanned': scanned_count, 'vector_indexed': vector_count})


# ==================== 收藏夹API ====================

@knowledge_bp.route('/api/favorites', methods=['GET'])
def get_fav():
    return jsonify(get_favorites())


@knowledge_bp.route('/api/favorites', methods=['POST'])
def toggle_fav():
    data = request.get_json()
    db_type = data.get('db_type', '')
    filename = data.get('filename', '')
    if not _validate_db_type(db_type):
        return jsonify({'error': '无效的数据库类型'}), 400
    action = toggle_favorite(db_type, filename)
    return jsonify({'message': action, 'favorites': get_favorites()})


@knowledge_bp.route('/api/knowledge/preview/<db_type>/<filename>', methods=['GET'])
def preview_file(db_type, filename):
    """预览文件内容"""
    if not _validate_db_type(db_type):
        return jsonify({'error': '无效的数据库类型'}), 400

    db_dir = os.path.join(KNOWLEDGE_DIR, db_type)
    filepath = os.path.join(db_dir, filename)

    if not os.path.exists(filepath):
        return jsonify({'error': '文件不存在'}), 404

    if not can_preview(filename):
        return jsonify({'error': '该文件格式不支持预览'}), 400

    try:
        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()

        return jsonify({
            'filename': filename,
            'content': content,
            'size': os.path.getsize(filepath)
        })
    except Exception as e:
        return jsonify({'error': f'读取文件失败: {str(e)}'}), 500


@knowledge_bp.route('/api/knowledge/tags/<db_type>/<filename>', methods=['PUT'])
def update_file_tags(db_type, filename):
    """更新文件标签"""
    if not _validate_db_type(db_type):
        return jsonify({'error': '无效的数据库类型'}), 400

    data = request.get_json()
    tags = data.get('tags', [])

    from db.database import get_db
    conn = get_db()
    import json
    tags_str = json.dumps(tags, ensure_ascii=False)

    conn.execute(
        "UPDATE knowledge_files SET tags=? WHERE db_type=? AND filename=?",
        (tags_str, db_type, filename)
    )
    conn.commit()

    return jsonify({'message': '标签更新成功', 'tags': tags})
