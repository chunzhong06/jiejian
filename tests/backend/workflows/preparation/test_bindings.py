# 验证 Recording 最终化与动作技术绑定在真实 SQLite 事务中的闭环。

from __future__ import annotations

import hashlib
import json

import pytest

from product.backend.core.action_preparation import (
    ActionResourceBinding,
    ActionEvidenceKind,
    RegisteredObserverReference,
)
from product.backend.core.application_understanding import (
    ActionCandidate,
    CandidateConfidence,
    CandidateDecision,
    CandidateEvidence,
    CandidateOrigin,
    candidate_id,
)
from product.backend.core.assurance import compile_action_assurance
from product.backend.core.business_boundary import (
    ActionImplementationBinding,
    BusinessAction,
    BusinessActor,
    boundary_sha256,
)
from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.core.lifecycle import ProjectStatus
from product.backend.core.recording import RecordingPurpose, RecordingState
from product.backend.infra.storage import FlowDraftRevisionRecord, RecordingRecord
from product.backend.infra.storage.action_preparation import ActionPreparationRepository
from product.backend.infra.storage.projects import ProjectRecord
from product.backend.workflows.preparation.bindings import PreparationBindingService
from product.backend.workflows.preparation.models import PreparationStatus
from product.backend.workflows.preparation.service import PreparationService
from product.backend.workflows.recording.lifecycle import RecordingLifecycle
from product.backend.workflows.recording.source import require_recording_source
from product.protocols.flow_draft import canonical_flow_draft_json_bytes

from tests.fixtures.action_preparation import (
    PreparationHarness,
    add_recording,
    build_preparation_harness,
)
from tests.fixtures import assurance


def _finalize(harness: PreparationHarness, recording: RecordingRecord):
    return harness.core.recording_lifecycle.finalize(
        recording.recording_id,
        var_dir=harness.var_dir,
        now_us=100,
    )


