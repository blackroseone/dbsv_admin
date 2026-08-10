import sys; sys.stdout.reconfigure(encoding='utf-8')
import os
import sys

# 添加项目根目录到路径
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

from db.database import get_db, transaction, get_knowledge_file_by_id, update_knowledge_content, save_embeddings
from utils import extract_content
from rag.embedder import chunk_text, Embedder

# 需要重建的文件ID
FILE_IDS = [59, 60, 63, 65]

# 第一步：删除旧embeddings
print("=" * 60)
print("步骤1：删除旧embeddings")
print("=" * 60)
conn = get_db()
conn.execute("DELETE FROM embeddings WHERE file_id IN (59,60,63,65)")
conn.commit()
print("已删除 file_id IN (59,60,63,65) 的旧embeddings")

# 第二步：逐个处理文件
print("\n" + "=" * 60)
print("步骤2：逐个处理文件生成新embeddings")
print("=" * 60)

embedder = Embedder()
total_chunks = 0

for file_id in FILE_IDS:
    print(f"\n--- 处理文件 ID={file_id} ---")
    try:
        # 获取文件信息
        file_info = get_knowledge_file_by_id(file_id)
        if not file_info:
            print(f"  [跳过] 文件 ID={file_id} 不存在")
            continue

        filename = file_info['filename']
        filepath = file_info['file_path']
        print(f"  文件名: {filename}")
        print(f"  文件路径: {filepath}")

        # 检查文件是否存在
        if not os.path.exists(filepath):
            print(f"  [跳过] 文件不存在: {filepath}")
            continue

        # 提取内容
        print(f"  正在提取内容...")
        content = extract_content(filepath)
        content_len = len(content) if content else 0
        print(f"  内容长度: {content_len} 字符")

        if not content or not content.strip():
            print(f"  [跳过] 内容为空")
            continue

        # 更新数据库中的文本内容
        update_knowledge_content(file_id, content)
        print(f"  已更新数据库中的content_text")

        # 分块（使用默认参数 chunk_size=2000, overlap=100）
        print(f"  正在分块...")
        chunks = chunk_text(content)
        chunk_count = len(chunks)
        print(f"  分块数量: {chunk_count}")

        if not chunks:
            print(f"  [跳过] 分块结果为空")
            continue

        # 生成嵌入向量
        print(f"  正在生成嵌入向量...")
        embeddings = embedder.embed_chunks(chunks)
        emb_count = len(embeddings)
        print(f"  嵌入向量数量: {emb_count}")

        if not embeddings:
            print(f"  [跳过] 嵌入向量生成失败（模型可能不可用）")
            continue

        # 保存到数据库
        save_embeddings(file_id, embeddings)
        print(f"  [成功] 已保存 {emb_count} 个嵌入向量")

        total_chunks += chunk_count

    except Exception as e:
        print(f"  [错误] 处理失败: {e}")
        import traceback
        traceback.print_exc()
        continue

print("\n" + "=" * 60)
print("重建完成")
print("=" * 60)
print(f"总 chunks 数量: {total_chunks}")
