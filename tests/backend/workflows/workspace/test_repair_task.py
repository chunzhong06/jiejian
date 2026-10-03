# 验证原题问题的主任务定位，修复入口不能越过现有材料与源码门禁。
from types import SimpleNamespace
from dataclasses import replace
from product.backend.workflows.workspace.reading import WorkspaceCheckReaders

import pytest

from product.backend.workflows.checks.repairs.repair import build_current_repair_contract
from product.backend.workflows.projects.repair import CurrentRepairTask, ProjectRepair
from tests.backend.core._support_check_repair import package
from tests.fixtures.preparation.action_preparation import build_preparation_harness

pytestmark = [pytest.mark.database, pytest.mark.essential]


@pytest.mark.parametrize("status,drifted,keep_preparation,expected", [
    ("REPAIR_REQUIRED", False, False, "PREPARE_AGENT_REPAIR"),
    ("NOT_VERIFIED", False, False, "PREPARE_AGENT_REPAIR"),
    ("REPAIR_REQUIRED", True, False, "REGISTER_SOURCE_CHANGE"),
    ("REPAIR_REQUIRED", False, True, "DEMONSTRATE_ACTION"),
    ("READY_TO_VERIFY", False, False, "VERIFY_REPAIR"),
])
def test_repair_primary_task_preserves_exact_reference_and_existing_gates(
    tmp_path, monkeypatch, status, drifted, keep_preparation, expected,
):
    harness = build_preparation_harness(tmp_path)
    try:
        source = package()
        source.request = source.request.model_copy(update={"project_id": harness.project_id})
        deny = next(case for action in source.request.actions for case in action.cases
                    if case.permission.expectation == "DENY")
        contract = build_current_repair_contract(source, deny.case_id)
        repair = CurrentRepairTask(task_reference="a" * 64, contract=contract, status=status,
                                  change_id="chg_" + "b" * 32 if status == "READY_TO_VERIFY" else None)
        projection = ProjectRepair(project_id=harness.project_id, status=status, tasks=(repair,),
                                   primary_task_reference=repair.task_reference)
        service = harness.core.workspace
        if not keep_preparation:
            # 只隔离准备状态选择；接入、权限与原题任务选择仍走正式服务。
            monkeypatch.setattr(service, "_preparation_task", lambda *_: None)
        fingerprint = harness.core.application_understanding.get(harness.project_id).source_fingerprint
        service._reader.current_checks = WorkspaceCheckReaders(
            checks=SimpleNamespace(preview=lambda _: pytest.fail("已有明确修复任务不应重新选择普通检查")),
            reader=SimpleNamespace(active_for_project=lambda _: None, list_for_project=lambda _: ()),
            changes=SimpleNamespace(latest=lambda _: None),
            repairs=SimpleNamespace(evaluate=lambda _: projection),
            source_inspector=lambda _: "c" * 64 if drifted else fingerprint,
        )
        task = service.get(harness.project_id).primary_task
        assert task.task_kind == expected
        if expected == "PREPARE_AGENT_REPAIR":
            assert task.route == "/changes"
            assert task.repair_fingerprint == contract.repair_fingerprint
            assert task.action_label == "准备 Agent 修复任务"
        else:
            assert task.repair_fingerprint is None
        if expected == "VERIFY_REPAIR":
            assert task.change_id == repair.change_id
    finally:
        harness.close()
