# 按当前源码生成模块与契约参考，默认只读校验；说明正文由人工编写。
import argparse
import os
import sys
from pathlib import Path

if __package__ in {None,''}:sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from scripts.docs.sources import modules,routes,schemas,migrations
from scripts.docs.checks import check_documents
from scripts.quality.catalog import AREAS

def render(root):
    output={}
    index=['# 模块索引','','本页从当前源码静态提取文件、行数和顶层公开声明，用于定位所有者。列表不表示完整调用关系或运行验收。','','[架构说明](../工程/架构.md)']
    section=None
    for name,lines,names in modules(root):
        parts=Path(name).parts
        group='/'.join(parts[:3] if parts[1] in {'backend','frontend'} else parts[:2])
        if group!=section:
            section=group
            index+=['',f'## {group}','','| 文件 | 行数 | 公开声明 |','| --- | ---: | --- |']
        symbols='、'.join(names[:8])+('等' if len(names)>8 else '')
        index.append(f'| [{name}](../../{name}) | {lines} | {symbols or "包、内部机制或样式"} |')
    output['docs/参考/模块索引.md']='\n'.join(index)+'\n'
    contract=['# 接口与协议','','本页静态提取 HTTP 声明和 Schema 注册。调用条件见[本地接口](本地接口.md)，迁移另见[数据库修订](数据库修订.md)。HTTP 表不代替鉴权、前置条件和 OpenAPI；声明是否实际装配需沿接口组合入口核对。','','## HTTP 接口','','| 方法 | 路径 | 声明位置 |','| --- | --- | --- |']
    for method,path,owner,name in routes(root):
        contract.append(f'| {method} | `{path}` | [{name}](../../{owner}) |')
    contract+=['','## 协议声明','','注册表包含独立根文档、联合格式与可复用组件。根版本从 Schema 的显式版本约束提取；横线表示本声明不直接约束根版本，联合分支需打开 Schema 查阅。格式一致性由 Schema 命令验证，兼容决策见[协议与持久化](../工程/协议与持久化.md)。','','| 格式 | 根版本 | 实际声明 |','| --- | --- | --- |']
    for name,owner,versions in schemas(root):
        version='、'.join(f'`{value}`' for value in versions) or '—'
        contract.append(f'| [{name}](../../product/protocols/schemas/{name}) | {version} | `{owner}` |')
    output['docs/参考/接口与协议.md']='\n'.join(contract)+'\n'
    history=['# 数据库修订','','本页从签入迁移静态提取修订、前驱和职责。编号属于数据库历史，与产品版本独立。当前支持范围、升级与维护步骤见[数据库与迁移](../工程/数据库与迁移.md)。','','| 修订 | 前驱 | 用途 | 声明 |','| --- | --- | --- | --- |']
    for revision,parent,name in migrations(root):
        purpose=next((line.lstrip('# ').strip() for line in (root/name).read_text('utf-8-sig').splitlines() if line.startswith('#') and line.lstrip('# =-').strip()),'见迁移操作')
        history.append(f'| `{revision}` | {"`"+parent+"`" if parent else "基线"} | {purpose} | [{Path(name).name}](../../{name}) |')
    output['docs/参考/数据库修订.md']='\n'.join(history)+'\n'
    verification=['# 验证范围','','本页从验证目录生成，列出可选择的契约及实际步骤。范围不是完整影响分析，等级也不要求逐级跑满。选择方法见[测试与验证](../工程/测试.md)。','','`verify --area 名称` 默认展示计划；追加 `--run` 才执行。`--all` 不含真实场景，L5 独立交付另行约定。']
    for name,area in AREAS.items():
        verification+=['',f'## {name}','',area.purpose+'。','']
        for title,paths in [('源码范围',area.source),('后端契约',area.backend),('前端契约',tuple('product/frontend/'+path for path in area.frontend))]:
            if paths:verification.append(title+'：'+'、'.join(f'[{path}](../../{path})' for path in paths)+'。')
        level=4 if area.journey else max(area.backend_level if area.backend else 1,2 if area.frontend else 1)
        verification+=['',f'本地契约默认选择至 L{level}。下方命令查看计划，追加 --run 才执行。普通范围排除标记为 level4 的进程场景；未执行的场景不能算作通过。','', '```text']
        verification+=[f'powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File .\\scripts\\dev.ps1 verify --area {name} --level L{level}']
        verification+=['```']
    output['docs/参考/验证范围.md']='\n'.join(verification)+'\n'
    return output

def generate(root,update=False):
    root=root.resolve()
    documents=render(root)
    changed=[]
    for name,text in documents.items():
        path=root/name
        if path.is_symlink() or not path.resolve().is_relative_to(root/'docs/参考'):raise ValueError('生成路径越界')
        if path.exists() and path.read_text('utf-8')==text:continue
        changed.append(name)
        if update:
            path.parent.mkdir(parents=True,exist_ok=True)
            temporary=path.with_suffix('.tmp')
            temporary.write_text(text,encoding='utf-8',newline='\n')
            os.replace(temporary,path)
    failures=check_documents(root)
    if changed and not update:failures.extend('静态参考需要更新：'+name for name in changed)
    if failures:raise ValueError('\n'.join(failures))
    return changed

def main():
    parser=argparse.ArgumentParser(description='检查说明链接与当前源码参考')
    parser.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[2])
    parser.add_argument('--update',action='store_true')
    args=parser.parse_args()
    try:
        changed=generate(args.root,args.update)
    except (ValueError,OSError,SyntaxError) as error:
        print(str(error),file=sys.stderr);return 1
    print(f'文档检查通过，更新 {len(changed) if args.update else 0} 份静态参考')
    return 0

if __name__=='__main__':raise SystemExit(main())
