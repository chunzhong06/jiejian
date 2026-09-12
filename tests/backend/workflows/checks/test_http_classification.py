# 验证新快照的保守 HTTP 分类、完成来源引用和执行终态绑定，不修改历史 Flow。
import copy
import json
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from product.backend.core.errors import JiejianError
from product.backend.infra.execution.check_executor import CheckExecutor
from product.backend.infra.observers.check_runtime import CheckObservedSource
from product.backend.workflows.checks.runtime_bundle import derive_target_classifiers
from product.protocols.check_result import CheckObservation
from product.protocols.check_runtime import CheckActionConfig, CheckRuntimeBundle, canonical_check_runtime_bytes, parse_check_runtime
from product.protocols.web.response import HttpOutcomeClassifier
from tests.fixtures.check_execution import execution_pair
from tests.backend.infra.execution.test_check_executor import check_target, execution_configuration


def configuration(count=1):
    request, bundle = execution_pair()
    payload = bundle.model_dump(mode="json")
    config = payload["actions"][0]
    config["steps"][-1]["classifier"] = {"accepted": [{"kind": "STATUS_IN", "statuses": [200, 202]}]}
    proof = config["proofs"][0]
    for index in range(count):
        observer = f"completion-{index}"
        payload["observers"].append(dict(observer_id=observer, observer_type="ASYNC_TASK_STATUS",
            target=dict(target_id=observer, normalization_id=observer, normalization_version="1",
                locator=dict(locator_type="ASYNC_TASK_STATUS", base_url="http://127.0.0.1:8765",
                    relative_path_template="/tasks/{request_marker}", read_only_credential_ref="env:TASK_OBSERVER",
                    allow_private_network=False, allow_loopback_http=True,
                    poll_budget=dict(max_polls=2, poll_interval_us=0, per_request_timeout_us=1000000, max_response_bytes=262144))),
            phases=["EVENTUAL"], required=False, budget=dict(timeout_us=3000000, max_rows=1, max_bytes=262144)))
        proof["auxiliary_sources"].append(dict(observer_id=observer, descriptor_fingerprint="a" * 64,
            observation_identity_id=proof["observation_identity_id"], level="SUPPORTING",
            source_label="异步执行状态", source_location=f"observer/{observer}"))
    return request, payload


def derive(payload):
    return derive_target_classifiers(payload["actions"][0],
        {spec["observer_id"]: spec for spec in payload["observers"]}, payload["identities"])


@pytest.mark.parametrize("status,task,binding,accept,expected", [
    (202, "SUCCESS", True, 202, "ACCEPTED"),
    (202, "FAILED", True, 202, "UNKNOWN"),
    (202, "TIMED_OUT", True, 202, "UNKNOWN"),
    (202, "NOT_CREATED", True, 202, "UNKNOWN"),
    (202, "SUCCESS", False, 202, "UNKNOWN"),
    (202, "SUCCESS", True, 201, "UNKNOWN"),
    (403, "SUCCESS", True, 202, "DENIED"),
    (404, "SUCCESS", True, 202, "UNKNOWN"),
    (500, "SUCCESS", True, 202, "UNKNOWN"),
])
def test_real_target_response_is_classified_once_after_task_observation(
    check_target, tmp_path, status, task, binding, accept, expected,
):
    port, state = check_target
    def configure(payload):
        _, template = configuration(1 if binding else 0)
        action = payload["actions"][0]
        action["steps"][-1]["classifier"] = dict(accepted=[dict(kind="STATUS_IN", statuses=[accept])])
        if binding:
            spec = template["observers"][-1]
            spec["target"]["locator"]["base_url"] = f"http://127.0.0.1:{port}"
            payload["observers"].append(spec)
            source = template["actions"][0]["proofs"][0]["auxiliary_sources"][-1]
            source["observation_identity_id"] = action["proofs"][0]["observation_identity_id"]
            action["proofs"][0]["auxiliary_sources"].append(source)
            action["steps"][-1]["classifier"]["completion_binding"] = source["observer_id"]
        action["steps"] = derive(payload)
    request, bundle, runner_input, environment = execution_configuration(
        check_target, configure=configure, allow_status=status, task_state=task,
    )
    environment["TASK_OBSERVER"] = "test-task-observer"
    from tests.fixtures.runtime_environment import runtime_identity_environment
    environment = runtime_identity_environment(tmp_path / "runtime", extra=environment)
    executor = CheckExecutor(request, bundle, runner_input, environ=environment,
        attempt_dir=tmp_path, cancellation_requested=lambda: False)
    output = executor.execute()
    allow = next(case for action in request.actions for case in action.cases if case.permission.expectation == "ALLOW")
    result = next(item for item in output.result.case_results if item.case_id == allow.case_id)
    diagnostic = dict(result=result.model_dump(mode="json"), observations=[
        item.model_dump(mode="json") for document in output.evidence if document.case.case_id == allow.case_id
        for item in document.observations])
    assert result.outcome.execution_outcome == expected, json.dumps(diagnostic, ensure_ascii=False)
    assert result.outcome.http_status == status
    assert sum(case_id == allow.case_id for case_id, _ in state["target_calls"]) == 1


