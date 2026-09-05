# 验证正式动作准备绑定的纯领域约束、来源溯源和非秘密请求模板。
# 测试只构造严格模型，不连接数据库、不调用绑定服务，也不改变产品语义。

from __future__ import annotations

import math

import pytest
from pydantic import ValidationError

from product.backend.core.action_preparation import (
    ActionEvidenceBinding,
    ActionEvidenceKind,
    ActionExecutionBinding,
    ActionRecoveryBinding,
    ActionResourceBinding,
    RecordedRequestTemplate,
    RegisteredObserverReference,
    ResourceInjection,
    ResourceInjectionKind,
    seal_binding,
)


PROJECT_ID = "sample-project"
ACTION_ID = "bac_" + "1" * 32
RECORDING_ID = "rec_" + "2" * 32
TEST_IDENTITY_ID = "tid_" + "3" * 32
OTHER_TEST_IDENTITY_ID = "tid_" + "4" * 32
FLOW_ID = "sample-flow"
SHA = "a" * 64
OTHER_SHA = "b" * 64


def _base_facts(test_identity_id: str = TEST_IDENTITY_ID) -> dict[str, object]:
    return {
        "project_id": PROJECT_ID,
        "business_action_id": ACTION_ID,
        "action_revision": 1,
        "action_semantic_fingerprint": SHA,
        "implementation_fingerprint": OTHER_SHA,
        "source_fingerprint": None,
        "endpoint_fingerprint": "c" * 64,
        "test_identity_id": test_identity_id,
        "identity_fingerprint": "d" * 64,
        "confirmed_at_us": 100,
    }


def _recorded_facts(test_identity_id: str = TEST_IDENTITY_ID) -> dict[str, object]:
    return _base_facts(test_identity_id) | {
        "source_recording_id": RECORDING_ID,
        "source_draft_revision": 2,
        "source_draft_sha256": "e" * 64,
    }


def _injection(kind: ResourceInjectionKind = ResourceInjectionKind.PATH) -> ResourceInjection:
    locations = {
        ResourceInjectionKind.PATH: "path[0]",
        ResourceInjectionKind.QUERY: "query.resource_id",
        ResourceInjectionKind.JSON_BODY: "$.resource.id",
    }
    return ResourceInjection(
        consumer=kind,
        location=locations[kind],
        template_fingerprint="f" * 64,
    )


def _request(method: str = "GET", *, body: dict[str, object] | None = None) -> RecordedRequestTemplate:
    return RecordedRequestTemplate(
        method=method,
        relative_path="/items/{case_resource_id}",
        json_body={} if body is None else body,
    )


def _execution(test_identity_id: str = TEST_IDENTITY_ID, flow_sha256: str = SHA) -> ActionExecutionBinding:
    return seal_binding(
        ActionExecutionBinding,
        **(_recorded_facts(test_identity_id) | {
            "flow_id": FLOW_ID,
            "flow_sha256": flow_sha256,
            "resource_injection": _injection(),
        }),
    )


def _resource(
    test_identity_id: str = TEST_IDENTITY_ID,
    flow_sha256: str = SHA,
    actual_resource_id: str = "resource-1",
) -> ActionResourceBinding:
    return seal_binding(
        ActionResourceBinding,
        **(_recorded_facts(test_identity_id) | {
            "owner_test_identity_id": test_identity_id,
            "actual_resource_id": actual_resource_id,
            "flow_id": FLOW_ID,
            "flow_sha256": flow_sha256,
            "resource_injection": _injection(),
        }),
    )


def _recorded_evidence() -> ActionEvidenceBinding:
    return seal_binding(
        ActionEvidenceBinding,
        **(_base_facts() | {
            "effect_id": "bef_" + "5" * 32,
            "kind": ActionEvidenceKind.RECORDED_OBSERVATION,
            "source_recording_id": RECORDING_ID,
            "source_draft_revision": 2,
            "source_draft_sha256": "e" * 64,
            "step_id": "step-observation",
            "request_template": _request(),
            "observer_reference": None,
        }),
    )


def _registered_evidence() -> ActionEvidenceBinding:
    return seal_binding(
        ActionEvidenceBinding,
        **(_base_facts() | {
            "effect_id": "bef_" + "6" * 32,
            "kind": ActionEvidenceKind.REGISTERED_OBSERVER,
            "observer_reference": RegisteredObserverReference(
                descriptor_id="exp_" + "7" * 32,
                descriptor_fingerprint="8" * 64,
                observer_id=PROJECT_ID,
            ),
        }),
    )


