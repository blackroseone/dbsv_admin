# -*- coding: utf-8 -*-
"""
向量嵌入与语义检索模块
使用 sentence-transformers 实现本地向量检索
"""
import os
import threading
import numpy as np

# 懒加载模型，避免启动时就加载
_model = None
_model_lock = threading.Lock()
_model_load_failed = False  # 标记模型加载是否失败
# 支持多模型切换：默认使用 m3e-base（中文检索精度更高），可配置为 paraphrase-multilingual-MiniLM-L12-v2
MODEL_NAME = os.environ.get('DB_TOOL_EMBED_MODEL', 'moka-ai/m3e-base')


def _check_model_cached(cache_dir):
    """检查模型是否已经在本地缓存中存在"""
    import json

    # HuggingFace 缓存结构: models--<org>--<model>/snapshots/<hash>/
    # 支持两种格式：sentence-transformers 官方模型 和 第三方组织模型（如 moka-ai）
    if '/' in MODEL_NAME:
        # 第三方组织模型，如 moka-ai/m3e-base
        org, model = MODEL_NAME.split('/', 1)
        model_cache_name = f"models--{org}--{model}"
    else:
        # sentence-transformers 官方模型
        model_cache_name = f"models--sentence-transformers--{MODEL_NAME}"

    model_cache_path = os.path.join(cache_dir, model_cache_name)

    if not os.path.exists(model_cache_path):
        return False

    # 检查关键文件是否存在（model.safetensors 或 pytorch_model.bin）
    snapshots_dir = os.path.join(model_cache_path, 'snapshots')
    if not os.path.exists(snapshots_dir):
        return False

    # 遍历所有 snapshot 目录，检查是否有模型文件
    for snapshot in os.listdir(snapshots_dir):
        snapshot_path = os.path.join(snapshots_dir, snapshot)
        if not os.path.isdir(snapshot_path):
            continue

        # 检查关键模型文件
        has_model = (
            os.path.exists(os.path.join(snapshot_path, 'model.safetensors')) or
            os.path.exists(os.path.join(snapshot_path, 'pytorch_model.bin'))
        )
        has_config = os.path.exists(os.path.join(snapshot_path, 'config.json'))

        if has_model and has_config:
            return True

    return False


def _get_model():
    global _model, _model_load_failed
    if _model_load_failed:
        return None  # 已知加载失败，直接返回
    if _model is None:
        with _model_lock:
            if _model is None and not _model_load_failed:
                try:
                    from sentence_transformers import SentenceTransformer
                    cache_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', 'models')
                    os.makedirs(cache_dir, exist_ok=True)

                    # 检查模型是否已在本地缓存
                    if _check_model_cached(cache_dir):
                        print(f"[RAG] 检测到本地已有模型缓存，跳过网络下载: {MODEL_NAME}")
                        # 设置离线模式，避免连接网络
                        os.environ['TRANSFORMERS_OFFLINE'] = '1'
                        os.environ['HF_DATASETS_OFFLINE'] = '1'
                    else:
                        print(f"[RAG] 本地未找到模型缓存，将从网络下载: {MODEL_NAME}")

                    # 设置 HuggingFace 镜像，解决国内网络访问问题
                    os.environ['HF_ENDPOINT'] = 'https://hf-mirror.com'
                    # 设置较短的超时时间，避免长时间等待
                    os.environ['HF_HUB_DOWNLOAD_TIMEOUT'] = '30'  # 30秒超时
                    _model = SentenceTransformer(MODEL_NAME, cache_folder=cache_dir, local_files_only=_check_model_cached(cache_dir))
                    print(f"[RAG] 模型加载成功: {MODEL_NAME}")
                except Exception as e:
                    _model_load_failed = True
                    print(f"[RAG] 模型加载失败，将使用关键词检索: {e}")
                    return None
    return _model


