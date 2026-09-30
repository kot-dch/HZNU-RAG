"""切分预览：人工检查切分质量。

    python -m rag.cli_chunks
    python -m rag.cli_chunks --doc doc-005 --show 3
"""
from __future__ import annotations

import argparse
import sys

from .chunker import build_chunks, stats, load_document
from .config import CONFIG, DOCS_DIR, describe


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description='预览文档切分结果')
    ap.add_argument('--doc', help='只看某个文档，如 doc-005')
    ap.add_argument('--show', type=int, default=2, help='每个文档展示几块（默认 2）')
    ap.add_argument('--docs-dir', help='语料目录，默认取配置')
    args = ap.parse_args(argv)

    print(describe())
    print()

    chunks = build_chunks(args.docs_dir)
    print(stats(chunks))
    print()

    # 按文档分组展示
    by_doc = {}
    for c in chunks:
        by_doc.setdefault(c.doc_id, []).append(c)

    docs = sorted(by_doc)
    if args.doc:
        docs = [d for d in docs if d == args.doc]
        if not docs:
            print('未找到文档 %s' % args.doc, file=sys.stderr)
            return 1

    print('=' * 78)
    for doc_id in docs:
        group = by_doc[doc_id]
        first = group[0]
        print('[%s] %s' % (doc_id, first.title))
        print('    栏目=%s  块数=%d  来源=%s' % (first.section, len(group), first.url))
        for c in group[:args.show]:
            snippet = c.text.replace('\n', ' / ')
            if len(snippet) > 150:
                snippet = snippet[:150] + '…'
            print('    %-14s (%4d 字) %s' % (c.chunk_id, len(c.text), snippet))
        if len(group) > args.show:
            print('    … 其余 %d 块省略' % (len(group) - args.show))
        print('-' * 78)

    return 0


if __name__ == '__main__':
    raise SystemExit(main())
