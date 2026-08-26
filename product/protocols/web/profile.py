# =============================================================================
# Web 执行 Profile 协议
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
# Profile source → ExecutionWorkflow → WebExecutionSnapshot / ExecutionRequest
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
from product.backend.core.verification.differential import (
    DifferentialExperimentPlan,
    build_differential_experiment_plan,
)
from product.backend.core.verification.facts import TargetType
from product.backend.core.verification.permissions.coverage import PermissionMutationPlan
from product.backend.core.verification.permissions import PermissionContract, permission_model_sha256
from product.protocols.execution import (
    EffectBinding,
    ObserverRequirementBinding,
    ObserverRequirementKind,
    ProtocolModel,
    SubjectExecutionBinding,
)
from product.protocols.observer import ObserverSpec, ObserverType, ObservationPhase
from product.protocols.web.identity import WebExecutionIdentity, binding_secret_refs
from product.protocols.web.target import WebTargetDefinition
from product.protocols.web.workflow import (
    CASE_SUBJECT_IDENTITY,
    HttpWorkflowBinding,
)


WEB_EXECUTION_PROFILE_MAX_BYTES = 1_048_576
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


class WebExecutionSnapshot(ProtocolModel):
    """单次 Web Run 的目标、Contract、计划、身份和观察冻结快照。"""

    project_id: str = Field(pattern=_PROFILE_ID.pattern)
    project_name: str = Field(min_length=1, max_length=128)
    target_type: TargetType = TargetType.WEB
    target: WebTargetDefinition
    identities: tuple[WebExecutionIdentity, ...] = Field(
        min_length=1, max_length=4096
    )
    contract: PermissionContract
    plan: PermissionMutationPlan
    differential_plan: DifferentialExperimentPlan
    observers: tuple[ObserverSpec, ...] = Field(default=(), max_length=256)
    subject_bindings: tuple[SubjectExecutionBinding, ...] = Field(
        min_length=1, max_length=4096
    )
    workflow_bindings: tuple[HttpWorkflowBinding, ...] = Field(
        min_length=1, max_length=4096
    )
    effect_bindings: tuple[EffectBinding, ...] = Field(
        min_length=1, max_length=4096
    )
    observer_bindings: tuple[ObserverRequirementBinding, ...] = Field(
        min_length=1, max_length=256
    )
    contract_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    plan_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    differential_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_snapshot(self) -> WebExecutionSnapshot:
        identity_ids = {item.identity_id for item in self.identities}
        subject_ids = {item.subject_id for item in self.contract.subjects}
        action_map = {item.action_id: item for item in self.contract.actions}
        effect_ids = {item.effect_id for item in self.contract.effects}
        plan_cases = {item.case_id: item for item in self.plan.cases}
        case_actions = {case.action_id for case in self.plan.cases}
        if len(identity_ids) != len(self.identities):
            raise ValueError("snapshot identity IDs must be unique")
        if len({item.subject_id for item in self.subject_bindings}) != len(
            self.subject_bindings
        ):
            raise ValueError("subject bindings must be unique")
        if len({item.action_id for item in self.workflow_bindings}) != len(
            self.workflow_bindings
        ):
            raise ValueError("workflow bindings must be unique")
        if len({item.observer_id for item in self.observers}) != len(self.observers):
            raise ValueError("observer IDs must be unique")
        if len({item.requirement_id for item in self.observer_bindings}) != len(
            self.observer_bindings
        ):
            raise ValueError("observer requirement IDs must be unique")
        if len({item.effect_id for item in self.effect_bindings}) != len(
            self.effect_bindings
        ):
            raise ValueError("effect bindings must be unique")
        bound_observer_ids = [
            item.observer_id
            for item in self.observer_bindings
            if item.kind is ObserverRequirementKind.OBSERVER_SPEC
        ]
        if len(set(bound_observer_ids)) != len(bound_observer_ids):
            raise ValueError("an observer spec cannot serve multiple requirements")
        if self.contract_fingerprint != permission_model_sha256(self.contract):
            raise ValueError("contract fingerprint does not match canonical contract")
        if self.plan_fingerprint != self.plan.plan_fingerprint:
            raise ValueError("plan fingerprint does not match plan")
        if (
            self.differential_fingerprint
            != self.differential_plan.differential_fingerprint
        ):
            raise ValueError("differential fingerprint does not match plan")
        if self.differential_plan.coverage_plan_fingerprint != self.plan.plan_fingerprint:
            raise ValueError("differential plan does not bind this coverage plan")
        if any(
            plan_cases.get(case.case_id) != case
            for twin in self.differential_plan.twins
            for case in (twin.allow_case, twin.deny_case)
        ):
            raise ValueError(
                "differential twin cases must come from the frozen coverage plan"
            )
        if self.plan.contract_fingerprint != self.contract_fingerprint:
            raise ValueError("plan contract fingerprint does not match snapshot")
        if not case_actions.issubset(action_map):
            raise ValueError("plan case action is not declared by contract")
        if not case_actions.issubset(
            {item.action_id for item in self.workflow_bindings}
        ):
            raise ValueError("workflow bindings must cover every plan case action")
        for binding in self.subject_bindings:
            if (
                binding.subject_id not in subject_ids
                or binding.identity_id not in identity_ids
            ):
                raise ValueError(
                    "subject binding must reference the contract subject and snapshot identity"
                )
        if {item.subject_id for item in self.subject_bindings} != {
            case.subject_id for case in self.plan.cases
        }:
            raise ValueError("subject bindings must cover every plan subject")
        for binding in self.workflow_bindings:
            action = action_map[binding.action_id]
            if any(
                step.identity_id != CASE_SUBJECT_IDENTITY
                and step.identity_id not in identity_ids
                for step in binding.steps
            ):
                raise ValueError("workflow step references an unknown identity")
            if action.is_batch and not binding.logical_resource_slots:
                raise ValueError("batch actions require a logical resource slot")
        spec_map = {item.observer_id: item for item in self.observers}
        requirement_map = {
            item.requirement_id: item for item in self.observer_bindings
        }
        effect_binding_map = {item.effect_id: item for item in self.effect_bindings}
        for workflow in self.workflow_bindings:
            target_step = next(
                step for step in workflow.steps if step.id == workflow.target_step_id
            )
            completion_id = target_step.classifier.completion_binding
            if completion_id is None:
                continue
            completion = requirement_map.get(completion_id)
            if (
                completion is None
                or completion.observer_type is not ObserverType.ASYNC_TASK_STATUS
                or ObservationPhase.EVENTUAL not in completion.phases
            ):
                raise ValueError(
                    "HTTP completion binding must reference an EVENTUAL async task observer"
                )
        required_plan_observations = {
            requirement
            for case in self.plan.cases
            for requirement in case.required_observations
        }
        if not required_plan_observations.issubset(requirement_map):
            raise ValueError("observer bindings must cover every plan requirement")
        required_effect_ids = {
            effect_id
            for action_id in case_actions
            for effect_id in action_map[action_id].effect_ids
        }
        if (
            required_effect_ids != set(effect_binding_map)
            or not required_effect_ids.issubset(effect_ids)
        ):
            raise ValueError(
                "effect bindings must exactly cover every planned action effect"
            )
        if any(
            channel not in requirement_map
            for binding in self.effect_bindings
            for channel in (
                *binding.required_channels,
                *binding.corroborating_channels,
            )
        ):
            raise ValueError("effect binding references an unknown observation requirement")
        for binding in self.observer_bindings:
            spec = spec_map.get(binding.observer_id or "")
            if (
                spec is None
                or not spec.required
                or spec.observer_type is not binding.observer_type
                or not set(binding.phases).issubset(spec.phases)
            ):
                raise ValueError(
                    "observer binding must reference a required spec with matching phases"
                )
            if binding.identity_id is not None and binding.identity_id not in identity_ids:
                raise ValueError("observer binding references an unknown prepared identity")
        bound_ids = {item.observer_id for item in self.observer_bindings}
        if any(
            spec.required and spec.observer_id not in bound_ids
            for spec in self.observers
        ):
            raise ValueError(
                "every required observer spec must have an explicit binding"
            )
        if self.target_type is not TargetType.WEB:
            raise ValueError("only WEB target snapshots are executable in this release")
        _reject_secret_material(self.model_dump(mode="python"))
        return self


