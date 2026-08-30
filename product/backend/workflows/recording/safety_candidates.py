# 录制安全候选生成与归一化辅助。
#
# 职责：从受限录制生成资源、观察、恢复和效果候选；候选确认前不形成安全事实。
# 边界：不执行目标请求，不接受任意 URL、脚本或 JSONPath。

from __future__ import annotations

import json
from collections import Counter
from typing import Any, Callable
from urllib.parse import parse_qsl, quote, unquote, urlencode, urlsplit

from pydantic import BaseModel

from product.backend.core.application_understanding import (
    ActionRiskHint,
    ApplicationUnderstanding,
)
from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.core.test_setup import (
    ResourceValueConsumer,
    test_setup_sha256,
)
from product.backend.core.verification.permissions import SecurityEffectKind
from product.backend.infra.storage import RecordingRecord
from product.backend.core.recording import RecordingPurpose
from product.protocols import FlowDraftResourceCandidate, FlowDraftStep
from product.protocols.recording import RecordingEvent, RecordingEventKind
from product.protocols.web.workflow import ValueSlotConsumer

_MUTATING_METHODS = frozenset({"PATCH", "POST", "PUT", "DELETE"})
_SUCCESS_MIN = 200
_SUCCESS_MAX = 299


def _resource_candidate_view(context: _SetupContext) -> TestResourceCandidateView:
    from .safety_setup import TestResourceCandidateView
    payload = {
        "recording_id": context.recording.recording_id,
        "step_id": context.target_step.id,
        "candidate_id": context.resource_candidate.candidate_id,
        "value": context.resource_value,
    }
    fingerprint = test_setup_sha256("test_resource_candidate", payload)
    return TestResourceCandidateView(
        candidate_id=f"trc_{fingerprint[:32]}",
        label="录制中已确认的业务资源",
        suggested_resource_type=_suggest_resource_type(
            context.target_event,
            context.resource_candidate,
        ),
        actual_resource_id=context.resource_value,
        consumer=ResourceValueConsumer(context.resource_candidate.consumer.value),
        location=context.resource_candidate.location,
    )

def _binding_candidates(
    context: _SetupContext,
) -> tuple[tuple[ObservationCandidateView, ...], tuple[RecoveryCandidateView, ...]]:
    from .safety_setup import ObservationCandidateView, RecoveryCandidateView
    target_index = next(
        index
        for index, step in enumerate(context.draft.steps)
        if step.id == context.target_step.id
    )
    observations: list[ObservationCandidateView] = []
    recoveries: list[RecoveryCandidateView] = []
    sources = (
        (context.recording, context.draft, context.draft.steps[target_index + 1 :]),
        *(
            (recording, draft, draft.steps)
            for recording, draft in context.supplements
        ),
    )
    for recording, _draft, steps in sources:
        responses = {
            event.request_id: event
            for event in recording.browser_events
            if event.kind is RecordingEventKind.RESPONSE and event.request_id is not None
        }
        for step in steps:
            if step.method is None or step.request_id is None:
                continue
            if recording.purpose is RecordingPurpose.OBSERVATION and step.method != "GET":
                continue
            if recording.purpose is RecordingPurpose.RECOVERY and step.method not in _MUTATING_METHODS:
                continue
            request = _request_event(recording, step)
            response = responses.get(request.request_id)
            if (
                response is None
                or response.status_code is None
                or not _SUCCESS_MIN <= response.status_code <= _SUCCESS_MAX
                or response.truncated
            ):
                continue
            template = _template_for_resource(request, context.resource_value)
            if template is None:
                continue
            base = {
                "recording_id": recording.recording_id,
                "source_step_id": step.id,
                "path_template": template.path,
                "json_body_template": template.json_body,
                "test_identity_id": context.recording_identity.identity_id,
            }
            if step.method == "GET" and response.body:
                digest = test_setup_sha256("observation_candidate", base)
                observations.append(
                    ObservationCandidateView(
                        candidate_id=f"obc_{digest[:32]}",
                        label="独立读取并核对业务结果",
                        source_recording_id=recording.recording_id,
                        source_step_id=step.id,
                        method="GET",
                        path_template=template.path,
                        trusted_test_identity_id=context.recording_identity.identity_id,
                    )
                )
            elif step.method in _MUTATING_METHODS:
                digest = test_setup_sha256(
                    "recovery_candidate",
                    {**base, "method": step.method},
                )
                recoveries.append(
                    RecoveryCandidateView(
                        candidate_id=f"rcc_{digest[:32]}",
                        label="恢复测试现场",
                        source_recording_id=recording.recording_id,
                        source_step_id=step.id,
                        method=step.method,
                        path_template=template.path,
                        json_body_template=template.json_body,
                        test_identity_id=context.recording_identity.identity_id,
                    )
                )
    return (
        _disambiguate_labels(
            _dedupe_candidates(tuple(observations), key=_observation_key),
            context,
        ),
        _disambiguate_labels(
            _dedupe_candidates(tuple(recoveries), key=_recovery_key),
            context,
        ),
    )


