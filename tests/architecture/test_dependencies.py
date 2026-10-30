# 验证领域与共用界面的依赖方向和源码职责，不锁定历史目录名称。
import ast
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]

def python_files(base):return [path for path in base.rglob('*.py') if '__pycache__' not in path.parts]

def test_domain_does_not_import_transport_database_or_execution_frameworks():
    forbidden=('fastapi','sqlalchemy','playwright','httpx','product.backend.infrastructure','product.backend.interfaces','product.backend.application','product.backend.bootstrap')
    violations=[]
    for path in python_files(ROOT/'product/backend/domain'):
        for node in ast.walk(ast.parse(path.read_text('utf-8-sig'))):
            names=[alias.name for alias in node.names] if isinstance(node,ast.Import) else [node.module or ''] if isinstance(node,ast.ImportFrom) else []
            violations.extend((path.name,name) for name in names if any(name==prefix or name.startswith(prefix+'.') for prefix in forbidden))
    assert violations==[]

def test_shared_frontend_does_not_depend_on_pages_entities_or_application():
    violations=[]
    for path in (ROOT/'product/frontend/src/shared').rglob('*'):
        if path.suffix not in {'.ts','.tsx'} or '.test.' in path.name:continue
        text=path.read_text('utf-8')
        if any('/'+layer+'/' in text for layer in ['pages','entities','app']):violations.append(path.name)
    assert violations==[]

def test_python_child_launches_explicitly_select_an_environment_role():
    sites=[]
    missing=[]
    for path in python_files(ROOT/'product/backend'):
        for node in ast.walk(ast.parse(path.read_text('utf-8-sig'))):
            if not isinstance(node,ast.Call):continue
            name=node.func.id if isinstance(node.func,ast.Name) else node.func.attr if isinstance(node.func,ast.Attribute) else ''
            if name not in {'minimal_process_environment','run_python_module','spawn_python_module'}:continue
            location=f'{path.relative_to(ROOT)}:{node.lineno}'
            sites.append(location)
            if not any(keyword.arg=='role' for keyword in node.keywords):missing.append(location)
    assert sites, '未发现任何子进程环境调用，先核对扫描范围'
    assert missing==[]


def runtime_imports(tree):
    class Imports(ast.NodeVisitor):
        def __init__(self):
            self.names = []

        def visit_If(self, node):
            type_only = isinstance(node.test, ast.Name) and node.test.id == 'TYPE_CHECKING'
            type_only |= isinstance(node.test, ast.Attribute) and node.test.attr == 'TYPE_CHECKING'
            for statement in node.orelse if type_only else [*node.body, *node.orelse]:
                self.visit(statement)

        def visit_Import(self, node):
            self.names.extend((0, alias.name, ()) for alias in node.names)

        def visit_ImportFrom(self, node):
            self.names.append((node.level, node.module or '', tuple(alias.name for alias in node.names)))

    visitor = Imports()
    visitor.visit(tree)
    return visitor.names


def test_runtime_modules_do_not_depend_on_each_other_in_a_cycle():
    modules = {}
    for path in python_files(ROOT/'product'):
        parts = path.relative_to(ROOT).with_suffix('').parts
        modules['.'.join(parts[:-1] if path.name == '__init__.py' else parts)] = path
    graph = {}
    for module, path in modules.items():
        edges = set()
        for level, target, imported in runtime_imports(ast.parse(path.read_text('utf-8-sig'))):
            if level:
                parent = module.split('.') if path.name == '__init__.py' else module.split('.')[:-1]
                target = '.'.join(parent[:len(parent)-level+1] + ([target] if target else []))
            edges.update(name for name in [target, *(target+'.'+item for item in imported)]
                         if name in modules and name != module)
        graph[module] = edges
    visited, active = set(), []

    def visit(module):
        assert module not in active, ' -> '.join([*active, module])
        if module in visited:
            return
        active.append(module)
        for dependency in sorted(graph[module]):
            visit(dependency)
        active.pop()
        visited.add(module)

    for module in sorted(graph):
        visit(module)


def test_infrastructure_does_not_import_the_composition_root_or_entrypoints():
    violations = []
    for path in python_files(ROOT/'product/backend/infrastructure'):
        for _, name, _ in runtime_imports(ast.parse(path.read_text('utf-8-sig'))):
            if name.startswith(('product.backend.bootstrap', 'product.backend.interfaces')):
                violations.append((path.relative_to(ROOT).as_posix(), name))
    assert violations == []


def test_login_browser_mechanics_do_not_own_account_use_cases():
    violations = []
    for path in python_files(ROOT/'product/backend/infrastructure/identity'):
        for _, name, _ in runtime_imports(ast.parse(path.read_text('utf-8-sig'))):
            if name.startswith('product.backend.application'):
                violations.append((path.relative_to(ROOT).as_posix(), name))
    assert violations == []
