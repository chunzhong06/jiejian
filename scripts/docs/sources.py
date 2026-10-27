# 静态提取当前模块、HTTP声明、公共格式与迁移元数据，不执行产品。
import ast
import json
import re
from pathlib import Path

IGNORED={'__pycache__','node_modules','dist','coverage'}
SUFFIXES={'.py','.ts','.tsx','.css','.ps1','.cmd','.mjs','.cjs','.c'}

def tree(path):
    return ast.parse(path.read_text('utf-8-sig'),filename=str(path))

def literal(node):
    try:return ast.literal_eval(node)
    except (ValueError,TypeError):return None

def modules(root):
    result=[]
    for folder in ('product/backend','product/frontend/src','product/frontend/tooling','product/protocols','product/launcher','scripts'):
        for path in sorted((root/folder).rglob('*')):
            if not path.is_file() or path.suffix not in SUFFIXES or set(path.parts)&IGNORED:continue
            if '.test.' in path.name or '.fixtures.' in path.name or 'testing' in path.parts:continue
            if path.is_symlink():raise ValueError('源码索引拒绝链接')
            text=path.read_text('utf-8-sig')
            if path.suffix=='.py':
                names=[n.name for n in tree(path).body if isinstance(n,(ast.ClassDef,ast.FunctionDef,ast.AsyncFunctionDef)) and not n.name.startswith('_')]
            else:
                names=sorted(set(re.findall(r'\bexport\s+(?:default\s+)?(?:async\s+)?(?:function|class|const|type|interface)\s+(\w+)',text)))
            result.append((path.relative_to(root).as_posix(),len(text.splitlines()),names))
    return result

def routes(root):
    rows=[]
    for path in sorted((root/'product/backend/interfaces/http/routers').rglob('*.py')):
        parsed=tree(path)
        constants={target.id:literal(node.value) for node in ast.walk(parsed) if isinstance(node,ast.Assign) for target in node.targets if isinstance(target,ast.Name) and isinstance(literal(node.value),str)}
        def route_value(node):
            value=literal(node)
            if isinstance(value,str):return value
            if isinstance(node,ast.JoinedStr):
                parts=[]
                for part in node.values:
                    if isinstance(part,ast.Constant):parts.append(part.value)
                    elif isinstance(part,ast.FormattedValue) and isinstance(part.value,ast.Name) and part.value.id in constants:parts.append(constants[part.value.id])
                    else:return None
                return ''.join(parts)
            return None
        prefixes={}
        for node in ast.walk(parsed):
            if isinstance(node,ast.Assign) and isinstance(node.value,ast.Call) and isinstance(node.value.func,ast.Name) and node.value.func.id=='APIRouter':
                prefix=next((literal(k.value) for k in node.value.keywords if k.arg=='prefix'),'')
                for target in node.targets:
                    if isinstance(target,ast.Name):prefixes[target.id]=prefix
        for node in ast.walk(parsed):
            if not isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef)):continue
            for decorator in node.decorator_list:
                if not isinstance(decorator,ast.Call) or not isinstance(decorator.func,ast.Attribute) or decorator.func.attr not in {'get','post','put','patch','delete'}:continue
                endpoint=route_value(decorator.args[0]) if decorator.args else None
                prefix=prefixes.get(decorator.func.value.id,'') if isinstance(decorator.func.value,ast.Name) else None
                location=path.relative_to(root).as_posix()
                rows.append((decorator.func.attr.upper(),prefix+endpoint if isinstance(prefix,str) and isinstance(endpoint,str) else '动态路径，需读源码',location,node.name))
    return sorted(rows)

def schemas(root):
    parsed=tree(root/'product/protocols/schema.py')
    entries=next(n.value for n in parsed.body if isinstance(n,(ast.Assign,ast.AnnAssign)) and any(isinstance(t,ast.Name) and t.id=='SCHEMA_REGISTRY' for t in (n.targets if isinstance(n,ast.Assign) else [n.target])))
    if not isinstance(entries,(ast.Tuple,ast.List)):raise ValueError('协议注册表必须可静态读取')
    rows=[]
    for node in entries.elts:
        name,owner=map(literal,node.args[:2])
        path=root/'product/protocols/schemas'/name
        schema=json.loads(path.read_text('utf-8'))
        version=schema.get('properties',{}).get('schema_version',{})
        values=[version['const']] if 'const' in version else version.get('enum',[])
        rows.append((name,owner,tuple(str(value) for value in values)))
    actual={p.relative_to(root/'product/protocols/schemas').as_posix() for p in (root/'product/protocols/schemas').rglob('*.schema.json')}
    if actual!={name for name,_,_ in rows}:raise ValueError('协议注册与Schema文件不一致')
    return sorted(rows)

def migrations(root):
    rows=[]
    for path in sorted((root/'product/backend/migrations/versions').glob('*.py')):
        values={}
        for node in tree(path).body:
            if isinstance(node,(ast.Assign,ast.AnnAssign)):
                for target in node.targets if isinstance(node,ast.Assign) else [node.target]:
                    if isinstance(target,ast.Name) and target.id in {'revision','down_revision'}:values[target.id]=literal(node.value)
        if 'revision' in values:rows.append((values['revision'],values.get('down_revision'),path.relative_to(root).as_posix()))
    parents={revision:parent for revision,parent,_ in rows}
    heads=set(parents)-set(parents.values())
    if len(parents)!=len(rows) or len(heads)!=1:raise ValueError('迁移链标识或head异常')
    visited=set();current=next(iter(heads))
    while current is not None:
        if current in visited or current not in parents:raise ValueError('迁移链循环或前驱缺失')
        visited.add(current);current=parents[current]
    if len(visited)!=len(rows):raise ValueError('迁移链不连通')
    return rows
