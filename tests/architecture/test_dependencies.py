from __future__ import annotations

import ast
import inspect
import re
import tomllib
from pathlib import Path

import pytest

from product.backend import __version__
from product.backend.core.verification.facts import TargetType
from product.backend.workflows.context import ApplicationCore
from product.backend.workflows.worker_container import WorkerContainer


pytestmark = pytest.mark.essential

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "product" / "backend"
PROTOCOLS = ROOT / "product" / "protocols"


def _python_files(root: Path) -> list[Path]:
    return sorted(root.rglob("*.py"))


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    result: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            result.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            result.add(node.module)
    return result


def _forbidden_imports(path: Path, prefixes: tuple[str, ...]) -> set[str]:
    return {
        item
        for item in _imports(path)
        if any(item == prefix or item.startswith(prefix + ".") for prefix in prefixes)
    }


def test_core_and_protocol_dependencies_preserve_boundaries() -> None:
    core_forbidden = ("product.backend.workflows", "product.backend.infra", "product.backend.api", "product.backend.cli", "fastapi", "sqlalchemy", "httpx", "playwright")
    for path in _python_files(BACKEND / "core"):
        assert not _forbidden_imports(path, core_forbidden), path
    protocol_forbidden = (
        "product.backend.workflows",
        "product.backend.infra",
        "product.backend.api",
        "product.backend.cli",
    )
    for path in _python_files(PROTOCOLS):
        assert not _forbidden_imports(path, protocol_forbidden), path


def test_control_plane_and_verification_do_not_reach_target_adapters() -> None:
    control_forbidden = (
        "product.backend.infra.execution",
        "product.backend.infra.observers",
        "product.backend.infra.runtime.runner",
        "product.protocols.web",
    )
    for root in (BACKEND / "api", BACKEND / "cli"):
        for path in _python_files(root):
            assert not _forbidden_imports(path, control_forbidden), path

    verification_forbidden = (
        "product.backend.infra.execution",
        "product.backend.infra.runtime",
        "product.protocols.web",
    )
    for path in _python_files(BACKEND / "core" / "verification"):
        assert not _forbidden_imports(path, verification_forbidden), path


def test_target_runtime_dependencies_have_one_web_composition_point() -> None:
    execution = BACKEND / "infra" / "execution"
    port = execution / "port.py"
    registry = execution / "registry.py"
    web_runtime = execution / "web" / "runtime.py"
    composition = BACKEND / "infra" / "runtime" / "runner" / "composition.py"

    assert not _forbidden_imports(port, ("product.backend.infra.execution.web",))
    assert not _forbidden_imports(registry, ("product.backend.infra.execution.web",))
    assert "product.backend.infra.execution.port" in _imports(web_runtime)
    factory_users = {
        path.relative_to(ROOT).as_posix()
        for path in _python_files(BACKEND)
        if "WebTargetRuntimeFactory" in path.read_text(encoding="utf-8")
    }
    assert factory_users == {
        "product/backend/infra/execution/web/runtime.py",
        "product/backend/infra/runtime/runner/composition.py",
    }
    assert "registry.register(WebTargetRuntimeFactory())" in composition.read_text(encoding="utf-8")


def test_generic_runner_modules_do_not_import_web_protocol_or_runtime() -> None:
    runner = BACKEND / "infra" / "runtime" / "runner"
    forbidden = (
        "product.backend.infra.execution.web",
        "product.protocols.web",
    )
    for name in ("executor.py", "case_orchestrator.py", "result_builder.py", "staging.py"):
        path = runner / name
        assert not _forbidden_imports(path, forbidden), path


def test_current_target_capability_is_web_only_without_test_or_placeholder_kinds() -> None:
    assert tuple(TargetType) == (TargetType.WEB,)
    schema_text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted((PROTOCOLS / "schemas").rglob("*.json"))
    )
    production_text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in _python_files(ROOT / "product")
    )
    for name in ("CLI_APPLICATION", "MCP_AGENT", "TEST_FAKE"):
        assert name not in schema_text
        assert name not in production_text


def test_application_and_worker_containers_are_independent_complete_roots() -> None:
    assert ApplicationCore not in WorkerContainer.__mro__
    assert WorkerContainer not in ApplicationCore.__mro__
    assert "_minimal" not in inspect.signature(ApplicationCore).parameters
    container_text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (
            BACKEND / "workflows" / "context.py",
            BACKEND / "workflows" / "worker_container.py",
        )
    )
    assert "WorkerContext" not in container_text
    assert "_minimal" not in container_text


