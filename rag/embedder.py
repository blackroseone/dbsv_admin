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


def _resolve_device():
    """根据环境变量 DB_TOOL_EMBED_DEVICE 决定运行设备：auto/cuda/cpu，默认 auto
    auto 表示：有可用 CUDA 则用 GPU，否则用 CPU（内网无 GPU 服务器安全回退）
    """
    requested = os.environ.get('DB_TOOL_EMBED_DEVICE', 'auto').strip().lower()
    if requested == 'cuda':
        return 'cuda'
    if requested == 'cpu':
        return 'cpu'
    try:
        import torch
        if torch.cuda.is_available():
            return 'cuda'
    except ImportError:
        pass
    return 'cpu'


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
                    device = _resolve_device()
                    _model = SentenceTransformer(MODEL_NAME, cache_folder=cache_dir,
                                                 local_files_only=_check_model_cached(cache_dir),
                                                 device=device)
                    print(f"[RAG] 模型加载成功: {MODEL_NAME} (device={device})")
                except Exception as e:
                    _model_load_failed = True
                    print(f"[RAG] 模型加载失败，将使用关键词检索: {e}")
                    return None
    return _model


def chunk_text(text, chunk_size=None, overlap=None):
    """将文本按段落分块，每块约 chunk_size 字符，重叠 overlap 字符

    参数:
        chunk_size: 每块目标大小（默认取 config.CHUNK_SIZE，当前500）
        overlap: 相邻块重叠字符数（默认取 config.CHUNK_OVERLAP，当前50）
    """
    if chunk_size is None or overlap is None:
        from config import CHUNK_SIZE, CHUNK_OVERLAP
        if chunk_size is None:
            chunk_size = CHUNK_SIZE
        if overlap is None:
            overlap = CHUNK_OVERLAP
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


