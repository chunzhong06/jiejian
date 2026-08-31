# 验证项目修复任务从全部可信发布 Run 派生，并只由匹配的独立复验关闭。

from __future__ import annotations

from types import SimpleNamespace

import pytest

from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.core.lifecycle import RunLifecycle, RunVerdict
from product.backend.core.repair import (
    RepairContractReference,
    RepairRequirementView,
    RepairVerification,
    RepairVerificationStatus,
)
from product.backend.workflows.projects.repair import (
    ProjectRepairService,
    ProjectRepairStatus,
)
from product.backend.workflows.projects.revalidation import ProjectRevalidationStatus
from product.backend.workflows.results.presentation import PresentedCaseVerdict


_PROJECT_ID = "app_demo"
_SOURCE_RUN_ID = "run_" + "2" * 32
_REFERENCE = RepairContractReference(
    source_run_id=_SOURCE_RUN_ID,
    source_finding_id="finding_" + "3" * 32,
    repair_fingerprint="4" * 64,
)
_SECOND_REFERENCE = RepairContractReference(
    source_run_id=_SOURCE_RUN_ID,
    source_finding_id="finding_" + "5" * 32,
    repair_fingerprint="6" * 64,
)
_REQUIREMENT = RepairRequirementView(
    reference=_REFERENCE,
    must_disappear="越权业务后果必须消失。",
    must_remain="原有合法业务路径必须保留。",
    must_not_change=("关键证据标准", "原权限考题"),
)
_SECOND_REQUIREMENT = RepairRequirementView(
    reference=_SECOND_REFERENCE,
    must_disappear="第二个越权业务后果必须消失。",
    must_remain="第二条合法业务路径必须保留。",
    must_not_change=("第二项关键证据标准", "原权限考题"),
)


class _Runs:
    def __init__(self, runs) -> None:
        self._runs = tuple(runs)

    def list_for_project(self, project_id: str):
        assert project_id == _PROJECT_ID
        return self._runs


class _Work:
    def __init__(self, runs) -> None:
        self.runs = _Runs(runs)

    def __enter__(self):
        return self

    def __exit__(self, *_args) -> None:
        return None


class _RepairContracts:
    def __init__(self, requirements) -> None:
        self._requirements = {
            (item.reference.source_run_id, item.reference.source_finding_id): item
            for item in requirements
        }

    def requirement(self, source_run_id: str, source_finding_id: str):
        return self._requirements[(source_run_id, source_finding_id)]


class _SourceChanges:
    def __init__(self, changes=None, *, stale: bool = False) -> None:
        self._changes = changes or {}
        self._stale = stale

    def latest_for_repair(self, project_id: str, reference: RepairContractReference):
        assert project_id == _PROJECT_ID
        if self._stale:
            raise JiejianError(ErrorCode.STATE_PRECONDITION, "修复引用已失效")
        linked = self._changes.get(_reference_key(reference))
        if linked is None:
            return None
        change_id, created_at_us = linked
        return SimpleNamespace(change_id=change_id, created_at_us=created_at_us), object(), object()


class _Revalidation:
    def __init__(
        self,
        status: ProjectRevalidationStatus = ProjectRevalidationStatus.READY,
    ) -> None:
        self._status = status

    def evaluate_change(self, project_id: str, change_id: str, **_kwargs):
        assert project_id == _PROJECT_ID
        routes = {
            ProjectRevalidationStatus.REVIEW_REQUIRED: ("/permissions", "确认权限实现"),
            ProjectRevalidationStatus.PREPARATION_REQUIRED: ("/preparation", "补齐测试准备"),
            ProjectRevalidationStatus.READY: ("/validation", "开始重新验证"),
            ProjectRevalidationStatus.VERIFIED: ("/results", "查看验证结果"),
            ProjectRevalidationStatus.STALE: ("/changes", "重新说明代码变化"),
        }
        next_path, next_label = routes[self._status]
        return SimpleNamespace(
            status=self._status,
            next_path=next_path,
            next_label=next_label,
            reason_codes=(f"REVALIDATION_{self._status.value}",),
        )


class _Presentations:
    def __init__(self, presentations) -> None:
        self._presentations = dict(presentations)

    def build(self, run_id: str):
        return self._presentations[run_id]


def _reference_key(reference: RepairContractReference) -> tuple[str, str, str]:
    return (
        reference.source_run_id,
        reference.source_finding_id,
        reference.repair_fingerprint,
    )


def _run(run_id: str, *, created_at_us: int, finished_at_us: int):
    return SimpleNamespace(
        run_id=run_id,
        lifecycle=RunLifecycle.COMPLETED,
        created_at_us=created_at_us,
        finished_at_us=finished_at_us,
    )


