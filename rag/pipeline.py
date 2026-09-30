"""RAG 主流程：把检索与生成串起来。

对外只暴露一个 ask()，页面 / API / CLI 都走它，保证行为一致。
"""
from __future__ import annotations

from typing import List, Optional

from .config import CONFIG
from .generator import Answer, Generator
from .store import Retriever, VectorStore


class RagPipeline:
    """检索增强生成流水线。

        pipe = RagPipeline.load()          # 载入已建好的索引
        ans = pipe.ask("转专业需要什么条件")
        print(ans.answer)
    """

    def __init__(self, store: VectorStore, retriever: Optional[Retriever] = None,
                 generator: Optional[Generator] = None):
        self.store = store
        self.retriever = retriever or Retriever(store, CONFIG.retrieve)
        self.generator = generator or Generator(CONFIG.llm)

    # ------------------------------ 构建

    @classmethod
    def load(cls) -> 'RagPipeline':
        return cls(VectorStore.load())

    @classmethod
    def build(cls, docs_dir=None, use_cleaner: bool = True) -> 'RagPipeline':
        from .chunker import build_chunks
        chunks = build_chunks(docs_dir, use_cleaner=use_cleaner)
        return cls(VectorStore.build(chunks))

    # ------------------------------ 问答

    def ask(self, question: str, top_k: int = None,
            threshold: float = None) -> Answer:
        question = (question or '').strip()
        if not question:
            return Answer(question=question, grounded=False,
                          answer='请先输入你的问题。', source='refused')

        hits, grounded = self.retriever.retrieve(question, top_k=top_k,
                                                threshold=threshold)
        return self.generator.generate(question, hits, grounded)

    def retrieve_only(self, question: str, top_k: int = None,
                      threshold: float = None) -> List[dict]:
        """只检索不生成，便于调参与前端展示来源。"""
        hits, _ = self.retriever.retrieve(question, top_k=top_k, threshold=threshold)
        return [h.to_dict() for h in hits]

    def info(self) -> str:
        return '\n'.join([
            self.store.info(),
            '  向量化：%s' % self.store.embedder.describe(),
            '  生成  ：%s' % self.generator.describe(),
            '  检索  ：top_k=%d  阈值=%.2f'
            % (self.retriever.cfg.top_k, self.retriever.cfg.score_threshold),
        ])
