import sys
sys.stdout.reconfigure(encoding='utf-8')

import sqlite3
import os
from utils import extract_content
from rag.embedder import chunk_text, Embedder
from db.database import save_embeddings

conn = sqlite3.connect('data/db_tool.db')
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

# 获取剩余3个需要重建的Oracle文件
cursor.execute('SELECT id, filename, file_path, LENGTH(content_text) as content_len FROM knowledge_files WHERE id IN (60,63,65) ORDER BY id')
files = cursor.fetchall()

print(f'Remaining files: {len(files)}')

embedder = Embedder()
total = 0

for f in files:
    fid = f['id']
    fname = f['filename']
    fpath = f['file_path']

    print(f'\n[{fid}] {fname}')

    if not os.path.exists(fpath):
        print('  File not found')
        continue

    try:
        cursor.execute('DELETE FROM embeddings WHERE file_id=?', (fid,))
        conn.commit()

        content = extract_content(fpath)
        if not content:
            print('  No content')
            continue

        chunks = chunk_text(content)
        print(f'  chunks={len(chunks)}')

        if not chunks:
            continue

        embs = embedder.embed_chunks(chunks)
        if embs:
            save_embeddings(fid, embs)
            total += len(embs)
            print(f'  embeddings={len(embs)}')
        else:
            print('  Failed')
    except Exception as e:
        print(f'  Error: {e}')

conn.close()
print(f'\nTotal: {total}')
