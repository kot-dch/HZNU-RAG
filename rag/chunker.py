"""文档加载与切分。

设计要点（这是 RAG 质量的第一道闸门）：

1. 校园制度文档有天然的条款结构（「第X条」「一、」「（一）」），
   按条款边界切分比按固定长度硬切检索质量高得多——因为一个条款
   通常就是一个完整的语义单元，切碎了会导致检索到半句话。

2. 但条款可能很长（超过 chunk_size），所以条款内部还要按句子退让，
   实在不行才硬切。

3. 保留 chunk_overlap，避免答案正好跨在切分边界上被截断。

4. 每个块都带完整 metadata（doc_id / title / url / chunk_index /
   total_chunks），这样生成阶段才能给出可核对的出处引用。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Iterable, List, Optional

from .config import CONFIG, DOCS_DIR

# ---------------------------------------------------------------- 数据结构


@dataclass
class Chunk:
    """一个可检索的文本片段。"""

    chunk_id: str          # 全局唯一，如 doc-001#3
    doc_id: str            # 来源文档，如 doc-001
    title: str             # 文档标题
    url: str               # 原始 URL（用于引用溯源）
    section: str           # 所属栏目
    chunk_index: int       # 在文档内的序号（从 0 开始）
    total_chunks: int      # 该文档共切成几块
    text: str              # 片段正文

    def to_dict(self) -> dict:
        return asdict(self)

    def citation(self) -> str:
        """给用户看的出处，例如：doc-005《新生入学指南》"""
        return '%s《%s》' % (self.doc_id, self.title)


# ---------------------------------------------------------------- 条款切分

# 条款起始标记：行首的「第X条」「一、」「（一）」「1.」等
CLAUSE_PATTERNS = [
    re.compile(r'^第[一二三四五六七八九十百零〇\d]+条'),          # 第X条
    re.compile(r'^第[一二三四五六七八九十百零〇\d]+章'),          # 第X章
    re.compile(r'^[一二三四五六七八九十]+[、.．]'),              # 一、
    re.compile(r'^（[一二三四五六七八九十\d]+）'),                # （一）
    re.compile(r'^\([一二三四五六七八九十\d]+\)'),                # (一)
    re.compile(r'^\d+[、.．]\s*\S'),                             # 1.
]

# 句子边界（中文标点）
SENTENCE_END = re.compile(r'(?<=[。！？；])')


def _is_clause_start(line: str) -> bool:
    s = line.strip()
    if not s:
        return False
    return any(p.match(s) for p in CLAUSE_PATTERNS)


def _split_by_sentence(text: str) -> List[str]:
    """按中文句末标点切句，保留标点。"""
    parts = SENTENCE_END.split(text)
    return [p for p in parts if p]


def _hard_split(text: str, size: int) -> List[str]:
    """兜底：按固定长度硬切（通常用不到，说明有超长无标点文本）。"""
    return [text[i:i + size] for i in range(0, len(text), size)]


def _pack(units: Iterable[str], size: int) -> List[str]:
    """把若干小单元（条款/句子）贪心装进 size 大小的桶里。"""
    chunks: List[str] = []
    buf = ''
    for u in units:
        if not u:
            continue
        # 单个单元就超长，先冲掉缓冲，再内部退让切分
        if len(u) > size:
            if buf:
                chunks.append(buf)
                buf = ''
            if len(u) <= size * 1.6:
                chunks.append(u)
            else:
                for s in _split_by_sentence(u):
                    if len(s) > size:
                        chunks.extend(_hard_split(s, size))
                    else:
                        chunks.append(s)
            continue
        if len(buf) + len(u) > size:
            chunks.append(buf)
            buf = u
        else:
            buf += u
    if buf:
        chunks.append(buf)
    return [c.strip() for c in chunks if c.strip()]


def _apply_overlap(chunks: List[str], overlap: int) -> List[str]:
    """给每个块前置上一块的尾部若干字符，避免答案跨边界被截断。"""
    if overlap <= 0 or len(chunks) < 2:
        return chunks
    out = [chunks[0]]
    for i in range(1, len(chunks)):
        prev_tail = chunks[i - 1][-overlap:]
        # 避免重复拼接同一段
        if prev_tail and not chunks[i].startswith(prev_tail):
            out.append(prev_tail + chunks[i])
        else:
            out.append(chunks[i])
    return out


def _merge_tiny(chunks: List[str], min_size: int) -> List[str]:
    """把过短的块并入前一块。"""
    if not chunks:
        return chunks
    out: List[str] = [chunks[0]]
    for c in chunks[1:]:
        if len(c) < min_size and len(out[-1]) + len(c) <= CONFIG.chunk.chunk_size * 1.4:
            out[-1] = out[-1] + c
        else:
            out.append(c)
    return out


def split_text(text: str, chunk_size: int = None, chunk_overlap: int = None,
               min_chunk_size: int = None, split_on_clause: bool = None) -> List[str]:
    """把一段正文切成若干片段。"""
    cfg = CONFIG.chunk
    size = chunk_size or cfg.chunk_size
    overlap = cfg.chunk_overlap if chunk_overlap is None else chunk_overlap
    min_size = cfg.min_chunk_size if min_chunk_size is None else min_chunk_size
    by_clause = cfg.split_on_clause if split_on_clause is None else split_on_clause

    text = (text or '').strip()
    if not text:
        return []
    if len(text) <= size:
        return [text]

    lines = [ln.strip() for ln in text.split('\n') if ln.strip()]

    # 先按条款标记聚合成「条款单元」
    units: List[str] = []
    if by_clause:
        buf = ''
        for ln in lines:
            if _is_clause_start(ln) and buf:
                units.append(buf)
                buf = ln
            else:
                buf = (buf + '\n' + ln) if buf else ln
        if buf:
            units.append(buf)
    else:
        units = lines

    # 条款单元还是太长就先按句子打散
    fine: List[str] = []
    for u in units:
        if len(u) > size:
            fine.extend(_split_by_sentence(u))
        else:
            fine.append(u)

    chunks = _pack(fine, size)
    chunks = _merge_tiny(chunks, min_size)
    chunks = _apply_overlap(chunks, overlap)
    return chunks


# ---------------------------------------------------------------- 文档加载

HDR_PAT = re.compile(r'^#\s*(来源|栏目|字数|抓取时间)\s*[:：]\s*(.*)$')


def _looks_like_title(line: str) -> bool:
    if not (8 <= len(line) <= 60):
        return False
    if _is_clause_start(line):
        return False
    # 标题一般不以句号结尾，且不含句号
    if line.endswith('。') or '。' in line:
        return False
    return True


def load_document(path: Path) -> Optional[dict]:
    """读一个采集产物 txt（只做基础解析，不负责清洗）。

    清洗请用 cleaner.clean_corpus —— 它需要跨文档统计才能识别模板行。
    """
    try:
        raw = path.read_text(encoding='utf-8')
    except (OSError, UnicodeDecodeError):
        return None

    lines = raw.split('\n')
    meta = {'title': '', 'url': '', 'section': ''}
    body_start = 0

    for i, ln in enumerate(lines[:8]):
        if ln.startswith('# ') and not HDR_PAT.match(ln):
            t = ln[2:].strip()
            if t and not meta['title']:
                meta['title'] = t
            continue
        m = HDR_PAT.match(ln)
        if m:
            key, val = m.group(1), m.group(2).strip()
            if key == '来源':
                meta['url'] = val
            elif key == '栏目':
                meta['section'] = val
            continue
        if meta['url']:
            body_start = i + 1 if not ln.strip() else i
            break

    body_lines = [ln.rstrip() for ln in lines[body_start:] if ln.strip()]
    text = '\n'.join(body_lines)
    if len(text) < 50:
        return None

    return {
        'doc_id': path.stem,
        'title': meta['title'] or path.stem,
        'url': meta['url'],
        'section': meta['section'],
        'text': text,
    }


def build_chunks(docs_dir: Path = None, use_cleaner: bool = True,
                 min_doc_ratio: float = 0.25, verbose: bool = False) -> List[Chunk]:
    """扫描语料目录，清洗后切分成块。

    use_cleaner=True（默认）会先做跨文档模板行剔除，
    这样检索时不会被"课程思政教学研究中心"这类导航噪声干扰。
    """
    docs_dir = Path(docs_dir or DOCS_DIR)
    if not docs_dir.exists():
        raise FileNotFoundError(
            '语料目录不存在：%s\n请先运行 campus-secondhand\\tools\\collect-hznu-v2.ps1 采集文档。'
            % docs_dir)

    if use_cleaner:
        from .cleaner import clean_corpus
        docs, _diag = clean_corpus(docs_dir, min_doc_ratio=min_doc_ratio, verbose=verbose)
    else:
        paths = sorted(p for p in docs_dir.iterdir() if p.suffix.lower() == '.txt')
        docs = [d for d in (load_document(p) for p in paths) if d]

    chunks: List[Chunk] = []
    for doc in docs:
        pieces = split_text(doc['text'])
        total = len(pieces)
        for idx, piece in enumerate(pieces):
            chunks.append(Chunk(
                chunk_id='%s#%d' % (doc['doc_id'], idx),
                doc_id=doc['doc_id'],
                title=doc['title'],
                url=doc['url'],
                section=doc['section'],
                chunk_index=idx,
                total_chunks=total,
                text=piece,
            ))
    return chunks


def stats(chunks: List[Chunk]) -> str:
    """切分结果概览，用于人工检查切得好不好。"""
    if not chunks:
        return '没有切出任何片段'
    lengths = [len(c.text) for c in chunks]
    docs = {c.doc_id for c in chunks}
    return '\n'.join([
        '切分统计',
        '  文档数      : %d' % len(docs),
        '  片段总数    : %d' % len(chunks),
        '  片段均长    : %.0f 字' % (sum(lengths) / len(lengths)),
        '  最短 / 最长 : %d / %d 字' % (min(lengths), max(lengths)),
        '  平均每文档  : %.1f 块' % (len(chunks) / max(len(docs), 1)),
    ])
