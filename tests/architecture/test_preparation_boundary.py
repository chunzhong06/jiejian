# 保护测试准备服务的依赖方向、自动权限和非持久化边界。

from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SERVICE = ROOT / "product/backend/workflows/projects/preparation.py"
APPLICATION = ROOT / "product/backend/composition/application.py"
WORKER = ROOT / "product/backend/composition/worker.py"
STORAGE = ROOT / "product/backend/infra/storage"
FRONTEND = ROOT / "product/frontend/src/features/preparation/PreparationPage.tsx"


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

    assert "ProjectPreparationService(" in application
    assert "ProjectPreparationService" not in worker
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


def test_prepare_safe_does_not_call_human_confirmation_or_run_submission() -> None:
    tree = ast.parse(SERVICE.read_text(encoding="utf-8"), filename=str(SERVICE))
    prepare_safe = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "prepare_safe"
    )
    called_attributes = {
        node.func.attr
        for node in ast.walk(prepare_safe)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }
    assert "confirm" not in called_attributes
    assert "submit" not in called_attributes


def test_preparation_page_does_not_reconstruct_backend_gap_semantics() -> None:
    source = FRONTEND.read_text(encoding="utf-8")
    for forbidden in (
        "permission_actions",
        "startsWith(",
        "MISSING_SUBJECT",
        "TEST_IDENTITY_",
        "reason_codes.map",
    ):
        assert forbidden not in source
