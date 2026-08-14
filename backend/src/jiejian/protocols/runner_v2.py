# =============================================================================
# Runner V2 / Evidence V2 公共协议
#
# 定位：冻结 V2 输入快照、单用例事实和 Runner 结果的独立 wire DTO。
# 本模块只校验结构、引用、完整性和确定性编码，不执行请求、不保存原始凭据，
# 也不把 V2 投影为 Runner V1。
# =============================================================================

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Mapping, Sequence
from enum import StrEnum
from typing import Any, Literal, TypeAlias, TypeVar
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from ..domain.identifiers import JOB_ID_PATTERN, PROJECT_ID_PATTERN, RUN_ID_PATTERN, SHA256_PATTERN
from ..domain.lifecycle import CaseVerdict, JobState, RunLifecycle, RunVerdict
from ..errors import JiejianError
from ..verification.models import Flow, Identity, TargetScope
from ..verification.permission_coverage import PermissionMutationCaseV2, PermissionMutationPlanV2
from ..verification.permissions import PermissionContractV2, canonical_sha256
from .observer_v2 import ObservationCompleteness, ObservationEnvelopeV2, ObservationPhase, ObserverOutcomeV2, ObserverSpecV2, ObserverType


RUNNER_V2_INPUT_MAX_BYTES = 1_048_576
RUNNER_V2_RESULT_MAX_BYTES = 4_194_304
EVIDENCE_V2_MAX_BYTES = 4_194_304
STAGED_ARTIFACT_V2_MAX_BYTES = 1_073_741_824
STAGED_ARTIFACT_V2_TOTAL_MAX_BYTES = 1_073_741_824

_LEASE_OWNER = r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$"
_REASON_CODE = r"^[A-Z][A-Z0-9_]{0,127}$"
_HEX = r"^[0-9a-f]{64}$"
_TEXT = r"^[A-Za-z][A-Za-z0-9_.:-]{0,127}$"
_SECRET_KEY = re.compile(r"(?:authorization|cookie|credential|password|passwd|secret|token|api[_-]?key)", re.I)
_SAFE_SECRET_KEY_NAMES = frozenset({"fencing_token"})
_WINDOWS_DRIVE = re.compile(r"^[A-Za-z]:")
_FORBIDDEN_PATH_CHARS = frozenset('<>:"|?*')
_WINDOWS_RESERVED_NAMES = frozenset(
    {"con", "prn", "aux", "nul"} | {f"com{i}" for i in range(1, 10)} | {f"lpt{i}" for i in range(1, 10)}
)


class RunnerV2Model(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True, hide_input_in_errors=True)
    schema_version: Literal["2"] = "2"


class RunnerResultTypeV2(StrEnum):
    SUCCESS = "SUCCESS"
    SAFETY_STOPPED = "SAFETY_STOPPED"
    CANCELLED = "CANCELLED"
    RETRYABLE_ERROR = "RETRYABLE_ERROR"
    FATAL_ERROR = "FATAL_ERROR"


class CleanupStatusV2(StrEnum):
    NOT_REQUIRED = "NOT_REQUIRED"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"


class ResourceInjectionV2(StrEnum):
    PATH_RESOURCE_ID = "PATH_RESOURCE_ID"
    JSON_RESOURCE_IDS = "JSON_RESOURCE_IDS"


def _validate_reason_codes(values: tuple[str, ...], label: str) -> tuple[str, ...]:
    if len(set(values)) != len(values) or any(re.fullmatch(_REASON_CODE, value) is None for value in values):
        raise ValueError(f"{label} must contain unique stable codes")
    return tuple(sorted(values))


class ExecutionBudgetV2(RunnerV2Model):
    max_requests: int = Field(ge=1, le=500)
    request_timeout_us: int = Field(ge=1, le=30_000_000)
    max_duration_us: int = Field(ge=1, le=3_600_000_000)
    max_response_bytes: int = Field(ge=1, le=4_194_304)
    max_cases: int = Field(ge=1, le=8192)
    max_parallel_cases: Literal[1]


