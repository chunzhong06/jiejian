# =============================================================================
# 统一报告严格协议
#
# 定位
#   以已发布 Run、Finalizer 快照、确定性展示快照、Artifact 三态和明确
#   GateResult 组成不可变 Report；report.json 是唯一语义真源。
#
# 职责
#   约束 Base/Gate 判别联合｜计算语义输入与稳定身份｜约束 package manifest。
#
# 边界
#   协议只消费已验证事实，不执行 Target、不写 Finding、不决定 Verdict。
# =============================================================================

from __future__ import annotations

import hashlib
import json
import re
from enum import StrEnum
from typing import Annotated, Any, Literal, TypeAlias

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, model_validator

from product.backend.core.redaction import redact

REPORT_SCHEMA_VERSION = "1"
REPORT_RULESET_VERSION = "report-local-2026.08.18"
_TOKEN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:/@+\-]{0,255}$")
_SHA256 = r"^[0-9a-f]{64}$"


class ReportModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True, hide_input_in_errors=True)



class ReportEvidenceRef(ReportModel):
    evidence_id: str = Field(pattern=r"^(?:ev_[0-9a-f]{20}|aev_[0-9a-f]{20})$")
    source_type: Literal["RUNTIME", "ARTIFACT"]


class ReportFinding(ReportModel):
    finding_id: str = Field(pattern=r"^(?:finding_[0-9a-f]{32}|af_[0-9a-f]{32})$")
    source_type: Literal["RUNTIME", "ARTIFACT"]
    occurrence_id: str | None = Field(default=None, pattern=r"^occ_[0-9a-f]{32}$")
    verdict: Literal["SAFE", "VULNERABLE", "INCONCLUSIVE", "SKIPPED", "ERROR"]
    severity: Literal["low", "medium", "high", "critical", "unknown"]
    evidence_refs: tuple[ReportEvidenceRef, ...] = Field(max_length=64)
    rule_id: str | None = Field(default=None, pattern=r"^[A-Z][A-Z0-9_]{0,63}$")
    category: str | None = Field(default=None, pattern=r"^[A-Z][A-Z0-9_]{0,63}$")
    path: str | None = Field(default=None, min_length=1, max_length=512)
    message: str | None = Field(default=None, min_length=1, max_length=128)

    @model_validator(mode="after")
    def validate_source_shape(self) -> ReportFinding:
        if self.source_type == "RUNTIME" and self.occurrence_id is None:
            raise ValueError("runtime report finding requires an occurrence")
        if self.source_type == "ARTIFACT" and self.occurrence_id is not None:
            raise ValueError("artifact report finding cannot contain a runtime occurrence")
        if self.source_type == "ARTIFACT" and not self.evidence_refs:
            raise ValueError("artifact report finding requires evidence")
        return self


class ReportObserverStatus(ReportModel):
    observer_id: str = Field(min_length=1, max_length=128)
    required: bool
    status: str = Field(pattern=r"^[A-Z][A-Z0-9_]{0,63}$")
    reason_codes: tuple[str, ...] = Field(default=(), max_length=16)

    @model_validator(mode="after")
    def validate_tokens(self) -> ReportObserverStatus:
        if any(not _TOKEN.fullmatch(item) for item in self.reason_codes):
            raise ValueError("observer reason code is not bounded")
        return self


class ReportRuntime(ReportModel):
    lifecycle: str = Field(pattern=r"^[A-Z][A-Z0-9_]{0,31}$")
    verdict: str | None = Field(default=None, pattern=r"^[A-Z][A-Z0-9_]{0,31}$")
    evidence_refs: tuple[ReportEvidenceRef, ...] = Field(max_length=8192)
    findings: tuple[ReportFinding, ...] = Field(max_length=8192)
    observer_statuses: tuple[ReportObserverStatus, ...] = Field(max_length=8192)
    execution_errors: tuple[str, ...] = Field(default=(), max_length=256)

    @model_validator(mode="after")
    def validate_runtime_sources(self) -> ReportRuntime:
        if any(item.source_type != "RUNTIME" for item in self.evidence_refs):
            raise ValueError("runtime facts cannot contain artifact evidence")
        if any(item.source_type != "RUNTIME" for item in self.findings):
            raise ValueError("runtime facts cannot contain artifact findings")
        if any(not _TOKEN.fullmatch(item) for item in self.execution_errors):
            raise ValueError("execution error is not bounded")
        return self


