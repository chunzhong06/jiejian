# 验证项目式录制提交的正式来源、同动作同账号补录与秘密清理。

from pathlib import Path
from unittest.mock import Mock

import pytest

from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.core.recording import RecordingPurpose
from product.backend.workflows.recording.project_submission import ProjectRecordingService
from tests.fixtures.recording import RecordingContext


def test_other_role_recording_freezes_subject_and_owner_and_requires_confirmation(tmp_path):
    from tests.fixtures.action_preparation import build_preparation_harness
    from tests.fixtures.assurance import permission, ACTOR, OTHER_ACTOR
    from product.backend.core.permission_intent import PermissionIntentRelation
    from product.backend.workflows.preparation.demonstrations import legal_demonstrations
    harness = build_preparation_harness(tmp_path, identity_count=2, second_actor=True)
    try:
        core = harness.core
        with core.uow_factory() as work:
            work.permission_intents.add_revision(permission(3, subject=OTHER_ACTOR, owner=ACTOR,
                relation=PermissionIntentRelation.OTHER_ROLE).model_copy(update={"project_id": harness.project_id}))
            work.commit()
        prepared = core.preparation.get(harness.project_id).actions[0]
        choice = next(item for item in legal_demonstrations(prepared.assurance_contract, prepared.permissions,
            prepared.identity_requirements) if item.subject_test_identity_id != item.resource_owner_test_identity_id)
        arguments = dict(business_action_id=harness.action.action_id, action_revision=1,
            subject_test_identity_id=choice.subject_test_identity_id,
            resource_owner_test_identity_id=choice.resource_owner_test_identity_id,
            subject_slot_id=choice.subject_slot_id, resource_owner_slot_id=choice.resource_owner_slot_id,
            duration_seconds=60, idempotency_key="other-role")
        with pytest.raises(JiejianError):
            core.project_recordings.submit(harness.project_id, **arguments)
        assert core.runtime_secrets.model_dump() == {"session_count": 0}
        started = core.project_recordings.submit(harness.project_id, **arguments, resource_owner_confirmed=True)
        assert started.request.sessions[0].test_identity_id == choice.subject_test_identity_id
        assert started.result.recording.subject_test_identity_id == choice.subject_test_identity_id
        assert started.result.recording.resource_owner_test_identity_id == choice.resource_owner_test_identity_id
        assert started.result.recording.subject_test_identity_id != started.result.recording.resource_owner_test_identity_id
    finally:
        harness.close()


@pytest.mark.parametrize("duration", [0, -1, 3601, True, 1.5])
def test_project_recording_rejects_unbounded_duration_before_side_effects(duration) -> None:
    dependency = Mock(side_effect=AssertionError("不可进入依赖"))
    service = ProjectRecordingService(dependency, dependency, dependency, dependency, business_boundaries=dependency)
    with pytest.raises(JiejianError) as error:
        service.submit("project_current", business_action_id="bac_" + "1" * 32,
            action_revision=1, subject_test_identity_id="tid_" + "1" * 32,
            resource_owner_test_identity_id="tid_" + "1" * 32,
            subject_slot_id="isl_" + "1" * 32, resource_owner_slot_id="isl_" + "1" * 32,
            duration_seconds=duration, idempotency_key="invalid-duration")
    assert error.value.code == ErrorCode.INPUT_INVALID.value
    assert dependency.mock_calls == []


def _arguments(context):
    position = context.harness.core.preparation.get(context.project_id).actions[0].assurance_contract.identity_requirements.permissions[0]
    return dict(business_action_id=context.harness.action.action_id, action_revision=1,
        subject_test_identity_id=context.harness.identities[0].identity_id,
        resource_owner_test_identity_id=context.harness.identities[0].identity_id,
        subject_slot_id=position.subject_slot_id, resource_owner_slot_id=position.resource_owner_slot_id,
        duration_seconds=60, idempotency_key="supplement")


