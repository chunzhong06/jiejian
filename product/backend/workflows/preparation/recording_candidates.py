# 从已保存的录制事件提取有限资源和明确目的的请求候选，不猜测业务效果。

from __future__ import annotations

import json
import re
from typing import Any
from urllib.parse import parse_qsl, quote, unquote, urlencode, urlsplit

from pydantic import ValidationError

from product.backend.core.action_preparation import RecordedRequestTemplate, ResourceInjection, ResourceInjectionKind
from product.backend.core.business_boundary import BoundaryModel, boundary_sha256
from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.core.recording import RecordingPurpose
from product.protocols.recording import RecordingEventKind
from product.protocols.web.workflow import ValueSlotConsumer


class RecordedPreparationCandidate(BoundaryModel):
    candidate_id: str
    step_id: str
    request_template: RecordedRequestTemplate


def request_event(recording, step):
    event = next((item for item in recording.browser_events
                  if item.kind is RecordingEventKind.REQUEST and item.request_id == step.request_id), None)
    if event is None or event.url is None or event.method != step.method or event.truncated:
        raise JiejianError(ErrorCode.RECORD_DRAFT_REFERENCE, "录制请求与已确认步骤无法关联")
    return event


def resource_value(event, candidate) -> str:
    """从候选声明的单一位置读回真实有限值，不能由候选标签补造资源。"""
    parsed = urlsplit(event.url or "")
    if candidate.consumer is ValueSlotConsumer.PATH:
        index = int(candidate.location.removeprefix("path[").removesuffix("]"))
        parts = [unquote(item) for item in parsed.path.split("/") if item]
        value = parts[index] if index < len(parts) else None
    elif candidate.consumer is ValueSlotConsumer.QUERY:
        values = [item for name, item in parse_qsl(parsed.query, keep_blank_values=True)
                  if name == candidate.location.removeprefix("query.")]
        value = values[0] if len(values) == 1 else None
    else:
        value = _json_location(_request_json(event), candidate.location)
    if type(value) not in {str, int}:
        raise JiejianError(ErrorCode.INPUT_INVALID, "录制中的测试资源不是唯一有限标识")
    return str(value)


def flow_resource_injection(flow, candidate) -> ResourceInjection:
    target = next(item for item in flow.steps if item.id == flow.target_step_id)
    template = target.request_template
    # 比较资源槽所在请求的地址与消费位置，不把来源账号、具体资源或普通表单值混入兼容性。
    fingerprint = boundary_sha256({
        "method": template.method, "path": template.path,
        "query_names": sorted(item.name for item in template.query),
        "consumer": candidate.consumer.value, "location": candidate.location,
    })
    return ResourceInjection(
        consumer=ResourceInjectionKind(candidate.consumer.value), location=candidate.location,
        template_fingerprint=fingerprint,
    )


def supplement_candidates(recording, draft, actual_resource_id: str) -> tuple[RecordedPreparationCandidate, ...]:
    """只按提交时冻结的目的筛选；多个不同请求始终留给用户确认。"""
    if recording.purpose is RecordingPurpose.TARGET:
        return ()
    methods = {"GET"} if recording.purpose is RecordingPurpose.OBSERVATION else {"POST", "PUT", "PATCH", "DELETE"}
    candidates = []
    seen = set()
    for step in draft.steps:
        if step.method not in methods or step.request_id is None:
            continue
        event = request_event(recording, step)
        response = next((item for item in recording.browser_events
                         if item.kind is RecordingEventKind.RESPONSE and item.request_id == step.request_id), None)
        if (response is None or response.truncated or response.status_code is None
                or not 200 <= response.status_code < 300
                or (recording.purpose is RecordingPurpose.OBSERVATION and not response.body)):
            continue
        template = _template_for_resource(event, actual_resource_id)
        if template is None:
            continue
        digest = boundary_sha256(template.model_dump(mode="json"))
        if digest in seen:
            continue
        seen.add(digest)
        candidates.append(RecordedPreparationCandidate(
            candidate_id="request-" + digest[:24], step_id=step.id, request_template=template,
        ))
    return tuple(candidates)


def choose_supplement_candidate(recording, draft, actual_resource_id: str):
    candidates = supplement_candidates(recording, draft, actual_resource_id)
    if draft.target_step_id is not None:
        selected = next((item for item in candidates if item.step_id == draft.target_step_id), None)
        if selected is None:
            raise JiejianError(ErrorCode.RECORD_DRAFT_REFERENCE, "所选步骤不属于当前补录目的的有效候选")
        return selected
    if len(candidates) != 1:
        raise JiejianError(ErrorCode.RECORD_DRAFT_UNCONFIRMED, "请确认结果证明或恢复方式的唯一业务步骤")
    return candidates[0]


def _template_for_resource(event, resource: str) -> RecordedRequestTemplate | None:
    parsed = urlsplit(event.url or "")
    path = []
    replaced = False
    for part in parsed.path.split("/"):
        value = unquote(part)
        if value and value == resource:
            value, replaced = "{case_resource_id}", True
        path.append(quote(value, safe="{}:@!$&'()*+,;=-._~"))
    query = []
    for name, value in parse_qsl(parsed.query, keep_blank_values=True):
        if value == resource:
            value, replaced = "{case_resource_id}", True
        query.append((name, value))
    try:
        body, body_replaced = _replace_json_value(_request_json(event), resource)
        if event.method == "GET" and body:
            return None
        if not (replaced or body_replaced):
            return None
        relative_path = "/".join(path)
        if query:
            relative_path += "?" + urlencode(query, safe="{}")
        return RecordedRequestTemplate(method=event.method, relative_path=relative_path, json_body=body)
    except (JiejianError, ValidationError):
        # 无法完整表达或含脱敏空洞的请求不构成可接受的技术来源。
        return None


def _request_json(event) -> dict[str, Any]:
    if not event.body:
        return {}
    try:
        value = json.loads(event.body)
    except ValueError:
        raise JiejianError(ErrorCode.RECORD_DRAFT_REFERENCE, "录制请求正文不能表示为受限 JSON") from None
    if not isinstance(value, dict):
        raise JiejianError(ErrorCode.RECORD_DRAFT_REFERENCE, "录制请求正文必须是 JSON 对象")
    return value


def _json_location(value, path):
    current = value
    for field, offset in re.findall(r"\.([A-Za-z_][A-Za-z0-9_-]*)|\[([0-9]+)\]", path):
        try:
            current = current[field if field else int(offset)]
        except (KeyError, IndexError, TypeError):
            return None
    return current


def _replace_json_value(value, expected):
    if isinstance(value, dict):
        pairs = {key: _replace_json_value(item, expected) for key, item in value.items()}
        return {key: pair[0] for key, pair in pairs.items()}, any(pair[1] for pair in pairs.values())
    if isinstance(value, list):
        pairs = [_replace_json_value(item, expected) for item in value]
        return [pair[0] for pair in pairs], any(pair[1] for pair in pairs)
    if type(value) in {str, int} and str(value) == expected:
        return "{case_resource_id}", True
    return value, False
