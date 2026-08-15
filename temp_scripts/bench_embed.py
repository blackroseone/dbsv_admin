# -*- coding: utf-8 -*-
"""向量嵌入性能基准测试：CPU vs GPU

生成 N 段 ~500 字的中文运维文本，分别用 CPU / GPU（若可用）编码，
对比 chunks/sec。用于验证分块 500 后 GPU 加速效果。

用法:
    python temp_scripts/bench_embed.py [--chunks 2000]
"""
import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ['TRANSFORMERS_OFFLINE'] = '1'


def make_chunks(n):
    """生成 N 段中文运维文本（~500 字/段，模拟分块 500 的知识库）"""
    base = ('MySQL 数据库参数 innodb_buffer_pool_size 决定 InnoDB 缓冲池大小，'
            '对数据库性能影响显著。当遇到 ORA-00600 或 ERROR 1045 等错误时，'
            '需要检查数据库参数配置与用户权限。达梦数据库支持主备集群部署，'
            '通过守护进程实现数据同步与故障切换。表空间使用率超过 80% 时应'
            '及时扩容，避免数据库因空间不足而停止服务。')
    chunks = []
    for i in range(n):
        # 循环拼接 base，凑 ~500 字，末尾带序号增加多样性
        rep = 500 // len(base) + 1
        text = (base * rep)[:480]
        chunks.append(f'{text} 序号{i:05d}')
    return chunks


def bench(device, chunks, batch_size=64):
    """在指定设备上编码 chunks，返回 chunks/sec"""
    import rag.embedder as emb
    # 重置模型单例，强制按目标设备重载
    emb._model = None
    emb._model_load_failed = False
    os.environ['DB_TOOL_EMBED_DEVICE'] = device

    model = emb._get_model()
    if model is None:
        return None

    # 预热（小批次）
    model.encode(chunks[:8], show_progress_bar=False, normalize_embeddings=True)

    t0 = time.time()
    model.encode(chunks, show_progress_bar=False, normalize_embeddings=True, batch_size=batch_size)
    dt = time.time() - t0
    return len(chunks) / dt


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--chunks', type=int, default=2000)
    args = parser.parse_args()

    chunks = make_chunks(args.chunks)
    print(f'生成 {len(chunks)} 段文本（~500 字/段）')

    # CPU
    print('--- 测试 CPU ---')
    cpu_rate = bench('cpu', chunks)
    print(f'CPU: {cpu_rate:.1f} chunks/s')

    # GPU
    try:
        import torch
        if torch.cuda.is_available():
            print(f'--- 测试 GPU ({torch.cuda.get_device_name(0)}) ---')
            gpu_rate = bench('cuda', chunks)
            print(f'GPU: {gpu_rate:.1f} chunks/s')
            if cpu_rate and gpu_rate:
                print(f'加速比: {gpu_rate / cpu_rate:.2f}x')
        else:
            print('CUDA 不可用，跳过 GPU 测试')
    except Exception as e:
        print(f'GPU 测试失败: {e}')


if __name__ == '__main__':
    main()