def _observation_key(candidate: Any) -> tuple[str, str, str]:
    """按真实执行语义去重，录制步骤只作为首条候选的来源证据。"""

    return (
        candidate.method,
        candidate.path_template,
        candidate.trusted_test_identity_id,
    )


def _recovery_key(candidate: Any) -> tuple[str, str, str, str]:
    """按恢复请求语义去重，不把同一请求的录制位置当成不同方案。"""

    return (
        candidate.method,
        candidate.path_template,
        _json_sha256(candidate.json_body_template),
        candidate.test_identity_id,
    )


def _effect_key(candidate: Any) -> tuple[str, tuple[str, ...]]:
    return candidate.kind.value, tuple(candidate.protected_fields)


def _dedupe_candidates(
    candidates: tuple[Any, ...],
    *,
    key: Callable[[Any], object],
) -> tuple[Any, ...]:
    seen: set[object] = set()
    result: list[Any] = []
    for candidate in candidates:
        candidate_key = key(candidate)
        if candidate_key in seen:
            continue
        seen.add(candidate_key)
        result.append(candidate)
    return tuple(result)


def _disambiguate_labels(candidates: tuple[Any, ...], context: _SetupContext) -> tuple[Any, ...]:
    del context
    counts = Counter(candidate.label for candidate in candidates)
    offsets: Counter[str] = Counter()
    result: list[Any] = []
    for candidate in candidates:
        if counts[candidate.label] == 1:
            result.append(candidate)
            continue
        offsets[candidate.label] += 1
        result.append(
            candidate.model_copy(
                update={"label": f"{candidate.label}（方案 {offsets[candidate.label]}）"},
            )
        )
    return tuple(result)

def _effect_candidates(
    context: _SetupContext,
) -> tuple[SecurityEffectCandidateView, ...]:
    from .safety_setup import SecurityEffectCandidateView
    method = str(context.target_step.method)
    if context.action.risk_hint is ActionRiskHint.ADMIN:
        return ()
    if method in {"PATCH", "PUT", "DELETE"}:
        kind = SecurityEffectKind.STATE_MUTATION
        label = "修改受保护资源状态"
    elif method == "POST" and context.action.risk_hint is ActionRiskHint.WRITE:
        kind = SecurityEffectKind.OBJECT_CREATION
        label = "创建受保护业务对象"
    else:
        # DATA_DISCLOSURE 还需要明确受保护字段；没有可靠字段候选时不能兜底为状态变更。
        return ()
    digest = test_setup_sha256(
        "security_effect_candidate",
        {
            "action_candidate_id": context.action.candidate_id,
            "method": method,
            "kind": kind.value,
        },
    )
    return _dedupe_candidates((
        SecurityEffectCandidateView(
            candidate_id=f"sfc_{digest[:32]}",
            kind=kind,
            label=label,
        ),
    ), key=_effect_key)

def _state_changing(context: _SetupContext) -> bool:
    return not (
        context.target_step.method == "GET"
        and context.action.risk_hint is ActionRiskHint.READ
    )


def _setup_is_current(context: _SetupContext) -> bool:
    setup = context.existing
    if setup is None:
        return False
    resource = setup.resource
    return (
        resource.recording_id == context.recording.recording_id
        and resource.flow_id == context.flow.id
        and resource.flow_sha256 == context.flow_sha256
        and resource.endpoint_source_fingerprint
        == context.understanding.endpoint_source_fingerprint
        and resource.actual_resource_id == context.resource_value
    )

def _request_event(recording: RecordingRecord, step: FlowDraftStep) -> RecordingEvent:
    event = next(
        (
            item
            for item in recording.browser_events
            if item.kind is RecordingEventKind.REQUEST
            and item.request_id == step.request_id
        ),
        None,
    )
    if event is None or event.url is None or event.method != step.method:
        raise JiejianError(
            ErrorCode.RECORD_DRAFT_REFERENCE,
            "录制请求与已确认步骤无法关联",
        )
    return event