def _presentation(
    verdict: RunVerdict,
    *,
    requirements=(),
    verification: RepairVerification | None = None,
):
    return SimpleNamespace(
        verdict=verdict,
        issues=tuple(
            SimpleNamespace(
                verdict=PresentedCaseVerdict.VULNERABLE,
                repair_requirement=requirement,
            )
            for requirement in requirements
        ),
        repair_verification=verification,
    )


def _verification(
    status: RepairVerificationStatus,
    *,
    reference: RepairContractReference = _REFERENCE,
    run_id: str = "run_" + "7" * 32,
) -> RepairVerification:
    return RepairVerification(
        reference=reference,
        verification_run_id=run_id,
        status=status,
        message="独立复验已经形成确定结果。",
        reason_codes=(f"REPAIR_{status.value}",),
    )


def _service(
    history,
    *,
    changes=None,
    revalidation: ProjectRevalidationStatus = ProjectRevalidationStatus.READY,
    stale: bool = False,
    requirements=(_REQUIREMENT, _SECOND_REQUIREMENT),
) -> ProjectRepairService:
    runs = tuple(item[0] for item in history)
    presentations = {item[0].run_id: item[1] for item in history}
    return ProjectRepairService(
        lambda: _Work(runs),
        _RepairContracts(requirements),
        _SourceChanges(changes, stale=stale),
        _Revalidation(revalidation),
        _Presentations(presentations),
    )


def _evaluate(service: ProjectRepairService):
    return service.evaluate(
        _PROJECT_ID,
        preparation=SimpleNamespace(ready=True),
        verified_run_id=None,
        verified_change_id=None,
    )


def _source_history(*requirements: RepairRequirementView):
    run = _run(_SOURCE_RUN_ID, created_at_us=10, finished_at_us=20)
    return [(run, _presentation(RunVerdict.BLOCK, requirements=requirements))]


def test_block_without_linked_change_requires_coding_agent_repair() -> None:
    view = _evaluate(_service(_source_history(_REQUIREMENT)))

    assert view.status is ProjectRepairStatus.REPAIR_REQUIRED
    assert view.next_path == "/results"
    assert view.tasks[0].linked_change_id is None


@pytest.mark.parametrize(
    ("revalidation", "expected_status", "expected_path"),
    (
        (
            ProjectRevalidationStatus.REVIEW_REQUIRED,
            ProjectRepairStatus.CHANGE_SUBMITTED,
            "/permissions",
        ),
        (
            ProjectRevalidationStatus.PREPARATION_REQUIRED,
            ProjectRepairStatus.CHANGE_SUBMITTED,
            "/preparation",
        ),
        (
            ProjectRevalidationStatus.READY,
            ProjectRepairStatus.READY_TO_VERIFY,
            "/validation",
        ),
        (
            ProjectRevalidationStatus.STALE,
            ProjectRepairStatus.STALE,
            "/changes",
        ),
    ),
)
def test_linked_repair_change_reuses_exact_revalidation_state(
    revalidation: ProjectRevalidationStatus,
    expected_status: ProjectRepairStatus,
    expected_path: str,
) -> None:
    change_id = "chg_" + "1" * 32
    view = _evaluate(
        _service(
            _source_history(_REQUIREMENT),
            changes={_reference_key(_REFERENCE): (change_id, 30)},
            revalidation=revalidation,
        )
    )

    assert view.status is expected_status
    assert view.next_path == expected_path
    assert view.tasks[0].linked_change_id == change_id


@pytest.mark.parametrize(
    ("verification_status", "expected_status", "expected_path"),
    (
        (RepairVerificationStatus.VERIFIED, ProjectRepairStatus.VERIFIED, "/results"),
        (
            RepairVerificationStatus.NOT_VERIFIED,
            ProjectRepairStatus.NOT_VERIFIED,
            "/results",
        ),
        (
            RepairVerificationStatus.INCONCLUSIVE,
            ProjectRepairStatus.INCONCLUSIVE,
            "/preparation",
        ),
    ),
)
def test_repair_verification_projects_exact_status(
    verification_status: RepairVerificationStatus,
    expected_status: ProjectRepairStatus,
    expected_path: str,
) -> None:
    verification_run = _run("run_" + "7" * 32, created_at_us=30, finished_at_us=40)
    history = [
        *_source_history(_REQUIREMENT),
        (
            verification_run,
            _presentation(
                RunVerdict.PASS,
                verification=_verification(verification_status),
            ),
        ),
    ]

    view = _evaluate(_service(history))

    assert view.status is expected_status
    assert view.next_path == expected_path
    assert view.tasks[0].verification_status is verification_status


def test_unfinished_repair_survives_later_ordinary_pass() -> None:
    ordinary_pass = _run("run_" + "8" * 32, created_at_us=30, finished_at_us=40)
    history = [
        *_source_history(_REQUIREMENT),
        (ordinary_pass, _presentation(RunVerdict.PASS)),
    ]

    view = _evaluate(_service(history))

    assert view.status is ProjectRepairStatus.REPAIR_REQUIRED
    assert tuple(task.reference for task in view.tasks) == (_REFERENCE,)


