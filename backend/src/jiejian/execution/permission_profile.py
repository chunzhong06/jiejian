# 阶段 6 V2 权限执行 Profile。
#
# 定位：保存无秘密高级执行配置的严格真源、规范化加载和确定性摘要。
# 完整 Profile 只存在受控源文件；数据库只保存治理元数据。

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Mapping, Sequence
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from ..errors import ErrorCode, JiejianError
from ..protocols import (
    ActionExecutionBindingV2,
    ExecutionProjectSnapshotV2,
    ObserverRequirementBindingV2,
    ObserverSpecV2,
    SubjectExecutionBindingV2,
)
from ..verification.models import Flow, Identity, TargetScope
from ..verification.permission_coverage import PermissionMutationPlanV2
from ..verification.permissions import PermissionContractV2


PERMISSION_EXECUTION_PROFILE_MAX_BYTES = 1_048_576
_PROFILE_ID = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")
_SECRET_KEY = re.compile(
    r"(?:authorization|cookie|credential|password|passwd|secret|token|api[_-]?key)",
    re.IGNORECASE,
)
_INLINE_SECRET = re.compile(
    r"(?:\bBearer\s+\S+|\b(?:authorization|cookie|credential|password|passwd|"
    r"secret|token|api[_-]?key)\s*[:=]\s*\S+)",
    re.IGNORECASE,
)


class PermissionExecutionProfileV2(BaseModel):
    """完整、无秘密的 V2 权限执行配置；不含运行时 Job 或结果字段。"""

    model_config = ConfigDict(
        strict=True,
        frozen=True,
        extra="forbid",
        hide_input_in_errors=True,
    )

    schema_version: Literal["2"] = "2"
    profile_id: str = Field(pattern=_PROFILE_ID.pattern)
    project_id: str = Field(pattern=_PROFILE_ID.pattern)
    project_name: str = Field(min_length=1, max_length=128)
    target: TargetScope
    identities: tuple[Identity, ...] = Field(min_length=1, max_length=4096)
    flow: Flow
    contract: PermissionContractV2
    observers: tuple[ObserverSpecV2, ...] = Field(default=(), max_length=256)
    subject_bindings: tuple[SubjectExecutionBindingV2, ...] = Field(min_length=1, max_length=4096)
    action_bindings: tuple[ActionExecutionBindingV2, ...] = Field(min_length=1, max_length=4096)
    observer_bindings: tuple[ObserverRequirementBindingV2, ...] = Field(min_length=1, max_length=256)
    seed: int = Field(ge=0, le=9_223_372_036_854_775_807)
    case_budget: int = Field(ge=1, le=8192)
    max_relation_depth: int = Field(ge=1, le=64)
    max_duration_us: int = Field(ge=1, le=3_600_000_000)

    @model_validator(mode="after")
    def validate_profile(self) -> PermissionExecutionProfileV2:
        if len({item.id for item in self.identities}) != len(self.identities):
            raise ValueError("profile identity IDs must be unique")
        if len({item.observer_id for item in self.observers}) != len(self.observers):
            raise ValueError("profile observer IDs must be unique")
        _reject_secret_material(self.model_dump(mode="python"))
        return self

    def build_snapshot(
        self,
        plan: PermissionMutationPlanV2,
    ) -> ExecutionProjectSnapshotV2:
        """让 Runner V2 唯一快照校验器执行全部跨引用检查。"""

        return ExecutionProjectSnapshotV2(
            project_id=self.project_id,
            project_name=self.project_name,
            target=self.target,
            identities=self.identities,
            flow=self.flow,
            contract=self.contract,
            plan=plan,
            observers=self.observers,
            subject_bindings=self.subject_bindings,
            action_bindings=self.action_bindings,
            observer_bindings=self.observer_bindings,
            contract_fingerprint=_contract_fingerprint(self.contract),
            plan_fingerprint=plan.plan_fingerprint,
        )


def _contract_fingerprint(contract: PermissionContractV2) -> str:
    from ..verification.permissions import canonical_sha256

    return canonical_sha256(contract)


def _reject_secret_material(value: Any) -> None:
    pending = [value]
    while pending:
        item = pending.pop()
        if isinstance(item, Mapping):
            for key, child in item.items():
                if (
                    isinstance(key, str)
                    and not key.endswith("_ref")
                    and _SECRET_KEY.search(key)
                ):
                    raise ValueError("profile contains a sensitive field")
                pending.append(child)
        elif isinstance(item, (list, tuple)):
            pending.extend(item)
        elif isinstance(item, float) and not math.isfinite(item):
            raise ValueError("profile contains a non-finite number")
        elif isinstance(item, str) and not item.startswith("env:") and _INLINE_SECRET.search(item):
            raise ValueError("profile contains inline sensitive material")


def canonical_permission_execution_profile_json_bytes(
    profile: PermissionExecutionProfileV2,
    *,
    known_secrets: Sequence[str] = (),
) -> bytes:
    payload = profile.model_dump(mode="json")
    _reject_secret_values(payload, known_secrets)
    try:
        return json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeError):
        raise JiejianError(ErrorCode.PERMISSION_PROFILE_INVALID, "Profile 规范化失败") from None


def permission_execution_profile_sha256(
    profile: PermissionExecutionProfileV2,
    *,
    known_secrets: Sequence[str] = (),
) -> str:
    return hashlib.sha256(
        canonical_permission_execution_profile_json_bytes(profile, known_secrets=known_secrets)
    ).hexdigest()


def parse_permission_execution_profile(
    raw: bytes,
    *,
    known_secrets: Sequence[str] = (),
) -> PermissionExecutionProfileV2:
    if len(raw) > PERMISSION_EXECUTION_PROFILE_MAX_BYTES:
        raise JiejianError(ErrorCode.PERMISSION_PROFILE_INVALID, "Profile 超过大小限制")
    if raw.startswith(b"\xef\xbb\xbf"):
        raise JiejianError(ErrorCode.PERMISSION_PROFILE_INVALID, "Profile 不接受 BOM")

    def reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate JSON key")
            result[key] = value
        return result

    try:
        data = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=reject_duplicate_keys,
            parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)),
        )
        if not isinstance(data, dict):
            raise ValueError("profile root must be an object")
        # 先用 json.loads 只做重复键/根类型检查，再由 Pydantic 的 JSON
        # strict parser 保留 tuple 等 JSON 数组到严格模型的合法转换。
        profile = PermissionExecutionProfileV2.model_validate_json(raw, strict=True)
        _reject_secret_values(profile.model_dump(mode="json"), known_secrets)
        return profile
    except JiejianError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError, ValidationError):
        raise JiejianError(ErrorCode.PERMISSION_PROFILE_INVALID, "Profile 文件无效") from None


def _reject_secret_values(value: Any, known_secrets: Sequence[str]) -> None:
    secrets = tuple(secret for secret in known_secrets if secret)
    pending = [value]
    while pending:
        item = pending.pop()
        if isinstance(item, Mapping):
            pending.extend(item.keys())
            pending.extend(item.values())
        elif isinstance(item, (list, tuple)):
            pending.extend(item)
        elif isinstance(item, str) and any(secret in item for secret in secrets):
            raise JiejianError(ErrorCode.PERMISSION_PROFILE_INVALID, "Profile 包含敏感内容")
