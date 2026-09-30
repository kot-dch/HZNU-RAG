"""RAG 冒烟测试。

不依赖 pytest，直接运行：
    python tests/test_rag.py

覆盖：
  1. 归一化与 n-gram 提取
  2. 向量化：确定性、归一化、维度一致
  3. 切分：尺寸约束、重叠、条款边界
  4. 清洗：模板行与噪声剔除
  5. 覆盖率：二元组逻辑（含"整串当词"这个历史 bug 的回归测试）
  6. 检索：真实语料上的 Recall@k 与拒答
  7. 生成：引用结构与拒答路径
  8. 端到端：ask() 返回完整结构
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

# 让 tests/ 目录下可直接运行
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rag.chunker import split_text, build_chunks, stats
from rag.cleaner import rule_clean, find_boilerplate_line_sets, looks_like_title
from rag.config import CONFIG
from rag.embedder import Embedder, char_ngrams, normalize, local_embed
from rag.pipeline import RagPipeline
from rag.store import VectorStore, keyword_coverage, coverage_bigrams
from rag.generator import build_context, build_messages, Generator

PASSED = []
FAILED = []


def test(name):
    def deco(fn):
        try:
            fn()
            PASSED.append(name)
            print('  ✓ %s' % name)
        except Exception as exc:
            FAILED.append((name, exc))
            print('  ✗ %s\n      %s: %s' % (name, type(exc).__name__, exc))
        return fn
    return deco


def eq(a, b, msg=''):
    assert a == b, '%s 期望 %r，实际 %r' % (msg, b, a)


def ok(cond, msg='断言失败'):
    assert cond, msg


# ---------------------------------------------------------------- 1. 归一化

print('\n[1] 归一化与 n-gram')

@test('归一化统一全角标点')
def _():
    eq(normalize('转专业（试行）'), '转专业(试行)')

@test('归一化压缩空白')
def _():
    eq(normalize('a   b\n c'), 'a b c')

@test('n-gram 覆盖 1~3 字')
def _():
    grams = set(char_ngrams('转专业', 1, 3))
    for g in ('转', '专', '业', '转专', '专业', '转专业'):
        ok(g in grams, '缺少 n-gram：%s' % g)

@test('n-gram 不跨空白组合')
def _():
    grams = char_ngrams('ab cd', 2, 2)
    ok('b ' not in grams and ' c' not in grams, '不应跨空格组合')

@test('空文本返回空')
def _():
    eq(char_ngrams('', 1, 3), [])


# ---------------------------------------------------------------- 2. 向量化

print('\n[2] 向量化')

@test('相同文本得到相同向量（确定性）')
def _():
    a = local_embed('转专业实施办法', 512, 1, 3)
    b = local_embed('转专业实施办法', 512, 1, 3)
    ok(np.allclose(a, b), '同文本应得到完全相同的向量')

@test('向量已 L2 归一化')
def _():
    v = local_embed('杭州师范大学本科生转专业', 512, 1, 3)
    ok(abs(float(np.linalg.norm(v)) - 1.0) < 1e-5, '范数应为 1')

@test('维度正确')
def _():
    eq(local_embed('测试', 256, 1, 3).shape, (256,))

@test('空文本得到零向量而不报错')
def _():
    v = local_embed('', 128, 1, 3)
    eq(float(np.linalg.norm(v)), 0.0)

@test('相关文本相似度高于无关文本')
def _():
    q = local_embed('转专业', 1024, 1, 3)
    near = local_embed('本科生转专业实施办法', 1024, 1, 3)
    far = local_embed('体质测试安排在田径场', 1024, 1, 3)
    ok(float(q @ near) > float(q @ far), '相关文本应更相似')

@test('Embedder.encode 批量返回矩阵')
def _():
    e = Embedder()
    m = e.encode(['转专业', '奖学金'])
    eq(m.shape[0], 2)
    eq(m.shape[1], CONFIG.embed.local_dim)


# ---------------------------------------------------------------- 3. 切分

print('\n[3] 切分')

@test('短文本不切分')
def _():
    eq(len(split_text('很短的一句话')), 1)

@test('长文本切成多块且不超长太多')
def _():
    text = '第一条 这是测试内容。' * 200
    chunks = split_text(text, chunk_size=300, chunk_overlap=50)
    ok(len(chunks) > 1, '应切成多块')
    # 允许 overlap 带来的超出
    for c in chunks:
        ok(len(c) <= 300 + 50 + 10, '块过长：%d' % len(c))

@test('条款标记处优先切分')
def _():
    text = ('第一条 学生的权利与义务。' + '内容甲' * 40 +
            '第二条 学籍管理规定。' + '内容乙' * 40 +
            '第三条 考核与成绩。' + '内容丙' * 40)
    chunks = split_text(text, chunk_size=200, chunk_overlap=0)
    # 至少有一个块以条款标记开头
    ok(any(c.strip().startswith(('第一条', '第二条', '第三条')) for c in chunks),
       '应保留条款起始')

@test('相邻块存在重叠')
def _():
    # 样本要足够长，保证能产生 ≥3 块（chunk_size=200 时约需 600 字以上）
    text = ''.join('第%d条 测试条款内容在这里展开说明。' % i for i in range(1, 40))
    ok(len(text) > 600, '样本长度不足：%d' % len(text))
    chunks = split_text(text, chunk_size=200, chunk_overlap=60)
    ok(len(chunks) >= 3, '样本应产生 ≥3 块，实际 %d 块（总长 %d）' % (len(chunks), len(text)))
    # 从第二块起，开头应包含前一块的尾部片段
    ok(chunks[1].startswith(chunks[0][-60:]),
       '第二块开头应等于前一块末尾 60 字')

@test('真实语料切分统计合理')
def _():
    chunks = build_chunks()
    ok(len(chunks) > 50, '片段数应大于 50，实际 %d' % len(chunks))
    lengths = [len(c.text) for c in chunks]
    ok(min(lengths) >= 100, '最短块不应过小：%d' % min(lengths))
    ok(max(lengths) <= 1200, '最长块不应过大：%d' % max(lengths))

@test('每个片段都带完整 metadata')
def _():
    chunks = build_chunks()
    for c in chunks[:20]:
        ok(c.chunk_id and c.doc_id and c.title, 'metadata 缺失：%s' % c.chunk_id)
        ok(c.url.startswith('http'), '缺少来源 URL：%s' % c.chunk_id)
        ok(c.total_chunks >= 1)


# ---------------------------------------------------------------- 4. 清洗

print('\n[4] 清洗')

@test('规则清洗丢掉面包屑与元信息行')
def _():
    lines = ['首页 > 规章制度 > 教务管理',
             '来源 : 教务处 作者 : 系统管理员 时间 : 2017-09-12 访问量 : 2446',
             '第一条 本规定适用于全体本科生。',
             '--------友情链接--------',
             'Copyright © 2020 All Rights Reserved']
    out = rule_clean(lines)
    eq(len(out), 1)
    ok('第一条' in out[0])

@test('跨文档重复行被识别为模板')
def _():
    docs = {
        'd1': ['课程思政教学研究中心', '第一条 内容甲', '独特内容一'],
        'd2': ['课程思政教学研究中心', '第二条 内容乙', '独特内容二'],
        'd3': ['课程思政教学研究中心', '第三条 内容丙', '独特内容三'],
    }
    bp, counter = find_boilerplate_line_sets(docs, min_doc_ratio=0.5)
    ok('课程思政教学研究中心' in bp, '应识别为模板行')
    ok('第一条 内容甲' not in bp, '正文不应被判为模板')

@test('标题判定能认出制度类标题')
def _():
    ok(looks_like_title('杭州师范大学本科生转专业实施办法（试行）'))
    ok(looks_like_title('关于做好2020届本科生毕业设计(论文)工作的通知'))
    ok(not looks_like_title('课程思政教学研究中心'))
    ok(not looks_like_title('首页 > 规章制度'))


# ---------------------------------------------------------------- 5. 覆盖率

print('\n[5] 关键词覆盖率')

@test('回归：整串汉字不应被当成一个词（历史 bug）')
def _():
    # 旧实现把"什么情况下不能转专业"当单一 token，覆盖率算成 0，误杀正确结果。
    # 现在应切成多个二元组，且必须保留"转专业"的二元组。
    grams = coverage_bigrams('什么情况下不能转专业')
    ok(len(grams) >= 3, '应切成 ≥3 个二元组，实际 %d 个：%s' % (len(grams), grams))
    ok('转专' in grams or '专业' in grams, '应保留"转专业"的二元组：%s' % grams)

@test('疑问词不制造虚假覆盖（有实词时保留实词二元组）')
def _():
    # "怎么办" 去掉疑问词后只剩单字，算法会回退保留原段。
    # 关键不是把疑问词删干净，而是**不能因为疑问词而给出高覆盖率**：
    # 疑问词不能在文档里命中。
    grams = coverage_bigrams('怎么办')
    ok(len(grams) >= 1, '不应返回空')
    ok(keyword_coverage('怎么办', '完全无关的一段文字内容。') == 0.0,
       '疑问词不应在无关文本上产生覆盖')

@test('停用词不会留下无意义残片拼接')
def _():
    grams = coverage_bigrams('学校有哪些资助政策')
    # 不该出现 "校有""有哪" 这类跨停用词拼接的残片
    for bad in ('校有', '有哪'):
        ok(bad not in grams, '出现跨停用词残片：%s（完整：%s）' % (bad, grams))

@test('命中片段覆盖率高于无关片段')
def _():
    q = '转专业需要什么条件'
    hit = keyword_coverage(q, '第四条 属于下列情形之一者，不予进行转专业：已完成一次转专业的学生。')
    miss = keyword_coverage(q, '新生入学时须参加体质健康测试，测试地点在田径场。')
    ok(hit > miss, '相关片段覆盖率应更高：hit=%.2f miss=%.2f' % (hit, miss))

@test('全角罗马数字归一化（Ⅱ 与 II）')
def _():
    ok(keyword_coverage('II类学分', '创新实践（Ⅱ类）学分管理办法') > 0.5,
       'Ⅱ 应能匹配 II')


# ---------------------------------------------------------------- 6. 检索

print('\n[6] 检索')

@test('索引可加载且维度一致')
def _():
    store = VectorStore.load()
    ok(len(store.chunks) > 0)
    eq(store.vectors.shape[0], len(store.chunks))

@test('检索返回按分数降序')
def _():
    store = VectorStore.load()
    hits = store.search('转专业需要什么条件', top_k=5)
    ok(len(hits) == 5)
    for i in range(1, len(hits)):
        ok(hits[i].score <= hits[i - 1].score, '结果未降序')

@test('库内问题能检索到正确文档')
def _():
    pipe = RagPipeline.load()
    cases = [
        ('本科生转专业实施办法', 'doc-008'),
        ('创新实践学分怎么获得', 'doc-006'),
        ('体质测试在哪个校区测', 'doc-002'),
        ('经亨颐奖学金怎么评选', 'doc-020'),
    ]
    for q, doc in cases:
        hits, grounded = pipe.retriever.retrieve(q, top_k=5)
        ok(grounded, '应判定为有依据：%s' % q)
        ok(any(h.chunk.doc_id == doc for h in hits),
           '%s 应命中 %s，实际 %s' % (q, doc, [h.chunk.doc_id for h in hits]))

@test('库外问题被正确拒答')
def _():
    pipe = RagPipeline.load()
    for q in ('今天杭州天气怎么样', 'Python 怎么安装', '世界杯什么时候开始'):
        hits, grounded = pipe.retriever.retrieve(q, top_k=5)
        ok(not grounded, '应拒答：%s（却命中 %s）'
           % (q, [h.chunk.doc_id for h in hits]))

@test('相邻块去重生效')
def _():
    pipe = RagPipeline.load()
    hits, _ = pipe.retriever.retrieve('学生综合素质评价和评奖评优', top_k=5)
    keys = [(h.chunk.doc_id, h.chunk.chunk_index) for h in hits]
    eq(len(keys), len(set(keys)), '不应出现完全重复的块')
    for i in range(len(keys)):
        for j in range(i + 1, len(keys)):
            if keys[i][0] == keys[j][0]:
                ok(abs(keys[i][1] - keys[j][1]) > 1,
                   '不应同时返回相邻块：%s' % str((keys[i], keys[j])))


# ---------------------------------------------------------------- 7. 生成

print('\n[7] 生成')

@test('上下文带编号且与引用一致')
def _():
    pipe = RagPipeline.load()
    hits, grounded = pipe.retriever.retrieve('转专业需要什么条件', top_k=3)
    ok(grounded)
    ctx = build_context(hits)
    for i in range(1, len(hits) + 1):
        ok('[%d]' % i in ctx, '上下文缺少编号 [%d]' % i)

@test('提示词包含关键约束')
def _():
    pipe = RagPipeline.load()
    hits, _ = pipe.retriever.retrieve('转专业需要什么条件', top_k=2)
    msgs = build_messages('转专业需要什么条件', hits)
    eq(len(msgs), 2)
    eq(msgs[0]['role'], 'system')
    text = msgs[0]['content'] + msgs[1]['content']
    # 提示词里必须有的四类约束：只用材料 / 不许编造 / 标注引用 / 拒答分支
    for kw in ('只依据', '不要编造', '[编号]', '没有找到'):
        ok(kw in text, '提示词缺少约束：%s' % kw)

@test('库外问题直接拒答，不调用模型')
def _():
    pipe = RagPipeline.load()
    ans = pipe.ask('今天杭州天气怎么样')
    ok(not ans.grounded)
    eq(ans.source, 'refused')
    eq(ans.citations, [])
    ok('没有找到' in ans.answer)

@test('无 Key 时走抽取式并给出出处')
def _():
    pipe = RagPipeline.load()
    ans = pipe.ask('转专业需要什么条件')
    ok(ans.grounded)
    ok(ans.source in ('llm', 'extractive'))
    ok(len(ans.citations) >= 1, '应给出引用')
    for c in ans.citations:
        for k in ('index', 'doc_id', 'title', 'url', 'score'):
            ok(k in c, '引用缺少字段 %s' % k)

@test('空问题被拦下')
def _():
    pipe = RagPipeline.load()
    ans = pipe.ask('   ')
    ok(not ans.grounded)
    eq(ans.source, 'refused')


# ---------------------------------------------------------------- 8. 端到端

print('\n[8] 端到端')

@test('ask() 返回结构完整且可 JSON 序列化')
def _():
    import json
    pipe = RagPipeline.load()
    ans = pipe.ask('体质测试在哪里进行')
    d = ans.to_dict()
    json.dumps(d, ensure_ascii=False)   # 不抛异常即通过
    for k in ('question', 'grounded', 'answer', 'citations', 'hits', 'source'):
        ok(k in d, '返回缺少字段 %s' % k)

@test('批量问题全部有确定结果（不抛异常）')
def _():
    pipe = RagPipeline.load()
    qs = ['转专业需要什么条件', '奖学金怎么申请', '今天天气', '图书馆借书',
          '毕业设计什么时候开始', 'II类学分是什么']
    for q in qs:
        ans = pipe.ask(q)
        ok(ans.answer and len(ans.answer) > 5, '答案过短：%s' % q)


# ---------------------------------------------------------------- 汇总

print('\n' + '=' * 70)
print('通过 %d 项，失败 %d 项' % (len(PASSED), len(FAILED)))
if FAILED:
    print('\n失败明细：')
    for name, exc in FAILED:
        print('  ✗ %s\n      %s: %s' % (name, type(exc).__name__, exc))
print('=' * 70)
sys.exit(1 if FAILED else 0)