class ReportArtifact(ReportModel):
    artifact_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
    status: Literal["COMPLETE", "INCONCLUSIVE"]
    verdict: Literal["SAFE", "VULNERABLE", "INCONCLUSIVE"]
    error_code: str | None = Field(default=None, pattern=r"^[A-Z][A-Z0-9_]{0,63}$")
    manifest_sha256: str = Field(pattern=_SHA256)
    ruleset_version: str = Field(min_length=1, max_length=64)
    evidence_refs: tuple[ReportEvidenceRef, ...] = Field(max_length=4096)
    findings: tuple[ReportFinding, ...] = Field(max_length=4096)

    @model_validator(mode="after")
    def validate_artifact_sources(self) -> ReportArtifact:
        if any(item.source_type != "ARTIFACT" for item in self.findings):
            raise ValueError("artifact facts cannot contain runtime findings")
        if any(item.source_type != "ARTIFACT" for item in self.evidence_refs):
            raise ValueError("artifact facts cannot contain runtime evidence")
        if self.status == "COMPLETE" and self.error_code is not None:
            raise ValueError("complete artifact result cannot contain an error")
        if self.status == "INCONCLUSIVE" and self.error_code is None:
            raise ValueError("inconclusive artifact result requires an error")
        return self


class ArtifactSummaryStatus(StrEnum):
    NOT_REQUESTED = "NOT_REQUESTED"
    COMPLETE = "COMPLETE"
    INCONCLUSIVE = "INCONCLUSIVE"


class ArtifactSummary(ReportModel):
    status: ArtifactSummaryStatus
    results: tuple[ReportArtifact, ...] = Field(max_length=256)
    reason_codes: tuple[str, ...] = Field(default=(), max_length=64)
    snapshot_sha256: str = Field(pattern=_SHA256)

    @model_validator(mode="after")
    def validate_summary(self) -> ArtifactSummary:
        if tuple(sorted(self.results, key=lambda item: item.artifact_id)) != self.results:
            raise ValueError("artifact results must be stable sorted")
        if tuple(sorted(set(self.reason_codes))) != self.reason_codes:
            raise ValueError("artifact reason codes must be stable sorted")
        if self.status is ArtifactSummaryStatus.NOT_REQUESTED and (self.results or self.reason_codes):
            raise ValueError("not requested artifact summary must be empty")
        if self.status is ArtifactSummaryStatus.COMPLETE and any(item.status != "COMPLETE" for item in self.results):
            raise ValueError("complete artifact summary contains an incomplete result")
        if self.status is ArtifactSummaryStatus.INCONCLUSIVE and not self.reason_codes:
            raise ValueError("inconclusive artifact summary needs a reason")
        if self.snapshot_sha256 != artifact_summary_sha256(self.status, self.results, self.reason_codes):
            raise ValueError("artifact summary hash is invalid")
        return self

    @classmethod
    def create(
        cls,
        status: ArtifactSummaryStatus,
        results: tuple[ReportArtifact, ...] = (),
        reason_codes: tuple[str, ...] = (),
    ) -> ArtifactSummary:
        normalized = tuple(sorted(results, key=lambda item: item.artifact_id))
        reasons = tuple(sorted(set(reason_codes)))
        digest = artifact_summary_sha256(status, normalized, reasons)
        return cls(status=status, results=normalized, reason_codes=reasons, snapshot_sha256=digest)


class ReportVersions(ReportModel):
    contract_id: str = Field(min_length=1, max_length=128)
    contract_version: int = Field(ge=1)
    engine_version: str = Field(min_length=1, max_length=64)
    runner_schema_version: Literal["1"]
    evidence_schema_version: Literal["1"]
    observer_schema_version: Literal["1"]
    artifact_schema_version: Literal["1"]
    report_schema_version: Literal["1"] = REPORT_SCHEMA_VERSION
    ruleset_versions: tuple[str, ...] = Field(default=(), max_length=16)

    @model_validator(mode="after")
    def validate_versions(self) -> ReportVersions:
        if tuple(sorted(set(self.ruleset_versions))) != self.ruleset_versions:
            raise ValueError("ruleset versions must be stable sorted")
        return self


class ReportRun(ReportModel):
    run_id: str = Field(pattern=r"^run_[0-9a-f]{32}$")
    project_id: str = Field(pattern=r"^[a-z][a-z0-9_-]{0,63}$")
    lifecycle: str = Field(pattern=r"^[A-Z][A-Z0-9_]{0,31}$")
    verdict: str | None = Field(default=None, pattern=r"^[A-Z][A-Z0-9_]{0,31}$")
    created_at_us: int = Field(ge=0)
    finished_at_us: int | None = Field(default=None, ge=0)


