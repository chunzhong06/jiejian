# =============================================================================
# Runner 组合根
#
# 定位
#   唯一生产 Target Runtime 注册与 Runner attempt 文件入口。
#
# 职责
#   解析 RunnerInput｜注册 Web Runtime｜调度 Case｜写入 staging｜关闭 attempt 后收敛结果。
#
# 边界
#   具体 Case 编排在通用 Executor；本模块只负责组合和 attempt 结果收敛。
# =============================================================================

from __future__ import annotations

import hashlib
import os
import time
from collections.abc import Callable, Mapping
from pathlib import Path

from pydantic import ValidationError

from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.core.lifecycle import CaseVerdict, JobState, RunLifecycle, RunVerdict
from product.backend.core.verification.differential import TwinExecutionRole
from product.backend.infra.execution.port import TargetRuntimeContext
from product.backend.infra.execution.registry import TargetRuntimeRegistry
from product.backend.infra.execution.web.runtime import WebTargetRuntimeFactory
from product.backend.infra.runtime.runner.executor import RunnerExecutor
from product.backend.infra.runtime.runner.result_builder import evidence_from_case, run_verdict
from product.backend.infra.runtime.runner.staging import atomic_write, write_evidence
from product.protocols import CleanupResult, CleanupStatus, RunnerError, RunnerInput, RunnerResult, RunnerResultType, canonical_runner_json_bytes, parse_runner_input, required_web_secret_refs


RUNNER_EXIT_OK = 0
RUNNER_EXIT_PROTOCOL = 64
RUNNER_EXIT_INTERNAL = 70
RUNNER_EXIT_WRITE = 74


def _now_us() -> int:
    return time.time_ns() // 1_000


def build_target_runtime_registry() -> TargetRuntimeRegistry:
    """构造唯一生产注册表；当前只注册 Web Target Runtime。"""

    registry = TargetRuntimeRegistry()
    registry.register(WebTargetRuntimeFactory())
    return registry


def _result_error(document: RunnerInput, code: str, *, finished_at_us: int, cleanup_finished_at_us: int | None = None, cleanup_failed: bool = False, cancelled: bool = False, safety_stopped: bool = False) -> RunnerResult:
    if cleanup_failed:
        code = ErrorCode.CLEANUP_FAILED.value
        cancelled = False
        safety_stopped = False
    if cancelled:
        result_type = RunnerResultType.CANCELLED
        lifecycle = RunLifecycle.CANCELLED
        job_state = JobState.CANCELLED
        reasons = ()
        error = None
    elif safety_stopped:
        result_type = RunnerResultType.SAFETY_STOPPED
        lifecycle = RunLifecycle.SAFETY_STOPPED
        job_state = JobState.SUCCEEDED
        reasons = (code,)
        error = None
    else:
        result_type = RunnerResultType.FATAL_ERROR
        lifecycle = RunLifecycle.FAILED
        job_state = JobState.FAILED
        reasons = (code,)
        error = RunnerError(code=code, retryable=False)
    return RunnerResult(
        run_id=document.run_id,
        job_id=document.job_id,
        attempt=document.attempt,
        lease_owner=document.lease_owner,
        fencing_token=document.fencing_token,
        finished_at_us=finished_at_us,
        result_type=result_type,
        run_lifecycle=lifecycle,
        job_state=job_state,
        verdict=None,
        reason_codes=reasons,
        cleanup=CleanupResult(status=CleanupStatus.FAILED if cleanup_failed else CleanupStatus.SUCCEEDED, finished_at_us=cleanup_finished_at_us if cleanup_finished_at_us is not None else finished_at_us, reason_codes=(ErrorCode.CLEANUP_FAILED.value,) if cleanup_failed else ()),
        error=error,
        plan_fingerprint=document.project_snapshot.plan.plan_fingerprint,
        coverage_record_count=len(document.project_snapshot.plan.coverage),
        coverage_gap_count=len(document.project_snapshot.plan.gaps),
        evidence=(),
        artifacts=(),
    )