def _recovery() -> ActionRecoveryBinding:
    return seal_binding(
        ActionRecoveryBinding,
        **(_recorded_facts() | {
            "step_id": "step-recovery",
            "request_template": _request("POST", body={"resource": "{case_resource_id}"}),
        }),
    )


def test_four_binding_models_are_strict_and_have_no_live_state_fields() -> None:
    bindings = (_execution(), _resource(), _recorded_evidence(), _recovery())

    assert len(bindings) == 4
    for binding in bindings:
        fields = binding.model_dump(mode="json")
        assert "binding_fingerprint" in fields
        assert "confirmed_at_us" in fields
        assert not {"status", "schema_version", "permission", "live_status"} & fields.keys()
        with pytest.raises(ValidationError, match="extra_forbidden"):
            type(binding).model_validate(binding.model_dump() | {"unexpected": "field"})


def test_binding_fingerprint_ignores_confirmation_time_but_seals_other_facts() -> None:
    binding = _execution()
    changed_time = binding.model_dump() | {"confirmed_at_us": 101}

    rebound = ActionExecutionBinding.model_validate(changed_time)

    assert rebound.binding_fingerprint == binding.binding_fingerprint
    with pytest.raises(ValidationError, match="fingerprint"):
        ActionExecutionBinding.model_validate(
            binding.model_dump() | {"flow_sha256": "9" * 64}
        )
    assert _execution().binding_fingerprint != _resource().binding_fingerprint


def test_resource_owner_and_reusable_injection_are_explicit() -> None:
    first = _resource()
    second = _resource(OTHER_TEST_IDENTITY_ID, flow_sha256=OTHER_SHA)

    assert first.resource_injection == second.resource_injection
    assert first.flow_sha256 != second.flow_sha256
    with pytest.raises(ValidationError, match="owner"):
        seal_binding(
            ActionResourceBinding,
            **(_recorded_facts() | {
                "owner_test_identity_id": OTHER_TEST_IDENTITY_ID,
                "actual_resource_id": "resource-1",
                "flow_id": FLOW_ID,
                "flow_sha256": SHA,
                "resource_injection": _injection(),
            }),
        )


@pytest.mark.parametrize("value", ["https://example.test", "a/b", "<script>", "", ".", "..", "x" * 257])
def test_actual_resource_id_rejects_paths_scripts_empty_and_oversized_values(value: str) -> None:
    with pytest.raises(ValidationError):
        _resource(actual_resource_id=value)


@pytest.mark.parametrize("value", ["订单-甲_1.2", "resource.id"])
def test_actual_resource_id_accepts_bounded_plain_identifiers(value: str) -> None:
    assert _resource(actual_resource_id=value).actual_resource_id == value


@pytest.mark.parametrize(
    ("kind", "location"),
    [
        (ResourceInjectionKind.PATH, "path[12]"),
        (ResourceInjectionKind.QUERY, "query.resource-id"),
        (ResourceInjectionKind.JSON_BODY, "$.items[0].resource_id"),
    ],
)
def test_resource_injection_locations_match_their_consumer_syntax(
    kind: ResourceInjectionKind, location: str
) -> None:
    assert ResourceInjection(consumer=kind, location=location, template_fingerprint=SHA).location == location


@pytest.mark.parametrize(
    ("kind", "location"),
    [
        (ResourceInjectionKind.PATH, "query.id"),
        (ResourceInjectionKind.QUERY, "path[0]"),
        (ResourceInjectionKind.JSON_BODY, "$.bad path"),
        (ResourceInjectionKind.PATH, "path[]"),
    ],
)
def test_resource_injection_rejects_illegal_or_mixed_locations(
    kind: ResourceInjectionKind, location: str
) -> None:
    with pytest.raises(ValidationError, match="location"):
        ResourceInjection(consumer=kind, location=location, template_fingerprint=SHA)


