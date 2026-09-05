# 保存正式动作的执行、资源、效果证明与恢复来源；实时有效性由应用层检查。
# 这里只接受非秘密技术事实，不保存权限、准备状态或可由模型执行的指令。

from __future__ import annotations

import json
import re
from enum import StrEnum
from typing import Any, Literal
from urllib.parse import unquote, urlsplit

from pydantic import Field, field_validator, model_validator

from product.backend.core.business_boundary import ACTION_ID_PATTERN, EFFECT_ID_PATTERN, BoundaryModel, boundary_sha256
from product.backend.core.identifiers import PROJECT_ID_PATTERN, RECORDING_ID_PATTERN, SHA256_PATTERN, TEST_IDENTITY_ID_PATTERN
from product.backend.core.redaction import REDACTED


_UNSAFE_TEXT = re.compile(
    r"(?:<\s*script\b|javascript\s*:|\b(?:authorization|cookie|password|passwd|secret|token|api[_-]?key)\s*[:=])",
    re.IGNORECASE,
)
_SECRET_KEY = re.compile(r"^(?:authorization|cookie|password|passwd|secret|token|access_token|refresh_token|api[_-]?key)$", re.IGNORECASE)


class ResourceInjectionKind(StrEnum):
    PATH = "PATH"
    QUERY = "QUERY"
    JSON_BODY = "JSON_BODY"


class ActionEvidenceKind(StrEnum):
    RECORDED_OBSERVATION = "RECORDED_OBSERVATION"
    REGISTERED_OBSERVER = "REGISTERED_OBSERVER"


class ResourceInjection(BoundaryModel):
    consumer: ResourceInjectionKind
    location: str = Field(min_length=1, max_length=512)
    # 槽兼容性不包含录制账号或具体资源值，允许多位所有者复用同一动作执行模板。
    template_fingerprint: str = Field(pattern=SHA256_PATTERN)

    @model_validator(mode="after")
    def validate_location(self) -> ResourceInjection:
        patterns = {
            ResourceInjectionKind.PATH: r"path\[[0-9]{1,3}\]",
            ResourceInjectionKind.QUERY: r"query\.[A-Za-z0-9_.~-]{1,128}",
            ResourceInjectionKind.JSON_BODY: r"\$(?:\.[A-Za-z_][A-Za-z0-9_-]*|\[[0-9]+\])+",
        }
        if re.fullmatch(patterns[self.consumer], self.location) is None:
            raise ValueError("resource injection location is invalid")
        return self


class RecordedRequestTemplate(BoundaryModel):
    method: Literal["GET", "POST", "PUT", "PATCH", "DELETE"]
    relative_path: str = Field(min_length=1, max_length=2048)
    json_body: dict[str, Any] = Field(default_factory=dict)

    @field_validator("relative_path")
    @classmethod
    def validate_relative_path(cls, value: str) -> str:
        parsed = urlsplit(value)
        if (
            not value.startswith("/") or value.startswith("//") or "\\" in value
            or parsed.scheme or parsed.netloc or parsed.fragment
            or any(part in {".", ".."} for part in unquote(parsed.path).split("/"))
            or any(ord(char) < 32 or ord(char) == 127 for char in value)
            or _UNSAFE_TEXT.search(value) is not None or REDACTED in value
        ):
            raise ValueError("recorded request path is unsafe")
        return value

    @model_validator(mode="after")
    def validate_body(self) -> RecordedRequestTemplate:
        raw = json.dumps(self.json_body, ensure_ascii=False, allow_nan=False)
        if len(raw.encode("utf-8")) > 65_536:
            raise ValueError("recorded request body exceeds budget")
        pending = [self.json_body]
        while pending:
            item = pending.pop()
            if isinstance(item, dict):
                if any(type(key) is not str or _SECRET_KEY.fullmatch(key) for key in item):
                    raise ValueError("recorded request body contains secret fields")
                pending.extend(item.keys())
                pending.extend(item.values())
            elif isinstance(item, list):
                pending.extend(item)
            elif isinstance(item, str) and (len(item) > 8192 or _UNSAFE_TEXT.search(item) or REDACTED in item):
                raise ValueError("recorded request body contains unsafe text")
            elif item is not None and type(item) not in (str, int, float, bool):
                raise ValueError("recorded request body contains unsupported values")
        if "{case_resource_id}" not in self.relative_path and not contains_resource_slot(self.json_body):
            raise ValueError("recorded request requires a resource slot")
        return self


def contains_resource_slot(value: Any) -> bool:
    if isinstance(value, dict):
        return any(contains_resource_slot(item) for item in value.values())
    if isinstance(value, list):
        return any(contains_resource_slot(item) for item in value)
    return value == "{case_resource_id}"


class RegisteredObserverReference(BoundaryModel):
    # 这是受控注册表内的身份引用；没有路径、URL、查询或脚本字段。
    descriptor_id: str = Field(pattern=r"^exp_[0-9a-f]{32}$")
    descriptor_fingerprint: str = Field(pattern=SHA256_PATTERN)
    observer_id: str = Field(pattern=PROJECT_ID_PATTERN)


