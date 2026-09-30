"""语料清洗预览：看模板噪声被清掉了多少、标题抢救得对不对。

    python -m rag.cli_clean
"""
from __future__ import annotations

import argparse

from .cleaner import clean_corpus
from .config import DOCS_DIR, describe


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description='预览语料清洗结果')
    ap.add_argument('--docs-dir', help='语料目录')
    ap.add_argument('--show', type=int, default=30, help='展示多少篇的标题')
    ap.add_argument('--ratio', type=float, default=0.25,
                    help='判定为模板行的文档出现比例阈值')
    args = ap.parse_args(argv)

    print(describe())
    print()

    docs, diag = clean_corpus(DOCS_DIR if not args.docs_dir else __import__('pathlib').Path(args.docs_dir),
                              min_doc_ratio=args.ratio)
    print()
    print('=' * 78)
    print('清洗后标题与开头（用于检查标题是否抢救成功）')
    print('=' * 78)
    for d in docs[:args.show]:
        head = d['text'].split('\n')
        head = head[0][:56] if head else ''
        print('%s  %s' % (d['doc_id'], d['title'][:52]))
        print('          首行：%s' % head)
    print()
    print('若上面出现"课程思政教学研究中心""创新创业学分"这类，说明模板行没清干净。')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
