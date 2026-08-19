from __future__ import annotations

import ast
import re
import tomllib
from pathlib import Path

from product.backend import __version__

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


def test_backend_top_level_is_the_frozen_product_shape() -> None:
    names = {path.name for path in BACKEND.iterdir()}
    assert names == {"__init__.py", "api", "cli", "core", "workflows", "infra", "migrations", "alembic.ini"}
    assert not (BACKEND / "jiejian").exists()
    assert not any((BACKEND / name).exists() for name in ("application", "domain", "execution", "runner", "worker", "recording_runner", "results", "storage"))


def test_storage_runtime_and_protocol_roots_are_unique() -> None:
    assert (BACKEND / "infra" / "storage" / "db.py").is_file()
    assert not (BACKEND / "infra" / "storage" / "storage").exists()
    assert (BACKEND / "infra" / "execution" / "http.py").is_file()
    assert not (BACKEND / "infra" / "runtime" / "runner" / "http.py").exists()
    assert (PROTOCOLS / "execution_request.py").is_file()
    assert (PROTOCOLS / "execution_profile.py").is_file()
    assert not (BACKEND / "protocols").exists()


def test_core_and_protocol_dependencies_preserve_boundaries() -> None:
    core_forbidden = ("product.backend.workflows", "product.backend.infra", "product.backend.api", "product.backend.cli", "fastapi", "sqlalchemy", "httpx", "playwright")
    for path in _python_files(BACKEND / "core"):
        assert not {item for item in _imports(path) if item == core_forbidden or item.startswith(core_forbidden)}, path
    for path in _python_files(PROTOCOLS):
        imports = _imports(path)
        assert not any(
            item.startswith("product.backend.")
            and not item.startswith("product.backend.core")
            for item in imports
        ), path


def test_http_adapter_and_process_boundaries_are_explicit() -> None:
    adapter = BACKEND / "infra" / "execution" / "http.py"
    assert "class HttpExecutionAdapter" in adapter.read_text(encoding="utf-8")
    assert "class HttpExecutor" not in adapter.read_text(encoding="utf-8")
    assert (BACKEND / "infra" / "runtime" / "runner" / "__main__.py").is_file()
    assert (BACKEND / "infra" / "runtime" / "worker_process.py").is_file()
    assert (BACKEND / "infra" / "runtime" / "recording_process.py").is_file()
    for root in (BACKEND / "api", BACKEND / "cli"):
        for path in _python_files(root):
            imports = _imports(path)
            assert not any(item.startswith("product.backend.infra.execution") for item in imports), path
            assert not any(item.startswith("product.backend.infra.observers") for item in imports), path


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


def test_current_execution_and_protocol_boundaries_are_unique() -> None:
    router = BACKEND / "infra" / "execution" / "router.py"
    http = BACKEND / "infra" / "execution" / "http.py"
    facts = BACKEND / "core" / "verification" / "facts.py"
    assert router.is_file() and "class ExecutionRouter" in router.read_text(encoding="utf-8")
    assert http.is_file() and "class HttpExecutionAdapter" in http.read_text(encoding="utf-8")
    assert "class TargetType" in facts.read_text(encoding="utf-8")
    assert not (BACKEND / "infra" / "execution" / "process.py").exists()
    assert not (BACKEND / "infra" / "execution" / "mcp.py").exists()
    assert not (BACKEND / "mcp").exists()

    current_protocols = {
        "runner.py",
        "observer.py",
        "execution_request.py",
        "execution_profile.py",
        "recording.py",
        "flow_draft.py",
        "artifacts.py",
        "report.py",
    }
    assert current_protocols <= {path.name for path in PROTOCOLS.iterdir()}
    assert not any(PROTOCOLS.glob("runner_v*.py"))
    assert not any(PROTOCOLS.glob("observer_v*.py"))
    assert not any(PROTOCOLS.glob("recording_v*.py"))


def test_current_migration_api_and_runner_document_boundaries() -> None:
    migration_versions = BACKEND / "migrations" / "versions"
    assert {path.name for path in migration_versions.glob("*.py")} == {"0001_initial.py"}
    execution_profiles = (BACKEND / "infra" / "storage" / "execution_profiles.py").read_text(encoding="utf-8")
    assert '__tablename__ = "execution_profiles"' in execution_profiles
    for path in _python_files(BACKEND / "api"):
        assert not re.search(r"/api/v[12](?:/|['\"])", path.read_text(encoding="utf-8")), path
    protocol_doc = ROOT / "docs" / "04_协议与数据" / "Runner执行协议.md"
    assert protocol_doc.is_file()
    assert not (protocol_doc.parent / "Runner执行协议V1.md").exists()


