# -*- coding: utf-8 -*-
"""全量重建向量索引 + 知识图谱（分块 500 迁移用）

用法:
    python rebuild_index_full.py            # 重建全部知识库
    python rebuild_index_full.py mysql      # 只重建指定 db_type
    python rebuild_index_full.py _system    # 重建内部类型（拓扑/手册）

与 /api/knowledge/reindex/stream 逻辑一致：每个文件 extract -> chunk -> embed
-> save_embeddings -> _extract_knowledge_graph。额外打印每文件 chunk 数与耗时。
"""
import sys
import os
import time
import io

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', line_buffering=True)
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', line_buffering=True)
os.environ['TRANSFORMERS_OFFLINE'] = '1'

from db.database import get_all_knowledge_files, save_embeddings, update_knowledge_content
from utils import extract_content
from rag.embedder import chunk_text, Embedder

db_type_filter = sys.argv[1] if len(sys.argv) > 1 else None

files = get_all_knowledge_files(db_type_filter)
print(f'待处理文件总数: {len(files)} (db_type={db_type_filter or "全部"})')

embedder = Embedder()
t_start = time.time()
total_chunks = 0
ok = 0
failed = 0

for i, f in enumerate(files, 1):
    file_id = f['id']
    filepath = f['file_path']
    filename = f['filename']
    db_type = f['db_type']

    t_f = time.time()
    if not os.path.exists(filepath):
        print(f'[{i}/{len(files)}] 文件不存在，跳过: {filename}')
        failed += 1
        continue

    try:
        content = extract_content(filepath)
        if not content:
            print(f'[{i}/{len(files)}] 无法提取内容: {filename}')
            failed += 1
            continue

        update_knowledge_content(file_id, content)
        chunks = chunk_text(content)
        if not chunks:
            print(f'[{i}/{len(files)}] 分块为空: {filename}')
            failed += 1
            continue

        embeddings = embedder.embed_chunks(chunks)
        if not embeddings:
            print(f'[{i}/{len(files)}] 嵌入失败: {filename}')
            failed += 1
            continue

        save_embeddings(file_id, embeddings)

        try:
            embedder._extract_knowledge_graph(file_id, db_type, content, chunks, embeddings)
        except Exception as e:
            print(f'  [KG] 图谱提取失败: {filename} - {e}')

        total_chunks += len(chunks)
        ok += 1
        dt = time.time() - t_f
        print(f'[{i}/{len(files)}] OK {filename} ({db_type}) chunks={len(chunks)} 耗时={dt:.1f}s')

    except Exception as e:
        print(f'[{i}/{len(files)}] 失败: {filename} - {e}')
        failed += 1

t_total = time.time() - t_start
print('=' * 60)
print(f'完成: 成功 {ok}, 失败 {failed}, 总耗时 {t_total:.1f}s, 总块数 {total_chunks}')
print(f'平均 {total_chunks / max(t_total, 0.001):.1f} chunks/s')
