# 验证材料详情只复制当前绑定元数据，漂移和未知能力不能被解释为有效证明。
from contextlib import nullcontext
from types import SimpleNamespace as N
from unittest.mock import Mock

import pytest
from pydantic import ValidationError

from product.backend.core.action_preparation import ActionEvidenceKind
from product.backend.workflows.preparation.bindings import PreparationBindingService
from product.backend.workflows.preparation.evidence_models import EffectMaterialSummary
from product.backend.workflows.preparation.models import EffectEvidencePreparationView, PreparationStatus
from tests.fixtures.assurance import action


def _service():
    from product.backend.workflows.business_boundaries.models import BusinessBoundaryView
    from product.backend.workflows.preparation.service import PreparationService
    from tests.fixtures.assurance import PROJECT, actor, permission
    state = N(boundary=BusinessBoundaryView(project_id=PROJECT, policy_epoch=1,
        actors=(actor(),), actions=(action(),), actor_bindings=(), action_bindings=(),
        permission_intents=(permission(),), permission_statuses=()))
    return PreparationService(N(view=lambda _: state.boundary), N(list=lambda _: ())), state


def _describe(tmp_path, *, kind=ActionEvidenceKind.REGISTERED_OBSERVER, available=True,
              capability=None, fingerprint="a" * 64, expected="a" * 64, missing=False, reader_present=True):
    current = action()
    effect = current.effect_catalog[0]
    reference = N(descriptor_id="descriptor", descriptor_fingerprint="b" * 64, observer_id="observer")
    binding = None if missing else N(project_id=current.project_id, business_action_id=current.action_id,
        action_revision=current.revision, effect_id=effect.effect_id, binding_fingerprint=fingerprint,
        kind=kind, observer_reference=reference)
    repository = N(evidence=Mock(return_value=binding), replace=Mock(side_effect=AssertionError("writer called")))
    work = N(action_preparation=repository, commit=Mock(side_effect=AssertionError("commit called")))
    reader = N(contains=Mock(return_value=available))
    proofs = N(capability=Mock(return_value=capability))
    service = PreparationBindingService(lambda: nullcontext(work), tmp_path,
        registered_observers=reader if reader_present else None, effect_proofs=proofs)
    view = EffectEvidencePreparationView(effect_id=effect.effect_id,
        status=PreparationStatus.NEEDS_USER if missing else PreparationStatus.SATISFIED,
        binding_fingerprint=expected, reason_codes=("EFFECT_EVIDENCE_REQUIRED",) if missing else ())
    result = service.describe_evidence(current, (view,))[0]
    repository.replace.assert_not_called()
    work.commit.assert_not_called()
    return result, reader, proofs


def test_missing_and_recorded_materials_do_not_consult_registry(tmp_path):
    missing, reader, proofs = _describe(tmp_path, missing=True, expected=None)
    assert missing.source_kind is None and missing.source_label == "尚无证明材料"
    assert missing.material_status is PreparationStatus.NEEDS_USER
    reader.contains.assert_not_called()
    proofs.capability.assert_not_called()
    recorded, reader, proofs = _describe(tmp_path, kind=ActionEvidenceKind.RECORDED_OBSERVATION)
    assert recorded.source_label == "已保存的观察材料"
    assert recorded.registered_source_available is None and recorded.closure_supported is None
    reader.contains.assert_not_called()
    proofs.capability.assert_not_called()


def test_registered_availability_and_unknown_capability_are_separate(tmp_path):
    result, _, _ = _describe(tmp_path)
    assert result.registered_source_available is True and result.closure_supported is None
    assert result.reason_codes == ("PROOF_CAPABILITY_UNAVAILABLE",)
    unavailable, _, _ = _describe(tmp_path, available=False)
    assert unavailable.registered_source_available is False
    assert "REGISTERED_OBSERVER_UNAVAILABLE" in unavailable.reason_codes
    unknown, reader, proofs = _describe(tmp_path, reader_present=False)
    assert unknown.registered_source_available is None
    assert "REGISTERED_OBSERVER_UNAVAILABLE" not in unknown.reason_codes
    assert unknown.closure_supported is None
    reader.contains.assert_not_called()
    proofs.capability.assert_not_called()


