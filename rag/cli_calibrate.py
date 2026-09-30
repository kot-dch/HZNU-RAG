"""阈值标定：用真实问题与"库里没有答案的问题"对比，找出能区分两者的分界线。

这是定阈值唯一靠谱的办法——拍脑袋定 0.35 或 0.7 都会出错，
因为不同向量化方式的余弦分布尺度完全不同。

判据：
  · 有答案的问题 → 最高相似度应明显更高
  · 没答案的问题 → 最高相似度应明显更低
若两组分布能拉开，就取中间值作为阈值。

    python -m rag.cli_calibrate
"""
from __future__ import annotations

import statistics

from .store import VectorStore

# 知识库里确实有答案的问题（每题标出期望命中的文档）
ANSWERABLE = [
    ('转专业需要什么条件', ['doc-008']),
    ('本科生转专业实施办法', ['doc-008']),
    ('创新实践学分怎么获得', ['doc-006']),
    ('体质测试在哪个校区测', ['doc-002']),
    ('毕业设计论文什么时候开始做', ['doc-003', 'doc-004']),
    ('奖学金怎么申请', None),
    ('助学贷款怎么办', ['doc-005', 'doc-024']),
    ('评奖评优看什么', None),
    ('学生综合素质评价怎么算', None),
    ('平安保险须知', ['doc-010']),
]

# 知识库里没有答案的问题（用来测拒答能力）
UNANSWERABLE = [
    '今天杭州天气怎么样',
    '学校食堂哪个窗口好吃',
    '怎么报考计算机二级考试',
    '这附近有什么好吃的',
    'Python 怎么安装',
    '世界杯什么时候开始',
    '怎么申请出国交换',
    '学校健身房怎么收费',
    '校园卡丢了怎么办',
    '宿舍可以住到什么时候',
]


def probe(store: VectorStore, questions, label):
    print('=== %s ===' % label)
    tops = []
    for q in questions:
        query = q[0] if isinstance(q, tuple) else q
        expected = q[1] if isinstance(q, tuple) and len(q) > 1 else None
        hits = store.search(query, top_k=5)
        if not hits:
            print('  %-24s 无结果' % query)
            continue
        top = hits[0]
        doc_hits = [h for h in hits if h.chunk.doc_id in expected] if expected else []
        mark = ''
        if expected:
            mark = '✓' if doc_hits else '✗ 期望 %s' % ','.join(expected)
        tops.append(top.score)
        print('  %-24s top1=%.4f  %-40s %s'
              % (query, top.score, top.chunk.title[:40], mark))
    print()
    return tops


def main() -> int:
    store = VectorStore.load()
    print(store.info())
    print('向量化：%s' % store.embedder.describe())
    print()

    a = probe(store, ANSWERABLE, '有答案的问题')
    b = probe(store, UNANSWERABLE, '库里没有答案的问题')

    print('=== 分数分布 ===')
    print('  有答案  : n=%d  min=%.4f  中位=%.4f  max=%.4f'
          % (len(a), min(a), statistics.median(a), max(a)))
    print('  无答案  : n=%d  min=%.4f  中位=%.4f  max=%.4f'
          % (len(b), min(b), statistics.median(b), max(b)))
    print()

    # 简单分类器评估：扫描阈值，找使准确率最高的点
    best = None
    for th in [x / 1000 for x in range(30, 400, 5)]:
        tp = sum(1 for s in a if s >= th)
        tn = sum(1 for s in b if s < th)
        acc = (tp + tn) / (len(a) + len(b))
        if best is None or acc > best[1]:
            best = (th, acc, tp, tn)

    th, acc, tp, tn = best
    print('=== 建议阈值 ===')
    print('  阈值 %.3f  →  正确率 %.1f%%' % (th, acc * 100))
    print('    有答案被判为"有依据"：%d/%d' % (tp, len(a)))
    print('    无答案被判为"该拒答"：%d/%d' % (tn, len(b)))
    print()
    print('  在 config.py 的 RetrieveConfig.score_threshold 里改成 %.2f 即可。' % th)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
