# 自动代码参考：后端 Runtime

> 生成区域只描述当前代码结构；职责与安全理由由模块参考和任务指南维护。

<!-- GENERATED:START -->

<!-- 此区域由 scripts/docs/generate.py 从 product/backend/infra/runtime/ 读取。 -->

### `product/backend/infra/runtime/__init__.py`
主要 import / dot-source：`.paths`

### `product/backend/infra/runtime/diagnostics.py`
- `class DoctorCheck`
- `class DoctorReport`
- `browser_availability() -> str`
- `runtime_environment_details() -> dict[str, Any]`
- `run_doctor(config_path, cli_overrides, project_root) -> DoctorReport`
- `human_lines(report) -> tuple[str, ...]`
主要 import / dot-source：`__future__`, `importlib.metadata`, `ipaddress`, `json`, `os`, `pathlib`, `product.backend.core.errors`, `product.backend.core.redaction`, `product.backend.infra.runtime.logging`, `product.backend.infra.runtime.process.identity`, `product.backend.infra.runtime.settings`, `pydantic`, `shutil`, `socket`, `sqlite3`, `subprocess`, `sys`, `tempfile`, `typing`

### `product/backend/infra/runtime/jobs/attempts.py`
- `_TERMINAL_JOB_STATES`
- `class JobAttempts`
主要 import / dot-source：`__future__`, `collections.abc`, `product.backend.core.errors`, `product.backend.core.lifecycle`, `product.backend.infra.runtime.jobs.events`, `product.backend.infra.runtime.jobs.models`, `product.backend.infra.runtime.jobs.targets`, `product.backend.infra.storage`, `secrets`

### `product/backend/infra/runtime/jobs/dispatch.py`
- `WORKER_LOG_MAX_BYTES`
- `WORKER_LOG_BACKUPS`
- `class WorkerDispatcher`
主要 import / dot-source：`__future__`, `collections.abc`, `dataclasses`, `hashlib`, `json`, `os`, `pathlib`, `product.backend.core.errors`, `product.backend.core.identifiers`, `product.backend.core.lifecycle`, `product.backend.infra.artifacts.run_packages`, `product.backend.infra.runtime.paths`, `product.backend.infra.runtime.process.environment`, `product.backend.infra.runtime.process.tree`, `product.backend.infra.runtime.worker.lifetime`, `product.backend.infra.storage`, `product.protocols`, `pydantic`, `re`, `subprocess`, `sys`, `time`, `typing`

### `product/backend/infra/runtime/jobs/events.py`
- `append_job_event(work, job, event_type, source_state, target_state, occurred_at_us, metadata) -> None`
主要 import / dot-source：`__future__`, `product.backend.core.lifecycle`, `product.backend.infra.runtime.jobs.models`, `product.backend.infra.storage`

### `product/backend/infra/runtime/jobs/factory.py`
- `class WorkerHandlerFactory`
主要 import / dot-source：`__future__`, `collections.abc`, `pathlib`, `product.backend.infra.artifacts.run_packages`, `product.backend.infra.artifacts.scan_job`, `product.backend.infra.recording.request_store`, `product.backend.infra.runtime.jobs.attempts`, `product.backend.infra.runtime.jobs.handlers`, `product.backend.infra.runtime.jobs.recording`, `product.backend.infra.runtime.jobs.requests`, `product.backend.infra.runtime.jobs.targets`, `product.backend.infra.runtime.jobs.verification`, `product.backend.infra.storage`

### `product/backend/infra/runtime/jobs/handlers.py`
- `class JobHandler`
- `class JobAttemptPort`
- `class JobHandlerRegistry`
主要 import / dot-source：`__future__`, `collections.abc`, `product.backend.core.errors`, `product.backend.infra.runtime.jobs.models`, `product.backend.infra.runtime.jobs.targets`, `product.backend.infra.storage`, `typing`

### `product/backend/infra/runtime/jobs/models.py`
- `MAX_LEASE_DURATION_US`
- `MAX_RETRY_DELAY_US`
- `MAX_RECOVERY_SCAN_ITEMS`
- `_MAX_SQLITE_INTEGER`
- `class JobEventType`
- `class RetryableFailureCode`
- `class FatalFailureCode`
- `class RecoveryProofType`
- `class RecoveryOperator`
- `class RecoveryReasonCode`
- `class WorkerControlModel`
- `class RetryPolicy`
- `class SubmitJob`
- `class ClaimJob`
- `class RenewLease`
- `class RequestCancellation`
- `class WaitingFatalFailure`
- `class FencedJobMutation`
- `class CompleteCancellation`
- `class RetryableFailure`
- `class FatalFailure`
- `class RecoveryScan`
- `class ConfirmRecovery`
- `class JobSubmissionResult`
- `class ClaimedJob`
- `class JobMutationResult`
- `class CancellationResult`
- `class RecoveryCandidate`
- `validate_control_request(request, known_secrets) -> None`
- `checked_time_add(left, right) -> int`
- `compute_retry_available_at(policy, jitter_source, now_us, attempt) -> int`
主要 import / dot-source：`__future__`, `collections.abc`, `enum`, `product.backend.core.errors`, `product.backend.core.identifiers`, `product.backend.infra.storage`, `product.protocols.runner`, `pydantic`, `typing`

