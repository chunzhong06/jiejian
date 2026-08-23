# =============================================================================
# Recording FlowDraft 编译
#
# 定位
#   已脱敏事件序列与待审阅 FlowDraft 之间的确定性转换
#
# 职责
#   关联逻辑动作｜提取变量来源｜生成稳定 step、依赖和规范草稿
#
# 边界
#   只消费已脱敏事件，不访问浏览器或目标，也不把推断变量自动视为人工确认。
#
# 调用链
#   RecordingSubmission → FlowDraftProcessor → FlowDraft
# =============================================================================

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import parse_qsl, unquote, urlencode, urlsplit

from product.backend.core.errors import ErrorCode, JiejianError
from product.protocols.flow_draft import FlowDraftStep, FlowDraft, FlowDraftVariableSource, FlowDraftVariableStatus, FlowDraftVariable, canonical_flow_draft_json_bytes
from product.protocols.recording import RecordingEventKind, RecordingEvent
from product.backend.core.redaction import REDACTED

_UI_KINDS = {
    RecordingEventKind.UI_CLICK,
    RecordingEventKind.UI_INPUT_CHANGE,
    RecordingEventKind.UI_SUBMIT,
}
_HTTP_METHODS = {"GET", "PATCH", "POST", "PUT", "DELETE"}
_SENSITIVE_FIELD = re.compile(
    r"(?:authorization|cookie|credential|password|passwd|secret|token|"
    r"api[_-]?key|id[_-]?card|ssn|email|phone|address|full[_-]?name)",
    re.IGNORECASE,
)


@dataclass(slots=True)
class _LogicalAction:
    events: list[RecordingEvent]

    @property
    def action_ids(self) -> tuple[str, ...]:
        return tuple(event.action_id for event in self.events if event.action_id)


@dataclass(slots=True)
class _StepData:
    first_sequence: int
    identity_id: str
    actions: list[RecordingEvent] = field(default_factory=list)
    request: RecordingEvent | None = None
    response: RecordingEvent | None = None
    step_id: str = ""
    path: str | None = None
    json_body: dict[str, Any] = field(default_factory=dict)
    dependencies: set[str] = field(default_factory=set)


@dataclass(frozen=True, slots=True)
class _ValueSource:
    value: str | int
    source: FlowDraftVariableSource


@dataclass(slots=True)
class _VariableData:
    name: str
    candidates: tuple[FlowDraftVariableSource, ...]
    consumers: set[str] = field(default_factory=set)


