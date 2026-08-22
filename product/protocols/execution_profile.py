# =============================================================================
# 权限执行 Profile 协议
#
# 定位
# 用户治理源文件进入冻结执行快照前的无秘密高级配置真源。
#
# 职责
# 校验目标与身份绑定｜约束预算和 Observer｜规范化加载并生成确定性摘要
#
# 边界
# 完整 Profile 只存在受控源文件，数据库只保存治理元数据；协议不读取秘密或执行目标。
#
# 调用链
# Profile source → ExecutionWorkflow → ExecutionProjectSnapshot / ExecutionRequest
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
from product.backend.core.verification.differential import build_differential_experiment_plan
from .http import HttpWorkflowBinding
from .runner import EffectBinding, ExecutionIdentity, ExecutionProjectSnapshot, ObserverRequirementBinding, ObserverSpec, SubjectExecutionBinding, TargetType, WebTargetDefinition
from product.backend.core.verification.permission_coverage import PermissionMutationPlan
from product.backend.core.verification.permissions import PermissionContract, canonical_sha256


EXECUTION_PROFILE_MAX_BYTES = 1_048_576
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


class ExecutionProfile(BaseModel):
    """完整、无秘密的  权限执行配置；不含运行时 Job 或结果字段。"""

    model_config = ConfigDict(
        strict=True,
        frozen=True,
        extra="forbid",
        hide_input_in_errors=True,
    )

    schema_version: Literal["3"] = "3"
    profile_id: str = Field(pattern=_PROFILE_ID.pattern)
    project_id: str = Field(pattern=_PROFILE_ID.pattern)
    project_name: str = Field(min_length=1, max_length=128)
    target_type: TargetType = TargetType.WEB
    target: WebTargetDefinition
    identities: tuple[ExecutionIdentity, ...] = Field(min_length=1, max_length=4096)
    contract_id: str = Field(pattern=_PROFILE_ID.pattern)
    contract_version: int = Field(ge=1)
    observers: tuple[ObserverSpec, ...] = Field(default=(), max_length=256)
    subject_bindings: tuple[SubjectExecutionBinding, ...] = Field(min_length=1, max_length=4096)
    workflow_bindings: tuple[HttpWorkflowBinding, ...] = Field(min_length=1, max_length=4096)
    effect_bindings: tuple[EffectBinding, ...] = Field(min_length=1, max_length=4096)
    observer_bindings: tuple[ObserverRequirementBinding, ...] = Field(min_length=1, max_length=256)
    seed: int = Field(ge=0, le=9_223_372_036_854_775_807)
    case_budget: int = Field(ge=1, le=8192)
    max_relation_depth: int = Field(ge=1, le=64)
    max_duration_us: int = Field(ge=1, le=3_600_000_000)

    @model_validator(mode="after")
    def validate_profile(self) -> ExecutionProfile:
        if len({item.identity_id for item in self.identities}) != len(self.identities):
            raise ValueError("profile identity IDs must be unique")
        if len({item.observer_id for item in self.observers}) != len(self.observers):
            raise ValueError("profile observer IDs must be unique")
        if len({item.effect_id for item in self.effect_bindings}) != len(self.effect_bindings):
            raise ValueError("profile effect bindings must be unique")
        _reject_secret_material(self.model_dump(mode="python"))
        return self

    def build_snapshot(
        self,
        contract: PermissionContract,
        plan: PermissionMutationPlan,
        *,
        target_override: WebTargetDefinition | None = None,
        workflow_bindings_override: tuple[HttpWorkflowBinding, ...] | None = None,
    ) -> ExecutionProjectSnapshot:
        """让 Runner 唯一快照校验器执行全部跨引用检查。"""

        bindings = self.workflow_bindings if workflow_bindings_override is None else workflow_bindings_override
        target = self.target if target_override is None else target_override
        if self.target_type is not TargetType.WEB:
            raise ValueError("only WEB execution profiles are supported")
        if contract.contract_id != self.contract_id or contract.version != self.contract_version:
            raise ValueError("profile contract reference does not match the governed snapshot")
        workflow_by_action = {item.action_id: item for item in bindings}
        effects_by_id = {item.effect_id: item for item in contract.effects}
        effect_binding_by_id = {item.effect_id: item for item in self.effect_bindings}
        planned_actions = {case.action_id for case in plan.cases}
        planned_effect_ids = {
            effect_id
            for action in contract.actions
            if action.action_id in planned_actions
            for effect_id in action.effect_ids
        }
        if planned_effect_ids != set(effect_binding_by_id):
            raise ValueError("profile effect bindings must exactly cover planned action effects")
        action_effect_fingerprints = {
            action.action_id: canonical_sha256(
                tuple((effects_by_id[effect_id], effect_binding_by_id[effect_id]) for effect_id in action.effect_ids)
            )
            for action in contract.actions
            if action.action_id in planned_actions
        }
        normalization_versions = {
            projection.normalization_version
            for workflow in bindings
            for projection in workflow.baseline_projections
        }
        if len(normalization_versions) != 1:
            raise ValueError("differential execution requires one frozen normalization version")
        differential_plan = build_differential_experiment_plan(
            contract,
            plan,
            workflow_fingerprints={action_id: workflow.workflow_fingerprint or "" for action_id, workflow in workflow_by_action.items()},
            effect_fingerprints=action_effect_fingerprints,
            observer_fingerprint=canonical_sha256((self.observers, self.observer_bindings, self.effect_bindings)),
            baseline_fingerprints={action_id: canonical_sha256(workflow.baseline_projections) for action_id, workflow in workflow_by_action.items()},
            normalization_version=next(iter(normalization_versions)),
        )
        return ExecutionProjectSnapshot(
            project_id=self.project_id,
            project_name=self.project_name,
            target_type=self.target_type,
            target=target,
            identities=self.identities,
            contract=contract,
            plan=plan,
            differential_plan=differential_plan,
            observers=self.observers,
            subject_bindings=self.subject_bindings,
            workflow_bindings=bindings,
            effect_bindings=self.effect_bindings,
            observer_bindings=self.observer_bindings,
            contract_fingerprint=_contract_fingerprint(contract),
            plan_fingerprint=plan.plan_fingerprint,
            differential_fingerprint=differential_plan.differential_fingerprint,
        )


