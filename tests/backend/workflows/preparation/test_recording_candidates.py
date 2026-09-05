# 验证录制事实到验证候选的有限提取、资源槽替换和确定性选择。
# 测试只消费协议叶模型与已保存事件，不启动目标、数据库、Worker 或浏览器。

from __future__ import annotations

from types import SimpleNamespace

import pytest

from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.core.recording import RecordingPurpose
from product.backend.workflows.preparation.recording_candidates import (
    choose_supplement_candidate,
    flow_resource_injection,
    request_event,
    resource_value,
    supplement_candidates,
)
from product.protocols.flow_draft import FlowDraftResourceCandidate
from product.protocols.recording import RecordingEvent, RecordingEventKind
from product.protocols.web.request import (
    EmptyBody,
    HttpParameter,
    HttpRequestTemplate,
    ValueSlot,
    ValueSlotConsumer,
    ValueSlotSource,
)


PROJECT_ID = "sample-project"
ACTION_ID = "bac_" + "1" * 32
TEST_IDENTITY_ID = "tid_" + "2" * 32
RESOURCE_VALUE = "resource-7"


def _candidate(
    consumer: ValueSlotConsumer,
    location: str,
    suffix: str = "1",
) -> FlowDraftResourceCandidate:
    return FlowDraftResourceCandidate(
        candidate_id="resource-" + suffix * 16,
        consumer=consumer,
        location=location,
        label="录制资源",
    )


def _event(
    kind: RecordingEventKind,
    *,
    request_id: str | None = "request_000001",
    url: str | None = None,
    method: str | None = None,
    body: str | None = None,
    status_code: int | None = None,
    truncated: bool = False,
    sequence: int = 1,
) -> RecordingEvent:
    return RecordingEvent(
        sequence=sequence,
        occurred_at_us=sequence,
        kind=kind,
        identity_id=PROJECT_ID,
        page_id="page_000001",
        request_id=request_id,
        url=url,
        method=method,
        body=body,
        status_code=status_code,
        truncated=truncated,
    )


def _recording(
    purpose: RecordingPurpose,
    events: tuple[RecordingEvent, ...],
) -> SimpleNamespace:
    return SimpleNamespace(purpose=purpose, browser_events=events)


def _step(
    step_id: str = "step-1",
    *,
    request_id: str | None = "request_000001",
    method: str = "GET",
) -> SimpleNamespace:
    return SimpleNamespace(id=step_id, request_id=request_id, method=method)


