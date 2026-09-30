"""诊断：分数间隔能否区分"真命中"与"噪声命中"。

覆盖率闸门有个绕不过去的短板：库外问题里的字可能与文档正文里的常用字重合。
例如"怎么补办学生证"的二元组「学生」「生证」在《平安保险须知》正文中
（"新生入学""学生平安保险"）确实出现，覆盖率虚高到 0.50，闸门失效。

换个角度：真命中时 top-1 通常明显甩开后面的候选（分布陡峭），
噪声命中时所有片段分数挤在一起（分布平坦）。

这个脚本量化两个统计量的区分能力：
  · rel_margin = (top1 - top2) / top1      —— 相对间隔
  · z_score    = (top1 - 其余均值) / 其余标准差  —— 离群程度

    python -m rag.cli_margin
"""
from __future__ import annotations

import statistics

import numpy as np

from .cli_eval import load_questions
from .store import VectorStore, keyword_coverage


def stats_for(store: VectorStore, query: str):
    hits = store.search(query, top_k=10)
    if len(hits) < 2:
        return None
    scores = np.array([h.score for h in hits])
    top1, rest = scores[0], scores[1:]
    rel_margin = (top1 - rest[0]) / top1 if top1 > 0 else 0.0
    sd = float(rest.std())
    z = (top1 - float(rest.mean())) / sd if sd > 1e-9 else 0.0
    cov = keyword_coverage(query, hits[0].chunk.text)
    return top1, rel_margin, z, cov, hits[0].chunk.doc_id


def main() -> int:
    store = VectorStore.load()
    questions = load_questions()

    rows = []
    for item in questions:
        r = stats_for(store, item['q'])
        if not r:
            continue
        top1, margin, z, cov, doc = r
        in_kb = bool(item.get('relevant'))
        rows.append((item['q'], in_kb, top1, margin, z, cov, doc))

    print('%-24s %-6s %-7s %-7s %-7s %-6s' %
          ('问题', '库内', 'top1', 'rel_marg', 'z', '覆盖'))
    print('-' * 78)
    for q, in_kb, top1, margin, z, cov, doc in rows:
        print('%-24s %-6s %-7.4f %-7.3f %-7.2f %-6.2f'
              % (q[:22], '是' if in_kb else '否', top1, margin, z, cov))

    a = [r for r in rows if r[1]]
    b = [r for r in rows if not r[1]]

    print()
    print('=== 分布对比（库内 vs 库外）===')
    for name, idx, label in (('top1', 2, '相似度'), ('rel_margin', 3, '相对间隔'),
                             ('z', 4, '离群 z 值'), ('coverage', 5, '覆盖率')):
        av = [r[idx] for r in a]
        bv = [r[idx] for r in b]
        print('  %-10s 库内 min=%-7.3f 中位=%-7.3f | 库外 min=%-7.3f 中位=%-7.3f | %s'
              % (label, min(av), statistics.median(av), min(bv), statistics.median(bv),
                 '可区分' if min(av) > max(bv) else '有重叠'))

    # 组合规则：多信号取交集，看能不能把库外问题全挡掉且不误杀库内
    print()
    print('=== 组合规则搜索结果 ===')
    best = None
    for cov_th in [0.3, 0.4, 0.5, 0.6]:
        for z_th in [0.0, 1.0, 1.5, 2.0, 2.5]:
            for s_th in [0.11, 0.13, 0.15]:
                tp = sum(1 for r in a if r[2] >= s_th and (r[5] >= cov_th or r[2] >= 0.25))
                tn = sum(1 for r in b if not (r[2] >= s_th and (r[5] >= cov_th or r[2] >= 0.25)))
                acc = (tp + tn) / len(rows)
                if best is None or acc > best[0]:
                    best = (acc, cov_th, z_th, s_th, tp, tn)
    acc, cov_th, z_th, s_th, tp, tn = best
    print('  最优组合：score>=%.2f 且 (coverage>=%.2f 或 score>=0.25)'
          % (s_th, cov_th))
    print('    准确率 %.1f%%   库内召回 %d/%d   库外拒答 %d/%d'
          % (acc * 100, tp, len(a), tn, len(b)))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
