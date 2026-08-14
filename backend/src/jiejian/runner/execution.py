# =============================================================================
# Verification Runner 进程适配
#
# 定位
#   Runner V1 协议与 Verification 核心之间的独立进程边界
#
# 职责
#   严格加载输入｜构造 VerificationSnapshot 并执行｜写入可信结果或错误文件
#
# 调用链
#   runner.__main__ → execute_runner_attempt → SnapshotRunExecutor → staging / RunnerResultV1
# =============================================================================

from __future__ import annotations

import hashlib
import os
import time
import json
from collections.abc import Callable, Mapping
from pathlib import Path
from uuid import uuid4

from ..domain.lifecycle import JobState, RunLifecycle
from ..verification.models import ReasonCode
from ..errors import ErrorCode, JiejianError
from ..protocols import (
    RUNNER_INPUT_MAX_BYTES,
    CleanupResultV1,
    CleanupStatus,
    RunnerErrorV1,
    RunnerInputV1,
    RunnerResultType,
    RunnerResultV1,
    StagedArtifactV1,
    canonical_json_bytes,
    parse_runner_input,
)
from ..verification.execution import SnapshotRunExecutor, VerificationSnapshot
from .execution_v2 import execute_runner_v2_attempt

RUNNER_EXIT_OK = 0
RUNNER_EXIT_PROTOCOL = 64
RUNNER_EXIT_INTERNAL = 70
RUNNER_EXIT_WRITE = 74

_SAFETY_ERRORS = {
    ErrorCode.SCOPE_URL.value,
    ErrorCode.SCOPE_HOST.value,
    ErrorCode.SCOPE_PORT.value,
    ErrorCode.SCOPE_PRIVATE_NETWORK.value,
    ErrorCode.SCOPE_REDIRECT.value,
    ErrorCode.EXEC_BUDGET.value,
    ErrorCode.EXEC_RESPONSE_TOO_LARGE.value,
}
_RETRYABLE_ERRORS = {ErrorCode.EXEC_REQUEST.value, ErrorCode.EXEC_TIMEOUT.value}


