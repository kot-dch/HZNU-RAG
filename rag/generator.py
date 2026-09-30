"""答案生成：把检索到的片段交给大模型，产出带出处的答案。

设计要点（这些都是"不是套壳"的证据）：

1. **强制引用**：要求模型用 [1][2] 标注依据，并在返回里附上出处列表。
   学生问的是校规，答错了后果比答不出更严重，所以必须可核对。

2. **强制拒答**：检索为空（低于阈值）时直接返回"没找到依据 + 建议找谁问"，
   绝不把问题丢给模型自由发挥。政策类问答编造的代价极高。

3. **上下文预算控制**：片段按分数降序拼接，超长时截断，避免超出模型窗口。

4. **无 Key 时的抽取式兜底**：没有大模型也能给出"相关原文 + 出处"，
   保证功能永不不可用，也方便离线演示。

提示词工程说明见 build_messages()。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional

from .config import CONFIG
from .store import Hit

# ---------------------------------------------------------------- 返回结构

REFUSE_TEXT = (
    '抱歉，我在校园公开文档里没有找到与这个问题相关的依据。\n\n'
    '建议你通过以下途径确认：\n'
    '· 教务处（学籍、选课、考试、毕业相关）\n'
    '· 党委学生工作部/学生处（奖助学金、评优、保险、宿舍）\n'
    '· 所在学院的辅导员或教务员\n\n'
    '（知识库只收录了学校官网公开的部分文档，未覆盖的内容不予猜测回答。）'
)


@dataclass
class Answer:
    """一次问答的完整结果。"""

    question: str
    grounded: bool                 # 检索是否找到依据
    answer: str                    # 给用户看的答案
    citations: List[dict] = field(default_factory=list)  # 出处
    hits: List[Hit] = field(default_factory=list)        # 命中的片段
    source: str = ''               # 'llm' | 'extractive' | 'refused'
    model: str = ''

    def to_dict(self) -> dict:
        return {
            'question': self.question,
            'grounded': self.grounded,
            'answer': self.answer,
            'citations': self.citations,
            'source': self.source,
            'model': self.model,
            'hits': [h.to_dict() for h in self.hits],
        }


# ---------------------------------------------------------------- 上下文拼装

# 单条片段最多塞多少字符，避免一条超长片段吃掉整个预算
MAX_CHUNK_CHARS = 700


def build_context(hits: List[Hit]) -> str:
    """把检索结果拼成带编号的上下文。编号与引用一一对应。"""
    blocks = []
    for i, h in enumerate(hits, 1):
        text = h.chunk.text.strip()
        if len(text) > MAX_CHUNK_CHARS:
            text = text[:MAX_CHUNK_CHARS] + '…'
        blocks.append(
            '[%d] 文档：%s\n栏目：%s\n内容：%s' % (i, h.chunk.title, h.chunk.section, text)
        )
    return '\n\n'.join(blocks)


def build_messages(question: str, hits: List[Hit]) -> List[dict]:
    """构造对话消息。

    提示词设计说明：
      · 角色：校园事务助手，不是通用助手 —— 决定了语气与边界
      · 硬约束：只依据给定材料作答；材料没有就说没有
      · 引用格式：要求 [编号]，且不许编造不存在于材料里的信息
      · 拒答分支：明确写出"材料不足以回答时应如何回复"，
        比只说"不要编造"更可执行
      · 输出形态：分点、简洁、直接给结论 —— 学生要的是能用的答案
    """
    context = build_context(hits)

    system = '\n'.join([
        '你是杭州师范大学的校园事务助手，帮学生查学校公开文档里的规定。',
        '',
        '必须遵守的规则：',
        '1. 只依据【参考材料】回答，不得使用材料之外的知识，不得推断或补充。',
        '2. 每一条结论后面用 [编号] 标注依据，如「转专业每学期只能申请一个志愿[3]」。',
        '3. 如果材料不足以回答问题，直接说明「材料中没有找到相关规定」，',
        '   并建议学生咨询教务处或辅导员，不要猜测。',
        '4. 不要编造条款号、金额、日期、比例等具体数字；材料里没有就不写。',
        '5. 回答用中文，条理清晰，先说结论，再列要点，必要时分点。',
        '6. 不要输出"根据参考材料"这类套话，直接给答案。',
    ])

    user = '\n'.join([
        '【参考材料】',
        context,
        '',
        '【学生的问题】',
        question,
    ])

    return [
        {'role': 'system', 'content': system},
        {'role': 'user', 'content': user},
    ]


# ---------------------------------------------------------------- 抽取式兜底

def extractive_answer(question: str, hits: List[Hit]) -> str:
    """没有大模型时的兜底：直接把最相关的原文摘出来，并标明出处。

    不能像大模型那样总结，但胜在**绝对忠实**——原文怎么写的就怎么给，
    对政策查询反而更可靠。
    """
    lines = ['没有接入大模型，下面直接给出知识库中最相关的原文片段：', '']
    for i, h in enumerate(hits, 1):
        text = h.chunk.text.strip()
        if len(text) > 420:
            text = text[:420] + '…'
        lines.append('【%d】%s' % (i, h.chunk.title))
        lines.append(text)
        lines.append('')
    lines.append('（把检索到的片段直接给你，未做归纳。配置 RAG_LLM_API_KEY 后可获得总结式回答。）')
    return '\n'.join(lines)


# ---------------------------------------------------------------- 大模型调用

def _call_llm(messages: List[dict], cfg) -> str:
    import requests

    url = cfg.base_url.rstrip('/') + '/chat/completions'
    resp = requests.post(
        url,
        headers={
            'Authorization': 'Bearer %s' % cfg.api_key,
            'Content-Type': 'application/json',
        },
        json={
            'model': cfg.model,
            'messages': messages,
            'temperature': cfg.temperature,
            'max_tokens': cfg.max_tokens,
            'stream': False,
        },
        timeout=cfg.timeout,
    )
    resp.raise_for_status()
    data = resp.json()
    content = ''
    try:
        content = data['choices'][0]['message']['content'] or ''
    except (KeyError, IndexError, TypeError):
        raise RuntimeError('模型返回结构异常：%s' % str(data)[:200])
    if not content.strip():
        raise RuntimeError('模型返回内容为空')
    return content.strip()


def clean_answer(text: str) -> str:
    """清掉模型偶尔带出的 Markdown 标记与前后缀。"""
    t = text.strip()
    t = re.sub(r'^```[\s\S]*?\n', '', t)
    t = t.replace('```', '')
    t = re.sub(r'^#+\s*', '', t, flags=re.M)
    t = t.replace('**', '')
    return t.strip()


# ---------------------------------------------------------------- 主类

class Generator:
    """RAG 的生成端。"""

    def __init__(self, cfg=None):
        self.cfg = cfg or CONFIG.llm
        self.use_llm = bool(self.cfg.api_key)

    def describe(self) -> str:
        if self.use_llm:
            return '大模型（%s @ %s）' % (self.cfg.model, self.cfg.base_url)
        return '抽取式兜底（未配置 RAG_LLM_API_KEY）'

    def generate(self, question: str, hits: List[Hit], grounded: bool) -> Answer:
        """生成答案。

        grounded=False 时直接拒答，不调用模型 —— 这是刻意的：
        让模型面对"没有材料的问题"，它一定会用训练数据里的通用知识编，
        而校规这种东西编出来是有害的。
        """
        citations = [{
            'index': i,
            'doc_id': h.chunk.doc_id,
            'title': h.chunk.title,
            'section': h.chunk.section,
            'url': h.chunk.url,
            'chunk_id': h.chunk.chunk_id,
            'score': round(h.score, 4),
        } for i, h in enumerate(hits, 1)]

        if not grounded or not hits:
            return Answer(
                question=question, grounded=False, answer=REFUSE_TEXT,
                citations=[], hits=[], source='refused',
            )

        if not self.use_llm:
            return Answer(
                question=question, grounded=True,
                answer=extractive_answer(question, hits),
                citations=citations, hits=hits, source='extractive',
            )

        messages = build_messages(question, hits)
        try:
            raw = _call_llm(messages, self.cfg)
            text = clean_answer(raw)
            if not text:
                raise RuntimeError('清洗后为空')
            return Answer(
                question=question, grounded=True, answer=text,
                citations=citations, hits=hits,
                source='llm', model=self.cfg.model,
            )
        except Exception as exc:
            # 模型不可用时退回抽取式，保证服务不中断
            print('[generator] 大模型调用失败，降级为抽取式：%s' % exc)
            return Answer(
                question=question, grounded=True,
                answer=extractive_answer(question, hits),
                citations=citations, hits=hits, source='extractive',
            )