### `product/backend/infra/runtime/jobs/queue.py`
- `_TERMINAL_JOB_STATES`
- `class JobQueue`
主要 import / dot-source：`__future__`, `collections.abc`, `product.backend.core.errors`, `product.backend.core.lifecycle`, `product.backend.infra.runtime.jobs.events`, `product.backend.infra.runtime.jobs.models`, `product.backend.infra.runtime.jobs.targets`, `product.backend.infra.storage`, `uuid`

### `product/backend/infra/runtime/jobs/reconciliation.py`
- `class ReconciliationResult`
- `class RunReconciler`
主要 import / dot-source：`__future__`, `collections.abc`, `os`, `pathlib`, `product.backend.core.errors`, `product.backend.core.lifecycle`, `product.backend.infra.artifacts.run_packages`, `product.backend.infra.artifacts.run_publication`, `product.backend.infra.runtime.paths`, `product.backend.infra.storage`, `pydantic`, `time`, `typing`, `uuid`

### `product/backend/infra/runtime/jobs/recording.py`
- `_CANCEL_PATH_ENV`
- `_ATTEMPT_DIR_ENV`
- `class RecordingSubmissionPort`
- `class RecordingJobHandler`
- `class RecordingJobTargetHandler`
主要 import / dot-source：`__future__`, `collections.abc`, `logging`, `os`, `pathlib`, `product.backend.core.errors`, `product.backend.core.lifecycle`, `product.backend.core.recording`, `product.backend.infra.recording.control`, `product.backend.infra.recording.request_store`, `product.backend.infra.runtime.jobs.handlers`, `product.backend.infra.runtime.jobs.models`, `product.backend.infra.runtime.jobs.targets`, `product.backend.infra.runtime.paths`, `product.backend.infra.runtime.process.control`, `product.backend.infra.runtime.process.environment`, `product.backend.infra.runtime.process.tree`, `product.backend.infra.storage`, `product.protocols`, `subprocess`, `tempfile`, `time`, `typing`

### `product/backend/infra/runtime/jobs/recovery.py`
- `_TERMINAL_JOB_STATES`
- `class JobRecovery`
主要 import / dot-source：`__future__`, `collections.abc`, `product.backend.core.errors`, `product.backend.core.lifecycle`, `product.backend.infra.runtime.jobs.events`, `product.backend.infra.runtime.jobs.models`, `product.backend.infra.runtime.jobs.targets`, `product.backend.infra.storage`, `secrets`

### `product/backend/infra/runtime/jobs/requests.py`
- `class ExecutionRequestStore`
主要 import / dot-source：`__future__`, `collections.abc`, `hashlib`, `hmac`, `os`, `pathlib`, `product.backend.core.errors`, `product.backend.core.identifiers`, `product.backend.infra.runtime.paths`, `product.protocols`, `product.protocols.execution_request`, `re`, `uuid`

### `product/backend/infra/runtime/jobs/targets.py`
- `class JobTargetType`
- `class JobTargetOutcome`
- `class JobTargetHandler`
- `class JobTargetRegistry`
- `class RunJobTargetHandler`
- `default_run_job_targets() -> JobTargetRegistry`
主要 import / dot-source：`__future__`, `enum`, `product.backend.core.errors`, `product.backend.core.lifecycle`, `product.backend.infra.storage`, `typing`

### `product/backend/infra/runtime/jobs/verification.py`
- `_LOGGER`
- `class ResultFinalizerPort`
- `class VerificationRunJobHandler`
主要 import / dot-source：`__future__`, `collections.abc`, `logging`, `pathlib`, `product.backend.core.errors`, `product.backend.infra.artifacts.run_packages`, `product.backend.infra.artifacts.run_publication`, `product.backend.infra.runtime.jobs.attempts`, `product.backend.infra.runtime.jobs.handlers`, `product.backend.infra.runtime.jobs.reconciliation`, `product.backend.infra.runtime.jobs.requests`, `product.backend.infra.runtime.runner.supervisor`, `product.backend.infra.storage`, `typing`

