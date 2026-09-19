# 位置提示不得依步骤顺序推导完成，也不得用历史结果掩盖源码变化。
from types import SimpleNamespace

from product.backend.workflows.workspace.service import WorkspaceService


def task(kind, route):
    return SimpleNamespace(task_id="ptk_" + "1" * 32, task_kind=kind, route=route, business_action_id=None)


def test_unconnected_project_has_no_invented_completed_steps():
    view = WorkspaceService._journey(SimpleNamespace(endpoint_status="NEEDS_CONFIRMATION", source_analysis_status="NOT_AUTHORIZED"),
        True, False, task("CONFIRM_APPLICATION_ENDPOINT", "/application"), None, None, None)
    assert [step.status for step in view.steps] == ["CURRENT", "PENDING", "PENDING", "PENDING"]


def test_source_drift_requires_review_even_with_existing_result():
    connection = SimpleNamespace(endpoint_status="CONFIRMED", source_analysis_status="COMPLETED")
    result = SimpleNamespace(run_id="old-run")
    view = WorkspaceService._journey(connection, False, True,
        task("REGISTER_SOURCE_CHANGE", "/changes"), result, None, None)
    assert [step.status for step in view.steps] == ["COMPLETE", "COMPLETE", "CURRENT", "NEEDS_REVIEW"]


def test_permission_review_does_not_mark_preparation_complete():
    view = WorkspaceService._journey(SimpleNamespace(endpoint_status="CONFIRMED", source_analysis_status="COMPLETED"),
        True, True, task("REVIEW_PERMISSION_REVISION", "/permissions"), None, None, None)
    assert [step.status for step in view.steps] == ["COMPLETE", "CURRENT", "PENDING", "PENDING"]


def test_previous_result_cannot_complete_changed_rules():
    view = WorkspaceService._journey(SimpleNamespace(endpoint_status="CONFIRMED", source_analysis_status="COMPLETED"),
        True, True, task("REVIEW_PERMISSION_REVISION", "/permissions"), SimpleNamespace(run_id="old-run"), None, None)
    assert view.steps[-1].status == "NEEDS_REVIEW"


def test_new_material_task_does_not_inherit_previous_result_completion():
    view = WorkspaceService._journey(SimpleNamespace(endpoint_status="CONFIRMED", source_analysis_status="COMPLETED"),
        False, False, task("PREPARE_TEST_IDENTITY", "/tests"), SimpleNamespace(run_id="old-run"), None, None)
    assert [step.status for step in view.steps] == ["COMPLETE", "COMPLETE", "CURRENT", "NEEDS_REVIEW"]


def test_first_candidates_do_not_mark_unwritten_rules_as_needing_review():
    view = WorkspaceService._journey(SimpleNamespace(endpoint_status="CONFIRMED", source_analysis_status="COMPLETED"),
        True, False, task("REVIEW_APPLICATION_CANDIDATES", "/application"), None, None, None)
    assert [step.status for step in view.steps] == ["CURRENT", "PENDING", "PENDING", "PENDING"]