def test_no_compatibility_import_mechanisms_or_old_python_root() -> None:
    text = "\n".join(path.read_text(encoding="utf-8") for path in _python_files(ROOT / "product"))
    assert "backend/src/jiejian" not in text
    assert "sys.path" not in text
    assert "PYTHONPATH" not in text
    assert "import jiejian." not in text


def test_official_samples_have_one_way_dependency_and_fixed_tree() -> None:
    samples = ROOT / "samples"
    assert (samples / "http" / "target" / "server.py").is_file()
    for variant in ("fixed", "vulnerable", "inconclusive"):
        bundle = samples / "http" / variant
        assert {path.name for path in bundle.iterdir()} == {"contract.json", "profile.json", "scenario.json", "truth.json"}
    assert not (samples / "http" / "authorization").exists()
    assert not (samples / "http" / "targets").exists()
    assert not any((samples / "http" / variant / scenario).exists() for variant in ("fixed", "vulnerable", "inconclusive") for scenario in ("ownership", "permissions"))
    for old in ("fixed_apps", "vulnerable_apps", "inconclusive_apps"):
        assert not (samples / old).exists()
    assert not (samples / "cli").exists()
    assert not (samples / "mcp").exists()

    for path in _python_files(ROOT / "product"):
        assert not any(item == "samples" or item.startswith("samples.") for item in _imports(path)), path
    for path in _python_files(samples):
        assert not any(item == "tests" or item.startswith("tests.") for item in _imports(path)), path
    product_text = "\n".join(path.read_text(encoding="utf-8") for path in _python_files(ROOT / "product"))
    assert "truth.json" not in product_text


def test_frontend_and_wheel_sources_are_scoped() -> None:
    frontend = ROOT / "product" / "frontend"
    assert (frontend / "src" / "app").is_dir()
    assert (frontend / "src" / "api").is_dir()
    workspace_text = (frontend / "pnpm-workspace.yaml").read_text(encoding="utf-8")
    assert "storeDir: ../../../.pnpm-store" in workspace_text
    assert (frontend / "../../../.pnpm-store").resolve() == (ROOT.parent / ".pnpm-store").resolve()
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    wheel = project["tool"]["hatch"]["build"]["targets"]["wheel"]
    assert wheel["only-include"] == ["product/backend", "product/protocols"]
    assert wheel["force-include"]["product/frontend/dist"] == "product/frontend/dist"
    assert "product/frontend/src" not in str(wheel)
    assert project["project"]["scripts"]["jiejian"] == "product.backend.cli:main"
    assert project["project"]["version"] == __version__


def test_frontend_uses_task_pages_without_legacy_wrappers() -> None:
    frontend = ROOT / "product" / "frontend" / "src"
    control_shell = (frontend / "app" / "ControlShell.tsx").read_text(encoding="utf-8")
    for route in ("/workspace", "/apps/access", "/apps/rules", "/checks/start", "/checks/results", "/checks/history", "/advanced/recording", "/advanced/models", "/advanced/system"):
        assert route in control_shell
    assert "StageGuide" not in control_shell
    assert all(name not in control_shell for name in ("ContractPage", "RunPage", "VerifyPage", "ReportPage"))
    assert "import { HistoryPage }" not in control_shell
    assert (frontend / "features" / "permissions" / "PermissionRulesPage.tsx").is_file()
    for name in ("StartCheckPage.tsx", "CheckProgress.tsx", "CheckResultsPage.tsx", "EvidenceTimeline.tsx", "ReportPanel.tsx", "CheckHistoryPage.tsx"):
        assert (frontend / "features" / "checks" / name).is_file()
    for legacy in (
        frontend / "features" / "contracts" / "ContractPage.tsx",
        frontend / "features" / "runs" / "RunPage.tsx",
        frontend / "features" / "verification" / "VerifyPage.tsx",
        frontend / "features" / "results" / "ReportPage.tsx",
        frontend / "features" / "history" / "HistoryPage.tsx",
        frontend / "features" / "runs" / "JobProgress.tsx",
    ):
        assert not legacy.exists(), legacy