### `product/backend/infra/runtime/logging.py`
- `class JsonFormatter`
- `configure_logging(level, stream, trace_id, var_dir, console, known_secrets) -> stdlib_logging.Logger`
主要 import / dot-source：`__future__`, `collections.abc`, `datetime`, `json`, `logging`, `logging.handlers`, `pathlib`, `product.backend.core.redaction`, `product.backend.infra.runtime.paths`, `sys`, `typing`

### `product/backend/infra/runtime/maintenance.py`
- `_ORPHAN_MIN_AGE_SECONDS`
- `_LOG_MAX_AGE_SECONDS`
- `_LOG_KEEP_PER_CATEGORY`
- `_SESSION_MTIME_TOLERANCE_SECONDS`
- `_PLAN_TTL_SECONDS`
- `_OPERATIONS`
- `class MaintenanceCandidate`
- `class MaintenancePlan`
- `class LocalMaintenanceService`
主要 import / dot-source：`__future__`, `collections.abc`, `contextlib`, `dataclasses`, `hashlib`, `json`, `os`, `pathlib`, `product.backend.core.errors`, `product.backend.infra.runtime.paths`, `product.backend.infra.runtime.process.lock`, `secrets`, `shutil`, `time`

### `product/backend/infra/runtime/paths.py`
- `class RuntimePaths`
主要 import / dot-source：`__future__`, `dataclasses`, `pathlib`

### `product/backend/infra/runtime/process/__init__.py`
- `_EXPORTS`
主要 import / dot-source：`importlib`

### `product/backend/infra/runtime/process/bootstrap.py`
- `_GATE_TIMEOUT_SECONDS`
- `main() -> int`
主要 import / dot-source：`__future__`, `argparse`, `pathlib`, `runpy`, `sys`, `time`

### `product/backend/infra/runtime/process/control.py`
- `DEFAULT_LEASE_DURATION_US`
- `DEFAULT_POLL_INTERVAL_SECONDS`
- `DEFAULT_TERMINATION_GRACE_SECONDS`
- `force_terminate_process_tree(process, timeout) -> None`
- `class AttemptProcessControl`
主要 import / dot-source：`__future__`, `collections.abc`, `logging`, `pathlib`, `product.backend.core.errors`, `product.backend.infra.runtime.jobs.handlers`, `product.backend.infra.runtime.jobs.models`, `product.backend.infra.runtime.process.tree`, `product.backend.infra.storage`, `subprocess`, `time`, `typing`

### `product/backend/infra/runtime/process/environment.py`
- `class ProcessEnvironmentRole`
- `_COMMON_SOURCE_NAMES`
- `_ROLE_POLICIES`
- `_COMMON_IDENTITY_NAMES`
- `_RUNTIME_IDENTITY_NAMES`
- `_ALL_IDENTITY_NAMES`
- `_MAIN_PROCESS_ONLY_NAMES`
- `_FORCED_ENVIRONMENT_NAMES`
- `_ROLE_CONTROLLED_NAMES`
- `_CONTROLLED_NAME_CASEFOLDS`
- `_ENVIRONMENT_NAME_PATTERN`
- `_FAILURE_REASON_BY_MESSAGE`
- `process_environment_failure_summary(error) -> dict[str, object]`
- `minimal_process_environment(source, role, secret_names) -> dict[str, str]`
- `confirmed_python_executable(source) -> str`
- `python_module_command(source, module, *arguments) -> list[str]`
- `spawn_python_module(source, module, *arguments, role, secret_names, extra_environment, cwd, popen, python_executable, tree_name, before_release, **kwargs) -> subprocess.Popen[Any]`
- `run_python_module(source, module, *arguments, role, cwd, timeout_seconds, secret_names, extra_environment, python_executable) -> subprocess.CompletedProcess[str]`
主要 import / dot-source：`__future__`, `collections.abc`, `dataclasses`, `enum`, `os`, `pathlib`, `product.backend.core.errors`, `product.backend.infra.runtime.paths`, `product.backend.infra.runtime.process.tree`, `re`, `subprocess`, `sys`, `types`, `typing`, `uuid`

### `product/backend/infra/runtime/process/identity.py`
- `SUPPORTED_PYTHON`
- `_RUNTIME_MODES`
- `_IDENTITY_KEYS`
- `_RUNTIME_PACKAGES`
- `python_environment_report(environment, package_names) -> dict[str, Any]`
- `require_python_environment(environment) -> dict[str, Any]`
主要 import / dot-source：`__future__`, `collections.abc`, `hashlib`, `importlib.metadata`, `importlib.util`, `json`, `os`, `pathlib`, `product.backend.core.errors`, `site`, `sys`, `typing`, `urllib.parse`

