"""文本向量化。

提供两条实现路径，对外接口一致：

1. **API 模式**：配置 RAG_EMBED_API_KEY 后走真实 embedding 模型。
   语义泛化能力好，能处理"挂科" ↔ "考核不合格"这类同义改写。

2. **本地 n-gram 模式**（默认，无需任何 Key）：
   用字符 n-gram 做特征哈希（hashing trick）得到确定性向量。
   原理和经典文本检索里的向量空间模型一致，只是把稀疏词袋
   压成固定维度稠密向量。

   它的短板是**只做字面匹配**，同义改写会漏。但对校园制度类文档
   （用户提问用词和文档用词高度重合，比如"转专业""奖学金""助学贷款"）
   实测召回是可用的，而且带来了两个真实好处：
     - 完全离线、零成本、可复现：换个参数立刻能重跑对比
     - 不依赖外部服务，演示时不会因为网络或额度翻车

   所以整条链路（切分→清洗→检索→生成→评测）都能先跑通，
   之后配上 Key 就自动升级为语义检索，代码零改动。
"""
from __future__ import annotations

import hashlib
import math
import re
import unicodedata
from typing import List, Sequence

import numpy as np

from .config import CONFIG

# ---------------------------------------------------------------- 文本归一化

_PUNCT = re.compile(r'[\s\u3000]+')
# 全角转半角常用符号，减少表述差异带来的匹配损失
_FULL2HALF = {
    '（': '(', '）': ')', '，': ',', '。': '.', '；': ';', '：': ':',
    '？': '?', '！': '!', '、': ',', '“': '"', '”': '"', '‘': "'", '’': "'",
    '《': '<', '》': '>', '〔': '(', '〕': ')', '—': '-', '－': '-',
}


def normalize(text: str) -> str:
    """归一化：去多余空白、统一标点、英文字母小写。"""
    if not text:
        return ''
    s = unicodedata.normalize('NFKC', text)
    for a, b in _FULL2HALF.items():
        s = s.replace(a, b)
    s = _PUNCT.sub(' ', s)
    return s.strip().lower()


def char_ngrams(text: str, n_min: int, n_max: int) -> List[str]:
    """提取字符 n-gram。

    中文没有天然空格分词，字符 n-gram 是最稳的免分词方案：
    既保留单字信息（n=1），又能捕捉"转专业""助学贷款"这类词的搭配（n=2,3）。
    """
    s = normalize(text)
    if not s:
        return []
    grams: List[str] = []
    # 只在连续非空白段上取 n-gram，避免跨词边界产生无意义组合
    for chunk in s.split(' '):
        if not chunk:
            continue
        L = len(chunk)
        for n in range(n_min, n_max + 1):
            if n > L:
                break
            for i in range(L - n + 1):
                grams.append(chunk[i:i + n])
    return grams


def _stable_hash(token: str) -> int:
    """用 blake2b 而不是内置 hash()，因为后者在各进程间不稳定，
    会导致索引与查询落在不同的桶上（这是个很容易踩的坑）。"""
    h = hashlib.blake2b(token.encode('utf-8'), digest_size=8).digest()
    return int.from_bytes(h, 'big')


def local_embed(text: str, dim: int, n_min: int, n_max: int) -> np.ndarray:
    """特征哈希 + 带符号累加，得到 L2 归一化后的稠密向量。

    带符号（把哈希拆成"落到哪个桶"和"+1/-1"两部分）是为了抵消哈希冲突带来的
    系统性偏差——这是 hashing trick 的标准做法。
    """
    vec = np.zeros(dim, dtype=np.float32)
    grams = char_ngrams(text, n_min, n_max)
    if not grams:
        return vec

    for g in grams:
        h = _stable_hash(g)
        idx = h % dim
        sign = 1.0 if (h >> 63) & 1 else -1.0
        # 长 n-gram 权重更高：它携带的信息比单字更具体
        vec[idx] += sign * (1.0 + 0.5 * (len(g) - n_min))

    # 词频饱和：出现次数多的特征不该无限放大（类似 BM25 的思路）
    vec = np.sign(vec) * np.log1p(np.abs(vec))

    norm = float(np.linalg.norm(vec))
    if norm > 0:
        vec /= norm
    return vec


# ---------------------------------------------------------------- 对外接口

class Embedder:
    """向量化器。根据是否配置 API Key 自动选择实现。"""

    def __init__(self, cfg=None):
        self.cfg = cfg or CONFIG.embed
        self.mode = 'api' if self.cfg.api_key else 'local'
        self.dim = self.cfg.local_dim if self.mode == 'local' else None
        # API 模式下第一次调用才知道真实维度
        self._api_dim: int = 0
        self._api_failed = False

    # ------------------------------ API 路径

    def _api_embed_batch(self, texts: Sequence[str]) -> np.ndarray:
        import requests  # 延迟导入，离线模式不依赖

        url = self.cfg.base_url.rstrip('/') + '/embeddings'
        resp = requests.post(
            url,
            headers={
                'Authorization': 'Bearer %s' % self.cfg.api_key,
                'Content-Type': 'application/json',
            },
            json={'model': self.cfg.model, 'input': list(texts)},
            timeout=self.cfg.timeout,
        )
        resp.raise_for_status()
        data = resp.json()
        items = data.get('data') or []
        if not items:
            raise RuntimeError('向量化接口返回为空：%s' % str(data)[:200])
        items = sorted(items, key=lambda x: x.get('index', 0))
        arr = np.array([it['embedding'] for it in items], dtype=np.float32)
        norm = np.linalg.norm(arr, axis=1, keepdims=True)
        norm[norm == 0] = 1.0
        return arr / norm

    # ------------------------------ 统一入口

    def encode(self, texts: Sequence[str], batch_size: int = 32) -> np.ndarray:
        """把一批文本编码成 (n, dim) 的归一化向量矩阵。"""
        texts = list(texts)
        if not texts:
            return np.zeros((0, 0), dtype=np.float32)

        if self.mode == 'api' and not self._api_failed:
            try:
                out = []
                for i in range(0, len(texts), batch_size):
                    out.append(self._api_embed_batch(texts[i:i + batch_size]))
                mat = np.vstack(out)
                self._api_dim = mat.shape[1]
                self.dim = self._api_dim
                return mat
            except Exception as exc:  # 网络/额度/模型名错误都退化为本地
                print('[embedder] API 向量化失败，自动降级为本地 n-gram：%s' % exc)
                self._api_failed = True
                self.mode = 'local'
                self.dim = self.cfg.local_dim

        dim = self.cfg.local_dim
        return np.vstack([
            local_embed(t, dim, self.cfg.ngram_min, self.cfg.ngram_max)
            for t in texts
        ]).astype(np.float32)

    def encode_one(self, text: str) -> np.ndarray:
        return self.encode([text])[0]

    def describe(self) -> str:
        if self.mode == 'api':
            return 'API embedding（%s）' % self.cfg.model
        if self._api_failed:
            return '本地 n-gram（API 调用失败后降级）dim=%d' % self.cfg.local_dim
        return '本地 n-gram（离线，无需 Key）dim=%d' % self.cfg.local_dim
