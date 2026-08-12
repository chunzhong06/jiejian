# =============================================================================
# Recording FlowDraft 审阅
#
# 定位
#   不可信 FlowDraft 与人工确认的可执行 Flow 之间的信任转换边界
#
# 职责
#   应用版本化审阅命令｜保持草稿不可变历史｜校验绑定后编译 Flow
#
# 调用链
#   RecordingWorkflow → FlowDraftReviewer → FlowDraft revision / verification.models.Flow
# =============================================================================

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from pydantic import ValidationError

from ..verification.models import Flow, FlowStep, FlowVariableSource
from ..errors import ErrorCode, JiejianError
from ..protocols.flow_draft_v1 import (
    ConfirmFlowDraftVariableV1,
    DeleteFlowDraftStepV1,
    FlowDraftReviewCommandV1,
    FlowDraftStepV1,
    FlowDraftV1,
    FlowDraftVariableSourceV1,
    FlowDraftVariableStatus,
    FlowDraftVariableV1,
    MergeFlowDraftStepsV1,
    RenameFlowDraftStepV1,
)

_SENSITIVE_FIELD = re.compile(
    r"(?:authorization|cookie|credential|password|passwd|secret|token|api[_-]?key)",
    re.IGNORECASE,
)


class FlowDraftReviewer:
    """每次审阅都返回新 revision，不修改传入草稿。"""

    def apply(
        self,
        draft: FlowDraftV1,
        command: FlowDraftReviewCommandV1,
    ) -> FlowDraftV1:
        if isinstance(command, DeleteFlowDraftStepV1):
            steps, variables = self._delete_step(draft, command.step_id)
        elif isinstance(command, MergeFlowDraftStepsV1):
            steps, variables = self._merge_steps(
                draft,
                command.left_step_id,
                command.right_step_id,
            )
        elif isinstance(command, RenameFlowDraftStepV1):
            steps, variables = self._rename_step(draft, command.step_id, command.name)
        elif isinstance(command, ConfirmFlowDraftVariableV1):
            steps, variables = self._confirm_variable(draft, command)
        else:
            raise TypeError("unsupported Flow draft review command")
        self._ensure_acyclic(steps)
        return self._new_revision(draft, steps, variables)

    def compile(self, draft: FlowDraftV1) -> Flow:
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
            for consumer in variable.consumer_step_ids:
                sources_by_consumer.setdefault(consumer, []).append(
                    FlowVariableSource(
                        schema_version="1",
                        name=variable.name,
                        source_step_id=source.source_step_id,
                        source_event_sequence=source.source_event_sequence,
                        json_path=source.json_path,
                    )
                )
        try:
            steps = tuple(
                FlowStep(
                    schema_version="1",
                    id=step.id,
                    name=step.name,
                    method=step.method,
                    path=step.path,
                    identity_id=step.identity_id,
                    resource_id=step.resource_id,
                    alternate_identity_id=step.alternate_identity_id,
                    alternate_resource_id=step.alternate_resource_id,
                    json_body=self._drop_sensitive_json(step.json_body),
                    expected_statuses=step.expected_statuses,
                    depends_on_step_ids=step.depends_on_step_ids,
                    variable_sources=tuple(
                        sorted(
                            sources_by_consumer.get(step.id, ()),
                            key=lambda item: item.name,
                        )
                    ),
                    sensitive_fields=step.sensitive_fields,
                )
                for step in draft.steps
            )
            return Flow(
                schema_version="1",
                id=draft.flow_id,
                steps=steps,
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
        draft: FlowDraftV1,
        step_id: str,
    ) -> tuple[tuple[FlowDraftStepV1, ...], tuple[FlowDraftVariableV1, ...]]:
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
        draft: FlowDraftV1,
        left_id: str,
        right_id: str,
    ) -> tuple[tuple[FlowDraftStepV1, ...], tuple[FlowDraftVariableV1, ...]]:
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
        draft: FlowDraftV1,
        step_id: str,
        name: str,
    ) -> tuple[tuple[FlowDraftStepV1, ...], tuple[FlowDraftVariableV1, ...]]:
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
        draft: FlowDraftV1,
        command: ConfirmFlowDraftVariableV1,
    ) -> tuple[tuple[FlowDraftStepV1, ...], tuple[FlowDraftVariableV1, ...]]:
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
        source: FlowDraftVariableSourceV1,
        old_id: str,
        new_id: str,
    ) -> FlowDraftVariableSourceV1:
        return (
            source.model_copy(update={"source_step_id": new_id})
            if source.source_step_id == old_id
            else source
        )

    @staticmethod
    def _ensure_acyclic(steps: tuple[FlowDraftStepV1, ...] | list[FlowDraftStepV1]) -> None:
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
        draft: FlowDraftV1,
        steps: tuple[FlowDraftStepV1, ...] | list[FlowDraftStepV1],
        variables: tuple[FlowDraftVariableV1, ...],
    ) -> FlowDraftV1:
        data = draft.model_dump(mode="python")
        data.update(
            {
                "revision": draft.revision + 1,
                "steps": tuple(steps),
                "variables": variables,
            }
        )
        try:
            return FlowDraftV1.model_validate(data)
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
