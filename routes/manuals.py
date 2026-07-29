# -*- coding: utf-8 -*-
"""运维手册 API"""
import os
from datetime import datetime
from flask import Blueprint, request, jsonify, send_from_directory
from werkzeug.utils import secure_filename
from db.database import add_operation_log

manuals_bp = Blueprint('manuals', __name__)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MANUALS_DIR = os.path.join(BASE_DIR, 'data', 'manuals')

# 可预览的文件类型
PREVIEWABLE_EXTENSIONS = {'txt', 'md', 'html', 'htm', 'json', 'xml', 'sql', 'py', 'sh', 'log'}


def can_preview(filename):
    """检查文件是否可预览"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in PREVIEWABLE_EXTENSIONS


@manuals_bp.route('/api/manuals', methods=['GET'])
def get_manuals():
    os.makedirs(MANUALS_DIR, exist_ok=True)
    manuals = []
    for filename in os.listdir(MANUALS_DIR):
        filepath = os.path.join(MANUALS_DIR, filename)
        if os.path.isfile(filepath):
            stat = os.stat(filepath)
            manuals.append({
                'name': filename,
                'size': stat.st_size,
                'modified': datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M:%S'),
                'can_preview': can_preview(filename)
            })
    manuals.sort(key=lambda x: x['modified'], reverse=True)
    return jsonify({'manuals': manuals})


@manuals_bp.route('/api/manuals/upload', methods=['POST'])
def upload_manual():
    if 'file' not in request.files:
        return jsonify({'error': '没有文件'}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': '未选择文件'}), 400

    # 保留原始中文文件名，secure_filename 会过滤非ASCII字符
    original_filename = file.filename
    filename = secure_filename(original_filename)
    # 如果 secure_filename 过滤后为空（纯中文文件名），使用原始文件名
    if not filename or filename == '':
        filename = original_filename
    # 如果过滤后的文件名与原始不同（包含中文），优先使用原始文件名
    elif filename != original_filename:
        # 检查原始文件名是否安全（只包含常见字符）
        import re
        if re.match(r'^[\w\s\-\.一-鿿　-〿＀-￯]+$', original_filename):
            filename = original_filename

    os.makedirs(MANUALS_DIR, exist_ok=True)
    filepath = os.path.join(MANUALS_DIR, filename)

    if os.path.exists(filepath):
        name, ext = os.path.splitext(filename)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"{name}_{timestamp}{ext}"
        filepath = os.path.join(MANUALS_DIR, filename)

    file.save(filepath)
    add_operation_log('运维手册', '上传手册', filename)
    return jsonify({'message': '上传成功', 'filename': filename})


@manuals_bp.route('/api/manuals/<filename>', methods=['DELETE'])
def delete_manual(filename):
    import time
    filepath = os.path.join(MANUALS_DIR, filename)
    if not os.path.exists(filepath):
        return jsonify({'error': '文件不存在'}), 404
    for _ in range(3):
        try:
            os.remove(filepath)
            break
        except PermissionError:
            time.sleep(0.1)
    add_operation_log('运维手册', '删除手册', filename)
    return jsonify({'message': '删除成功'})


@manuals_bp.route('/api/manuals/<filename>', methods=['GET'])
def download_manual(filename):
    if not os.path.exists(os.path.join(MANUALS_DIR, filename)):
        return jsonify({'error': '文件不存在'}), 404
    return send_from_directory(MANUALS_DIR, filename, as_attachment=True)


@manuals_bp.route('/api/manuals/preview/<filename>', methods=['GET'])
def preview_manual(filename):
    """预览手册内容"""
    filepath = os.path.join(MANUALS_DIR, filename)

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


def sync_manuals_to_knowledge():
    """将运维手册内容同步到知识库（_system 类型），供RAG检索"""
    from db.database import add_knowledge_file, get_knowledge_files, delete_knowledge_file
    from utils import extract_content

    try:
        if not os.path.exists(MANUALS_DIR):
            return 0

        # 获取当前已同步的手册文件列表
        existing_files = {}
        try:
            files = get_knowledge_files('_system')
            for f in files:
                if f['filename'] != '_topology.txt':  # 保留拓扑文件
                    existing_files[f['filename']] = f['id']
        except Exception:
            pass

        synced_count = 0
        current_files = set()

        for filename in os.listdir(MANUALS_DIR):
            filepath = os.path.join(MANUALS_DIR, filename)
            if not os.path.isfile(filepath):
                continue

            current_files.add(filename)

            # 如果文件已存在且内容未变，跳过
            if filename in existing_files:
                continue

            # 提取文件内容
            content_text = extract_content(filepath)
            if not content_text:
                continue

            # 添加前缀标识来源
            content_text = f"【运维手册：{filename}】\n\n{content_text}"

            file_size = os.path.getsize(filepath)

            # 存入知识库，db_type 为 _system
            add_knowledge_file('_system', filename, filepath, file_size, content_text, ['manual'])
            synced_count += 1

            # 生成向量嵌入
            try:
                from rag import Embedder
                from rag.embedder import chunk_text
                from db.database import save_embeddings

                files = get_knowledge_files('_system')
                for f in files:
                    if f['filename'] == filename:
                        chunks = chunk_text(content_text)
                        if chunks:
                            embedder = Embedder()
                            embeddings = embedder.embed_chunks(chunks)
                            save_embeddings(f['id'], embeddings)
                        break
            except Exception:
                pass  # 向量嵌入失败不影响同步

        # 删除已不在手册目录中的文件
        for old_filename in existing_files:
            if old_filename not in current_files:
                try:
                    delete_knowledge_file('_system', old_filename)
                except Exception:
                    pass

        if synced_count > 0:
            print(f"[自动同步] 运维手册同步完成，共 {synced_count} 个文件")
        return synced_count
    except Exception as e:
        print(f"[自动同步] 运维手册同步失败: {e}")
        return 0
