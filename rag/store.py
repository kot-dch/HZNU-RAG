"""向量索引与检索。

索引结构很简单：一个 (N, dim) 的归一化向量矩阵 + 一份 chunk 元数据列表。
因为向量已经 L2 归一化，余弦相似度就等于内积，检索是一次矩阵乘法。

这个规模（几百到几千块）用 numpy 暴力检索完全够：1000 块 × 2048 维
一次查询是 200 万次乘加，毫秒级。**不需要引入 FAISS 之类的向量库**——
数据量小的时候裸算余弦相似度反而是更透明、更可控的选择，
而且面试问"你向量检索怎么实现的"你能直接讲清原理。
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

import numpy as np

from .chunker import Chunk
from .config import CONFIG, ARTIFACT_DIR
from .embedder import Embedder

# ---------------------------------------------------------------- 关键词覆盖率

# 疑问词与虚词不参与覆盖计算——它们在任何文档里都可能出现，没有区分度
STOPWORDS = {
    '怎么', '什么', '如何', '哪些', '哪个', '哪里', '多少', '为什么', '是否',
    '可以', '能不能', '需要', '应该', '要求', '有没', '有没有', '关于',
    '的', '了', '吗', '呢', '和', '与', '或', '是', '在', '我', '你',
    '学校', '我们', '这个', '那个', '一个', '时候', '情况', '不能',
}

# 全角/罗马数字归一化：文档里写"Ⅱ类学分"，用户敲"II类学分"
_NORMALIZE = {
    'Ⅱ': 'II', 'Ⅲ': 'III', 'Ⅰ': 'I', 'Ⅳ': 'IV',
    '１': '1', '２': '2', '３': '3', '４': '4', '５': '5',
}


def _norm(text: str) -> str:
    s = text or ''
    for a, b in _NORMALIZE.items():
        s = s.replace(a, b)
    return s.lower()


def key_terms(text: str) -> List[str]:
    """抽取用于覆盖判定的实词（按标点切段，仅用于展示诊断）。"""
    out = []
    for seg in re.split(r'[^\u4e00-\u9fa5A-Za-z0-9]+', _norm(text)):
        if not seg or seg in STOPWORDS:
            continue
        out.append(seg)
    return out


def coverage_bigrams(query: str) -> List[str]:
    """把查询切成字符二元组，作为覆盖判定的基本单位。

    为什么不用分词：中文没有天然空格，先前用"连续汉字串"当词，
    结果「什么情况下不能转专业」整串被当成一个词，而它在文档里显然不存在，
    覆盖率被算成 0 —— 指标直接失效（实测误杀 3 道题）。

    为什么按"段"而不是整串去停用词：直接在整个字符串上 replace 会留下
    无意义残片（"什么情况下不能转专业" 去掉「什么/情况/不能」后剩下
    "下转专业"，多出一个噪声二元组「下转」）。所以先按标点切段，
    只丢弃**整段等于停用词**的段，再做兜底替换。
    """
    s = _norm(query)
    parts = [p for p in re.split(r'[^\u4e00-\u9fa5A-Za-z0-9]+', s) if p]
    cleaned = []
    for p in parts:
        if p in STOPWORDS:
            continue
        # 段内仍可能夹着停用词（如"什么情况下不能转专业"整段无标点），
        # 做一次兜底剥离，剥完还剩 ≥2 字才采用；否则保留原段，
        # 避免"剥成一个残字"或"原段+剥后段"重复拼接
        stripped = p
        for w in sorted(STOPWORDS, key=len, reverse=True):
            stripped = stripped.replace(w, '')
        cleaned.append(stripped if len(stripped) >= 2 else p)

    s = ''.join(cleaned)
    if len(s) < 2:
        return [s] if s else []
    return [s[i:i + 2] for i in range(len(s) - 1)]


def keyword_coverage(query: str, passage: str) -> float:
    """查询二元组在片段中的覆盖比例（0~1）。

    宽松匹配：只要片段包含该二元组即算命中。
    对"怎么补办学生证"这类库里没有的问题，二元组多为「补办」「学生」「生证」，
    在《平安保险须知》里几乎都不出现，覆盖率接近 0，从而被拦下。
    """
    grams = coverage_bigrams(query)
    if not grams:
        return 1.0                      # 没有可判定的实词，不做覆盖拦截
    p = _norm(passage)
    hit = sum(1 for g in grams if g in p)
    return hit / len(grams)


@dataclass
class Hit:
    """一条检索结果。"""

    chunk: Chunk
    score: float

    def to_dict(self) -> dict:
        d = self.chunk.to_dict()
        d['score'] = round(float(self.score), 4)
        return d


class VectorStore:
    """向量索引：构建、保存、加载、检索。"""

    def __init__(self, chunks: List[Chunk], vectors: np.ndarray, embedder: Embedder):
        assert len(chunks) == vectors.shape[0], '片段数与向量数不一致'
        self.chunks = chunks
        self.vectors = vectors.astype(np.float32)
        self.embedder = embedder

    # ------------------------------ 构建

    @classmethod
    def build(cls, chunks: List[Chunk], embedder: Optional[Embedder] = None) -> 'VectorStore':
        emb = embedder or Embedder()
        # 把标题拼到片段前面：标题是极强的检索信号，尤其对"XX办法/XX通知"
        # 这类提问（用户可能直接问"转专业实施办法"）。代价很低，收益明显。
        texts = ['%s\n%s' % (c.title, c.text) for c in chunks]
        vecs = emb.encode(texts)
        return cls(chunks, vecs, emb)

    # ------------------------------ 持久化

    def save(self, directory: Path = None) -> Path:
        d = Path(directory or ARTIFACT_DIR)
        d.mkdir(parents=True, exist_ok=True)
        np.save(d / 'vectors.npy', self.vectors)
        with open(d / 'chunks.json', 'w', encoding='utf-8') as f:
            json.dump([c.to_dict() for c in self.chunks], f, ensure_ascii=False, indent=1)
        meta = {
            'count': len(self.chunks),
            'dim': int(self.vectors.shape[1]) if self.vectors.size else 0,
            'embed_mode': self.embedder.mode,
            'embed_desc': self.embedder.describe(),
        }
        with open(d / 'index_meta.json', 'w', encoding='utf-8') as f:
            json.dump(meta, f, ensure_ascii=False, indent=1)
        return d

    @classmethod
    def load(cls, directory: Path = None) -> 'VectorStore':
        d = Path(directory or ARTIFACT_DIR)
        vec_path, chunk_path = d / 'vectors.npy', d / 'chunks.json'
        if not vec_path.exists() or not chunk_path.exists():
            raise FileNotFoundError(
                '索引不存在：%s\n请先运行  python -m rag.cli_index  构建索引。' % d)
        vectors = np.load(vec_path)
        with open(chunk_path, encoding='utf-8') as f:
            raw = json.load(f)
        chunks = [Chunk(**item) for item in raw]
        return cls(chunks, vectors, Embedder())

    def info(self) -> str:
        return '索引：%d 个片段，维度 %d' % (
            len(self.chunks), int(self.vectors.shape[1]) if self.vectors.size else 0)

    # ------------------------------ 检索

    def search(self, query: str, top_k: int = None) -> List[Hit]:
        """返回按相似度降序的 top_k 结果。"""
        k = top_k or CONFIG.retrieve.top_k
        if not self.chunks or not query.strip():
            return []
        q = self.embedder.encode_one(query)
        if q.size == 0 or q.shape[0] != self.vectors.shape[1]:
            return []
        # 向量均已归一化 → 内积即余弦相似度
        scores = self.vectors @ q
        k = min(k, scores.shape[0])
        # argpartition 取 top-k 再局部排序，比全排序快
        idx = np.argpartition(-scores, k - 1)[:k]
        idx = idx[np.argsort(-scores[idx])]
        return [Hit(self.chunks[i], float(scores[i])) for i in idx]


class Retriever:
    """在 VectorStore 之上加检索后处理。"""

    def __init__(self, store: VectorStore, cfg=None):
        self.store = store
        self.cfg = cfg or CONFIG.retrieve

    def retrieve(self, query: str, top_k: int = None,
                 threshold: float = None) -> Tuple[List[Hit], bool]:
        """检索并做后处理。

        :return: (命中的片段列表, 是否"有依据")
                 第二个返回值用于兜底拒答——相似度都低于阈值时说明
                 知识库里没有相关内容，此时必须拒答而不是让模型硬编。
        """
        k = top_k or self.cfg.top_k
        th = self.cfg.score_threshold if threshold is None else threshold

        # 多取一些候选，留出给去重的余量
        raw = self.store.search(query, top_k=max(k * 3, k))
        if self.cfg.dedup_adjacent:
            raw = self._dedup(raw)

        hits = [h for h in raw if h.score >= th][:k]

        # 第二道闸：关键词覆盖率，只作用于"低分带"。
        #
        # 单看向量相似度会有"貌似相关"的假阳性（问"怎么补办学生证"命中
        # 《平安保险须知》，0.1191 刚好越线）；但一刀切地要求覆盖率又会误杀
        # 高分段里覆盖率偏低却正确的结果（"转专业每学期可以填几个志愿"
        # 覆盖率仅 0.30，命中文档却完全正确）。
        #
        # 所以按分数分档：
        #   score >= coverage_band → 高相似度本身已足够可信，直接采信
        #   score <  coverage_band → 疑似命中，再要求覆盖率达标
        if hits and self.cfg.require_keyword_coverage:
            band = self.cfg.coverage_band
            filtered = [
                h for h in hits
                if h.score >= band
                or keyword_coverage(query, h.chunk.text) >= self.cfg.min_coverage
            ]
            if not filtered:
                return [], False
            hits = filtered

        grounded = bool(hits)
        return hits, grounded

    @staticmethod
    def _dedup(hits: List[Hit]) -> List[Hit]:
        """同一文档的相邻块只保留得分最高的那个。

        为什么需要：chunk_overlap 会让相邻块内容高度重叠，
        如果 top-5 里有 3 块来自同一位置，等于浪费了上下文预算，
        也会让答案看起来"只有一条依据"。
        """
        kept: List[Hit] = []
        taken = set()
        for h in hits:
            c = h.chunk
            key = (c.doc_id, c.chunk_index)
            if key in taken:
                continue
            # 与已选中的同文档块序号相差 1 以内视为相邻，跳过
            if any(c.doc_id == k2[0] and abs(c.chunk_index - k2[1]) <= 1 for k2 in taken):
                continue
            taken.add(key)
            kept.append(h)
        return kept
