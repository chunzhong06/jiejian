# =============================================================================
# Artifact Check V1 严格协议
#
# 定位
#   将构建产物检查与运行时 Evidence、Verdict 和 Finding 明确分离。
#
# 安全边界
#   只保存脱敏规则命中、稳定指纹和 manifest 引用，不保存匹配文本或秘密。
# =============================================================================

from __future__ import annotations

import hashlib
import json
import re
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ..domain.identifiers import PROJECT_ID_PATTERN, RUN_ID_PATTERN, SHA256_PATTERN

_SAFE_ID = r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$"
_RELATIVE_PATH = re.compile(r"^[A-Za-z0-9_./:@+\-]{1,512}$")
RULESET_VERSION = "artifact-local-2026.08.18"


class ArtifactModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        strict=True,
        hide_input_in_errors=True,
    )

    schema_version: Literal["1"] = "1"


class ScanBudgetV1(ArtifactModel):
    # 当前扫描器刻意不并行；该字段把串行边界冻结在协议层。
    max_parallel_files: Literal[1] = 1
    max_files: int = Field(default=4096, ge=1, le=4096)
    max_file_bytes: int = Field(default=16 * 1024 * 1024, ge=1, le=64 * 1024 * 1024)
    max_total_bytes: int = Field(default=512 * 1024 * 1024, ge=1, le=1024 * 1024 * 1024)
    max_results: int = Field(default=4096, ge=1, le=4096)
    max_duration_us: int = Field(default=30_000_000, ge=1_000, le=300_000_000)
    max_compressed_layers: int = Field(default=0, ge=0, le=0)


class ArtifactCheckRequestV1(ArtifactModel):
    project_id: str = Field(pattern=PROJECT_ID_PATTERN)
    artifact_id: str = Field(pattern=_SAFE_ID)
    run_id: str | None = Field(default=None, pattern=RUN_ID_PATTERN)
    artifact_root: str = Field(min_length=1, max_length=1024)
    manifest_path: str = Field(min_length=1, max_length=1024)
    ruleset_version: Literal["artifact-local-2026.08.18"] = RULESET_VERSION
    budget: ScanBudgetV1 = Field(default_factory=ScanBudgetV1)

    @field_validator("artifact_root", "manifest_path")
    @classmethod
    def absolute_path_only(cls, value: str) -> str:
        if not re.match(r"^[A-Za-z]:[\\/]", value) and not value.startswith("/"):
            raise ValueError("artifact paths must be absolute")
        return value


class ArtifactScanStatus(StrEnum):
    COMPLETE = "COMPLETE"
    INCONCLUSIVE = "INCONCLUSIVE"


class ArtifactVerdict(StrEnum):
    SAFE = "SAFE"
    VULNERABLE = "VULNERABLE"
    INCONCLUSIVE = "INCONCLUSIVE"


class ArtifactEvidenceV1(ArtifactModel):
    evidence_id: str = Field(pattern=r"^aev_[0-9a-f]{20}$")
    source_type: Literal["ARTIFACT"] = "ARTIFACT"
    artifact_id: str = Field(pattern=_SAFE_ID)
    manifest_sha256: str = Field(pattern=SHA256_PATTERN)
    rule_id: str = Field(pattern=r"^[A-Z][A-Z0-9_]{0,63}$")
    path: str = Field(min_length=1, max_length=512)
    fingerprint: str = Field(pattern=SHA256_PATTERN)
    line: int | None = Field(default=None, ge=1, le=10_000_000)
    reason_code: str = Field(pattern=r"^[A-Z][A-Z0-9_]{0,63}$")

    @field_validator("path")
    @classmethod
    def relative_path(cls, value: str) -> str:
        if not _RELATIVE_PATH.fullmatch(value) or "\\" in value or ".." in value.split("/"):
            raise ValueError("artifact evidence path must be relative")
        return value


class ArtifactFindingV1(ArtifactModel):
    finding_id: str = Field(pattern=r"^af_[0-9a-f]{32}$")
    source_type: Literal["ARTIFACT"] = "ARTIFACT"
    artifact_id: str = Field(pattern=_SAFE_ID)
    rule_id: str = Field(pattern=r"^[A-Z][A-Z0-9_]{0,63}$")
    category: Literal[
        "SECRET_CANDIDATE",
        "FORBIDDEN_FILE",
        "SOURCE_MAP",
        "FRONTEND_SERVER_SECRET",
        "DEPENDENCY_VERSION",
    ]
    severity: Literal["low", "medium", "high", "critical"]
    path: str = Field(min_length=1, max_length=512)
    evidence_id: str = Field(pattern=r"^aev_[0-9a-f]{20}$")
    message: Literal[
        "检测到秘密候选",
        "检测到禁止发布文件",
        "检测到 Source Map",
        "前端产物包含明显服务端秘密",
        "依赖版本低于固定本地规则集要求",
    ]

    @model_validator(mode="after")
    def validate_identity(self) -> ArtifactFindingV1:
        if self.path == "" or "\\" in self.path or ".." in self.path.split("/"):
            raise ValueError("artifact finding path must be relative")
        return self


