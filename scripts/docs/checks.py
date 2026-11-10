# 检查说明正文的本地链接、任务路由和独立可读性，不依赖历史清单。
import re
from urllib.parse import unquote,urlsplit
from scripts.docs.markdown import heading_ids,link_targets,without_fences

def check_documents(root):
    failures=[]
    paths=[root/'README.md',*(root/'docs').rglob('*.md'),root/'docs/llms.txt']
    contents={}
    anchors={}
    def read(path):
        if path not in contents:contents[path]=path.read_text('utf-8-sig')
        return contents[path]
    def check_target(path,value,base,route=False):
        value=value.strip().strip('<>')
        parsed=urlsplit(value)
        label='任务路由' if route else '本地链接'
        if parsed.scheme or parsed.netloc:
            if route:failures.append(f'任务路由必须指向仓库文档：{path.relative_to(root)} -> {value}')
            return
        target=(base/unquote(parsed.path)).resolve() if parsed.path else path.resolve()
        if route and (not target.is_relative_to(root/'docs') or target.suffix not in {'.md','.txt'}):
            failures.append(f'任务路由必须指向仓库文档：{path.relative_to(root)} -> {value}')
        elif not target.is_relative_to(root) or not target.exists() or (route and not target.is_file()):
            failures.append(f'无效{label}：{path.relative_to(root)} -> {value}')
        elif parsed.fragment and target.suffix=='.md':
            if target not in anchors:anchors[target]=heading_ids(read(target))
            if unquote(parsed.fragment) not in anchors[target]:
                failures.append(f'无效标题锚点：{path.relative_to(root)} -> {value}')
    for path in paths:
        if not path.is_file():failures.append(f'缺少文档：{path.relative_to(root)}');continue
        text=read(path)
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
            check_target(path,value,path.parent,route=path.name=='llms.txt')
        if path.name=='llms.txt':
            # 旧的仓库相对路径继续接受；章节片段与 Markdown 链接一样校验。
            prose=without_fences(text)
            raw_pattern=r'(?<![\w/])docs/[^\s、，；;。)\]`<>]+'
            for relative in re.findall(raw_pattern,prose):
                check_target(path,relative,root,route=True)
            for number,line in enumerate(prose.splitlines(),1):
                line=line.strip().removeprefix('- ').strip()
                invalid=False
                if '→' in line:
                    trigger,destinations=line.split('→',1)
                    linked,_=link_targets(destinations)
                    invalid=not trigger.strip() or not (linked or re.findall(raw_pattern,destinations))
                elif line.startswith('['):
                    # 单目标入口直接用触发说明作链接文字；空说明或断开的链接仍拒绝。
                    match=re.match(r'\[([^]]*)\]\(',line)
                    invalid=not match or not match[1].strip() or not link_targets(line)[0]
                if invalid:
                    failures.append(f'任务路由缺少触发条件或文档目标：{path.relative_to(root)}:{number}')
    return failures