def execute_attempt(input_path: Path, staging_dir: Path, *, environ: Mapping[str, str] | None = None, finished_at_us: Callable[[], int] | None = None) -> int:
    """执行完整 attempt，并在 Runtime 关闭后写入最终 RunnerResult。"""

    environment = os.environ if environ is None else environ
    try:
        raw = input_path.read_bytes()
        preliminary = parse_runner_input(raw)
        known_secrets = tuple(dict.fromkeys(environment[name.removeprefix("env:")] for name in required_web_secret_refs(preliminary.project_snapshot) if environment.get(name.removeprefix("env:"))))
        document = parse_runner_input(raw, known_secrets=known_secrets)
    except (OSError, JiejianError, ValidationError, ValueError):
        return RUNNER_EXIT_PROTOCOL

    staging = staging_dir.resolve()
    finish_clock = finished_at_us or _now_us
    try:
        staging.mkdir(parents=True, exist_ok=False)
        web_factory = build_target_runtime_registry().factory(document.project_snapshot.target_type.value)
        cancellation_requested = lambda: (staging.parent / "cancel.requested").is_file()
        executor = RunnerExecutor(document, runtime_factory=web_factory, environ=environment, staging=staging, clock=finish_clock, cancellation_requested=cancellation_requested)
        evidences = []
        artifacts = []
        failure: tuple[str, bool, bool, bool] | None = None
        try:
            paired: set[str] = set()
            for twin in document.project_snapshot.differential_plan.twins:
                allow = executor.run_case(twin.allow_case, twin=twin, twin_role=TwinExecutionRole.ALLOW_CONTROL, allow_control_valid=True)
                deny = executor.run_case(twin.deny_case, twin=twin, twin_role=TwinExecutionRole.DENY_VARIANT, allow_control_valid=allow.verdict is CaseVerdict.SAFE)
                evidences.extend((evidence_from_case(document, allow), evidence_from_case(document, deny)))
                paired.update((twin.allow_case.case_id, twin.deny_case.case_id))
            for case in document.project_snapshot.plan.cases:
                if case.case_id not in paired:
                    evidences.append(evidence_from_case(document, executor.run_case(case)))
            artifacts = [write_evidence(staging, item, known_secrets=known_secrets) for item in evidences]
        except JiejianError as exc:
            failure = (
                exc.code,
                exc.code == ErrorCode.EXEC_CANCELLED.value,
                exc.code in {
                    ErrorCode.SCOPE_URL.value,
                    ErrorCode.SCOPE_HOST.value,
                    ErrorCode.SCOPE_PORT.value,
                    ErrorCode.SCOPE_PRIVATE_NETWORK.value,
                    ErrorCode.SCOPE_REDIRECT.value,
                    ErrorCode.EXEC_BUDGET.value,
                    ErrorCode.EXEC_RESPONSE_TOO_LARGE.value,
                },
                exc.code == ErrorCode.CLEANUP_FAILED.value,
            )
        except Exception:
            failure = ("RUNNER_FATAL", False, False, False)
        close_failed = False
        try:
            executor.close()
        except Exception:
            close_failed = True
        cleanup_finished_at_us = finish_clock()
        result_finished_at_us = finish_clock()
        if close_failed or (failure is not None and failure[3]):
            result = _result_error(
                document,
                ErrorCode.CLEANUP_FAILED.value,
                finished_at_us=result_finished_at_us,
                cleanup_finished_at_us=cleanup_finished_at_us,
                cleanup_failed=True,
            )
        elif failure is not None:
            code, cancelled, safety_stopped, _cleanup_failed = failure
            result = _result_error(
                document,
                code,
                finished_at_us=result_finished_at_us,
                cleanup_finished_at_us=cleanup_finished_at_us,
                cancelled=cancelled,
                safety_stopped=safety_stopped,
            )
        else:
            result = RunnerResult(
                run_id=document.run_id,
                job_id=document.job_id,
                attempt=document.attempt,
                lease_owner=document.lease_owner,
                fencing_token=document.fencing_token,
                finished_at_us=result_finished_at_us,
                result_type=RunnerResultType.SUCCESS,
                run_lifecycle=RunLifecycle.COMPLETED,
                job_state=JobState.SUCCEEDED,
                verdict=run_verdict(
                    evidences,
                    has_gaps=bool(document.project_snapshot.plan.gaps),
                ),
                reason_codes=(),
                cleanup=CleanupResult(
                    status=CleanupStatus.SUCCEEDED,
                    finished_at_us=cleanup_finished_at_us,
                ),
                error=None,
                plan_fingerprint=document.project_snapshot.plan.plan_fingerprint,
                coverage_record_count=len(document.project_snapshot.plan.coverage),
                coverage_gap_count=len(document.project_snapshot.plan.gaps),
                evidence=tuple(evidences),
                artifacts=tuple(artifacts),
            )
        atomic_write(staging / "result.json", canonical_runner_json_bytes(result, known_secrets=known_secrets))
        return RUNNER_EXIT_OK
    except (OSError, JiejianError, ValidationError, ValueError):
        return RUNNER_EXIT_WRITE
    except Exception:
        return RUNNER_EXIT_INTERNAL
