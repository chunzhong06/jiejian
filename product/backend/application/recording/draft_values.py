# 已脱敏录制值的解析、变量替换与敏感字段标注。
from __future__ import annotations
import hashlib
import json
import re
from collections.abc import Mapping
from typing import Any
from urllib.parse import parse_qsl, unquote, urlencode, urlsplit
from product.backend.domain.errors import ErrorCode, JiejianError
from product.protocols.recording.flow_draft import FlowDraftVariableSource
from product.protocols.recording.events import RecordingEventKind, RecordingEvent
from product.backend.domain.redaction import REDACTED
from .draft_models import _StepData

def _relative_path(url: str | None) -> str:
    if not url:
        raise JiejianError(ErrorCode.RECORD_DRAFT_INVALID, '请求事件缺少 URL')
    parsed = urlsplit(url)
    return parsed.path + (f'?{parsed.query}' if parsed.query else '')

def _request_json(event: RecordingEvent) -> dict[str, Any]:
    if event.method not in _HTTP_METHODS:
        raise JiejianError(ErrorCode.RECORD_DRAFT_INVALID, '请求方法无法编译为 Flow')
    if not event.body:
        return {}
    try:
        value = json.loads(event.body)
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}

def _replace_path(path: str, available: Mapping[str, list[FlowDraftVariableSource]], matched: set[str]) -> str:
    parsed = urlsplit(path)
    segments = []
    for segment in parsed.path.split('/'):
        key = _value_key(unquote(segment))
        if segment and key in available:
            segments.append(_candidate_placeholder(key))
            matched.add(key)
        else:
            segments.append(segment)
    query = []
    for name, value in parse_qsl(parsed.query, keep_blank_values=True):
        key = _value_key(value)
        if key in available and (not _SENSITIVE_FIELD.search(name)):
            query.append((name, _candidate_placeholder(key)))
            matched.add(key)
        else:
            query.append((name, value))
    encoded_query = urlencode(query, safe='{}')
    return '/'.join(segments) + (f'?{encoded_query}' if encoded_query else '')

def _replace_json(value: Any, available: Mapping[str, list[FlowDraftVariableSource]], matched: set[str], *, parent_key: str='') -> Any:
    if isinstance(value, Mapping):
        return {key: _replace_json(item, available, matched, parent_key=str(key)) for key, item in value.items()}
    if isinstance(value, list):
        return [_replace_json(item, available, matched, parent_key=parent_key) for item in value]
    key = _value_key(value) if isinstance(value, (str, int)) else ''
    if key in available and (not _SENSITIVE_FIELD.search(parent_key)):
        matched.add(key)
        return _candidate_placeholder(key)
    return value

def _walk_scalars(value: Any, path: str='$') -> list[tuple[str, Any]]:
    found: list[tuple[str, Any]] = []
    if isinstance(value, Mapping):
        for key in sorted(value, key=str):
            found.extend(_walk_scalars(value[key], f'{path}.{_safe_name(str(key))}'))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            found.extend(_walk_scalars(item, f'{path}[{index}]'))
    elif isinstance(value, (str, int)) and (not isinstance(value, bool)):
        found.append((path, value))
    return found

def _business_field(value: str) -> str:
    tail = re.split('[.\\[\\]_-]+', value)[-1].strip()
    return {'id': '业务对象', 'project': '项目', 'resource': '资源'}.get(tail.casefold(), tail or '业务对象')

def _candidate_value(value: Any) -> bool:
    return isinstance(value, str) and value != REDACTED and (3 <= len(value) <= 256) or (isinstance(value, int) and (not isinstance(value, bool)) and (value >= 2))

def _path_sensitive(path: str) -> bool:
    return any((_SENSITIVE_FIELD.search(part) for part in path.split('.')))

def _value_key(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))

def _candidate_placeholder(value_key: str) -> str:
    digest = hashlib.sha256(value_key.encode('utf-8')).hexdigest()[:16]
    return '{candidate-' + digest + '}'

def _safe_name(value: str) -> str:
    normalized = re.sub('[^a-z0-9_-]+', '_', value.casefold()).strip('_-')
    if not normalized or not normalized[0].isalpha():
        return 'value'
    return normalized[:64]

def _variable_name(json_path: str, used_names: set[str]) -> str:
    tail = re.split('[.\\[\\]]+', json_path)[-1] or 'resource_id'
    base = _safe_name(tail)
    if base == 'id' or json_path.startswith('$location'):
        base = 'resource_id'
    if base == 'created_resource_id':
        base = 'response_created_resource_id'
    name = base
    suffix = 2
    while name in used_names:
        name = f'{base[:58]}-{suffix}'
        suffix += 1
    return name

def _rename_placeholder(value: Any, source: str, target: str) -> Any:
    if isinstance(value, Mapping):
        return {key: _rename_placeholder(item, source, target) for key, item in value.items()}
    if isinstance(value, list):
        return [_rename_placeholder(item, source, target) for item in value]
    return target if value == source else value

def _sensitive_fields(step: _StepData) -> tuple[str, ...]:
    fields: set[str] = set()
    for event in step.actions:
        if event.field_name and _SENSITIVE_FIELD.search(event.field_name):
            fields.add(f'ui.{event.field_name}')
        if event.input_type and _SENSITIVE_FIELD.search(event.input_type):
            fields.add(f'ui.{event.input_type}')
    if step.request is not None:
        fields.update((f'headers.{header.name}' for header in step.request.headers if _SENSITIVE_FIELD.search(header.name)))
        _collect_sensitive_json(step.json_body, '$', fields)
    return tuple(sorted(fields))

def _collect_sensitive_json(value: Any, path: str, fields: set[str]) -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            child = f'{path}.{key}'
            if _SENSITIVE_FIELD.search(str(key)):
                fields.add(child)
            _collect_sensitive_json(item, child, fields)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _collect_sensitive_json(item, f'{path}[{index}]', fields)

def _step_name(step: _StepData) -> str:
    if step.request is not None:
        return {'GET': '读取业务状态', 'POST': '提交业务操作', 'PUT': '更新业务对象', 'PATCH': '更新业务对象', 'DELETE': '删除业务对象'}.get(str(step.request.method), '完成业务操作')
    if step.actions:
        labels = {RecordingEventKind.UI_CLICK: 'click', RecordingEventKind.UI_INPUT_CHANGE: 'input change', RecordingEventKind.UI_SUBMIT: 'submit'}
        return labels[step.actions[-1].kind]
    return 'recorded step'
_HTTP_METHODS = {'GET', 'PATCH', 'POST', 'PUT', 'DELETE'}
_SENSITIVE_FIELD = re.compile('(?:authorization|cookie|credential|password|passwd|secret|token|api[_-]?key|id[_-]?card|ssn|email|phone|address|full[_-]?name)', re.IGNORECASE)
_OPAQUE_BUSINESS_VALUE = re.compile('^(?:[a-z][a-z0-9_]*[-_])?(?:[0-9]+|[0-9a-f]{8,})$|^[0-9a-f-]{16,}$', re.IGNORECASE)
