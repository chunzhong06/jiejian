# =============================================================================
# 修复要求与独立复验模型
#
# 定位
#   把一次已发布 BLOCK 中不可降低的权限考题、业务后果和证据标准冻结为只读修复要求。
#
# 职责
#   约束 RepairContract｜形成稳定引用与指纹｜表达独立于安全 Verdict 的复验三态。
#
# 边界
#   不包含文件、代码位置或补丁建议，不批准权限变化，也不执行目标或重新计算安全 Verdict。
#
# 调用链
#   Published result → RepairContractService → Change / ExecutionRequest / Result
# =============================================================================

from __future__ import annotations

import hashlib
import json
import re
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from product.backend.core.identifiers import PROJECT_ID_PATTERN, RUN_ID_PATTERN, SHA256_PATTERN


_FINDING_ID_PATTERN = r"^finding_[0-9a-f]{32}$"
_INTENT_ID_PATTERN = r"^pin_[0-9a-f]{32}$"
_PUBLIC_ID_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9_.:/-]{0,159}$"
_REASON_CODE = re.compile(r"^[A-Z][A-Z0-9_]{0,127}$")


class RepairModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        strict=True,
        hide_input_in_errors=True,
    )


class RepairContractReference(RepairModel):
    source_run_id: str = Field(pattern=RUN_ID_PATTERN)
    source_finding_id: str = Field(pattern=_FINDING_ID_PATTERN)
    repair_fingerprint: str = Field(pattern=SHA256_PATTERN)


class RepairIntentIdentity(RepairModel):
    intent_id: str = Field(pattern=_INTENT_ID_PATTERN)
    revision: int = Field(ge=1)
    intent_hash: str = Field(pattern=SHA256_PATTERN)


class RepairAllowControlIdentity(RepairModel):
    intent: RepairIntentIdentity
    action_id: str = Field(pattern=_PUBLIC_ID_PATTERN)
    subject_id: str = Field(pattern=_PUBLIC_ID_PATTERN)
    case_fingerprint: str = Field(pattern=SHA256_PATTERN)


