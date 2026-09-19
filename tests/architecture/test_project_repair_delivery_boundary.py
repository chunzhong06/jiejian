# 保护当前原题修复的事实来源、单一装配及普通产品续接边界。
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "product/backend"
REPAIR = BACKEND / "workflows/projects/repair.py"


def _tree(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def test_project_repair_uses_published_history_and_exact_original_question_links() -> None:
    tree = _tree(REPAIR)
    calls = {ast.unparse(node.func) for node in ast.walk(tree) if isinstance(node, ast.Call)}
    assert {"self._reader.list_for_project", "self._reader.package", "self._repairs.contracts",
            "self._changes.latest_for_repair", "self._repairs.verification"} <= calls
    # 必须共同匹配原题指纹、源 Run 和变化引用，不能拿最新普通结果冒充复验。
    required = {
        "context.repair_reference == contract.repair_fingerprint",
        "context.source_run_id == contract.source_run_id",
        "request.change_context.change_id == change_id",
    }
    conjunctions = [node for node in ast.walk(tree) if isinstance(node, ast.BoolOp) and isinstance(node.op, ast.And)]
    assert any(required <= {ast.unparse(part) for part in node.values} for node in conjunctions)


def test_project_repair_has_no_storage_target_or_legacy_result_dependency() -> None:
    forbidden = ("sqlalchemy", "httpx", "playwright", "subprocess", "samples",
                 "product.backend.infra", "product.backend.workflows.control",
                 "product.backend.workflows.results", "product.backend.workflows.official_sample")
    for node in ast.walk(_tree(REPAIR)):
        names = [a.name for a in node.names] if isinstance(node, ast.Import) else [node.module] if isinstance(node, ast.ImportFrom) else []
        assert not any(name and any(name == p or name.startswith(p + ".") for p in forbidden) for name in names)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            assert node.func.attr not in {"commit", "submit", "approve", "create", "write", "publish", "run_job"}


def test_current_project_repair_is_composed_once_in_application_only() -> None:
    application = _tree(BACKEND / "composition/application.py")
    calls = [node for node in ast.walk(application) if isinstance(node, ast.Call)]
    names = [ast.unparse(node.func) for node in calls]
    assert names.count("CurrentProjectRepairService") == 1
    assert not {"ProjectRepairService", "DeliveryCheckService", "ProductStatusService"} & set(names)
    constructor = next(node for node in calls if ast.unparse(node.func) == "CurrentProjectRepairService")
    assert {item.arg: ast.unparse(item.value) for item in constructor.keywords} == {
        "reader": "self.check_results", "repairs": "self.check_repairs", "changes": "self.source_changes",
        "boundaries": "self.business_boundaries", "pending_request_reader": "self.checks.pending_request",
    }
    worker = (BACKEND / "composition/worker.py").read_text(encoding="utf-8")
    for forbidden in ("CurrentProjectRepairService", "WorkspaceService", "DeliveryCheckService", "ProductStatusService"):
        assert forbidden not in worker


def test_shell_continuation_uses_current_workspace_primary_task() -> None:
    shell = (ROOT / "product/frontend/src/app/ControlShell.tsx").read_text(encoding="utf-8")
    assert "const task = workspace?.primary_task" in shell
    assert "workspaceState.refreshCurrentWorkspace" in shell
    for current in ("ChangesPage", "CurrentTestsPage", "CheckHistoryPage", "BusinessBoundaryPage"):
        assert current in shell
    for forbidden in ("snapshot.readiness", "status?.inconclusive_recovery", "PermissionCheckPage",
                      "CheckResultsPage", "cell.can_confirm", "canVerifyOfficialFix", "verifyOfficialFix"):
        assert forbidden not in shell


def test_current_checks_and_repair_do_not_use_sample_specific_dependencies() -> None:
    for path in (REPAIR, BACKEND / "workflows/checks/repair.py"):
        source = path.read_text(encoding="utf-8")
        assert "official_sample" not in source
        assert "samples." not in source
        assert "sample_repair" not in source
    page = (ROOT / "product/frontend/src/features/testing/CurrentTestsPage.tsx").read_text(encoding="utf-8")
    for forbidden in ("experienceApi", "verifyFixedBehavior", "sample_repair", "officialSample"):
        assert forbidden not in page