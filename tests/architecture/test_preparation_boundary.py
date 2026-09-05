# 保护测试准备服务的依赖方向、自动权限和非持久化边界。

from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SERVICE = ROOT / "product/backend/workflows/preparation/service.py"
BINDINGS = ROOT / "product/backend/workflows/preparation/bindings.py"
APPLICATION = ROOT / "product/backend/composition/application.py"
WORKER = ROOT / "product/backend/composition/worker.py"
STORAGE = ROOT / "product/backend/infra/storage"


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    result: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            result.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            result.add(node.module)
    return result


def test_project_preparation_has_no_model_browser_runner_or_orm_row_dependency() -> None:
    imports = _imports(SERVICE)
    assert not any(
        name.startswith(
            (
                "playwright",
                "product.backend.infra.runtime.runner",
                "product.backend.infra.llm",
            )
        )
        for name in imports
    )
    assert not any(name.endswith("Row") for name in SERVICE.read_text(encoding="utf-8").split())


def test_preparation_is_only_composed_in_application_core_and_not_persisted() -> None:
    application = APPLICATION.read_text(encoding="utf-8")
    worker = WORKER.read_text(encoding="utf-8")
    storage = "\n".join(path.read_text(encoding="utf-8") for path in STORAGE.rglob("*.py"))

    assert "PreparationService(" in application
    assert "PreparationService(" not in worker
    assert "ProjectPreparationService" not in application
    for forbidden in (
        "PreparationPlan",
        "PreparationProgress",
        "PreparationTask",
        "PreparationState",
        "preparation_plans",
        "preparation_progress",
        "preparation_tasks",
        "preparation_states",
    ):
        assert forbidden not in storage


def test_preparation_read_does_not_confirm_submit_or_persist() -> None:
    tree = ast.parse(SERVICE.read_text(encoding="utf-8"), filename=str(SERVICE))
    read_preparation = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "get"
    )
    called_attributes = {
        node.func.attr
        for node in ast.walk(read_preparation)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }
    assert "confirm" not in called_attributes
    assert "submit" not in called_attributes
    assert not {"commit", "add", "replace"} & called_attributes


def test_preparation_consumes_action_asset_inspection_without_storage_internals() -> None:
    source = SERVICE.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(SERVICE))
    accessed = {
        node.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Attribute)
    }

    assert "inspect" in accessed
    assert not {"recordings", "flow_drafts", "action_safety_setups"} & accessed
    assert not any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "preview"
        and isinstance(node.func.value, ast.Attribute)
        and node.func.value.attr == "_action_safety_setup"
        for node in ast.walk(tree)
    )


def test_binding_inspection_has_no_runtime_observer_llm_or_health_storage() -> None:
    imports = _imports(BINDINGS)
    assert not any(
        name.startswith(
            (
                "product.backend.infra.runtime.runner",
                "product.backend.infra.observers",
                "product.backend.infra.llm",
                "httpx",
                "playwright",
            )
        )
        for name in imports
    )
    storage = "\n".join(
        path.read_text(encoding="utf-8") for path in STORAGE.rglob("*.py")
    )
    for forbidden in (
        "AssetHealth",
        "asset_health",
        "HealthManager",
        "health_manager",
    ):
        assert forbidden not in storage


def test_current_preparation_has_one_binding_owner_and_no_legacy_safety_shell() -> None:
    for relative in (
        "product/backend/core/test_setup.py",
        "product/backend/workflows/recording/safety_setup.py",
        "product/backend/workflows/recording/safety_candidates.py",
        "product/backend/infra/storage/setup/test_setup.py",
    ):
        assert not (ROOT / relative).exists()
    for path in (APPLICATION, WORKER, SERVICE, BINDINGS):
        assert not any(
            name.startswith("product.backend.workflows.projects.preparation")
            or name.endswith("safety_setup") or name.endswith("core.test_setup")
            for name in _imports(path)
        )
