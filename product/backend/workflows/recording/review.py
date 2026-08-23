# =============================================================================
# Recording FlowDraft 审阅
#
# 定位
#   不可信 FlowDraft 与人工确认的可执行 Flow 之间的信任转换边界
#
# 职责
#   应用版本化审阅命令｜保持草稿不可变历史｜校验绑定后编译 Flow
#
# 边界
#   不修改传入草稿、不执行 Flow，也不把未确认变量或敏感字段编译为可执行值。
#
# 调用链
#   RecordingLifecycle → FlowDraftReviewer → FlowDraft revision / recording_flow.Flow
# =============================================================================

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from pydantic import ValidationError

from product.protocols.recording_flow import Flow, FlowStep, FlowVariableSource
from product.backend.core.errors import ErrorCode, JiejianError
from product.protocols.flow_draft import ConfirmFlowDraftVariable, DeleteFlowDraftStep, FlowDraftReviewCommand, FlowDraftStep, FlowDraft, FlowDraftVariableSource, FlowDraftVariableStatus, FlowDraftVariable, MergeFlowDraftSteps, RenameFlowDraftStep
from product.protocols.web.profile import WebExecutionProfile
from product.protocols.web.target import WebTargetDefinition
from product.protocols.web.workflow import CASE_SUBJECT_IDENTITY, EmptyBody, HttpOutcomeClassifier, HttpPredicate, HttpPredicateKind, HttpRequestTemplate, HttpWorkflowBinding, HttpWorkflowStep, JsonBody, ResponseExtractor, ResponseExtractorKind, ValueSlot, ValueSlotConsumer, ValueSlotSource, WorkflowStepPurpose

_SENSITIVE_FIELD = re.compile(
    r"(?:authorization|cookie|credential|password|passwd|secret|token|api[_-]?key)",
    re.IGNORECASE,
)


