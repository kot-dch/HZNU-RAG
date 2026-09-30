"""校园知识问答助手（RAG）配置。

所有可调参数集中在这里，方便实验对比。

环境变量（可选，不配也能跑）：
    RAG_LLM_API_KEY    大模型 API Key
    RAG_LLM_BASE_URL   接口地址，默认 DeepSeek
    RAG_LLM_MODEL      模型名，默认 deepseek-chat
    RAG_EMBED_API_KEY  向量化 API Key，不配则用本地确定性向量
    RAG_EMBED_BASE_URL 向量化接口地址
    RAG_EMBED_MODEL    向量化模型名
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

# ---------------------------------------------------------------- 路径

RAG_ROOT = Path(__file__).resolve().parent          # <repo>/rag/rag   （包目录）
PKG_PARENT = RAG_ROOT.parent                        # <repo>/rag
_TOP = PKG_PARENT.parent                            # 再上一层，可能是仓库根，也可能不是


def _pick_dir(candidates):
    """从候选路径里挑第一个"看起来像语料目录"的，都不满足则返回第一候选。

    为什么要自适应而不是写死：
    本项目原本挂在另一个工程里，语料位于 `<工程>/data/docs`（包的"上两级"）。
    独立成仓库后语料位于 `<仓库>/data/docs`（包的"上一级"）。
    写死任一种布局，另一种都会报"语料目录不存在"——这是克隆后跑不起来的
    最常见原因。所以按优先级探测：
        1. 环境变量 RAG_DOCS_DIR（显式指定最优先）
        2. <repo>/data/docs            ← 独立仓库布局
        3. <repo>/rag/data/docs
        4. <repo>/../data/docs         ← 内置在其他工程里时的布局
    判定标准：目录存在，且里面有 .txt 文件（或存在 docs 子目录）。
    """
    for c in candidates:
        p = Path(c)
        if not p.is_dir():
            continue
        try:
            if any(f.suffix.lower() == '.txt' for f in p.iterdir() if f.is_file()):
                return p
        except OSError:
            continue
    for c in candidates:
        p = Path(c)
        if p.is_dir():
            return p
    return Path(candidates[0])


_env_docs = os.environ.get('RAG_DOCS_DIR')
if _env_docs:
    DOCS_DIR = Path(_env_docs)
else:
    DOCS_DIR = _pick_dir([
        _TOP / 'data' / 'docs',                 # 独立仓库：<repo>/data/docs
        PKG_PARENT / 'data' / 'docs',           # <repo>/rag/data/docs
        _TOP.parent / 'data' / 'docs',          # 内置在其他工程里
    ])

# REPO_ROOT：取语料目录所在的那一层作为仓库根。
# 不直接写 _TOP，是因为包目录多套了一层（<repo>/rag/rag），
# 算出来的"上一级"未必是仓库根——(DOCS_DIR.parent).parent 才是可靠来源。
REPO_ROOT = DOCS_DIR.parent.parent

# 索引与评测产物的落盘目录（生成物，不入版本库）
ARTIFACT_DIR = Path(os.environ.get('RAG_ARTIFACT_DIR', RAG_ROOT / 'data'))
EVAL_DIR = RAG_ROOT / 'eval'


# ---------------------------------------------------------------- 切分

@dataclass
class ChunkConfig:
    """切分策略。

    中文校园文档的特点：条款以「第X条」「一、」「（一）」这类标记开头，
    所以优先在标记处切，其次才按句子/长度硬切。
    一篇文档的上下文靠 metadata（doc_id + chunk_index）保留。
    """

    # 目标块大小（字符）。中文按字符计：500 字约等于 350~400 token
    chunk_size: int = 500
    # 相邻块重叠，避免答案跨越切分边界时被截断
    chunk_overlap: int = 80
    # 小于这个长度不单独成块，并入前一块
    min_chunk_size: int = 120
    # 是否在条款标记处优先切分
    split_on_clause: bool = True


# ---------------------------------------------------------------- 检索

@dataclass
class RetrieveConfig:
    """检索参数。"""

    # 返回 top-k 个片段给大模型
    top_k: int = 5
    # 相似度阈值：低于该值认为"没找到依据"，触发拒答。
    #
    # 这个值不是拍脑袋定的，是用 cli_calibrate 实测标定出来的：
    # 用 10 个知识库里确有答案的问题 + 10 个库里没有答案的问题对比分数分布，
    # 本地 n-gram 向量下两组完全分开：
    #     有答案  min=0.1188  中位=0.1881  max=0.3285
    #     无答案  min=0.0544  中位=0.0806  max=0.1042
    # 取 0.11（介于 0.1042 与 0.1188 之间，略偏安全侧）。
    #
    # ⚠ 换成 API embedding 后分数尺度会变，必须重新跑 cli_calibrate 标定。
    score_threshold: float = 0.11
    # 是否对结果做去重（同一文档相邻块只留最相关的一个）
    dedup_adjacent: bool = True

    # ---- 第二道闸：关键词覆盖率（只作用于"低分带"）----
    # 光靠向量相似度会有"貌似相关"的假阳性（实测：问"怎么补办学生证"命中
    # 《平安保险须知》，分数 0.1191 刚好越线）。
    #
    # 但覆盖率不能一刀切 —— 实测发现高分段里存在覆盖率偏低却正确的结果
    # （"转专业每学期可以填几个志愿" 覆盖率仅 0.30，但命中文档完全正确），
    # 一刀切会误杀，实测把 Recall@5 从 100% 拉到 90%。
    #
    # 所以按分数分档：
    #     score >= coverage_band  → 高相似度本身够可信，直接采信
    #     score <  coverage_band  → 疑似命中，再要求覆盖率达标
    #
    # 实测效果（30 道库内题 + 12 道库外题）：Recall@5 100%、MRR 0.950、
    # 拒答准确率 91.7%（唯一漏网："怎么补办学生证" → 命中的《平安保险须知》
    # 正文里含"学生"二字，字面重叠导致覆盖率虚高。本地字面向量下难以消除，
    # 换语义 embedding 或补充语料才是正解）。详见 README「已知局限」。
    require_keyword_coverage: bool = True
    coverage_band: float = 0.25
    # 覆盖率下限：0.30 表示查询二元组里至少三成能在片段中找到
    min_coverage: float = 0.30


# ---------------------------------------------------------------- 向量化

@dataclass
class EmbedConfig:
    """向量化配置。

    两条路：
      1. API：配置 RAG_EMBED_API_KEY 后走真实 embedding 模型
      2. 本地：无需任何 Key，用字符 n-gram 特征哈希生成确定性向量
         质量不如真模型，但能让整条链路（切分→检索→生成→评测）
         在离线环境完整跑通，也便于做可复现的实验对比。
    """

    api_key: str = field(default_factory=lambda: os.environ.get('RAG_EMBED_API_KEY', ''))
    base_url: str = field(default_factory=lambda: os.environ.get(
        'RAG_EMBED_BASE_URL', 'https://api.deepseek.com/v1'))
    model: str = field(default_factory=lambda: os.environ.get(
        'RAG_EMBED_MODEL', 'embedding-2'))
    # 本地向量的维度
    local_dim: int = 2048
    # 本地向量的 n-gram 范围（中文用 1~3 字组合效果较稳）
    ngram_min: int = 1
    ngram_max: int = 3
    timeout: int = 20


# ---------------------------------------------------------------- 生成

@dataclass
class LLMConfig:
    """大模型配置。不配 Key 时自动降级为"抽取式回答"。"""

    api_key: str = field(default_factory=lambda: os.environ.get('RAG_LLM_API_KEY', ''))
    base_url: str = field(default_factory=lambda: os.environ.get(
        'RAG_LLM_BASE_URL', 'https://api.deepseek.com/v1'))
    model: str = field(default_factory=lambda: os.environ.get('RAG_LLM_MODEL', 'deepseek-chat'))
    temperature: float = 0.2          # 政策问答要稳，不要发散
    max_tokens: int = 700
    timeout: int = 30


@dataclass
class AppConfig:
    chunk: ChunkConfig = field(default_factory=ChunkConfig)
    retrieve: RetrieveConfig = field(default_factory=RetrieveConfig)
    embed: EmbedConfig = field(default_factory=EmbedConfig)
    llm: LLMConfig = field(default_factory=LLMConfig)


CONFIG = AppConfig()


def describe() -> str:
    """打印当前生效的配置，方便确认走的是哪条链路。"""
    c = CONFIG
    embed_mode = 'API' if c.embed.api_key else '本地 n-gram（离线）'
    llm_mode = 'API' if c.llm.api_key else '抽取式兜底（离线）'
    return '\n'.join([
        '当前 RAG 配置',
        '  语料目录      : %s' % DOCS_DIR,
        '  切分          : size=%d overlap=%d 条款优先=%s'
        % (c.chunk.chunk_size, c.chunk.chunk_overlap, c.chunk.split_on_clause),
        '  检索          : top_k=%d 阈值=%.2f 去重=%s'
        % (c.retrieve.top_k, c.retrieve.score_threshold, c.retrieve.dedup_adjacent),
        '  向量化        : %s' % embed_mode,
        '  生成          : %s' % llm_mode,
    ])
