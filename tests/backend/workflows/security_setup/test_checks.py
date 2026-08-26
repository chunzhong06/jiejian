# 验证普通检查只投影现有计划，并以当前 Generated Profile 提交唯一执行链。

from pathlib import Path

import pytest

from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.core.lifecycle import ProjectStatus
from product.backend.core.permission_intent import PermissionIntentRelation
from product.backend.core.test_identity import (
    TestIdentity as IdentityRecord,
    TestIdentityAuthMethod as IdentityAuthMethod,
)
from product.backend.core.verification.permissions import PermissionExpectation
from product.backend.workflows.context import ApplicationCore
from tests.backend.workflows.recording.test_action_safety_setup import (
    ACTION_ID,
    ENDPOINT_FINGERPRINT,
    IDENTITY_ID,
    NOW_US,
    PROJECT_ID,
    RECORDING_ID,
    ROLE_ID,
    _FakeSecretStore,
    _confirmation,
    _persist_completed_recording,
)


pytestmark = pytest.mark.database
PEER_IDENTITY_ID = "tid_" + "7" * 32


def test_check_preview_and_submit_reuse_current_frozen_execution_plan(
    tmp_path: Path,
) -> None:
    core = _prepared_core(tmp_path)
    try:
        before = core.checks.preview(PROJECT_ID)
        assert before.ready is False
        assert before.next_path == "/apps/rules"
        assert {item.code for item in before.gaps} == {"GENERATED_PROFILE_MISSING"}

        compiled = core.security_setup.compile(PROJECT_ID, actor="测试用户")
        preview = core.checks.preview(PROJECT_ID)

        assert preview.ready is True
        assert preview.gaps == ()
        assert preview.case_count == 2
        assert preview.differential_pair_count == 1
        assert len(preview.actions) == 1
        assert preview.actions[0].action_display_name == "修改所有者资源"
        assert {item.expectation for item in preview.actions[0].checks} == {
            PermissionExpectation.ALLOW,
            PermissionExpectation.DENY,
        }
        assert all(item.ready for item in preview.actions[0].checks)
        with core.uow_factory() as work:
            project = work.projects.get(PROJECT_ID)
        assert project is not None
        assert project.status is ProjectStatus.READY

        submission, request, _ = core.checks.submit(
            PROJECT_ID,
            idempotency_key="ordinary-check-1",
        )
        snapshot = request.project_snapshot
        assert submission.run.project_id == PROJECT_ID
        assert not snapshot.plan.gaps
        assert not snapshot.differential_plan.gaps
        assert len(snapshot.differential_plan.twins) == 1
        assert snapshot.workflow_bindings[0].action_id == ACTION_ID
        assert (
            core.security_setup.current_generated_profile_id(PROJECT_ID)
            == compiled.profile_id
        )
    finally:
        core.close()


