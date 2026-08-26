# Runner 公开协议名称；canonical、解析和生命周期模型均从正式子模块显式导出。

from .input import (
    EVIDENCE_MAX_BYTES,
    RUNNER_INPUT_MAX_BYTES,
    RUNNER_RESULT_MAX_BYTES,
    STAGED_ARTIFACT_MAX_BYTES,
    STAGED_ARTIFACT_TOTAL_MAX_BYTES,
    CleanupIssueCode,
    CleanupStatus,
    ResourceInjection,
    RunnerFailurePhase,
    RunnerInput,
    RunnerResultType,
)
from .evidence import Evidence, build_evidence
from .result import CleanupIssue, CleanupResult, RunnerError, RunnerResult, StagedArtifact
from .codec import (
    canonical_runner_json_bytes,
    canonical_runner_sha256,
    parse_evidence,
    parse_runner_input,
    parse_runner_result,
)

__all__ = [
    "EVIDENCE_MAX_BYTES",
    "RUNNER_INPUT_MAX_BYTES",
    "RUNNER_RESULT_MAX_BYTES",
    "STAGED_ARTIFACT_MAX_BYTES",
    "STAGED_ARTIFACT_TOTAL_MAX_BYTES",
    "CleanupIssue",
    "CleanupIssueCode",
    "CleanupResult",
    "CleanupStatus",
    "Evidence",
    "ResourceInjection",
    "RunnerError",
    "RunnerFailurePhase",
    "RunnerInput",
    "RunnerResult",
    "RunnerResultType",
    "StagedArtifact",
    "build_evidence",
    "canonical_runner_json_bytes",
    "canonical_runner_sha256",
    "parse_evidence",
    "parse_runner_input",
    "parse_runner_result",
]
