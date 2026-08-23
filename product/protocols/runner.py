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
import json
import math
import re
from collections.abc import Mapping, Sequence
from enum import StrEnum
from typing import Any, Literal, TypeAlias, TypeVar

from pydantic import BaseModel, Field, ValidationError, field_validator, model_validator

from product.backend.core.identifiers import JOB_ID_PATTERN, RUN_ID_PATTERN, SHA256_PATTERN
from product.backend.core.lifecycle import CaseVerdict, JobState, RunLifecycle, RunVerdict
from product.backend.core.errors import JiejianError
from product.backend.core.verification.differential import PermissionTwin, TwinExecutionRole
from product.backend.core.verification.permission_coverage import PermissionMutationCase
from product.backend.core.verification.facts import ExecutionFact, ExecutionOutcome, ObservationFact, ObservedEffect, SecurityEffectFact
from product.protocols.execution import (
    ExecutionBudget,
    ObserverRequirementBinding,
    ObserverRequirementKind,
    ProtocolModel,
)
from product.protocols.observer import ObservationCompleteness, ObservationEnvelope, ObserverOutcome
from product.protocols.web.profile import WebExecutionSnapshot


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


def _validate_reason_codes(values: tuple[str, ...], label: str) -> tuple[str, ...]:
    if len(set(values)) != len(values) or any(re.fullmatch(_REASON_CODE, value) is None for value in values):
        raise ValueError(f"{label} must contain unique stable codes")
    return tuple(sorted(values))


class RunnerInput(ProtocolModel):
    schema_version: Literal["4"] = "4"
    run_id: str = Field(pattern=RUN_ID_PATTERN)
    job_id: str = Field(pattern=JOB_ID_PATTERN)
    attempt: int = Field(ge=1)
    lease_owner: str = Field(pattern=_LEASE_OWNER)
    fencing_token: int = Field(ge=1)
    created_at_us: int = Field(ge=0)
    budget: ExecutionBudget
    project_snapshot: WebExecutionSnapshot

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
    schema_version: Literal["4"] = "4"
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
        expected = _evidence_semantic_sha256(_evidence_semantic_payload(self))
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
    expected = _evidence_semantic_sha256(semantic_payload)
    return Evidence(
        **fields,
        evidence_id=f"ev_{expected[:20]}",
        evidence_hash=expected,
    )


class CleanupResult(ProtocolModel):
    status: CleanupStatus
    finished_at_us: int | None = Field(default=None, ge=0)
    reason_codes: tuple[str, ...] = Field(default=(), max_length=64)

    @model_validator(mode="after")
    def validate_cleanup(self) -> CleanupResult:
        reasons = _validate_reason_codes(self.reason_codes, "cleanup reason_codes")
        if self.status is CleanupStatus.NOT_REQUIRED:
            if self.finished_at_us is not None or reasons:
                raise ValueError("not-required cleanup cannot contain completion facts")
        elif self.finished_at_us is None:
            raise ValueError("performed cleanup requires a completion time")
        if self.status is CleanupStatus.FAILED:
            if reasons != ("CLEANUP_FAILED",):
                raise ValueError("failed cleanup must use CLEANUP_FAILED")
        elif reasons:
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
    schema_version: Literal["4"] = "4"
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
            valid = self.run_lifecycle is RunLifecycle.RUNNING and self.job_state is JobState.RETRY_WAIT and self.verdict is None and self.error is not None and self.error.retryable and self.cleanup.status in allowed_cleanup
        else:
            valid = self.run_lifecycle is RunLifecycle.FAILED and self.job_state is JobState.FAILED and self.verdict is None and self.error is not None and not self.error.retryable and self.cleanup.status in {CleanupStatus.NOT_REQUIRED, CleanupStatus.SUCCEEDED, CleanupStatus.FAILED}
        if self.cleanup.status is CleanupStatus.FAILED:
            valid = valid and self.result_type is RunnerResultType.FATAL_ERROR and self.error is not None and self.error.code == "CLEANUP_FAILED" and "CLEANUP_FAILED" in reasons
        if not valid:
            raise ValueError("runner  result violates the lifecycle and verdict matrix")
        if any(item.run_id != self.run_id for item in self.evidence):
            raise ValueError("evidence run_id must match the runner result")
        if any(item.window.finished_at_us > self.finished_at_us for item in (observation for evidence in self.evidence for observation in evidence.observations)):
            raise ValueError("runner finish time precedes an evidence observation window")
        if self.cleanup.finished_at_us is not None and self.cleanup.finished_at_us > self.finished_at_us:
            raise ValueError("runner finish time precedes cleanup completion")
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


def _evidence_semantic_sha256(value: Any) -> str:
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


def _parse_(
    raw: bytes,
    model: type[ProtocolT],
    maximum: int,
    label: str,
    known_secrets: Sequence[str],
    *,
    expected_schema_version: str | None = None,
) -> ProtocolT:
    if not isinstance(raw, bytes):
        raise TypeError(" parser requires bytes")
    if len(raw) > maximum or raw.startswith(b"\xef\xbb\xbf"):
        raise JiejianError("PROTOCOL_INVALID", f"{label} is oversized or contains a BOM")
    try:
        parsed = json.loads(raw.decode("utf-8"), object_pairs_hook=_reject_pairs, parse_constant=_reject_nonfinite)
        if not isinstance(parsed, dict):
            raise ValueError(" root must be an object")
        if expected_schema_version is not None and parsed.get("schema_version") != expected_schema_version:
            raise ValueError(" schema_version is missing or unsupported")
        _reject_secret_material(parsed)
        if any(secret and secret in raw.decode("utf-8") for secret in known_secrets):
            raise JiejianError("PROTOCOL_SECRET_EXPOSED", f"{label} contains known secret material")
        return model.model_validate_json(raw)
    except JiejianError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError, ValidationError) as exc:
        raise JiejianError("PROTOCOL_INVALID", f"{label} is not a valid strict  document", details={"reason": type(exc).__name__}) from None


def parse_runner_input(raw: bytes, *, known_secrets: Sequence[str] = ()) -> RunnerInput:
    return _parse_(
        raw,
        RunnerInput,
        RUNNER_INPUT_MAX_BYTES,
        "Runner  input",
        known_secrets,
        expected_schema_version="4",
    )


def parse_runner_result(raw: bytes, *, known_secrets: Sequence[str] = ()) -> RunnerResult:
    return _parse_(
        raw,
        RunnerResult,
        RUNNER_RESULT_MAX_BYTES,
        "Runner  result",
        known_secrets,
        expected_schema_version="4",
    )


def parse_evidence(raw: bytes, *, known_secrets: Sequence[str] = ()) -> Evidence:
    return _parse_(
        raw,
        Evidence,
        EVIDENCE_MAX_BYTES,
        "Evidence ",
        known_secrets,
        expected_schema_version="4",
    )
