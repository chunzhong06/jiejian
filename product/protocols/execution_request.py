# =============================================================================
# 持久执行请求协议
#
# 定位
# Application Core、Job 存储与 Worker 之间的唯一冻结执行快照。
#
# 职责
# 组合执行预算、项目快照、权限策略及可选变化/修复上下文｜校验秘密引用｜编码有界 canonical JSON
#
# 边界
# 不包含秘密正文、不读取 Profile 源文件，也不允许 Worker 重新解释治理配置。
#
# 调用链
# ExecutionWorkflow → ExecutionRequestStore → Worker / RunnerInput
# =============================================================================

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Mapping, Sequence
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.core.identifiers import (
    PROJECT_ID_PATTERN,
    SHA256_PATTERN,
    TEST_IDENTITY_ID_PATTERN,
)
from product.backend.core.permission_intent import PermissionIntentRelation, ProtectedEffect
from product.backend.core.repair import (
    RepairAllowControlIdentity,
    RepairContractReference,
    RepairEvidenceStandard,
    RepairIntentIdentity,
    RepairRegressionControlIdentity,
)
from product.backend.core.verification.permissions import PermissionExpectation
from product.protocols.execution import ExecutionBudget
from product.protocols.runner import RUNNER_INPUT_MAX_BYTES
from product.protocols.web.profile import (
    WebExecutionSnapshot,
    required_web_secret_refs,
)


class PermissionPolicySnapshotEntry(BaseModel):
    """一次运行冻结的单条人类权限 revision 与实现绑定身份。"""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True, hide_input_in_errors=True)

    intent_id: str = Field(pattern=r"^pin_[0-9a-f]{32}$")
    revision: int = Field(ge=1)
    intent_hash: str = Field(pattern=SHA256_PATTERN)
    binding_fingerprint: str = Field(pattern=SHA256_PATTERN)
    expectation: PermissionExpectation | None = None
    relation: PermissionIntentRelation | None = None
    subject_display_name: str | None = Field(default=None, min_length=1, max_length=128)
    action_display_name: str | None = Field(default=None, min_length=1, max_length=256)
    resource_owner_display_name: str | None = Field(default=None, min_length=1, max_length=128)
    protected_effects: tuple[ProtectedEffect, ...] = Field(default=(), max_length=16)
    action_candidate_id: str | None = Field(default=None, pattern=r"^action_[0-9a-f]{32}$")
    subject_test_identity_id: str | None = Field(default=None, pattern=TEST_IDENTITY_ID_PATTERN)

    @model_validator(mode="after")
    def validate_semantic_projection(self) -> PermissionPolicySnapshotEntry:
        projection = (
            self.expectation,
            self.relation,
            self.subject_display_name,
            self.action_display_name,
            self.resource_owner_display_name,
            self.action_candidate_id,
            self.subject_test_identity_id,
        )
        if any(item is not None for item in projection) and any(item is None for item in projection):
            raise ValueError("permission policy semantic projection must be complete")
        if all(item is None for item in projection) and self.protected_effects:
            raise ValueError("legacy permission policy entry cannot carry protected effects")
        return self

    def fingerprint_payload(self) -> dict[str, Any]:
        """旧冻结请求保持原指纹；新请求把完整业务语义投影纳入指纹。"""

        if self.expectation is not None:
            return self.model_dump(mode="json")
        return self.model_dump(
            mode="json",
            exclude={
                "expectation",
                "relation",
                "subject_display_name",
                "action_display_name",
                "resource_owner_display_name",
                "protected_effects",
                "action_candidate_id",
                "subject_test_identity_id",
            },
        )


