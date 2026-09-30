"""检索调试：不调大模型，只看检索到了什么。

调 RAG 时最重要的一步——**先把检索调对，再谈生成**。
如果检索召回的就是无关内容，提示词写得再好也没用。

    python -m rag.cli_search "转专业需要什么条件"
    python -m rag.cli_search "奖学金怎么申请" -k 3
    python -m rag.cli_search --batch           # 跑一组预设问题
"""
from __future__ import annotations

import argparse

from .config import describe
from .store import Retriever, VectorStore

# 用真实校园场景的高频问题探检索质量
BATCH_QUERIES = [
    '转专业需要什么条件',
    '奖学金怎么申请',
    '助学贷款怎么办理',
    '体质测试在哪里测',
    '毕业设计什么时候开始',
    '创新实践学分怎么获得',
    '评奖评优要看什么',
    '请假和考勤有什么规定',
    '校园卡丢了怎么办',
    '宿舍可以住到什么时候',
]


def run_one(store: VectorStore, query: str, k: int, threshold: float, show_text: bool):
    retriever = Retriever(store)
    hits, grounded = retriever.retrieve(query, top_k=k, threshold=threshold)
    print('提问：%s' % query)
    if not grounded:
        print('  ✗ 无依据（所有结果低于阈值 %.2f）→ 应触发拒答' % threshold)
        # 展示一下实际最高分，方便判断阈值是否定得太高
        raw = store.search(query, top_k=1)
        if raw:
            print('    最高相似度仅 %.4f：%s' % (raw[0].score, raw[0].chunk.title[:40]))
        print()
        return
    print('  ✓ 命中 %d 条' % len(hits))
    for i, h in enumerate(hits, 1):
        c = h.chunk
        print('  %d) %.4f  %s  [%s#%d]' % (i, h.score, c.title[:44], c.doc_id, c.chunk_index))
        if show_text:
            body = h.chunk.text.replace('\n', ' ')
            print('       %s' % (body[:120] + ('…' if len(body) > 120 else '')))
    print()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description='RAG 检索调试')
    ap.add_argument('query', nargs='*', help='查询问题')
    ap.add_argument('-k', '--top-k', type=int, default=5)
    ap.add_argument('-t', '--threshold', type=float, default=0.35)
    ap.add_argument('--batch', action='store_true', help='跑一组预设问题')
    ap.add_argument('--text', action='store_true', help='显示片段内容')
    args = ap.parse_args(argv)

    store = VectorStore.load()
    print(store.info())
    print('  向量化：%s' % store.embedder.describe())
    print()

    if args.batch or not args.query:
        queries = BATCH_QUERIES
    else:
        queries = [' '.join(args.query)]

    for q in queries:
        run_one(store, q, args.top_k, args.threshold, args.text)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