### `product/backend/infra/runtime/process/lock.py`
- `try_lock_stream(stream) -> bool`
- `unlock_stream(stream) -> None`
- `lock_is_available(path) -> bool`
主要 import / dot-source：`__future__`, `os`, `pathlib`, `typing`

### `product/backend/infra/runtime/process/tree.py`
- `_CONTROLLERS`
- `_NATIVE_POPEN`
- `class ProcessTreeController`
- `spawn_managed_process(command, popen, tree_name, **kwargs) -> subprocess.Popen[Any]`
- `controller_for(process) -> ProcessTreeController | None`
- `release_process_tree(process, timeout) -> None`
- `terminate_process_tree(process, timeout) -> None`
- `process_tree_has_exited(process) -> bool`
- `kernel_tree_has_exited(identity) -> bool`
主要 import / dot-source：`__future__`, `collections.abc`, `ctypes`, `ctypes.wintypes`, `os`, `product.backend.core.errors`, `signal`, `subprocess`, `time`, `typing`, `weakref`

### `product/backend/infra/runtime/runner/__main__.py`
- `main() -> int`
主要 import / dot-source：`__future__`, `argparse`, `pathlib`, `product.backend.infra.runtime.runner.executor`

### `product/backend/infra/runtime/runner/case_orchestrator.py`
- `class CaseResult`
- `class CaseExecutionFailure`
- `class CaseOrchestrator`
主要 import / dot-source：`__future__`, `dataclasses`, `product.backend.core.errors`, `product.backend.core.lifecycle`, `product.backend.core.verification.differential`, `product.backend.core.verification.facts`, `product.backend.core.verification.permissions.coverage`, `product.backend.infra.execution.port`, `product.backend.infra.observers.coordinator`, `product.protocols`, `product.protocols.execution`, `typing`

### `product/backend/infra/runtime/runner/composition.py`
- `RUNNER_EXIT_OK`
- `RUNNER_EXIT_PROTOCOL`
- `RUNNER_EXIT_INTERNAL`
- `RUNNER_EXIT_WRITE`
- `_SAFETY_STOP_CODES`
- `build_target_runtime_registry() -> TargetRuntimeRegistry`
- `execute_attempt(input_path, staging_dir, environ, finished_at_us) -> int`
主要 import / dot-source：`__future__`, `collections.abc`, `dataclasses`, `hashlib`, `os`, `pathlib`, `product.backend.core.errors`, `product.backend.core.lifecycle`, `product.backend.core.verification.differential`, `product.backend.infra.execution.port`, `product.backend.infra.execution.registry`, `product.backend.infra.execution.web.runtime`, `product.backend.infra.runtime.runner.case_orchestrator`, `product.backend.infra.runtime.runner.executor`, `product.backend.infra.runtime.runner.progress`, `product.backend.infra.runtime.runner.result_builder`, `product.backend.infra.runtime.runner.staging`, `product.protocols`, `pydantic`, `time`

### `product/backend/infra/runtime/runner/executor.py`
- `class RunnerExecutor`
- `execute_runner_attempt(input_path, staging_dir, environ, finished_at_us) -> int`
主要 import / dot-source：`__future__`, `collections.abc`, `hashlib`, `pathlib`, `product.backend.core.lifecycle`, `product.backend.core.verification.differential`, `product.backend.core.verification.facts`, `product.backend.core.verification.permissions`, `product.backend.core.verification.permissions.evaluation`, `product.backend.infra.execution.port`, `product.backend.infra.observers.coordinator`, `product.backend.infra.observers.effect_projector`, `product.backend.infra.runtime.runner.case_orchestrator`, `product.protocols`

### `product/backend/infra/runtime/runner/progress.py`
- `PROGRESS_MAX_EVENTS`
- `PROGRESS_MAX_BYTES`
- `PROGRESS_MAX_LINE_BYTES`
- `_CASE_ID_PATTERN`
- `_BUSINESS_ID_PATTERN`
- `_SENSITIVE_NAME_PARTS`
- `class ProgressTwinRole`
- `class ProgressPhase`
- `class ProgressState`
- `class RunnerProgressEvent`
- `class RunnerProgressWriter`
- `class RunnerProgressReader`
主要 import / dot-source：`__future__`, `enum`, `json`, `pathlib`, `product.backend.infra.artifacts.run_packages`, `product.backend.infra.storage`, `pydantic`, `re`, `typing`

