"""构建向量索引。

    python -m rag.cli_index
    python -m rag.cli_index --no-clean     # 不清洗语料（用于对比清洗效果）
"""
from __future__ import annotations

import argparse
import time

from .chunker import build_chunks, stats
from .config import ARTIFACT_DIR, describe
from .store import VectorStore


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description='构建 RAG 向量索引')
    ap.add_argument('--docs-dir', help='语料目录')
    ap.add_argument('--out', help='索引输出目录')
    ap.add_argument('--no-clean', action='store_true', help='跳过语料清洗')
    args = ap.parse_args(argv)

    print(describe())
    print()

    t0 = time.time()
    chunks = build_chunks(args.docs_dir, use_cleaner=not args.no_clean, verbose=True)
    if not chunks:
        print('没有切出任何片段，请检查语料目录', flush=True)
        return 1
    print()
    print(stats(chunks))

    print()
    print('向量化 %d 个片段…' % len(chunks), flush=True)
    t1 = time.time()
    store = VectorStore.build(chunks)
    t2 = time.time()

    out = store.save(args.out)
    print('  向量化耗时：%.2f 秒' % (t2 - t1))
    print('  %s' % store.info())
    print('  %s' % store.embedder.describe())
    print('  索引写入：%s' % out)
    print()
    print('总耗时 %.2f 秒' % (time.time() - t0))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
