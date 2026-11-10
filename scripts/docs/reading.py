"""从现有路由和语义标题读取正文；不维护索引副本，也不截断完整契约。"""
import hashlib
import re
from pathlib import Path
from urllib.parse import unquote, urlsplit

from scripts.docs.markdown import heading_rows

MAX_BYTES = 2 * 1024 * 1024


def digest(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


class Reader:
    def __init__(self, root):
        self.root = root.resolve()
        self.contents = {}

    def locate(self, reference):
        parsed = urlsplit(reference)
        if parsed.scheme or parsed.netloc or parsed.query:
            raise ValueError('只接受仓库内文档引用')
        relative = unquote(parsed.path).replace('\\', '/')
        path = (self.root / relative).resolve()
        if not path.is_relative_to(self.root):
            raise ValueError('文档引用越出仓库')
        name = path.relative_to(self.root).as_posix()
        if not (name in {'AGENTS.md', 'README.md'} or name.startswith(('docs/', 'var/'))):
            raise ValueError('上下文读取限于文档与任务运行记录')
        if path.suffix not in {'.md', '.txt', '.json'} or not path.is_file():
            raise ValueError('文档不存在或格式不受支持')
        return name, unquote(parsed.fragment)

    def text(self, name):
        if name not in self.contents:
            path = self.root / name
            if path.stat().st_size > MAX_BYTES:
                raise ValueError('文档超过2MiB；先按任务整理准确来源，不输出截断正文')
            self.contents[name] = path.read_text('utf-8-sig')
        return self.contents[name]

    def select(self, name, anchors=(), *, preface=True):
        text = self.text(name)
        lines = text.splitlines(keepends=True)
        rows = heading_rows(text)
        ranges = []
        if not anchors:
            ranges.append((0, len(lines)))
        else:
            if preface:
                ranges.append((0, next((i for i, level, _, _ in rows if level > 1), len(lines))))
            for anchor in anchors:
                found = next((r for r in rows if anchor in (r[2], r[3]) or anchor.casefold() == r[3]), None)
                if found is None:
                    raise ValueError('找不到文档章节：' + name + '#' + anchor)
                start, depth, _, _ = found
                stop = next((i for i, level, _, _ in rows if i > start and level <= depth), len(lines))
                ranges.append((start, stop))
        merged = []
        for start, stop in sorted(ranges):
            if merged and start <= merged[-1][1]:
                merged[-1] = (merged[-1][0], max(stop, merged[-1][1]))
            else:
                merged.append((start, stop))
        payload = ''.join(''.join(lines[start:stop]) for start, stop in merged)
        reference = name + ('#' + ','.join(sorted(anchors)) if anchors else '')
        return self.passage(reference, payload, [name], [[a + 1, b] for a, b in merged])

    def passage(self, reference, text, sources, ranges):
        return dict(ref=reference, text=text, sha256=digest(text),
            source_sha256=digest('\0'.join(self.text(p) for p in sources)), ranges=ranges)

    def read(self, reference):
        name, anchor = self.locate(reference)
        return self.select(name, [anchor] if anchor else [])

    def routes(self):
        result = {}
        for line in self.text('docs/llms.txt').splitlines():
            if '→' in line:
                label, body = line.split('→', 1)
            elif line.startswith('['):
                match = re.match(r'\[([^]]+)\]\(', line)
                if not match:
                    continue
                label, body = match[1], line
            else:
                continue
            targets = re.findall(r'\[[^]]+\]\(([^)]+)\)', body)
            result[label.strip()] = ['docs/' + target for target in targets]
        return result

    def source(self, source):
        """声明查询返回索引的证据前提及准确文件节，省去整张目录表。"""
        index_name = 'docs/参考/模块索引.md'
        index = self.text(index_name)
        matches = []
        for line in index.splitlines():
            match = re.match(r'\| `([^`]+)` \|.*?\[查看声明\]\(([^)]+)\)', line)
            if match and source.startswith(match[1] + '/'):
                matches.append((match[1], match[2]))
        if not matches:
            # 题面常只给目录后缀；只在声明索引中消歧，不读取或猜测真实源码。
            candidates = set()
            for target in re.findall(r'\[查看声明\]\(([^)]+)\)', index):
                page = (Path('docs/参考') / target).as_posix()
                self.locate(page)
                for candidate in re.findall(r'\[源码\]\(\.\./\.\./\.\./([^)]+)\)', self.text(page)):
                    if candidate == source or candidate.endswith('/' + source):
                        candidates.add(candidate)
            if len(candidates) != 1:
                raise ValueError('源码后缀缺失或不唯一，请提供更长路径')
            return self.source(next(iter(candidates)))
        prefix, target = max(matches, key=lambda pair: len(pair[0]))
        page = (Path('docs/参考') / target).as_posix()
        self.locate(page)
        title = source.removeprefix(prefix + '/')
        part = self.select(page, [title], preface=False)
        preface = index.split('|', 1)[0]
        premise = self.passage(index_name + '#声明前提', preface, [index_name], [])
        return [premise, part]


def read_context(root, routes=(), refs=(), source=None, implement=False, seen=None):
    reader = Reader(root)
    selected = []
    mapping = reader.routes()
    for label in routes:
        if label not in mapping:
            raise ValueError('未知任务入口；使用docs/llms.txt中的完整触发说明')
        selected.extend(mapping[label])
    if source:
        # 源码定位已返回索引前提；同次选择通用模块入口不再重复整张目录表。
        selected = [ref for ref in selected if ref != 'docs/参考/模块索引.md']
    selected.extend(refs)
    if source and implement:
        raise ValueError('声明查询不能代替实施契约；请按受影响所有者指定路由')
    if implement:
        selected.append('docs/工程/开发.md')
    grouped = {}
    for reference in selected:
        name, anchor = reader.locate(reference)
        grouped.setdefault(name, []).append('' if implement else anchor)
    parts = [reader.select(name, () if '' in anchors else sorted(set(anchors)))
             for name, anchors in grouped.items()]
    if source:
        parts.extend(reader.source(source))
    if not parts:
        raise ValueError('至少指定一个路由、文档引用或源码声明')
    receipts, returned = {}, []
    for part in parts:
        receipts[part['ref']] = part['source_sha256']
        if not seen or seen.get(part['ref']) != part['source_sha256']:
            returned.append(part)
    return dict(schema_version='1', document_type='context_reading', passages=returned,
        receipts=receipts, content_chars=sum(len(p['text']) for p in returned),
        document_reads=len(reader.contents), selected_owners_full=implement,
        note='实施仍须核对其他受影响所有者和直接消费者；静态参考不作运行证据。')