class SubjectExecutionBindingV2(RunnerV2Model):
    subject_id: str = Field(pattern=PROJECT_ID_PATTERN)
    identity_id: str = Field(pattern=PROJECT_ID_PATTERN)


class ActionExecutionBindingV2(RunnerV2Model):
    action_id: str = Field(pattern=PROJECT_ID_PATTERN)
    flow_step_id: str = Field(pattern=PROJECT_ID_PATTERN)
    resource_injection: ResourceInjectionV2


class ObserverRequirementKindV2(StrEnum):
    REQUEST_FACT = "REQUEST_FACT"
    OBSERVER_SPEC = "OBSERVER_SPEC"


class ObserverRequirementBindingV2(RunnerV2Model):
    requirement_id: str = Field(pattern=PROJECT_ID_PATTERN)
    kind: ObserverRequirementKindV2
    observer_id: str | None = Field(default=None, pattern=PROJECT_ID_PATTERN)
    observer_type: ObserverType | None = None
    owner_api_credential_ref: str | None = Field(default=None, pattern=r"^env:[A-Z][A-Z0-9_]{0,127}$")
    phases: tuple[ObservationPhase, ...] = Field(default=(), max_length=5)

    @model_validator(mode="after")
    def validate_binding(self) -> ObserverRequirementBindingV2:
        if len(set(self.phases)) != len(self.phases):
            raise ValueError("observer binding phases must be unique")
        if any(phase not in {ObservationPhase.BEFORE, ObservationPhase.AFTER, ObservationPhase.EVENTUAL} for phase in self.phases):
            raise ValueError("Runner V2 observer binding phases must be BEFORE, AFTER, or EVENTUAL")
        if self.kind is ObserverRequirementKindV2.REQUEST_FACT:
            if self.requirement_id != "http" or self.observer_id is not None or self.observer_type is not None or self.owner_api_credential_ref is not None or self.phases:
                raise ValueError("REQUEST_FACT binding is the fixed http requirement")
        elif self.observer_id is None or self.observer_type is None or not self.phases:
            raise ValueError("OBSERVER_SPEC binding requires an observer and phase window")
        elif self.observer_type is ObserverType.OWNER_API and self.owner_api_credential_ref is None:
            raise ValueError("OWNER_API binding requires owner_api_credential_ref")
        elif self.observer_type is not ObserverType.OWNER_API and self.owner_api_credential_ref is not None:
            raise ValueError("owner_api_credential_ref is only valid for OWNER_API bindings")
        return self


