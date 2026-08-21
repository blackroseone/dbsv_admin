# -*- coding: utf-8 -*-
import sys
sys.stdout.reconfigure(encoding='utf-8')
import os
os.environ['TRANSFORMERS_OFFLINE'] = '1'

from db.database import get_knowledge_files, save_embeddings, update_knowledge_content
from utils import extract_content
from rag.embedder import chunk_text, Embedder

files = get_knowledge_files('dm')
print(f'达梦文件总数: {len(files)}')

embedder = Embedder()
success = 0
failed = 0

for f in files:
    file_id = f['id']
    filepath = f['file_path']
    filename = f['filename']

    print(f'处理: {filename}')

    if not os.path.exists(filepath):
        print(f'  文件不存在')
        failed += 1
        continue

    try:
        content = extract_content(filepath)
        if not content:
            print(f'  无法提取内容')
            failed += 1
            continue

        update_knowledge_content(file_id, content)
        chunks = chunk_text(content)  # 使用 config 默认参数
        if not chunks:
            print(f'  无法分块')
            failed += 1
            continue

        print(f'  生成 {len(chunks)} chunks')

        embeddings = embedder.embed_chunks(chunks)
        if embeddings:
            save_embeddings(file_id, embeddings)
            success += 1
            print(f'  成功: {len(chunks)} chunks, {len(embeddings)} embeddings')
        else:
            print(f'  嵌入生成失败')
            failed += 1

    except Exception as e:
        print(f'  错误: {e}')
        failed += 1

print(f'\n达梦完成! 成功: {success}, 失败: {failed}')
