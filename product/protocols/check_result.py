# 当前检查的跨进程输入、证据与结果根；只传递有界事实和不可变资产引用。
from __future__ import annotations

import hashlib
import json
import re
from typing import Annotated, Literal, TypeVar

from pydantic import Field, model_validator

from product.backend.core.lifecycle import CaseVerdict, RunLifecycle, RunVerdict
from product.backend.core.verification.trace import ExecutionTrace
from product.protocols.execution_v3 import ExecutionCase, Hash, LogicalId, WireModel, content_hash
from product.protocols.check_publication import CheckPublicationManifest
from product.protocols.check_runtime import check_payload_contains_secret

RunId = Annotated[str, Field(pattern=r"^run_[0-9a-f]{32}$")]
JobId = Annotated[str, Field(pattern=r"^job_[0-9a-f]{32}$")]
CaseId = Annotated[str, Field(pattern=r"^case_[0-9a-f]{32}$")]
EvidenceId = Annotated[str, Field(pattern=r"^ev_[0-9a-f]{64}$")]
ActionId = Annotated[str, Field(pattern=r"^bac_[0-9a-f]{32}$")]
ReasonCode = Annotated[str, Field(pattern=r"^[A-Z][A-Z0-9_]{0,127}$")]
CHECK_RESULT_MAX_BYTES = 1_048_576


def check_request_marker(run_id: str, job_id: str, attempt: int, case_id: str) -> str:
    """同一 Case 的本次执行关联键；计划 Case ID 相同也不能跨 Run/attempt 复用观察。"""
    return "req_" + content_hash("CheckRequestMarker", dict(run_id=run_id, job_id=job_id, attempt=attempt, case_id=case_id))[:48]


class CheckAssetReference(WireModel):
    logical_id: Literal["request", "runtime"]
    sha256: Hash