def required_web_secret_refs(snapshot: WebExecutionSnapshot) -> tuple[str, ...]:
    """返回 Web Runner 实际使用的非秘密环境引用。"""

    identity_ids = {item.identity_id for item in snapshot.subject_bindings}
    identity_ids.update(
        step.identity_id
        for workflow in snapshot.workflow_bindings
        for step in workflow.steps
        if step.identity_id != CASE_SUBJECT_IDENTITY
    )
    identity_ids.update(
        binding.identity_id
        for binding in snapshot.observer_bindings
        if binding.identity_id is not None
    )
    references: list[str] = []
    for identity in snapshot.identities:
        if identity.identity_id in identity_ids:
            references.extend(
                binding_secret_refs(identity.binding.model_dump(mode="python"))
            )
            references.extend(
                binding_secret_refs(
                    tuple(
                        item.model_dump(mode="python")
                        for item in identity.bootstrap_requests
                    )
                )
            )
    references.extend(
        binding.credential_ref
        for binding in snapshot.observer_bindings
        if binding.credential_ref is not None
    )
    for spec in snapshot.observers:
        locator = spec.target.locator
        references.extend(
            value
            for name in (
                "database_secret_ref",
                "authorized_root_ref",
                "read_only_credential_ref",
                "read_only_sas_ref",
            )
            if (value := getattr(locator, name, None)) is not None
        )
    return tuple(dict.fromkeys(references))