class ReportGate(ReportModel):
    gate_result_id: str = Field(pattern=r"^gate_[0-9a-f]{32}$")
    baseline_id: str = Field(pattern=r"^baseline_[0-9a-f]{32}$")
    run_id: str = Field(pattern=r"^run_[0-9a-f]{32}$")
    policy_version: Literal["gate-v1"]
    input_hash: str = Field(pattern=_SHA256)
    decision: Literal["PASS", "BLOCK", "ERROR"]
    reasons: tuple[dict[str, str], ...] = Field(max_length=8192)
    evaluated_at_us: int = Field(ge=0)


class ReportPresentationIssue(ReportModel):
    """冻结单个权限问题的人类可读表达，不承载新的安全判断。"""

    finding_id: str = Field(pattern=r"^(?:finding_[0-9a-f]{32}|af_[0-9a-f]{32})$")
    title: str = Field(min_length=1, max_length=200)
    subject_group: str = Field(min_length=1, max_length=160)
    action: str = Field(min_length=1, max_length=160)
    resource: str = Field(min_length=1, max_length=160)
    relation: str = Field(min_length=1, max_length=160)
    expectation: str = Field(min_length=1, max_length=240)
    surface_result: str = Field(min_length=1, max_length=240)
    actual_result: str = Field(min_length=1, max_length=240)
    conclusion: str = Field(min_length=1, max_length=160)
    explanation: str = Field(min_length=1, max_length=480)
    severity: Literal["unknown", "low", "medium", "high", "critical"]
    evidence_refs: tuple[str, ...] = Field(default=(), max_length=8192)
    verdict: Literal["SAFE", "VULNERABLE", "INCONCLUSIVE"]
    occurrence_status: str | None = Field(
        default=None,
        pattern=r"^[A-Z][A-Z0-9_]{0,31}$",
    )

    @model_validator(mode="after")
    def validate_evidence_refs(self) -> ReportPresentationIssue:
        if any(
            re.fullmatch(r"^(?:ev_[0-9a-f]{20}|aev_[0-9a-f]{20})$", item) is None
            for item in self.evidence_refs
        ):
            raise ValueError("presentation issue evidence reference is invalid")
        return self


class ReportPresentation(ReportModel):
    """冻结 D-3 确定性结果投影，供所有人类报告格式复用。"""

    run_id: str = Field(pattern=r"^run_[0-9a-f]{32}$")
    project_id: str = Field(pattern=r"^[a-z][a-z0-9_-]{0,63}$")
    project_name: str = Field(min_length=1, max_length=128)
    run_lifecycle: Literal[
        "QUEUED",
        "RUNNING",
        "COMPLETED",
        "FAILED",
        "CANCELLED",
        "SAFETY_STOPPED",
    ]
    verdict: Literal["PASS", "BLOCK", "INCONCLUSIVE"] | None
    headline: str = Field(min_length=1, max_length=160)
    scope_statement: str = Field(min_length=1, max_length=320)
    checked_count: int = Field(ge=0)
    safe_count: int = Field(ge=0)
    problem_count: int = Field(ge=0)
    inconclusive_count: int = Field(ge=0)
    uncovered_count: int = Field(ge=0)
    execution_problem: str | None = Field(default=None, max_length=320)
    issues: tuple[ReportPresentationIssue, ...] = Field(default=(), max_length=8192)
    limitations: tuple[str, ...] = Field(default=(), max_length=128)

    @model_validator(mode="after")
    def validate_counts(self) -> ReportPresentation:
        if self.safe_count + self.problem_count + self.inconclusive_count != self.checked_count:
            raise ValueError("presentation summary counts are inconsistent")
        return self


