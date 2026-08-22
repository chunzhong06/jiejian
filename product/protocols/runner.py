# =============================================================================
# Runner 与 Evidence 公共协议
#
# 定位
# Worker 与隔离 Runner 之间冻结项目快照、单 case 事实和 attempt 结果的 wire DTO。
#
# 职责
# 校验范围与预算｜约束 Evidence 完整性｜提供确定性 canonical 编码与 hash
#
# 边界
# 不执行请求、不保存原始凭据，不把生命周期与 Verdict 混合，也不维护并行旧协议投影。
#
# 调用链
# Worker ↔ Runner input/result files ↔ RunnerExecutor / publication
# =============================================================================

from __future__ import annotations

import hashlib
import ipaddress
import json
import math
import re
from collections.abc import Mapping, Sequence
from enum import StrEnum
from typing import Any, Literal, TypeAlias, TypeVar
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from product.backend.core.identifiers import JOB_ID_PATTERN, PROJECT_ID_PATTERN, RUN_ID_PATTERN, SHA256_PATTERN
from product.backend.core.lifecycle import CaseVerdict, JobState, RunLifecycle, RunVerdict
from product.backend.core.errors import JiejianError
from product.backend.core.verification.differential import DifferentialExperimentPlan, PermissionTwin, TwinExecutionRole
from product.backend.core.verification.permissions import PermissionContract
from product.backend.core.verification.permission_coverage import PermissionMutationCase, PermissionMutationPlan
from product.backend.core.verification.permissions import canonical_sha256
from product.backend.core.verification.facts import ExecutionFact, ExecutionOutcome, ObservationFact, ObservedEffect, SecurityEffectFact, TargetType
from product.protocols.observer import ObservationCompleteness, ObservationEnvelope, ObservationPhase, ObserverOutcome, ObserverSpec, ObserverType


RUNNER_INPUT_MAX_BYTES = 1_048_576
RUNNER_RESULT_MAX_BYTES = 4_194_304
EVIDENCE_MAX_BYTES = 4_194_304
STAGED_ARTIFACT_MAX_BYTES = 1_073_741_824
STAGED_ARTIFACT_TOTAL_MAX_BYTES = 1_073_741_824

_LEASE_OWNER = r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$"
_REASON_CODE = r"^[A-Z][A-Z0-9_]{0,127}$"
_HEX = r"^[0-9a-f]{64}$"
_TEXT = r"^[A-Za-z][A-Za-z0-9_.:-]{0,127}$"
_SECRET_KEY = re.compile(r"(?:authorization|cookie|credential|password|passwd|secret|token|api[_-]?key)", re.I)
_SAFE_SECRET_KEY_NAMES = frozenset({"fencing_token", "secret"})
_WINDOWS_DRIVE = re.compile(r"^[A-Za-z]:")
_FORBIDDEN_PATH_CHARS = frozenset('<>:"|?*')
_WINDOWS_RESERVED_NAMES = frozenset(
    {"con", "prn", "aux", "nul"} | {f"com{i}" for i in range(1, 10)} | {f"lpt{i}" for i in range(1, 10)}
)


class ProtocolModel(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True, hide_input_in_errors=True)
    schema_version: Literal["2"] = "2"


# HTTP 工作流模型复用本模块协议基类；延迟导入用于避免拆出第二套基类或形成循环依赖。
from .http import CASE_SUBJECT_IDENTITY, CookieSessionIdentityBinding, HttpIdentityBinding, HttpIdentityKind, HttpWorkflowBinding, IdentityBootstrapRequest, LoginWorkflowIdentityBinding, ValueSlotSource


class RunnerResultType(StrEnum):
    SUCCESS = "SUCCESS"
    SAFETY_STOPPED = "SAFETY_STOPPED"
    CANCELLED = "CANCELLED"
    RETRYABLE_ERROR = "RETRYABLE_ERROR"
    FATAL_ERROR = "FATAL_ERROR"


class CleanupStatus(StrEnum):
    NOT_REQUIRED = "NOT_REQUIRED"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"


class ResourceInjection(StrEnum):
    PATH_RESOURCE_ID = "PATH_RESOURCE_ID"
    JSON_RESOURCE_IDS = "JSON_RESOURCE_IDS"