def test_check_preview_runs_complete_subset_and_keeps_other_action_gap(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from tests.backend.workflows.recording import test_action_safety_setup as setup_fixture

    original_understanding = setup_fixture._understanding

    def understanding_with_uncovered_action():
        source = original_understanding()
        uncovered = source.action_candidates[0].model_copy(
            update={
                "candidate_id": "action_" + "8" * 32,
                "canonical_key": "view_owner_resource",
                "display_name": "查看所有者资源",
            }
        )
        return source.model_copy(
            update={"action_candidates": (*source.action_candidates, uncovered)}
        )

    monkeypatch.setattr(
        setup_fixture,
        "_understanding",
        understanding_with_uncovered_action,
    )
    core = _prepared_core(tmp_path)
    try:
        core.security_setup.compile(PROJECT_ID, actor="测试用户")

        preview = core.checks.preview(PROJECT_ID)

        assert preview.ready is True
        assert preview.case_count == 2
        assert preview.differential_pair_count == 1
        assert [item.ready for item in preview.actions] == [True, False]
        assert {gap.code for gap in preview.actions[1].gaps} == {
            "ACTION_FLOW_OR_RESOURCE_MISSING"
        }
        readiness = core.project_readiness.get(PROJECT_ID)
        assert readiness.current_scope_runnable is True
        assert readiness.remaining_gap_count == len(preview.gaps) == 1
        assert readiness.next_required_action == "RUN_CHECK"
        submission, _, _ = core.checks.submit(
            PROJECT_ID,
            idempotency_key="covered-subset-check",
        )
        assert submission.run.project_id == PROJECT_ID
    finally:
        core.close()


def test_check_submit_rejects_stale_preparation_and_returns_earliest_gap(
    tmp_path: Path,
) -> None:
    core = _prepared_core(tmp_path)
    try:
        core.security_setup.compile(PROJECT_ID, actor="测试用户")
        with core.uow_factory() as work:
            understanding = work.application_understanding.get(PROJECT_ID)
            assert understanding is not None
            work.application_understanding.replace(
                understanding.model_copy(
                    update={
                        "source_fingerprint": "c" * 64,
                        "revision": understanding.revision + 1,
                        "updated_at_us": understanding.updated_at_us + 1,
                    }
                )
            )
            work.commit()

        preview = core.checks.preview(PROJECT_ID)
        assert preview.ready is False
        assert preview.next_path == "/apps/flows"
        assert "TEST_RESOURCE_UNCONFIRMED" in {
            item.code for item in preview.gaps
        }
        with pytest.raises(JiejianError) as error:
            core.checks.submit(PROJECT_ID, idempotency_key="stale-check")
        assert error.value.code == ErrorCode.STATE_PRECONDITION.value
        assert error.value.to_dict()["details"]["next_path"] == "/apps/flows"
    finally:
        core.close()


def _prepared_core(tmp_path: Path) -> ApplicationCore:
    store = _FakeSecretStore()
    owner_ref = f"cred:jiejian/test-identity/{PROJECT_ID}/{IDENTITY_ID}/bearer"
    peer_ref = f"cred:jiejian/test-identity/{PROJECT_ID}/{PEER_IDENTITY_ID}/bearer"
    store.write(owner_ref, "owner-secret")
    store.write(peer_ref, "peer-secret")
    core = ApplicationCore(
        tmp_path / "var",
        secret_store=store,
        clock_us=lambda: NOW_US + 100,
    )
    _persist_completed_recording(core, owner_ref)
    preview = core.action_safety_setup.preview(RECORDING_ID)
    core.action_safety_setup.confirm(
        RECORDING_ID,
        _confirmation(preview, include_recovery=True),
    )
    with core.uow_factory() as work:
        work.test_identities.add(
            IdentityRecord(
                identity_id=PEER_IDENTITY_ID,
                project_id=PROJECT_ID,
                role_candidate_id=ROLE_ID,
                role_canonical_key="owner",
                role_display_name="所有者",
                label="同角色其他测试账号",
                confirmed_endpoint="http://127.0.0.1:18080",
                endpoint_source_fingerprint=ENDPOINT_FINGERPRINT,
                understanding_revision=3,
                auth_method=IdentityAuthMethod.BEARER,
                bearer_secret_ref=peer_ref,
                prepared_at_us=NOW_US + 1,
                refreshed_at_us=NOW_US + 1,
                created_at_us=NOW_US,
                updated_at_us=NOW_US + 1,
            )
        )
        work.commit()
    core.permission_intents.confirm(
        PROJECT_ID,
        ACTION_ID,
        ROLE_ID,
        ROLE_ID,
        PermissionIntentRelation.OWNS,
        expectation=PermissionExpectation.ALLOW,
        actor="测试用户",
    )
    core.permission_intents.confirm(
        PROJECT_ID,
        ACTION_ID,
        ROLE_ID,
        ROLE_ID,
        PermissionIntentRelation.SAME_ROLE_OTHER_ACCOUNT,
        expectation=PermissionExpectation.DENY,
        actor="测试用户",
    )
    return core