class FlowDraftReviewer:
    """每次审阅都返回新 revision，不修改传入草稿。"""

    def apply(
        self,
        draft: FlowDraft,
        command: FlowDraftReviewCommand,
    ) -> FlowDraft:
        """在 expected revision 上应用一条审阅命令，并返回新的不可变 revision。"""

        if isinstance(command, DeleteFlowDraftStep):
            steps, variables = self._delete_step(draft, command.step_id)
        elif isinstance(command, MergeFlowDraftSteps):
            steps, variables = self._merge_steps(
                draft,
            command.left_step_id,
            command.right_step_id,
        )
        elif isinstance(command, RenameFlowDraftStep):
            steps, variables = self._rename_step(draft, command.step_id, command.name)
        elif isinstance(command, ConfirmFlowDraftVariable):
            steps, variables = self._confirm_variable(draft, command)
        else:
            raise TypeError("unsupported Flow draft review command")
        self._ensure_acyclic(steps)
        return self._new_revision(draft, steps, variables)

    def compile(self, draft: FlowDraft) -> Flow:
        """仅将已确认变量、绑定和无环步骤编译为可执行 Flow。"""

        # --- 阶段：拒绝未完成审阅或敏感输入 ---
        if any(step.method is None for step in draft.steps):
            raise JiejianError(
                ErrorCode.RECORD_DRAFT_COMPILE,
                "Flow 草稿仍包含未归并的 UI 动作",
            )
        if any(not step.bindings_confirmed for step in draft.steps):
            raise JiejianError(
                ErrorCode.RECORD_DRAFT_UNCONFIRMED,
                "Flow 草稿的身份或资源映射尚未确认",
            )
        if any(
            variable.status is not FlowDraftVariableStatus.CONFIRMED
            for variable in draft.variables
        ):
            raise JiejianError(
                ErrorCode.RECORD_DRAFT_UNCONFIRMED,
                "Flow 草稿的变量来源尚未确认",
            )
        sources_by_consumer: dict[str, list[FlowVariableSource]] = {}
        for variable in draft.variables:
            source = variable.confirmed_source
            if source is None:
                raise JiejianError(
                    ErrorCode.RECORD_DRAFT_UNCONFIRMED,
                    "Flow 草稿的变量来源尚未确认",
                )
            step_map = {step.id: step for step in draft.steps}
            for consumer in variable.consumer_step_ids:
                consumer_step = step_map[consumer]
                placeholder = "{" + variable.name + "}"
                sources_by_consumer.setdefault(consumer, []).append(
                    FlowVariableSource(
                        name=variable.name,
                        source_step_id=source.source_step_id,
                        source_event_sequence=source.source_event_sequence,
                        json_path=source.json_path,
                        consumer=(ValueSlotConsumer.PATH if placeholder in (consumer_step.path or "") else ValueSlotConsumer.JSON_BODY),
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
            steps: list[FlowStep] = []
            for step in draft.steps:
                sources = tuple(sorted(sources_by_consumer.get(step.id, ()), key=lambda item: item.name))
                slots = tuple(
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
                request_template = HttpRequestTemplate(
                    method=step.method,
                    path=step.path,
                    body=JsonBody(value=slot_json(self._drop_sensitive_json(step.json_body), {item.slot_id for item in slots})) if step.json_body else EmptyBody(),
                    input_slots=slots,
                    response_extractors=tuple(sorted(extractors_by_producer.get(step.id, ()), key=lambda item: item.extractor_id)),
                )
                steps.append(FlowStep(
                    id=step.id,
                    name=step.name,
                    identity_id=step.identity_id,
                    resource_id=step.resource_id,
                    alternate_identity_id=step.alternate_identity_id,
                    alternate_resource_id=step.alternate_resource_id,
                    request_template=request_template,
                    classifier=HttpOutcomeClassifier(accepted=(HttpPredicate(kind=HttpPredicateKind.STATUS_IN, statuses=step.expected_statuses),)),
                    depends_on_step_ids=step.depends_on_step_ids,
                    variable_sources=sources,
                    sensitive_fields=step.sensitive_fields,
                ))
            return Flow(
                schema_version="4",
                id=draft.flow_id,
                steps=tuple(steps),
                owner_observer_path=draft.owner_observer_path,
                reset_path=draft.reset_path,
            )
        except ValidationError:
            raise JiejianError(
                ErrorCode.RECORD_DRAFT_COMPILE,
                "Flow 草稿无法编译为可执行 Flow",
            ) from None

    def _delete_step(
        self,
        draft: FlowDraft,
        step_id: str,
    ) -> tuple[tuple[FlowDraftStep, ...], tuple[FlowDraftVariable, ...]]:
        if step_id not in {step.id for step in draft.steps}:
            raise JiejianError(ErrorCode.RECORD_DRAFT_REFERENCE, "Flow 草稿步骤引用不存在")
        if len(draft.steps) == 1:
            raise JiejianError(ErrorCode.RECORD_DRAFT_REFERENCE, "Flow 草稿不得删除最后一步")
        if any(step_id in step.depends_on_step_ids for step in draft.steps) or any(
            step_id in variable.consumer_step_ids
            or any(source.source_step_id == step_id for source in variable.candidate_sources)
            for variable in draft.variables
        ):
            raise JiejianError(
                ErrorCode.RECORD_DRAFT_REFERENCE,
                "Flow 草稿步骤仍被依赖或变量引用",
            )
        return (
            tuple(step for step in draft.steps if step.id != step_id),
            draft.variables,
        )

    def _merge_steps(
        self,
        draft: FlowDraft,
        left_id: str,
        right_id: str,
    ) -> tuple[tuple[FlowDraftStep, ...], tuple[FlowDraftVariable, ...]]:
        positions = {step.id: index for index, step in enumerate(draft.steps)}
        if left_id not in positions or right_id not in positions:
            raise JiejianError(ErrorCode.RECORD_DRAFT_REFERENCE, "Flow 草稿步骤引用不存在")
        left_index = positions[left_id]
        right_index = positions[right_id]
        if right_index != left_index + 1:
            raise JiejianError(
                ErrorCode.RECORD_DRAFT_NOT_ADJACENT,
                "Flow 草稿只允许合并相邻步骤",
            )
        left = draft.steps[left_index]
        right = draft.steps[right_index]
        if left.identity_id != right.identity_id or (
            left.method is not None and right.method is not None
        ):
            raise JiejianError(
                ErrorCode.RECORD_DRAFT_MERGE,
                "Flow 草稿步骤的身份或请求边界不能合并",
            )
        network = right if right.method is not None else left
        dependencies = {
            right_id if dependency == left_id else dependency
            for dependency in (*left.depends_on_step_ids, *right.depends_on_step_ids)
            if dependency not in {left_id, right_id}
        }
        merged = network.model_copy(
            update={
                "id": left_id,
                "name": left.name,
                "action_ids": tuple(dict.fromkeys((*left.action_ids, *right.action_ids))),
                "source_event_sequences": tuple(
                    sorted(
                        set(
                            (*left.source_event_sequences, *right.source_event_sequences)
                        )
                    )
                ),
                "depends_on_step_ids": tuple(sorted(dependencies)),
                "sensitive_fields": tuple(
                    sorted(set((*left.sensitive_fields, *right.sensitive_fields)))
                ),
            }
        )
        steps = []
        for index, step in enumerate(draft.steps):
            if index == left_index:
                steps.append(merged)
            elif index == right_index:
                continue
            else:
                rewritten = tuple(
                    sorted(
                        {
                            left_id if dependency == right_id else dependency
                            for dependency in step.depends_on_step_ids
                        }
                    )
                )
                steps.append(step.model_copy(update={"depends_on_step_ids": rewritten}))
        variables = tuple(
            variable.model_copy(
                update={
                    "candidate_sources": tuple(
                        self._replace_source_step(source, right_id, left_id)
                        for source in variable.candidate_sources
                    ),
                    "confirmed_source": (
                        self._replace_source_step(
                            variable.confirmed_source,
                            right_id,
                            left_id,
                        )
                        if variable.confirmed_source is not None
                        else None
                    ),
                    "consumer_step_ids": tuple(
                        sorted(
                            {
                                left_id if consumer == right_id else consumer
                                for consumer in variable.consumer_step_ids
                            }
                        )
                    ),
                }
            )
            for variable in draft.variables
        )
        return tuple(steps), variables

    def _rename_step(
        self,
        draft: FlowDraft,
        step_id: str,
        name: str,
    ) -> tuple[tuple[FlowDraftStep, ...], tuple[FlowDraftVariable, ...]]:
        if step_id not in {step.id for step in draft.steps}:
            raise JiejianError(ErrorCode.RECORD_DRAFT_REFERENCE, "Flow 草稿步骤引用不存在")
        return (
            tuple(
                step.model_copy(update={"name": name}) if step.id == step_id else step
                for step in draft.steps
            ),
            draft.variables,
        )

    def _confirm_variable(
        self,
        draft: FlowDraft,
        command: ConfirmFlowDraftVariable,
    ) -> tuple[tuple[FlowDraftStep, ...], tuple[FlowDraftVariable, ...]]:
        variable = next(
            (
                item
                for item in draft.variables
                if item.name == command.variable_name
            ),
            None,
        )
        if variable is None:
            raise JiejianError(ErrorCode.RECORD_DRAFT_REFERENCE, "Flow 草稿变量引用不存在")
        source = next(
            (
                item
                for item in variable.candidate_sources
                if item.source_event_sequence == command.source_event_sequence
                and item.json_path == command.source_json_path
            ),
            None,
        )
        if source is None:
            raise JiejianError(
                ErrorCode.RECORD_DRAFT_REFERENCE,
                "Flow 草稿变量来源引用不存在",
            )
        steps = tuple(
            step.model_copy(
                update={
                    "depends_on_step_ids": tuple(
                        sorted(
                            set(
                                (
                                    *step.depends_on_step_ids,
                                    *(
                                        (source.source_step_id,)
                                        if step.id in variable.consumer_step_ids
                                        and step.id != source.source_step_id
                                        else ()
                                    ),
                                )
                            )
                        )
                    )
                }
            )
            for step in draft.steps
        )
        variables = tuple(
            item.model_copy(
                update={
                    "status": FlowDraftVariableStatus.CONFIRMED,
                    "confirmed_source": source,
                }
            )
            if item.name == variable.name
            else item
            for item in draft.variables
        )
        self._ensure_acyclic(steps)
        return steps, variables

    @staticmethod
    def _replace_source_step(
        source: FlowDraftVariableSource,
        old_id: str,
        new_id: str,
    ) -> FlowDraftVariableSource:
        return (
            source.model_copy(update={"source_step_id": new_id})
            if source.source_step_id == old_id
            else source
        )

    @staticmethod
    def _ensure_acyclic(steps: tuple[FlowDraftStep, ...] | list[FlowDraftStep]) -> None:
        graph: Mapping[str, set[str]] = {
            step.id: set(step.depends_on_step_ids) for step in steps
        }
        known = set(graph)
        if any(dependency not in known for dependencies in graph.values() for dependency in dependencies):
            raise JiejianError(ErrorCode.RECORD_DRAFT_REFERENCE, "Flow 草稿依赖引用不存在")
        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(step_id: str) -> None:
            if step_id in visiting:
                raise JiejianError(ErrorCode.RECORD_DRAFT_CYCLE, "Flow 草稿依赖不得成环")
            if step_id in visited:
                return
            visiting.add(step_id)
            for dependency in graph[step_id]:
                visit(dependency)
            visiting.remove(step_id)
            visited.add(step_id)

        for step_id in graph:
            visit(step_id)

    @staticmethod
    def _new_revision(
        draft: FlowDraft,
        steps: tuple[FlowDraftStep, ...] | list[FlowDraftStep],
        variables: tuple[FlowDraftVariable, ...],
    ) -> FlowDraft:
        data = draft.model_dump(mode="python")
        data.update(
            {
                "revision": draft.revision + 1,
                "steps": tuple(steps),
                "variables": variables,
            }
        )
        try:
            return FlowDraft.model_validate(data)
        except ValidationError:
            raise JiejianError(
                ErrorCode.RECORD_DRAFT_INVALID,
                "Flow 草稿审阅结果无效",
            ) from None

    @staticmethod
    def _drop_sensitive_json(value: Any) -> Any:
        if isinstance(value, Mapping):
            return {
                key: FlowDraftReviewer._drop_sensitive_json(item)
                for key, item in value.items()
                if not _SENSITIVE_FIELD.search(str(key))
            }
        if isinstance(value, list):
            return [FlowDraftReviewer._drop_sensitive_json(item) for item in value]
        return value


def compile_flow_bindings(
    flow: Flow,
    profile: WebExecutionProfile,
) -> tuple[WebTargetDefinition, tuple[HttpWorkflowBinding, ...]]:
    """把已确认 Flow 投影为当前 Profile 可接受的 Web 执行绑定。"""

    profile_bindings = {binding.action_id: binding for binding in profile.workflow_bindings}
    if len(profile_bindings) != len(profile.workflow_bindings):
        raise JiejianError(
            ErrorCode.RECORD_DRAFT_INVALID,
            "Profile 的 action bindings 不得包含重复 action",
        )
    actions_by_step: dict[str, list[tuple[str, FlowStep]]] = {}
    for step in flow.steps:
        for action_id in step.action_ids:
            actions_by_step.setdefault(action_id, []).append((step.id, step))
    if set(actions_by_step) != set(profile_bindings):
        raise JiejianError(
            ErrorCode.RECORD_DRAFT_INVALID,
            "已确认 Flow 必须覆盖且仅覆盖 Profile 的 action bindings",
        )
    if any(len(items) != 1 for items in actions_by_step.values()):
        raise JiejianError(
            ErrorCode.RECORD_DRAFT_INVALID,
            "每个 action 必须恰好映射一个已确认 Flow step",
        )
    compiled: list[HttpWorkflowBinding] = []
    for action_id, items in sorted(actions_by_step.items()):
        target_id, _target_step = items[0]
        ancestors: set[str] = set()
        graph = {item.id: set(item.depends_on_step_ids) for item in flow.steps}
        pending = list(graph[target_id])
        while pending:
            current = pending.pop()
            if current in ancestors:
                continue
            ancestors.add(current)
            pending.extend(graph[current])
        steps = tuple(
            HttpWorkflowStep(
                id=step.id,
                purpose=(WorkflowStepPurpose.TARGET if step.id == target_id else WorkflowStepPurpose.SETUP if step.id in ancestors else WorkflowStepPurpose.CLEANUP),
                identity_id=CASE_SUBJECT_IDENTITY if step.id == target_id else step.identity_id,
                request_template=step.request_template,
                classifier=step.classifier,
                depends_on_step_ids=step.depends_on_step_ids,
            )
            for step in flow.steps
        )
        base = profile_bindings[action_id]
        compiled.append(
            HttpWorkflowBinding.model_validate({
                **base.model_dump(mode="python"),
                "source_flow_id": flow.id,
                "steps": steps,
                "target_step_id": target_id,
                "reset_strategy": {"kind": "RESET_ENDPOINT", "path": flow.reset_path},
                "workflow_fingerprint": None,
            }, strict=True)
        )
    target = WebTargetDefinition(scope=profile.target.scope, reset_path=flow.reset_path)
    return target, tuple(compiled)
