# 静态投影真实注册和迁移元数据；只读取AST与签入Schema，不创建产品对象。
from __future__ import annotations

import ast
import json
from pathlib import Path

from scripts.docs.sources import parse_python


def _tree(root: Path, relative: str):
    path = root / relative
    return parse_python(path) if path.exists() else ast.Module(body=[], type_ignores=[])


def _constant(node):
    try:
        return ast.literal_eval(node)
    except (ValueError, TypeError):
        return None


def _imports(tree):
    return {alias.asname or alias.name: (node.module or '', alias.name)
            for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) for alias in node.names}


def api_routes(root: Path) -> list[tuple[str, str, str]]:
    """沿显式include_router工厂递归；只确认静态装配关系。"""
    rows, visited = [], set()
    def visit(relative, function, parent):
        key = (relative, function)
        if key in visited:
            return
        visited.add(key)
        tree = _tree(root, relative)
        imports = _imports(tree)
        scope = next((n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == function), None)
        if scope is None:
            rows.append((parent, f'{relative}::{function}', '未静态确定工厂定义'))
            return
        for node in ast.walk(scope):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute) or node.func.attr != 'include_router':
                continue
            argument = node.args[0] if node.args else None
            name = argument.func.id if isinstance(argument, ast.Call) and isinstance(argument.func, ast.Name) else None
            if name not in imports:
                rows.append((f'{relative}::{function}', ast.unparse(argument) if argument else '空参数', '未静态确定'))
                continue
            module, symbol = imports[name]
            target = module.replace('.', '/') + '.py'
            rows.append((f'{relative}::{function}', f'{target}::{symbol}', '显式挂载（执行条件需读源码）'))
            visit(target, symbol, relative)
    if (root / 'product/backend/api/app.py').exists():
        visit('product/backend/api/app.py', 'create_app', 'API根')
    return rows


def mcp_tools(root: Path) -> list[tuple[str, str]]:
    rows, visited = [], set()
    def visit(relative, function):
        if (relative, function) in visited:
            return
        visited.add((relative, function))
        tree = _tree(root, relative)
        scope = next((n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == function), None)
        if scope is None:
            raise ValueError(f'MCP注册入口缺失：{relative}::{function}')
        imports = _imports(tree)
        for node in ast.walk(scope):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for decorator in node.decorator_list:
                    if isinstance(decorator, ast.Call) and isinstance(decorator.func, ast.Attribute) and decorator.func.attr == 'tool':
                        value = next((_constant(k.value) for k in decorator.keywords if k.arg == 'name'), None)
                        rows.append((value if isinstance(value, str) else '未静态确定', f'{relative}::{node.name}'))
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id.startswith('register_') and node.func.id in imports:
                module, name = imports[node.func.id]
                visit(module.replace('.', '/') + '.py', name)
    if (root / 'product/backend/api/mcp/server.py').exists():
        visit('product/backend/api/mcp/server.py', 'build_mcp_control')
    names = [name for name, _ in rows if name != '未静态确定']
    if len(names) != len(set(names)):
        raise ValueError('MCP工具名重复')
    return sorted(rows)


def worker_branches(root: Path):
    rows = []
    locations = [('通用Worker', 'product/backend/infra/runtime/jobs/factory.py', 'build_registry'),
                 ('运行加载专用Worker', 'product/backend/infra/runtime/jobs/target_handlers/runtime_load.py', 'runtime_load_targets')]
    for label, relative, function in locations:
        tree = _tree(root, relative)
        scope = next((n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == function), None)
        if scope is None:
            continue
        for node in ast.walk(scope):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == 'register':
                values = [ast.unparse(arg) for arg in node.args]
                values.extend(f'{k.arg}={ast.unparse(k.value)}' for k in node.keywords)
                rows.append((label, '; '.join(values), relative))
    return rows


