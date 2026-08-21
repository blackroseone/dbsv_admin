import sys; sys.stdout.reconfigure(encoding='utf-8')
import os
import sqlite3

# Add project root to path
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(BASE_DIR)

from db.database import get_db, save_embeddings, get_knowledge_file_by_id
from utils import extract_content
from rag.embedder import chunk_text, Embedder

DB_PATH = os.path.join(BASE_DIR, 'data', 'db_tool.db')
FILE_IDS = [54, 55, 56, 57, 58]

def main():
    # Step 1: Delete existing embeddings
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys=ON")
    placeholders = ','.join('?' * len(FILE_IDS))
    cursor = conn.execute(f"DELETE FROM embeddings WHERE file_id IN ({placeholders})", FILE_IDS)
    deleted = cursor.rowcount
    conn.commit()
    conn.close()
    print(f"[1/3] 已删除现有 embeddings: {deleted} 条")

    # Step 2: Process each file
    embedder = Embedder()
    total_chunks = 0
    processed = 0
    failed = 0

    for file_id in FILE_IDS:
        try:
            # Get file info
            file_info = get_knowledge_file_by_id(file_id)
            if not file_info:
                print(f"  [跳过] file_id={file_id}: 数据库中不存在")
                failed += 1
                continue

            filepath = file_info['file_path']
            filename = file_info['filename']

            if not os.path.exists(filepath):
                print(f"  [跳过] file_id={file_id}, {filename}: 文件不存在 ({filepath})")
                failed += 1
                continue

            # Extract content
            content = extract_content(filepath)
            if not content or content.startswith('[解析失败'):
                print(f"  [跳过] file_id={file_id}, {filename}: 内容提取失败 ({content[:50]}...)")
                failed += 1
                continue

            content_len = len(content)
            print(f"  [处理] file_id={file_id}, {filename}: 提取 {content_len} 字符")

            # Chunk text
            chunks = chunk_text(content)
            if not chunks:
                print(f"  [跳过] file_id={file_id}, {filename}: 分块结果为空")
                failed += 1
                continue

            print(f"         分块: {len(chunks)} 个 chunks")

            # Generate embeddings
            embeddings = embedder.embed_chunks(chunks)
            if not embeddings:
                print(f"  [跳过] file_id={file_id}, {filename}: 嵌入生成失败（模型不可用）")
                failed += 1
                continue

            # Save embeddings
            save_embeddings(file_id, embeddings)
            total_chunks += len(chunks)
            processed += 1
            print(f"  [完成] file_id={file_id}, {filename}: 保存 {len(embeddings)} 个 embeddings")

        except Exception as e:
            print(f"  [错误] file_id={file_id}: {str(e)}")
            failed += 1

    # Step 3: Summary
    print(f"\n[完成] 处理结果:")
    print(f"  - 成功: {processed} 个文件")
    print(f"  - 失败: {failed} 个文件")
    print(f"  - 总 chunks: {total_chunks}")

    # Verify
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    for file_id in FILE_IDS:
        row = conn.execute(
            "SELECT COUNT(*) as cnt FROM embeddings WHERE file_id=?", (file_id,)
        ).fetchone()
        print(f"  - file_id={file_id}: embeddings={row['cnt']}")
    conn.close()

if __name__ == '__main__':
    main()