@pytest.mark.parametrize("accepted,denied,expected", [
    ([200, 202], [], [401, 403]), ([200, 401], [], [403]), ([401, 403], [], []),
    ([200], [404], [404]), ([200, 403], [403], [403]),
])
def test_defaults_preserve_explicit_predicates_and_do_not_mutate_flow(accepted, denied, expected):
    _, payload = configuration(0)
    classifier = payload["actions"][0]["steps"][-1]["classifier"]
    classifier["accepted"] = [dict(kind="STATUS_IN", statuses=accepted)]
    classifier["denied"] = [] if not denied else [dict(kind="STATUS_IN", statuses=denied)]
    before = json.dumps(payload, sort_keys=True)
    result = derive(payload)[-1]["classifier"]
    assert [status for predicate in result["denied"] for status in predicate["statuses"]] == expected
    assert json.dumps(payload, sort_keys=True) == before
    parsed = HttpOutcomeClassifier.model_validate_json(json.dumps(result))
    if 404 not in denied:
        assert parsed.classify(dict(status_code=404, headers={}, body=b"")).value == "UNKNOWN"
    if accepted == [200, 403] and denied == [403]:
        assert parsed.classify(dict(status_code=403, headers={}, body=b"")).value == "UNKNOWN"


def test_complex_predicate_and_setup_are_preserved():
    _, payload = configuration(0)
    target = payload["actions"][0]["steps"][0]
    target["classifier"]["accepted"] = [dict(kind="JSON_PATH_EQUALS", json_path="$.ok", expected=True)]
    setup = copy.deepcopy(target)
    setup.update(step_id="setup", purpose="SETUP")
    target["depends_on_step_ids"] = ["setup"]
    payload["actions"][0]["steps"].insert(0, setup)
    result = derive(payload)
    assert not result[0]["classifier"]["denied"] and not result[-1]["classifier"]["denied"]
    assert result[0]["classifier"] == CheckActionConfig.model_validate_json(json.dumps(payload["actions"][0])).steps[0].classifier.model_dump(mode="json")


@pytest.mark.parametrize("count,explicit,expected", [(0, None, None), (1, None, "completion-0"),
    (2, "completion-1", "completion-1")])
def test_unique_or_explicit_completion_is_frozen(count, explicit, expected):
    _, payload = configuration(count)
    payload["actions"][0]["steps"][-1]["classifier"]["completion_binding"] = explicit
    payload["actions"][0]["steps"] = derive(payload)
    assert payload["actions"][0]["steps"][-1]["classifier"]["completion_binding"] == expected
    bundle = CheckRuntimeBundle.model_validate_json(json.dumps(payload))
    assert parse_check_runtime(canonical_check_runtime_bytes(bundle)) == bundle


