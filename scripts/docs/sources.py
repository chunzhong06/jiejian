# 从受管源码文本提取文件、公开符号与静态依赖；不导入或执行产品。
from __future__ import annotations

import ast
import re
from collections import defaultdict
from pathlib import Path

SOURCE_SUFFIXES = {'.py', '.ts', '.tsx', '.js', '.jsx', '.mjs', '.cjs', '.ps1', '.cmd', '.bat', '.css', '.html'}
CONFIG_SUFFIXES = {'.toml', '.json', '.yaml', '.yml', '.ini'}
ROOT_INPUTS = ('pyproject.toml', 'environment.yml', 'jiejian.code-workspace', 'start.cmd', 'tests/suites.toml')
IGNORED_DIRECTORIES = {'__pycache__', 'node_modules', '.git', 'dist', 'coverage'}


def parse_python(path: Path) -> ast.Module:
    """解析失败显式拒绝生成，避免把损坏模块误报为没有符号。"""
    try:
        return ast.parse(path.read_text(encoding='utf-8-sig'), filename=str(path))
    except (OSError, SyntaxError) as error:
        raise ValueError(f'源码解析失败：{path.name}：{type(error).__name__}') from error


def signature(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    args = [arg.arg for arg in (*node.args.posonlyargs, *node.args.args)]
    if node.args.vararg:
        args.append('*' + node.args.vararg.arg)
    args.extend(arg.arg for arg in node.args.kwonlyargs)
    if node.args.kwarg:
        args.append('**' + node.args.kwarg.arg)
    result = ' -> ' + ast.unparse(node.returns) if node.returns else ''
    return f'{node.name}({", ".join(args)}){result}'


def public_symbols(tree: ast.Module) -> list[str]:
    result = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and not node.name.startswith('_'):
            result.append(signature(node))
        elif isinstance(node, ast.ClassDef) and not node.name.startswith('_'):
            result.append('class ' + node.name)
            for method in node.body:
                if isinstance(method, (ast.FunctionDef, ast.AsyncFunctionDef)) and not method.name.startswith('_'):
                    result.append(node.name + '.' + signature(method))
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            result.extend(t.id for t in targets if isinstance(t, ast.Name) and t.id.isupper())
    return result


def powershell(text: str) -> tuple[list[str], list[str]]:
    symbols = ['function ' + name for name in sorted(set(re.findall(r'(?im)^\s*function\s+([\w-]+)', text)))]
    parameters = set()
    for match in re.finditer(r'(?im)^\s*param\s*\(', text):
        depth, cursor = 1, match.end()
        while cursor < len(text) and depth:
            depth += (text[cursor] == '(') - (text[cursor] == ')')
            cursor += 1
        if not depth:
            parameters.update(re.findall(r'(?m)(?:^|,)\s*(?:\[[^\]]+\]\s*)*\$([A-Za-z_]\w*)', text[match.end():cursor - 1]))
    symbols += ['param $' + name for name in sorted(parameters)]
    imports = []
    for line in text.splitlines():
        literal = re.match(r'''^\s*\.\s+(['"])([^'"$]+)\1\s*(?:#.*)?$''', line)
        joined = re.match(r'''^\s*\.\s+\(\s*Join-Path\s+\$PSScriptRoot\s+(['"])([^'"$]+)\1\s*\)\s*(?:#.*)?$''', line, re.I)
        if literal:
            imports.append(literal.group(2))
        elif joined:
            imports.append('$PSScriptRoot/' + joined.group(2).replace('\\', '/').removeprefix('./'))
    return symbols, sorted(set(imports))


def describe(path: Path) -> tuple[list[str], list[str], str]:
    """非Python只提取明确的词法形式，不宣称提供完整语法或调用关系。"""
    if path.suffix == '.py':
        tree = parse_python(path)
        imports = set()
        top = {id(node) for node in tree.body}
        for node in ast.walk(tree):
            prefix = '' if id(node) in top else '作用域内：'
            if isinstance(node, ast.Import):
                imports.update(prefix + alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imports.add(prefix + '.' * node.level + (node.module or ''))
            elif isinstance(node, ast.Call) and isinstance(node.func, (ast.Name, ast.Attribute)):
                name = node.func.id if isinstance(node.func, ast.Name) else node.func.attr
                if name in {'import_module', '__import__'}:
                    literal = node.args[0] if node.args else None
                    imports.add('动态引用：' + (literal.value if isinstance(literal, ast.Constant) and isinstance(literal.value, str) else '未静态确定'))
        return public_symbols(tree), sorted(imports), 'Python AST；作用域内import不表示每次调用均执行。'
    text = path.read_text(encoding='utf-8-sig')
    if path.suffix == '.ps1':
        symbols, imports = powershell(text)
        return symbols, imports, 'PowerShell词法提取；动态dot-source未静态确定。'
    if path.suffix in {'.ts', '.tsx', '.js', '.jsx', '.mjs', '.cjs'}:
        symbols = sorted(set(re.findall(r'\bexport\s+(?:default\s+)?(?:async\s+)?(?:function|const|class|type|interface)\s+([A-Za-z_$][\w$]*)', text)))
        imports = sorted(set(re.findall(r'''(?:\bfrom\s*|\bimport\s*|\brequire\(\s*)['"]([^'"\n]+)['"]''', text)))
        return symbols, imports, 'JS/TS词法提取；re-export、条件和动态表达式需读源码确认。'
    return [], [], '仅记录文件位置；配置值、样式规则和脚本执行关系不复制。'


def source_files(root: Path) -> list[Path]:
    files = set()
    for prefix in ('product', 'scripts'):
        base = root / prefix
        if not base.exists():
            continue
        for path in base.rglob('*'):
            if not path.is_file() or any(part in IGNORED_DIRECTORIES for part in path.parts):
                continue
            # Schema由注册参考覆盖，不在代码分片重复列字段。
            if path.is_relative_to(root / 'product/protocols/schemas'):
                continue
            if path.suffix in SOURCE_SUFFIXES | CONFIG_SUFFIXES:
                if path.is_symlink() or not path.resolve().is_relative_to(root.resolve()):
                    raise ValueError('源码索引拒绝链接或越界路径：' + path.relative_to(root).as_posix())
                files.add(path)
    files.update(root / name for name in ROOT_INPUTS if (root / name).is_file())
    return sorted(files)


def bucket(relative: str) -> str:
    parts = Path(relative).parts
    if parts[:2] == ('product', 'backend'):
        rest = parts[2:]
        if len(rest) == 1:
            return 'backend/_root'
        layer = rest[0]
        if layer in {'core', 'workflows'}:
            return f'backend/{layer}/' + (rest[1] if len(rest) > 2 else '_root')
        if layer == 'infra':
            if len(rest) < 3:
                return 'backend/infra/_root'
            if rest[1] in {'runtime', 'storage'}:
                return 'backend/infra/' + rest[1] + '/' + (rest[2] if len(rest) > 3 else '_root')
            return 'backend/infra/' + rest[1]
        if layer == 'api':
            return 'backend/api/' + (rest[1] if len(rest) > 2 else '_root')
        return 'backend/' + layer
    if parts[:3] == ('product', 'frontend', 'src'):
        rest = parts[3:]
        if len(rest) > 2 and rest[0] == 'features':
            return 'frontend/features/' + rest[1]
        return 'frontend/' + (rest[0] if len(rest) > 1 else '_root')
    if parts[:2] == ('product', 'protocols'):
        return 'protocols/' + (parts[2] if len(parts) > 3 else '_root')
    if parts[0] == 'scripts':
        return 'scripts/' + (parts[1] if len(parts) > 2 else '_root')
    return '配置与入口'


def grouped_sources(root: Path) -> dict[str, list[Path]]:
    groups = defaultdict(list)
    for path in source_files(root):
        groups[bucket(path.relative_to(root).as_posix())].append(path)
    return dict(sorted(groups.items()))
