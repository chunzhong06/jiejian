"""现有docs入口的只读上下文操作，不生成常驻知识或自动执行下一步。"""
import argparse
import json
import sys
from pathlib import Path

if __package__ in {None, ''}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.docs.reading import Reader, digest, read_context
from scripts.docs.task_records import TASK_FORMAT, check_task, load_json, resume_task


def rendered_text(result):
    return ''.join('# 来源：' + p['ref'] + '\n' + p['text'] + ('' if p['text'].endswith('\n') else '\n')
                   for p in result['passages'])


def page_text(text, cursor=None, budget=6000):
    """游标绑定本次完整选择的内容；输出只按段落/行分段，不丢弃后续契约。"""
    if budget < 256:
        raise ValueError('每段预算至少256字符')
    identity = digest(text)
    start = 0
    if cursor:
        offset, separator, expected = cursor.partition(':')
        if not separator or expected != identity or not offset.isdecimal():
            raise ValueError('读取游标过期或无效，重新读取当前内容')
        start = int(offset)
        if not 0 < start < len(text):
            raise ValueError('读取游标越界')
    end = min(start + budget, len(text))
    if end < len(text):
        boundary = text.rfind('\n\n', start + 1, end)
        if boundary < 0:
            boundary = text.rfind('\n', start + 1, end)
        if boundary >= 0:
            end = boundary + 1
    return dict(text=text[start:end], complete=end == len(text), start=start, end=end,
        total_chars=len(text), next_cursor=None if end == len(text) else str(end) + ':' + identity)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[2])
    commands = parser.add_subparsers(dest='command', required=True)
    read = commands.add_parser('read', help='合并路由、语义章节或准确源码声明')
    read.add_argument('--route', action='append', default=[])
    read.add_argument('--ref', action='append', default=[])
    read.add_argument('--source')
    read.add_argument('--implement', action='store_true')
    read.add_argument('--seen', help='仅限正文仍在当前上下文时提供上一读取回执')
    read.add_argument('--json', action='store_true', help='按需返回摘要、行段及可复用回执，默认只返回带来源的正文')
    read.add_argument('--cursor', help='沿用同一读取参数，继续上次未结束的分段')
    read.add_argument('--max-chars', type=int, default=6000, help='单次正文预算，默认6000字符；未返回部分必须继续读取')
    for name in ('resume', 'check-task'):
        command = commands.add_parser(name, epilog=TASK_FORMAT, formatter_class=argparse.RawDescriptionHelpFormatter)
        command.add_argument('--record', required=True)
        command.add_argument('--task', required=True)
        if name == 'resume':
            command.add_argument('--subject')
            command.add_argument('--property', dest='prop')
    args = parser.parse_args(argv)
    try:
        if args.command == 'read':
            seen = None
            if args.seen:
                document = load_json(Reader(args.root).read(args.seen)['text'])
                if document.get('schema_version') != '1' or document.get('document_type') != 'context_reading':
                    raise ValueError('未知上下文读取回执')
                seen = document['receipts']
                if not isinstance(seen, dict):
                    raise ValueError('读取回执无效')
            result = read_context(args.root, args.route, args.ref, args.source, args.implement, seen)
            page = page_text(rendered_text(result), args.cursor, args.max_chars)
        elif args.command == 'resume':
            result = resume_task(args.root, args.record, args.task, args.subject, args.prop)
        else:
            result = check_task(args.root, args.record, args.task)
    except (ValueError, OSError, KeyError, TypeError) as error:
        print('上下文读取失败：' + str(error), file=sys.stderr)
        return 1
    if args.command == 'read' and not args.json:
        print(page['text'], end='' if page['text'].endswith('\n') else '\n')
        if not page['complete']:
            print('尚未读完（' + str(page['end']) + '/' + str(page['total_chars']) + '）；保留相同参数，追加 --cursor ' + page['next_cursor'] + ' 继续。完成前不得将所选契约标为已读。')
        if not result['passages']:
            print('所选正文仍在本轮上下文，来源未变化。')
    else:
        if args.command == 'read':
            result['page'] = page
            # 不给未完整返回的正文发放可跳读回执；新上下文仍必须冷读。
            if page['start'] or not page['complete']:
                result['passages'], result['receipts'] = [], {}
            else:
                result['page'] = {key:value for key,value in page.items() if key != 'text'}
        print(json.dumps(result, ensure_ascii=False, indent=2))
    return 2 if result.get('status') in {'incomplete', 'paused'} else 0


if __name__ == '__main__':
    raise SystemExit(main())
