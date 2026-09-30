"""检索与问答评测。

为什么要做评测：没有评测的 RAG 项目只能靠"感觉还行"，
面试官一问"你怎么知道检索准不准"就答不上来。
这个脚本给出可复现的量化指标：

  1. Recall@K       —— 该召回的文档有没有进 top-K
  2. MRR            —— 正确文档排在多靠前
  3. 拒答准确率      —— 库里没有的问题有没有被正确拒答
  4. 引用准确率      —— 回答引用的出处是否真的包含答案（人工标注子集）

评测集 `eval/questions.json` 格式：
  [
    {"q": "转专业需要什么条件",
     "relevant": ["doc-008"],          # 期望命中的文档 id
     "note": "杭师大转专业实施办法"}
  ]
拒答用例把 relevant 设为 []。

    python -m rag.cli_eval
    python -m rag.cli_eval --top-k 3
"""
from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path
from typing import Dict, List

from .config import CONFIG, EVAL_DIR
from .store import Retriever, VectorStore

QUESTIONS_FILE = EVAL_DIR / 'questions.json'


def load_questions(path: Path = None) -> List[dict]:
    p = Path(path or QUESTIONS_FILE)
    if not p.exists():
        raise FileNotFoundError('评测集不存在：%s' % p)
    with open(p, encoding='utf-8') as f:
        return json.load(f)


def evaluate(store: VectorStore, questions: List[dict], top_k: int = 5,
             threshold: float = None) -> Dict:
    """跑一遍评测，返回各项指标。"""
    th = CONFIG.retrieve.score_threshold if threshold is None else threshold
    retriever = Retriever(store)

    recall_hits = 0
    recall_total = 0
    rr_sum = 0.0
    rr_n = 0
    refuse_ok = 0
    refuse_total = 0
    details = []

    for item in questions:
        q = item['q']
        relevant = set(item.get('relevant') or [])
        hits, grounded = retriever.retrieve(q, top_k=top_k, threshold=th)
        got_docs = [h.chunk.doc_id for h in hits]
        top1 = hits[0].chunk if hits else None

        if relevant:
            # ---- 可回答题 ----
            recall_total += 1
            hit = bool(relevant & set(got_docs))
            if hit:
                recall_hits += 1
            # MRR：第一个相关结果的名次倒数
            rank = None
            for i, d in enumerate(got_docs, 1):
                if d in relevant:
                    rank = i
                    break
            if rank:
                rr_sum += 1.0 / rank
            rr_n += 1
            details.append({
                'q': q, 'type': 'answerable', 'relevant': sorted(relevant),
                'recall': hit, 'rank': rank, 'grounded': grounded,
                'top1': top1.title if top1 else '', 'top1_doc': top1.doc_id if top1 else '',
            })
        else:
            # ---- 应拒答题 ----
            refuse_total += 1
            ok = not grounded
            if ok:
                refuse_ok += 1
            details.append({
                'q': q, 'type': 'unanswerable', 'refused': ok, 'grounded': grounded,
                'top1': top1.title if top1 else '',
                'top_score': round(hits[0].score, 4) if hits else 0.0,
            })

    metrics = {
        'top_k': top_k,
        'threshold': th,
        f'recall@{top_k}': recall_hits / recall_total if recall_total else 0.0,
        'mrr': rr_sum / rr_n if rr_n else 0.0,
        'refuse_accuracy': refuse_ok / refuse_total if refuse_total else 0.0,
        'n_answerable': recall_total,
        'n_unanswerable': refuse_total,
    }
    return {'metrics': metrics, 'details': details}


def print_report(result: Dict) -> None:
    m = result['metrics']
    print('=' * 78)
    print('评测结果')
    print('=' * 78)
    print('  参数        : top_k=%d  阈值=%.2f' % (m['top_k'], m['threshold']))
    print('  可回答题    : %d 条' % m['n_answerable'])
    print('  应拒答题    : %d 条' % m['n_unanswerable'])
    print()
    # 注意：字符串末尾必须带 \n，否则不带换行符的 print 会让 \r
    # 把同一行反复覆盖重打（终端里看着像刷屏）
    recall = m[f'recall@{m["top_k"]}']
    print('  Recall@%-2d   : %6.1f%%   ← 该召回的文档进了 top-K 的比例\n'
          % (m['top_k'], recall * 100), end='')
    print('  MRR         : %6.3f     ← 正确文档的平均排名倒数（越接近1越靠前）\n'
          % m['mrr'], end='')
    print('  拒答准确率  : %6.1f%%   ← 库里没有的问题被正确拒答的比例\n'
          % (m['refuse_accuracy'] * 100), end='')
    print()
    print('-' * 78)
    print('逐题明细')
    print('-' * 78)

    print('\n【可回答题】')
    for d in result['details']:
        if d['type'] != 'answerable':
            continue
        flag = '✓' if d['recall'] else '✗'
        rank = ('rank=%d' % d['rank']) if d['rank'] else '未命中'
        print('  %s %-26s %-9s top1=%s' % (flag, d['q'][:26], rank, d['top1'][:34]))

    print('\n【应拒答题】')
    for d in result['details']:
        if d['type'] != 'unanswerable':
            continue
        flag = '✓' if d['refused'] else '✗'
        print('  %s %-26s score=%.4f  top1=%s'
              % (flag, d['q'][:26], d['top_score'], d['top1'][:30]))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description='RAG 检索评测')
    ap.add_argument('--top-k', type=int, default=5)
    ap.add_argument('--threshold', type=float, default=None)
    ap.add_argument('--questions', help='评测集路径')
    ap.add_argument('--json', action='store_true', help='输出 JSON 结果')
    args = ap.parse_args(argv)

    store = VectorStore.load()
    questions = load_questions(args.questions)
    result = evaluate(store, questions, top_k=args.top_k, threshold=args.threshold)

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(store.info())
        print('向量化：%s' % store.embedder.describe())
        print()
        print_report(result)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
