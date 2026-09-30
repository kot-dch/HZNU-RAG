"""语料清洗。

采集下来的网页正文里混着站点模板噪声，典型三类：

1. 栏目导航（「课程思政教学研究中心」「创新创业研究中心」…）
   ——它出现在每一个页面上，对检索毫无价值，却会被算进相似度。
2. 面包屑（「首页 > 规章制度 > 教务管理」）——纯路径信息。
3. 元信息（「来源 : 教务处 作者 : 系统管理員 时间 : … 访问量 : 2446」）
   ——访问量这类会变化的噪声对问答无意义。

清洗策略：
  A. 规则清洗：正则命中已知模式的行直接丢。
  B. 跨文档重复行检测：一行若出现在 ≥N% 的文档里，说明它是站点模板而非内容。
     这招不需要事先知道模板长什么样，对任何 CMS 站点都适用。
  C. 真正标题的抢救：模板标题被丢掉后，从清洗过的正文里重新取标题。
"""
from __future__ import annotations

import re
from collections import Counter
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# ---------------------------------------------------------------- 规则模式

# 纯装饰字符（分隔线由它们拼成）
DECOR_CHARS = set('-—_=*·•.~～▬■□●○ \t')
# 去掉装饰符后若是这些词，整行也是模板
BOILERPLATE_WORDS = ('友情链接', '相关链接', '快速链接', '常用链接',
                     '返回顶部', '关闭窗口', '打印本页')


def is_separator_line(s: str) -> bool:
    """判断整行是否只是装饰性内容。

    不用正则字符类：装饰字符有多种写法（— U+2014 / – U+2013 / － 全角减号 /
    · / * / = / _），靠枚举容易漏。

    也不能简单地"全字符都在装饰集里"就算——真实页面里的分隔线常常夹着文字，
    例如 `--------友情链接--------`，去掉装饰符后剩「友情链接」，
    属于模板行，也应整行丢掉。所以这里做两步：
      1. 整行只有装饰字符 → 是分隔线
      2. 剥掉装饰字符后剩下的内容若是模板词 → 也是模板行
    """
    if len(s) < 4:
        return False
    if all(ch in DECOR_CHARS for ch in s):
        return True
    stripped = ''.join(ch for ch in s if ch not in DECOR_CHARS).strip()
    if not stripped:
        return True
    return stripped in BOILERPLATE_WORDS


# 单行即丢（与文档内容无关的模板行）
DROP_LINE_PATTERNS = [
    re.compile(r'^首页\s*[>》/]'),                       # 面包屑
    re.compile(r'^来源\s*[:：].*访问量\s*[:：]'),          # 来源+作者+时间+访问量
    re.compile(r'^(来源|作者|时间|访问量|浏览次数|点击次数)\s*[:：]\s*$'),
    re.compile(r'^(地址|邮编|电话|传真)\s*[:：]'),
    re.compile(r'^(版权|版权所有|公安备案|浙ICP|ICP备)'),
    re.compile(r'^Copyright\b', re.I),
    re.compile(r'^(友情链接|相关链接|快速链接|常用链接)'),
    re.compile(r'^(上一篇|下一篇|返回列表|打印本页|关闭窗口)'),
    re.compile(r'^\s*\[?(责任编辑|审核人|编辑)\s*[:：]'),
    re.compile(r'^分享到'),
    re.compile(r'^\d+\s*$'),                            # 纯数字行
]

# 正文里的换行很碎，先做一次合并还原（行尾无标点的行与下一行拼）
TAIL_NO_PUNCT = re.compile(r'[^。！？；：》」』）\)\.!?;:]$')


def rule_clean(lines: List[str]) -> List[str]:
    """按规则丢掉模板行。"""
    out = []
    for ln in lines:
        s = ln.strip()
        if not s or len(s) < 2:
            continue
        if is_separator_line(s):
            continue
        if any(p.search(s) for p in DROP_LINE_PATTERNS):
            continue
        out.append(s)
    return out


def find_boilerplate_line_sets(docs: Dict[str, List[str]], min_doc_ratio: float = 0.25,
                               max_line_len: int = 40) -> Tuple[set, Counter]:
    """找出跨文档高频重复的短行 → 站点模板。

    返回值：(需要丢弃的行集合, 行频统计)

    只考虑较短的行（导航项通常很短），避免把真正重复的正文条款误删。
    """
    counter: Counter = Counter()
    for doc_id, lines in docs.items():
        # 同一文档内只计一次
        for s in {ln.strip() for ln in lines if 2 <= len(ln.strip()) <= max_line_len}:
            counter[s] += 1

    n_docs = max(len(docs), 1)
    threshold = max(2, int(n_docs * min_doc_ratio))
    boilerplate = {line for line, cnt in counter.items() if cnt >= threshold}
    return boilerplate, counter


def strip_boilerplate(lines: List[str], boilerplate: set) -> List[str]:
    return [ln for ln in lines if ln.strip() not in boilerplate]


