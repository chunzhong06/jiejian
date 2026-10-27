# 从已脱敏事件确定性编排动作关联、变量和待审录制草稿。
from __future__ import annotations
import json
from collections.abc import Sequence
from urllib.parse import parse_qsl, unquote, urlsplit
from product.backend.domain.errors import ErrorCode, JiejianError
from product.backend.domain.recording.models import RecordingPurpose
from product.protocols.recording.flow_draft import FlowDraft, FlowDraftStep, FlowDraftVariable, FlowDraftVariableSource, FlowDraftVariableStatus, canonical_flow_draft_json_bytes
from product.protocols.recording.events import RecordingEventKind, RecordingEvent
from product.protocols.web.workflow import ValueSlotConsumer
from .draft_models import _LogicalAction, _StepData, _ValueSource, _VariableData
from .draft_values import _OPAQUE_BUSINESS_VALUE, _SENSITIVE_FIELD, _candidate_placeholder, _candidate_value, _path_sensitive, _relative_path, _rename_placeholder, _replace_json, _replace_path, _request_json, _safe_name, _sensitive_fields, _step_name, _value_key, _variable_name, _walk_scalars
from .draft_resources import _automatic_target, _confirmed_path_positions, _recommend_target, _resource_candidates
_UI_KINDS = {RecordingEventKind.UI_CLICK, RecordingEventKind.UI_INPUT_CHANGE, RecordingEventKind.UI_SUBMIT}