def test_removed_execution_abstractions_have_no_definition_alias_or_export() -> None:
    old_names = {
        "ExecutionRouter",
        "ExecutionAdapter",
        "ExecutionProfile",
        "ExecutionIdentity",
        "ExecutionProjectSnapshot",
        "WorkerContext",
    }
    for path in _python_files(ROOT / "product"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        declared = {
            node.name
            for node in ast.walk(tree)
            if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
        }
        imported = {
            alias.asname or alias.name.rsplit(".", 1)[-1]
            for node in ast.walk(tree)
            if isinstance(node, (ast.Import, ast.ImportFrom))
            for alias in node.names
        }
        assigned = {
            target.id
            for node in ast.walk(tree)
            if isinstance(node, (ast.Assign, ast.AnnAssign))
            for target in (
                node.targets if isinstance(node, ast.Assign) else (node.target,)
            )
            if isinstance(target, ast.Name)
        }
        assert not old_names.intersection(declared | imported | assigned), path

    for path in (
        BACKEND / "infra" / "execution" / "router.py",
        BACKEND / "infra" / "execution" / "http.py",
        BACKEND / "infra" / "execution" / "http_identity.py",
        PROTOCOLS / "execution_profile.py",
        PROTOCOLS / "http.py",
    ):
        assert not path.exists(), path


def test_worker_runner_and_recording_process_boundaries_are_explicit() -> None:
    assert (BACKEND / "infra" / "runtime" / "runner" / "__main__.py").is_file()
    assert (BACKEND / "infra" / "runtime" / "worker_process.py").is_file()
    assert (BACKEND / "infra" / "runtime" / "recording_process.py").is_file()


def test_product_names_do_not_encode_development_generations() -> None:
    generation_name = re.compile(r"(?i)(?:^|[_-])v[12](?:[._-]|$)|(?:^|[_-])stage(?:[._-]|$)|阶段")
    product_files = []
    for path in (ROOT / "product").rglob("*"):
        relative_parts = path.relative_to(ROOT / "product").parts
        if not path.is_file() or "node_modules" in relative_parts or "dist" in relative_parts:
            continue
        if path.suffix.lower() in {".py", ".ts", ".tsx", ".json"}:
            product_files.append(path)
    assert not [path for path in product_files if generation_name.search(path.name)]

    for path in _python_files(ROOT / "product"):
        if "node_modules" in path.parts or "dist" in path.parts:
            continue
        relative = path.relative_to(ROOT).as_posix()
        tree = ast.parse(path.read_text(encoding="utf-8"))
        definitions = {
            node.name
            for node in ast.walk(tree)
            if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
            and ("V1" in node.name or "V2" in node.name or "_v1" in node.name or "_v2" in node.name)
        }
        assert not definitions, (path, relative, definitions)
    assert not any("_new" in path.name or "_latest" in path.name for path in ROOT.rglob("*.py"))


def test_public_api_does_not_reintroduce_generation_paths() -> None:
    for path in _python_files(BACKEND / "api"):
        assert not re.search(r"/api/v[12](?:/|['\"])", path.read_text(encoding="utf-8")), path


def test_no_compatibility_import_mechanisms_or_old_python_root() -> None:
    files = _python_files(ROOT / "product")
    text = "\n".join(path.read_text(encoding="utf-8") for path in files)
    assert "backend/src/jiejian" not in text
    assert "import jiejian." not in text
    for path in files:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                continue
            owner = node.func.value
            assert not (
                isinstance(owner, ast.Attribute)
                and isinstance(owner.value, ast.Name)
                and owner.value.id == "sys"
                and owner.attr == "path"
                and node.func.attr in {"append", "extend", "insert", "remove"}
            ), path


def test_samples_are_one_way_test_data_not_product_dependencies() -> None:
    samples = ROOT / "samples"
    sample_web = samples / "web"
    assert not (samples / "http").exists()
    assert (sample_web / "target" / "server.py").is_file()
    assert (sample_web / "launch" / "gui.ps1").is_file()
    assert (sample_web / "launch" / "cli.ps1").is_file()
    for variant in ("fixed", "vulnerable", "inconclusive"):
        assert {path.name for path in (sample_web / variant).iterdir()} == {
            "contract.json",
            "profile.json",
            "scenario.json",
            "truth.json",
        }
    for path in _python_files(ROOT / "product"):
        assert not any(item == "samples" or item.startswith("samples.") for item in _imports(path)), path
    for path in _python_files(samples):
        assert not any(item == "tests" or item.startswith("tests.") for item in _imports(path)), path
    product_text = "\n".join(path.read_text(encoding="utf-8") for path in _python_files(ROOT / "product"))
    assert "truth.json" not in product_text
    frontend_text = "\n".join(
        path.read_text(encoding="utf-8")
        for suffix in ("*.ts", "*.tsx")
        for path in sorted((ROOT / "product" / "frontend" / "src").rglob(suffix))
    )
    assert "samples/" not in frontend_text
    for removed_handle in (
        "DemoRuntimeSupervisor",
        "DemoRunService",
        "OnboardingDemoStatus",
        "ONBOARDING_DEMO_FAILED",
        "/api/onboarding/demo",
        "demoStatus",
        "demoStart",
        "demoStop",
        "demo_data",
    ):
        assert removed_handle not in product_text + frontend_text
    for removed_path in (
        BACKEND / "workflows" / "onboarding" / "demo.py",
        BACKEND / "workflows" / "onboarding" / "demo_service.py",
        BACKEND / "workflows" / "onboarding" / "demo_target.py",
    ):
        assert not removed_path.exists()


def test_frontend_and_wheel_sources_are_scoped() -> None:
    frontend = ROOT / "product" / "frontend"
    assert (frontend / "src" / "app").is_dir()
    assert (frontend / "src" / "api").is_dir()
    workspace_text = (frontend / "pnpm-workspace.yaml").read_text(encoding="utf-8")
    assert "storeDir" not in workspace_text
    assert "virtualStoreDir" not in workspace_text
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    wheel = project["tool"]["hatch"]["build"]["targets"]["wheel"]
    assert wheel["only-include"] == ["product/backend", "product/protocols"]
    assert wheel["force-include"]["var/runtime/frontend"] == "product/frontend/dist"
    assert "product/frontend/src" not in str(wheel)
    assert project["project"]["scripts"]["jiejian"] == "product.backend.cli:main"
    assert project["project"]["version"] == __version__


def test_frontend_source_tree_contains_no_generated_install_or_build_artifacts() -> None:
    frontend = ROOT / "product" / "frontend"

    assert not (frontend / "node_modules").exists()
    assert not (frontend / "dist").exists()
    assert not tuple(frontend.rglob("*.tsbuildinfo"))