# ---------------------------------------------------------------- 标题判定

TITLE_REJECT = re.compile(
    r'^(首页|栏目|来源|作者|时间|访问量|地址|邮编|版权|Copyright|友情链接|相关链接|'
    r'课程思政|创新创业|毕业论文|教学成果|教师发展|质量监控|实践管理|教务管理|'
    r'规章制度|公示公告|学生管理|学生工作|党建工作|招生就业|信息公开)'
)


def looks_like_title(line: str) -> bool:
    s = line.strip()
    if not (8 <= len(s) <= 64):
        return False
    if '。' in s or s.endswith(('，', ',')):
        return False
    if TITLE_REJECT.search(s):
        return False
    # 制度/通知类标题的特征词
    if re.search(r'(规定|办法|通知|意见|细则|条例|方案|指南|须知|章程|规则|名单|结果|公示|评选|标准)$', s):
        return True
    if re.search(r'(规定|办法|通知|意见|细则|条例|方案|指南|须知|章程|准则|评选)', s):
        return True
    return False


def pick_title(cleaned_lines: List[str], fallback: str) -> str:
    """从清洗后的正文里挑一个像文档标题的行。"""
    for ln in cleaned_lines[:8]:
        if looks_like_title(ln):
            return ln.strip()
    # 次选：前几行里最长的一行短文本
    cands = [ln.strip() for ln in cleaned_lines[:6] if 8 <= len(ln.strip()) <= 64]
    if cands:
        return max(cands, key=len)
    return fallback


# ---------------------------------------------------------------- 主流程

HDR_PAT = re.compile(r'^#\s*(来源|栏目|字数|抓取时间)\s*[:：]\s*(.*)$')


def read_raw(path: Path) -> Optional[dict]:
    """读采集产物，返回元信息与原始正文行（未清洗）。"""
    try:
        raw = path.read_text(encoding='utf-8')
    except (OSError, UnicodeDecodeError):
        return None

    lines = raw.split('\n')
    meta = {'title': '', 'url': '', 'section': ''}
    body_start = 0
    for i, ln in enumerate(lines[:8]):
        if ln.startswith('# ') and not HDR_PAT.match(ln):
            if not meta['title']:
                meta['title'] = ln[2:].strip()
            continue
        m = HDR_PAT.match(ln)
        if m:
            k, v = m.group(1), m.group(2).strip()
            if k == '来源':
                meta['url'] = v
            elif k == '栏目':
                meta['section'] = v
            continue
        if meta['url']:
            body_start = i + 1 if not ln.strip() else i
            break

    body = [ln.rstrip() for ln in lines[body_start:] if ln.strip()]
    if len('\n'.join(body)) < 50:
        return None

    return {'doc_id': path.stem, 'title': meta['title'], 'url': meta['url'],
            'section': meta['section'], 'lines': body}


def clean_corpus(docs_dir: Path, min_doc_ratio: float = 0.25, verbose: bool = True
                 ) -> Tuple[List[dict], dict]:
    """清洗整个语料目录。

    :return: (清洗后的文档列表, 诊断信息)
    """
    paths = sorted(p for p in docs_dir.iterdir() if p.suffix.lower() == '.txt')
    raws = [d for d in (read_raw(p) for p in paths) if d]
    if not raws:
        return [], {'error': '没有读到任何文档'}

    # 第一遍：规则清洗
    for d in raws:
        d['rule_lines'] = rule_clean(d['lines'])

    # 第二遍：跨文档重复行 → 模板
    boilerplate, counter = find_boilerplate_line_sets(
        {d['doc_id']: d['rule_lines'] for d in raws}, min_doc_ratio=min_doc_ratio)

    cleaned_docs = []
    for d in raws:
        kept = strip_boilerplate(d['rule_lines'], boilerplate)
        if not kept:
            continue
        title = pick_title(kept, d['title'])
        cleaned_docs.append({
            'doc_id': d['doc_id'],
            'title': title,
            'url': d['url'],
            'section': d['section'],
            'text': '\n'.join(kept),
        })

    diag = {
        'docs_in': len(raws),
        'docs_out': len(cleaned_docs),
        'boilerplate_count': len(boilerplate),
        'chars_in': sum(len('\n'.join(d['lines'])) for d in raws),
        'chars_out': sum(len(d['text']) for d in cleaned_docs),
        'top_boilerplate': counter.most_common(15),
    }
    if verbose:
        d = diag
        print('清洗结果')
        print('  文档          : %d -> %d' % (d['docs_in'], d['docs_out']))
        print('  字符          : %d -> %d (删掉 %.0f%%)'
              % (d['chars_in'], d['chars_out'],
                 100 * (1 - d['chars_out'] / max(d['chars_in'], 1))))
        print('  识别出的模板行: %d 条' % d['boilerplate_count'])
        print('  命中最多:')
        for line, cnt in d['top_boilerplate'][:8]:
            print('      x%-3d %s' % (cnt, line[:40]))
    return cleaned_docs, diag