class _ActionBinding(BoundaryModel):
    project_id: str = Field(pattern=PROJECT_ID_PATTERN)
    business_action_id: str = Field(pattern=ACTION_ID_PATTERN)
    action_revision: int = Field(ge=1)
    action_semantic_fingerprint: str = Field(pattern=SHA256_PATTERN)
    implementation_fingerprint: str = Field(pattern=SHA256_PATTERN)
    source_fingerprint: str | None = Field(default=None, pattern=SHA256_PATTERN)
    endpoint_fingerprint: str = Field(pattern=SHA256_PATTERN)
    test_identity_id: str = Field(pattern=TEST_IDENTITY_ID_PATTERN)
    identity_fingerprint: str = Field(pattern=SHA256_PATTERN)
    confirmed_at_us: int = Field(ge=0)
    binding_fingerprint: str = Field(pattern=SHA256_PATTERN)

    @model_validator(mode="after")
    def validate_fingerprint(self):
        if self.binding_fingerprint != binding_fingerprint(type(self), self.model_dump(mode="json")):
            raise ValueError("action preparation binding fingerprint is inconsistent")
        return self


class _RecordedBinding(_ActionBinding):
    source_recording_id: str = Field(pattern=RECORDING_ID_PATTERN)
    source_draft_revision: int = Field(ge=1)
    source_draft_sha256: str = Field(pattern=SHA256_PATTERN)


class ActionExecutionBinding(_RecordedBinding):
    flow_id: str = Field(pattern=PROJECT_ID_PATTERN)
    flow_sha256: str = Field(pattern=SHA256_PATTERN)
    resource_injection: ResourceInjection


class ActionResourceBinding(_RecordedBinding):
    owner_test_identity_id: str = Field(pattern=TEST_IDENTITY_ID_PATTERN)
    actual_resource_id: str = Field(min_length=1, max_length=256)
    flow_id: str = Field(pattern=PROJECT_ID_PATTERN)
    flow_sha256: str = Field(pattern=SHA256_PATTERN)
    resource_injection: ResourceInjection

    @field_validator("actual_resource_id")
    @classmethod
    def validate_resource_id(cls, value: str) -> str:
        if (re.fullmatch(r"[\w.-]{1,256}", value) is None or value in {".", ".."}
                or REDACTED in value or _UNSAFE_TEXT.search(value)):
            raise ValueError("resource value must be a bounded non-secret identifier")
        return value

    @model_validator(mode="after")
    def validate_owner(self) -> ActionResourceBinding:
        if self.owner_test_identity_id != self.test_identity_id:
            raise ValueError("resource owner must be the source recording identity")
        return self


class ActionEvidenceBinding(_ActionBinding):
    effect_id: str = Field(pattern=EFFECT_ID_PATTERN)
    kind: ActionEvidenceKind
    source_recording_id: str | None = Field(default=None, pattern=RECORDING_ID_PATTERN)
    source_draft_revision: int | None = Field(default=None, ge=1)
    source_draft_sha256: str | None = Field(default=None, pattern=SHA256_PATTERN)
    step_id: str | None = Field(default=None, pattern=PROJECT_ID_PATTERN)
    request_template: RecordedRequestTemplate | None = None
    observer_reference: RegisteredObserverReference | None = None

    @model_validator(mode="after")
    def validate_source(self) -> ActionEvidenceBinding:
        recorded = (self.source_recording_id, self.source_draft_revision, self.source_draft_sha256,
                    self.step_id, self.request_template)
        if self.kind is ActionEvidenceKind.RECORDED_OBSERVATION:
            if any(item is None for item in recorded) or self.observer_reference is not None:
                raise ValueError("recorded evidence requires its exact recording source")
            if self.request_template.method != "GET" or self.request_template.json_body:
                raise ValueError("recorded observation must be a read-only request")
        elif any(item is not None for item in recorded) or self.observer_reference is None:
            raise ValueError("registered evidence only accepts a controlled descriptor reference")
        return self


class ActionRecoveryBinding(_RecordedBinding):
    step_id: str = Field(pattern=PROJECT_ID_PATTERN)
    request_template: RecordedRequestTemplate

    @model_validator(mode="after")
    def validate_recovery(self) -> ActionRecoveryBinding:
        if self.request_template.method == "GET":
            raise ValueError("recovery requires a recorded state-changing request")
        return self


def binding_fingerprint(model_type, values: dict[str, Any]) -> str:
    """内容身份不包含确认时间；不同类型的技术事实使用独立摘要域。"""
    payload = {key: value for key, value in values.items()
               if key not in {"binding_fingerprint", "confirmed_at_us"}}
    return boundary_sha256({"kind": model_type.__name__, "facts": payload})


def seal_binding(model_type, **values):
    """由确定性来源构造完整严格对象；默认字段也纳入稳定摘要。"""
    # model_construct 只用于补齐默认值和规范化摘要输入，返回前仍运行全部严格校验。
    draft = model_type.model_construct(**values, binding_fingerprint="0" * 64)
    payload = draft.model_dump(mode="json")
    payload["binding_fingerprint"] = binding_fingerprint(model_type, payload)
    return model_type.model_validate_json(json.dumps(payload, ensure_ascii=False, allow_nan=False), strict=True)


__all__ = [
    "ActionEvidenceBinding", "ActionEvidenceKind", "ActionExecutionBinding", "ActionRecoveryBinding",
    "ActionResourceBinding", "RecordedRequestTemplate", "RegisteredObserverReference",
    "ResourceInjection", "ResourceInjectionKind", "binding_fingerprint", "seal_binding",
]
