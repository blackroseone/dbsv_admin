# -*- coding: utf-8 -*-
"""
临时只读诊断：用真实 m3e-base tokenizer 精确统计知识库所有向量分块的 token 长度，
确认 500 字符分块是否导致 token 超 m3e 的 512 上限（超出的部分会被模型静默截断，
但 chunk_text 仍存全文 -> 向量与文本错配）。

用法（在能加载模型的运行环境执行，例如你启动 app.py 的那个终端）：
    cd D:\Projects\dbsv_admin
    python temp_scripts\diag_chunk_tokens.py

说明：
- 仅读取 kb_embeddings 表，不写库、不重建索引；
- 复用 rag/embedder._get_model() 的真实 tokenizer（应用已加载则秒出，否则现场加载）；
- token 数含 [CLS]/[SEP]，m3e max_position_embeddings=512。
"""
import sys
sys.stdout.reconfigure(encoding='utf-8')

import os
import sqlite3
import collections

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

from rag.embedder import _get_model  # 复用已加载的真实 tokenizer


def main():
    model = _get_model()
    if model is None:
        print('[ERROR] 嵌入模型不可用（_get_model 返回 None），无法精确统计 token。'
              '请在已配置并可加载 m3e-base 权重的运行环境运行。')
        return

    tok = model.tokenizer
    max_len = getattr(tok, 'model_max_length', 512)
    print(f'真实 tokenizer 加载 OK, model_max_length = {max_len}')

    db_path = os.path.join(BASE_DIR, 'data', 'db_tool.db')
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    rows = conn.execute(
        "SELECT e.id, e.file_id, e.chunk_text, k.db_type "
        "FROM kb_embeddings e JOIN kb_files k ON e.file_id=k.id"
    ).fetchall()
    print(f'总分块数: {len(rows)}')

    counts = []
    over = []  # (token_len, char_len, db_type, file_id, chunk_index)
    # 批量编码（truncation=False：不截断，拿到真实 token 数）
    texts = [r['chunk_text'] or '' for r in rows]
    enc = tok(texts, add_special_tokens=True, truncation=False)
    for i, ids in enumerate(enc['input_ids']):
        tl = len(ids)
        counts.append(tl)
        if tl > 512:
            over.append((tl, len(texts[i]), rows[i]['db_type'], rows[i]['file_id']))

    def bucket(n):
        if n <= 200: return '<=200'
        if n <= 400: return '201-400'
        if n <= 500: return '401-500'
        if n <= 512: return '501-512'
        if n <= 600: return '513-600'
        return '>600'

    b = collections.Counter(bucket(c) for c in counts)
    print('\n=== 真实 token 长度分布 (m3e-base 真实 tokenizer) ===')
    for k in ['<=200', '201-400', '401-500', '501-512', '513-600', '>600']:
        print(f'  {k:10s} {b.get(k, 0)}')

    print(f'\n真实 token 均值: {sum(counts)/len(counts):.1f}')
    print(f'真实 token 中位数: {sorted(counts)[len(counts)//2]}')
    print(f'真实 token 最大: {max(counts)}')

    print(f'\n⚠️ 真实 token > 512 的块 (超 m3e 编码上限, embedding 仅编码前512token): '
          f'{len(over)} 块 ({100*len(over)/len(rows):.3f}%)')
    bt = collections.Counter(o[2] for o in over)
    print('  按数据库类型:', dict(bt.most_common()))

    if over:
        print('\n最大 token 块抽样 (token / 字符 / 类型 / file_id):')
        for tl, cl, ty, fid in sorted(over, key=lambda x: -x[0])[:10]:
            print(f'  {ty:10s} token={tl} 字符={cl} file_id={fid}')

    # 边界截断分析：块末是否落在句末标点
    SENT_END = set('。！？.!?\n')
    not_end = sum(1 for r in rows
                  if (r['chunk_text'] or '').strip()
                  and (r['chunk_text'].rstrip()[-1] not in SENT_END))
    print(f'\n块末非句末标点 (段落边界硬切, 可能句子中间切断): '
          f'{not_end} 块 ({100*not_end/len(rows):.1f}%)')

    conn.close()
    print('\n[完成] 本脚本只读，未写入任何数据。')


if __name__ == '__main__':
    main()
