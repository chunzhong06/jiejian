# 保护项目修复、源码身份与交付证明的只读依赖方向和唯一当前协议写路径。

from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "product/backend"
REPAIR = BACKEND / "workflows/projects/repair.py"
DELIVERY = BACKEND / "workflows/projects/delivery.py"
SOURCE_CHANGES = BACKEND / "workflows/source_changes.py"
APPLICATION_UNDERSTANDING = (
    BACKEND / "workflows/application_understanding/service.py"
)
CHECKS = BACKEND / "workflows/security_setup/checks.py"
EXECUTION = BACKEND / "workflows/runs/execution.py"
EXECUTION_REQUEST = ROOT / "product/protocols/execution_request.py"
PREPARATION = BACKEND / "workflows/projects/preparation.py"
APPLICATION = BACKEND / "composition/application.py"
WORKER = BACKEND / "composition/worker.py"
CONTROL_SHELL = ROOT / "product/frontend/src/app/ControlShell.tsx"
PERMISSION_PAGE = (
    ROOT / "product/frontend/src/features/checks/PermissionCheckPage.tsx"
)
RESULTS_PAGE = ROOT / "product/frontend/src/features/checks/CheckResultsPage.tsx"
VERIFICATION_PAGE = ROOT / "product/frontend/src/features/checks/VerificationPage.tsx"
EXPERIENCE_API = ROOT / "product/frontend/src/api/experience.ts"
PREPARATION_PAGE = (
    ROOT / "product/frontend/src/features/preparation/PreparationPage.tsx"
)
OFFICIAL_SAMPLE = ROOT / "scripts/dev/sample_test/official.py"


