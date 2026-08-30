# =============================================================================
# Recording 业务歧义确认
#
# 定位
#   不可信 FlowDraft 与人工确认的可执行 Flow 之间的信任转换边界
#
# 职责
#   应用版本化审阅命令｜确认 TARGET/资源｜修订变量与步骤
#
# 边界
#   不修改传入草稿、不执行 Flow，也不编译未确认值或具体差分身份/资源。
#
# 调用链
#   RecordingLifecycle → FlowDraftReviewer → FlowDraft revision
# =============================================================================

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any
from urllib.parse import parse_qsl, urlsplit

from pydantic import ValidationError

from product.backend.core.errors import ErrorCode, JiejianError
from product.protocols.flow_draft import (
    ConfirmFlowDraftResource,
    ConfirmFlowDraftTarget,
    ConfirmFlowDraftVariableChoice,
    FlowDraft,
    FlowDraftResourceCandidate,
    FlowDraftReviewCommand,
    FlowDraftStep,
    FlowDraftVariable,
    FlowDraftVariableStatus,
    flow_draft_source_choice_id,
)
from product.protocols.web.workflow import ValueSlotConsumer


class FlowDraftReviewer:
    """每次审阅都返回新 revision，不修改传入草稿。"""

    def apply(
        self,
        draft: FlowDraft,
        command: FlowDraftReviewCommand,
    ) -> FlowDraft:
        """在 expected revision 上应用一条审阅命令，并返回新的不可变 revision。"""

        if isinstance(command, ConfirmFlowDraftTarget):
            return self._confirm_target(draft, command.step_id)
        if isinstance(command, ConfirmFlowDraftResource):
            return self._confirm_resource(draft, command.candidate_id)
        if isinstance(command, ConfirmFlowDraftVariableChoice):
            steps, variables = self._confirm_variable(draft, command)
        else:
            raise TypeError("unsupported Flow draft review command")
        self._ensure_acyclic(steps)
        return self._new_revision(draft, steps, variables)


    def _confirm_target(self, draft: FlowDraft, step_id: str) -> FlowDraft:
        step = next((item for item in draft.steps if item.id == step_id), None)
        if step is None or step.method is None:
            raise JiejianError(
                ErrorCode.RECORD_DRAFT_REFERENCE,
                "目标请求步骤不存在",
            )
        return self._new_revision(
            draft,
            draft.steps,
            draft.variables,
            updates={
                "target_step_id": step_id,
                "resource_candidate_id": (
                    draft.resource_candidate_id
                    if draft.target_step_id == step_id
                    else None
                ),
            },
        )

    def _confirm_resource(self, draft: FlowDraft, candidate_id: str) -> FlowDraft:
        if draft.target_step_id is None:
            raise JiejianError(
                ErrorCode.RECORD_DRAFT_UNCONFIRMED,
                "请先确认目标请求",
            )
        target = next(step for step in draft.steps if step.id == draft.target_step_id)
        candidate = next(
            (
                item
                for item in target.resource_candidates
                if item.candidate_id == candidate_id
            ),
            None,
        )
        if candidate is None:
            raise JiejianError(
                ErrorCode.RECORD_DRAFT_REFERENCE,
                "业务资源位置不属于已确认目标请求",
            )
        resource_variable = self._resource_placeholder_name(target, candidate)
        variables: list[FlowDraftVariable] = []
        removed_source_steps: set[str] = set()
        for variable in draft.variables:
            if variable.name != resource_variable or target.id not in variable.consumer_step_ids:
                variables.append(variable)
                continue
            removed_source_steps.update(
                source.source_step_id for source in variable.candidate_sources
            )
            remaining_consumers = tuple(
                item for item in variable.consumer_step_ids if item != target.id
            )
            if remaining_consumers:
                variables.append(
                    variable.model_copy(
                        update={"consumer_step_ids": remaining_consumers}
                    )
                )
        remaining_target_sources = {
            source.source_step_id
            for variable in variables
            if target.id in variable.consumer_step_ids
            for source in (
                (variable.confirmed_source,)
                if variable.confirmed_source is not None
                else variable.candidate_sources
                if len(variable.candidate_sources) == 1
                else ()
            )
        }
        steps = tuple(
            step.model_copy(
                update={
                    "depends_on_step_ids": tuple(
                        dependency
                        for dependency in step.depends_on_step_ids
                        if dependency not in removed_source_steps
                        or dependency in remaining_target_sources
                    )
                }
            )
            if step.id == target.id
            else step
            for step in draft.steps
        )
        return self._new_revision(
            draft,
            steps,
            tuple(variables),
            updates={"resource_candidate_id": candidate_id},
        )

    @classmethod
    def _resource_placeholder_name(
        cls,
        step: FlowDraftStep,
        candidate: FlowDraftResourceCandidate,
    ) -> str | None:
        """识别资源位置原有的动态变量，确认后由 CASE_RESOURCE_ID 取代。"""

        value: Any = None
        if candidate.consumer is ValueSlotConsumer.PATH:
            index = int(candidate.location.removeprefix("path[").removesuffix("]"))
            parts = [item for item in urlsplit(step.path or "/").path.split("/") if item]
            if index < len(parts):
                value = parts[index]
        elif candidate.consumer is ValueSlotConsumer.QUERY:
            name = candidate.location.removeprefix("query.")
            value = next(
                (
                    item
                    for key, item in parse_qsl(
                        urlsplit(step.path or "/").query,
                        keep_blank_values=True,
                    )
                    if key == name
                ),
                None,
            )
        else:
            value = cls._json_location_value(step.json_body, candidate.location)
        if (
            isinstance(value, str)
            and value.startswith("{")
            and value.endswith("}")
        ):
            return value[1:-1]
        return None

    @staticmethod
    def _json_location_value(value: Any, path: str) -> Any:
        current = value
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


    def _confirm_variable(
        self,
        draft: FlowDraft,
        command: ConfirmFlowDraftVariableChoice,
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
                if flow_draft_source_choice_id(item) == command.choice_id
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
        *,
        updates: Mapping[str, Any] | None = None,
    ) -> FlowDraft:
        data = draft.model_dump(mode="python")
        data.update(
            {
                "revision": draft.revision + 1,
                "steps": tuple(steps),
                "variables": variables,
            }
        )
        if updates:
            data.update(updates)
        known = {step.id for step in steps}
        if data.get("recommended_target_step_id") not in known:
            data["recommended_target_step_id"] = None
        if data.get("target_step_id") not in known:
            data["target_step_id"] = None
            data["resource_candidate_id"] = None
        try:
            return FlowDraft.model_validate(data)
        except ValidationError:
            raise JiejianError(
                ErrorCode.RECORD_DRAFT_INVALID,
                "Flow 草稿审阅结果无效",
            ) from None