def _draft(
    steps: tuple[SimpleNamespace, ...],
    *,
    target_step_id: str | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(steps=steps, target_step_id=target_step_id)


def _observation(
    *,
    url: str = "https://example.test/items/resource-7?view=compact",
    body: str | None = None,
    response_body: str | None = "{\"ok\":true}",
    response_status: int | None = 200,
    response_truncated: bool = False,
    request_truncated: bool = False,
    step_id: str = "step-1",
    request_id: str = "request_000001",
) -> tuple[SimpleNamespace, SimpleNamespace]:
    recording = _recording(
        RecordingPurpose.OBSERVATION,
        (
            _event(
                RecordingEventKind.REQUEST,
                request_id=request_id,
                url=url,
                method="GET",
                body=body,
                truncated=request_truncated,
                sequence=1,
            ),
            _event(
                RecordingEventKind.RESPONSE,
                request_id=request_id,
                body=response_body,
                status_code=response_status,
                truncated=response_truncated,
                sequence=2,
            ),
        ),
    )
    return recording, _draft((_step(step_id, request_id=request_id, method="GET"),))


def _recovery(
    *,
    method: str = "POST",
    url: str = "https://example.test/items/resource-7",
    body: str | None = '{"resource":"resource-7","keep":true}',
    response_body: str | None = "{}",
    response_status: int | None = 204,
    response_truncated: bool = False,
) -> tuple[SimpleNamespace, SimpleNamespace]:
    recording = _recording(
        RecordingPurpose.RECOVERY,
        (
            _event(
                RecordingEventKind.REQUEST,
                url=url,
                method=method,
                body=body,
                sequence=1,
            ),
            _event(
                RecordingEventKind.RESPONSE,
                body=response_body,
                status_code=response_status,
                truncated=response_truncated,
                sequence=2,
            ),
        ),
    )
    return recording, _draft((_step(method=method),))


def test_resource_value_reads_only_the_declared_path_query_or_nested_json_scalar() -> None:
    path_event = _event(
        RecordingEventKind.REQUEST,
        url="https://example.test/items/resource-7",
        method="GET",
    )
    query_event = _event(
        RecordingEventKind.REQUEST,
        url="https://example.test/items?resource_id=resource-7",
        method="GET",
    )
    json_event = _event(
        RecordingEventKind.REQUEST,
        url="https://example.test/items",
        method="POST",
        body='{"data":{"resource_id":7}}',
    )

    assert resource_value(path_event, _candidate(ValueSlotConsumer.PATH, "path[1]")) == RESOURCE_VALUE
    assert resource_value(query_event, _candidate(ValueSlotConsumer.QUERY, "query.resource_id")) == RESOURCE_VALUE
    assert resource_value(json_event, _candidate(ValueSlotConsumer.JSON_BODY, "$.data.resource_id")) == "7"


@pytest.mark.parametrize(
    "event_and_candidate",
    [
        (
            _event(RecordingEventKind.REQUEST, url="https://example.test/items", method="GET"),
            _candidate(ValueSlotConsumer.PATH, "path[1]"),
        ),
        (
            _event(RecordingEventKind.REQUEST, url="https://example.test/items?resource_id=a&resource_id=b", method="GET"),
            _candidate(ValueSlotConsumer.QUERY, "query.resource_id"),
        ),
        (
            _event(RecordingEventKind.REQUEST, url="https://example.test/items", method="POST", body='{"resource":true}'),
            _candidate(ValueSlotConsumer.JSON_BODY, "$.resource"),
        ),
    ],
)
def test_resource_value_rejects_missing_duplicate_or_non_scalar_values(event_and_candidate) -> None:
    event, candidate = event_and_candidate

    with pytest.raises(JiejianError) as caught:
        resource_value(event, candidate)

    assert caught.value.code == ErrorCode.INPUT_INVALID.value


@pytest.mark.parametrize(
    "events",
    [
        (
            _event(RecordingEventKind.REQUEST, request_id="request_000002", url="https://example.test/items/resource-7", method="GET"),
        ),
        (
            _event(RecordingEventKind.REQUEST, url="https://example.test/items/resource-7", method="POST"),
        ),
        (
            _event(RecordingEventKind.REQUEST, url=None, method="GET"),
        ),
        (
            _event(RecordingEventKind.REQUEST, url="https://example.test/items/resource-7", method="GET", truncated=True),
        ),
    ],
)
def test_request_event_requires_matching_request_method_url_and_complete_event(events: tuple[RecordingEvent, ...]) -> None:
    recording = _recording(RecordingPurpose.OBSERVATION, events)

    with pytest.raises(JiejianError) as caught:
        request_event(recording, _step())

    assert caught.value.code == ErrorCode.RECORD_DRAFT_REFERENCE.value


def test_observation_candidates_require_get_successful_complete_nonempty_response_without_body() -> None:
    recording, draft = _observation()

    candidates = supplement_candidates(recording, draft, RESOURCE_VALUE)

    assert len(candidates) == 1
    assert candidates[0].step_id == "step-1"
    assert candidates[0].request_template.method == "GET"
    assert candidates[0].request_template.relative_path == "/items/{case_resource_id}?view=compact"
    assert candidates[0].request_template.json_body == {}


def test_observation_candidate_replaces_matching_query_value_without_changing_other_query_facts() -> None:
    recording, draft = _observation(
        url="https://example.test/items?resource_id=resource-7&view=compact"
    )

    candidates = supplement_candidates(recording, draft, RESOURCE_VALUE)

    assert len(candidates) == 1
    assert candidates[0].request_template.relative_path == (
        "/items?resource_id={case_resource_id}&view=compact"
    )
    assert candidates[0].request_template.json_body == {}


@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE"])
def test_recovery_candidates_accept_only_successful_state_changing_requests(method: str) -> None:
    recording, draft = _recovery(method=method)

    candidates = supplement_candidates(recording, draft, RESOURCE_VALUE)

    assert len(candidates) == 1
    assert candidates[0].request_template.method == method
    assert candidates[0].request_template.json_body == {
        "resource": "{case_resource_id}",
        "keep": True,
    }


@pytest.mark.parametrize(
    "recording_and_draft",
    [
        _observation(url="https://example.test/items/unrelated"),
        _observation(response_status=500),
        _observation(response_body="", response_status=200),
        _observation(response_truncated=True),
        _observation(body='{"resource":"resource-7"}'),
        _observation(url="https://example.test/items/resource-7?token=secret"),
        _recovery(body="not-json"),
    ],
)
def test_invalid_or_unsafe_recording_facts_do_not_form_candidates(recording_and_draft) -> None:
    recording, draft = recording_and_draft

    assert supplement_candidates(recording, draft, RESOURCE_VALUE) == ()


def test_target_recording_never_forms_supplement_candidates() -> None:
    observation, draft = _observation()
    target = _recording(RecordingPurpose.TARGET, observation.browser_events)

    assert supplement_candidates(target, draft, RESOURCE_VALUE) == ()


def test_empty_supplement_candidates_require_review() -> None:
    recording, draft = _observation(response_status=500)
    with pytest.raises(JiejianError) as caught:
        choose_supplement_candidate(recording, draft, RESOURCE_VALUE)
    assert caught.value.code == ErrorCode.RECORD_DRAFT_UNCONFIRMED.value


def test_nested_json_resource_replacement_preserves_nonmatching_values() -> None:
    recording, draft = _recovery(
        url="https://example.test/items/recover",
        body='{"nested":{"ids":["resource-7","other"],"label":"prefix-resource-7"}}',
    )
    candidates = supplement_candidates(recording, draft, RESOURCE_VALUE)
    assert len(candidates) == 1
    assert candidates[0].request_template.json_body == {
        "nested": {"ids": ["{case_resource_id}", "other"], "label": "prefix-resource-7"},
    }


def test_same_request_template_is_deduplicated_deterministically_without_first_choice() -> None:
    first_recording, first_draft = _observation()
    duplicate_request = _event(
        RecordingEventKind.REQUEST,
        request_id="request_000002",
        url="https://example.test/items/resource-7?view=compact",
        method="GET",
        sequence=3,
    )
    duplicate_response = _event(
        RecordingEventKind.RESPONSE,
        request_id="request_000002",
        body="{\"ok\":true}",
        status_code=200,
        sequence=4,
    )
    recording = _recording(
        RecordingPurpose.OBSERVATION,
        first_recording.browser_events + (duplicate_request, duplicate_response),
    )
    draft = _draft((_step("step-1"), _step("step-2", request_id="request_000002")))

    first = supplement_candidates(recording, draft, RESOURCE_VALUE)
    second = supplement_candidates(recording, draft, RESOURCE_VALUE)

    assert len(first) == 1
    assert first == second
    assert first[0].candidate_id == second[0].candidate_id


def test_different_successful_templates_remain_unconfirmed_and_are_not_auto_selected() -> None:
    first_recording, _ = _observation()
    second_request = _event(
        RecordingEventKind.REQUEST,
        request_id="request_000002",
        url="https://example.test/items/resource-7?view=full",
        method="GET",
        sequence=3,
    )
    second_response = _event(
        RecordingEventKind.RESPONSE,
        request_id="request_000002",
        body="{\"ok\":true}",
        status_code=200,
        sequence=4,
    )
    recording = _recording(
        RecordingPurpose.OBSERVATION,
        first_recording.browser_events + (second_request, second_response),
    )
    draft = _draft((_step("step-1"), _step("step-2", request_id="request_000002")))

    with pytest.raises(JiejianError) as caught:
        choose_supplement_candidate(recording, draft, RESOURCE_VALUE)

    assert caught.value.code == ErrorCode.RECORD_DRAFT_UNCONFIRMED.value


def test_choose_supplement_candidate_auto_selects_one_or_requires_matching_explicit_step() -> None:
    recording, draft = _observation()

    selected = choose_supplement_candidate(recording, draft, RESOURCE_VALUE)
    assert selected.step_id == "step-1"

    explicit = choose_supplement_candidate(
        recording,
        _draft((_step("step-1"),), target_step_id="step-1"),
        RESOURCE_VALUE,
    )
    assert explicit == selected

    with pytest.raises(JiejianError) as caught:
        choose_supplement_candidate(
            recording,
            _draft((_step("step-1"),), target_step_id="step-other"),
            RESOURCE_VALUE,
        )
    assert caught.value.code == ErrorCode.RECORD_DRAFT_REFERENCE.value


def _flow_template(
    *,
    method: str = "GET",
    path: str = "/items/{resource}",
    query_value: str = "compact",
) -> HttpRequestTemplate:
    return HttpRequestTemplate(
        method=method,
        path=path,
        query=(HttpParameter(name="view", literal=query_value),),
        body=EmptyBody(),
        input_slots=(
            ValueSlot(
                slot_id="resource",
                source=ValueSlotSource.CASE_RESOURCE_ID,
                consumer=ValueSlotConsumer.PATH,
            ),
        ),
    )


def _flow(template: HttpRequestTemplate) -> SimpleNamespace:
    return SimpleNamespace(
        target_step_id="step-1",
        steps=(SimpleNamespace(id="step-1", request_template=template),),
    )


def test_flow_resource_injection_fingerprint_ignores_values_but_distinguishes_compatibility() -> None:
    candidate = _candidate(ValueSlotConsumer.PATH, "path[1]")
    same_shape = _candidate(ValueSlotConsumer.PATH, "path[1]", suffix="2")

    first = flow_resource_injection(_flow(_flow_template(query_value="compact")), candidate)
    second = flow_resource_injection(_flow(_flow_template(query_value="full")), same_shape)
    changed_address = flow_resource_injection(
        _flow(_flow_template(path="/records/{resource}")), candidate
    )
    changed_method = flow_resource_injection(
        _flow(_flow_template(method="POST")), candidate
    )
    changed_consumer = flow_resource_injection(
        _flow(_flow_template()), _candidate(ValueSlotConsumer.QUERY, "query.view")
    )
    changed_location = flow_resource_injection(
        _flow(_flow_template()), _candidate(ValueSlotConsumer.PATH, "path[2]", suffix="3")
    )

    assert first.template_fingerprint == second.template_fingerprint
    assert first.template_fingerprint != changed_address.template_fingerprint
    assert first.template_fingerprint != changed_method.template_fingerprint
    assert first.template_fingerprint != changed_consumer.template_fingerprint
    assert first.template_fingerprint != changed_location.template_fingerprint