def test_recorded_observation_requires_exact_read_only_recording_source() -> None:
    evidence = _recorded_evidence()

    assert evidence.kind is ActionEvidenceKind.RECORDED_OBSERVATION
    assert evidence.request_template is not None
    assert evidence.request_template.method == "GET"
    assert evidence.request_template.json_body == {}
    assert evidence.observer_reference is None
    with pytest.raises(ValidationError):
        seal_binding(
            ActionEvidenceBinding,
            **(_base_facts() | {
                "effect_id": "bef_" + "5" * 32,
                "kind": ActionEvidenceKind.RECORDED_OBSERVATION,
                "source_recording_id": RECORDING_ID,
                "source_draft_revision": 2,
                "source_draft_sha256": "e" * 64,
                "step_id": "step-observation",
                "request_template": _request("POST", body={"x": "{case_resource_id}"}),
            }),
        )


def test_registered_observer_is_a_narrow_descriptor_reference() -> None:
    evidence = _registered_evidence()

    assert evidence.observer_reference is not None
    assert evidence.observer_reference.descriptor_id.startswith("exp_")
    with pytest.raises(ValidationError):
        RegisteredObserverReference.model_validate(
            evidence.observer_reference.model_dump(mode="json") | {"url": "https://example.test"}
        )
    with pytest.raises(ValidationError):
        seal_binding(
            ActionEvidenceBinding,
            **(_base_facts() | {
                "effect_id": "bef_" + "6" * 32,
                "kind": ActionEvidenceKind.REGISTERED_OBSERVER,
                "observer_reference": evidence.observer_reference,
                "request_template": _request(),
            }),
        )


@pytest.mark.parametrize("method", ["GET"])
def test_recovery_binding_rejects_read_only_templates(method: str) -> None:
    with pytest.raises(ValidationError, match="state-changing"):
        seal_binding(
            ActionRecoveryBinding,
            **(_recorded_facts() | {
                "step_id": "step-recovery",
                "request_template": _request(method),
            }),
        )


def test_recovery_binding_accepts_state_changing_template_with_resource_slot() -> None:
    recovery = _recovery()

    assert recovery.request_template.method == "POST"
    assert recovery.request_template.json_body["resource"] == "{case_resource_id}"


@pytest.mark.parametrize(
    "path",
    [
        "https://example.test/items/{case_resource_id}",
        "//example.test/items/{case_resource_id}",
        "/items\\{case_resource_id}",
        "/items/../{case_resource_id}",
        "/items/%2e%2e/{case_resource_id}",
        "/items/{case_resource_id}#fragment",
        "/items/{case_resource_id}\n",
        "/items/{case_resource_id}?token=secret",
    ],
)
def test_recorded_request_template_rejects_external_or_unsafe_paths(path: str) -> None:
    with pytest.raises(ValidationError):
        RecordedRequestTemplate(method="GET", relative_path=path)


@pytest.mark.parametrize(
    "body",
    [
        {"token": "secret", "resource": "{case_resource_id}"},
        {"nested": {"password": "secret", "resource": "{case_resource_id}"}},
        {"resource": "<script>alert(1)</script>"},
        {"resource": "{case_resource_id}", "number": math.nan},
        {"resource": "{case_resource_id}", "large": "x" * 8193},
        {"resource": "{case_resource_id}", "unsupported": object()},
    ],
)
def test_recorded_request_template_rejects_secret_unsafe_or_nonfinite_bodies(
    body: dict[str, object],
) -> None:
    with pytest.raises((ValidationError, ValueError, TypeError)):
        RecordedRequestTemplate(method="POST", relative_path="/items", json_body=body)


def test_recorded_request_template_accepts_finite_nested_json_and_requires_resource_slot() -> None:
    template = RecordedRequestTemplate(
        method="PATCH",
        relative_path="/items",
        json_body={"resource": {"id": "{case_resource_id}"}, "count": 2.5, "enabled": True},
    )

    assert template.json_body["resource"] == {"id": "{case_resource_id}"}
    with pytest.raises(ValidationError, match="resource slot"):
        RecordedRequestTemplate(method="GET", relative_path="/items", json_body={})


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("business_action_id", "action-1"),
        ("test_identity_id", "identity-1"),
        ("source_recording_id", "recording-1"),
        ("source_draft_revision", 0),
        ("source_draft_sha256", "short"),
        ("action_revision", 0),
    ],
)
def test_action_execution_provenance_fields_are_strictly_validated(field: str, value: object) -> None:
    with pytest.raises(ValidationError):
        seal_binding(ActionExecutionBinding, **(_recorded_facts() | {
            "flow_id": FLOW_ID,
            "flow_sha256": SHA,
            "resource_injection": _injection(),
            field: value,
        }))