class PermissionPolicySnapshot(BaseModel):
    """Run 只读取的项目权限版本；live Ledger 变化不能改写它。"""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True, hide_input_in_errors=True)

    project_id: str = Field(pattern=PROJECT_ID_PATTERN)
    policy_epoch: int = Field(ge=0)
    policy_fingerprint: str = Field(pattern=SHA256_PATTERN)
    entries: tuple[PermissionPolicySnapshotEntry, ...] = Field(default=(), max_length=4096)

    @model_validator(mode="after")
    def validate_snapshot(self) -> PermissionPolicySnapshot:
        ordered = tuple(sorted(self.entries, key=lambda item: item.intent_id))
        if ordered != self.entries or len({item.intent_id for item in ordered}) != len(ordered):
            raise ValueError("permission policy entries must be unique and sorted")
        payload = {
            "project_id": self.project_id,
            "policy_epoch": self.policy_epoch,
            "entries": [item.fingerprint_payload() for item in ordered],
        }
        encoded = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
        if self.policy_fingerprint != hashlib.sha256(encoded).hexdigest():
            raise ValueError("permission policy fingerprint is inconsistent")
        return self


def build_permission_policy_snapshot(
    project_id: str,
    policy_epoch: int,
    entries: Sequence[PermissionPolicySnapshotEntry],
) -> PermissionPolicySnapshot:
    ordered = tuple(sorted(entries, key=lambda item: item.intent_id))
    payload = {
        "project_id": project_id,
        "policy_epoch": policy_epoch,
        "entries": [item.fingerprint_payload() for item in ordered],
    }
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return PermissionPolicySnapshot(
        project_id=project_id,
        policy_epoch=policy_epoch,
        policy_fingerprint=hashlib.sha256(encoded).hexdigest(),
        entries=ordered,
    )


class ChangeVerificationContext(BaseModel):
    """一次代码变化重验随 Run 冻结的最小事实，不携带文件清单或源码内容。"""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True, hide_input_in_errors=True)

    change_id: str = Field(pattern=r"^chg_[0-9a-f]{32}$")
    impact_fingerprint: str = Field(pattern=SHA256_PATTERN)
    required_intent_ids: tuple[str, ...] = Field(default=(), max_length=4096)

    @model_validator(mode="after")
    def validate_required_intents(self) -> ChangeVerificationContext:
        if (
            self.required_intent_ids != tuple(sorted(self.required_intent_ids))
            or len(set(self.required_intent_ids)) != len(self.required_intent_ids)
            or any(
                re.fullmatch(r"pin_[0-9a-f]{32}", intent_id) is None
                for intent_id in self.required_intent_ids
            )
        ):
            raise ValueError("change verification intent IDs must be unique and sorted")
        return self


class LegacyChangeVerificationContext(BaseModel):
    """仅为已发布 v1 Run 保留的旧变化上下文，禁止用于当前提交。"""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True, hide_input_in_errors=True)

    change_id: str = Field(pattern=r"^chg_[0-9a-f]{32}$")
    impact_fingerprint: str = Field(pattern=SHA256_PATTERN)
    required_intent_ids: tuple[str, ...] = Field(default=(), max_length=4096)
    source_fingerprint: str = Field(pattern=SHA256_PATTERN)

    @model_validator(mode="after")
    def validate_required_intents(self) -> LegacyChangeVerificationContext:
        _validate_required_intent_ids(self.required_intent_ids)
        return self


class RepairVerificationContext(BaseModel):
    """随修复重验 Run 冻结原考题、受保护后果、ALLOW 控制和证据标准。"""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True, hide_input_in_errors=True)

    reference: RepairContractReference
    original_policy_epoch: int = Field(ge=0)
    target_intent: RepairIntentIdentity
    original_intents: tuple[RepairIntentIdentity, ...] = Field(min_length=2, max_length=4096)
    must_disappear_effect_ids: tuple[str, ...] = Field(min_length=1, max_length=64)
    must_remain_allow_control: RepairAllowControlIdentity
    must_remain_regression_controls: tuple[RepairRegressionControlIdentity, ...] = Field(
        default=(),
        max_length=64,
    )
    original_key_evidence: RepairEvidenceStandard

    @model_validator(mode="after")
    def validate_context(self) -> RepairVerificationContext:
        ordered = tuple(sorted(self.original_intents, key=lambda item: item.intent_id))
        if (
            ordered != self.original_intents
            or len({item.intent_id for item in ordered}) != len(ordered)
            or self.target_intent.intent_id not in {item.intent_id for item in ordered}
            or self.must_remain_allow_control.intent.intent_id
            not in {item.intent_id for item in ordered}
            or any(
                item.intent.intent_id not in {identity.intent_id for identity in ordered}
                for item in self.must_remain_regression_controls
            )
            or self.must_disappear_effect_ids
            != tuple(sorted(set(self.must_disappear_effect_ids)))
        ):
            raise ValueError("repair verification context must preserve sorted original facts")
        control_keys = tuple(
            (item.intent.intent_id, item.action_id, item.subject_id)
            for item in self.must_remain_regression_controls
        )
        if control_keys != tuple(sorted(control_keys)) or len(set(control_keys)) != len(control_keys):
            raise ValueError("repair regression controls must be unique and sorted")
        return self


