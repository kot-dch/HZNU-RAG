"""诊断关键词覆盖率闸门：看它到底误杀了哪些题。

    python -m rag.cli_diag_coverage
"""
from __future__ import annotations

import json

from .cli_eval import load_questions
from .config import CONFIG
from .store import VectorStore, keyword_coverage, key_terms


def main() -> int:
    store = VectorStore.load()
    questions = load_questions()
    th = CONFIG.retrieve.score_threshold

    print('诊断关键词覆盖率（阈值 th=%.2f，覆盖率下限=%.2f）'
          % (th, CONFIG.retrieve.min_coverage))
    print()
    print('%-26s %-7s %-7s %-7s %s' % ('问题', 'top1分', '覆盖率', '判定', 'top1 文档'))
    print('-' * 100)

    wrongly_refused = []
    for item in questions:
        q = item['q']
        relevant = item.get('relevant') or []
        raw = store.search(q, top_k=1)
        if not raw:
            continue
        top = raw[0]
        cov = keyword_coverage(q, top.chunk.text)
        terms = key_terms(q)
        score_ok = top.score >= th
        cov_ok = cov >= CONFIG.retrieve.min_coverage
        final = score_ok and cov_ok

        verdict = '通过' if final else ('覆盖率拦下' if score_ok else '分数不够')
        print('%-26s %-7.4f %-7.2f %-7s %s'
              % (q[:24], top.score, cov, verdict, top.chunk.title[:34]))

        # 本该有答案却被覆盖率拦下 = 误杀
        if relevant and score_ok and not cov_ok:
            wrongly_refused.append((q, cov, terms, top.chunk.title))

    print()
    if wrongly_refused:
        print('=== 被误杀的题（有答案，却被覆盖率拦下）===')
        for q, cov, terms, title in wrongly_refused:
            print('  问题：%s' % q)
            print('    实词：%s' % '、'.join(terms))
            print('    覆盖率 %.2f   top1=%s' % (cov, title[:40]))
            print()
        print('原因分析：这些题里有的实词是"同义词"而非"同字"——')
        print('本地 n-gram 只能字面匹配，用户口语提问与文档书面用语不一致时就会漏。')
        print('这正是需要 API embedding 的场景，或需要加一层查询改写。')
    else:
        print('没有误杀。')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