class WebExecutionProfile(BaseModel):
    """完整、无秘密的 Web 权限执行配置。"""

    model_config = ConfigDict(
        strict=True,
        frozen=True,
        extra="forbid",
        hide_input_in_errors=True,
    )

    schema_version: Literal["1"] = "1"
    profile_id: str = Field(pattern=_PROFILE_ID.pattern)
    project_id: str = Field(pattern=_PROFILE_ID.pattern)
    project_name: str = Field(min_length=1, max_length=128)
    target_type: TargetType = TargetType.WEB
    target: WebTargetDefinition
    identities: tuple[WebExecutionIdentity, ...] = Field(
        min_length=1, max_length=4096
    )
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
    def validate_profile(self) -> WebExecutionProfile:
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
    ) -> WebExecutionSnapshot:
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
            action.action_id: permission_model_sha256(
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
            observer_fingerprint=permission_model_sha256((self.observers, self.observer_bindings, self.effect_bindings)),
            baseline_fingerprints={action_id: permission_model_sha256(workflow.baseline_projections) for action_id, workflow in workflow_by_action.items()},
            normalization_version=next(iter(normalization_versions)),
        )
        return WebExecutionSnapshot(
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
    from product.backend.core.verification.permissions import permission_model_sha256

    return permission_model_sha256(contract)


def _reject_secret_material(value: Any) -> None:
    pending: list[tuple[tuple[str | int, ...], Any]] = [((), value)]
    while pending:
        path, item = pending.pop()
        if isinstance(item, Mapping):
            for key, child in item.items():
                child_path = (*path, key)
                if (
                    isinstance(key, str)
                    and not (key == "secret" and isinstance(child, bool))
                    and not key.endswith("_ref")
                    # 这里只放行严格身份模型中的 Cookie 描述集合；集合内部仍递归检查，
                    # 任意流程正文或其他位置出现同名字段仍按敏感字段拒绝。
                    and not _is_prepared_cookie_descriptor_path(child_path)
                    and _SECRET_KEY.search(key)
                ):
                    raise ValueError("profile contains a sensitive field")
                pending.append((child_path, child))
        elif isinstance(item, (list, tuple)):
            pending.extend(((*path, index), child) for index, child in enumerate(item))
        elif isinstance(item, float) and not math.isfinite(item):
            raise ValueError("profile contains a non-finite number")
        elif isinstance(item, str) and not item.startswith("env:") and _INLINE_SECRET.search(item):
            raise ValueError("profile contains inline sensitive material")


def _is_prepared_cookie_descriptor_path(path: tuple[str | int, ...]) -> bool:
    """只识别类型化身份绑定中的 Cookie 元数据集合。"""

    return (
        len(path) == 4
        and path[0] == "identities"
        and isinstance(path[1], int)
        and path[2:] == ("binding", "cookies")
    )


def canonical_web_execution_profile_json_bytes(
    profile: WebExecutionProfile,
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


def web_execution_profile_sha256(
    profile: WebExecutionProfile,
    *,
    known_secrets: Sequence[str] = (),
) -> str:
    return hashlib.sha256(
        canonical_web_execution_profile_json_bytes(
            profile,
            known_secrets=known_secrets,
        )
    ).hexdigest()


def parse_web_execution_profile(
    raw: bytes,
    *,
    known_secrets: Sequence[str] = (),
) -> WebExecutionProfile:
    if len(raw) > WEB_EXECUTION_PROFILE_MAX_BYTES:
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
        if data.get("schema_version") != "1":
            raise ValueError("profile schema_version is missing or unsupported")
        # 先用 json.loads 只做重复键/根类型检查，再由 Pydantic 的 JSON
        # strict parser 保留 tuple 等 JSON 数组到严格模型的合法转换。
        profile = WebExecutionProfile.model_validate_json(raw, strict=True)
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