def test_two_repair_tasks_close_independently() -> None:
    verification_run = _run("run_" + "7" * 32, created_at_us=30, finished_at_us=40)
    history = [
        *_source_history(_REQUIREMENT, _SECOND_REQUIREMENT),
        (
            verification_run,
            _presentation(
                RunVerdict.PASS,
                verification=_verification(RepairVerificationStatus.VERIFIED),
            ),
        ),
    ]

    view = _evaluate(_service(history))

    by_reference = {task.reference: task for task in view.tasks}
    assert by_reference[_REFERENCE].status is ProjectRepairStatus.VERIFIED
    assert by_reference[_SECOND_REFERENCE].status is ProjectRepairStatus.REPAIR_REQUIRED
    assert view.status is ProjectRepairStatus.REPAIR_REQUIRED


def test_new_same_reference_change_after_not_verified_reenters_revalidation() -> None:
    verification_run = _run("run_" + "7" * 32, created_at_us=30, finished_at_us=40)
    change_id = "chg_" + "9" * 32
    history = [
        *_source_history(_REQUIREMENT),
        (
            verification_run,
            _presentation(
                RunVerdict.BLOCK,
                verification=_verification(RepairVerificationStatus.NOT_VERIFIED),
            ),
        ),
    ]

    view = _evaluate(
        _service(
            history,
            changes={_reference_key(_REFERENCE): (change_id, 41)},
            revalidation=ProjectRevalidationStatus.REVIEW_REQUIRED,
        )
    )

    assert view.status is ProjectRepairStatus.CHANGE_SUBMITTED
    assert view.tasks[0].linked_change_id == change_id
    assert view.tasks[0].verification_status is None


def test_inconclusive_without_new_change_keeps_recovery_state() -> None:
    verification_run = _run("run_" + "7" * 32, created_at_us=30, finished_at_us=40)
    history = [
        *_source_history(_REQUIREMENT),
        (
            verification_run,
            _presentation(
                RunVerdict.INCONCLUSIVE,
                verification=_verification(RepairVerificationStatus.INCONCLUSIVE),
            ),
        ),
    ]

    view = _evaluate(_service(history))

    assert view.status is ProjectRepairStatus.INCONCLUSIVE
    assert view.next_path == "/preparation"


def test_new_same_reference_change_after_inconclusive_starts_new_revalidation() -> None:
    verification_run = _run("run_" + "7" * 32, created_at_us=30, finished_at_us=40)
    change_id = "chg_" + "a" * 32
    history = [
        *_source_history(_REQUIREMENT),
        (
            verification_run,
            _presentation(
                RunVerdict.INCONCLUSIVE,
                verification=_verification(RepairVerificationStatus.INCONCLUSIVE),
            ),
        ),
    ]

    view = _evaluate(
        _service(
            history,
            changes={_reference_key(_REFERENCE): (change_id, 41)},
        )
    )

    assert view.status is ProjectRepairStatus.READY_TO_VERIFY
    assert view.tasks[0].linked_change_id == change_id


def test_verified_repair_remains_terminal_after_later_ordinary_pass() -> None:
    verification_run = _run("run_" + "7" * 32, created_at_us=30, finished_at_us=40)
    ordinary_pass = _run("run_" + "8" * 32, created_at_us=50, finished_at_us=60)
    history = [
        *_source_history(_REQUIREMENT),
        (
            verification_run,
            _presentation(
                RunVerdict.PASS,
                verification=_verification(RepairVerificationStatus.VERIFIED),
            ),
        ),
        (ordinary_pass, _presentation(RunVerdict.PASS)),
    ]

    view = _evaluate(_service(history))

    assert view.status is ProjectRepairStatus.VERIFIED
    assert view.tasks[0].verification_status is RepairVerificationStatus.VERIFIED


def test_ordinary_pass_never_substitutes_for_repair_verification() -> None:
    ordinary_pass = _run("run_" + "8" * 32, created_at_us=40, finished_at_us=50)
    change_id = "chg_" + "b" * 32
    history = [
        *_source_history(_REQUIREMENT),
        (ordinary_pass, _presentation(RunVerdict.PASS)),
    ]

    view = _evaluate(
        _service(
            history,
            changes={_reference_key(_REFERENCE): (change_id, 30)},
            revalidation=ProjectRevalidationStatus.VERIFIED,
        )
    )

    assert view.status is ProjectRepairStatus.READY_TO_VERIFY
    assert view.tasks[0].verification_status is None


def test_stale_repair_reference_fails_closed() -> None:
    view = _evaluate(_service(_source_history(_REQUIREMENT), stale=True))

    assert view.status is ProjectRepairStatus.STALE
    assert view.next_path == "/results"
    assert view.reason_codes == (ErrorCode.STATE_PRECONDITION.value,)
