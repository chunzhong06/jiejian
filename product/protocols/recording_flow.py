# =============================================================================
# 已确认 Recording Flow 协议
#
# 定位
# 人工确认的录制步骤进入后续执行绑定前的稳定、不可变协议。
#
# 职责
# 表达步骤依赖与变量来源｜校验相对路径｜约束身份和资源绑定
#
# 边界
# 不属于 Verification Core 或 Execution Profile，不携带 secret，也不自行执行请求。
#
# 调用链
# FlowDraftReviewer → Flow → Contract candidate / replay boundaries
# =============================================================================

from __future__ import annotations

import re
from typing import Any, Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from product.backend.core.identifiers import PROJECT_ID_PATTERN


class RecordingFlowModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        strict=True,
        hide_input_in_errors=True,
    )

    schema_version: Literal["1"] = "1"


class FlowVariableSource(RecordingFlowModel):
    name: str = Field(pattern=PROJECT_ID_PATTERN)
    source_step_id: str = Field(pattern=PROJECT_ID_PATTERN)
    source_event_sequence: int = Field(ge=1)
    json_path: str = Field(min_length=1, max_length=512)


class FlowStep(RecordingFlowModel):
    id: str = Field(pattern=PROJECT_ID_PATTERN)
    name: str | None = Field(default=None, min_length=1, max_length=128)
    method: Literal["GET", "PATCH", "POST", "PUT", "DELETE"]
    path: str
    identity_id: str
    resource_id: str
    alternate_identity_id: str
    alternate_resource_id: str
    json_body: dict[str, Any] = Field(default_factory=dict)
    expected_statuses: tuple[int, ...] = (200,)
    action_ids: tuple[str, ...] = Field(default=(), max_length=16)
    depends_on_step_ids: tuple[str, ...] = Field(default=(), max_length=128)
    variable_sources: tuple[FlowVariableSource, ...] = Field(default=(), max_length=128)
    sensitive_fields: tuple[str, ...] = Field(default=(), max_length=256)

    @field_validator("path")
    @classmethod
    def validate_relative_http_path(cls, value: str) -> str:
        parsed = urlsplit(value)
        if (
            not value.startswith("/")
            or value.startswith("//")
            or parsed.scheme
            or parsed.netloc
            or parsed.fragment
            or any(segment in {".", ".."} for segment in parsed.path.split("/"))
        ):
            raise ValueError("flow step path must be an absolute-path reference")
        return value

    @field_validator("json_body")
    @classmethod
    def reject_inline_secrets(cls, value: dict[str, Any]) -> dict[str, Any]:
        if any(
            re.search(
                r"authorization|cookie|credential|password|secret|token|api[_-]?key",
                str(key),
                re.IGNORECASE,
            )
            for key in value
        ):
            raise ValueError("flow JSON must not contain inline credential fields")
        return value

    @model_validator(mode="after")
    def validate_metadata(self) -> FlowStep:
        if len(set(self.depends_on_step_ids)) != len(self.depends_on_step_ids):
            raise ValueError("flow step dependencies must be unique")
        if len({source.name for source in self.variable_sources}) != len(self.variable_sources):
            raise ValueError("flow variable sources must be unique")
        if len(set(self.sensitive_fields)) != len(self.sensitive_fields):
            raise ValueError("flow sensitive fields must be unique")
        return self


# 已确认、无环且不含秘密的录制流程；变量只能引用先前步骤。
class Flow(RecordingFlowModel):
    id: str = Field(pattern=PROJECT_ID_PATTERN)
    steps: tuple[FlowStep, ...] = Field(min_length=1)
    owner_observer_path: str = "/owner/resources/{resource_id}"
    reset_path: str = "/reset"

    @field_validator("owner_observer_path", "reset_path")
    @classmethod
    def validate_support_path(cls, value: str) -> str:
        parsed = urlsplit(value)
        if (
            not value.startswith("/")
            or value.startswith("//")
            or parsed.scheme
            or parsed.netloc
            or parsed.query
            or parsed.fragment
            or any(segment in {".", ".."} for segment in parsed.path.split("/"))
        ):
            raise ValueError("support endpoint must be an absolute-path reference")
        return value

    @model_validator(mode="after")
    def validate_dependency_graph(self) -> Flow:
        step_ids = tuple(step.id for step in self.steps)
        if len(set(step_ids)) != len(step_ids):
            raise ValueError("flow step IDs must be unique")
        known = set(step_ids)
        graph = {step.id: set(step.depends_on_step_ids) for step in self.steps}
        if any(
            dependency not in known or dependency == step_id
            for step_id, dependencies in graph.items()
            for dependency in dependencies
        ):
            raise ValueError("flow step dependency reference is invalid")
        if any(
            source.source_step_id not in known or source.source_step_id not in graph[step.id]
            for step in self.steps
            for source in step.variable_sources
        ):
            raise ValueError("flow variable source must be a declared dependency")
        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(step_id: str) -> None:
            if step_id in visiting:
                raise ValueError("flow dependencies must be acyclic")
            if step_id in visited:
                return
            visiting.add(step_id)
            for dependency in graph[step_id]:
                visit(dependency)
            visiting.remove(step_id)
            visited.add(step_id)

        for step_id in step_ids:
            visit(step_id)
        return self


__all__ = ["Flow", "FlowStep", "FlowVariableSource"]