def _contract_fingerprint(contract: PermissionContract) -> str:
    from product.backend.core.verification.permissions import canonical_sha256

    return canonical_sha256(contract)


def _reject_secret_material(value: Any) -> None:
    pending = [value]
    while pending:
        item = pending.pop()
        if isinstance(item, Mapping):
            for key, child in item.items():
                if (
                    isinstance(key, str)
                    and not (key == "secret" and isinstance(child, bool))
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


def canonical_execution_profile_json_bytes(
    profile: ExecutionProfile,
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
        raise JiejianError(ErrorCode.EXECUTION_PROFILE_INVALID, "Profile 规范化失败") from None


def execution_profile_sha256(
    profile: ExecutionProfile,
    *,
    known_secrets: Sequence[str] = (),
) -> str:
    return hashlib.sha256(
        canonical_execution_profile_json_bytes(profile, known_secrets=known_secrets)
    ).hexdigest()


def parse_execution_profile(
    raw: bytes,
    *,
    known_secrets: Sequence[str] = (),
) -> ExecutionProfile:
    if len(raw) > EXECUTION_PROFILE_MAX_BYTES:
        raise JiejianError(ErrorCode.EXECUTION_PROFILE_INVALID, "Profile 超过大小限制")
    if raw.startswith(b"\xef\xbb\xbf"):
        raise JiejianError(ErrorCode.EXECUTION_PROFILE_INVALID, "Profile 不接受 BOM")

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
        profile = ExecutionProfile.model_validate_json(raw, strict=True)
        _reject_secret_values(profile.model_dump(mode="json"), known_secrets)
        return profile
    except JiejianError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError, ValidationError):
        raise JiejianError(ErrorCode.EXECUTION_PROFILE_INVALID, "Profile 文件无效") from None


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
            raise JiejianError(ErrorCode.EXECUTION_PROFILE_INVALID, "Profile 包含敏感内容")