def _tree(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _imports(path: Path) -> set[str]:
    result: set[str] = set()
    for node in ast.walk(_tree(path)):
        if isinstance(node, ast.Import):
            result.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            result.add(node.module)
    return result


def _method(path: Path, name: str) -> ast.FunctionDef:
    return next(
        node
        for node in ast.walk(_tree(path))
        if isinstance(node, ast.FunctionDef) and node.name == name
    )


def _called_attributes(node: ast.AST) -> tuple[str, ...]:
    return tuple(
        item.func.attr
        for item in ast.walk(node)
        if isinstance(item, ast.Call) and isinstance(item.func, ast.Attribute)
    )


def test_project_repair_and_delivery_have_no_storage_runner_llm_or_orm_dependency() -> None:
    forbidden = (
        "sqlalchemy",
        "product.backend.infra.storage",
        "product.backend.infra.runtime",
        "product.backend.infra.llm",
        "product.backend.core.verification",
    )
    for path in (REPAIR, DELIVERY):
        imports = _imports(path)
        assert not {
            name
            for name in imports
            if any(name == prefix or name.startswith(prefix + ".") for prefix in forbidden)
        }, path


def test_repair_and_delivery_services_do_not_write_or_decide_verdicts() -> None:
    forbidden_calls = {
        "add",
        "apply",
        "approve",
        "commit",
        "complete",
        "create",
        "delete",
        "replace",
        "submit",
        "write",
    }
    for path in (REPAIR, DELIVERY):
        assert not forbidden_calls & set(_called_attributes(_tree(path))), path


def test_project_repair_owns_published_run_history_not_latest_result_projection() -> None:
    source = REPAIR.read_text(encoding="utf-8")
    history_calls = _called_attributes(_method(REPAIR, "_published_history"))

    assert "latest_presentation" not in source
    assert "list_for_project" in history_calls
    assert "build" in history_calls


def test_workspace_inspection_and_fingerprint_inspection_are_zero_write() -> None:
    workspace = _method(SOURCE_CHANGES, "inspect_workspace")
    fingerprint = _method(APPLICATION_UNDERSTANDING, "inspect_source_fingerprint")

    assert not {"commit", "add", "replace", "analyze_source"} & set(
        _called_attributes(workspace)
    )
    assert not {"commit", "add", "replace", "_analyze_source"} & set(
        _called_attributes(fingerprint)
    )


def test_only_check_submit_scans_workspace_before_execution_submission() -> None:
    preview_calls = _called_attributes(_method(CHECKS, "preview"))
    prepare_calls = _called_attributes(_method(CHECKS, "prepare"))
    submit_calls = _called_attributes(_method(CHECKS, "submit"))

    assert "inspect_workspace" not in preview_calls
    assert "inspect_workspace" not in prepare_calls
    assert "inspect_workspace" in submit_calls
    assert "submit" in submit_calls
    assert submit_calls.index("inspect_workspace") < submit_calls.index("submit")


def test_current_execution_write_path_uses_only_schema_two_and_no_legacy_model() -> None:
    source = EXECUTION.read_text(encoding="utf-8")
    protocol = EXECUTION_REQUEST.read_text(encoding="utf-8")

    assert "PersistedExecutionRequest(" in source
    assert "source_fingerprint=source_fingerprint" in source
    assert 'schema_version: Literal["2"] = "2"' in protocol
    assert 'schema_version="1"' not in source
    assert "LegacyPersistedExecutionRequest" not in source


def test_preparation_uses_confirmed_actions_and_actionable_permission_count() -> None:
    source = PREPARATION.read_text(encoding="utf-8")
    status = _method(PREPARATION, "status")
    status_calls = _called_attributes(status)

    assert "inspect_action" in status_calls
    assert "_action_items" in status_calls
    permission = _method(PREPARATION, "_permission_blockers")
    permission_source = ast.get_source_segment(source, permission) or ""
    assert "required_confirmation_count" in permission_source
    assert "confirmed_count == 0" not in permission_source


def test_repair_and_delivery_are_only_composed_in_application_core() -> None:
    application = APPLICATION.read_text(encoding="utf-8")
    worker = WORKER.read_text(encoding="utf-8")

    for service in ("ProjectRepairService", "DeliveryCheckService"):
        assert f"{service}(" in application
        assert service not in worker


def test_frontend_continuation_uses_fresh_authoritative_preparation_projection() -> None:
    shell = CONTROL_SHELL.read_text(encoding="utf-8")
    preparation = PREPARATION_PAGE.read_text(encoding="utf-8")

    assert "const snapshot = await workspace.refreshCurrent()" in shell
    assert "snapshot.readiness?.preparation" in shell
    assert "preparation.next_path" in shell
    assert "onNext=" not in shell
    assert "nextItem?.next_path" not in preparation
    assert "nextBlocker?.next_path" not in preparation


def test_frontend_permission_and_repair_routes_have_no_legacy_decision_source() -> None:
    shell = CONTROL_SHELL.read_text(encoding="utf-8")
    permission = PERMISSION_PAGE.read_text(encoding="utf-8")
    results = RESULTS_PAGE.read_text(encoding="utf-8")

    assert "review_reasons" not in permission
    assert "required_confirmation_count" in permission
    assert "cell.can_confirm" in permission
    assert "cell.requires_human_confirmation" in permission
    for legacy in (
        "canVerifyOfficialFix",
        "verifyOfficialFix",
        "canVerifyFix",
        "onVerifyFix",
        "repair_change_id",
    ):
        assert legacy not in shell
        assert legacy not in results


def test_official_sample_uses_current_workspace_continuation_labels() -> None:
    source = OFFICIAL_SAMPLE.read_text(encoding="utf-8")

    assert source.count('name="继续准备", exact=True') == 1
    assert 'name="自动完成这一步", exact=True' in source
    assert 'name="继续测试准备", exact=True' not in source


def test_official_sample_repair_enters_the_ordinary_project_repair_path() -> None:
    source = OFFICIAL_SAMPLE.read_text(encoding="utf-8")

    assert 'repair.get("status") == "CHANGE_SUBMITTED"' in source
    assert "/preparation/prepare-safe" in source
    assert 'repair.get("status") != "READY_TO_VERIFY"' in source
    assert 'name="复验这次修复", exact=True' in source
    assert 'name="使用原考题复验", exact=True' not in source


def test_ordinary_verification_has_no_sample_repair_callback() -> None:
    verification = VERIFICATION_PAGE.read_text(encoding="utf-8")
    experience_api = EXPERIENCE_API.read_text(encoding="utf-8")

    for legacy in ("onRetest", "retestBusy", "使用原考题复验"):
        assert legacy not in verification
    assert "verifyFixedBehavior" not in experience_api
