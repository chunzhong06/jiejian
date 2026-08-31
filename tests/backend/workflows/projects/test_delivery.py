# 验证交付检查按固定 fail-closed 顺序核对源码、权限、重验与可信结果。

from __future__ import annotations

from types import SimpleNamespace

import pytest

from product.backend.core.lifecycle import RunVerdict
from product.backend.workflows.projects.delivery import (
    DeliveryCheckService,
    DeliveryDecision,
)
from product.backend.workflows.projects.repair import ProjectRepairStatus
from product.backend.workflows.projects.revalidation import ProjectRevalidationStatus
from product.backend.workflows.source_changes import (
    SourceWorkspaceInspection,
    SourceWorkspaceInspectionStatus,
)
from product.protocols.execution_request import (
    LegacyPersistedExecutionRequest,
    PersistedExecutionRequest,
    build_permission_policy_snapshot,
)
from tests.fixtures.runner import runner_input


_PROJECT_ID = "runner-project"
_RUN_ID = "run_" + "1" * 32
_INTENT_ID = "pin_" + "2" * 32
_INTENT_HASH = "3" * 64
_SOURCE_FINGERPRINT = "4" * 64


def _request(*, legacy: bool = False):
    current_input = runner_input()
    common = {
        "budget": current_input.budget,
        "permission_policy": build_permission_policy_snapshot(_PROJECT_ID, 0, ()),
        "project_snapshot": current_input.project_snapshot,
    }
    if legacy:
        return LegacyPersistedExecutionRequest(schema_version="1", **common)
    return PersistedExecutionRequest(
        schema_version="2",
        source_fingerprint=_SOURCE_FINGERPRINT,
        **common,
    )


class _SourceChanges:
    def __init__(
        self,
        status: SourceWorkspaceInspectionStatus,
        *,
        live_source_fingerprint: str | None = _SOURCE_FINGERPRINT,
    ) -> None:
        self._status = status
        self._live = live_source_fingerprint

    def inspect_workspace(self, project_id: str) -> SourceWorkspaceInspection:
        assert project_id == _PROJECT_ID
        return SourceWorkspaceInspection(
            project_id=project_id,
            status=self._status,
            registered_source_fingerprint=_SOURCE_FINGERPRINT,
            live_source_fingerprint=self._live,
            reason_codes=(f"SOURCE_WORKSPACE_{self._status.value}",),
        )


class _PublishedReader:
    def __init__(self, request) -> None:
        self._request = request

    def read(self, run_id: str):
        assert run_id == _RUN_ID
        return object()

    def execution_request(self, _published):
        return self._request


def _intent(*, intent_hash: str = _INTENT_HASH):
    return SimpleNamespace(
        intent_id=_INTENT_ID,
        revision=1,
        intent_hash=intent_hash,
    )


def _check(
    *,
    workspace_status: SourceWorkspaceInspectionStatus = SourceWorkspaceInspectionStatus.CURRENT,
    live_source_fingerprint: str | None = _SOURCE_FINGERPRINT,
    legacy: bool = False,
    current_intent_hash: str = _INTENT_HASH,
    run_intent_hash: str = _INTENT_HASH,
    repair_status: ProjectRepairStatus = ProjectRepairStatus.NONE,
    revalidation_status: ProjectRevalidationStatus = ProjectRevalidationStatus.NO_CHANGE,
    uncovered_count: int = 0,
    verdict: RunVerdict = RunVerdict.PASS,
    no_result: bool = False,
    login_expired: bool = False,
):
    repair = SimpleNamespace(
        status=repair_status,
        reason_codes=(f"REPAIR_{repair_status.value}",),
        next_path="/results",
        next_label="继续处理修复",
    )
    revalidation = SimpleNamespace(
        status=revalidation_status,
        reason_codes=(f"REVALIDATION_{revalidation_status.value}",),
        next_path="/validation",
        next_label="完成代码变化重验",
    )
    recovery = SimpleNamespace(
        next_path="/preparation",
        next_label="恢复复验条件",
    )
    status = SimpleNamespace(
        repair=repair,
        revalidation=revalidation,
        latest_result=None if no_result else SimpleNamespace(run_id=_RUN_ID),
        inconclusive_recovery=recovery,
        login_expired=login_expired,
    )
    presentation = SimpleNamespace(
        relevant_intents=(_intent(intent_hash=run_intent_hash),),
        uncovered_count=uncovered_count,
        verdict=verdict,
    )
    service = DeliveryCheckService(
        source_changes=_SourceChanges(
            workspace_status,
            live_source_fingerprint=live_source_fingerprint,
        ),
        permission_intents=SimpleNamespace(
            current_intents=lambda project_id: (
                _intent(intent_hash=current_intent_hash),
            )
        ),
        product_status=SimpleNamespace(get=lambda project_id: status),
        result_presentation=SimpleNamespace(build=lambda run_id: presentation),
        published_reader=_PublishedReader(_request(legacy=legacy)),
    )
    return service.check(_PROJECT_ID)


def test_current_v2_pass_with_matching_source_and_permissions_is_ready() -> None:
    view = _check(login_expired=True)

    assert view.decision is DeliveryDecision.READY
    assert view.verified_run_id == _RUN_ID
    assert view.next_path is None


@pytest.mark.parametrize(
    ("kwargs", "expected_reason", "expected_path"),
    (
        (
            {"workspace_status": SourceWorkspaceInspectionStatus.DRIFTED},
            "SOURCE_WORKSPACE_DRIFTED",
            "/changes",
        ),
        ({"legacy": True}, "LEGACY_EXECUTION_REQUEST", "/validation"),
        (
            {"current_intent_hash": "5" * 64},
            "PERMISSION_IDENTITY_CHANGED",
            "/permissions",
        ),
        (
            {"live_source_fingerprint": "6" * 64},
            "RUN_SOURCE_IDENTITY_CHANGED",
            "/validation",
        ),
        ({"uncovered_count": 1}, "RESULT_SCOPE_UNCOVERED", "/preparation"),
        (
            {"revalidation_status": ProjectRevalidationStatus.READY},
            "PROJECT_REVALIDATION_READY",
            "/validation",
        ),
        ({"verdict": RunVerdict.BLOCK}, "RESULT_BLOCK", "/results"),
        (
            {"verdict": RunVerdict.INCONCLUSIVE},
            "RESULT_INCONCLUSIVE",
            "/preparation",
        ),
        ({"no_result": True}, "TRUSTED_RESULT_MISSING", "/validation"),
    ),
)
def test_delivery_blockers_preserve_fixed_order_and_next_action(
    kwargs: dict[str, object],
    expected_reason: str,
    expected_path: str,
) -> None:
    view = _check(**kwargs)

    assert view.decision is DeliveryDecision.BLOCKED
    assert expected_reason in view.reason_codes
    assert view.next_path == expected_path


def test_source_scan_failure_is_delivery_error() -> None:
    view = _check(
        workspace_status=SourceWorkspaceInspectionStatus.UNAVAILABLE,
        live_source_fingerprint=None,
    )

    assert view.decision is DeliveryDecision.ERROR
    assert "SOURCE_WORKSPACE_UNAVAILABLE" in view.reason_codes
    assert view.verified_run_id is None


def test_latest_ordinary_pass_cannot_override_unfinished_project_repair() -> None:
    view = _check(
        verdict=RunVerdict.PASS,
        repair_status=ProjectRepairStatus.REPAIR_REQUIRED,
    )

    assert view.decision is DeliveryDecision.BLOCKED
    assert "PROJECT_REPAIR_REPAIR_REQUIRED" in view.reason_codes
    assert view.next_path == "/results"