class BaseRunReport(ReportModel):
    schema_version: Literal["1"] = REPORT_SCHEMA_VERSION
    report_type: Literal["BASE"]
    report_id: str = Field(pattern=r"^report_[0-9a-f]{32}$")
    run_id: str = Field(pattern=r"^run_[0-9a-f]{32}$")
    project_id: str = Field(pattern=r"^[a-z][a-z0-9_-]{0,63}$")
    semantic_input_sha256: str = Field(pattern=_SHA256)
    canonical_sha256: str = Field(pattern=_SHA256)
    run: ReportRun
    runtime: ReportRuntime
    presentation: ReportPresentation
    artifact_summary: ArtifactSummary
    versions: ReportVersions
    limitations: tuple[str, ...] = Field(default=(), max_length=256)

    @model_validator(mode="after")
    def validate_base(self) -> BaseRunReport:
        if self.run_id != self.run.run_id or self.project_id != self.run.project_id:
            raise ValueError("base report run identity is inconsistent")
        _validate_presentation_identity(self)
        if self.report_id != report_id_for("BASE", self.semantic_input_sha256):
            raise ValueError("base report ID is not deterministic")
        if self.canonical_sha256 != report_canonical_sha256(self.semantic_payload()):
            raise ValueError("base report canonical hash is invalid")
        _validate_public(self)
        return self

    def semantic_payload(self) -> dict[str, Any]:
        return self.model_dump(mode="json", exclude={"canonical_sha256"})

    @classmethod
    def create(cls, **values: Any) -> BaseRunReport:
        candidate = cls.model_construct(canonical_sha256="0" * 64, **values)
        payload = candidate.model_dump(mode="json", exclude={"canonical_sha256"})
        return cls.model_validate_json(json.dumps({**payload, "canonical_sha256": report_canonical_sha256(payload)}, ensure_ascii=False), strict=True)


class GateRunReport(ReportModel):
    schema_version: Literal["1"] = REPORT_SCHEMA_VERSION
    report_type: Literal["GATE"]
    report_id: str = Field(pattern=r"^report_[0-9a-f]{32}$")
    run_id: str = Field(pattern=r"^run_[0-9a-f]{32}$")
    project_id: str = Field(pattern=r"^[a-z][a-z0-9_-]{0,63}$")
    base_report_id: str = Field(pattern=r"^report_[0-9a-f]{32}$")
    base_report_sha256: str = Field(pattern=_SHA256)
    gate_result_id: str = Field(pattern=r"^gate_[0-9a-f]{32}$")
    semantic_input_sha256: str = Field(pattern=_SHA256)
    canonical_sha256: str = Field(pattern=_SHA256)
    run: ReportRun
    runtime: ReportRuntime
    presentation: ReportPresentation
    artifact_summary: ArtifactSummary
    versions: ReportVersions
    limitations: tuple[str, ...] = Field(default=(), max_length=256)
    gate: ReportGate

    @model_validator(mode="after")
    def validate_gate(self) -> GateRunReport:
        if self.run_id != self.run.run_id or self.project_id != self.run.project_id or self.gate.run_id != self.run_id:
            raise ValueError("gate report run identity is inconsistent")
        if self.gate_result_id != self.gate.gate_result_id:
            raise ValueError("gate report identity is inconsistent")
        _validate_presentation_identity(self)
        if self.report_id != report_id_for("GATE", self.semantic_input_sha256):
            raise ValueError("gate report ID is not deterministic")
        if self.canonical_sha256 != report_canonical_sha256(self.semantic_payload()):
            raise ValueError("gate report canonical hash is invalid")
        _validate_public(self)
        return self

    def semantic_payload(self) -> dict[str, Any]:
        return self.model_dump(mode="json", exclude={"canonical_sha256"})

    @classmethod
    def create(cls, **values: Any) -> GateRunReport:
        candidate = cls.model_construct(canonical_sha256="0" * 64, **values)
        payload = candidate.model_dump(mode="json", exclude={"canonical_sha256"})
        return cls.model_validate_json(json.dumps({**payload, "canonical_sha256": report_canonical_sha256(payload)}, ensure_ascii=False), strict=True)


ReportDocument: TypeAlias = Annotated[
    BaseRunReport | GateRunReport,
    Field(discriminator="report_type"),
]
_REPORT_ADAPTER = TypeAdapter(ReportDocument)


class ReportPackageFile(ReportModel):
    path: Literal["report.json", "report.html", "report.sarif.json", "report.junit.xml"]
    byte_count: int = Field(ge=1, le=16 * 1024 * 1024)
    sha256: str = Field(pattern=_SHA256)


class ReportPackageManifest(ReportModel):
    schema_version: Literal["1"] = REPORT_SCHEMA_VERSION
    report_id: str = Field(pattern=r"^report_[0-9a-f]{32}$")
    run_id: str = Field(pattern=r"^run_[0-9a-f]{32}$")
    report_type: Literal["BASE", "GATE"]
    base_report_id: str = Field(pattern=r"^report_[0-9a-f]{32}$")
    gate_result_id: str | None = Field(default=None, pattern=r"^gate_[0-9a-f]{32}$")
    canonical_sha256: str = Field(pattern=_SHA256)
    files: tuple[ReportPackageFile, ...] = Field(min_length=4, max_length=4)

    @model_validator(mode="after")
    def validate_manifest(self) -> ReportPackageManifest:
        if {item.path for item in self.files} != {"report.json", "report.html", "report.sarif.json", "report.junit.xml"}:
            raise ValueError("report package file set is incomplete")
        if self.report_type == "BASE" and (self.base_report_id != self.report_id or self.gate_result_id is not None):
            raise ValueError("base report manifest references are invalid")
        if self.report_type == "GATE" and (self.base_report_id == self.report_id or self.gate_result_id is None):
            raise ValueError("gate report manifest references are invalid")
        return self