def _flow_hash(flow) -> str:
    payload = json.dumps(
        flow.model_dump(mode="json"),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _records(harness: PreparationHarness, action_id: str):
    with harness.core.uow_factory() as work:
        return (
            work.action_preparation.execution(action_id, 1),
            work.action_preparation.resources(action_id, 1),
            work.action_preparation.evidence(action_id, 1, harness.effect_id),
            work.action_preparation.recovery(action_id, 1),
        )


def _inspect_action(harness: PreparationHarness):
    with harness.core.uow_factory() as work:
        action = work.business_boundaries.action_revision(harness.action.action_id, 1)
        intents = work.permission_intents.list_latest(harness.project_id)
    assert action is not None
    contract = compile_action_assurance(action, intents)
    identities = harness.core.test_identities.list(harness.project_id)
    identity_view = PreparationService._identities(
        contract,
        identities,
        {(harness.actor.actor_id, 1): harness.actor.display_name},
    )
    return harness.core.preparation_bindings.inspect(action, contract, identity_view)


def _binding_facts(harness: PreparationHarness):
    with harness.core.uow_factory() as work:
        execution = work.action_preparation.execution(harness.action.action_id, 1)
        resource = work.action_preparation.resource(
            harness.action.action_id,
            1,
            harness.identities[0].identity_id,
        )
    assert execution is not None and resource is not None
    return execution.model_dump(mode="json"), resource.model_dump(mode="json")


def _replace_understanding(harness: PreparationHarness, **updates) -> None:
    with harness.core.uow_factory() as work:
        current = work.application_understanding.get(harness.project_id)
        assert current is not None
        work.application_understanding.replace(
            current.model_copy(update={**updates, "updated_at_us": current.updated_at_us + 1})
        )
        work.commit()


def _apply_source_drift(harness: PreparationHarness, recording: RecordingRecord, drift: str) -> None:
    if drift == "confirmed_endpoint":
        _replace_understanding(harness, confirmed_endpoint="http://127.0.0.1:8766")
        return
    if drift == "endpoint_fingerprint":
        _replace_understanding(harness, endpoint_source_fingerprint="a" * 64)
        return
    if drift == "understanding_source":
        _replace_understanding(harness, source_fingerprint="b" * 64)
        return
    if drift == "action_revision":
        with harness.core.uow_factory() as work:
            current = work.business_boundaries.action_revision(harness.action.action_id, 1)
            root = work.business_boundaries.action(harness.action.action_id)
            assert current is not None and root is not None
            created_at_us = max(current.created_at_us, root.updated_at_us) + 1
            revised = current.model_copy(
                update={
                    "revision": 2,
                    "created_at_us": created_at_us,
                    "approval": current.approval.model_copy(update={"approved_at_us": created_at_us}),
                }
            )
            work.business_boundaries.add_action_revision(revised)
            work.business_boundaries.replace_action(
                root.model_copy(update={"current_revision": 2, "updated_at_us": created_at_us})
            )
            work.commit()
        return
    if drift == "actor_revision":
        with harness.core.uow_factory() as work:
            current = work.business_boundaries.actor_revision(harness.actor.actor_id, 1)
            root = work.business_boundaries.actor(harness.actor.actor_id)
            assert current is not None and root is not None
            created_at_us = max(current.created_at_us, root.updated_at_us) + 1
            revised = current.model_copy(
                update={
                    "revision": 2,
                    "created_at_us": created_at_us,
                    "approval": current.approval.model_copy(update={"approved_at_us": created_at_us}),
                }
            )
            work.business_boundaries.add_actor_revision(revised)
            work.business_boundaries.replace_actor(
                root.model_copy(update={"current_revision": 2, "updated_at_us": created_at_us})
            )
            work.commit()
        return
    if drift == "action_implementation":
        with harness.core.uow_factory() as work:
            understanding = work.application_understanding.get(harness.project_id)
            current = work.business_boundaries.action_binding(harness.action.action_id, 1)
            assert understanding is not None and current is not None
            alternate_id = candidate_id("action", "alternate_update")
            alternate = ActionCandidate(
                candidate_id=alternate_id,
                canonical_key="alternate_update",
                display_name="备用更新文档",
                confidence=CandidateConfidence.HIGH,
                decision=CandidateDecision.CONFIRMED,
                origin=CandidateOrigin.DETECTED,
                evidence=understanding.action_candidates[0].evidence,
            )
            updated_understanding = understanding.model_copy(
                update={
                    "action_candidates": (*understanding.action_candidates, alternate),
                    "revision": understanding.revision + 1,
                    "updated_at_us": understanding.updated_at_us + 1,
                }
            )
            work.application_understanding.replace(updated_understanding)
            values = {
                "action_id": current.action_id,
                "action_revision": current.action_revision,
                "understanding_revision": updated_understanding.revision,
                "source_fingerprint": updated_understanding.source_fingerprint,
                "action_candidate_ids": (alternate_id,),
            }
            work.business_boundaries.replace_action_binding(
                ActionImplementationBinding(
                    **values,
                    basis_version=1,
                    binding_fingerprint=boundary_sha256(values),
                    updated_at_us=current.updated_at_us + 1,
                )
            )
            work.commit()
        return
    if drift == "actor_implementation":
        with harness.core.uow_factory() as work:
            current = work.business_boundaries.actor_binding(harness.actor.actor_id, 1)
            assert current is not None
            values = {
                "actor_id": current.actor_id,
                "actor_revision": current.actor_revision,
                "understanding_revision": current.understanding_revision,
                "source_fingerprint": "c" * 64,
                "role_candidate_ids": current.role_candidate_ids,
            }
            from product.backend.core.business_boundary import ActorImplementationBinding

            work.business_boundaries.replace_actor_binding(
                ActorImplementationBinding(
                    **values,
                    basis_version=1,
                    binding_fingerprint=boundary_sha256(values),
                    updated_at_us=current.updated_at_us + 1,
                )
            )
            work.commit()
        return
    if drift == "identity_prepared":
        with harness.core.uow_factory() as work:
            current = work.test_identities.get(harness.identities[0].identity_id)
            assert current is not None
            work.test_identities.replace(
                current.model_copy(
                    update={
                        "auth_method": None,
                        "bearer_secret_ref": None,
                        "prepared_at_us": None,
                        "refreshed_at_us": None,
                        "updated_at_us": current.updated_at_us + 1,
                    }
                )
            )
            work.commit()
        return
    if drift == "identity_secret":
        identity = harness.identities[0]
        harness.core.secret_store.delete(identity.bearer_secret_ref)
        return
    if drift == "latest_draft":
        with harness.core.uow_factory() as work:
            current = work.flow_drafts.latest(recording.recording_id)
            assert current is not None
            draft = current.draft.model_copy(update={"revision": current.revision + 1})
            encoded = canonical_flow_draft_json_bytes(draft)
            work.flow_drafts.add(
                FlowDraftRevisionRecord(
                    recording_id=recording.recording_id,
                    revision=draft.revision,
                    flow_id=draft.flow_id,
                    draft=draft,
                    draft_sha256=hashlib.sha256(encoded).hexdigest(),
                    created_at_us=current.created_at_us + 1,
                )
            )
            work.commit()
        return
    raise AssertionError(f"unknown drift case: {drift}")


@pytest.fixture
def harness(tmp_path):
    value = build_preparation_harness(tmp_path)
    try:
        yield value
    finally:
        value.close()


def test_target_finalize_persists_flow_execution_resource_and_preserves_policy(harness):
    before = harness.core.business_boundaries.view(harness.project_id)
    recording = add_recording(harness)

    result = _finalize(harness, recording)
    assert result.recording.state is RecordingState.COMPLETED
    assert result.flow is not None
    assert result.flow.schema_version == "2"
    assert (
        result.flow.business_action_id,
        result.flow.action_revision,
        result.flow.test_identity_id,
    ) == (harness.action.action_id, 1, harness.identities[0].identity_id)

    execution, resources, _, _ = _records(harness, harness.action.action_id)
    assert execution is not None
    assert len(resources) == 1
    assert resources[0].owner_test_identity_id == harness.identities[0].identity_id
    assert execution.source_draft_sha256 == resources[0].source_draft_sha256
    assert execution.flow_sha256 == resources[0].flow_sha256 == _flow_hash(result.flow)
    assert resources[0].resource_injection == execution.resource_injection

    after = harness.core.business_boundaries.view(harness.project_id)
    assert after.policy_epoch == before.policy_epoch
    assert after.actions[0].revision == before.actions[0].revision
    assert after.permission_intents[0].revision == before.permission_intents[0].revision


def test_owner_resources_coexist_and_duplicate_finalize_keeps_latest_execution(tmp_path):
    harness = build_preparation_harness(tmp_path, identity_count=2)
    try:
        first = add_recording(harness, identity_index=0)
        first_result = _finalize(harness, first)
        second = add_recording(harness, identity_index=1)
        _finalize(harness, second)

        execution, resources, _, _ = _records(harness, harness.action.action_id)
        assert execution is not None
        assert {item.owner_test_identity_id for item in resources} == {
            harness.identities[0].identity_id,
            harness.identities[1].identity_id,
        }
        assert execution.source_recording_id == second.recording_id
        assert all(item.resource_injection == execution.resource_injection for item in resources)

        duplicate = _finalize(harness, first)
        assert duplicate.flow is not None
        assert duplicate.flow.id == first_result.flow.id
        execution_after, resources_after, _, _ = _records(harness, harness.action.action_id)
        assert execution_after is not None
        assert execution_after.source_recording_id == second.recording_id
        assert len(resources_after) == 2
    finally:
        harness.close()


def test_observation_unique_and_ambiguous_candidates_fail_closed(harness):
    target = add_recording(harness)
    _finalize(harness, target)
    ambiguous_without_evidence = add_recording(
        harness,
        purpose=RecordingPurpose.OBSERVATION,
        parent_recording_id=target.recording_id,
        effect_id=harness.effect_id,
        step_count=2,
    )
    with pytest.raises(JiejianError) as error:
        _finalize(harness, ambiguous_without_evidence)
    assert error.value.code == ErrorCode.RECORD_DRAFT_UNCONFIRMED.value
    with harness.core.uow_factory() as work:
        assert work.action_preparation.evidence(harness.action.action_id, 1, harness.effect_id) is None

    observation = add_recording(
        harness,
        purpose=RecordingPurpose.OBSERVATION,
        parent_recording_id=target.recording_id,
        effect_id=harness.effect_id,
    )
    _finalize(harness, observation)
    _, _, evidence, _ = _records(harness, harness.action.action_id)
    assert evidence is not None
    assert evidence.kind is ActionEvidenceKind.RECORDED_OBSERVATION
    evidence_before = evidence.model_dump(mode="json")

    ambiguous = add_recording(
        harness,
        purpose=RecordingPurpose.OBSERVATION,
        parent_recording_id=target.recording_id,
        effect_id=harness.effect_id,
        step_count=2,
    )
    with pytest.raises(JiejianError) as error:
        _finalize(harness, ambiguous)
    assert error.value.code == ErrorCode.RECORD_DRAFT_UNCONFIRMED.value
    with harness.core.uow_factory() as work:
        current = work.recordings.get(ambiguous.recording_id)
        assert current is not None and current.state is RecordingState.PENDING_REVIEW
        evidence_after = work.action_preparation.evidence(harness.action.action_id, 1, harness.effect_id)
        assert evidence_after is not None
        assert evidence_after.model_dump(mode="json") == evidence_before


def test_observation_explicit_step_and_recovery_bindings_complete_preparation(harness):
    target = add_recording(harness)
    _finalize(harness, target)
    observation = add_recording(
        harness,
        purpose=RecordingPurpose.OBSERVATION,
        parent_recording_id=target.recording_id,
        effect_id=harness.effect_id,
        step_count=2,
        target_step_id="first",
    )
    _finalize(harness, observation)
    recovery = add_recording(
        harness,
        purpose=RecordingPurpose.RECOVERY,
        parent_recording_id=target.recording_id,
        method="PATCH",
    )
    _finalize(harness, recovery)

    view = harness.core.preparation.get(harness.project_id)
    assert view.preparation_complete is True
    technical = view.actions[0]
    assert technical.effect_evidence[0].status is PreparationStatus.SATISFIED
    assert technical.recovery.status is PreparationStatus.SATISFIED


def test_read_only_action_does_not_create_recovery_and_stale_source_is_rejected(tmp_path):
    harness = build_preparation_harness(tmp_path, state_changing=False)
    try:
        target = add_recording(harness)
        _finalize(harness, target)
        view = harness.core.preparation.get(harness.project_id)
        assert view.actions[0].recovery.status is PreparationStatus.NOT_REQUIRED

        stale = add_recording(harness)
        with harness.core.uow_factory() as work:
            understanding = work.application_understanding.get(harness.project_id)
            assert understanding is not None
            work.application_understanding.replace(
                understanding.model_copy(
                    update={"source_fingerprint": "f" * 64, "revision": understanding.revision + 1}
                )
            )
            work.commit()
        with pytest.raises(JiejianError) as error:
            _finalize(harness, stale)
        assert error.value.code == ErrorCode.RECORD_STATE_PRECONDITION.value
        with harness.core.uow_factory() as work:
            current = work.recordings.get(stale.recording_id)
            assert current is not None and current.state is RecordingState.PENDING_REVIEW
    finally:
        harness.close()


@pytest.mark.parametrize(
    "drift",
    (
        "confirmed_endpoint",
        "endpoint_fingerprint",
        "understanding_source",
        "action_revision",
        "actor_revision",
        "action_implementation",
        "actor_implementation",
        "identity_prepared",
        "identity_secret",
        "latest_draft",
    ),
)
def test_source_drift_is_live_and_does_not_rewrite_binding_facts(tmp_path, drift):
    harness = build_preparation_harness(tmp_path)
    try:
        target = add_recording(harness)
        _finalize(harness, target)
        before = _binding_facts(harness)
        _apply_source_drift(harness, target, drift)

        if drift == "action_revision":
            view = harness.core.preparation.get(harness.project_id)
            assert view.actions[0].action_revision == 2
            assert view.actions[0].execution.status is PreparationStatus.NEEDS_USER
        else:
            technical = _inspect_action(harness)
            assert technical.execution.status is PreparationStatus.STALE
        assert _binding_facts(harness) == before
    finally:
        harness.close()


def test_context_rejects_invalid_effect_revision_foreign_identity_and_parent_identity(tmp_path):
    harness = build_preparation_harness(tmp_path, identity_count=2)
    try:
        target = add_recording(harness, identity_index=0)
        _finalize(harness, target)

        invalid_effect = add_recording(
            harness,
            purpose=RecordingPurpose.OBSERVATION,
            parent_recording_id=target.recording_id,
            effect_id="bef_" + "9" * 32,
        )
        with pytest.raises(JiejianError) as effect_error:
            _finalize(harness, invalid_effect)
        assert effect_error.value.code == ErrorCode.INPUT_INVALID.value

        # 不存在的 revision 在持久层已被拒绝；在来源边界独立验证相同非法输入。
        with harness.core.uow_factory() as work:
            wrong_revision = target.model_copy(update={"action_revision": 2})
            with pytest.raises(JiejianError) as revision_error:
                require_recording_source(work, wrong_revision)
        assert revision_error.value.code == ErrorCode.RECORD_STATE_PRECONDITION.value

        foreign_project = "foreign-project"
        foreign_actor = assurance.actor(assurance.OTHER_ACTOR).model_copy(update={"project_id": foreign_project})
        foreign_actor = foreign_actor.model_copy(
            update={"semantic_fingerprint": boundary_sha256(foreign_actor.semantic_payload())}
        )
        foreign_root = BusinessActor(
            actor_id=foreign_actor.actor_id,
            project_id=foreign_project,
            current_revision=1,
            created_at_us=foreign_actor.created_at_us,
            updated_at_us=foreign_actor.created_at_us,
        )
        foreign_identity_id = "tid_" + "f" * 32
        foreign_ref = f"cred:jiejian/test-identity/{foreign_project}/{foreign_identity_id}/bearer"
        foreign_identity = harness.identities[0].model_copy(
            update={
                "identity_id": foreign_identity_id,
                "project_id": foreign_project,
                "actor_id": foreign_actor.actor_id,
                "bearer_secret_ref": foreign_ref,
            }
        )
        harness.core.secret_store.write(foreign_ref, "fixture-secret")
        with harness.core.uow_factory() as work:
            work.projects.add(
                ProjectRecord(
                    project_id=foreign_project,
                    name="foreign",
                    status=ProjectStatus.READY,
                    created_at_us=foreign_actor.created_at_us,
                    updated_at_us=foreign_actor.created_at_us,
                )
            )
            work.business_boundaries.add_actor_revision(foreign_actor)
            work.business_boundaries.add_actor(foreign_root)
            work.test_identities.add(foreign_identity)
            work.commit()
        with harness.core.uow_factory() as work:
            bad_source = target.model_copy(update={"test_identity_id": foreign_identity_id})
            with pytest.raises(JiejianError) as foreign_error:
                require_recording_source(work, bad_source)
        assert foreign_error.value.code == ErrorCode.RECORD_STATE_PRECONDITION.value

        parent_identity = add_recording(
            harness,
            identity_index=1,
            purpose=RecordingPurpose.OBSERVATION,
            parent_recording_id=target.recording_id,
            effect_id=harness.effect_id,
        )
        with pytest.raises(JiejianError) as parent_error:
            _finalize(harness, parent_identity)
        assert parent_error.value.code == ErrorCode.RECORD_STATE_PRECONDITION.value

        with harness.core.uow_factory() as work:
            for recording_id in (invalid_effect.recording_id, parent_identity.recording_id):
                current = work.recordings.get(recording_id)
                assert current is not None and current.state is RecordingState.PENDING_REVIEW
            assert work.action_preparation.execution(harness.action.action_id, 1) is not None
            assert work.action_preparation.resource(harness.action.action_id, 1, harness.identities[1].identity_id) is None
    finally:
        harness.close()


def test_read_only_recovery_is_rejected_without_recovery_row(tmp_path):
    harness = build_preparation_harness(tmp_path, state_changing=False)
    try:
        target = add_recording(harness)
        _finalize(harness, target)
        recovery = add_recording(
            harness,
            purpose=RecordingPurpose.RECOVERY,
            parent_recording_id=target.recording_id,
            method="PATCH",
        )
        with pytest.raises(JiejianError) as error:
            _finalize(harness, recovery)
        assert error.value.code == ErrorCode.INPUT_INVALID.value
        with harness.core.uow_factory() as work:
            current = work.recordings.get(recovery.recording_id)
            assert current is not None and current.state is RecordingState.PENDING_REVIEW
            assert work.action_preparation.recovery(harness.action.action_id, 1) is None
        view = harness.core.preparation.get(harness.project_id)
        assert view.actions[0].recovery.status is PreparationStatus.NOT_REQUIRED
    finally:
        harness.close()


def test_live_inspection_marks_flow_drift_stale_without_persisting_status(harness):
    target = add_recording(harness)
    result = _finalize(harness, target)
    assert result.flow is not None
    before = harness.core.preparation.get(harness.project_id).actions[0]
    assert before.execution.status is PreparationStatus.SATISFIED

    drifted = result.flow.model_copy(update={"id": "flow_drift_" + "1" * 8})
    path = RecordingLifecycle.flow_path(harness.var_dir, target)
    path.write_text(
        json.dumps(drifted.model_dump(mode="json"), ensure_ascii=False, sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )
    after = harness.core.preparation.get(harness.project_id).actions[0]
    assert after.execution.status is PreparationStatus.STALE
    with harness.core.uow_factory() as work:
        binding = work.action_preparation.execution(harness.action.action_id, 1)
        assert binding is not None
        assert binding.flow_id == result.flow.id


class _ObserverReader:
    def __init__(self, reference: RegisteredObserverReference) -> None:
        self.reference = reference
        self.enabled = True

    def contains(self, project_id: str, reference: RegisteredObserverReference) -> bool:
        return self.enabled and project_id == reference.observer_id and reference == self.reference


def test_registered_observer_requires_controlled_reader_and_becomes_stale(harness):
    target = add_recording(harness)
    _finalize(harness, target)
    reference = RegisteredObserverReference(
        descriptor_id="exp_" + "1" * 32,
        descriptor_fingerprint="2" * 64,
        observer_id=harness.project_id,
    )
    reader = _ObserverReader(reference)
    service = PreparationBindingService(
        harness.core.uow_factory,
        harness.var_dir,
        test_identities=harness.core.test_identities,
        registered_observers=reader,
    )
    binding = service.register_observer(
        target.recording_id,
        effect_id=harness.effect_id,
        reference=reference,
        now_us=101,
    )
    assert binding.kind is ActionEvidenceKind.REGISTERED_OBSERVER
    assert binding.observer_reference == reference

    boundary = harness.core.business_boundaries.view(harness.project_id)
    contract = compile_action_assurance(boundary.actions[0], boundary.permission_intents)
    identities = harness.core.test_identities.list(harness.project_id)
    actor_names = {(item.actor_id, item.revision): item.display_name for item in boundary.actors}
    identity_view = PreparationService._identities(contract, identities, actor_names)
    technical = service.inspect(boundary.actions[0], contract, identity_view)
    assert technical.effect_evidence[0].status is PreparationStatus.SATISFIED
    reader.enabled = False
    stale = service.inspect(boundary.actions[0], contract, identity_view)
    assert stale.effect_evidence[0].status is PreparationStatus.STALE

    no_reader = PreparationBindingService(harness.core.uow_factory, harness.var_dir)
    with pytest.raises(JiejianError):
        no_reader.register_observer(
            target.recording_id,
            effect_id=harness.effect_id,
            reference=reference,
            now_us=102,
        )


def test_binding_failure_rolls_back_recording_and_row_but_retry_reuses_published_flow(harness, monkeypatch):
    target = add_recording(harness)
    original_replace = ActionPreparationRepository.replace
    replace_calls = []

    def fail_on_resource_replace(repository, binding):
        replace_calls.append(type(binding).__name__)
        if isinstance(binding, ActionResourceBinding):
            raise RuntimeError("fixture injected second binding failure")
        return original_replace(repository, binding)

    monkeypatch.setattr(ActionPreparationRepository, "replace", fail_on_resource_replace)
    with pytest.raises(RuntimeError, match="second binding failure"):
        harness.core.recording_lifecycle.finalize(
            target.recording_id,
            var_dir=harness.var_dir,
            now_us=100,
        )
    assert replace_calls == ["ActionExecutionBinding", "ActionResourceBinding"]
    monkeypatch.undo()
    flow_path = RecordingLifecycle.flow_path(harness.var_dir, target)
    assert flow_path.exists()
    with harness.core.uow_factory() as work:
        current = work.recordings.get(target.recording_id)
        assert current is not None and current.state is RecordingState.PENDING_REVIEW
        assert work.action_preparation.execution(harness.action.action_id, 1) is None
        assert work.action_preparation.resource(harness.action.action_id, 1, harness.identities[0].identity_id) is None

    retry = _finalize(harness, target)
    assert retry.recording.state is RecordingState.COMPLETED


def test_deleted_identity_preserves_recordings_flows_and_all_bindings_but_invalidates_preparation(harness):
    target = add_recording(harness)
    target_result = _finalize(harness, target)
    observation = add_recording(harness, purpose=RecordingPurpose.OBSERVATION,
        parent_recording_id=target.recording_id, effect_id=harness.effect_id)
    recovery = add_recording(harness, purpose=RecordingPurpose.RECOVERY,
        parent_recording_id=target.recording_id, method="PATCH")
    _finalize(harness, observation)
    _finalize(harness, recovery)
    assert harness.core.preparation.get(harness.project_id).preparation_complete is True
    identity = harness.identities[0]
    before_bindings = _records(harness, harness.action.action_id)
    flow_path = RecordingLifecycle.flow_path(harness.var_dir, target)
    before_flow = flow_path.read_bytes()
    with harness.core.uow_factory() as work:
        before_recordings = tuple(work.recordings.get(item.recording_id) for item in (target, observation, recovery))
        before_drafts = tuple(work.flow_drafts.list_for_recording(item.recording_id) for item in (target, observation, recovery))
    harness.core.secret_store.write("unrelated-secret-reference", "keep-me")

    harness.core.test_identities.delete(identity.identity_id)

    assert harness.core.secret_store.read(identity.bearer_secret_ref) is None
    assert harness.core.secret_store.read("unrelated-secret-reference") == "keep-me"
    with harness.core.uow_factory() as work:
        assert work.test_identities.get(identity.identity_id) is None
        assert tuple(work.recordings.get(item.recording_id) for item in (target, observation, recovery)) == before_recordings
        assert tuple(work.flow_drafts.list_for_recording(item.recording_id) for item in (target, observation, recovery)) == before_drafts
    assert _records(harness, harness.action.action_id) == before_bindings
    execution, resources, evidence, recovery_binding = before_bindings
    assert all(item.test_identity_id == identity.identity_id for item in (execution, *resources, evidence, recovery_binding))
    assert resources[0].owner_test_identity_id == identity.identity_id
    assert flow_path.read_bytes() == before_flow
    assert target_result.flow.test_identity_id == identity.identity_id
    view = harness.core.preparation.get(harness.project_id)
    assert view.preparation_complete is False
    assert view.actions[0].execution.status is PreparationStatus.STALE
    assert view.actions[0].recovery.status is PreparationStatus.STALE
    assert all(item.status is PreparationStatus.STALE for item in view.actions[0].effect_evidence)