class ArtifactScanResultV1(ArtifactModel):
    project_id: str = Field(pattern=PROJECT_ID_PATTERN)
    artifact_id: str = Field(pattern=_SAFE_ID)
    run_id: str | None = Field(default=None, pattern=RUN_ID_PATTERN)
    source_type: Literal["ARTIFACT"] = "ARTIFACT"
    ruleset_version: Literal["artifact-local-2026.08.18"] = RULESET_VERSION
    status: ArtifactScanStatus
    verdict: ArtifactVerdict
    error_code: str | None = Field(default=None, pattern=r"^[A-Z][A-Z0-9_]{0,63}$")
    manifest_sha256: str = Field(pattern=SHA256_PATTERN)
    scanned_file_count: int = Field(ge=0, le=4096)
    scanned_byte_count: int = Field(ge=0, le=1024 * 1024 * 1024)
    findings: tuple[ArtifactFindingV1, ...] = Field(default=(), max_length=4096)
    evidence: tuple[ArtifactEvidenceV1, ...] = Field(default=(), max_length=4096)

    @model_validator(mode="after")
    def validate_result(self) -> ArtifactScanResultV1:
        if len(self.findings) != len(self.evidence):
            raise ValueError("artifact findings and evidence must be paired")
        if any(item.evidence_id != evidence.evidence_id for item, evidence in zip(self.findings, self.evidence)):
            raise ValueError("artifact finding evidence must be paired")
        if any(
            item.artifact_id != self.artifact_id
            or item.source_type != self.source_type
            or evidence.artifact_id != self.artifact_id
            or evidence.source_type != self.source_type
            or evidence.manifest_sha256 != self.manifest_sha256
            or item.rule_id != evidence.rule_id
            or item.path != evidence.path
            for item, evidence in zip(self.findings, self.evidence)
        ):
            raise ValueError("artifact result contains an unrelated finding")
        for item, evidence in zip(self.findings, self.evidence):
            expected_finding, expected_evidence = stable_artifact_ids(
                self.artifact_id,
                item.rule_id,
                item.path,
                evidence.fingerprint,
            )
            if item.finding_id != expected_finding or evidence.evidence_id != expected_evidence:
                raise ValueError("artifact finding identity is not stable")
        if self.status is ArtifactScanStatus.COMPLETE:
            if self.error_code is not None or self.verdict is ArtifactVerdict.INCONCLUSIVE:
                raise ValueError("complete artifact scan cannot be inconclusive")
            expected = ArtifactVerdict.VULNERABLE if self.findings else ArtifactVerdict.SAFE
            if self.verdict is not expected:
                raise ValueError("artifact verdict does not match findings")
        else:
            if self.error_code is None or self.verdict is not ArtifactVerdict.INCONCLUSIVE:
                raise ValueError("inconclusive artifact scan requires a stable error")
        return self


class ArtifactResultFileV1(ArtifactModel):
    path: Literal["artifact-result.json"]
    byte_count: int = Field(ge=1, le=4 * 1024 * 1024)
    sha256: str = Field(pattern=SHA256_PATTERN)


class ArtifactResultManifestV1(ArtifactModel):
    artifact_id: str = Field(pattern=_SAFE_ID)
    project_id: str = Field(pattern=PROJECT_ID_PATTERN)
    result_sha256: str = Field(pattern=SHA256_PATTERN)
    input_manifest_sha256: str = Field(pattern=SHA256_PATTERN)
    files: tuple[ArtifactResultFileV1, ...] = Field(min_length=1, max_length=1)


def stable_artifact_fingerprint(rule_id: str, path: str, line: int | None, kind: str) -> str:
    payload = f"{rule_id}\0{path}\0{line or 0}\0{kind}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def stable_artifact_ids(artifact_id: str, rule_id: str, path: str, fingerprint: str) -> tuple[str, str]:
    payload = json.dumps(
        {"artifact_id": artifact_id, "rule_id": rule_id, "path": path, "fingerprint": fingerprint},
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    digest = hashlib.sha256(payload).hexdigest()
    return f"af_{digest[:32]}", f"aev_{digest[:20]}"