def test_only_exact_existing_capability_is_copied(tmp_path):
    capability = N(descriptor_id="descriptor", descriptor_fingerprint="b"*64, observer_id="observer",
        effect_id=action().effect_catalog[0].effect_id, closure_supported=True, resource_correlation_supported=False)
    result, _, _ = _describe(tmp_path, capability=capability)
    assert result.closure_supported is True and result.resource_correlation_supported is False
    capability.effect_id = "different-effect"
    result, _, _ = _describe(tmp_path, capability=capability)
    assert result.closure_supported is None and "PROOF_CAPABILITY_UNAVAILABLE" in result.reason_codes


def test_changed_snapshot_discards_new_source_and_does_not_mutate_status(tmp_path):
    result, reader, proofs = _describe(tmp_path, fingerprint="c"*64)
    assert result.material_status is PreparationStatus.STALE
    assert result.reason_codes == ("EVIDENCE_SNAPSHOT_CHANGED",)
    assert result.binding_fingerprint is None and result.source_kind is None
    reader.contains.assert_not_called()
    proofs.capability.assert_not_called()


def test_detail_dto_is_strict_and_contains_no_operational_fields(tmp_path):
    result, _, _ = _describe(tmp_path)
    raw = result.model_dump()
    assert set(raw) == {"effect_id", "business_label", "resource_concept", "material_status",
        "binding_fingerprint", "source_kind", "source_label", "registered_source_available",
        "closure_supported", "resource_correlation_supported", "reason_codes"}
    for name in ("request_template", "observer_reference", "schema_version", "can_execute", "proof_level"):
        with pytest.raises(ValidationError):
            EffectMaterialSummary.model_validate(raw | {name: "unexpected"})


def test_service_multiple_effects_and_business_revision_drift_do_not_change_get():
    from tests.fixtures.assurance import PROJECT

    service, state = _service()
    prepared = service.get(PROJECT)
    current = state.boundary.actions[0]
    first = current.effect_catalog[0]
    second = first.model_copy(update={"effect_id": "bef_" + "f"*32, "business_label": "第二项结果"})
    state.boundary = state.boundary.model_copy(update={"actions": (
        current.model_copy(update={"effect_catalog": (first, second)}),)})
    original = prepared.actions[0]
    original = original.model_copy(update={"effect_evidence": (*original.effect_evidence,
        original.effect_evidence[0].model_copy(update={"effect_id": second.effect_id}))})
    service.get = Mock(return_value=prepared.model_copy(update={"actions": (original,)}))
    detail = service.evidence_details(PROJECT, current.action_id)
    assert [item.business_label for item in detail.effects] == [first.business_label, "第二项结果"]
    assert all(item.material_status is PreparationStatus.NEEDS_USER for item in detail.effects)
    before = service.get(PROJECT)
    state.boundary = state.boundary.model_copy(update={"actions": (
        state.boundary.actions[0].model_copy(update={"revision": current.revision + 1}),)})
    detail = service.evidence_details(PROJECT, current.action_id)
    assert all(item.material_status is PreparationStatus.STALE and
               item.reason_codes == ("EVIDENCE_SNAPSHOT_CHANGED",) for item in detail.effects)
    assert service.get(PROJECT) == before


def test_cross_project_action_is_not_exposed():
    from product.backend.core.errors import ErrorCode, JiejianError
    from tests.fixtures.assurance import PROJECT
    service, state = _service()
    current = state.boundary.actions[0]
    state.boundary = state.boundary.model_copy(update={"actions": (
        current.model_copy(update={"project_id": "other-project"}),)})
    with pytest.raises(JiejianError) as error:
        service.evidence_details(PROJECT, current.action_id)
    assert error.value.code == ErrorCode.APPLICATION_CANDIDATE_NOT_FOUND