def chunk_text(text, chunk_size=2000, overlap=100):
    """将文本按段落分块，每块约 chunk_size 字符，重叠 overlap 字符

    参数:
        chunk_size: 每块目标大小（默认2000字符，平衡存储和语义完整性）
        overlap: 相邻块重叠字符数（默认100，保持上下文连贯）
    """
    if not text or not text.strip():
        return []

    # 先按段落分割
    paragraphs = [p.strip() for p in text.split('\n') if p.strip()]

    chunks = []
    current_chunk = ""

    for para in paragraphs:
        if len(current_chunk) + len(para) > chunk_size and current_chunk:
            chunks.append(current_chunk.strip())
            # 保留尾部 overlap 字符作为下一块的开头
            if overlap > 0 and len(current_chunk) > overlap:
                current_chunk = current_chunk[-overlap:] + "\n" + para
            else:
                current_chunk = para
        else:
            if current_chunk:
                current_chunk += "\n" + para
            else:
                current_chunk = para

    if current_chunk.strip():
        chunks.append(current_chunk.strip())

    # 对超长块进行二次切分
    final_chunks = []
    for chunk in chunks:
        if len(chunk) <= chunk_size * 2:
            final_chunks.append(chunk)
        else:
            # 按句号/换行切分
            sentences = []
            for sep in ['\n', '。', '；', '. ', ';\n']:
                if sep in chunk:
                    sentences = [s.strip() for s in chunk.split(sep) if s.strip()]
                    break
            if not sentences:
                sentences = [chunk[i:i+chunk_size] for i in range(0, len(chunk), chunk_size)]
            sub_chunk = ""
            for sent in sentences:
                if len(sub_chunk) + len(sent) > chunk_size and sub_chunk:
                    final_chunks.append(sub_chunk.strip())
                    sub_chunk = sent
                else:
                    sub_chunk = sub_chunk + "\n" + sent if sub_chunk else sent
            if sub_chunk.strip():
                final_chunks.append(sub_chunk.strip())

    return final_chunks


def _embedding_to_bytes(embedding):
    """将 numpy 数组转为 bytes 用于 SQLite BLOB 存储"""
    return embedding.astype(np.float32).tobytes()


def _bytes_to_embedding(data):
    """将 bytes 还原为 numpy 数组"""
    return np.frombuffer(data, dtype=np.float32)