@pytest.mark.parametrize("fault,reason", [("multiple", "ASYNC_COMPLETION_AMBIGUOUS"),
    ("identity", "ASYNC_COMPLETION_BINDING_INVALID"), ("phase", "ASYNC_COMPLETION_BINDING_INVALID"),
    ("type", "ASYNC_COMPLETION_BINDING_INVALID"), ("other", "ASYNC_COMPLETION_BINDING_INVALID"),
    ("conflict", "ASYNC_COMPLETION_CONFLICT")])
def test_invalid_completion_is_a_structured_gap(fault, reason):
    _, payload = configuration(2 if fault == "multiple" else 1)
    config = payload["actions"][0]
    if fault != "multiple":
        config["steps"][-1]["classifier"]["completion_binding"] = "completion-0"
    if fault == "identity":
        for identity in payload["identities"]:
            identity["verification"] = None
    elif fault == "phase":
        payload["observers"][-1]["phases"] = ["AFTER"]
    elif fault == "type":
        config["steps"][-1]["classifier"]["completion_binding"] = payload["observers"][0]["observer_id"]
    elif fault == "other":
        config["steps"][-1]["classifier"]["completion_binding"] = "other-action-task"
    elif fault == "conflict":
        duplicate = copy.deepcopy(config["proofs"][0])
        duplicate["binding_fingerprint"] = "c" * 64
        duplicate["auxiliary_sources"][0]["descriptor_fingerprint"] = "d" * 64
        config["proofs"].append(duplicate)
    with pytest.raises(JiejianError) as error:
        derive(payload)
    assert error.value.to_dict()["details"]["reason"] == reason
    if fault != "multiple":
        with pytest.raises(ValidationError):
            CheckRuntimeBundle.model_validate_json(json.dumps(payload))


@pytest.mark.parametrize("fault", [None, "identity", "binding", "case", "resource", "proof", "effect",
    "observer", "phase", "marker", "missing", "incomplete", "conflict"])
def test_completion_requires_exact_case_and_all_matching_eventual_facts(fault):
    request, payload = configuration()
    payload["actions"][0]["steps"] = derive(payload)
    action = CheckActionConfig.model_validate_json(json.dumps(payload["actions"][0]))
    case = request.actions[0].cases[0]
    requirement = case.proof_requirements[0]
    observation = CheckObservation(effect_id=requirement.effect_id, proof_fingerprint=requirement.proof_fingerprint,
        observer_id="completion-0", level="SUPPORTING", phase="EVENTUAL", state="UNKNOWN", closure="UNKNOWN",
        complete=False, reliable=False, correlated=False, authoritative=False, window_start_us=1, window_end_us=2,
        correlation_refs=(case.case_id, "current-marker"))
    item = CheckObservedSource(observation, None, True, case.case_id, case.resource_id, requirement.binding_fingerprint)
    changes = {}
    if fault in {"case", "resource", "binding"}:
        changes[{"case": "completion_case_id", "resource": "completion_resource_id", "binding": "completion_binding_fingerprint"}[fault]] = "wrong"
    elif fault in {"proof", "effect", "observer", "phase", "marker"}:
        key, value = {"proof": ("proof_fingerprint", "f" * 64), "effect": ("effect_id", "bef_" + "f" * 32),
            "observer": ("observer_id", "other-task"), "phase": ("phase", "AFTER"), "marker": ("correlation_refs", (case.case_id,))}[fault]
        changes["observation"] = observation.model_copy(update={key: value})
    elif fault == "incomplete":
        changes["execution_completed"] = False
    from dataclasses import replace
    item = replace(item, **changes)
    items = () if fault == "missing" else (item, replace(item, execution_completed=False)) if fault == "conflict" else (item,)
    executor = object.__new__(CheckExecutor)
    executor.web = SimpleNamespace(request_marker=lambda _: "current-marker")
    assert executor._trusted_terminal_completion(action, case, "UNKNOWN" if fault == "identity" else "MATCH", items) is (fault is None)