def report_canonical_sha256(value: Any) -> str:
    payload = value.model_dump(mode="json") if hasattr(value, "model_dump") else value
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def artifact_summary_sha256(status: ArtifactSummaryStatus, results: tuple[ReportArtifact, ...], reason_codes: tuple[str, ...]) -> str:
    return report_canonical_sha256({
        "status": status.value,
        "results": [item.model_dump(mode="json") for item in results],
        "reason_codes": list(reason_codes),
    })


def base_semantic_input_sha256(run_id: str, publication_sha256: str, findings_snapshot_sha256: str, artifact_snapshot_sha256: str, versions: ReportVersions) -> str:
    return report_canonical_sha256({
        "report_type": "BASE",
        "run_id": run_id,
        "publication_sha256": publication_sha256,
        "findings_snapshot_sha256": findings_snapshot_sha256,
        "artifact_summary_snapshot_sha256": artifact_snapshot_sha256,
        "versions": versions.model_dump(mode="json"),
    })


def gate_semantic_input_sha256(base_report_id: str, base_report_sha256: str, gate_result_id: str, gate_input_hash: str) -> str:
    return report_canonical_sha256({
        "report_type": "GATE",
        "base_report_id": base_report_id,
        "base_report_sha256": base_report_sha256,
        "gate_result_id": gate_result_id,
        "gate_input_hash": gate_input_hash,
    })


def report_id_for(report_type: Literal["BASE", "GATE"], semantic_input_sha256: str) -> str:
    payload = {"report_type": report_type, "semantic_input_sha256": semantic_input_sha256}
    return f"report_{report_canonical_sha256(payload)[:32]}"


def parse_report_document(raw: bytes | str | dict[str, Any]) -> ReportDocument:
    value = (
        json.loads(
            raw,
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_nonfinite,
        )
        if isinstance(raw, (bytes, str))
        else raw
    )
    if not isinstance(value, dict) or value.get("schema_version") != REPORT_SCHEMA_VERSION or value.get("report_type") not in {"BASE", "GATE"}:
        raise ValueError("report root version or discriminator is invalid")
    return _REPORT_ADAPTER.validate_json(json.dumps(value, ensure_ascii=False), strict=True)


def parse_report_package_manifest(raw: bytes | str) -> ReportPackageManifest:
    value = json.loads(
        raw,
        object_pairs_hook=_reject_duplicate_keys,
        parse_constant=_reject_nonfinite,
    )
    if not isinstance(value, dict) or value.get("schema_version") != REPORT_SCHEMA_VERSION:
        raise ValueError("report manifest root version is invalid")
    return ReportPackageManifest.model_validate_json(
        json.dumps(value, ensure_ascii=False), strict=True
    )


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _reject_nonfinite(value: str) -> Any:
    raise ValueError(f"non-finite JSON value: {value}")


def report_json_schema() -> dict[str, Any]:
    """返回运行时 parser 使用的当前 Report 判别联合 Schema。"""

    return _REPORT_ADAPTER.json_schema()


def _validate_public(model: BaseRunReport | GateRunReport) -> None:
    if any(not _TOKEN.fullmatch(item) for item in model.limitations):
        raise ValueError("report limitation is not bounded")
    if redact(model.model_dump(mode="python")) != model.model_dump(mode="python"):
        raise ValueError("report contains sensitive material")


def _validate_presentation_identity(model: BaseRunReport | GateRunReport) -> None:
    presentation = model.presentation
    if presentation.run_id != model.run_id or presentation.project_id != model.project_id:
        raise ValueError("report presentation identity is inconsistent")
    if (
        presentation.run_lifecycle != model.run.lifecycle
        or presentation.run_lifecycle != model.runtime.lifecycle
        or presentation.verdict != model.run.verdict
        or presentation.verdict != model.runtime.verdict
    ):
        raise ValueError("report presentation safety facts are inconsistent")
