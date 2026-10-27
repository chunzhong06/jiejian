# 检查说明正文的本地链接、任务路由和独立可读性，不依赖历史清单。
import re
from urllib.parse import unquote,urlsplit
from scripts.docs.markdown import heading_ids,link_targets,without_fences

def check_documents(root):
    failures=[]
    paths=[root/'README.md',*(root/'docs').rglob('*.md'),root/'docs/llms.txt']
    for path in paths:
        if not path.is_file():failures.append(f'缺少文档：{path.relative_to(root)}');continue
        text=path.read_text('utf-8-sig')
        if 'var/audit' in text.replace(chr(92),'/'):
            failures.append(f'说明正文依赖临时审计目录：{path.relative_to(root)}')
        targets,missing=link_targets(text)
        for literal in re.findall(r'`((?:product|scripts|tests|docs)/[^`\n]+)`',without_fences(text)):
            if any(value in literal for value in ('*','<','{')) or re.search(r'\s',literal):continue
            relative=literal.split('::',1)[0]
            target=(root/relative).resolve()
            if not target.is_relative_to(root) or not target.exists():
                failures.append(f'无效源码引用：{path.relative_to(root)} -> {relative}')
        failures.extend(f'未定义文档引用：{path.relative_to(root)} -> {name}' for name in missing)
        for value in targets:
            value=value.strip().strip('<>')
            parsed=urlsplit(value)
            if parsed.scheme or parsed.netloc:continue
            target=(path.parent/unquote(parsed.path)).resolve() if parsed.path else path.resolve()
            if not target.is_relative_to(root) or not target.exists():
                failures.append(f'无效本地链接：{path.relative_to(root)} -> {value}')
            elif parsed.fragment and target.suffix=='.md' and unquote(parsed.fragment) not in heading_ids(target.read_text('utf-8-sig')):
                failures.append(f'无效标题锚点：{path.relative_to(root)} -> {value}')
        if path.name=='llms.txt':
            for relative in re.findall(r'docs/[^\s、，]+\.(?:md|txt)',text):
                if not (root/relative).is_file():failures.append(f'无效任务路由：{relative}')
    return failures
