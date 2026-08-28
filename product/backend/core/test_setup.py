# =============================================================================
# 测试资源与安全动作准备事实
#
# 定位
#   已确认 Recording Flow 与后续 PermissionContract/Profile 编译之间的领域事实边界
#
# 职责
#   表达测试资源归属｜固定独立观察与恢复方式｜保存用户确认的安全效果
#
# 边界
#   候选不构成事实；本模块不执行目标请求、不生成权限结论，也不保存秘密正文。
#
# 调用链
#   Recording safety setup workflow → Core facts → Storage / deterministic compiler
# =============================================================================

from __future__ import annotations

import hashlib
import json
import re
from enum import StrEnum
from typing import Any, Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from product.backend.core.identifiers import (
    PROJECT_ID_PATTERN,
    RECORDING_ID_PATTERN,
    SHA256_PATTERN,
    TEST_IDENTITY_ID_PATTERN,
)
from product.backend.core.redaction import REDACTED
from product.backend.core.verification.permissions import SecurityEffectKind

_ACTION_ID_PATTERN = r"^action_[0-9a-f]{32}$"
_TEST_RESOURCE_ID_PATTERN = r"^trs_[0-9a-f]{32}$"
_OBSERVATION_BINDING_ID_PATTERN = r"^obs_[0-9a-f]{32}$"
_RECOVERY_BINDING_ID_PATTERN = r"^rcv_[0-9a-f]{32}$"
_EFFECT_CONFIRMATION_ID_PATTERN = r"^efc_[0-9a-f]{32}$"
_FLOW_ID_PATTERN = PROJECT_ID_PATTERN
_STEP_ID_PATTERN = PROJECT_ID_PATTERN
_RESOURCE_VALUE = re.compile(r"^[\w.-]{1,256}$", re.UNICODE)
_RESOURCE_TYPE = re.compile(r"^[\w][\w .:/-]{0,127}$", re.UNICODE)
_PROJECTION_PATH = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]{0,127}$")
_UNSAFE_TEXT = re.compile(
    r"(?:<\s*script\b|javascript\s*:|\b(?:authorization|cookie|password|passwd|"
    r"secret|token|api[_-]?key)\s*[:=])",
    re.IGNORECASE,
)


class TestSetupModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        strict=True,
        hide_input_in_errors=True,
    )


class TestResourceRelation(StrEnum):
    OWNS = "OWNS"


class ResourceValueConsumer(StrEnum):
    PATH = "PATH"
    QUERY = "QUERY"
    JSON_BODY = "JSON_BODY"


class ObservationBindingKind(StrEnum):
    OWNER_READ = "OWNER_READ"


class RecoveryBindingKind(StrEnum):
    RECORDED_REQUEST = "RECORDED_REQUEST"
    NOT_REQUIRED = "NOT_REQUIRED"


