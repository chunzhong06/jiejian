# 用真实 SQLite 验证局部替换、重复回执、陈旧拒绝与有限草稿恢复。
from uuid import uuid4
import pytest
from pydantic import ValidationError
from product.backend.core.errors import JiejianError
from product.backend.core.recording.models import RecordingPurpose
from product.backend.workflows.preparation.materials.models import MaterialChange, MaterialReference, PreparationDraft
from tests.fixtures.preparation.action_preparation import build_preparation_harness, add_recording


@pytest.fixture
def materials(tmp_path):
    h = build_preparation_harness(tmp_path)
    target = add_recording(h)
    h.core.recording_lifecycle.finalize(target.recording_id, var_dir=h.var_dir, now_us=100)
    observation = add_recording(h, purpose=RecordingPurpose.OBSERVATION, parent_recording_id=target.recording_id, effect_id=h.effect_id)
    h.core.recording_lifecycle.finalize(observation.recording_id, var_dir=h.var_dir, now_us=100)
    try:
        yield h, target, observation
    finally:
        h.close()


def test_preview_replace_and_duplicate_receipt_preserve_unrelated(materials):
    h, target, observation = materials
    newer = add_recording(h, purpose=RecordingPurpose.OBSERVATION, parent_recording_id=target.recording_id, effect_id=h.effect_id)
    h.core.recording_lifecycle.finalize(newer.recording_id, var_dir=h.var_dir, now_us=100)
    service = h.core.preparation_materials
    ref = MaterialReference(action_id=h.action.action_id, action_revision=1, kind="evidence", member_id=h.effect_id)
    before = h.core.preparation.get(h.project_id)
    details = service.details(h.project_id, ref)
    assert details["status"] == "SATISFIED"
    assert any(item["recording_id"] == observation.recording_id for item in details["candidates"])
    command = MaterialChange(operation_id=uuid4().hex, material=ref,
        expected_fingerprint=details["expected_fingerprint"], candidate_recording_id=observation.recording_id)
    preview = service.preview(h.project_id, command)
    assert preview["updates"] == [ref.model_dump(mode="json")]
    assert preview["recheck"] == []
    assert h.core.preparation.get(h.project_id) == before
    receipt = service.apply(h.project_id, command)
    assert service.apply(h.project_id, command) == receipt
    assert service.receipt(h.project_id, command.operation_id) == receipt
    after = h.core.preparation.get(h.project_id)
    assert after.actions[0].execution == before.actions[0].execution
    assert after.actions[0].resources == before.actions[0].resources
    assert after.actions[0].recovery == before.actions[0].recovery
    assert after.actions[0].effect_evidence != before.actions[0].effect_evidence
    with pytest.raises(JiejianError):
        service.apply(h.project_id, command.model_copy(update={"candidate_recording_id": target.recording_id}))


def test_stale_scope_and_wrong_candidate_rejected(materials):
    h, target, _ = materials
    service = h.core.preparation_materials
    ref = MaterialReference(action_id=h.action.action_id, action_revision=1, kind="evidence", member_id=h.effect_id)
    details = service.details(h.project_id, ref)
    command = MaterialChange(operation_id=uuid4().hex, material=ref,
        expected_fingerprint=details["expected_fingerprint"], candidate_recording_id=target.recording_id)
    with pytest.raises(JiejianError):
        service.preview(h.project_id, command)
    with h.core.uow_factory() as work:
        value = work.application_understanding.get(h.project_id)
        work.application_understanding.replace(value.model_copy(update={"source_fingerprint": "f" * 64}))
        work.commit()
    with pytest.raises(JiejianError):
        service.apply(h.project_id, command.model_copy(update={"candidate_recording_id": None}))
    assert service.details(h.project_id, ref)["status"] == "STALE"


def test_draft_compare_and_swap_and_no_secret_fields(materials):
    h, _, _ = materials
    service = h.core.preparation_materials
    draft = PreparationDraft(revision=0, action_id=h.action.action_id, action_revision=1)
    saved = service.save_draft(h.project_id, draft)
    assert saved["revision"] == 1
    assert service.draft(h.project_id) == saved
    with pytest.raises(JiejianError):
        service.save_draft(h.project_id, draft)
    with pytest.raises(ValidationError):
        PreparationDraft.model_validate({"revision": 1, "cookie": "forbidden"})
    with pytest.raises(ValidationError):
        PreparationDraft(revision=1, pending_operation_id=uuid4().hex)


def test_concurrent_same_operation_returns_one_durable_receipt(materials):
    from concurrent.futures import ThreadPoolExecutor
    h, _, _ = materials
    service = h.core.preparation_materials
    ref = MaterialReference(action_id=h.action.action_id, action_revision=1, kind="evidence", member_id=h.effect_id)
    details = service.details(h.project_id, ref)
    command = MaterialChange(operation_id=uuid4().hex, material=ref, expected_fingerprint=details["expected_fingerprint"])
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(service.apply, h.project_id, command) for _ in range(2)]
        receipts = [future.result() for future in futures]
    assert receipts[0] == receipts[1] == service.receipt(h.project_id, command.operation_id)