class FlowDraftProcessor:
    """执行动作归并、因果关联、变量提取、DAG 和敏感标注。"""

    def build(
        self,
        *,
        recording_id: str,
        flow_id: str,
        events: Sequence[RecordingEvent],
        alternate_identities: Mapping[str, str] | None = None,
        resource_bindings: Mapping[str, tuple[str, str]] | None = None,
        known_secrets: Sequence[str] = (),
    ) -> FlowDraft:
        """把连续、已脱敏事件确定性编译为仍需人工确认的首个 FlowDraft revision。"""

        # --- 阶段：验证事件序列并关联逻辑动作 ---
        ordered = tuple(events)
        alternate_identities = alternate_identities or {}
        resource_bindings = resource_bindings or {}
        if not ordered or tuple(event.sequence for event in ordered) != tuple(
            range(1, len(ordered) + 1)
        ):
            raise JiejianError(
                ErrorCode.RECORD_DRAFT_INVALID,
                "录制事件序号必须从 1 连续递增",
            )
        actions = self._merge_actions(ordered)
        steps = self._correlate_steps(ordered, actions)
        for index, step in enumerate(steps, start=1):
            step.step_id = f"step-{index:06d}"
            if step.request is not None:
                step.path = self._relative_path(step.request.url)
                step.json_body = self._request_json(step.request)

        # --- 阶段：提取变量来源并替换动态值 ---
        sources = self._response_sources(steps)
        variables = self._replace_dynamic_values(steps, sources)
        draft_steps = tuple(
            self._build_step(
                step,
                alternate_identities,
                resource_bindings,
            )
            for step in steps
        )
        draft_variables = tuple(
            FlowDraftVariable(
                name=variable.name,
                placeholder="{" + variable.name + "}",
                status=(
                    FlowDraftVariableStatus.INFERRED
                    if len(variable.candidates) == 1
                    else FlowDraftVariableStatus.UNCONFIRMED
                ),
                candidate_sources=variable.candidates,
                consumer_step_ids=tuple(sorted(variable.consumers)),
            )
            for variable in variables
        )
        # --- 阶段：构造草稿并执行 canonical 安全校验 ---
        draft = FlowDraft(
            schema_version="2",
            recording_id=recording_id,
            flow_id=flow_id,
            revision=1,
            steps=draft_steps,
            variables=draft_variables,
        )
        canonical_flow_draft_json_bytes(draft, known_secrets=known_secrets)
        return draft

    def _merge_actions(
        self,
        events: tuple[RecordingEvent, ...],
    ) -> tuple[_LogicalAction, ...]:
        actions: list[_LogicalAction] = []
        for event in events:
            if event.kind not in _UI_KINDS:
                continue
            previous = actions[-1].events[-1] if actions else None
            if (
                previous is not None
                and previous.kind is RecordingEventKind.UI_INPUT_CHANGE
                and event.kind is RecordingEventKind.UI_INPUT_CHANGE
                and previous.sequence + 1 == event.sequence
                and (
                    previous.identity_id,
                    previous.page_id,
                    previous.frame_id,
                    previous.element_locator,
                )
                == (
                    event.identity_id,
                    event.page_id,
                    event.frame_id,
                    event.element_locator,
                )
            ):
                actions[-1].events.append(event)
            else:
                actions.append(_LogicalAction(events=[event]))
        return tuple(actions)

    def _correlate_steps(
        self,
        events: tuple[RecordingEvent, ...],
        actions: tuple[_LogicalAction, ...],
    ) -> list[_StepData]:
        steps = [
            _StepData(
                first_sequence=action.events[0].sequence,
                identity_id=action.events[0].identity_id,
                actions=list(action.events),
            )
            for action in actions
        ]
        by_action = {
            action_id: step
            for action, step in zip(actions, steps, strict=True)
            for action_id in action.action_ids
        }
        by_request: dict[str, _StepData] = {}
        for event in events:
            if event.kind is RecordingEventKind.REQUEST and event.request_id is not None:
                step = by_action.get(event.caused_by_action_id or "")
                if step is None or step.request is not None:
                    step = _StepData(
                        first_sequence=event.sequence,
                        identity_id=event.identity_id,
                    )
                    steps.append(step)
                step.request = event
                by_request[event.request_id] = step
            elif (
                event.kind is RecordingEventKind.RESPONSE
                and event.request_id in by_request
            ):
                by_request[str(event.request_id)].response = event
        steps.sort(key=lambda item: item.first_sequence)
        return steps

    def _response_sources(self, steps: Sequence[_StepData]) -> tuple[_ValueSource, ...]:
        sources: list[_ValueSource] = []
        for step in steps:
            response = step.response
            if response is None:
                continue
            if response.body:
                try:
                    body = json.loads(response.body)
                except json.JSONDecodeError:
                    body = None
                if body is not None:
                    for path, value in self._walk_scalars(body):
                        if self._candidate_value(value) and not self._path_sensitive(path):
                            sources.append(
                                _ValueSource(
                                    value=value,
                                    source=FlowDraftVariableSource(
                                        source_step_id=step.step_id,
                                        source_event_sequence=response.sequence,
                                        json_path=path,
                                    ),
                                )
                            )
            location = next(
                (
                    header.value
                    for header in response.headers
                    if header.name.casefold() == "location"
                ),
                None,
            )
            if location:
                parsed = urlsplit(location)
                segments = [unquote(part) for part in parsed.path.split("/") if part]
                if segments and self._candidate_value(segments[-1]):
                    sources.append(
                        _ValueSource(
                            value=segments[-1],
                                source=FlowDraftVariableSource(
                                source_step_id=step.step_id,
                                source_event_sequence=response.sequence,
                                json_path="$location.path",
                            ),
                        )
                    )
                for key, value in parse_qsl(parsed.query, keep_blank_values=True):
                    if self._candidate_value(value) and not _SENSITIVE_FIELD.search(key):
                        sources.append(
                            _ValueSource(
                                value=value,
                                source=FlowDraftVariableSource(
                                    source_step_id=step.step_id,
                                    source_event_sequence=response.sequence,
                                    json_path=f"$location.query.{self._safe_name(key)}",
                                ),
                            )
                        )
        return tuple(sources)

    def _replace_dynamic_values(
        self,
        steps: Sequence[_StepData],
        sources: tuple[_ValueSource, ...],
    ) -> tuple[_VariableData, ...]:
        variables: dict[tuple[str, tuple[tuple[str, int, str], ...]], _VariableData] = {}
        used_names: set[str] = set()
        for step in steps:
            if step.request is None:
                continue
            available: dict[str, list[FlowDraftVariableSource]] = {}
            for item in sources:
                if item.source.source_event_sequence < step.request.sequence:
                    key = self._value_key(item.value)
                    available.setdefault(key, []).append(item.source)
            matched: set[str] = set()
            step.path = self._replace_path(step.path or "/", available, matched)
            step.json_body = self._replace_json(step.json_body, available, matched)
            for value_key in sorted(matched):
                candidates = tuple(
                    sorted(
                        available[value_key],
                        key=lambda item: (
                            item.source_event_sequence,
                            item.source_step_id,
                            item.json_path,
                        ),
                    )
                )
                identity = (
                    value_key,
                    tuple(
                        (
                            item.source_step_id,
                            item.source_event_sequence,
                            item.json_path,
                        )
                        for item in candidates
                    ),
                )
                variable = variables.get(identity)
                if variable is None:
                    name = self._variable_name(candidates[0].json_path, used_names)
                    variable = _VariableData(name=name, candidates=candidates)
                    variables[identity] = variable
                    used_names.add(name)
                placeholder = "{" + variable.name + "}"
                candidate_placeholder = self._candidate_placeholder(value_key)
                step.path = step.path.replace(candidate_placeholder, placeholder)
                step.json_body = self._rename_placeholder(
                    step.json_body,
                    candidate_placeholder,
                    placeholder,
                )
                variable.consumers.add(step.step_id)
                if len(candidates) == 1 and candidates[0].source_step_id != step.step_id:
                    step.dependencies.add(candidates[0].source_step_id)
        return tuple(
            sorted(variables.values(), key=lambda variable: variable.name)
        )

    def _build_step(
        self,
        step: _StepData,
        alternate_identities: Mapping[str, str],
        resource_bindings: Mapping[str, tuple[str, str]],
    ) -> FlowDraftStep:
        request = step.request
        resource_pair = (
            resource_bindings.get(request.request_id)
            if request is not None and request.request_id is not None
            else None
        )
        alternate = alternate_identities.get(step.identity_id)
        confirmed = request is not None and alternate is not None and resource_pair is not None
        sequences = [event.sequence for event in step.actions]
        if request is not None:
            sequences.append(request.sequence)
        if step.response is not None:
            sequences.append(step.response.sequence)
        return FlowDraftStep(
            id=step.step_id,
            name=self._step_name(step),
            identity_id=step.identity_id,
            alternate_identity_id=alternate,
            resource_id=resource_pair[0] if resource_pair else None,
            alternate_resource_id=resource_pair[1] if resource_pair else None,
            bindings_confirmed=confirmed,
            method=request.method if request is not None else None,
            path=step.path,
            json_body=step.json_body,
            expected_statuses=(
                (step.response.status_code or 200,)
                if request is not None and step.response is not None
                else (200,)
                if request is not None
                else ()
            ),
            request_id=request.request_id if request is not None else None,
            action_ids=tuple(
                event.action_id for event in step.actions if event.action_id is not None
            ),
            source_event_sequences=tuple(sorted(sequences)),
            depends_on_step_ids=tuple(sorted(step.dependencies)),
            sensitive_fields=self._sensitive_fields(step),
        )

    @staticmethod
    def _relative_path(url: str | None) -> str:
        if not url:
            raise JiejianError(ErrorCode.RECORD_DRAFT_INVALID, "请求事件缺少 URL")
        parsed = urlsplit(url)
        return parsed.path + (f"?{parsed.query}" if parsed.query else "")

    @staticmethod
    def _request_json(event: RecordingEvent) -> dict[str, Any]:
        if event.method not in _HTTP_METHODS:
            raise JiejianError(ErrorCode.RECORD_DRAFT_INVALID, "请求方法无法编译为 Flow")
        if not event.body:
            return {}
        try:
            value = json.loads(event.body)
        except json.JSONDecodeError:
            return {}
        return value if isinstance(value, dict) else {}

    def _replace_path(
        self,
        path: str,
        available: Mapping[str, list[FlowDraftVariableSource]],
        matched: set[str],
    ) -> str:
        parsed = urlsplit(path)
        segments = []
        for segment in parsed.path.split("/"):
            key = self._value_key(unquote(segment))
            if segment and key in available:
                segments.append(self._candidate_placeholder(key))
                matched.add(key)
            else:
                segments.append(segment)
        query = []
        for name, value in parse_qsl(parsed.query, keep_blank_values=True):
            key = self._value_key(value)
            if key in available and not _SENSITIVE_FIELD.search(name):
                query.append((name, self._candidate_placeholder(key)))
                matched.add(key)
            else:
                query.append((name, value))
        encoded_query = urlencode(query, safe="{}")
        return "/".join(segments) + (f"?{encoded_query}" if encoded_query else "")

    def _replace_json(
        self,
        value: Any,
        available: Mapping[str, list[FlowDraftVariableSource]],
        matched: set[str],
        *,
        parent_key: str = "",
    ) -> Any:
        if isinstance(value, Mapping):
            return {
                key: self._replace_json(
                    item,
                    available,
                    matched,
                    parent_key=str(key),
                )
                for key, item in value.items()
            }
        if isinstance(value, list):
            return [
                self._replace_json(item, available, matched, parent_key=parent_key)
                for item in value
            ]
        key = self._value_key(value) if isinstance(value, (str, int)) else ""
        if key in available and not _SENSITIVE_FIELD.search(parent_key):
            matched.add(key)
            return self._candidate_placeholder(key)
        return value

    def _walk_scalars(self, value: Any, path: str = "$") -> list[tuple[str, Any]]:
        found: list[tuple[str, Any]] = []
        if isinstance(value, Mapping):
            for key in sorted(value, key=str):
                found.extend(self._walk_scalars(value[key], f"{path}.{self._safe_name(str(key))}"))
        elif isinstance(value, list):
            for index, item in enumerate(value):
                found.extend(self._walk_scalars(item, f"{path}[{index}]"))
        elif isinstance(value, (str, int)) and not isinstance(value, bool):
            found.append((path, value))
        return found

    @staticmethod
    def _candidate_value(value: Any) -> bool:
        return (
            isinstance(value, str)
            and value != REDACTED
            and 3 <= len(value) <= 256
        ) or (isinstance(value, int) and not isinstance(value, bool) and value >= 2)

    @staticmethod
    def _path_sensitive(path: str) -> bool:
        return any(_SENSITIVE_FIELD.search(part) for part in path.split("."))

    @staticmethod
    def _value_key(value: Any) -> str:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))

    @staticmethod
    def _candidate_placeholder(value_key: str) -> str:
        digest = hashlib.sha256(value_key.encode("utf-8")).hexdigest()[:16]
        return "{candidate-" + digest + "}"

    @staticmethod
    def _safe_name(value: str) -> str:
        normalized = re.sub(r"[^a-z0-9_-]+", "_", value.casefold()).strip("_-")
        if not normalized or not normalized[0].isalpha():
            return "value"
        return normalized[:64]

    def _variable_name(
        self,
        json_path: str,
        used_names: set[str],
    ) -> str:
        tail = re.split(r"[.\[\]]+", json_path)[-1] or "resource_id"
        base = self._safe_name(tail)
        if base == "id" or json_path.startswith("$location"):
            base = "resource_id"
        name = base
        suffix = 2
        while name in used_names:
            name = f"{base[:58]}-{suffix}"
            suffix += 1
        return name

    def _rename_placeholder(self, value: Any, source: str, target: str) -> Any:
        if isinstance(value, Mapping):
            return {
                key: self._rename_placeholder(item, source, target)
                for key, item in value.items()
            }
        if isinstance(value, list):
            return [self._rename_placeholder(item, source, target) for item in value]
        return target if value == source else value

    def _sensitive_fields(self, step: _StepData) -> tuple[str, ...]:
        fields: set[str] = set()
        for event in step.actions:
            if event.field_name and _SENSITIVE_FIELD.search(event.field_name):
                fields.add(f"ui.{event.field_name}")
            if event.input_type and _SENSITIVE_FIELD.search(event.input_type):
                fields.add(f"ui.{event.input_type}")
        if step.request is not None:
            fields.update(
                f"headers.{header.name}"
                for header in step.request.headers
                if _SENSITIVE_FIELD.search(header.name)
            )
            self._collect_sensitive_json(step.json_body, "$", fields)
        return tuple(sorted(fields))

    def _collect_sensitive_json(
        self,
        value: Any,
        path: str,
        fields: set[str],
    ) -> None:
        if isinstance(value, Mapping):
            for key, item in value.items():
                child = f"{path}.{key}"
                if _SENSITIVE_FIELD.search(str(key)):
                    fields.add(child)
                self._collect_sensitive_json(item, child, fields)
        elif isinstance(value, list):
            for index, item in enumerate(value):
                self._collect_sensitive_json(item, f"{path}[{index}]", fields)

    @staticmethod
    def _step_name(step: _StepData) -> str:
        if step.request is not None:
            return f"{step.request.method} request"
        if step.actions:
            labels = {
                RecordingEventKind.UI_CLICK: "click",
                RecordingEventKind.UI_INPUT_CHANGE: "input change",
                RecordingEventKind.UI_SUBMIT: "submit",
            }
            return labels[step.actions[-1].kind]
        return "recorded step"
