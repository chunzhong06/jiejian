# 拒绝合法单体配置之间的跨动作、身份、证明和预算拼接。
import pytest

from product.backend.core.errors import JiejianError
from product.backend.infra.artifacts.check_validation import validate_check_inputs
from tests.fixtures.check_execution import execution_pair


def test_current_plan_and_frozen_runtime_are_consistent():
    request, bundle = execution_pair()
    validate_check_inputs(request, bundle)


@pytest.mark.parametrize("field,value", [("project_id", "other"), ("source_fingerprint", "e" * 64),
    ("config_fingerprint", "e" * 64), ("budget_fingerprint", "e" * 64)])
def test_asset_association_rejects_changed_root(field, value):
    request, bundle = execution_pair()
    with pytest.raises(JiejianError) as caught:
        validate_check_inputs(request.model_copy(update={field: value}), bundle)
    assert caught.value.code == "RUNNER_PROTOCOL_INVALID"


@pytest.mark.parametrize("configure", [
    lambda p: p["actions"][0].update(action_revision=2),
    lambda p: p["actions"][0].update(action_semantic_fingerprint="d" * 64),
    lambda p: p["actions"][0].update(flow_sha256="d" * 64),
    lambda p: p["actions"][0].update(execution_binding_fingerprint="d" * 64),
    lambda p: p["actions"][0]["proofs"][0].update(binding_fingerprint="d" * 64),
    lambda p: p["actions"][0]["proofs"][0].update(effect_id="bef_" + "f" * 32),
    lambda p: p["actions"][0]["proofs"][0].update(descriptor_fingerprint="d" * 64),
    lambda p: p["identities"][0].update(identity_fingerprint="d" * 64),
    lambda p: p["budget"].update(max_cases=1),
])
def test_hash_valid_bundle_cannot_replace_frozen_case_facts(configure):
    request, bundle = execution_pair(configure=configure)
    with pytest.raises(JiejianError) as caught:
        validate_check_inputs(request, bundle)
    assert caught.value.code == "RUNNER_PROTOCOL_INVALID"


def test_publication_budget_rejects_plan_that_cannot_fit_result_before_target_io():
    from product.backend.infra.artifacts.check_validation import check_publication_budget_reason
    request, bundle = execution_pair(configure=lambda payload: payload["budget"].update(max_cases=8192))
    action = request.actions[0]
    expanded = action.model_copy(update={"cases": action.cases * 128})
    assert check_publication_budget_reason((expanded,), bundle) == "CHECK_CASE_BUDGET_EXCEEDED"


@pytest.mark.parametrize("path,slots", [
    ("/restore/fixed", []),
    ("/restore/prefix-{resource}", [dict(slot_id="resource", source="CASE_RESOURCE_ID", consumer="PATH")]),
    ("/restore/fixed", [dict(slot_id="resource", source="CASE_RESOURCE_ID", consumer="PATH")]),
])
def test_recovery_must_address_the_exact_case_resource(path, slots):
    def configure(payload):
        payload["actions"][0]["recovery"]["request"].update(path=path, input_slots=slots)
    with pytest.raises(ValueError, match="recovery"):
        execution_pair(state_changing=True, configure=configure)