### `product/backend/infra/runtime/runner/result_builder.py`
- `evidence_from_case(document, case_result) -> Evidence`
- `run_verdict(evidence, has_gaps) -> RunVerdict`
主要 import / dot-source：`__future__`, `collections.abc`, `product.backend.core.lifecycle`, `product.protocols`

### `product/backend/infra/runtime/runner/staging.py`
- `atomic_write(path, data) -> None`
- `write_evidence(staging, evidence, known_secrets) -> StagedArtifact`
主要 import / dot-source：`__future__`, `hashlib`, `os`, `pathlib`, `product.backend.core.errors`, `product.protocols`, `uuid`

### `product/backend/infra/runtime/runner/supervisor.py`
- `class RunnerSupervisor`
主要 import / dot-source：`__future__`, `collections.abc`, `hashlib`, `json`, `logging`, `os`, `pathlib`, `product.backend.core.errors`, `product.backend.core.lifecycle`, `product.backend.infra.artifacts.run_packages`, `product.backend.infra.artifacts.run_publication`, `product.backend.infra.runtime.jobs.attempts`, `product.backend.infra.runtime.jobs.models`, `product.backend.infra.runtime.jobs.requests`, `product.backend.infra.runtime.paths`, `product.backend.infra.runtime.process.control`, `product.backend.infra.runtime.process.environment`, `product.backend.infra.runtime.process.tree`, `product.backend.infra.storage`, `product.protocols`, `subprocess`, `time`, `typing`, `uuid`

### `product/backend/infra/runtime/serve_lock.py`
- `class ServeLock`
主要 import / dot-source：`__future__`, `dataclasses`, `json`, `os`, `pathlib`, `product.backend.core.errors`, `product.backend.infra.runtime.paths`, `product.backend.infra.runtime.process.lock`, `secrets`, `typing`

### `product/backend/infra/runtime/service_lifetime.py`
- `serve_owner_is_alive(path, owner_token) -> bool`
主要 import / dot-source：`__future__`, `json`, `pathlib`, `product.backend.infra.runtime.process.lock`

### `product/backend/infra/runtime/settings.py`
- `_ENVIRONMENT_KEYS`
- `class Settings`
- `class LoadedSettings`
- `default_config_path() -> Path | None`
- `load_settings(config_path, cli_overrides, environ, default_path) -> LoadedSettings`
主要 import / dot-source：`__future__`, `dataclasses`, `os`, `pathlib`, `product.backend.core.errors`, `product.backend.infra.runtime.paths`, `pydantic`, `tomllib`, `typing`

### `product/backend/infra/runtime/worker/__init__.py`
- `_EXPORTS`
主要 import / dot-source：`importlib`

### `product/backend/infra/runtime/worker/lifetime.py`
- `worker_lifetime_path(var_dir, job_id) -> Path`
- `worker_tree_identity_path(var_dir, job_id) -> Path`
- `worker_tree_name(job_id, lease_owner) -> str`
- `write_worker_tree_identity(var_dir, job_id, lease_owner, controller) -> None`
- `class WorkerLifetimeLock`
主要 import / dot-source：`__future__`, `dataclasses`, `hashlib`, `json`, `os`, `pathlib`, `product.backend.core.identifiers`, `product.backend.infra.runtime.paths`, `product.backend.infra.runtime.process.lock`, `product.backend.infra.runtime.process.tree`, `typing`

### `product/backend/infra/runtime/worker/process.py`
- `main() -> int`
主要 import / dot-source：`__future__`, `argparse`, `logging`, `os`, `pathlib`, `sys`, `threading`, `time`, `typing`

### `product/backend/infra/runtime/worker/supervisor.py`
- `class LocalWorkerSupervisor`
主要 import / dot-source：`__future__`, `logging`, `pathlib`, `product.backend.core.errors`, `product.backend.core.lifecycle`, `product.backend.infra.recording.request_store`, `product.backend.infra.runtime.jobs.attempts`, `product.backend.infra.runtime.jobs.dispatch`, `product.backend.infra.runtime.jobs.models`, `product.backend.infra.runtime.jobs.queue`, `product.backend.infra.runtime.jobs.recovery`, `product.backend.infra.runtime.jobs.requests`, `product.backend.infra.runtime.paths`, `product.backend.infra.runtime.process.tree`, `product.backend.infra.runtime.worker.lifetime`, `product.backend.infra.storage`, `product.protocols`, `threading`, `time`, `uuid`

<!-- GENERATED:END -->