class CheckRunnerInput(WireModel):
    schema_version: Literal["1"] = "1"
    run_id: RunId
    job_id: JobId
    attempt: int = Field(ge=1)
    lease_owner: Annotated[str, Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")]
    fencing_token: int = Field(ge=1)
    created_at_us: int = Field(ge=0)
    request_hash: Hash
    config_hash: Hash
    assets: tuple[CheckAssetReference, ...] = Field(min_length=2, max_length=2)

    @model_validator(mode="after")
    def validate_assets(self):
        if {item.logical_id: item.sha256 for item in self.assets} != {"request": self.request_hash, "runtime": self.config_hash}:
            raise ValueError("runner assets must exactly bind request and runtime hashes")
        return self


class CheckRunnerProgress(WireModel):
    schema_version: Literal["1"] = "1"
    run_id: RunId
    job_id: JobId
    attempt: int = Field(ge=1)
    fencing_token: int = Field(ge=1)
    request_hash: Hash
    phase: Literal["PREPARING", "EXECUTING", "FINALIZING"]
    completed_cases: int = Field(ge=0, le=8192)
    planned_cases: int = Field(ge=1, le=8192)
    observed_at_us: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_counts(self):
        if self.completed_cases > self.planned_cases:
            raise ValueError("progress exceeds frozen case count")
        return self


class CheckObservation(WireModel):
    effect_id: Annotated[str, Field(pattern=r"^bef_[0-9a-f]{32}$")]
    proof_fingerprint: Hash
    observer_id: LogicalId
    level: Literal["VERDICT_REQUIRED", "DIAGNOSIS_REQUIRED", "SUPPORTING"]
    phase: Literal["BASELINE", "BEFORE", "AFTER", "EVENTUAL", "RECOVERY"]
    state: Literal["CONFIRMED", "ABSENT", "UNKNOWN"]
    closure: Literal["CLOSED", "OPEN", "UNKNOWN"]
    complete: bool
    reliable: bool
    correlated: bool
    authoritative: bool
    window_start_us: int = Field(ge=0)
    window_end_us: int = Field(ge=0)
    correlation_refs: tuple[Annotated[str, Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:/-]{0,159}$")], ...] = Field(default=(), max_length=32)
    reason_codes: tuple[ReasonCode, ...] = Field(default=(), max_length=16)

    @model_validator(mode="after")
    def validate_window(self):
        if self.window_end_us < self.window_start_us:
            raise ValueError("observation window reversed")
        return self


class CheckCaseOutcome(WireModel):
    execution_outcome: Literal["ACCEPTED", "DENIED", "FAILED", "UNKNOWN"]
    http_status: int | None = Field(default=None, ge=100, le=599)
    actual_identity_status: Literal["MATCH", "MISMATCH", "UNKNOWN"]
    baseline_trusted: bool
    recovery_verified: bool
    run_correlated: bool
    resource_correlated: bool


class CheckEvidence(WireModel):
    schema_version: Literal["1"] = "1"
    evidence_id: EvidenceId
    run_id: RunId
    job_id: JobId
    attempt: int = Field(ge=1)
    action_id: ActionId
    action_revision: int = Field(ge=1)
    request_hash: Hash
    config_hash: Hash
    case: ExecutionCase
    outcome: CheckCaseOutcome
    observations: tuple[CheckObservation, ...] = Field(max_length=240)
    trace: ExecutionTrace | None = None

    @model_validator(mode="after")
    def validate_associations(self):
        proofs = {proof.proof_fingerprint: proof for proof in self.case.proof_requirements}
        for item in self.observations:
            proof = proofs.get(item.proof_fingerprint)
            if proof is None or proof.effect_id != item.effect_id or (
                item.level != proof.level and item.level not in ("SUPPORTING", "DIAGNOSIS_REQUIRED")
            ):
                raise ValueError("observation must reference the frozen case proof")
        keys = [(item.proof_fingerprint, item.observer_id, item.phase) for item in self.observations]
        if len(keys) != len(set(keys)):
            raise ValueError("duplicate published observation")
        if self.trace is not None and (self.trace.case_id, self.trace.action_id) != (self.case.case_id, self.action_id):
            raise ValueError("evidence trace case mismatch")
        if self.evidence_id != evidence_content_id(self.model_dump(mode="json", exclude={"evidence_id"})):
            raise ValueError("evidence content address mismatch")
        return self


class CheckCaseResult(WireModel):
    case_id: CaseId
    action_id: ActionId
    verdict: CaseVerdict
    reason_codes: tuple[ReasonCode, ...] = Field(max_length=32)
    evidence_ids: tuple[EvidenceId, ...] = Field(max_length=48)
    outcome: CheckCaseOutcome


class CheckPrimaryError(WireModel):
    code: ReasonCode
    phase: ReasonCode
    cause_code: ReasonCode | None = None


class CheckRunnerResult(WireModel):
    schema_version: Literal["1"] = "1"
    run_id: RunId
    job_id: JobId
    attempt: int = Field(ge=1)
    lease_owner: Annotated[str, Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")]
    fencing_token: int = Field(ge=1)
    request_hash: Hash
    config_hash: Hash
    result_type: Literal["SUCCESS", "SAFETY_STOPPED", "FAILED", "CANCELLED"]
    lifecycle: RunLifecycle
    case_results: tuple[CheckCaseResult, ...] = Field(max_length=8192)
    verdict: RunVerdict | None
    primary_error: CheckPrimaryError | None = None
    cleanup_issues: tuple[ReasonCode, ...] = Field(default=(), max_length=32)
    started_at_us: int = Field(ge=0)
    completed_at_us: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_result(self):
        if self.completed_at_us < self.started_at_us:
            raise ValueError("result completion precedes start")
        expected = {"SUCCESS": RunLifecycle.COMPLETED, "SAFETY_STOPPED": RunLifecycle.SAFETY_STOPPED,
                    "FAILED": RunLifecycle.FAILED, "CANCELLED": RunLifecycle.CANCELLED}
        if self.lifecycle is not expected[self.result_type]:
            raise ValueError("result type and lifecycle differ")
        if self.result_type == "SUCCESS" and self.verdict is None:
            raise ValueError("completed result requires a verdict")
        if self.result_type == "SAFETY_STOPPED" and self.verdict not in (RunVerdict.BLOCK, RunVerdict.INCONCLUSIVE):
            raise ValueError("safety stop cannot claim pass")
        if self.result_type in ("FAILED", "CANCELLED") and self.verdict is not None:
            raise ValueError("unfinished result cannot carry a verdict")
        if len({item.case_id for item in self.case_results}) != len(self.case_results):
            raise ValueError("duplicate case result")
        return self


def evidence_content_id(payload) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    return "ev_" + hashlib.sha256(raw).hexdigest()


def seal_check_evidence(**fields) -> CheckEvidence:
    # 先补齐根默认值，再计算内容地址；最终严格 reader 仍拒绝绕过校验的嵌套事实。
    draft = CheckEvidence.model_construct(evidence_id="ev_" + "0" * 64, **fields)
    payload = draft.model_dump(mode="json", exclude={"evidence_id"})
    payload["evidence_id"] = evidence_content_id(payload)
    return CheckEvidence.model_validate_json(json.dumps(payload), strict=True)


class CheckResultProtocolError(ValueError):
    code = "RUNNER_PROTOCOL_INVALID"


CheckDocument = TypeVar("CheckDocument", CheckRunnerInput, CheckEvidence, CheckRunnerResult, CheckPublicationManifest, CheckRunnerProgress)
_CHECK_ROOTS = (CheckRunnerInput, CheckEvidence, CheckRunnerResult, CheckPublicationManifest, CheckRunnerProgress)


def canonical_check_document(document: CheckDocument, *, known_secrets: tuple[str, ...] = ()) -> bytes:
    """只编码本检查协议族的独立根，并重新验证所有嵌套关联。"""
    try:
        if type(document) not in _CHECK_ROOTS:
            raise ValueError("unsupported check root")
        parsed = type(document).model_validate_json(document.model_dump_json(), strict=True)
        if check_payload_contains_secret(parsed.model_dump(mode="json"), known_secrets):
            raise ValueError("unsafe check document")
        raw = json.dumps(parsed.model_dump(mode="json"), ensure_ascii=False, sort_keys=True,
            separators=(",", ":"), allow_nan=False).encode()
        if len(raw) > CHECK_RESULT_MAX_BYTES or any(secret and secret.encode() in raw for secret in known_secrets):
            raise ValueError("unsafe check document")
        if re.search(rb"(?i)(?:\bBearer\s+\S+|\b(?:password|token|api[_-]?key)\s*[:=]\s*\S+)", raw):
            raise ValueError("unsafe check document")
        return raw
    except (ValueError, TypeError, AttributeError):
        raise CheckResultProtocolError("执行快照格式无效") from None


def parse_check_document(raw: bytes, model: type[CheckDocument], *, known_secrets: tuple[str, ...] = ()) -> CheckDocument:
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate key")
            result[key] = value
        return result
    try:
        if model not in _CHECK_ROOTS or type(raw) is not bytes or len(raw) > CHECK_RESULT_MAX_BYTES or raw.startswith(b"\xef\xbb\xbf"):
            raise ValueError("invalid check document")
        json.loads(raw.decode(), object_pairs_hook=unique,
            parse_constant=lambda _: (_ for _ in ()).throw(ValueError("nonfinite")))
        document = model.model_validate_json(raw, strict=True)
        if canonical_check_document(document, known_secrets=known_secrets) != raw:
            raise ValueError("noncanonical check document")
        return document
    except (ValueError, TypeError, UnicodeError):
        raise CheckResultProtocolError("执行快照格式无效") from None