# 冻结身份以受控 HTTP binding 表达运行时认证，不保存秘密值。
class ExecutionIdentity(ProtocolModel):
    """执行配置中的身份，只保存非秘密环境引用。"""

    schema_version: Literal["3"] = "3"
    identity_id: str = Field(pattern=PROJECT_ID_PATTERN)
    role: str = Field(min_length=1, max_length=64)
    label: str | None = Field(default=None, min_length=1, max_length=128)
    binding: HttpIdentityBinding
    bootstrap_requests: tuple[IdentityBootstrapRequest, ...] = Field(default=(), max_length=32)

    @model_validator(mode="after")
    def validate_bootstrap(self) -> ExecutionIdentity:
        ids = tuple(item.template_id for item in self.bootstrap_requests)
        if len(set(ids)) != len(ids):
            raise ValueError("identity bootstrap request IDs must be unique")
        if isinstance(self.binding, CookieSessionIdentityBinding):
            if ids != self.binding.bootstrap_template_ids or not ids:
                raise ValueError("COOKIE_SESSION bootstrap requests must exactly match declared template IDs")
        elif isinstance(self.binding, LoginWorkflowIdentityBinding):
            if not ids:
                raise ValueError("LOGIN_WORKFLOW requires frozen bootstrap requests")
        elif self.binding.kind in {
            HttpIdentityKind.BEARER,
            HttpIdentityKind.STATIC_HEADERS,
            HttpIdentityKind.OAUTH2_CLIENT_CREDENTIALS,
            HttpIdentityKind.OAUTH2_REFRESH_TOKEN,
        } and ids:
            raise ValueError("this identity kind cannot carry business-origin bootstrap requests")
        csrf_slot_id = getattr(self.binding, "csrf_slot_id", None)
        completed: set[str] = set()
        produced: dict[str, str] = {}
        prior_sources = {
            ValueSlotSource.PRIOR_STEP_JSON_PATH,
            ValueSlotSource.PRIOR_STEP_HEADER,
            ValueSlotSource.PRIOR_STEP_COOKIE,
            ValueSlotSource.PRIOR_STEP_LOCATION,
        }
        for request in self.bootstrap_requests:
            for slot in request.request_template.input_slots:
                if slot.source in {ValueSlotSource.CASE_SUBJECT_ID, ValueSlotSource.CASE_RESOURCE_ID}:
                    raise ValueError("identity bootstrap cannot consume business case slots")
                if slot.source in prior_sources and (
                    slot.producer_step_id not in completed
                    or produced.get(slot.slot_id) != slot.producer_step_id
                ):
                    raise ValueError("identity bootstrap slot must reference an earlier declared extractor")
            for extractor in request.request_template.response_extractors:
                produced[extractor.extractor_id] = request.template_id
            completed.add(request.template_id)
        if csrf_slot_id is not None:
            extractors = {
                item.extractor_id: item
                for request in self.bootstrap_requests
                for item in request.request_template.response_extractors
            }
            extractor = extractors.get(csrf_slot_id)
            if extractor is None or not extractor.secret:
                raise ValueError("CSRF slot must come from an explicitly secret bootstrap extractor")
        return self


