# 验证 Storage ORM 登记与 Backend 组合根的 CURRENT 单向装配边界。

from __future__ import annotations

import ast
from pathlib import Path

from product.backend.composition import ApplicationCore, WorkerContainer
from product.backend.infra import storage as storage_facade
from product.backend.infra.storage.base import Base
from product.backend.infra.storage.orm_registry import load_storage_orm_mappings


ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "product" / "backend"
STORAGE = BACKEND / "infra" / "storage"
PEER_MODULES = {
    "product.backend.infra.storage.projects": STORAGE / "projects.py",
    "product.backend.infra.storage.recordings": STORAGE / "recordings.py",
    "product.backend.infra.storage.execution.jobs": STORAGE / "execution" / "jobs.py",
    "product.backend.infra.storage.execution.runs": STORAGE / "execution" / "runs.py",
    "product.backend.infra.storage.results.evidence": STORAGE / "results" / "evidence.py",
}


def _tree(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _module_name(path: Path) -> str:
    relative = path.relative_to(ROOT).with_suffix("")
    parts = list(relative.parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def _row_modules_and_tables() -> tuple[set[str], set[str]]:
    modules: set[str] = set()
    tables: set[str] = set()
    for path in STORAGE.rglob("*.py"):
        for node in _tree(path).body:
            if not isinstance(node, ast.ClassDef) or not any(
                isinstance(base, ast.Name) and base.id == "Base" for base in node.bases
            ):
                continue
            modules.add(_module_name(path))
            for statement in node.body:
                if not isinstance(statement, ast.Assign):
                    continue
                if not any(
                    isinstance(target, ast.Name) and target.id == "__tablename__"
                    for target in statement.targets
                ):
                    continue
                assert isinstance(statement.value, ast.Constant)
                assert isinstance(statement.value.value, str)
                tables.add(statement.value.value)
    return modules, tables


def _row_class_names() -> set[str]:
    return {
        node.name
        for path in STORAGE.rglob("*.py")
        for node in _tree(path).body
        if isinstance(node, ast.ClassDef)
        and any(isinstance(base, ast.Name) and base.id == "Base" for base in node.bases)
    }


def _registry_modules() -> tuple[str, ...]:
    path = STORAGE / "orm_registry.py"
    for statement in _tree(path).body:
        if not isinstance(statement, ast.Assign):
            continue
        if not any(
            isinstance(target, ast.Name) and target.id == "_STORAGE_ORM_MODULES"
            for target in statement.targets
        ):
            continue
        value = ast.literal_eval(statement.value)
        assert isinstance(value, tuple)
        assert all(isinstance(item, str) for item in value)
        return value
    raise AssertionError("orm_registry 缺少固定模块集合")


def _strongly_connected_components(
    graph: dict[str, set[str]],
) -> tuple[frozenset[str], ...]:
    index = 0
    indexes: dict[str, int] = {}
    lowlinks: dict[str, int] = {}
    stack: list[str] = []
    active: set[str] = set()
    components: list[frozenset[str]] = []

    def visit(node: str) -> None:
        nonlocal index
        indexes[node] = index
        lowlinks[node] = index
        index += 1
        stack.append(node)
        active.add(node)
        for target in graph[node]:
            if target not in indexes:
                visit(target)
                lowlinks[node] = min(lowlinks[node], lowlinks[target])
            elif target in active:
                lowlinks[node] = min(lowlinks[node], indexes[target])
        if lowlinks[node] != indexes[node]:
            return
        component: set[str] = set()
        while True:
            member = stack.pop()
            active.remove(member)
            component.add(member)
            if member == node:
                break
        components.append(frozenset(component))

    for node in graph:
        if node not in indexes:
            visit(node)
    return tuple(components)


def _class_locations(class_name: str) -> set[str]:
    locations: set[str] = set()
    for path in BACKEND.rglob("*.py"):
        if any(
            isinstance(node, ast.ClassDef) and node.name == class_name
            for node in ast.walk(_tree(path))
        ):
            locations.add(path.relative_to(ROOT).as_posix())
    return locations


def _imported_modules(path: Path) -> set[str]:
    modules: set[str] = set()
    for node in ast.walk(_tree(path)):
        if isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
        elif isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
    return modules


def test_registry_exactly_loads_ast_row_modules_and_is_idempotent() -> None:
    row_modules, row_tables = _row_modules_and_tables()
    assert set(_registry_modules()) == row_modules

    load_storage_orm_mappings()
    first = tuple(sorted(Base.metadata.tables))
    load_storage_orm_mappings()
    second = tuple(sorted(Base.metadata.tables))

    assert first == second == tuple(sorted(row_tables))
    registry_source = (STORAGE / "orm_registry.py").read_text(encoding="utf-8")
    assert not any(token in registry_source for token in ("rglob(", "glob(", "pkgutil", "walk_packages"))


def test_five_storage_aggregates_have_no_direct_edges_or_cycles() -> None:
    graph = {module: set() for module in PEER_MODULES}
    for source_module, path in PEER_MODULES.items():
        graph[source_module].update(
            node.module
            for node in ast.walk(_tree(path))
            if isinstance(node, ast.ImportFrom) and node.module in PEER_MODULES
        )

    assert not {(source, target) for source, targets in graph.items() for target in targets}
    assert all(len(component) == 1 for component in _strongly_connected_components(graph))


def test_storage_facade_does_not_export_rows_or_register_mappings_implicitly() -> None:
    row_classes = _row_class_names()
    assert row_classes.isdisjoint(storage_facade.__all__)

    production_consumers: list[tuple[str, str]] = []
    for path in (ROOT / "product").rglob("*.py"):
        for node in ast.walk(_tree(path)):
            if not isinstance(node, ast.ImportFrom):
                continue
            if node.module != "product.backend.infra.storage":
                continue
            production_consumers.extend(
                (path.relative_to(ROOT).as_posix(), alias.name)
                for alias in node.names
                if alias.name in row_classes
            )
    assert production_consumers == []

    facade_source = (STORAGE / "__init__.py").read_text(encoding="utf-8")
    assert "load_storage_orm_mappings" not in facade_source


def test_backend_composition_has_two_unique_independent_roots() -> None:
    assert {path.name for path in (BACKEND / "composition").glob("*.py")} == {
        "__init__.py",
        "application.py",
        "worker.py",
    }
    assert _class_locations("ApplicationCore") == {
        "product/backend/composition/application.py"
    }
    assert _class_locations("WorkerContainer") == {
        "product/backend/composition/worker.py"
    }
    assert ApplicationCore not in WorkerContainer.__mro__
    assert WorkerContainer not in ApplicationCore.__mro__


def test_control_and_worker_process_use_the_current_composition_boundary() -> None:
    assert "product.backend.composition" in _imported_modules(BACKEND / "api" / "app.py")
    assert "product.backend.composition" in _imported_modules(BACKEND / "cli" / "bootstrap.py")
    assert "product.backend.composition" in _imported_modules(
        BACKEND / "infra" / "runtime" / "worker" / "process.py"
    )