# 这类路径不属于漏洞孪生，但修复后仍必须保持原 ALLOW 语义。
class RepairRegressionControlIdentity(RepairModel):
    intent: RepairIntentIdentity
    action_id: str = Field(pattern=_PUBLIC_ID_PATTERN)
    subject_id: str = Field(pattern=_PUBLIC_ID_PATTERN)
    subject_display_name: str = Field(min_length=1, max_length=160)
    action_display_name: str = Field(min_length=1, max_length=160)
    case_fingerprint: str = Field(pattern=SHA256_PATTERN)
    protected_effect_ids: tuple[str, ...] = Field(min_length=1, max_length=64)
    key_evidence: RepairEvidenceStandard

    @field_validator("protected_effect_ids")
    @classmethod
    def validate_effects(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if values != tuple(sorted(values)) or len(set(values)) != len(values):
            raise ValueError("repair regression effects must be unique and sorted")
        return values


class RepairEvidenceStandard(RepairModel):
    requirement_ids: tuple[str, ...] = Field(min_length=1, max_length=64)
    fingerprint: str = Field(pattern=SHA256_PATTERN)

    @field_validator("requirement_ids")
    @classmethod
    def validate_requirements(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if (
            values != tuple(sorted(values))
            or len(set(values)) != len(values)
            or any(re.fullmatch(_PUBLIC_ID_PATTERN, value) is None for value in values)
        ):
            raise ValueError("repair evidence requirements must be unique and sorted")
        return values


class RepairContract(RepairModel):
    source_run_id: str = Field(pattern=RUN_ID_PATTERN)
    source_finding_id: str = Field(pattern=_FINDING_ID_PATTERN)
    project_id: str = Field(pattern=PROJECT_ID_PATTERN)
    original_policy_epoch: int = Field(ge=0)
    intent: RepairIntentIdentity
    original_intents: tuple[RepairIntentIdentity, ...] = Field(min_length=2, max_length=4096)
    deny_action_id: str = Field(pattern=_PUBLIC_ID_PATTERN)
    deny_subject_id: str = Field(pattern=_PUBLIC_ID_PATTERN)
    resource_ids: tuple[str, ...] = Field(min_length=1, max_length=256)
    resource_relation: tuple[str, ...] = Field(min_length=1, max_length=128)
    protected_effect_ids: tuple[str, ...] = Field(min_length=1, max_length=64)
    allow_control: RepairAllowControlIdentity
    regression_controls: tuple[RepairRegressionControlIdentity, ...] = Field(
        default=(),
        max_length=64,
    )
    key_evidence: RepairEvidenceStandard
    authorization_continuity_state: Literal["ORPHAN_EFFECT_CONFIRMED"]
    orphan_effect_ids: tuple[str, ...] = Field(min_length=1, max_length=64)
    primary_breakpoint: Literal[
        "AUTHORIZATION_MISSING",
        "AUTHORIZATION_LATE",
        "AUTHORIZATION_BYPASS",
        "IDENTITY_SUBSTITUTION",
        "AUTHORITY_EXPANSION",
        "COMPENSATION_MASKING",
    ] | None
    breakpoint_precision: Literal["EXACT", "RANGE", "VIOLATION_ONLY"]
    amplifier_types: tuple[str, ...] = Field(default=(), max_length=5)
    must_disappear: str = Field(min_length=1, max_length=320)
    must_remain: str = Field(min_length=1, max_length=320)
    must_not_change: tuple[str, ...] = Field(min_length=2, max_length=8)
    repair_fingerprint: str = Field(pattern=SHA256_PATTERN)

    @field_validator("original_intents")
    @classmethod
    def validate_original_intents(
        cls,
        values: tuple[RepairIntentIdentity, ...],
    ) -> tuple[RepairIntentIdentity, ...]:
        if (
            values != tuple(sorted(values, key=lambda item: item.intent_id))
            or len({item.intent_id for item in values}) != len(values)
        ):
            raise ValueError("repair contract intents must be unique and sorted")
        return values

    @field_validator(
        "resource_ids",
        "resource_relation",
        "protected_effect_ids",
        "orphan_effect_ids",
        "amplifier_types",
        "must_not_change",
    )
    @classmethod
    def validate_sorted_unique(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if values != tuple(sorted(values)) or len(set(values)) != len(values):
            raise ValueError("repair contract collections must be unique and sorted")
        return values

    @model_validator(mode="after")
    def validate_contract(self) -> RepairContract:
        identities = {item.intent_id for item in self.original_intents}
        if (
            self.intent.intent_id not in identities
            or self.allow_control.intent.intent_id not in identities
            or any(item.intent.intent_id not in identities for item in self.regression_controls)
            or not set(self.orphan_effect_ids).issubset(self.protected_effect_ids)
            or self.repair_fingerprint != repair_contract_fingerprint(self)
        ):
            raise ValueError("repair contract identity or fingerprint is inconsistent")
        control_keys = tuple(
            (item.intent.intent_id, item.action_id, item.subject_id)
            for item in self.regression_controls
        )
        if control_keys != tuple(sorted(control_keys)) or len(set(control_keys)) != len(control_keys):
            raise ValueError("repair regression controls must be unique and sorted")
        if self.primary_breakpoint is None and self.breakpoint_precision != "VIOLATION_ONLY":
            raise ValueError("unlocated repair breakpoint must be VIOLATION_ONLY")
        if self.primary_breakpoint is not None and self.primary_breakpoint in self.amplifier_types:
            raise ValueError("repair primary breakpoint cannot also be an amplifier")
        return self

    @property
    def reference(self) -> RepairContractReference:
        return RepairContractReference(
            source_run_id=self.source_run_id,
            source_finding_id=self.source_finding_id,
            repair_fingerprint=self.repair_fingerprint,
        )


class RepairRequirementView(RepairModel):
    reference: RepairContractReference
    must_disappear: str = Field(min_length=1, max_length=320)
    must_remain: str = Field(min_length=1, max_length=320)
    must_not_change: tuple[str, ...] = Field(min_length=2, max_length=8)


class RepairVerificationStatus(StrEnum):
    VERIFIED = "VERIFIED"
    NOT_VERIFIED = "NOT_VERIFIED"
    INCONCLUSIVE = "INCONCLUSIVE"


class RepairPathKind(StrEnum):
    DENY_EFFECT_REMOVAL = "DENY_EFFECT_REMOVAL"
    ALLOW_CONTROL = "ALLOW_CONTROL"
    REGRESSION_CONTROL = "REGRESSION_CONTROL"


# 路径结果只拆解总复验的既有事实，不引入第二套 Verdict。
class RepairPathVerification(RepairModel):
    kind: RepairPathKind
    action_id: str = Field(pattern=_PUBLIC_ID_PATTERN)
    subject_id: str = Field(pattern=_PUBLIC_ID_PATTERN)
    subject_display_name: str = Field(min_length=1, max_length=160)
    action_display_name: str = Field(min_length=1, max_length=160)
    status: RepairVerificationStatus
    message: str = Field(min_length=1, max_length=320)
    evidence_refs: tuple[str, ...] = Field(default=(), max_length=64)
    reason_codes: tuple[str, ...] = Field(min_length=1, max_length=32)

    @field_validator("evidence_refs")
    @classmethod
    def validate_evidence_refs(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if values != tuple(sorted(values)) or len(set(values)) != len(values):
            raise ValueError("repair path evidence refs must be unique and sorted")
        return values

    @field_validator("reason_codes")
    @classmethod
    def validate_reason_codes(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        return _validate_reason_codes(values, "repair path")


class RepairVerification(RepairModel):
    reference: RepairContractReference
    verification_run_id: str = Field(pattern=RUN_ID_PATTERN)
    status: RepairVerificationStatus
    message: str = Field(min_length=1, max_length=320)
    reason_codes: tuple[str, ...] = Field(min_length=1, max_length=32)
    path_results: tuple[RepairPathVerification, ...] = Field(default=(), max_length=66)

    @field_validator("reason_codes")
    @classmethod
    def validate_reason_codes(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        return _validate_reason_codes(values, "repair verification")

    @model_validator(mode="after")
    def validate_path_results(self) -> RepairVerification:
        keys = tuple((item.kind.value, item.action_id, item.subject_id) for item in self.path_results)
        if keys != tuple(sorted(keys)) or len(set(keys)) != len(keys):
            raise ValueError("repair path results must be unique and sorted")
        return self


def _validate_reason_codes(values: tuple[str, ...], label: str) -> tuple[str, ...]:
    if (
        values != tuple(sorted(values))
        or len(set(values)) != len(values)
        or any(_REASON_CODE.fullmatch(value) is None for value in values)
    ):
        raise ValueError(f"{label} reason codes must be stable sorted tokens")
    return values


def repair_contract_fingerprint(contract: RepairContract | dict[str, Any]) -> str:
    payload = (
        contract.model_dump(mode="json", exclude={"repair_fingerprint"})
        if isinstance(contract, RepairContract)
        else _jsonable(
            {key: value for key, value in contract.items() if key != "repair_fingerprint"}
        )
    )
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _jsonable(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, tuple | list):
        return [_jsonable(item) for item in value]
    return value


__all__ = [
    "RepairAllowControlIdentity",
    "RepairContract",
    "RepairContractReference",
    "RepairEvidenceStandard",
    "RepairIntentIdentity",
    "RepairPathKind",
    "RepairPathVerification",
    "RepairRegressionControlIdentity",
    "RepairRequirementView",
    "RepairVerification",
    "RepairVerificationStatus",
    "repair_contract_fingerprint",
]
