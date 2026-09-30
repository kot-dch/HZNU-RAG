"""命令行问答入口。

    python -m rag.cli_ask "转专业需要什么条件"
    python -m rag.cli_ask                  # 进入交互模式
"""
from __future__ import annotations

import argparse
import sys

from .pipeline import RagPipeline


def print_answer(ans) -> None:
    print('─' * 74)
    print('问：%s' % ans.question)
    print()
    if not ans.grounded:
        print('【未找到依据】')
        print(ans.answer)
    else:
        print(ans.answer)
    if ans.citations:
        print()
        print('出处：')
        for c in ans.citations:
            print('  [%d] %s  (%s)' % (c['index'], c['title'], c['doc_id']))
            if c.get('url'):
                print('      %s' % c['url'])
    print()
    print('（来源：%s%s）' % (ans.source, (' / ' + ans.model) if ans.model else ''))
    print('─' * 74)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description='校园知识问答助手')
    ap.add_argument('question', nargs='*', help='要问的问题')
    ap.add_argument('-k', '--top-k', type=int, default=None)
    ap.add_argument('-t', '--threshold', type=float, default=None)
    ap.add_argument('--quiet', action='store_true', help='不打印索引信息')
    args = ap.parse_args(argv)

    try:
        pipe = RagPipeline.load()
    except FileNotFoundError as exc:
        print(exc, file=sys.stderr)
        return 1

    if not args.quiet:
        print(pipe.info())
        print()

    q = ' '.join(args.question).strip()
    if q:
        print_answer(pipe.ask(q, top_k=args.top_k, threshold=args.threshold))
        return 0

    print('输入问题回车即可（输入 q 退出）')
    while True:
        try:
            line = input('\n> ').strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if line.lower() in ('q', 'quit', 'exit'):
            break
        if not line:
            continue
        print_answer(pipe.ask(line, top_k=args.top_k, threshold=args.threshold))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