class ExecutionProjectSnapshotV2(RunnerV2Model):
    project_id: str = Field(pattern=PROJECT_ID_PATTERN)
    project_name: str = Field(min_length=1, max_length=128)
    target: TargetScope
    identities: tuple[Identity, ...] = Field(min_length=1, max_length=4096)
    flow: Flow
    contract: PermissionContractV2
    plan: PermissionMutationPlanV2
    observers: tuple[ObserverSpecV2, ...] = Field(default=(), max_length=256)
    subject_bindings: tuple[SubjectExecutionBindingV2, ...] = Field(min_length=1, max_length=4096)
    action_bindings: tuple[ActionExecutionBindingV2, ...] = Field(min_length=1, max_length=4096)
    observer_bindings: tuple[ObserverRequirementBindingV2, ...] = Field(min_length=1, max_length=256)
    contract_fingerprint: str = Field(pattern=_HEX)
    plan_fingerprint: str = Field(pattern=_HEX)

    @model_validator(mode="after")
    def validate_snapshot(self) -> ExecutionProjectSnapshotV2:
        identity_ids = {item.id for item in self.identities}
        subject_ids = {item.subject_id for item in self.contract.subjects}
        resource_ids = {item.resource_id for item in self.contract.resources}
        step_map = {item.id: item for item in self.flow.steps}
        action_map = {item.action_id: item for item in self.contract.actions}
        case_actions = {case.action_id for case in self.plan.cases}
        if len(identity_ids) != len(self.identities):
            raise ValueError("snapshot identity IDs must be unique")
        if len({item.subject_id for item in self.subject_bindings}) != len(self.subject_bindings):
            raise ValueError("subject bindings must be unique")
        if len({item.action_id for item in self.action_bindings}) != len(self.action_bindings):
            raise ValueError("action bindings must be unique")
        if len({item.observer_id for item in self.observers}) != len(self.observers):
            raise ValueError("observer IDs must be unique")
        if len({item.requirement_id for item in self.observer_bindings}) != len(self.observer_bindings):
            raise ValueError("observer requirement IDs must be unique")
        bound_observer_ids = [
            item.observer_id
            for item in self.observer_bindings
            if item.kind is ObserverRequirementKindV2.OBSERVER_SPEC
        ]
        if len(set(bound_observer_ids)) != len(bound_observer_ids):
            raise ValueError("an observer spec cannot serve multiple requirements")
        if self.contract_fingerprint != canonical_sha256(self.contract):
            raise ValueError("contract fingerprint does not match canonical contract")
        if self.plan_fingerprint != self.plan.plan_fingerprint:
            raise ValueError("plan fingerprint does not match plan")
        if self.plan.contract_fingerprint != self.contract_fingerprint:
            raise ValueError("plan contract fingerprint does not match snapshot")
        if not case_actions.issubset(action_map):
            raise ValueError("plan case action is not declared by contract")
        if not case_actions.issubset({item.action_id for item in self.action_bindings}):
            raise ValueError("action bindings must cover every plan case action")
        if any(step_id not in step_map for item in self.action_bindings for step_id in (item.flow_step_id,)):
            raise ValueError("action binding references an undeclared flow step")
        if any(identity_id not in identity_ids for step in self.flow.steps for identity_id in (step.identity_id, step.alternate_identity_id)):
            raise ValueError("flow identity is outside the snapshot")
        if any(resource_id not in resource_ids for step in self.flow.steps for resource_id in (step.resource_id, step.alternate_resource_id)):
            raise ValueError("flow resource is outside the permission contract")
        for binding in self.subject_bindings:
            if binding.subject_id not in subject_ids or binding.identity_id not in identity_ids:
                raise ValueError("subject binding must reference the contract subject and snapshot identity")
        if {item.subject_id for item in self.subject_bindings} != {case.subject_id for case in self.plan.cases}:
            raise ValueError("subject bindings must cover every plan subject")
        for binding in self.action_bindings:
            action = action_map[binding.action_id]
            step = step_map[binding.flow_step_id]
            parsed_path = urlsplit(step.path)
            if parsed_path.query or parsed_path.fragment:
                raise ValueError("flow action path cannot contain query or fragment")
            if binding.flow_step_id not in action.flow_step_ids:
                raise ValueError("action binding step is not declared by the action")
            batch = any(case.action_id == binding.action_id and len(case.resource_ids) > 1 for case in self.plan.cases)
            if batch != action.is_batch:
                raise ValueError("action batch declaration does not match the plan")
            if batch:
                if binding.resource_injection is not ResourceInjectionV2.JSON_RESOURCE_IDS:
                    raise ValueError("batch actions require JSON_RESOURCE_IDS injection")
                if step.json_body.get("resource_ids") not in ("{resource_ids}", ["{resource_ids}"]):
                    raise ValueError("batch flow step must expose the fixed resource_ids placeholder")
            elif binding.resource_injection is not ResourceInjectionV2.PATH_RESOURCE_ID or step.path.count("{resource_id}") != 1:
                raise ValueError("ordinary actions require one PATH_RESOURCE_ID placeholder")
        spec_map = {item.observer_id: item for item in self.observers}
        requirement_map = {item.requirement_id: item for item in self.observer_bindings}
        required_plan_observers = {observer for case in self.plan.cases for observer in case.required_observers}
        if not required_plan_observers.issubset(requirement_map):
            raise ValueError("observer bindings must cover every plan requirement")
        for binding in self.observer_bindings:
            if binding.kind is ObserverRequirementKindV2.OBSERVER_SPEC:
                spec = spec_map.get(binding.observer_id or "")
                if spec is None or not spec.required or spec.observer_type is not binding.observer_type or not set(binding.phases).issubset(spec.phases):
                    raise ValueError("observer binding must reference a required spec with matching phases")
        bound_observer_ids = {item.observer_id for item in self.observer_bindings if item.kind is ObserverRequirementKindV2.OBSERVER_SPEC}
        if any(spec.required and spec.observer_id not in bound_observer_ids for spec in self.observers):
            raise ValueError("every required observer spec must have an explicit binding")
        for case in self.plan.cases:
            for requirement in case.required_observers:
                if requirement == "http":
                    if requirement_map[requirement].kind is not ObserverRequirementKindV2.REQUEST_FACT:
                        raise ValueError("http must use the fixed REQUEST_FACT binding")
                elif requirement_map[requirement].kind is not ObserverRequirementKindV2.OBSERVER_SPEC:
                    raise ValueError("non-http requirements must bind an ObserverSpec")
        _reject_secret_material(self.model_dump(mode="python"))
        return self