def test_supplement_reuses_parent_action_and_identity(tmp_path: Path) -> None:
    context = RecordingContext(tmp_path)
    try:
        parent = context.complete_target()
        result = context.harness.core.project_recordings.submit(context.project_id,
            **_arguments(context), purpose=RecordingPurpose.OBSERVATION,
            parent_recording_id=parent.recording_id, effect_id=context.harness.effect_id)
        assert result.request.business_action_id == parent.business_action_id
        assert result.request.action_revision == parent.action_revision
        assert result.request.subject_test_identity_id == parent.subject_test_identity_id
        assert result.request.sessions[0].test_identity_id == parent.subject_test_identity_id
        assert result.result.recording.purpose is RecordingPurpose.OBSERVATION
        assert result.result.recording.effect_id == context.harness.effect_id
        assert result.result.recording.parent_recording_id == parent.recording_id
    finally:
        context.harness.close()


@pytest.mark.parametrize("field,value", [
    ("business_action_id", "bac_" + "9" * 32),
    ("action_revision", 2),
    ("subject_test_identity_id", "tid_" + "9" * 32),
    ("resource_owner_test_identity_id", "tid_" + "9" * 32),
])
def test_supplement_rejects_different_parent_source_before_browser_session(tmp_path, monkeypatch, field, value) -> None:
    context = RecordingContext(tmp_path)
    try:
        parent = context.complete_target()
        credentials = Mock(side_effect=AssertionError("不可准备秘密"))
        monkeypatch.setattr(context.harness.core.recording_credentials, "prepare", credentials)
        arguments = _arguments(context) | {field: value}
        with pytest.raises(JiejianError) as error:
            context.harness.core.project_recordings.submit(context.project_id, **arguments,
                purpose=RecordingPurpose.RECOVERY, parent_recording_id=parent.recording_id)
        assert error.value.code == ErrorCode.INPUT_INVALID.value
        credentials.assert_not_called()
    finally:
        context.harness.close()


@pytest.mark.parametrize("purpose,effect", [
    (RecordingPurpose.OBSERVATION, None),
    (RecordingPurpose.OBSERVATION, "bef_" + "9" * 32),
    (RecordingPurpose.RECOVERY, "bef_" + "1" * 32),
])
def test_supplement_rejects_missing_or_foreign_effect(tmp_path, purpose, effect) -> None:
    context = RecordingContext(tmp_path)
    try:
        parent = context.complete_target()
        with pytest.raises(JiejianError) as error:
            context.harness.core.project_recordings.submit(context.project_id, **_arguments(context),
                purpose=purpose, parent_recording_id=parent.recording_id, effect_id=effect)
        assert error.value.code == ErrorCode.INPUT_INVALID.value
        assert context.harness.core.runtime_secrets.model_dump() == {"session_count": 0}
    finally:
        context.harness.close()


def test_submission_failure_clears_only_this_recording_vault(tmp_path, monkeypatch) -> None:
    context = RecordingContext(tmp_path)
    core = context.harness.core
    try:
        core.runtime_secrets.put("other-recording", {"OTHER": "other-secret"})
        def fail(_command):
            assert core.runtime_secrets.model_dump() == {"session_count": 2}
            raise JiejianError(ErrorCode.RECORD_STATE_PRECONDITION, "来源已变化")
        monkeypatch.setattr(core.recording_submission, "submit", fail)
        with pytest.raises(JiejianError) as error:
            core.project_recordings.submit(context.project_id, **_arguments(context))
        assert error.value.code == ErrorCode.RECORD_STATE_PRECONDITION.value
        assert core.runtime_secrets.model_dump() == {"session_count": 1}
        assert core.runtime_secrets.resolve(("OTHER",)) == {"OTHER": "other-secret"}
    finally:
        context.harness.close()


def test_read_only_action_rejects_recovery_before_credentials(tmp_path, monkeypatch) -> None:
    context = RecordingContext(tmp_path, state_changing=False)
    try:
        parent = context.complete_target()
        prepare = Mock(side_effect=AssertionError("只读动作不可准备恢复会话"))
        monkeypatch.setattr(context.harness.core.recording_credentials, "prepare", prepare)
        with pytest.raises(JiejianError) as error:
            context.harness.core.project_recordings.submit(context.project_id, **_arguments(context),
                purpose=RecordingPurpose.RECOVERY, parent_recording_id=parent.recording_id)
        assert error.value.code == ErrorCode.INPUT_INVALID.value
        prepare.assert_not_called()
    finally:
        context.harness.close()