class WebTargetScope(ProtocolModel):
    """Web 目标的协议级授权范围；不依赖 Core 的历史 TargetScope。"""

    base_url: str
    allowed_origins: tuple[str, ...]
    allowed_hosts: tuple[str, ...]
    allowed_ports: tuple[int, ...]
    allow_private_network: bool = False
    follow_redirects: Literal[False] = False
    timeout_seconds: float = Field(default=5.0, gt=0, le=30)
    max_requests: int = Field(default=64, ge=1, le=500)
    max_response_bytes: int = Field(default=262_144, ge=1, le=4_194_304)

    @field_validator("allowed_hosts")
    @classmethod
    def normalize_hosts(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(dict.fromkeys(value.strip().lower() for value in values))
        if not normalized or any(not value for value in normalized):
            raise ValueError("allowed_hosts must contain explicit hosts")
        try:
            return tuple(str(ipaddress.IPv4Address(value)) for value in normalized)
        except ipaddress.AddressValueError as exc:
            raise ValueError("allowed_hosts must be IPv4 literals") from exc

    @field_validator("allowed_ports")
    @classmethod
    def normalize_ports(cls, values: tuple[int, ...]) -> tuple[int, ...]:
        normalized = tuple(dict.fromkeys(values))
        if not normalized or any(port < 1 or port > 65535 for port in normalized):
            raise ValueError("allowed_ports must contain valid explicit ports")
        return normalized

    @model_validator(mode="after")
    def validate_scope(self) -> WebTargetScope:
        parsed = urlsplit(self.base_url)
        if parsed.scheme not in {"http", "https"} or parsed.username is not None or parsed.password is not None:
            raise ValueError("base_url must be an HTTP origin without user information")
        if parsed.hostname is None or parsed.path not in {"", "/"} or parsed.query or parsed.fragment:
            raise ValueError("base_url must be an origin without path, query, or fragment")
        try:
            port = parsed.port or (443 if parsed.scheme == "https" else 80)
            host = str(ipaddress.IPv4Address(parsed.hostname.lower()))
        except (ValueError, ipaddress.AddressValueError) as exc:
            raise ValueError("base_url must use an IPv4 literal and valid port") from exc
        if host not in self.allowed_hosts or port not in self.allowed_ports:
            raise ValueError("base_url is outside the declared host or port allowlist")
        origins: list[str] = []
        for raw_origin in self.allowed_origins:
            origin = urlsplit(raw_origin)
            if (
                origin.scheme not in {"http", "https"}
                or origin.hostname is None
                or origin.username is not None
                or origin.password is not None
                or origin.path not in {"", "/"}
                or origin.query
                or origin.fragment
            ):
                raise ValueError("allowed_origins must contain normalized HTTP origins")
            try:
                origin_port = origin.port or (443 if origin.scheme == "https" else 80)
                origin_host = str(ipaddress.IPv4Address(origin.hostname.lower()))
            except (ValueError, ipaddress.AddressValueError) as exc:
                raise ValueError("allowed_origins must use IPv4 literals and valid ports") from exc
            origins.append(f"{origin.scheme}://{origin_host}:{origin_port}")
        normalized_origins = tuple(dict.fromkeys(origins))
        if f"{parsed.scheme}://{host}:{port}" not in normalized_origins:
            raise ValueError("base_url origin is outside allowed_origins")
        if not self.allow_private_network and not ipaddress.IPv4Address(host).is_global:
            raise ValueError("private or local base_url requires explicit authorization")
        object.__setattr__(self, "base_url", self.base_url.rstrip("/"))
        object.__setattr__(self, "allowed_origins", normalized_origins)
        return self


class WebTargetDefinition(ProtocolModel):
    scope: WebTargetScope
    reset_path: str = Field(pattern=r"^/[A-Za-z0-9_./{}-]{1,255}$")


def _validate_reason_codes(values: tuple[str, ...], label: str) -> tuple[str, ...]:
    if len(set(values)) != len(values) or any(re.fullmatch(_REASON_CODE, value) is None for value in values):
        raise ValueError(f"{label} must contain unique stable codes")
    return tuple(sorted(values))


class ExecutionBudget(ProtocolModel):
    max_requests: int = Field(ge=1, le=500)
    request_timeout_us: int = Field(ge=1, le=30_000_000)
    max_duration_us: int = Field(ge=1, le=3_600_000_000)
    max_response_bytes: int = Field(ge=1, le=4_194_304)
    max_cases: int = Field(ge=1, le=8192)
    max_parallel_cases: Literal[1]


class SubjectExecutionBinding(ProtocolModel):
    subject_id: str = Field(pattern=PROJECT_ID_PATTERN)
    identity_id: str = Field(pattern=PROJECT_ID_PATTERN)


class ObserverRequirementKind(StrEnum):
    OBSERVER_SPEC = "OBSERVER_SPEC"


class EffectClosurePolicy(StrEnum):
    IMMEDIATE = "IMMEDIATE"
    TERMINAL_STATE = "TERMINAL_STATE"
    BOUNDED_QUIESCENCE = "BOUNDED_QUIESCENCE"
    EXCLUSIVE_CHANNEL_WINDOW = "EXCLUSIVE_CHANNEL_WINDOW"


# 把 Contract 安全效果绑定到权威通道与可选佐证通道，不暴露适配器实现。
class EffectBinding(ProtocolModel):
    schema_version: Literal["3"] = "3"
    effect_id: str = Field(pattern=PROJECT_ID_PATTERN)
    required_channels: tuple[str, ...] = Field(min_length=1, max_length=32)
    corroborating_channels: tuple[str, ...] = Field(default=(), max_length=32)
    closure_policy: EffectClosurePolicy
    projection_version: str = Field(pattern=_TEXT)

    @model_validator(mode="after")
    def validate_effect_binding(self) -> EffectBinding:
        if len(set(self.required_channels)) != len(self.required_channels):
            raise ValueError("required effect channels must be unique")
        if len(set(self.corroborating_channels)) != len(self.corroborating_channels):
            raise ValueError("corroborating effect channels must be unique")
        if set(self.required_channels) & set(self.corroborating_channels):
            raise ValueError("required and corroborating effect channels must be disjoint")
        return self


class ObserverRequirementBinding(ProtocolModel):
    requirement_id: str = Field(pattern=PROJECT_ID_PATTERN)
    kind: ObserverRequirementKind
    observer_id: str | None = Field(default=None, pattern=PROJECT_ID_PATTERN)
    observer_type: ObserverType | None = None
    credential_ref: str | None = Field(default=None, pattern=r"^env:[A-Z][A-Z0-9_]{0,127}$")
    phases: tuple[ObservationPhase, ...] = Field(default=(), max_length=5)

    @model_validator(mode="after")
    def validate_binding(self) -> ObserverRequirementBinding:
        if len(set(self.phases)) != len(self.phases):
            raise ValueError("observer binding phases must be unique")
        if any(phase not in {ObservationPhase.BASELINE, ObservationPhase.BEFORE, ObservationPhase.AFTER, ObservationPhase.EVENTUAL} for phase in self.phases):
            raise ValueError("Runner observer binding phases must be BASELINE, BEFORE, AFTER, or EVENTUAL")
        if self.observer_id is None or self.observer_type is None or not self.phases:
            raise ValueError("OBSERVER_SPEC binding requires an observer and phase window")
        return self


# 单次 Run 使用的目标、Contract、覆盖计划、身份和 Observer 冻结快照。
class ExecutionProjectSnapshot(ProtocolModel):
    schema_version: Literal["3"] = "3"
    project_id: str = Field(pattern=PROJECT_ID_PATTERN)
    project_name: str = Field(min_length=1, max_length=128)
    target_type: TargetType = TargetType.WEB
    target: WebTargetDefinition
    identities: tuple[ExecutionIdentity, ...] = Field(min_length=1, max_length=4096)
    contract: PermissionContract
    plan: PermissionMutationPlan
    differential_plan: DifferentialExperimentPlan
    observers: tuple[ObserverSpec, ...] = Field(default=(), max_length=256)
    subject_bindings: tuple[SubjectExecutionBinding, ...] = Field(min_length=1, max_length=4096)
    workflow_bindings: tuple[HttpWorkflowBinding, ...] = Field(min_length=1, max_length=4096)
    effect_bindings: tuple[EffectBinding, ...] = Field(min_length=1, max_length=4096)
    observer_bindings: tuple[ObserverRequirementBinding, ...] = Field(min_length=1, max_length=256)
    contract_fingerprint: str = Field(pattern=_HEX)
    plan_fingerprint: str = Field(pattern=_HEX)
    differential_fingerprint: str = Field(pattern=_HEX)

    @model_validator(mode="after")
    def validate_snapshot(self) -> ExecutionProjectSnapshot:
        identity_ids = {item.identity_id for item in self.identities}
        subject_ids = {item.subject_id for item in self.contract.subjects}
        resource_ids = {item.resource_id for item in self.contract.resources}
        action_map = {item.action_id: item for item in self.contract.actions}
        effect_ids = {item.effect_id for item in self.contract.effects}
        plan_cases = {item.case_id: item for item in self.plan.cases}
        case_actions = {case.action_id for case in self.plan.cases}
        if len(identity_ids) != len(self.identities):
            raise ValueError("snapshot identity IDs must be unique")
        if len({item.subject_id for item in self.subject_bindings}) != len(self.subject_bindings):
            raise ValueError("subject bindings must be unique")
        if len({item.action_id for item in self.workflow_bindings}) != len(self.workflow_bindings):
            raise ValueError("workflow bindings must be unique")
        if len({item.observer_id for item in self.observers}) != len(self.observers):
            raise ValueError("observer IDs must be unique")
        if len({item.requirement_id for item in self.observer_bindings}) != len(self.observer_bindings):
            raise ValueError("observer requirement IDs must be unique")
        if len({item.effect_id for item in self.effect_bindings}) != len(self.effect_bindings):
            raise ValueError("effect bindings must be unique")
        bound_observer_ids = [
            item.observer_id
            for item in self.observer_bindings
            if item.kind is ObserverRequirementKind.OBSERVER_SPEC
        ]
        if len(set(bound_observer_ids)) != len(bound_observer_ids):
            raise ValueError("an observer spec cannot serve multiple requirements")
        if self.contract_fingerprint != canonical_sha256(self.contract):
            raise ValueError("contract fingerprint does not match canonical contract")
        if self.plan_fingerprint != self.plan.plan_fingerprint:
            raise ValueError("plan fingerprint does not match plan")
        if self.differential_fingerprint != self.differential_plan.differential_fingerprint:
            raise ValueError("differential fingerprint does not match plan")
        if self.differential_plan.coverage_plan_fingerprint != self.plan.plan_fingerprint:
            raise ValueError("differential plan does not bind this coverage plan")
        if any(
            plan_cases.get(case.case_id) != case
            for twin in self.differential_plan.twins
            for case in (twin.allow_case, twin.deny_case)
        ):
            raise ValueError("differential twin cases must come from the frozen coverage plan")
        if self.plan.contract_fingerprint != self.contract_fingerprint:
            raise ValueError("plan contract fingerprint does not match snapshot")
        if not case_actions.issubset(action_map):
            raise ValueError("plan case action is not declared by contract")
        if not case_actions.issubset({item.action_id for item in self.workflow_bindings}):
            raise ValueError("workflow bindings must cover every plan case action")
        for binding in self.subject_bindings:
            if binding.subject_id not in subject_ids or binding.identity_id not in identity_ids:
                raise ValueError("subject binding must reference the contract subject and snapshot identity")
        if {item.subject_id for item in self.subject_bindings} != {case.subject_id for case in self.plan.cases}:
            raise ValueError("subject bindings must cover every plan subject")
        for binding in self.workflow_bindings:
            action = action_map[binding.action_id]
            if any(step.identity_id != CASE_SUBJECT_IDENTITY and step.identity_id not in identity_ids for step in binding.steps):
                raise ValueError("workflow step references an unknown identity")
            if action.is_batch and not binding.logical_resource_slots:
                raise ValueError("batch actions require a logical resource slot")
        spec_map = {item.observer_id: item for item in self.observers}
        requirement_map = {item.requirement_id: item for item in self.observer_bindings}
        effect_binding_map = {item.effect_id: item for item in self.effect_bindings}
        for workflow in self.workflow_bindings:
            target_step = next(step for step in workflow.steps if step.id == workflow.target_step_id)
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
        required_plan_observations = {requirement for case in self.plan.cases for requirement in case.required_observations}
        if not required_plan_observations.issubset(requirement_map):
            raise ValueError("observer bindings must cover every plan requirement")
        required_effect_ids = {effect_id for action_id in case_actions for effect_id in action_map[action_id].effect_ids}
        if required_effect_ids != set(effect_binding_map) or not required_effect_ids.issubset(effect_ids):
            raise ValueError("effect bindings must exactly cover every planned action effect")
        if any(channel not in requirement_map for binding in self.effect_bindings for channel in (*binding.required_channels, *binding.corroborating_channels)):
            raise ValueError("effect binding references an unknown observation requirement")
        for binding in self.observer_bindings:
            if binding.kind is ObserverRequirementKind.OBSERVER_SPEC:
                spec = spec_map.get(binding.observer_id or "")
                if spec is None or not spec.required or spec.observer_type is not binding.observer_type or not set(binding.phases).issubset(spec.phases):
                    raise ValueError("observer binding must reference a required spec with matching phases")
        bound_observer_ids = {item.observer_id for item in self.observer_bindings if item.kind is ObserverRequirementKind.OBSERVER_SPEC}
        if any(spec.required and spec.observer_id not in bound_observer_ids for spec in self.observers):
            raise ValueError("every required observer spec must have an explicit binding")
        if self.target_type is not TargetType.WEB:
            raise ValueError("only WEB target snapshots are executable in this release")
        _reject_secret_material(self.model_dump(mode="python"))
        return self


def required_secret_refs(snapshot: ExecutionProjectSnapshot) -> tuple[str, ...]:
    """返回  Runner 实际使用的非秘密 env 引用，调用方不得在此解析值。"""

    identity_ids = {item.identity_id for item in snapshot.subject_bindings}
    identity_ids.update(
        step.identity_id
        for workflow in snapshot.workflow_bindings
        for step in workflow.steps
        if step.identity_id != CASE_SUBJECT_IDENTITY
    )
    references: list[str] = []
    for identity in snapshot.identities:
        if identity.identity_id in identity_ids:
            references.extend(_binding_secret_refs(identity.binding.model_dump(mode="python")))
            references.extend(_binding_secret_refs(tuple(item.model_dump(mode="python") for item in identity.bootstrap_requests)))
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


def required_identity_secret_refs(identity: ExecutionIdentity) -> tuple[str, ...]:
    """返回单个 Web 身份在录制边界需要的 env 引用，不解析秘密值。"""

    references = list(_binding_secret_refs(identity.binding.model_dump(mode="python")))
    references.extend(
        _binding_secret_refs(
            tuple(item.model_dump(mode="python") for item in identity.bootstrap_requests)
        )
    )
    return tuple(dict.fromkeys(references))


def _binding_secret_refs(value: Any) -> tuple[str, ...]:
    found: list[str] = []
    pending = [value]
    while pending:
        item = pending.pop()
        if isinstance(item, Mapping):
            for key, child in item.items():
                if isinstance(key, str) and key.endswith("_ref") and isinstance(child, str):
                    found.append(child)
                pending.append(child)
        elif isinstance(item, (list, tuple)):
            pending.extend(item)
    return tuple(found)


class RunnerInput(ProtocolModel):
    schema_version: Literal["3"] = "3"
    run_id: str = Field(pattern=RUN_ID_PATTERN)
    job_id: str = Field(pattern=JOB_ID_PATTERN)
    attempt: int = Field(ge=1)
    lease_owner: str = Field(pattern=_LEASE_OWNER)
    fencing_token: int = Field(ge=1)
    created_at_us: int = Field(ge=0)
    budget: ExecutionBudget
    project_snapshot: ExecutionProjectSnapshot

    @model_validator(mode="after")
    def validate_budget(self) -> RunnerInput:
        target = self.project_snapshot.target.scope
        if self.budget.max_requests != target.max_requests or self.budget.max_response_bytes != target.max_response_bytes:
            raise ValueError(" execution budget must match the target snapshot")
        if self.budget.request_timeout_us != int(target.timeout_seconds * 1_000_000):
            raise ValueError(" request timeout must match the target snapshot")
        paired_case_ids = {
            case.case_id
            for twin in self.project_snapshot.differential_plan.twins
            for case in (twin.allow_case, twin.deny_case)
        }
        execution_case_count = 2 * len(self.project_snapshot.differential_plan.twins) + sum(
            case.case_id not in paired_case_ids for case in self.project_snapshot.plan.cases
        )
        if self.budget.max_cases < execution_case_count:
            raise ValueError("max_cases cannot be smaller than the differential execution plan")
        return self


# 单个 case 的不可变执行与观察事实，以及由确定性 Verification 给出的 Verdict。
class Evidence(ProtocolModel):
    schema_version: Literal["3"] = "3"
    evidence_id: str = Field(pattern=r"^ev_[0-9a-f]{20}$")
    run_id: str = Field(pattern=RUN_ID_PATTERN)
    case_snapshot: PermissionMutationCase
    twin_snapshot: PermissionTwin | None = None
    twin_role: TwinExecutionRole | None = None
    allow_control_valid: bool
    baseline_integrity: bool
    finding_pre_identity: str = Field(pattern=_HEX)
    execution_fact: ExecutionFact
    requirement_bindings: tuple[ObserverRequirementBinding, ...] = Field(default=(), max_length=16)
    observation_facts: tuple[ObservationFact, ...] = Field(default=(), max_length=19_200)
    security_effect_facts: tuple[SecurityEffectFact, ...] = Field(min_length=1, max_length=19_200)
    observations: tuple[ObservationEnvelope, ...] = Field(default=(), max_length=19_200)
    outcomes: tuple[ObserverOutcome, ...] = Field(default=(), max_length=64)
    verdict: CaseVerdict
    reason_codes: tuple[str, ...] = Field(default=(), max_length=64)
    evidence_hash: str = Field(pattern=_HEX)

    @model_validator(mode="after")
    def validate_evidence(self) -> Evidence:
        observations = tuple(sorted(self.observations, key=lambda item: (item.observer_id, item.phase.value, item.correlation.resource_id)))
        outcomes = tuple(sorted(self.outcomes, key=lambda item: item.observer_id))
        if len({(item.observer_id, item.phase, item.correlation.resource_id) for item in observations}) != len(observations):
            raise ValueError("evidence observations must have unique observer, phase, and resource")
        if len({item.observer_id for item in outcomes}) != len(outcomes):
            raise ValueError("evidence outcomes must have unique observer IDs")
        binding_map = {item.requirement_id: item for item in self.requirement_bindings}
        case_requirements = set(self.case_snapshot.required_observations)
        if len(binding_map) != len(self.requirement_bindings) or set(binding_map) != case_requirements:
            raise ValueError("evidence bindings must exactly cover this case requirements")
        if (self.twin_snapshot is None) != (self.twin_role is None):
            raise ValueError("twin snapshot and role must be present together")
        if self.twin_snapshot is not None:
            expected_case = self.twin_snapshot.allow_case if self.twin_role is TwinExecutionRole.ALLOW_CONTROL else self.twin_snapshot.deny_case
            if expected_case != self.case_snapshot:
                raise ValueError("evidence case does not match its twin role")
        observer_bindings = {
            item.requirement_id: item
            for item in self.requirement_bindings
            if item.kind is ObserverRequirementKind.OBSERVER_SPEC
        }
        if any(item.required is not True for item in outcomes):
            raise ValueError("evidence outcomes must describe required observers")
        if {item.observer_id for item in observer_bindings.values()} != {item.observer_id for item in outcomes}:
            raise ValueError("evidence outcomes must exactly cover bound observers")
        bound_observer_ids = {item.observer_id for item in observer_bindings.values()}
        if any(item.observer_id not in bound_observer_ids for item in observations):
            raise ValueError("evidence observation references an unbound observer")
        outcome_map = {item.observer_id: item for item in outcomes}
        for requirement, binding in observer_bindings.items():
            assert binding.observer_id is not None
            bound_observations = tuple(item for item in observations if item.observer_id == binding.observer_id)
            expected_keys = {
                (binding.observer_id, phase, resource_id)
                for resource_id in self.case_snapshot.resource_ids
                for phase in binding.phases
            }
            actual_keys = {
                (item.observer_id, item.phase, item.correlation.resource_id)
                for item in bound_observations
            }
            if any(item.phase not in binding.phases for item in bound_observations):
                raise ValueError("evidence contains an observer phase outside its binding")
            if any(item.observer_type is not binding.observer_type for item in bound_observations):
                raise ValueError("evidence observer type does not match its binding")
            if outcome_map[binding.observer_id].status.value == "AVAILABLE" and actual_keys != expected_keys:
                raise ValueError("available observer outcome requires every resource and phase")
            if outcome_map[binding.observer_id].status.value == "AVAILABLE" and not bound_observations:
                raise ValueError("available outcome requires an observation envelope")
        for envelope in observations:
            correlation = envelope.correlation
            if correlation.case_id != self.case_snapshot.case_id or correlation.resource_id not in self.case_snapshot.resource_ids:
                raise ValueError("observation correlation does not match the case snapshot")
            if envelope.completeness is ObservationCompleteness.COMPLETE and envelope.causality.value != "CORRELATED":
                raise ValueError("complete evidence observation must be correlated")
        confirmed_effect = any(item.state is ObservedEffect.CONFIRMED for item in self.security_effect_facts)
        unavailable_required = any(item.status.value != "AVAILABLE" for item in outcomes)
        failed_request = self.execution_fact.outcome in {ExecutionOutcome.FAILED, ExecutionOutcome.UNKNOWN}
        if (unavailable_required or failed_request) and self.verdict is not CaseVerdict.INCONCLUSIVE and not (self.verdict is CaseVerdict.VULNERABLE and confirmed_effect):
            raise ValueError("incomplete required observation can only produce INCONCLUSIVE evidence")
        if self.verdict not in {CaseVerdict.SAFE, CaseVerdict.VULNERABLE, CaseVerdict.INCONCLUSIVE}:
            raise ValueError(" evidence verdict must be SAFE, VULNERABLE, or INCONCLUSIVE")
        expected_fact_keys = {
            (requirement, resource_id)
            for requirement in case_requirements
            for resource_id in self.case_snapshot.resource_ids
        }
        actual_fact_keys = {
            (item.requirement_id, item.resource_id)
            for item in self.observation_facts
        }
        if len(actual_fact_keys) != len(self.observation_facts) or actual_fact_keys != expected_fact_keys:
            raise ValueError("evidence observation facts must exactly cover every requirement and resource")
        effect_keys = {(item.effect_id, item.resource_id) for item in self.security_effect_facts}
        expected_effect_keys = {
            (effect_id, resource_id)
            for effect_id in {
                effect_id
                for action_id in {self.case_snapshot.action_id}
                for effect_id in (
                    item.effect_id
                    for item in self.security_effect_facts
                    if item.effect_id
                )
            }
            for resource_id in self.case_snapshot.resource_ids
        }
        if len(effect_keys) != len(self.security_effect_facts) or effect_keys != expected_effect_keys:
            raise ValueError("evidence effect facts must uniquely cover every effect and resource")
        safe_effect_state = (
            ObservedEffect.CONFIRMED
            if self.twin_role is TwinExecutionRole.ALLOW_CONTROL
            or all(item.value == "ALLOW" for item in self.case_snapshot.expectations)
            else ObservedEffect.ABSENT
        )
        if self.verdict is CaseVerdict.SAFE and (
            failed_request
            or not self.baseline_integrity
            or not self.allow_control_valid
            or any(item.state is not safe_effect_state for item in self.security_effect_facts)
        ):
            raise ValueError("safe evidence requires a valid control, baseline, and role-appropriate effects")
        if self.verdict is CaseVerdict.VULNERABLE and not confirmed_effect and self.execution_fact.outcome is not ExecutionOutcome.ACCEPTED:
            raise ValueError("vulnerable evidence requires accepted execution or a confirmed effect")
        if self.finding_pre_identity != self.case_snapshot.finding_pre_identity:
            raise ValueError("finding_pre_identity must match the case snapshot")
        normalized_reasons = _validate_reason_codes(self.reason_codes, "evidence reason_codes")
        object.__setattr__(self, "observations", observations)
        object.__setattr__(self, "outcomes", outcomes)
        object.__setattr__(self, "observation_facts", tuple(sorted(self.observation_facts, key=lambda item: (item.requirement_id, item.resource_id))))
        object.__setattr__(self, "reason_codes", normalized_reasons)
        expected = _sha256_json(_evidence_semantic_payload(self))
        if self.evidence_id != f"ev_{expected[:20]}" or self.evidence_hash != expected:
            raise ValueError("evidence_hash does not match the evidence semantic payload")
        return self


def _evidence_semantic_payload(evidence: Evidence) -> dict[str, Any]:
    payload = evidence.model_dump(mode="json")
    payload.pop("evidence_id", None)
    payload.pop("evidence_hash", None)
    payload["observations"] = sorted(
        payload.get("observations", ()),
        key=lambda item: (item["observer_id"], item["phase"], item["correlation"]["resource_id"]),
    )
    payload["outcomes"] = sorted(payload.get("outcomes", ()), key=lambda item: item["observer_id"])
    return payload


def build_evidence(**fields: Any) -> Evidence:
    """构造内容寻址 Evidence，统一计算语义 hash 和 evidence_id。"""

    if "evidence_id" in fields or "evidence_hash" in fields:
        raise TypeError("build_evidence computes evidence_id and evidence_hash")
    semantic_payload = _jsonable(fields)
    semantic_payload["observations"] = sorted(
        semantic_payload.get("observations", ()),
        key=lambda item: (item["observer_id"], item["phase"], item["correlation"]["resource_id"]),
    )
    semantic_payload["outcomes"] = sorted(semantic_payload.get("outcomes", ()), key=lambda item: item["observer_id"])
    expected = _sha256_json(semantic_payload)
    return Evidence(
        **fields,
        evidence_id=f"ev_{expected[:20]}",
        evidence_hash=expected,
    )


class CleanupResult(ProtocolModel):
    status: CleanupStatus
    reason_codes: tuple[str, ...] = Field(default=(), max_length=64)

    @model_validator(mode="after")
    def validate_cleanup(self) -> CleanupResult:
        reasons = _validate_reason_codes(self.reason_codes, "cleanup reason_codes")
        if self.status is CleanupStatus.FAILED and not reasons:
            raise ValueError("failed cleanup requires a reason")
        if self.status is not CleanupStatus.FAILED and reasons:
            raise ValueError("successful cleanup cannot contain a reason")
        object.__setattr__(self, "reason_codes", reasons)
        return self


class RunnerError(ProtocolModel):
    code: str = Field(pattern=_REASON_CODE)
    retryable: bool


class StagedArtifact(ProtocolModel):
    path: str = Field(min_length=1, max_length=512)
    byte_count: int = Field(ge=0, le=STAGED_ARTIFACT_MAX_BYTES)
    sha256: str = Field(pattern=SHA256_PATTERN)

    @field_validator("path")
    @classmethod
    def validate_path(cls, value: str) -> str:
        segments = value.split("/")
        if (
            value.startswith("/")
            or _WINDOWS_DRIVE.match(value)
            or "\\" in value
            or any(character in _FORBIDDEN_PATH_CHARS for character in value)
            or any(segment in {"", ".", ".."} for segment in segments)
            or any(ord(character) < 32 for character in value)
            or any(len(segment) > 255 for segment in segments)
            or any(segment.endswith((".", " ")) for segment in segments)
            or any(segment.split(".", 1)[0].rstrip(" .").casefold() in _WINDOWS_RESERVED_NAMES for segment in segments)
        ):
            raise ValueError("artifact path must be normalized and relative")
        return value


# 一次 attempt 的生命周期结果、聚合 Verdict、Evidence 与 staging 工件清单。
class RunnerResult(ProtocolModel):
    run_id: str = Field(pattern=RUN_ID_PATTERN)
    job_id: str = Field(pattern=JOB_ID_PATTERN)
    attempt: int = Field(ge=1)
    lease_owner: str = Field(pattern=_LEASE_OWNER)
    fencing_token: int = Field(ge=1)
    finished_at_us: int = Field(ge=0)
    result_type: RunnerResultType
    run_lifecycle: RunLifecycle
    job_state: JobState
    verdict: RunVerdict | None
    reason_codes: tuple[str, ...] = Field(default=(), max_length=128)
    cleanup: CleanupResult
    error: RunnerError | None
    plan_fingerprint: str = Field(pattern=_HEX)
    coverage_record_count: int = Field(ge=0, le=16384)
    coverage_gap_count: int = Field(ge=0, le=16384)
    evidence: tuple[Evidence, ...] = Field(default=(), max_length=8192)
    artifacts: tuple[StagedArtifact, ...] = Field(default=(), max_length=8192)

    @model_validator(mode="after")
    def validate_result(self) -> RunnerResult:
        reasons = _validate_reason_codes(self.reason_codes, "result reason_codes")
        allowed_cleanup = {CleanupStatus.NOT_REQUIRED, CleanupStatus.SUCCEEDED}
        if self.result_type is RunnerResultType.SUCCESS:
            valid = (
                self.run_lifecycle is RunLifecycle.COMPLETED
                and self.job_state is JobState.SUCCEEDED
                and self.error is None
                and self.cleanup.status in allowed_cleanup
            )
            if valid and self.coverage_gap_count > 0:
                valid = self.verdict is RunVerdict.INCONCLUSIVE
            elif valid:
                valid = bool(self.evidence)
                aggregate = (
                    RunVerdict.BLOCK
                    if any(item.verdict is CaseVerdict.VULNERABLE for item in self.evidence)
                    else RunVerdict.INCONCLUSIVE
                    if any(item.verdict is CaseVerdict.INCONCLUSIVE for item in self.evidence)
                    else RunVerdict.PASS
                )
                valid = self.verdict is aggregate
        elif self.result_type is RunnerResultType.SAFETY_STOPPED:
            valid = self.run_lifecycle is RunLifecycle.SAFETY_STOPPED and self.job_state is JobState.SUCCEEDED and self.verdict is None and self.error is None and bool(reasons) and self.cleanup.status in allowed_cleanup
        elif self.result_type is RunnerResultType.CANCELLED:
            valid = self.run_lifecycle is RunLifecycle.CANCELLED and self.job_state is JobState.CANCELLED and self.verdict is None and self.error is None and self.cleanup.status is CleanupStatus.SUCCEEDED
        elif self.result_type is RunnerResultType.RETRYABLE_ERROR:
            valid = self.run_lifecycle in {RunLifecycle.PREFLIGHT, RunLifecycle.PLANNING, RunLifecycle.EXECUTING, RunLifecycle.VERIFYING, RunLifecycle.REPORTING} and self.job_state is JobState.RETRY_WAIT and self.verdict is None and self.error is not None and self.error.retryable and self.cleanup.status in allowed_cleanup
        else:
            valid = self.run_lifecycle is RunLifecycle.FAILED and self.job_state is JobState.FAILED and self.verdict is None and self.error is not None and not self.error.retryable and self.cleanup.status in {CleanupStatus.NOT_REQUIRED, CleanupStatus.SUCCEEDED, CleanupStatus.FAILED}
        if not valid:
            raise ValueError("runner  result violates the lifecycle and verdict matrix")
        if any(item.run_id != self.run_id for item in self.evidence):
            raise ValueError("evidence run_id must match the runner result")
        execution_keys = {
            (
                item.case_snapshot.case_id,
                item.twin_snapshot.twin_id if item.twin_snapshot is not None else None,
                item.twin_role,
            )
            for item in self.evidence
        }
        if len(execution_keys) != len(self.evidence):
            raise ValueError("runner result evidence executions must be unique")
        if len({item.path.casefold() for item in self.artifacts}) != len(self.artifacts):
            raise ValueError("artifact paths must be case-insensitively unique")
        if sum(item.byte_count for item in self.artifacts) > STAGED_ARTIFACT_TOTAL_MAX_BYTES:
            raise ValueError("artifact total exceeds the limit")
        object.__setattr__(self, "reason_codes", reasons)
        _reject_secret_material(self.model_dump(mode="python"))
        return self


ProtocolDocument: TypeAlias = RunnerInput | RunnerResult | Evidence
ProtocolT = TypeVar("ProtocolT", RunnerInput, RunnerResult, Evidence)


def _jsonable(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return _jsonable(value.model_dump(mode="python"))
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_jsonable(item) for item in value]
    return value


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(_jsonable(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def _sha256_json(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _reject_secret_material(value: Any) -> None:
    pending = [value]
    while pending:
        item = pending.pop()
        if isinstance(item, str):
            if item.startswith("env:"):
                continue
            if re.search(r"\bBearer\s+\S+|\b(?:authorization|cookie|password|passwd|secret|token|api[_-]?key)\s*[:=]\s*\S+", item, re.I):
                raise ValueError(" protocol contains inline secret material")
        elif isinstance(item, Mapping):
            for key, child in item.items():
                if str(key) not in _SAFE_SECRET_KEY_NAMES and _SECRET_KEY.search(str(key)) and not str(key).endswith("_ref"):
                    raise ValueError(" protocol contains an inline secret field")
                pending.extend((key, child))
        elif isinstance(item, Sequence) and not isinstance(item, (bytes, bytearray, str)):
            pending.extend(item)


def canonical_runner_json_bytes(document: ProtocolDocument, *, known_secrets: Sequence[str] = ()) -> bytes:
    if not isinstance(document, (RunnerInput, RunnerResult, Evidence)):
        raise TypeError("canonical JSON only accepts a Runner  document")
    if any(not isinstance(secret, str) for secret in known_secrets):
        raise TypeError("known_secrets must contain only strings")
    data = _jsonable(document)
    _reject_secret_material(data)
    for secret in known_secrets:
        if secret and secret in json.dumps(data, ensure_ascii=False, sort_keys=True):
            raise JiejianError("PROTOCOL_SECRET_EXPOSED", " protocol contains known secret material")
    encoded = _canonical_bytes(data)
    maximum = RUNNER_INPUT_MAX_BYTES if isinstance(document, RunnerInput) else RUNNER_RESULT_MAX_BYTES
    if isinstance(document, Evidence):
        maximum = EVIDENCE_MAX_BYTES
    if len(encoded) > maximum:
        raise JiejianError("PROTOCOL_TOO_LARGE", "Runner  document exceeds its size limit")
    return encoded


def canonical_runner_sha256(document: ProtocolDocument, *, known_secrets: Sequence[str] = ()) -> str:
    return hashlib.sha256(canonical_runner_json_bytes(document, known_secrets=known_secrets)).hexdigest()


def _reject_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(" JSON contains duplicate keys")
        result[key] = value
    return result


def _reject_nonfinite(value: str) -> None:
    raise ValueError(" JSON contains a non-finite number")


def _parse_(raw: bytes, model: type[ProtocolT], maximum: int, label: str, known_secrets: Sequence[str]) -> ProtocolT:
    if not isinstance(raw, bytes):
        raise TypeError(" parser requires bytes")
    if len(raw) > maximum or raw.startswith(b"\xef\xbb\xbf"):
        raise JiejianError("PROTOCOL_INVALID", f"{label} is oversized or contains a BOM")
    try:
        parsed = json.loads(raw.decode("utf-8"), object_pairs_hook=_reject_pairs, parse_constant=_reject_nonfinite)
        if not isinstance(parsed, dict):
            raise ValueError(" root must be an object")
        _reject_secret_material(parsed)
        if any(secret and secret in raw.decode("utf-8") for secret in known_secrets):
            raise JiejianError("PROTOCOL_SECRET_EXPOSED", f"{label} contains known secret material")
        return model.model_validate_json(raw)
    except JiejianError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError, ValidationError) as exc:
        raise JiejianError("PROTOCOL_INVALID", f"{label} is not a valid strict  document", details={"reason": type(exc).__name__}) from None


def parse_runner_input(raw: bytes, *, known_secrets: Sequence[str] = ()) -> RunnerInput:
    return _parse_(raw, RunnerInput, RUNNER_INPUT_MAX_BYTES, "Runner  input", known_secrets)


def parse_runner_result(raw: bytes, *, known_secrets: Sequence[str] = ()) -> RunnerResult:
    return _parse_(raw, RunnerResult, RUNNER_RESULT_MAX_BYTES, "Runner  result", known_secrets)


def parse_evidence(raw: bytes, *, known_secrets: Sequence[str] = ()) -> Evidence:
    return _parse_(raw, Evidence, EVIDENCE_MAX_BYTES, "Evidence ", known_secrets)