def execute_runner_attempt(
    input_path: Path,
    staging_dir: Path,
    *,
    environ: Mapping[str, str] | None = None,
    finished_at_us: Callable[[], int] | None = None,
) -> int:
    """执行一次 Runner 并在当前 attempt staging 中形成可信结果。

    关键说明
        返回的进程退出码不表示 PASS、BLOCK 或 INCONCLUSIVE。
    """

    environment = os.environ if environ is None else environ
    try:
        if input_path.stat().st_size <= RUNNER_INPUT_MAX_BYTES:
            header = json.loads(input_path.read_bytes().decode("utf-8"))
            if isinstance(header, dict) and header.get("schema_version") == "2":
                return execute_runner_v2_attempt(input_path, staging_dir, environ=environment, finished_at_us=finished_at_us)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        pass
    clock = finished_at_us or (lambda: time.time_ns() // 1_000)
    try:
        runner_input, known_secrets = _load_input(input_path, environment)
    except (JiejianError, OSError):
        return RUNNER_EXIT_PROTOCOL

    staging = staging_dir.resolve()
    result_path = staging / "result.json"
    cancel_path = staging.parent / "cancel.requested"
    artifacts_dir = staging / "artifacts"
    try:
        staging.mkdir(parents=True, exist_ok=False)
        snapshot = _verification_snapshot(runner_input)
        try:
            result = SnapshotRunExecutor(
                environ=environment,
                cancellation_requested=cancel_path.exists,
                executor_process_id=os.getpid(),
            ).run(
                snapshot,
                run_id=runner_input.run_id,
                artifact_dir=Path("projects")
                / snapshot.project_id
                / "runs"
                / runner_input.run_id,
                destination_dir=artifacts_dir,
            )
            protocol_result = RunnerResultV1(
                schema_version="1",
                run_id=runner_input.run_id,
                job_id=runner_input.job_id,
                attempt=runner_input.attempt,
                lease_owner=runner_input.lease_owner,
                fencing_token=runner_input.fencing_token,
                finished_at_us=clock(),
                result_type=RunnerResultType.SUCCESS,
                run_lifecycle=RunLifecycle.COMPLETED,
                job_state=JobState.SUCCEEDED,
                verdict=result.verdict,
                reason_codes=result.reason_codes,
                cleanup=CleanupResultV1(
                    schema_version="1",
                    status=CleanupStatus.SUCCEEDED,
                ),
                error=None,
                artifacts=_artifacts(staging),
            )
        except JiejianError as exc:
            protocol_result = _error_result(runner_input, exc, clock())
        _write_result(result_path, protocol_result, known_secrets)
        return RUNNER_EXIT_OK
    except JiejianError:
        return RUNNER_EXIT_WRITE
    except OSError:
        return RUNNER_EXIT_WRITE
    except Exception:
        return RUNNER_EXIT_INTERNAL


def _load_input(
    input_path: Path,
    environ: Mapping[str, str],
) -> tuple[RunnerInputV1, tuple[str, ...]]:
    if input_path.stat().st_size > RUNNER_INPUT_MAX_BYTES:
        raise JiejianError("PROTOCOL_TOO_LARGE", "Runner 输入超过大小限制")
    raw = input_path.read_bytes()
    preliminary = parse_runner_input(raw)
    secret_names = tuple(
        dict.fromkeys(
            identity.secret_ref.removeprefix("env:")
            for identity in preliminary.project_snapshot.identities
        )
    )
    known_secrets = tuple(environ[name] for name in secret_names if environ.get(name))
    return parse_runner_input(raw, known_secrets=known_secrets), known_secrets


def _verification_snapshot(runner_input: RunnerInputV1) -> VerificationSnapshot:
    source = runner_input.project_snapshot
    return VerificationSnapshot(
        project_id=source.project_id,
        project_name=source.project_name,
        target=source.target,
        identities=source.identities,
        resources=source.resources,
        flow=source.flow,
        contract=source.contract,
        owner_observer_enabled=source.owner_observer_enabled,
        mutation_seed=source.mutation_seed,
    )


def _error_result(
    runner_input: RunnerInputV1,
    error: JiejianError,
    finished_at_us: int,
) -> RunnerResultV1:
    if error.code == ErrorCode.EXEC_CANCELLED.value:
        result_type = RunnerResultType.CANCELLED
        lifecycle = RunLifecycle.CANCELLED
        job_state = JobState.CANCELLED
        cleanup = CleanupResultV1(schema_version="1", status=CleanupStatus.SUCCEEDED)
        runner_error = None
    elif error.code in _SAFETY_ERRORS:
        result_type = RunnerResultType.SAFETY_STOPPED
        lifecycle = RunLifecycle.SAFETY_STOPPED
        job_state = JobState.SUCCEEDED
        cleanup = CleanupResultV1(schema_version="1", status=CleanupStatus.SUCCEEDED)
        runner_error = None
    elif error.code in _RETRYABLE_ERRORS:
        result_type = RunnerResultType.RETRYABLE_ERROR
        lifecycle = RunLifecycle.EXECUTING
        job_state = JobState.RETRY_WAIT
        cleanup = CleanupResultV1(schema_version="1", status=CleanupStatus.SUCCEEDED)
        runner_error = RunnerErrorV1(
            schema_version="1",
            code=error.code,
            retryable=True,
        )
    else:
        result_type = RunnerResultType.FATAL_ERROR
        lifecycle = RunLifecycle.FAILED
        job_state = JobState.FAILED
        cleanup_failed = error.code == ReasonCode.CLEANUP_FAILED.value
        cleanup = CleanupResultV1(
            schema_version="1",
            status=CleanupStatus.FAILED if cleanup_failed else CleanupStatus.NOT_REQUIRED,
            reason_codes=(ReasonCode.CLEANUP_FAILED.value,) if cleanup_failed else (),
        )
        runner_error = RunnerErrorV1(
            schema_version="1",
            code=(
                error.code
                if error.code.isupper() and len(error.code) <= 128
                else "RUNNER_FATAL"
            ),
            retryable=False,
        )
    return RunnerResultV1(
        schema_version="1",
        run_id=runner_input.run_id,
        job_id=runner_input.job_id,
        attempt=runner_input.attempt,
        lease_owner=runner_input.lease_owner,
        fencing_token=runner_input.fencing_token,
        finished_at_us=finished_at_us,
        result_type=result_type,
        run_lifecycle=lifecycle,
        job_state=job_state,
        verdict=None,
        reason_codes=(error.code,),
        cleanup=cleanup,
        error=runner_error,
        artifacts=(),
    )


def _artifacts(staging: Path) -> tuple[StagedArtifactV1, ...]:
    records = []
    for path in sorted(item for item in staging.rglob("*") if item.is_file()):
        if path.name == "result.json" or path.name.startswith(".result.json.tmp-"):
            continue
        raw = path.read_bytes()
        records.append(
            StagedArtifactV1(
                schema_version="1",
                path=path.relative_to(staging).as_posix(),
                byte_count=len(raw),
                sha256=hashlib.sha256(raw).hexdigest(),
            )
        )
    return tuple(records)


def _write_result(
    path: Path,
    result: RunnerResultV1,
    known_secrets: tuple[str, ...],
) -> None:
    encoded = canonical_json_bytes(result, known_secrets=known_secrets)
    temporary = path.with_name(f".{path.name}.tmp-{uuid4().hex}")
    try:
        with temporary.open("xb") as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except OSError:
        raise JiejianError(ErrorCode.ARTIFACT_WRITE, "Runner 结果写入失败") from None
    finally:
        temporary.unlink(missing_ok=True)
