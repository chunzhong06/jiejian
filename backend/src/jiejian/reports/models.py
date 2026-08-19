# =============================================================================
# 统一报告 V2 严格协议
#
# 定位
#   聚合已发布运行事实、已持久化 GateResult 和已发布 Artifact Result。
#   report.json 是唯一语义真源；HTML/SARIF/JUnit 不反向参与判定。
# =============================================================================

from __future__ import annotations

import hashlib
import json
import re
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ..redaction import redact

REPORT_SCHEMA_VERSION = "2"
REPORT_RULESET_VERSION = "report-local-2026.08.18"
_TOKEN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:/@+\-]{0,255}$")


class ReportModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        strict=True,
        hide_input_in_errors=True,
    )

    schema_version: Literal["2"] = REPORT_SCHEMA_VERSION


class ReportEvidenceRefV2(ReportModel):
    evidence_id: str = Field(pattern=r"^(?:ev_[0-9a-f]{20}|aev_[0-9a-f]{20})$")
    source_type: Literal["RUNTIME", "ARTIFACT"]


class ReportFindingV2(ReportModel):
    finding_id: str = Field(pattern=r"^(?:finding_[0-9a-f]{32}|af_[0-9a-f]{32})$")
    source_type: Literal["RUNTIME", "ARTIFACT"]
    occurrence_id: str | None = Field(default=None, pattern=r"^occ_[0-9a-f]{32}$")
    verdict: Literal["SAFE", "VULNERABLE", "INCONCLUSIVE", "SKIPPED", "ERROR"]
    severity: Literal["low", "medium", "high", "critical", "unknown"]
    evidence_refs: tuple[ReportEvidenceRefV2, ...] = Field(max_length=64)
    rule_id: str | None = Field(default=None, pattern=r"^[A-Z][A-Z0-9_]{0,63}$")
    category: str | None = Field(default=None, pattern=r"^[A-Z][A-Z0-9_]{0,63}$")
    path: str | None = Field(default=None, min_length=1, max_length=512)
    message: str | None = Field(default=None, min_length=1, max_length=128)

    @model_validator(mode="after")
    def validate_source_shape(self) -> ReportFindingV2:
        if self.source_type == "RUNTIME" and self.occurrence_id is None:
            raise ValueError("runtime report finding requires an occurrence")
        if self.source_type == "ARTIFACT" and self.occurrence_id is not None:
            raise ValueError("artifact report finding cannot contain a runtime occurrence")
        if self.source_type == "ARTIFACT" and not self.evidence_refs:
            raise ValueError("artifact report finding requires evidence")
        return self


class ReportObserverStatusV2(ReportModel):
    observer_id: str = Field(min_length=1, max_length=128)
    required: bool
    status: str = Field(pattern=r"^[A-Z][A-Z0-9_]{0,63}$")
    reason_codes: tuple[str, ...] = Field(default=(), max_length=16)

    @model_validator(mode="after")
    def validate_tokens(self) -> ReportObserverStatusV2:
        if any(not _TOKEN.fullmatch(item) for item in self.reason_codes):
            raise ValueError("observer reason code is not bounded")
        return self


class ReportRuntimeV2(ReportModel):
    lifecycle: str = Field(pattern=r"^[A-Z][A-Z0-9_]{0,31}$")
    verdict: str | None = Field(default=None, pattern=r"^[A-Z][A-Z0-9_]{0,31}$")
    evidence_refs: tuple[ReportEvidenceRefV2, ...] = Field(max_length=8192)
    findings: tuple[ReportFindingV2, ...] = Field(max_length=8192)
    observer_statuses: tuple[ReportObserverStatusV2, ...] = Field(max_length=8192)
    execution_errors: tuple[str, ...] = Field(default=(), max_length=256)

    @model_validator(mode="after")
    def validate_runtime_sources(self) -> ReportRuntimeV2:
        if any(item.source_type != "RUNTIME" for item in self.evidence_refs):
            raise ValueError("runtime facts cannot contain artifact evidence")
        if any(item.source_type != "RUNTIME" for item in self.findings):
            raise ValueError("runtime facts cannot contain artifact findings")
        if any(not _TOKEN.fullmatch(item) for item in self.execution_errors):
            raise ValueError("execution error is not bounded")
        return self


class ReportArtifactV2(ReportModel):
    artifact_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
    status: Literal["COMPLETE", "INCONCLUSIVE"]
    verdict: Literal["SAFE", "VULNERABLE", "INCONCLUSIVE"]
    error_code: str | None = Field(default=None, pattern=r"^[A-Z][A-Z0-9_]{0,63}$")
    manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    ruleset_version: str = Field(min_length=1, max_length=64)
    evidence_refs: tuple[ReportEvidenceRefV2, ...] = Field(max_length=4096)
    findings: tuple[ReportFindingV2, ...] = Field(max_length=4096)

    @model_validator(mode="after")
    def validate_artifact_sources(self) -> ReportArtifactV2:
        if any(item.source_type != "ARTIFACT" for item in self.findings):
            raise ValueError("artifact facts cannot contain runtime findings")
        if any(item.source_type != "ARTIFACT" for item in self.evidence_refs):
            raise ValueError("artifact facts cannot contain runtime evidence")
        if self.status == "COMPLETE" and self.error_code is not None:
            raise ValueError("complete artifact result cannot contain an error")
        if self.status == "INCONCLUSIVE" and self.error_code is None:
            raise ValueError("inconclusive artifact result requires an error")
        return self