def _is_llm_kg_enabled():
    """检查是否启用了 LLM 辅助知识图谱提取"""
    try:
        from db.database import get_config
        return bool(get_config('kg_llm_extract', False))
    except Exception:
        return False


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

    def is_available(self):
        """模型是否可用：用于区分「模型不可用导致检索为空」与「模型可用但无命中」"""
        return _get_model() is not None

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
                'chunk_id': row['id'],
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
        """从文件内容中提取知识图谱实体和关系（规则 + 可选 LLM 辅助）"""
        from kg.rules import extract_all_entities, infer_relationships
        from db.kg_database import (
            save_entities_batch, save_relationships_batch,
            link_chunks_entities_batch, clear_entities_by_file
        )

        # 清除该文件旧的知识图谱数据
        clear_entities_by_file(file_id)

        # 1. 从完整文本提取实体（规则），用于推断跨 chunk 关系
        all_text_entities = extract_all_entities(content, db_type)

        # 1.5 LLM 辅助提取（如果启用），补充规则遗漏的实体和关系
        llm_relationships = []
        if _is_llm_kg_enabled():
            try:
                from kg.llm_extractor import (
                    extract_entities_and_relations_multi_segment,
                    _merge_entities, _merge_relationships
                )
                from db.database import get_config
                seg_size = int(get_config('kg_llm_segment_size', 3000))
                max_segs = int(get_config('kg_llm_max_segments', 5))
                llm_result = extract_entities_and_relations_multi_segment(
                    content, db_type,
                    segment_size=seg_size, max_segments=max_segs
                )
                llm_entities = llm_result.get('entities', [])
                llm_relationships = llm_result.get('relationships', [])
                if llm_entities:
                    all_text_entities = _merge_entities(all_text_entities, llm_entities)
                    print(f"[RAG] LLM 辅助提取: +{len(llm_entities)} 实体(合并后), "
                          f"+{len(llm_relationships)} 关系")
            except Exception as e:
                print(f"[RAG] LLM 辅助提取失败: {e}")

        # 2. 收集全部待保存实体（全量 + 各 chunk，按 key 去重）
        #    实体按 (type, normalized_name) 去重，一次批量保存，避免逐条事务
        def _payload(entity, source_chunk_id=None):
            return {
                'entity_type': entity['entity_type'],
                'name': entity['name'],
                'normalized_name': entity.get('normalized_name', entity['name'].lower().strip()),
                'aliases': entity.get('aliases', []),
                'description': entity.get('description', ''),
                'properties': entity.get('properties', {}),
                'source_file_id': file_id,
                'source_chunk_id': source_chunk_id,
                'confidence': entity.get('confidence', 1.0),
                'extract_method': entity.get('extract_method', 'rule'),
            }

        def _key(entity):
            return (entity['entity_type'],
                    entity.get('normalized_name', entity['name'].lower().strip()))

        entity_payloads = []
        entity_payload_index = {}  # key -> index in entity_payloads
        for entity in all_text_entities:
            key = _key(entity)
            if key not in entity_payload_index:
                entity_payload_index[key] = len(entity_payloads)
                entity_payloads.append(_payload(entity))

        # 一次性取回该文件所有 chunk 的 id，避免逐 chunk 查询
        from db.database import get_db
        conn = get_db()
        chunk_id_map = {}
        for row in conn.execute(
                "SELECT id, chunk_index FROM embeddings WHERE file_id=?", (file_id,)
        ).fetchall():
            chunk_id_map[row['chunk_index']] = row['id']

        chunk_entity_links = []  # [(chunk_db_id, key), ...]，保存后映射为实体 id
        for i, (chunk_idx, chunk_text, emb_bytes) in enumerate(embeddings):
            chunk_db_id = chunk_id_map.get(chunk_idx)
            if not chunk_db_id:
                continue

            # 从 chunk 文本提取实体（仅规则，chunk 太短不适合 LLM）
            chunk_entities = extract_all_entities(chunk_text, db_type)
            for entity in chunk_entities:
                key = _key(entity)
                if key not in entity_payload_index:
                    entity_payload_index[key] = len(entity_payloads)
                    entity_payloads.append(_payload(entity, chunk_db_id))
                chunk_entity_links.append((chunk_db_id, key))

        # 3. 批量保存实体，得到 key -> id 映射
        entity_id_map = save_entities_batch(entity_payloads)

        # 4. 批量保存 chunk-实体关联
        if chunk_entity_links:
            links = [(cid, entity_id_map[key], 1)
                     for cid, key in chunk_entity_links if key in entity_id_map]
            if links:
                link_chunks_entities_batch(links)

        # 5. 推断关系（规则）并合并 LLM 关系，批量保存
        relationships = infer_relationships(all_text_entities, content)

        # 合并 LLM 关系（如有）
        if llm_relationships:
            from kg.llm_extractor import _merge_relationships
            relationships = _merge_relationships(relationships, llm_relationships)

        rel_payloads = []
        for rel in relationships:
            # LLM 关系的 from_entity/to_entity 为字符串，需转为 key
            if isinstance(rel.get('from_entity'), dict):
                from_key = (rel['from_entity'].get('entity_type'),
                            rel['from_entity'].get('normalized_name',
                                                   rel['from_entity']['name'].lower()))
            else:
                from_type = rel.get('from_type', '')
                from_name = rel.get('from_entity', '').lower().strip()
                from_key = (from_type, from_name)

            if isinstance(rel.get('to_entity'), dict):
                to_key = (rel['to_entity'].get('entity_type'),
                          rel['to_entity'].get('normalized_name',
                                               rel['to_entity']['name'].lower()))
            else:
                to_type = rel.get('to_type', '')
                to_name = rel.get('to_entity', '').lower().strip()
                to_key = (to_type, to_name)

            if from_key in entity_id_map and to_key in entity_id_map:
                rel_payloads.append({
                    'from_entity_id': entity_id_map[from_key],
                    'to_entity_id': entity_id_map[to_key],
                    'relation_type': rel['relation_type'],
                    'confidence': rel.get('confidence', 0.8),
                    'source_file_id': file_id,
                    'extract_method': rel.get('extract_method', 'rule'),
                })

        save_relationships_batch(rel_payloads)

        print(f"[RAG] 知识图谱提取完成 [{file_id}]: {len(entity_id_map)} 实体, {len(relationships)} 关系")

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
