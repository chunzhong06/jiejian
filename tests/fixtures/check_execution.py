# 从 A1 正式纯编译器生成相互绑定的请求与配置，供当前执行链测试复用。
import json

from product.backend.core.check_plan import compile_project_check_plan
from product.protocols.check_runtime import CheckRuntimeBundle, check_runtime_fingerprint
from product.protocols.execution_v3 import PersistedExecutionRequestV3
from tests.fixtures.check_plan import prepared_action
from tests.fixtures.check_runtime import runtime_bundle


def execution_pair(*, port=8765, configure=None, state_changing=False, prepared=None):
    prepared = prepared or prepared_action(state_changing=state_changing)
    payload = runtime_bundle(port=port).model_dump(mode="json")
    payload["project_id"] = prepared.action.project_id
    prototype = payload["identities"][0]
    payload["identities"] = []
    for index, assignment in enumerate(prepared.identities, 1):
        identity = json.loads(json.dumps(prototype))
        identity.update(identity_id=assignment.identity_id, actor_id=assignment.actor_id,
            actor_revision=assignment.actor_revision, identity_fingerprint=assignment.identity_fingerprint)
        identity["verification"].update(expected_actor_id=assignment.actor_id,
            expected_actor_revision=assignment.actor_revision)
        if state_changing:
            identity["binding"]["secret_ref"] = f"env:CHECK_TEST_{index}"
            identity["verification"]["expected_application_subject_id"] = f"subject-{index}"
        payload["identities"].append(identity)
    configured = payload["actions"][0]
    configured.update(action_id=prepared.action.action_id, action_revision=prepared.action.revision,
        action_semantic_fingerprint=prepared.action.semantic_fingerprint,
        flow_id=prepared.execution.flow_id, flow_sha256=prepared.execution.flow_sha256,
        execution_binding_fingerprint=prepared.execution.binding_fingerprint)
    if state_changing:
        configured["state_changing"] = True
        configured["steps"][0]["request"].update(method="POST", path="/target/{resource}")
        configured["recovery"] = dict(binding_fingerprint=prepared.recovery.binding_fingerprint,
            source_subject_identity_id=prepared.recovery.subject_test_identity_id,
            request=dict(method="POST", path="/restore/{resource}", input_slots=[
                dict(slot_id="resource", source="CASE_RESOURCE_ID", consumer="PATH")]))
    binding = prepared.evidence[0]
    reference = binding.observer_reference
    proof = configured["proofs"][0]
    proof.update(effect_id=binding.effect_id, binding_fingerprint=binding.binding_fingerprint,
        business_label=prepared.action.effect_catalog[0].business_label,
        resource_concept=prepared.action.effect_catalog[0].resource_concept,
        rule="REGISTERED_EFFECT", observation_identity_id=prepared.identities[0].identity_id,
        effect_kind=prepared.action.effect_catalog[0].effect_kind.value,
        request=None, observer_id=reference.observer_id, descriptor_fingerprint=reference.descriptor_fingerprint)
    if len(prepared.evidence) > 1:
        configured["proofs"] = []
        for evidence in prepared.evidence:
            effect = next(item for item in prepared.action.effect_catalog if item.effect_id == evidence.effect_id)
            configured["proofs"].append(dict(proof, effect_id=effect.effect_id,
                binding_fingerprint=evidence.binding_fingerprint, business_label=effect.business_label,
                resource_concept=effect.resource_concept, effect_kind=effect.effect_kind.value))
    payload["observers"] = [dict(observer_id=reference.observer_id, observer_type="OWNER_API",
        target=dict(target_id="object", locator=dict(locator_type="OWNER_API", relative_path_template="/objects/{resource_id}"),
            normalization_id="object", normalization_version="1"), phases=["BEFORE", "AFTER"], required=True,
        budget=dict(timeout_us=1_000_000, max_rows=1, max_bytes=262_144))]
    if configure is not None:
        configure(payload)
    bundle = CheckRuntimeBundle.model_validate_json(json.dumps(payload))
    config_hash = check_runtime_fingerprint(bundle)
    plan = compile_project_check_plan(prepared.action.project_id, source_fingerprint=bundle.source_fingerprint,
        policy_epoch=1, engine_version="test-1", config_fingerprint=config_hash, actions=(prepared,))
    request_payload = plan.model_dump(mode="json", exclude={"gaps"})
    for action in request_payload["actions"]:
        action.pop("gaps")
    request_payload.update(config_fingerprint=config_hash, budget_fingerprint=bundle.budget.fingerprint())
    return PersistedExecutionRequestV3.model_validate_json(json.dumps(request_payload)), bundle
