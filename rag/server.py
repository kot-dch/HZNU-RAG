"""FastAPI 服务：把 RAG 能力暴露成 HTTP 接口。

启动：
    cd rag
    python -m rag.server
    # 或
    uvicorn rag.server:app --host 127.0.0.1 --port 8000 --reload

接口：
    GET  /health          健康检查
    GET  /info            索引与链路信息
    POST /ask             问答（检索 + 生成 + 引用）
    POST /retrieve        只检索不生成（调参用）
    POST /rebuild         重建索引
    GET  /docs            Swagger 交互文档（FastAPI 自带）
"""
from __future__ import annotations

import time
from typing import List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .config import CONFIG, describe
from .pipeline import RagPipeline

app = FastAPI(
    title='校园知识问答助手 API',
    description='基于 RAG 的杭州师范大学校园文档问答服务',
    version='1.0.0',
)

# 允许小程序 / 本地网页调用
app.add_middleware(
    CORSMiddleware,
    allow_origins=['*'],
    allow_methods=['*'],
    allow_headers=['*'],
)

# 索引在首次请求时懒加载，避免启动即失败（索引可能还没建）
_pipeline: Optional[RagPipeline] = None


def get_pipeline() -> RagPipeline:
    global _pipeline
    if _pipeline is None:
        try:
            _pipeline = RagPipeline.load()
        except FileNotFoundError as exc:
            raise HTTPException(status_code=503, detail=str(exc))
    return _pipeline


# ---------------------------------------------------------------- 请求模型

class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=500, description='用户问题')
    top_k: Optional[int] = Field(None, ge=1, le=20, description='返回片段数')
    threshold: Optional[float] = Field(None, ge=0.0, le=1.0, description='相似度阈值')


class RetrieveRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=500)
    top_k: Optional[int] = Field(None, ge=1, le=20)
    threshold: Optional[float] = Field(None, ge=0.0, le=1.0)


# ---------------------------------------------------------------- 接口

@app.get('/health', summary='健康检查')
def health():
    """返回服务状态。索引未就绪时 index_ready=False。"""
    try:
        pipe = get_pipeline()
        ready = True
        info = pipe.info()
    except HTTPException as exc:
        ready = False
        info = exc.detail
    return {
        'status': 'ok' if ready else 'degraded',
        'index_ready': ready,
        'info': info,
    }


@app.get('/info', summary='链路与索引信息')
def info():
    pipe = get_pipeline()
    store = pipe.store
    return {
        'chunks': len(store.chunks),
        'dim': int(store.vectors.shape[1]) if store.vectors.size else 0,
        'embed': store.embedder.describe(),
        'generator': pipe.generator.describe(),
        'top_k': pipe.retriever.cfg.top_k,
        'score_threshold': pipe.retriever.cfg.score_threshold,
        'coverage_band': pipe.retriever.cfg.coverage_band,
        'min_coverage': pipe.retriever.cfg.min_coverage,
        'config': describe(),
    }


@app.post('/ask', summary='问答（检索 + 生成 + 引用）')
def ask(req: AskRequest):
    pipe = get_pipeline()
    t0 = time.time()
    ans = pipe.ask(req.question, top_k=req.top_k, threshold=req.threshold)
    payload = ans.to_dict()
    payload['elapsed_ms'] = int((time.time() - t0) * 1000)
    return payload


@app.post('/retrieve', summary='只检索不生成')
def retrieve(req: RetrieveRequest):
    pipe = get_pipeline()
    t0 = time.time()
    hits = pipe.retrieve_only(req.question, top_k=req.top_k, threshold=req.threshold)
    return {
        'question': req.question,
        'count': len(hits),
        'hits': hits,
        'elapsed_ms': int((time.time() - t0) * 1000),
    }


@app.post('/rebuild', summary='重建索引（语料更新后调用）')
def rebuild(use_cleaner: bool = True):
    global _pipeline
    from .chunker import build_chunks, stats as chunk_stats
    from .store import VectorStore

    t0 = time.time()
    chunks = build_chunks(use_cleaner=use_cleaner)
    if not chunks:
        raise HTTPException(status_code=400, detail='语料为空，请先采集文档')
    store = VectorStore.build(chunks)
    store.save()
    _pipeline = RagPipeline(store)
    return {
        'ok': True,
        'chunks': len(chunks),
        'stats': chunk_stats(chunks),
        'embed': store.embedder.describe(),
        'elapsed_ms': int((time.time() - t0) * 1000),
    }


def main() -> None:
    """python -m rag.server 启动开发服务器。"""
    import uvicorn

    print(describe())
    print()
    print('服务地址：http://127.0.0.1:8000')
    print('交互文档：http://127.0.0.1:8000/docs')
    print()
    uvicorn.run(app, host='127.0.0.1', port=8000, log_level='info')


if __name__ == '__main__':
    main()