class FlowDraftProcessor:
    """执行动作归并、因果关联、变量提取、DAG 和敏感标注。"""

    def build(self, *, recording_id: str, flow_id: str, business_action_id: str, action_revision: int, subject_test_identity_id: str, resource_owner_test_identity_id: str, events: Sequence[RecordingEvent], purpose: RecordingPurpose=RecordingPurpose.TARGET, parent_recording_id: str | None=None, effect_id: str | None=None, known_secrets: Sequence[str]=(), action_path_templates: Sequence[str]=(), allow_created_resources: bool=False) -> FlowDraft:
        """把连续、已脱敏事件确定性整理为只保留业务歧义的首个 revision。"""
        ordered = tuple(events)
        if not ordered or tuple((event.sequence for event in ordered)) != tuple(range(1, len(ordered) + 1)):
            raise JiejianError(ErrorCode.RECORD_DRAFT_INVALID, '录制事件序号必须从 1 连续递增')
        actions = self._merge_actions(ordered)
        steps = self._correlate_steps(ordered, actions)
        for index, step in enumerate(steps, start=1):
            step.step_id = f'step-{index:06d}'
            if step.request is not None:
                step.path = _relative_path(step.request.url)
                step.json_body = _request_json(step.request)
        sources = self._response_sources(steps)
        variables = self._replace_dynamic_values(steps, sources)
        draft_steps = tuple((self._build_step(step, action_path_templates, allow_created_resources) for step in steps))
        directly_triggered_requests = frozenset((event.request_id for event in ordered if event.kind is RecordingEventKind.REQUEST and event.request_id is not None and (event.caused_by_action_id is not None)))
        draft_variables = tuple((FlowDraftVariable(name=variable.name, placeholder='{' + variable.name + '}', status=FlowDraftVariableStatus.CONFIRMED if len(variable.candidates) == 1 else FlowDraftVariableStatus.UNCONFIRMED, candidate_sources=variable.candidates, confirmed_source=variable.candidates[0] if len(variable.candidates) == 1 else None, consumer_step_ids=tuple(sorted(variable.consumers))) for variable in variables))
        recommended_target = _recommend_target(draft_steps, directly_triggered_requests)
        target_step_id = _automatic_target(draft_steps, directly_triggered_requests)
        if purpose is not RecordingPurpose.TARGET:
            target_step_id = None
        target = next((step for step in draft_steps if step.id == target_step_id), None)
        resource_candidate_id = target.resource_candidates[0].candidate_id if target is not None and len(target.resource_candidates) == 1 else None
        if target is not None and any((str(item.consumer).startswith('RESPONSE_') for item in target.resource_candidates)):
            resource_candidate_id = None
        if resource_candidate_id and target.resource_candidates[0].consumer is ValueSlotConsumer.PATH:
            candidate = target.resource_candidates[0]
            source_step = next((step for step in steps if step.step_id == target.id))
            positions = _confirmed_path_positions(source_step, action_path_templates)
            index = int(candidate.location[5:-1])
            raw_parts = [unquote(part) for part in urlsplit(source_step.request.url).path.split('/') if part]
            if positions is None and (not _OPAQUE_BUSINESS_VALUE.fullmatch(raw_parts[index])):
                resource_candidate_id = None
        draft = FlowDraft(recording_id=recording_id, flow_id=flow_id, business_action_id=business_action_id, action_revision=action_revision, subject_test_identity_id=subject_test_identity_id, resource_owner_test_identity_id=resource_owner_test_identity_id, purpose=purpose, parent_recording_id=parent_recording_id, effect_id=effect_id, revision=1, steps=draft_steps, variables=draft_variables, recommended_target_step_id=recommended_target, target_step_id=target_step_id, resource_candidate_id=resource_candidate_id)
        canonical_flow_draft_json_bytes(draft, known_secrets=known_secrets)
        return draft

    def _merge_actions(self, events: tuple[RecordingEvent, ...]) -> tuple[_LogicalAction, ...]:
        actions: list[_LogicalAction] = []
        for event in events:
            if event.kind not in _UI_KINDS:
                continue
            previous = actions[-1].events[-1] if actions else None
            if previous is not None and previous.kind is RecordingEventKind.UI_INPUT_CHANGE and (event.kind is RecordingEventKind.UI_INPUT_CHANGE) and (previous.sequence + 1 == event.sequence) and ((previous.identity_id, previous.page_id, previous.frame_id, previous.element_locator) == (event.identity_id, event.page_id, event.frame_id, event.element_locator)):
                actions[-1].events.append(event)
            else:
                actions.append(_LogicalAction(events=[event]))
        return tuple(actions)

    def _correlate_steps(self, events: tuple[RecordingEvent, ...], actions: tuple[_LogicalAction, ...]) -> list[_StepData]:
        steps = [_StepData(first_sequence=action.events[0].sequence, identity_id=action.events[0].identity_id, actions=list(action.events)) for action in actions]
        by_action = {action_id: step for action, step in zip(actions, steps, strict=True) for action_id in action.action_ids}
        by_request: dict[str, _StepData] = {}
        for event in events:
            if event.kind is RecordingEventKind.REQUEST and event.request_id is not None:
                step = by_action.get(event.caused_by_action_id or '')
                if step is None or step.request is not None:
                    step = _StepData(first_sequence=event.sequence, identity_id=event.identity_id)
                    steps.append(step)
                step.request = event
                by_request[event.request_id] = step
            elif event.kind is RecordingEventKind.RESPONSE and event.request_id in by_request:
                by_request[str(event.request_id)].response = event
        network = [step for step in steps if step.request is not None]
        if not network:
            raise JiejianError(ErrorCode.RECORD_DRAFT_INVALID, '本次演示没有形成可执行的业务请求，请重新演示')
        for ui_only in (step for step in steps if step.request is None):
            distances = tuple((abs(item.first_sequence - ui_only.first_sequence) for item in network))
            nearest_distance = min(distances)
            nearest = [item for item, distance in zip(network, distances, strict=True) if distance == nearest_distance]
            if len(nearest) != 1:
                raise JiejianError(ErrorCode.RECORD_DRAFT_INVALID, '演示中的界面操作无法唯一归属业务请求，请减少无关操作后重新演示')
            nearest[0].actions.extend(ui_only.actions)
            nearest[0].first_sequence = min(nearest[0].first_sequence, ui_only.first_sequence)
        network.sort(key=lambda item: item.first_sequence)
        return network

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
                    for path, value in _walk_scalars(body):
                        if _candidate_value(value) and (not _path_sensitive(path)):
                            sources.append(_ValueSource(value=value, source=FlowDraftVariableSource(source_step_id=step.step_id, source_event_sequence=response.sequence, json_path=path)))
            location = next((header.value for header in response.headers if header.name.casefold() == 'location'), None)
            if location:
                parsed = urlsplit(location)
                segments = [unquote(part) for part in parsed.path.split('/') if part]
                if segments and _candidate_value(segments[-1]):
                    sources.append(_ValueSource(value=segments[-1], source=FlowDraftVariableSource(source_step_id=step.step_id, source_event_sequence=response.sequence, json_path='$location.path')))
                for key, value in parse_qsl(parsed.query, keep_blank_values=True):
                    if _candidate_value(value) and (not _SENSITIVE_FIELD.search(key)):
                        sources.append(_ValueSource(value=value, source=FlowDraftVariableSource(source_step_id=step.step_id, source_event_sequence=response.sequence, json_path=f'$location.query.{_safe_name(key)}')))
        return tuple(sources)

    def _replace_dynamic_values(self, steps: Sequence[_StepData], sources: tuple[_ValueSource, ...]) -> tuple[_VariableData, ...]:
        variables: dict[tuple[str, tuple[tuple[str, int, str], ...]], _VariableData] = {}
        used_names: set[str] = set()
        for step in steps:
            if step.request is None:
                continue
            available: dict[str, list[FlowDraftVariableSource]] = {}
            for item in sources:
                if item.source.source_event_sequence < step.request.sequence:
                    key = _value_key(item.value)
                    available.setdefault(key, []).append(item.source)
            matched: set[str] = set()
            step.path = _replace_path(step.path or '/', available, matched)
            step.json_body = _replace_json(step.json_body, available, matched)
            for value_key in sorted(matched):
                candidates = tuple(sorted(available[value_key], key=lambda item: (item.source_event_sequence, item.source_step_id, item.json_path)))
                identity = (value_key, tuple(((item.source_step_id, item.source_event_sequence, item.json_path) for item in candidates)))
                variable = variables.get(identity)
                if variable is None:
                    name = _variable_name(candidates[0].json_path, used_names)
                    variable = _VariableData(name=name, candidates=candidates)
                    variables[identity] = variable
                    used_names.add(name)
                placeholder = '{' + variable.name + '}'
                candidate_placeholder = _candidate_placeholder(value_key)
                step.path = step.path.replace(candidate_placeholder, placeholder)
                step.json_body = _rename_placeholder(step.json_body, candidate_placeholder, placeholder)
                variable.consumers.add(step.step_id)
                if len(candidates) == 1 and candidates[0].source_step_id != step.step_id:
                    step.dependencies.add(candidates[0].source_step_id)
        return tuple(sorted(variables.values(), key=lambda variable: variable.name))

    def _build_step(self, step: _StepData, action_path_templates: Sequence[str]=(), allow_created_resources: bool=False) -> FlowDraftStep:
        request = step.request
        sequences = [event.sequence for event in step.actions]
        if request is not None:
            sequences.append(request.sequence)
        if step.response is not None:
            sequences.append(step.response.sequence)
        return FlowDraftStep(id=step.step_id, name=_step_name(step), method=request.method if request is not None else None, path=step.path, json_body=step.json_body, expected_statuses=(step.response.status_code or 200,) if request is not None and step.response is not None else (200,) if request is not None else (), request_id=request.request_id if request is not None else None, source_event_sequences=tuple(sorted(sequences)), depends_on_step_ids=tuple(sorted(step.dependencies)), sensitive_fields=_sensitive_fields(step), resource_candidates=_resource_candidates(step, action_path_templates, allow_created_resources))