def test_setup_sha256(kind: str, payload: dict[str, Any]) -> str:
    """为单类准备事实生成稳定摘要；时间与数据库身份由调用方显式排除。"""

    encoded = json.dumps(
        {"kind": kind, "payload": payload},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class TestResource(TestSetupModel):
    resource_id: str = Field(pattern=_TEST_RESOURCE_ID_PATTERN)
    project_id: str = Field(pattern=PROJECT_ID_PATTERN)
    action_candidate_id: str = Field(pattern=_ACTION_ID_PATTERN)
    recording_id: str = Field(pattern=RECORDING_ID_PATTERN)
    flow_id: str = Field(pattern=_FLOW_ID_PATTERN)
    logical_name: str = Field(min_length=1, max_length=128)
    resource_type: str = Field(min_length=1, max_length=128)
    actual_resource_id: str = Field(min_length=1, max_length=256)
    owner_test_identity_id: str = Field(pattern=TEST_IDENTITY_ID_PATTERN)
    owner_role_candidate_id: str = Field(pattern=r"^role_[0-9a-f]{32}$")
    relation: Literal[TestResourceRelation.OWNS] = TestResourceRelation.OWNS
    consumer: ResourceValueConsumer
    location: str = Field(min_length=1, max_length=512)
    source_fingerprint: str = Field(pattern=SHA256_PATTERN)
    endpoint_source_fingerprint: str = Field(pattern=SHA256_PATTERN)
    understanding_revision: int = Field(ge=1, le=1_000_000)
    flow_sha256: str = Field(pattern=SHA256_PATTERN)
    fingerprint: str = Field(pattern=SHA256_PATTERN)
    created_at_us: int = Field(ge=0)
    updated_at_us: int = Field(ge=0)

    @field_validator("logical_name")
    @classmethod
    def validate_logical_name(cls, value: str) -> str:
        return _safe_display_text(value, "test resource label")

    @field_validator("resource_type")
    @classmethod
    def validate_resource_type(cls, value: str) -> str:
        cleaned = _safe_display_text(value, "test resource type")
        if _RESOURCE_TYPE.fullmatch(cleaned) is None:
            raise ValueError("test resource type is not bounded text")
        return cleaned

    @field_validator("actual_resource_id")
    @classmethod
    def validate_actual_resource_id(cls, value: str) -> str:
        """实际测试数据只允许有限标识，不接受 URL、路径、脚本或疑似秘密。"""

        if value != value.strip() or _RESOURCE_VALUE.fullmatch(value) is None:
            raise ValueError("test resource value is not a bounded identifier")
        parsed = urlsplit(value)
        if (
            parsed.scheme
            or parsed.netloc
            or value == REDACTED
            or _UNSAFE_TEXT.search(value) is not None
        ):
            raise ValueError("test resource value crosses the safe identifier boundary")
        return value

    @model_validator(mode="after")
    def validate_resource_fact(self) -> TestResource:
        if self.updated_at_us < self.created_at_us:
            raise ValueError("test resource update precedes creation")
        if self.consumer is ResourceValueConsumer.PATH:
            valid = re.fullmatch(r"path\[[0-9]{1,3}\]", self.location) is not None
        elif self.consumer is ResourceValueConsumer.QUERY:
            valid = re.fullmatch(r"query\.[A-Za-z0-9_.~-]{1,128}", self.location) is not None
        else:
            valid = re.fullmatch(
                r"^\$(?:\.[A-Za-z_][A-Za-z0-9_-]*|\[[0-9]+\])+$",
                self.location,
            ) is not None
        if not valid:
            raise ValueError("test resource location is invalid")
        return self


class ObservationBinding(TestSetupModel):
    observation_binding_id: str = Field(pattern=_OBSERVATION_BINDING_ID_PATTERN)
    resource_id: str = Field(pattern=_TEST_RESOURCE_ID_PATTERN)
    trusted_test_identity_id: str = Field(pattern=TEST_IDENTITY_ID_PATTERN)
    kind: Literal[ObservationBindingKind.OWNER_READ] = ObservationBindingKind.OWNER_READ
    recording_id: str = Field(pattern=RECORDING_ID_PATTERN)
    source_step_id: str = Field(pattern=_STEP_ID_PATTERN)
    method: Literal["GET"] = "GET"
    path_template: str = Field(min_length=1, max_length=8_192)
    required: Literal[True] = True
    fingerprint: str = Field(pattern=SHA256_PATTERN)
    confirmed_at_us: int = Field(ge=0)

    @field_validator("path_template")
    @classmethod
    def validate_path_template(cls, value: str) -> str:
        return _safe_relative_template(value, require_resource=True)


class RecoveryBinding(TestSetupModel):
    recovery_binding_id: str = Field(pattern=_RECOVERY_BINDING_ID_PATTERN)
    resource_id: str = Field(pattern=_TEST_RESOURCE_ID_PATTERN)
    test_identity_id: str = Field(pattern=TEST_IDENTITY_ID_PATTERN)
    kind: RecoveryBindingKind
    recording_id: str = Field(pattern=RECORDING_ID_PATTERN)
    source_step_id: str | None = Field(default=None, pattern=_STEP_ID_PATTERN)
    method: Literal["PATCH", "POST", "PUT", "DELETE"] | None = None
    path_template: str | None = Field(default=None, min_length=1, max_length=8_192)
    json_body_template: dict[str, Any] = Field(default_factory=dict)
    fingerprint: str = Field(pattern=SHA256_PATTERN)
    confirmed_at_us: int = Field(ge=0)

    @field_validator("path_template")
    @classmethod
    def validate_path_template(cls, value: str | None) -> str | None:
        return (
            None
            if value is None
            else _safe_relative_template(value, require_resource=False)
        )

    @model_validator(mode="after")
    def validate_recovery_kind(self) -> RecoveryBinding:
        _reject_unsafe_json(self.json_body_template)
        if self.kind is RecoveryBindingKind.NOT_REQUIRED:
            valid = (
                self.source_step_id is None
                and self.method is None
                and self.path_template is None
                and not self.json_body_template
            )
        else:
            valid = (
                self.source_step_id is not None
                and self.method is not None
                and self.path_template is not None
                and (
                    "{case_resource_id}" in self.path_template
                    or _json_contains_resource_slot(self.json_body_template)
                )
            )
        if not valid:
            raise ValueError("recovery binding kind and request template are inconsistent")
        return self


class SecurityEffectConfirmation(TestSetupModel):
    effect_confirmation_id: str = Field(pattern=_EFFECT_CONFIRMATION_ID_PATTERN)
    resource_id: str = Field(pattern=_TEST_RESOURCE_ID_PATTERN)
    action_candidate_id: str = Field(pattern=_ACTION_ID_PATTERN)
    kind: SecurityEffectKind
    protected_fields: tuple[str, ...] = Field(default=(), max_length=64)
    fingerprint: str = Field(pattern=SHA256_PATTERN)
    confirmed_at_us: int = Field(ge=0)

    @field_validator("protected_fields")
    @classmethod
    def validate_protected_fields(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if len(set(values)) != len(values) or any(
            _PROJECTION_PATH.fullmatch(value) is None for value in values
        ):
            raise ValueError("effect protected fields must be unique bounded projections")
        return values

    @model_validator(mode="after")
    def validate_effect_fields(self) -> SecurityEffectConfirmation:
        if self.kind is SecurityEffectKind.DATA_DISCLOSURE:
            if not self.protected_fields:
                raise ValueError("data disclosure confirmation requires protected fields")
        elif self.protected_fields:
            raise ValueError("protected fields apply only to data disclosure")
        return self


class ActionSafetySetup(TestSetupModel):
    resource: TestResource
    observation: ObservationBinding | None = None
    recovery: RecoveryBinding | None = None
    effect: SecurityEffectConfirmation | None = None

    @model_validator(mode="after")
    def validate_fact_links(self) -> ActionSafetySetup:
        facts = tuple(
            item
            for item in (self.observation, self.recovery, self.effect)
            if item is not None
        )
        if any(item.resource_id != self.resource.resource_id for item in facts):
            raise ValueError("action safety facts must reference one test resource")
        if (
            self.observation is not None
            and self.observation.recording_id != self.resource.recording_id
        ) or (
            self.recovery is not None
            and self.recovery.recording_id != self.resource.recording_id
        ):
            raise ValueError("action safety bindings must come from the same recording")
        if (
            self.effect is not None
            and self.effect.action_candidate_id != self.resource.action_candidate_id
        ):
            raise ValueError("security effect confirmation must match the resource action")
        return self


def _safe_display_text(value: str, field_name: str) -> str:
    if (
        value != value.strip()
        or not value
        or any(ord(char) < 32 for char in value)
        or _UNSAFE_TEXT.search(value) is not None
    ):
        raise ValueError(f"{field_name} is unsafe")
    return value


def _safe_relative_template(value: str, *, require_resource: bool) -> str:
    parsed = urlsplit(value)
    if (
        not value.startswith("/")
        or value.startswith("//")
        or parsed.scheme
        or parsed.netloc
        or parsed.fragment
        or (require_resource and "{case_resource_id}" not in value)
        or any(segment in {".", ".."} for segment in parsed.path.split("/"))
        or _UNSAFE_TEXT.search(value) is not None
    ):
        raise ValueError("binding path template is unsafe")
    return value


def _json_contains_resource_slot(value: Any) -> bool:
    pending = [value]
    while pending:
        item = pending.pop()
        if isinstance(item, dict):
            pending.extend(item.values())
        elif isinstance(item, list):
            pending.extend(item)
        elif item == "{case_resource_id}":
            return True
    return False


def _reject_unsafe_json(value: Any) -> None:
    pending = [value]
    while pending:
        item = pending.pop()
        if isinstance(item, dict):
            pending.extend(item.keys())
            pending.extend(item.values())
        elif isinstance(item, list):
            pending.extend(item)
        elif isinstance(item, str) and (
            len(item) > 8_192 or _UNSAFE_TEXT.search(item) is not None
        ):
            raise ValueError("recovery JSON contains unsafe text")


__all__ = [
    "ActionSafetySetup",
    "ObservationBinding",
    "ObservationBindingKind",
    "RecoveryBinding",
    "RecoveryBindingKind",
    "ResourceValueConsumer",
    "SecurityEffectConfirmation",
    "TestResource",
    "TestResourceRelation",
    "test_setup_sha256",
]