def _resource_value(
    event: RecordingEvent,
    candidate: FlowDraftResourceCandidate,
) -> str:
    parsed = urlsplit(event.url or "")
    value: Any = None
    if candidate.consumer is ValueSlotConsumer.PATH:
        index = int(candidate.location.removeprefix("path[").removesuffix("]"))
        parts = [unquote(item) for item in parsed.path.split("/") if item]
        if index < len(parts):
            value = parts[index]
    elif candidate.consumer is ValueSlotConsumer.QUERY:
        key = candidate.location.removeprefix("query.")
        value = next(
            (item for name, item in parse_qsl(parsed.query, keep_blank_values=True) if name == key),
            None,
        )
    else:
        value = _json_location(_request_json(event), candidate.location)
    if type(value) not in {str, int}:
        raise JiejianError(ErrorCode.INPUT_INVALID, "录制中的测试资源不是有限标识")
    return str(value)

def _template_for_resource(
    event: RecordingEvent,
    resource_value: str,
) -> _RequestTemplate | None:
    from .safety_setup import _RequestTemplate
    parsed = urlsplit(event.url or "")
    replaced = False
    path_parts = parsed.path.split("/")
    for index, item in enumerate(path_parts):
        if item and unquote(item) == resource_value:
            path_parts[index] = "{case_resource_id}"
            replaced = True
    query: list[tuple[str, str]] = []
    for key, value in parse_qsl(parsed.query, keep_blank_values=True):
        if value == resource_value:
            value = "{case_resource_id}"
            replaced = True
        query.append((key, value))
    body, body_replaced = _replace_json_value(_request_json(event), resource_value)
    replaced = replaced or body_replaced
    if not replaced:
        return None
    path = "/".join(
        quote(item, safe="{}:@!$&'()*+,;=-._~") if item else ""
        for item in path_parts
    )
    if not path.startswith("/"):
        path = "/" + path
    if query:
        path += "?" + urlencode(query, doseq=True, safe="{}")
    return _RequestTemplate(path=path, json_body=body)

def _request_json(event: RecordingEvent) -> dict[str, Any]:
    if not event.body:
        return {}
    try:
        value = json.loads(event.body)
    except (TypeError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}

def _json_location(value: Any, path: str) -> Any:
    current = value
    import re

    for field, offset in re.findall(
        r"\.([A-Za-z_][A-Za-z0-9_-]*)|\[([0-9]+)\]",
        path,
    ):
        key: str | int = field if field else int(offset)
        try:
            current = current[key]
        except (KeyError, IndexError, TypeError):
            return None
    return current

def _replace_json_value(value: Any, expected: str) -> tuple[Any, bool]:
    if isinstance(value, dict):
        changed = False
        result: dict[str, Any] = {}
        for key, item in value.items():
            next_item, item_changed = _replace_json_value(item, expected)
            result[key] = next_item
            changed = changed or item_changed
        return result, changed
    if isinstance(value, list):
        changed = False
        result = []
        for item in value:
            next_item, item_changed = _replace_json_value(item, expected)
            result.append(next_item)
            changed = changed or item_changed
        return result, changed
    if str(value) == expected and type(value) in {str, int}:
        return "{case_resource_id}", True
    return value, False

def _suggest_resource_type(
    event: RecordingEvent,
    candidate: FlowDraftResourceCandidate,
) -> str:
    parsed = urlsplit(event.url or "")
    segments = [unquote(item) for item in parsed.path.split("/") if item]
    if candidate.consumer is ValueSlotConsumer.PATH:
        index = int(candidate.location.removeprefix("path[").removesuffix("]"))
        if index > 0 and index <= len(segments) - 1:
            value = segments[index - 1].replace("_", " ").replace("-", " ")
            return value[:128] or "业务资源"
    return "业务资源"

def _required_endpoint_fingerprint(understanding: ApplicationUnderstanding) -> str:
    if understanding.endpoint_source_fingerprint is None:
        raise JiejianError(ErrorCode.APPLICATION_ENDPOINT_INVALID, "应用运行地址尚未确认")
    return understanding.endpoint_source_fingerprint

def _json_sha256(value: Any) -> str:
    return test_setup_sha256("canonical_json", _json_value(value))

def _json_value(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, dict):
        return {key: _json_value(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_json_value(item) for item in value]
    if hasattr(value, "value"):
        return value.value
    return value

def _pick(items: tuple[Any, ...], candidate_id: str, message: str) -> Any:
    selected = next((item for item in items if item.candidate_id == candidate_id), None)
    if selected is None:
        raise JiejianError(ErrorCode.INPUT_INVALID, message)
    return selected

def _pick_optional(
    items: tuple[Any, ...],
    candidate_id: str | None,
    message: str,
) -> Any | None:
    return None if candidate_id is None else _pick(items, candidate_id, message)

__all__ = [name for name in globals() if name.startswith("_") and name not in {"__all__"}]