def test_archived_materials_cannot_be_rewritten(materials):
    h, _, _ = materials
    service = h.core.preparation_materials
    ref = MaterialReference(action_id=h.action.action_id, action_revision=1, kind="evidence", member_id=h.effect_id)
    details = service.details(h.project_id, ref)
    from product.backend.core.lifecycle import ProjectStatus
    with h.core.uow_factory() as work:
        project = work.projects.get(h.project_id)
        work.projects.replace(project.model_copy(update={"status": ProjectStatus.ARCHIVED}))
        work.commit()
    with pytest.raises(JiejianError):
        service.apply(h.project_id, MaterialChange(operation_id=uuid4().hex, material=ref, expected_fingerprint=details["expected_fingerprint"]))


def test_candidate_review_never_adopts_until_material_confirmation(materials, monkeypatch):
    h, target, _ = materials
    service = h.core.preparation_materials
    ref = MaterialReference(action_id=h.action.action_id, action_revision=1, kind="evidence", member_id=h.effect_id)
    before = h.core.preparation.get(h.project_id)
    candidate = add_recording(h, purpose=RecordingPurpose.OBSERVATION, parent_recording_id=target.recording_id, effect_id=h.effect_id)
    with h.core.uow_factory() as work:
        work.preparation_recovery.mark_candidate_recording(candidate.recording_id)
        work.commit()
    h.core.recording_lifecycle.finalize(candidate.recording_id, var_dir=h.var_dir, now_us=100)
    assert h.core.preparation.get(h.project_id) == before
    details = service.details(h.project_id, ref)
    assert details["recording_context"]["can_execute"]
    command = MaterialChange(operation_id=uuid4().hex, material=ref, expected_fingerprint=details["expected_fingerprint"], candidate_recording_id=candidate.recording_id)
    from product.backend.infra.storage.preparation.preparation_recovery import PreparationRecoveryRepository
    from product.backend.core.errors import ErrorCode
    original = PreparationRecoveryRepository.add_receipt
    def fail(*args): raise JiejianError(ErrorCode.STORAGE_FAILURE, "injected receipt failure")
    monkeypatch.setattr(PreparationRecoveryRepository, "add_receipt", fail)
    with pytest.raises(JiejianError): service.apply(h.project_id, command)
    assert h.core.preparation.get(h.project_id) == before
    monkeypatch.setattr(PreparationRecoveryRepository, "add_receipt", original)
    assert service.apply(h.project_id, command)["result"] == "SAVED"
    assert h.core.preparation.get(h.project_id).actions[0].effect_evidence != before.actions[0].effect_evidence


def test_recording_candidate_intent_is_atomic_with_job_submission(materials):
    h, _, _ = materials
    ref = MaterialReference(action_id=h.action.action_id, action_revision=1, kind="evidence", member_id=h.effect_id)
    context = h.core.preparation_materials.details(h.project_id, ref)["recording_context"]
    result = h.core.project_recordings.submit(h.project_id, business_action_id=h.action.action_id, action_revision=1,
        subject_test_identity_id=context["subject_test_identity_id"], resource_owner_test_identity_id=context["resource_owner_test_identity_id"],
        subject_slot_id=context["subject_slot_id"], resource_owner_slot_id=context["resource_owner_slot_id"],
        resource_owner_confirmed=True, duration_seconds=30, idempotency_key=uuid4().hex,
        purpose=RecordingPurpose.OBSERVATION, parent_recording_id=context["parent_recording_id"], effect_id=h.effect_id, material_candidate=True)
    with h.core.uow_factory() as work:
        assert work.preparation_recovery.candidate_recording(result.result.recording.recording_id)
        assert work.jobs.get(result.result.job.job_id) is not None


def test_local_evidence_replacement_rejects_a_different_owner(tmp_path):
    # 两个正式角色各有自己的合法 ALLOW，拒绝必须发生在局部替换边界，而非录制准备阶段。
    h = build_preparation_harness(tmp_path, identity_count=2, second_actor=True)
    try:
        targets = []
        for index in (0, 1):
            target = add_recording(h, identity_index=index)
            h.core.recording_lifecycle.finalize(target.recording_id, var_dir=h.var_dir, now_us=100)
            targets.append(target)
        original = add_recording(h, purpose=RecordingPurpose.OBSERVATION, parent_recording_id=targets[0].recording_id, effect_id=h.effect_id)
        h.core.recording_lifecycle.finalize(original.recording_id, var_dir=h.var_dir, now_us=100)
        other = add_recording(h, identity_index=1, purpose=RecordingPurpose.OBSERVATION, parent_recording_id=targets[1].recording_id, effect_id=h.effect_id)
        with h.core.uow_factory() as work:
            work.preparation_recovery.mark_candidate_recording(other.recording_id); work.commit()
        h.core.recording_lifecycle.finalize(other.recording_id, var_dir=h.var_dir, now_us=100)
        ref = MaterialReference(action_id=h.action.action_id, action_revision=1, kind="evidence", member_id=h.effect_id)
        service = h.core.preparation_materials
        details = service.details(h.project_id, ref)
        assert other.recording_id not in {item["recording_id"] for item in details["candidates"]}
        with pytest.raises(JiejianError):
            service.preview(h.project_id, MaterialChange(operation_id=uuid4().hex, material=ref,
                expected_fingerprint=details["expected_fingerprint"], candidate_recording_id=other.recording_id))
    finally:
        h.close()
