# Runner 输入与最小秘密环境注入模型。

from __future__ import annotations


import re

from enum import StrEnum

from typing import Literal


from pydantic import Field, model_validator


from product.backend.core.identifiers import JOB_ID_PATTERN, RUN_ID_PATTERN


from product.protocols.execution import (
    ExecutionBudget,
    ProtocolModel,
)
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


class RunnerFailurePhase(StrEnum):
    """Runner 主错误发生的有限执行阶段。"""

    TARGET_VALIDATION = "TARGET_VALIDATION"
    PREPARE_RECOVERY = "PREPARE_RECOVERY"
    IDENTITY_PREPARATION = "IDENTITY_PREPARATION"
    SETUP = "SETUP"
    BASELINE = "BASELINE"
    BEFORE = "BEFORE"
    TARGET = "TARGET"
    AFTER = "AFTER"
    EVENTUAL = "EVENTUAL"
    VERIFY = "VERIFY"
    POST_CASE_RECOVERY = "POST_CASE_RECOVERY"
    RUNTIME_CLOSE = "RUNTIME_CLOSE"


class CleanupIssueCode(StrEnum):
    """不覆盖主错误的有限清理问题类型。"""

    POST_CASE_RECOVERY_FAILED = "POST_CASE_RECOVERY_FAILED"
    IDENTITY_CLOSE_FAILED = "IDENTITY_CLOSE_FAILED"
    RUNTIME_CLOSE_FAILED = "RUNTIME_CLOSE_FAILED"
    PROCESS_TREE_CLEANUP_FAILED = "PROCESS_TREE_CLEANUP_FAILED"


class ResourceInjection(StrEnum):
    PATH_RESOURCE_ID = "PATH_RESOURCE_ID"
    JSON_RESOURCE_IDS = "JSON_RESOURCE_IDS"


def _validate_reason_codes(values: tuple[str, ...], label: str) -> tuple[str, ...]:
    if len(set(values)) != len(values) or any(
        re.fullmatch(_REASON_CODE, value) is None for value in values
    ):
        raise ValueError(f"{label} must contain unique stable codes")
    return tuple(sorted(values))


class RunnerInput(ProtocolModel):
    schema_version: Literal["1"] = "1"
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


__all__ = [name for name in globals() if not name.startswith("__")]