def required_secret_refs_v2(snapshot: ExecutionProjectSnapshotV2) -> tuple[str, ...]:
    """返回 V2 Runner 实际使用的非秘密 env 引用，调用方不得在此解析值。"""

    identity_ids = {item.identity_id for item in snapshot.subject_bindings}
    references = [
        identity.secret_ref
        for identity in snapshot.identities
        if identity.id in identity_ids
    ]
    references.extend(
        binding.owner_api_credential_ref
        for binding in snapshot.observer_bindings
        if binding.owner_api_credential_ref is not None
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


class RunnerInputV2(RunnerV2Model):
    run_id: str = Field(pattern=RUN_ID_PATTERN)
    job_id: str = Field(pattern=JOB_ID_PATTERN)
    attempt: int = Field(ge=1)
    lease_owner: str = Field(pattern=_LEASE_OWNER)
    fencing_token: int = Field(ge=1)
    created_at_us: int = Field(ge=0)
    budget: ExecutionBudgetV2
    project_snapshot: ExecutionProjectSnapshotV2

    @model_validator(mode="after")
    def validate_budget(self) -> RunnerInputV2:
        target = self.project_snapshot.target
        if self.budget.max_requests != target.max_requests or self.budget.max_response_bytes != target.max_response_bytes:
            raise ValueError("V2 execution budget must match the target snapshot")
        if self.budget.request_timeout_us != int(target.timeout_seconds * 1_000_000):
            raise ValueError("V2 request timeout must match the target snapshot")
        if self.budget.max_cases < len(self.project_snapshot.plan.cases):
            raise ValueError("max_cases cannot be smaller than the permission plan")
        return self


class RequestFactV2(RunnerV2Model):
    method: str = Field(pattern=r"^[A-Z]{1,12}$")
    relative_path: str = Field(min_length=1, max_length=2048)
    status_code: int | None = Field(default=None, ge=100, le=599)
    failure_code: str | None = Field(default=None, pattern=_REASON_CODE)
    request_marker: str = Field(pattern=_TEXT)
    request_sha256: str = Field(pattern=_HEX)
    response_sha256: str = Field(pattern=_HEX)
    request_byte_count: int = Field(ge=0, le=4_194_304)
    response_byte_count: int = Field(ge=0, le=4_194_304)

    @model_validator(mode="after")
    def validate_response_or_failure(self) -> RequestFactV2:
        if (self.status_code is None) == (self.failure_code is None):
            raise ValueError("request fact requires exactly a response status or failure code")
        return self

    @field_validator("relative_path")
    @classmethod
    def validate_path(cls, value: str) -> str:
        parsed = urlsplit(value)
        segments = parsed.path.split("/")[1:]
        if (
            not value.startswith("/")
            or value.startswith("//")
            or parsed.scheme
            or parsed.netloc
            or parsed.query
            or parsed.fragment
            or "\\" in value
            or any(segment in {"", ".", ".."} for segment in segments)
            or any(ord(char) < 32 or ord(char) == 127 for char in value)
        ):
            raise ValueError("request fact path must be a bounded relative path")
        return value


class EvidenceV2(RunnerV2Model):
    evidence_id: str = Field(pattern=r"^ev_[0-9a-f]{20}$")
    run_id: str = Field(pattern=RUN_ID_PATTERN)
    case_snapshot: PermissionMutationCaseV2
    finding_pre_identity: str = Field(pattern=_HEX)
    request_fact: RequestFactV2
    requirement_bindings: tuple[ObserverRequirementBindingV2, ...] = Field(min_length=1, max_length=16)
    observations: tuple[ObservationEnvelopeV2, ...] = Field(default=(), max_length=19_200)
    outcomes: tuple[ObserverOutcomeV2, ...] = Field(default=(), max_length=64)
    verdict: CaseVerdict
    reason_codes: tuple[str, ...] = Field(default=(), max_length=64)
    evidence_hash: str = Field(pattern=_HEX)

    @model_validator(mode="after")
    def validate_evidence(self) -> EvidenceV2:
        observations = tuple(sorted(self.observations, key=lambda item: (item.observer_id, item.phase.value, item.correlation.resource_id)))
        outcomes = tuple(sorted(self.outcomes, key=lambda item: item.observer_id))
        if len({(item.observer_id, item.phase, item.correlation.resource_id) for item in observations}) != len(observations):
            raise ValueError("evidence observations must have unique observer, phase, and resource")
        if len({item.observer_id for item in outcomes}) != len(outcomes):
            raise ValueError("evidence outcomes must have unique observer IDs")
        binding_map = {item.requirement_id: item for item in self.requirement_bindings}
        case_requirements = set(self.case_snapshot.required_observers)
        if len(binding_map) != len(self.requirement_bindings) or set(binding_map) != case_requirements:
            raise ValueError("evidence bindings must exactly cover this case requirements")
        if binding_map.get("http") is None or binding_map["http"].kind is not ObserverRequirementKindV2.REQUEST_FACT:
            raise ValueError("evidence must carry the fixed http request binding")
        observer_bindings = {
            item.requirement_id: item
            for item in self.requirement_bindings
            if item.kind is ObserverRequirementKindV2.OBSERVER_SPEC
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
            if correlation.request_marker != self.request_fact.request_marker:
                raise ValueError("observation correlation does not match the request fact")
            if envelope.completeness is ObservationCompleteness.COMPLETE and envelope.causality.value != "CORRELATED":
                raise ValueError("complete evidence observation must be correlated")
        unavailable_required = any(item.status.value != "AVAILABLE" for item in outcomes)
        failed_request = self.request_fact.status_code is None
        if (unavailable_required or failed_request) and self.verdict is not CaseVerdict.INCONCLUSIVE:
            raise ValueError("incomplete required observation can only produce INCONCLUSIVE evidence")
        if self.verdict not in {CaseVerdict.SAFE, CaseVerdict.VULNERABLE, CaseVerdict.INCONCLUSIVE}:
            raise ValueError("V2 evidence verdict must be SAFE, VULNERABLE, or INCONCLUSIVE")
        complete_required = all(
            outcome_map[binding.observer_id].status.value == "AVAILABLE"
            and {
                (item.phase, item.correlation.resource_id)
                for item in observations
                if item.observer_id == binding.observer_id
            } == {(phase, resource_id) for resource_id in self.case_snapshot.resource_ids for phase in binding.phases}
            and all(
                item.completeness is ObservationCompleteness.COMPLETE and item.causality.value == "CORRELATED"
                for item in observations
                if item.observer_id == binding.observer_id
            )
            for binding in observer_bindings.values()
        )
        if self.verdict in {CaseVerdict.SAFE, CaseVerdict.VULNERABLE} and (not complete_required or failed_request):
            raise ValueError("safe or vulnerable evidence requires complete bound observations and a response")
        if self.finding_pre_identity != self.case_snapshot.finding_pre_identity:
            raise ValueError("finding_pre_identity must match the case snapshot")
        normalized_reasons = _validate_reason_codes(self.reason_codes, "evidence reason_codes")
        object.__setattr__(self, "observations", observations)
        object.__setattr__(self, "outcomes", outcomes)
        object.__setattr__(self, "reason_codes", normalized_reasons)
        expected = _sha256_json(_evidence_semantic_payload(self))
        if self.evidence_id != f"ev_{expected[:20]}" or self.evidence_hash != expected:
            raise ValueError("evidence_hash does not match the evidence semantic payload")
        return self


def _evidence_semantic_payload(evidence: EvidenceV2) -> dict[str, Any]:
    payload = evidence.model_dump(mode="json")
    payload.pop("evidence_id", None)
    payload.pop("evidence_hash", None)
    payload["observations"] = sorted(
        payload.get("observations", ()),
        key=lambda item: (item["observer_id"], item["phase"], item["correlation"]["resource_id"]),
    )
    payload["outcomes"] = sorted(payload.get("outcomes", ()), key=lambda item: item["observer_id"])
    return payload


def build_evidence_v2(**fields: Any) -> EvidenceV2:
    """构造内容寻址 Evidence，统一计算语义 hash 和 evidence_id。"""

    if "evidence_id" in fields or "evidence_hash" in fields:
        raise TypeError("build_evidence_v2 computes evidence_id and evidence_hash")
    semantic_payload = _jsonable(fields)
    semantic_payload["observations"] = sorted(
        semantic_payload.get("observations", ()),
        key=lambda item: (item["observer_id"], item["phase"], item["correlation"]["resource_id"]),
    )
    semantic_payload["outcomes"] = sorted(semantic_payload.get("outcomes", ()), key=lambda item: item["observer_id"])
    expected = _sha256_json(semantic_payload)
    return EvidenceV2(
        **fields,
        evidence_id=f"ev_{expected[:20]}",
        evidence_hash=expected,
    )


class CleanupResultV2(RunnerV2Model):
    status: CleanupStatusV2
    reason_codes: tuple[str, ...] = Field(default=(), max_length=64)

    @model_validator(mode="after")
    def validate_cleanup(self) -> CleanupResultV2:
        reasons = _validate_reason_codes(self.reason_codes, "cleanup reason_codes")
        if self.status is CleanupStatusV2.FAILED and not reasons:
            raise ValueError("failed cleanup requires a reason")
        if self.status is not CleanupStatusV2.FAILED and reasons:
            raise ValueError("successful cleanup cannot contain a reason")
        object.__setattr__(self, "reason_codes", reasons)
        return self


class RunnerErrorV2(RunnerV2Model):
    code: str = Field(pattern=_REASON_CODE)
    retryable: bool


class StagedArtifactV2(RunnerV2Model):
    path: str = Field(min_length=1, max_length=512)
    byte_count: int = Field(ge=0, le=STAGED_ARTIFACT_V2_MAX_BYTES)
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


class RunnerResultV2(RunnerV2Model):
    run_id: str = Field(pattern=RUN_ID_PATTERN)
    job_id: str = Field(pattern=JOB_ID_PATTERN)
    attempt: int = Field(ge=1)
    lease_owner: str = Field(pattern=_LEASE_OWNER)
    fencing_token: int = Field(ge=1)
    finished_at_us: int = Field(ge=0)
    result_type: RunnerResultTypeV2
    run_lifecycle: RunLifecycle
    job_state: JobState
    verdict: RunVerdict | None
    reason_codes: tuple[str, ...] = Field(default=(), max_length=128)
    cleanup: CleanupResultV2
    error: RunnerErrorV2 | None
    plan_fingerprint: str = Field(pattern=_HEX)
    coverage_record_count: int = Field(ge=0, le=16384)
    coverage_gap_count: int = Field(ge=0, le=16384)
    evidence: tuple[EvidenceV2, ...] = Field(default=(), max_length=8192)
    artifacts: tuple[StagedArtifactV2, ...] = Field(default=(), max_length=4096)

    @model_validator(mode="after")
    def validate_result(self) -> RunnerResultV2:
        reasons = _validate_reason_codes(self.reason_codes, "result reason_codes")
        allowed_cleanup = {CleanupStatusV2.NOT_REQUIRED, CleanupStatusV2.SUCCEEDED}
        if self.result_type is RunnerResultTypeV2.SUCCESS:
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
        elif self.result_type is RunnerResultTypeV2.SAFETY_STOPPED:
            valid = self.run_lifecycle is RunLifecycle.SAFETY_STOPPED and self.job_state is JobState.SUCCEEDED and self.verdict is None and self.error is None and bool(reasons) and self.cleanup.status in allowed_cleanup
        elif self.result_type is RunnerResultTypeV2.CANCELLED:
            valid = self.run_lifecycle is RunLifecycle.CANCELLED and self.job_state is JobState.CANCELLED and self.verdict is None and self.error is None and self.cleanup.status is CleanupStatusV2.SUCCEEDED
        elif self.result_type is RunnerResultTypeV2.RETRYABLE_ERROR:
            valid = self.run_lifecycle in {RunLifecycle.PREFLIGHT, RunLifecycle.PLANNING, RunLifecycle.EXECUTING, RunLifecycle.VERIFYING, RunLifecycle.REPORTING} and self.job_state is JobState.RETRY_WAIT and self.verdict is None and self.error is not None and self.error.retryable and self.cleanup.status in allowed_cleanup
        else:
            valid = self.run_lifecycle is RunLifecycle.FAILED and self.job_state is JobState.FAILED and self.verdict is None and self.error is not None and not self.error.retryable and self.cleanup.status in {CleanupStatusV2.NOT_REQUIRED, CleanupStatusV2.SUCCEEDED, CleanupStatusV2.FAILED}
        if not valid:
            raise ValueError("runner V2 result violates the lifecycle and verdict matrix")
        if any(item.run_id != self.run_id for item in self.evidence):
            raise ValueError("evidence run_id must match the runner result")
        if len({item.case_snapshot.case_id for item in self.evidence}) != len(self.evidence):
            raise ValueError("runner result evidence case IDs must be unique")
        if len({item.path.casefold() for item in self.artifacts}) != len(self.artifacts):
            raise ValueError("artifact paths must be case-insensitively unique")
        if sum(item.byte_count for item in self.artifacts) > STAGED_ARTIFACT_V2_TOTAL_MAX_BYTES:
            raise ValueError("artifact total exceeds the limit")
        object.__setattr__(self, "reason_codes", reasons)
        _reject_secret_material(self.model_dump(mode="python"))
        return self


RunnerV2Document: TypeAlias = RunnerInputV2 | RunnerResultV2 | EvidenceV2
RunnerV2T = TypeVar("RunnerV2T", RunnerInputV2, RunnerResultV2, EvidenceV2)


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
                raise ValueError("V2 protocol contains inline secret material")
        elif isinstance(item, Mapping):
            for key, child in item.items():
                if str(key) not in _SAFE_SECRET_KEY_NAMES and _SECRET_KEY.search(str(key)) and not str(key).endswith("_ref"):
                    raise ValueError("V2 protocol contains an inline secret field")
                pending.extend((key, child))
        elif isinstance(item, Sequence) and not isinstance(item, (bytes, bytearray, str)):
            pending.extend(item)


def canonical_runner_v2_json_bytes(document: RunnerV2Document, *, known_secrets: Sequence[str] = ()) -> bytes:
    if not isinstance(document, (RunnerInputV2, RunnerResultV2, EvidenceV2)):
        raise TypeError("canonical JSON only accepts a Runner V2 document")
    if any(not isinstance(secret, str) for secret in known_secrets):
        raise TypeError("known_secrets must contain only strings")
    data = _jsonable(document)
    _reject_secret_material(data)
    for secret in known_secrets:
        if secret and secret in json.dumps(data, ensure_ascii=False, sort_keys=True):
            raise JiejianError("PROTOCOL_SECRET_EXPOSED", "V2 protocol contains known secret material")
    encoded = _canonical_bytes(data)
    maximum = RUNNER_V2_INPUT_MAX_BYTES if isinstance(document, RunnerInputV2) else RUNNER_V2_RESULT_MAX_BYTES
    if isinstance(document, EvidenceV2):
        maximum = EVIDENCE_V2_MAX_BYTES
    if len(encoded) > maximum:
        raise JiejianError("PROTOCOL_TOO_LARGE", "Runner V2 document exceeds its size limit")
    return encoded


def canonical_runner_v2_sha256(document: RunnerV2Document, *, known_secrets: Sequence[str] = ()) -> str:
    return hashlib.sha256(canonical_runner_v2_json_bytes(document, known_secrets=known_secrets)).hexdigest()


def _reject_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("V2 JSON contains duplicate keys")
        result[key] = value
    return result


def _reject_nonfinite(value: str) -> None:
    raise ValueError("V2 JSON contains a non-finite number")


def _parse_v2(raw: bytes, model: type[RunnerV2T], maximum: int, label: str, known_secrets: Sequence[str]) -> RunnerV2T:
    if not isinstance(raw, bytes):
        raise TypeError("V2 parser requires bytes")
    if len(raw) > maximum or raw.startswith(b"\xef\xbb\xbf"):
        raise JiejianError("PROTOCOL_INVALID", f"{label} is oversized or contains a BOM")
    try:
        parsed = json.loads(raw.decode("utf-8"), object_pairs_hook=_reject_pairs, parse_constant=_reject_nonfinite)
        if not isinstance(parsed, dict):
            raise ValueError("V2 root must be an object")
        _reject_secret_material(parsed)
        if any(secret and secret in raw.decode("utf-8") for secret in known_secrets):
            raise JiejianError("PROTOCOL_SECRET_EXPOSED", f"{label} contains known secret material")
        return model.model_validate_json(raw)
    except JiejianError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError, ValidationError) as exc:
        raise JiejianError("PROTOCOL_INVALID", f"{label} is not a valid strict V2 document", details={"reason": type(exc).__name__}) from None


def parse_runner_input_v2(raw: bytes, *, known_secrets: Sequence[str] = ()) -> RunnerInputV2:
    return _parse_v2(raw, RunnerInputV2, RUNNER_V2_INPUT_MAX_BYTES, "Runner V2 input", known_secrets)


def parse_runner_result_v2(raw: bytes, *, known_secrets: Sequence[str] = ()) -> RunnerResultV2:
    return _parse_v2(raw, RunnerResultV2, RUNNER_V2_RESULT_MAX_BYTES, "Runner V2 result", known_secrets)


def parse_evidence_v2(raw: bytes, *, known_secrets: Sequence[str] = ()) -> EvidenceV2:
    return _parse_v2(raw, EvidenceV2, EVIDENCE_V2_MAX_BYTES, "Evidence V2", known_secrets)
