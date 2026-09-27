# 验证任务定位由服务端事实决定，展示文案不改变同一任务的身份。
from product.backend.workflows.workspace.service import WorkspaceService


def test_proposal_reference_is_public_and_presentation_does_not_change_identity():
    arguments = dict(task_kind="REVIEW_BOUNDARY_PROPOSAL", title="审阅业务权限", why_now="已有待审提案",
        user_responsibility="明确确认", system_will_do="读取决定", route="/permissions",
        facts={"proposal_id": "bpr_" + "a" * 32, "proposal_fingerprint": "b" * 64})
    task = WorkspaceService._task(**arguments)
    renamed = WorkspaceService._task(**{**arguments, "title": "核对变更"})
    assert task.proposal_id == arguments["facts"]["proposal_id"]
    assert task.action_label == "审阅这组变更"
    assert task.completion_criteria
    assert task.unavailable_reason is None
    assert task.task_id == renamed.task_id
    other = WorkspaceService._task(**{**arguments, "facts": {"proposal_id": "bpr_" + "c" * 32}})
    assert task.task_id != other.task_id


def test_disabled_task_explains_existing_reason_without_changing_capability():
    task = WorkspaceService._task("RUN_CURRENT_CHECK", title="检查", why_now="仍缺少准备材料",
        user_responsibility="补齐材料", system_will_do="核对材料", route="/tests", facts={}, can_execute=False)
    assert not task.can_execute
    assert task.unavailable_reason == "仍缺少准备材料"
    assert task.proposal_id is None