class Embedder:
    """向量嵌入管理器"""

    def embed_chunks(self, chunks):
        """批量计算文本块的嵌入向量，返回 [(chunk_index, chunk_text, embedding_bytes), ...]"""
        if not chunks:
            return []

        model = _get_model()
        if model is None:
            return []  # 模型不可用，返回空

        embeddings = model.encode(chunks, show_progress_bar=False, normalize_embeddings=True)

        result = []
        for i, (chunk, emb) in enumerate(zip(chunks, embeddings)):
            result.append((i, chunk, _embedding_to_bytes(emb)))
        return result

    def embed_query(self, query):
        """计算查询文本的嵌入向量"""
        model = _get_model()
        if model is None:
            return None
        embedding = model.encode([query], show_progress_bar=False, normalize_embeddings=True)
        return embedding[0]

    def similarity_search(self, query, db_type=None, top_k=5):
        """
        向量相似度搜索
        返回最相关的 top_k 个文本块，包含文件名和相似度分数
        """
        from db.database import get_embeddings_by_db_type, get_all_embeddings

        query_emb = self.embed_query(query)
        if query_emb is None:
            return []  # 模型不可用，返回空

        if db_type:
            rows = get_embeddings_by_db_type(db_type)
        else:
            rows = get_all_embeddings()

        if not rows:
            return []

        # 计算余弦相似度
        results = []
        for row in rows:
            stored_emb = _bytes_to_embedding(row['embedding'])
            # 已经 normalize 过，直接点积即余弦相似度
            similarity = float(np.dot(query_emb, stored_emb))
            results.append({
                'filename': row['filename'],
                'chunk_text': row['chunk_text'],
                'similarity': similarity
            })

        # 按相似度降序排列
        results.sort(key=lambda x: x['similarity'], reverse=True)
        return results[:top_k]

    def rebuild_all(self, db_type=None, extract_kg=True):
        """重建所有知识库文件的向量索引

        Args:
            db_type: 指定数据库类型，None 则重建所有
            extract_kg: 是否同时提取知识图谱实体（默认 True）
        """
        from db.database import get_all_knowledge_files, save_embeddings, update_knowledge_content
        from utils import extract_content

        model = _get_model()
        if model is None:
            return 0  # 模型不可用，返回0

        files = get_all_knowledge_files(db_type)
        count = 0
        for f in files:
            filepath = f['file_path']
            if not os.path.exists(filepath):
                continue

            # 提取内容
            content = extract_content(filepath)
            if not content:
                continue

            # 更新数据库中的文本内容
            update_knowledge_content(f['id'], content)

            # 分块并计算嵌入
            chunks = chunk_text(content)
            if not chunks:
                continue

            embeddings = self.embed_chunks(chunks)
            save_embeddings(f['id'], embeddings)
            count += 1

            # 提取知识图谱实体
            if extract_kg:
                try:
                    self._extract_knowledge_graph(f['id'], f['db_type'], content, chunks, embeddings)
                except Exception as e:
                    print(f"[RAG] 知识图谱提取失败 [{f['filename']}]: {e}")

        return count

    def _extract_knowledge_graph(self, file_id, db_type, content, chunks, embeddings):
        """从文件内容中提取知识图谱实体和关系"""
        from kg.rules import extract_all_entities, infer_relationships
        from db.kg_database import (
            save_entity, save_relationship, link_chunk_entity,
            save_entities_batch, save_relationships_batch, link_chunks_entities_batch,
            clear_entities_by_file
        )

        # 清除该文件旧的知识图谱数据
        clear_entities_by_file(file_id)

        # 1. 从完整文本提取实体（用于推断跨 chunk 关系）
        all_text_entities = extract_all_entities(content, db_type)

        # 保存全局实体
        global_entity_map = {}  # (type, normalized_name) -> entity_id
        for entity in all_text_entities:
            entity_id = save_entity(
                entity_type=entity['entity_type'],
                name=entity['name'],
                normalized_name=entity.get('normalized_name', entity['name'].lower().strip()),
                aliases=entity.get('aliases', []),
                description=entity.get('description', ''),
                properties=entity.get('properties', {}),
                source_file_id=file_id,
                confidence=entity.get('confidence', 1.0),
                extract_method=entity.get('extract_method', 'rule')
            )
            key = (entity['entity_type'], entity.get('normalized_name', entity['name'].lower().strip()))
            global_entity_map[key] = entity_id

        # 2. 从每个 chunk 提取实体并建立关联
        chunk_entity_links = []
        for i, (chunk_idx, chunk_text, emb_bytes) in enumerate(embeddings):
            # 获取 chunk 的数据库 ID
            from db.database import get_db
            conn = get_db()
            row = conn.execute(
                "SELECT id FROM embeddings WHERE file_id=? AND chunk_index=?",
                (file_id, chunk_idx)
            ).fetchone()
            if not row:
                continue
            chunk_db_id = row['id']

            # 从 chunk 文本提取实体
            chunk_entities = extract_all_entities(chunk_text, db_type)

            for entity in chunk_entities:
                key = (entity['entity_type'], entity.get('normalized_name', entity['name'].lower().strip()))
                if key in global_entity_map:
                    entity_id = global_entity_map[key]
                else:
                    # 新实体，保存到数据库
                    entity_id = save_entity(
                        entity_type=entity['entity_type'],
                        name=entity['name'],
                        normalized_name=entity.get('normalized_name', entity['name'].lower().strip()),
                        aliases=entity.get('aliases', []),
                        description=entity.get('description', ''),
                        properties=entity.get('properties', {}),
                        source_file_id=file_id,
                        source_chunk_id=chunk_db_id,
                        confidence=entity.get('confidence', 1.0),
                        extract_method=entity.get('extract_method', 'rule')
                    )
                    global_entity_map[key] = entity_id

                # 建立 chunk-实体关联
                chunk_entity_links.append((chunk_db_id, entity_id, 1))

        # 批量保存 chunk-实体关联
        if chunk_entity_links:
            link_chunks_entities_batch(chunk_entity_links)

        # 3. 推断关系
        relationships = infer_relationships(all_text_entities, content)

        # 保存关系
        for rel in relationships:
            from_key = (rel['from_entity'].get('entity_type'), rel['from_entity'].get('normalized_name', rel['from_entity']['name'].lower()))
            to_key = (rel['to_entity'].get('entity_type'), rel['to_entity'].get('normalized_name', rel['to_entity']['name'].lower()))

            if from_key in global_entity_map and to_key in global_entity_map:
                save_relationship(
                    from_entity_id=global_entity_map[from_key],
                    to_entity_id=global_entity_map[to_key],
                    relation_type=rel['relation_type'],
                    confidence=rel.get('confidence', 0.8),
                    source_file_id=file_id,
                    extract_method=rel.get('extract_method', 'rule')
                )

        print(f"[RAG] 知识图谱提取完成 [{file_id}]: {len(global_entity_map)} 实体, {len(relationships)} 关系")

    def rebuild_single(self, file_id, db_type, filepath, extract_kg=True):
        """重建单个文件的向量索引"""
        from db.database import save_embeddings, update_knowledge_content
        from utils import extract_content

        model = _get_model()
        if model is None:
            return False

        if not os.path.exists(filepath):
            return False

        # 提取内容
        content = extract_content(filepath)
        if not content:
            return False

        # 更新数据库中的文本内容
        update_knowledge_content(file_id, content)

        # 分块并计算嵌入
        chunks = chunk_text(content)
        if not chunks:
            return False

        embeddings = self.embed_chunks(chunks)
        save_embeddings(file_id, embeddings)

        # 提取知识图谱实体
        if extract_kg:
            try:
                self._extract_knowledge_graph(file_id, db_type, content, chunks, embeddings)
            except Exception as e:
                print(f"[RAG] 知识图谱提取失败 [{filepath}]: {e}")

        return True