class ReportGateV2(ReportModel):
    gate_result_id: str = Field(pattern=r"^gate_[0-9a-f]{32}$")
    baseline_id: str = Field(pattern=r"^baseline_[0-9a-f]{32}$")
    run_id: str = Field(pattern=r"^run_[0-9a-f]{32}$")
    policy_version: Literal["gate-v1"]
    input_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    decision: Literal["PASS", "BLOCK", "ERROR"]
    reasons: tuple[dict[str, str], ...] = Field(max_length=8192)
    evaluated_at_us: int = Field(ge=0)


class ReportVersionsV2(ReportModel):
    contract_id: str = Field(min_length=1, max_length=128)
    contract_version: int = Field(ge=1)
    engine_version: str = Field(min_length=1, max_length=64)
    runner_schema_version: Literal["1", "2"]
    observer_schema_version: Literal["1", "2"]
    report_schema_version: Literal["2"] = REPORT_SCHEMA_VERSION
    ruleset_versions: tuple[str, ...] = Field(default=(), max_length=16)


class ReportRunV2(ReportModel):
    run_id: str = Field(pattern=r"^run_[0-9a-f]{32}$")
    project_id: str = Field(pattern=r"^[a-z][a-z0-9_-]{0,63}$")
    lifecycle: str = Field(pattern=r"^[A-Z][A-Z0-9_]{0,31}$")
    verdict: str | None = Field(default=None, pattern=r"^[A-Z][A-Z0-9_]{0,31}$")
    created_at_us: int = Field(ge=0)
    finished_at_us: int | None = Field(default=None, ge=0)


class ReportV2(ReportModel):
    report_id: str = Field(pattern=r"^report_[0-9a-f]{32}$")
    run_id: str = Field(pattern=r"^run_[0-9a-f]{32}$")
    project_id: str = Field(pattern=r"^[a-z][a-z0-9_-]{0,63}$")
    gate_result_id: str = Field(pattern=r"^gate_[0-9a-f]{32}$")
    semantic_input_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    canonical_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    run: ReportRunV2
    runtime: ReportRuntimeV2
    artifacts: tuple[ReportArtifactV2, ...] = Field(max_length=256)
    gate: ReportGateV2
    versions: ReportVersionsV2
    limitations: tuple[str, ...] = Field(default=(), max_length=256)

    @model_validator(mode="after")
    def validate_report(self) -> ReportV2:
        if self.run_id != self.run.run_id or self.run_id != self.gate.run_id or self.project_id != self.run.project_id:
            raise ValueError("report run identity is inconsistent")
        if self.gate_result_id != self.gate.gate_result_id:
            raise ValueError("report gate identity is inconsistent")
        if self.report_id != report_id_for(self.run_id, self.gate_result_id, self.semantic_input_sha256):
            raise ValueError("report ID is not deterministic")
        if self.canonical_sha256 != canonical_sha256(self.semantic_payload()):
            raise ValueError("report canonical hash is invalid")
        if any(not _TOKEN.fullmatch(item) for item in self.limitations):
            raise ValueError("report limitation is not bounded")
        if redact(self.model_dump(mode="python")) != self.model_dump(mode="python"):
            raise ValueError("report contains sensitive material")
        return self

    def semantic_payload(self) -> dict[str, Any]:
        return self.model_dump(mode="json", exclude={"canonical_sha256"})

    @classmethod
    def create(cls, **values: Any) -> ReportV2:
        candidate = cls.model_construct(canonical_sha256="0" * 64, **values)
        canonical = canonical_sha256(candidate.semantic_payload())
        return cls.model_validate_json(
            json.dumps({**candidate.model_dump(mode="json"), "canonical_sha256": canonical}, ensure_ascii=False),
            strict=True,
        )


class ReportPackageFileV2(ReportModel):
    path: Literal["report.json", "report.html", "report.sarif.json", "report.junit.xml"]
    byte_count: int = Field(ge=1, le=16 * 1024 * 1024)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class ReportPackageManifestV2(ReportModel):
    report_id: str = Field(pattern=r"^report_[0-9a-f]{32}$")
    run_id: str = Field(pattern=r"^run_[0-9a-f]{32}$")
    gate_result_id: str = Field(pattern=r"^gate_[0-9a-f]{32}$")
    report_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    files: tuple[ReportPackageFileV2, ...] = Field(min_length=4, max_length=4)

    @model_validator(mode="after")
    def validate_files(self) -> ReportPackageManifestV2:
        if {item.path for item in self.files} != {"report.json", "report.html", "report.sarif.json", "report.junit.xml"}:
            raise ValueError("report package file set is incomplete")
        return self


def canonical_sha256(value: Any) -> str:
    payload = value.model_dump(mode="json") if hasattr(value, "model_dump") else value
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def report_id_for(run_id: str, gate_result_id: str, semantic_input_sha256: str) -> str:
    return f"report_{canonical_sha256((run_id, gate_result_id, semantic_input_sha256))[:32]}"