class PersistedExecutionRequest(BaseModel):
    """Worker 使用的不可变、无路径执行快照。"""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True, hide_input_in_errors=True)

    schema_version: Literal["2"] = "2"
    source_fingerprint: str = Field(pattern=SHA256_PATTERN)
    budget: ExecutionBudget
    permission_policy: PermissionPolicySnapshot
    project_snapshot: WebExecutionSnapshot
    change_context: ChangeVerificationContext | None = None
    repair_context: RepairVerificationContext | None = None

    @model_validator(mode="after")
    def validate_budget_snapshot(self) -> PersistedExecutionRequest:
        _validate_execution_request(self)
        return self


class LegacyPersistedExecutionRequest(BaseModel):
    """已发布历史结果的只读 v1 请求；新 Job 与 Worker 不接受该模型。"""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True, hide_input_in_errors=True)

    schema_version: Literal["1"] = "1"
    budget: ExecutionBudget
    permission_policy: PermissionPolicySnapshot
    project_snapshot: WebExecutionSnapshot
    change_context: LegacyChangeVerificationContext | None = None
    repair_context: RepairVerificationContext | None = None

    @model_validator(mode="after")
    def validate_budget_snapshot(self) -> LegacyPersistedExecutionRequest:
        _validate_execution_request(self)
        return self

    @property
    def source_fingerprint(self) -> None:
        """历史 v1 没有项目级源码身份，读取方不得从变化上下文补猜。"""

        return None


ExecutionRequestDocument = PersistedExecutionRequest | LegacyPersistedExecutionRequest


def canonical_execution_request_bytes(
    request: PersistedExecutionRequest,
    *,
    known_secrets: Sequence[str] = (),
) -> bytes:
    if not isinstance(request, PersistedExecutionRequest):
        raise TypeError("execution request serializer requires the current model")
    return _canonical_request_bytes(request, known_secrets=known_secrets)


def canonical_legacy_execution_request_bytes(
    request: LegacyPersistedExecutionRequest,
    *,
    known_secrets: Sequence[str] = (),
) -> bytes:
    """仅用于校验已发布 v1 请求仍是当时的 canonical JSON。"""

    if not isinstance(request, LegacyPersistedExecutionRequest):
        raise TypeError("legacy execution request serializer requires the legacy model")
    return _canonical_request_bytes(request, known_secrets=known_secrets)


def parse_execution_request(
    raw: bytes,
    *,
    known_secrets: Sequence[str] = (),
) -> ExecutionRequestDocument:
    if not isinstance(raw, bytes):
        raise TypeError("execution request parser requires bytes")
    if len(raw) > RUNNER_INPUT_MAX_BYTES or raw.startswith(b"\xef\xbb\xbf"):
        raise JiejianError(ErrorCode.JOB_REQUEST_CONFLICT, "任务执行请求格式无效")
    try:
        parsed = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_unique_object,
            parse_constant=_reject_nonfinite,
        )
        _reject_known_secrets(parsed, known_secrets)
        if not isinstance(parsed, dict) or parsed.get("schema_version") not in {"1", "2"}:
            raise ValueError("unsupported request schema version")
        model = (
            LegacyPersistedExecutionRequest
            if parsed["schema_version"] == "1"
            else PersistedExecutionRequest
        )
        return model.model_validate_json(raw, strict=True)
    except JiejianError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError, ValidationError):
        raise JiejianError(ErrorCode.JOB_REQUEST_CONFLICT, "任务执行请求格式无效") from None


