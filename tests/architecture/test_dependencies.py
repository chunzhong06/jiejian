from __future__ import annotations

import ast
import tomllib
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
PACKAGE_ROOT = PROJECT_ROOT / "backend" / "src" / "jiejian"


def _python_files(directory: Path) -> tuple[Path, ...]:
    return tuple(sorted(directory.rglob("*.py")))


def _module_name(path: Path) -> str:
    relative = path.relative_to(PACKAGE_ROOT.parent).with_suffix("")
    parts = relative.parts
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def _imports(path: Path) -> set[str]:
    module = _module_name(path)
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                package_parts = module.split(".")
                if path.name != "__init__.py":
                    package_parts = package_parts[:-1]
                parent_count = node.level - 1
                if parent_count:
                    package_parts = package_parts[:-parent_count]
                prefix = ".".join(package_parts)
                target = f"{prefix}.{node.module}" if node.module else prefix
            else:
                target = node.module or ""
            imports.add(target)
    return imports


def test_domain_has_no_execution_or_infrastructure_dependencies() -> None:
    forbidden = (
        "sqlalchemy",
        "alembic",
        "httpx",
        "playwright",
        "typer",
        "jiejian.storage",
        "jiejian.runtime",
        "jiejian.verification",
    )
    dependencies = {
        dependency
        for path in _python_files(PACKAGE_ROOT / "domain")
        for dependency in _imports(path)
    }
    assert not {
        dependency
        for dependency in dependencies
        if dependency.startswith(forbidden)
    }


def test_protocols_do_not_depend_on_runtime_storage_cli_or_pipeline() -> None:
    forbidden = (
        "jiejian.runtime",
        "jiejian.storage",
        "jiejian.cli",
        "jiejian.verification",
    )
    dependencies = {
        dependency
        for path in _python_files(PACKAGE_ROOT / "protocols")
        for dependency in _imports(path)
    }
    assert not {
        dependency
        for dependency in dependencies
        if dependency.startswith(forbidden)
    }


def test_storage_does_not_depend_on_worker_verification_or_cli() -> None:
    dependencies = {
        dependency
        for path in _python_files(PACKAGE_ROOT / "storage")
        for dependency in _imports(path)
    }
    forbidden = ("jiejian.worker", "jiejian.verification", "jiejian.cli")
    assert not {
        dependency
        for dependency in dependencies
        if dependency.startswith(forbidden)
    }


def test_worker_is_a_control_plane_without_cli_or_target_io_dependencies() -> None:
    worker_root = PACKAGE_ROOT / "worker"
    assert not (worker_root / "service.py").exists()
    assert {
        path.name for path in worker_root.glob("*.py")
    } == {
        "__init__.py",
        "attempts.py",
        "dispatch.py",
        "events.py",
        "models.py",
        "process_environment.py",
        "publication.py",
        "published_artifacts.py",
        "queue.py",
        "recording.py",
        "process_control.py",
        "reconciliation.py",
        "recovery.py",
        "request_store.py",
        "runtime.py",
        "submission.py",
        "supervisor.py",
        "targets.py",
    }
    dependencies = {
        dependency
        for path in _python_files(worker_root)
        for dependency in _imports(path)
    }
    forbidden = (
        "jiejian.cli",
        "jiejian.verification",
        "httpx",
        "urllib",
        "requests",
        "playwright",
    )
    assert not {
        dependency
        for dependency in dependencies
        if dependency.startswith(forbidden)
    }


def test_target_execution_is_confined_to_explicit_adapters() -> None:
    runner_root = PACKAGE_ROOT / "runner"
    assert {path.name for path in runner_root.glob("*.py")} == {
        "__init__.py",
        "__main__.py",
        "execution.py",
    }
    cli_dependencies = _imports(PACKAGE_ROOT / "cli.py")
    worker_dependencies = {
        dependency
        for path in _python_files(PACKAGE_ROOT / "worker")
        for dependency in _imports(path)
    }
    forbidden = ("httpx", "jiejian.verification.http")
    assert not {
        dependency
        for dependency in cli_dependencies | worker_dependencies
        if dependency.startswith(forbidden)
    }
    httpx_importers = {
        path.relative_to(PACKAGE_ROOT).as_posix()
        for path in _python_files(PACKAGE_ROOT)
        if any(dependency == "httpx" for dependency in _imports(path))
    }
    assert httpx_importers == {
        "recording/transport.py",
        "verification/http.py",
    }


def test_playwright_is_confined_to_recording_browser_boundary() -> None:
    playwright_importers = {
        path.relative_to(PACKAGE_ROOT).as_posix()
        for path in _python_files(PACKAGE_ROOT)
        if any(dependency.startswith("playwright") for dependency in _imports(path))
    }
    assert playwright_importers == {
        "recording/browser.py",
        "recording/events.py",
        "recording/transport.py",
        "recording/ui_capture.py",
        "recording_runner/execution.py",
        "runtime/diagnostics.py",
    }
    for protected in ("cli.py", "domain", "protocols", "storage", "worker"):
        path = PACKAGE_ROOT / protected
        files = (path,) if path.is_file() else _python_files(path)
        assert not any(
            dependency.startswith("playwright")
            for file in files
            for dependency in _imports(file)
        )


def test_verification_module_dependencies_are_acyclic() -> None:
    files = _python_files(PACKAGE_ROOT / "verification")
    modules = {_module_name(path) for path in files}
    graph = {
        _module_name(path): {
            dependency for dependency in _imports(path) if dependency in modules
        }
        for path in files
    }
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(module: str) -> None:
        if module in visiting:
            raise AssertionError(f"verification dependency cycle at {module}")
        if module in visited:
            return
        visiting.add(module)
        for dependency in graph[module]:
            visit(dependency)
        visiting.remove(module)
        visited.add(module)

    for module in graph:
        visit(module)


def test_old_flat_modules_are_removed_without_compatibility_wrappers() -> None:
    old_modules = {
        "artifacts.py",
        "config.py",
        "doctor.py",
        "engine.py",
        "inputs.py",
        "logging.py",
        "protocols.py",
        "safety.py",
        "services.py",
    }
    assert old_modules.isdisjoint(path.name for path in PACKAGE_ROOT.iterdir())
    assert not (PACKAGE_ROOT / "domain" / "models.py").exists()
    assert not (PACKAGE_ROOT / "domain" / "stage1.py").exists()


def test_cli_is_the_only_installed_product_command_entry() -> None:
    pyproject = tomllib.loads(
        (PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    )
    assert pyproject["project"]["scripts"] == {"jiejian": "jiejian.cli:main"}
    typer_importers = {
        path.relative_to(PACKAGE_ROOT).as_posix()
        for path in _python_files(PACKAGE_ROOT)
        if any(dependency == "typer" for dependency in _imports(path))
    }
    assert typer_importers == {"cli.py"}
    assert not any(
        (PACKAGE_ROOT / name).exists()
        for name in ("main.py", "worker_main.py", "runner_main.py")
    )