def test_consistent_shared_task_is_deduplicated_and_other_action_cannot_supply_binding(tmp_path):
    _, payload = configuration()
    action = payload["actions"][0]
    duplicate = copy.deepcopy(action["proofs"][0])
    duplicate["binding_fingerprint"] = "c" * 64
    action["proofs"].append(duplicate)
    assert derive(payload)[-1]["classifier"]["completion_binding"] == "completion-0"
    other = copy.deepcopy(action)
    other["action_id"] = "bac_" + "f" * 32
    action["proofs"][0]["auxiliary_sources"] = []
    action["proofs"] = action["proofs"][:1]
    action["steps"][-1]["classifier"]["completion_binding"] = "completion-0"
    payload["actions"].append(other)
    with pytest.raises(ValidationError):
        CheckRuntimeBundle.model_validate_json(json.dumps(payload))
    with pytest.raises(JiejianError):
        derive(payload)


@pytest.mark.parametrize("fault", [None, "task_id", "partial", "identity", "unavailable", "correlation", "observer", "phase", "target"])
def test_observer_private_completion_requires_complete_bound_envelope(tmp_path, monkeypatch, fault):
    from product.backend.infra.observers.check_runtime import CheckObserverRuntime
    from product.protocols.observer import Correlation, ObservationCompleteness, ObservationPhase, ObserverOutcomeStatus
    from tests.backend.infra.observers.test_async_task_observer import _run_fake, _response

    request, payload = configuration()
    bundle = CheckRuntimeBundle.model_validate_json(json.dumps(payload))
    case = request.actions[0].cases[0]
    requirement = case.proof_requirements[0]
    parent = bundle.actions[0].proofs[0]
    proof = parent.model_copy(update={"observer_id": "completion-0", "auxiliary_sources": ()})
    spec = bundle.observers[-1]
    marker = "test-marker"
    monkeypatch.setenv("TASK_OBSERVER", "opaque-task-secret")
    envelope, outcome = _run_fake(monkeypatch, [_response("SUCCESS")], spec=spec)
    envelope = envelope.model_copy(update={"correlation": Correlation(case_id=case.case_id, resource_id=case.resource_id, request_marker=marker)})
    if fault == "task_id":
        envelope = envelope.model_copy(update={"state": envelope.state.model_copy(update={"canonical_data": {**envelope.state.canonical_data, "task_id": None}})})
    elif fault == "partial":
        envelope = envelope.model_copy(update={"completeness": ObservationCompleteness.PARTIAL})
    elif fault == "unavailable":
        outcome = outcome.model_copy(update={"status": ObserverOutcomeStatus.INCONCLUSIVE})
    elif fault in {"correlation", "observer", "phase", "target"}:
        field, value = {"correlation": ("correlation", Correlation(case_id="wrong-case", resource_id=case.resource_id, request_marker=marker)),
            "observer": ("observer_id", "wrong-observer"), "phase": ("phase", ObservationPhase.AFTER), "target": ("target_id", "wrong-target")}[fault]
        envelope = envelope.model_copy(update={field: value})
    web = SimpleNamespace(verify_identity=lambda *args, **kwargs: "UNKNOWN" if fault == "identity" else "MATCH", request_marker=lambda _: marker)
    runtime = CheckObserverRuntime(bundle, web, attempt_dir=tmp_path, environ={}, cancellation_requested=lambda: False)
    runtime.coordinator = SimpleNamespace(observe_one=lambda *args: (envelope, outcome, ()))
    actual = runtime.observe(case=case, action_id=bundle.actions[0].action_id, requirement=requirement,
        proof=proof, phase="EVENTUAL", baseline_trusted=True)
    assert actual.execution_completed is (fault is None), actual.observation.model_dump_json()
    assert actual.observation.state != "CONFIRMED"
