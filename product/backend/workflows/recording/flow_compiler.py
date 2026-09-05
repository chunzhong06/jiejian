# =============================================================================
# Recording Flow 编译
#
# 定位
#   已确认 FlowDraft 到可执行 Flow 的结构化编译边界
#
# 职责
#   编译完整 Flow｜投影已确认资源与变量
#
# 边界
#   不修改传入草稿、不执行 Flow，也不编译未确认值或具体差分身份/资源。
#
# 调用链
#   RecordingLifecycle → FlowDraftCompiler → SecuritySetupCompiler
# =============================================================================

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any
from urllib.parse import parse_qsl, urlsplit

from pydantic import ValidationError

from product.backend.core.errors import ErrorCode, JiejianError
from product.protocols.recording_flow import Flow, FlowStep, FlowVariableSource
from product.protocols.flow_draft import FlowDraft, FlowDraftResourceCandidate, FlowDraftVariableStatus
from product.protocols.web.workflow import (
    EmptyBody,
    HttpOutcomeClassifier,
    HttpParameter,
    HttpPredicate,
    HttpPredicateKind,
    HttpRequestTemplate,
    JsonBody,
    ResponseExtractor,
    ResponseExtractorKind,
    ValueSlot,
    ValueSlotConsumer,
    ValueSlotSource,
    WorkflowStepPurpose,
)

_SENSITIVE_FIELD = re.compile(
    r"(?:authorization|cookie|credential|password|passwd|secret|token|api[_-]?key)",
    re.IGNORECASE,
)