def required_secret_names(request: ExecutionRequestDocument) -> tuple[str, ...]:
    return tuple(
        dict.fromkeys(
            reference.removeprefix("env:")
            for reference in required_web_secret_refs(request.project_snapshot)
        )
    )


def _canonical_request_bytes(
    request: BaseModel,
    *,
    known_secrets: Sequence[str],
) -> bytes:
    payload = request.model_dump(mode="json")
    _reject_known_secrets(payload, known_secrets)
    try:
        encoded = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError):
        raise JiejianError(ErrorCode.JOB_REQUEST_CONFLICT, "任务执行请求无法规范序列化") from None
    if len(encoded) > RUNNER_INPUT_MAX_BYTES:
        raise JiejianError(ErrorCode.JOB_REQUEST_CONFLICT, "任务执行请求超过大小限制")
    return encoded


def _validate_required_intent_ids(values: tuple[str, ...]) -> None:
    if (
        values != tuple(sorted(values))
        or len(set(values)) != len(values)
        or any(re.fullmatch(r"pin_[0-9a-f]{32}", intent_id) is None for intent_id in values)
    ):
        raise ValueError("change verification intent IDs must be unique and sorted")


def _validate_execution_request(request: Any) -> None:
    if request.permission_policy.project_id != request.project_snapshot.project_id:
        raise ValueError("permission policy project does not match snapshot")
    if request.change_context is not None and not set(
        request.change_context.required_intent_ids
    ).issubset({item.intent_id for item in request.permission_policy.entries}):
        raise ValueError("change verification intents must belong to the frozen policy")
    if request.repair_context is not None:
        if request.change_context is None:
            raise ValueError("repair verification requires a change verification context")
        current = {
            item.intent_id: (item.revision, item.intent_hash)
            for item in request.permission_policy.entries
        }
        original = {
            item.intent_id: (item.revision, item.intent_hash)
            for item in request.repair_context.original_intents
        }
        if request.permission_policy.policy_epoch != request.repair_context.original_policy_epoch or any(
            intent_id not in current or current[intent_id] != identity
            for intent_id, identity in original.items()
        ):
            raise ValueError("repair verification must use the original permission intents")
    target = request.project_snapshot.target.scope
    if request.budget.max_requests != target.max_requests:
        raise ValueError("request budget max_requests does not match snapshot")
    if request.budget.max_response_bytes != target.max_response_bytes:
        raise ValueError("request response budget does not match snapshot")
    if request.budget.request_timeout_us != int(target.timeout_seconds * 1_000_000):
        raise ValueError("request timeout does not match snapshot")
    if request.budget.max_cases < len(request.project_snapshot.plan.cases):
        raise ValueError("max_cases cannot be smaller than the permission plan")


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate key")
        result[key] = value
    return result


def _reject_nonfinite(value: str) -> None:
    if value in {"NaN", "Infinity", "-Infinity"} or not math.isfinite(float(value)):
        raise ValueError("non-finite number")


def _reject_known_secrets(value: Any, known_secrets: Sequence[str]) -> None:
    if any(not isinstance(secret, str) for secret in known_secrets):
        raise TypeError("known_secrets must contain strings")
    secrets = tuple(secret for secret in known_secrets if secret)
    pending = [value]
    while pending:
        item = pending.pop()
        if isinstance(item, str) and any(secret in item for secret in secrets):
            raise JiejianError(ErrorCode.JOB_SECRET, "任务执行请求包含敏感内容")
        if isinstance(item, Mapping):
            pending.extend(item.keys())
            pending.extend(item.values())
        elif isinstance(item, Sequence) and not isinstance(item, (str, bytes, bytearray)):
            pending.extend(item)