def root_versions(schema: dict) -> str:
    """只沿根联合及本地ref寻找根版本，不误取嵌套DTO的schema_version。"""
    values, seen = set(), set()
    def visit(node):
        reference = node.get('$ref')
        if reference and reference.startswith('#/') and reference not in seen:
            seen.add(reference)
            target = schema
            for key in reference[2:].split('/'):
                target = target[key.replace('~1', '/').replace('~0', '~')]
            visit(target)
        version = node.get('properties', {}).get('schema_version', {})
        if 'const' in version:
            values.add(str(version['const']))
        values.update(map(str, version.get('enum', [])))
        for kind in ('oneOf', 'anyOf', 'allOf'):
            for child in node.get(kind, []):
                visit(child)
    visit(schema)
    return ', '.join(sorted(values)) if values else '无可静态确认的根版本'


def schema_entries(root: Path):
    tree = _tree(root, 'product/protocols/schema.py')
    assignment = next((n for n in tree.body if isinstance(n, (ast.Assign, ast.AnnAssign)) and
                       any(isinstance(t, ast.Name) and t.id == 'SCHEMA_REGISTRY' for t in (n.targets if isinstance(n, ast.Assign) else [n.target]))), None)
    if assignment is None:
        return []
    if not isinstance(assignment.value, (ast.Tuple, ast.List)):
        raise ValueError('Schema注册表未静态确定')
    rows = []
    for call in assignment.value.elts:
        if not isinstance(call, ast.Call) or len(call.args) < 2:
            raise ValueError('Schema注册项未静态确定')
        relative, target = map(_constant, call.args[:2])
        if not isinstance(relative, str) or not isinstance(target, str):
            raise ValueError('Schema注册项必须是静态路径')
        path = (root / 'product/protocols/schemas' / relative).resolve()
        if not path.is_relative_to((root / 'product/protocols/schemas').resolve()):
            raise ValueError('Schema路径越界')
        schema = json.loads(path.read_text(encoding='utf-8'))
        rows.append((relative, target, root_versions(schema)))
    if len(rows) != len({r[0] for r in rows}):
        raise ValueError('Schema注册路径重复')
    actual = {p.relative_to(root / 'product/protocols/schemas').as_posix() for p in (root / 'product/protocols/schemas').rglob('*.schema.json')}
    if actual != {r[0] for r in rows}:
        raise ValueError('Schema文件与注册表不一致')
    return sorted(rows)


def migration_rows(root: Path):
    rows = []
    for path in sorted((root / 'product/backend/migrations/versions').glob('*.py')):
        values = {}
        for node in parse_python(path).body:
            if isinstance(node, (ast.Assign, ast.AnnAssign)):
                for target in (node.targets if isinstance(node, ast.Assign) else [node.target]):
                    if isinstance(target, ast.Name) and target.id in {'revision', 'down_revision'}:
                        values[target.id] = _constant(node.value)
        if 'revision' in values:
            if not isinstance(values['revision'], str) or not isinstance(values.get('down_revision'), (str, type(None))):
                raise ValueError('迁移元数据未静态确定：' + path.name)
            rows.append((values['revision'], values.get('down_revision'), path.relative_to(root).as_posix()))
    ids = {r[0] for r in rows}
    if len(ids) != len(rows):
        raise ValueError('迁移revision重复')
    if any(parent is not None and parent not in ids for _, parent, _ in rows):
        raise ValueError('迁移前驱缺失')
    heads = ids - {r[1] for r in rows}
    bases = [r for r in rows if r[1] is None]
    if rows and (len(heads) != 1 or len(bases) != 1):
        raise ValueError('迁移链必须有唯一基线和head')
    parents = {revision: parent for revision, parent, _ in rows}
    visited, cursor = set(), next(iter(heads), None)
    while cursor is not None and cursor not in visited:
        visited.add(cursor)
        cursor = parents[cursor]
    if rows and (cursor is not None or visited != ids):
        raise ValueError('迁移链循环或不连通')
    declared = None
    for node in _tree(root, 'product/backend/infra/storage/db.py').body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == '_CURRENT_MIGRATION_REVISION' for t in node.targets):
            declared = _constant(node.value)
    if rows and declared not in heads:
        raise ValueError('数据库head声明与迁移链不一致')
    return rows, declared