class FlowDraftCompiler:
    """只编译已确认草稿，并生成最终的 Web 执行绑定。"""

    def compile(self, draft: FlowDraft) -> Flow:
        """仅将已确认目标、资源位置、变量和无环步骤编译为动作 Flow。"""

        # --- 阶段：拒绝未完成审阅或敏感输入 ---
        if any(step.method is None for step in draft.steps):
            raise JiejianError(
                ErrorCode.RECORD_DRAFT_COMPILE,
                "Flow 草稿仍包含未归并的 UI 动作",
            )
        if draft.target_step_id is None:
            raise JiejianError(
                ErrorCode.RECORD_DRAFT_UNCONFIRMED,
                "Flow 草稿的目标请求尚未确认",
            )
        if draft.resource_candidate_id is None:
            raise JiejianError(
                ErrorCode.RECORD_DRAFT_UNCONFIRMED,
                "Flow 草稿的业务资源位置尚未确认",
            )
        if any(
            variable.status is not FlowDraftVariableStatus.CONFIRMED
            for variable in draft.variables
        ):
            raise JiejianError(
                ErrorCode.RECORD_DRAFT_UNCONFIRMED,
                "Flow 草稿的变量来源尚未确认",
            )
        step_map = {step.id: step for step in draft.steps}
        graph = {step.id: set(step.depends_on_step_ids) for step in draft.steps}
        ancestors: set[str] = set()
        pending = list(graph[draft.target_step_id])
        while pending:
            current = pending.pop()
            if current in ancestors:
                continue
            ancestors.add(current)
            pending.extend(graph[current])
        retained_step_ids = ancestors | {draft.target_step_id}

        # 目标后的观察步骤不会进入可执行 Flow，其变量需求也不能反向污染目标响应提取器。
        sources_by_consumer: dict[str, list[FlowVariableSource]] = {}
        for variable in draft.variables:
            source = variable.confirmed_source
            if source is None:
                raise JiejianError(
                    ErrorCode.RECORD_DRAFT_UNCONFIRMED,
                    "Flow 草稿的变量来源尚未确认",
                )
            for consumer in variable.consumer_step_ids:
                if consumer not in retained_step_ids:
                    continue
                consumer_step = step_map[consumer]
                placeholder = "{" + variable.name + "}"
                parsed_path = urlsplit(consumer_step.path or "/")
                if placeholder in parsed_path.path:
                    consumer_kind = ValueSlotConsumer.PATH
                elif any(
                    value == placeholder
                    for _, value in parse_qsl(
                        parsed_path.query,
                        keep_blank_values=True,
                    )
                ):
                    consumer_kind = ValueSlotConsumer.QUERY
                else:
                    consumer_kind = ValueSlotConsumer.JSON_BODY
                sources_by_consumer.setdefault(consumer, []).append(
                    FlowVariableSource(
                        name=variable.name,
                        source_step_id=source.source_step_id,
                        source_event_sequence=source.source_event_sequence,
                        json_path=source.json_path,
                        consumer=consumer_kind,
                    )
                )
        extractors_by_producer: dict[str, list[ResponseExtractor]] = {}
        for sources in sources_by_consumer.values():
            for source in sources:
                kind = ResponseExtractorKind.LOCATION if source.json_path.startswith("$location") else ResponseExtractorKind.JSON_PATH
                extractor = ResponseExtractor(
                    extractor_id=source.name,
                    kind=kind,
                    json_path=None if kind is ResponseExtractorKind.LOCATION else source.json_path,
                    max_length=source.max_length,
                    secret=source.secret,
                )
                existing = {item.extractor_id for item in extractors_by_producer.setdefault(source.source_step_id, [])}
                if extractor.extractor_id not in existing:
                    extractors_by_producer[source.source_step_id].append(extractor)

        def slot_json(value: Any, slot_ids: set[str]) -> Any:
            if isinstance(value, Mapping):
                return {key: slot_json(item, slot_ids) for key, item in value.items()}
            if isinstance(value, list):
                return [slot_json(item, slot_ids) for item in value]
            if isinstance(value, str) and value.startswith("{") and value.endswith("}") and value[1:-1] in slot_ids:
                return {"$slot": value[1:-1]}
            return value
        # --- 阶段：投影已确认步骤并验证最终 Flow ---
        try:
            target = step_map[draft.target_step_id]
            resource = next(
                item
                for item in target.resource_candidates
                if item.candidate_id == draft.resource_candidate_id
            )
            steps: list[FlowStep] = []
            for step in draft.steps:
                if step.id not in ancestors and step.id != draft.target_step_id:
                    continue
                sources = tuple(sorted(sources_by_consumer.get(step.id, ()), key=lambda item: item.name))
                slots = list(
                    ValueSlot(
                        slot_id=source.name,
                        source=ValueSlotSource.PRIOR_STEP_LOCATION if source.json_path.startswith("$location") else ValueSlotSource.PRIOR_STEP_JSON_PATH,
                        consumer=source.consumer,
                        value_type=source.value_type,
                        max_length=source.max_length,
                        secret=source.secret,
                        source_path=source.json_path,
                        producer_step_id=source.source_step_id,
                        consumer_step_id=step.id,
                    )
                    for source in sources
                )
                parsed = urlsplit(step.path or "/")
                compiled_path = parsed.path
                query_items = list(parse_qsl(parsed.query, keep_blank_values=True))
                compiled_json = self._drop_sensitive_json(step.json_body)
                if step.id == draft.target_step_id:
                    compiled_path, query_items, compiled_json = self._bind_case_resource(
                        compiled_path,
                        query_items,
                        compiled_json,
                        resource,
                    )
                    slots.append(
                        ValueSlot(
                            slot_id="case_resource_id",
                            source=ValueSlotSource.CASE_RESOURCE_ID,
                            consumer=resource.consumer,
                            consumer_step_id=step.id,
                        )
                    )
                slot_ids = {item.slot_id for item in slots}
                query = tuple(
                    HttpParameter(
                        name=name,
                        slot_id=(
                            value[1:-1]
                            if value.startswith("{")
                            and value.endswith("}")
                            and value[1:-1] in slot_ids
                            else None
                        ),
                        literal=(
                            None
                            if value.startswith("{")
                            and value.endswith("}")
                            and value[1:-1] in slot_ids
                            else value
                        ),
                    )
                    for name, value in query_items
                    if value
                )
                request_template = HttpRequestTemplate(
                    method=step.method,
                    path=compiled_path,
                    query=query,
                    body=JsonBody(value=slot_json(compiled_json, slot_ids)) if compiled_json else EmptyBody(),
                    input_slots=tuple(slots),
                    response_extractors=tuple(sorted(extractors_by_producer.get(step.id, ()), key=lambda item: item.extractor_id)),
                )
                steps.append(FlowStep(
                    id=step.id,
                    name=step.name,
                    purpose=(
                        WorkflowStepPurpose.TARGET
                        if step.id == draft.target_step_id
                        else WorkflowStepPurpose.SETUP
                    ),
                    request_template=request_template,
                    classifier=HttpOutcomeClassifier(accepted=(HttpPredicate(kind=HttpPredicateKind.STATUS_IN, statuses=step.expected_statuses),)),
                    depends_on_step_ids=step.depends_on_step_ids,
                    variable_sources=sources,
                    sensitive_fields=step.sensitive_fields,
                ))
            return Flow(
                schema_version="2",
                id=draft.flow_id,
                business_action_id=draft.business_action_id,
                action_revision=draft.action_revision,
                test_identity_id=draft.test_identity_id,
                target_step_id=draft.target_step_id,
                steps=tuple(steps),
            )
        except ValidationError:
            raise JiejianError(
                ErrorCode.RECORD_DRAFT_COMPILE,
                "Flow 草稿无法编译为可执行 Flow",
            ) from None

    @classmethod
    def _bind_case_resource(
        cls,
        path: str,
        query: list[tuple[str, str]],
        json_body: Any,
        candidate: FlowDraftResourceCandidate,
    ) -> tuple[str, list[tuple[str, str]], Any]:
        placeholder = "{case_resource_id}"
        if candidate.consumer is ValueSlotConsumer.PATH:
            index = int(candidate.location.removeprefix("path[").removesuffix("]"))
            parts = path.split("/")
            positions = [position for position, value in enumerate(parts) if value]
            if index >= len(positions):
                raise JiejianError(ErrorCode.RECORD_DRAFT_COMPILE, "业务资源路径位置已失效")
            parts[positions[index]] = placeholder
            return "/".join(parts), query, json_body
        if candidate.consumer is ValueSlotConsumer.QUERY:
            name = candidate.location.removeprefix("query.")
            updated = [
                (key, placeholder if key == name else value)
                for key, value in query
            ]
            if updated == query:
                raise JiejianError(ErrorCode.RECORD_DRAFT_COMPILE, "业务资源查询位置已失效")
            return path, updated, json_body
        return path, query, cls._replace_json_location(
            json_body,
            candidate.location,
            {"$slot": "case_resource_id"},
        )

    @staticmethod
    def _replace_json_location(value: Any, path: str, replacement: Any) -> Any:
        tokens = re.findall(r"\.([A-Za-z_][A-Za-z0-9_-]*)|\[([0-9]+)\]", path)
        if not tokens:
            raise JiejianError(ErrorCode.RECORD_DRAFT_COMPILE, "业务资源正文位置已失效")
        clone = value
        current = clone
        for index, (field, offset) in enumerate(tokens):
            key: str | int = field if field else int(offset)
            final = index == len(tokens) - 1
            try:
                if final:
                    current[key] = replacement
                else:
                    current = current[key]
            except (KeyError, IndexError, TypeError):
                raise JiejianError(
                    ErrorCode.RECORD_DRAFT_COMPILE,
                    "业务资源正文位置已失效",
                ) from None
        return clone

    @staticmethod
    def _drop_sensitive_json(value: Any) -> Any:
        if isinstance(value, Mapping):
            return {
                key: FlowDraftCompiler._drop_sensitive_json(item)
                for key, item in value.items()
                if not _SENSITIVE_FIELD.search(str(key))
            }
        if isinstance(value, list):
            return [FlowDraftCompiler._drop_sensitive_json(item) for item in value]
        return value
