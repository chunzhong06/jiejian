# 由录制步骤推导有限资源候选，不访问现场目标。
from __future__ import annotations
from product.backend.application.recording.json_locations import read_json_location
import hashlib
import re
from collections.abc import Sequence
from typing import Any
from urllib.parse import parse_qsl, unquote, urlsplit
from product.protocols.recording.flow_draft import FlowDraftResourceCandidate, FlowDraftStep
from product.protocols.web.workflow import ValueSlotConsumer
from .draft_models import _StepData
from .draft_values import _OPAQUE_BUSINESS_VALUE, _SENSITIVE_FIELD, _business_field, _candidate_value, _path_sensitive, _request_json, _walk_scalars

def _resource_candidates(step: _StepData, action_path_templates: Sequence[str]=(), allow_created_resources: bool=False) -> tuple[FlowDraftResourceCandidate, ...]:
    """从当前请求或已确认创建动作的响应列出有界位置，不接受自填对象。"""
    if step.request is None:
        return ()
    if allow_created_resources:
        from product.protocols.recording.created_resource import response_object_candidates
        response = step.response
        if response is None or response.truncated or step.request.truncated or (response.status_code is None) or (not 200 <= response.status_code < 300) or (response.status_code == 202):
            return ()
        response_candidates = tuple((_resource_candidate(step.step_id, kind, location, f'响应中的对象 {identifier[:180]}（候选 {index + 1}）') for index, (kind, location, identifier) in enumerate(response_object_candidates(response.body, [(header.name, header.value) for header in response.headers], step.request.url))))
        if response_candidates:
            return response_candidates
    candidates: list[FlowDraftResourceCandidate] = []
    parsed = urlsplit(step.path or '/')
    recorded = urlsplit(step.request.url or '/')
    path_segments = [segment for segment in parsed.path.split('/') if segment]
    recorded_segments = [unquote(segment) for segment in recorded.path.split('/') if segment]
    positions = _confirmed_path_positions(step, action_path_templates)
    for index, segment in enumerate(path_segments):
        value = recorded_segments[index] if index < len(recorded_segments) else unquote(segment)
        if (positions is None or index in positions) and _candidate_value(value):
            candidates.append(_resource_candidate(step.step_id, ValueSlotConsumer.PATH, f'path[{index}]', _business_candidate_label(value, '看起来是当前业务对象')))
    recorded_query = dict(parse_qsl(recorded.query, keep_blank_values=True))
    for name, current_value in parse_qsl(parsed.query, keep_blank_values=True):
        value = recorded_query.get(name, current_value)
        if _candidate_value(value) and (not _SENSITIVE_FIELD.search(name)):
            candidates.append(_resource_candidate(step.step_id, ValueSlotConsumer.QUERY, f'query.{name}', _business_candidate_label(value, f'看起来是当前 {_business_field(name)}')))
    recorded_body = _request_json(step.request)
    for path, current_value in _walk_scalars(step.json_body):
        value = read_json_location(recorded_body, path)
        if value is None:
            value = current_value
        if _candidate_value(value) and (not _path_sensitive(path)):
            candidates.append(_resource_candidate(step.step_id, ValueSlotConsumer.JSON_BODY, path, _business_candidate_label(value, f'看起来是当前 {_business_field(path)}')))
    return tuple(candidates[:128])

def _confirmed_path_positions(step, templates):
    recorded = [unquote(item) for item in urlsplit(step.request.url or '/').path.split('/') if item]
    positions = None
    for canonical in templates:
        method, separator, template = canonical.partition(' ')
        parts = [unquote(item) for item in template.split('/') if item]
        if not separator or method != step.request.method or len(parts) != len(recorded):
            continue
        slots = {i for i, part in enumerate(parts) if re.fullmatch('\\{[A-Za-z_][A-Za-z0-9_]*\\}', part)}
        if all((i in slots or part == recorded[i] for i, part in enumerate(parts))):
            positions = slots if positions is None else positions | slots
    return positions

def _resource_candidate(step_id: str, consumer: ValueSlotConsumer | str, location: str, label: str) -> FlowDraftResourceCandidate:
    digest = hashlib.sha256(f'{step_id}\x00{consumer}\x00{location}'.encode('utf-8')).hexdigest()[:16]
    return FlowDraftResourceCandidate(candidate_id=f'resource-{digest}', consumer=consumer, location=location, label=label)

def _business_candidate_label(value: Any, meaning: str) -> str:
    """只把可读业务值放进标签，内部编号仍留在确定性候选结构。"""
    if isinstance(value, str) and (not _OPAQUE_BUSINESS_VALUE.fullmatch(value)):
        return f'{value}（{meaning}）'
    return meaning

def _recommend_target(steps: tuple[FlowDraftStep, ...], directly_triggered_requests: frozenset[str]) -> str | None:
    network = tuple((step for step in steps if step.method is not None))
    if not network:
        return None
    ranked = sorted(network, key=lambda step: (step.request_id in directly_triggered_requests, step.method in {'PATCH', 'POST', 'PUT', 'DELETE'}, bool(step.resource_candidates), step.source_event_sequences[-1]))
    return ranked[-1].id

def _automatic_target(steps: tuple[FlowDraftStep, ...], directly_triggered_requests: frozenset[str]) -> str | None:
    network = tuple((step for step in steps if step.method is not None))
    if not network:
        return None
    scores = {step.id: (step.request_id in directly_triggered_requests, step.method in {'PATCH', 'POST', 'PUT', 'DELETE'}, bool(step.resource_candidates)) for step in network}
    best = max(scores.values())
    winners = tuple((step.id for step in network if scores[step.id] == best))
    return winners[0] if len(winners) == 1 else None
