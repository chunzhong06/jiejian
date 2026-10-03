# 自动代码参考：backend/infra/runtime/jobs

> 自动生成。当前源码结构与注册投影，不代表运行验收或完整调用图。

<!-- GENERATED:START -->

### `product/backend/infra/runtime/jobs/__init__.py`

[打开源码](../../../../../../../product/backend/infra/runtime/jobs/__init__.py) · Python AST；作用域内import不表示每次调用均执行。


### `product/backend/infra/runtime/jobs/attempts.py`

[打开源码](../../../../../../../product/backend/infra/runtime/jobs/attempts.py) · Python AST；作用域内import不表示每次调用均执行。

- `_TERMINAL_JOB_STATES`
- `class JobAttempts`
- `JobAttempts.claim(self, request, known_secrets) -> ClaimedJob &#124; None`
- `JobAttempts.claim_in_work(self, work, request, known_secrets) -> ClaimedJob &#124; None`
- `JobAttempts.renew_lease(self, request, known_secrets) -> JobMutationResult`
- `JobAttempts.complete_cancellation(self, request, known_secrets) -> CancellationResult`
- `JobAttempts.record_retryable_failure(self, request, known_secrets) -> JobMutationResult`
- `JobAttempts.record_fatal_failure(self, request, known_secrets) -> JobMutationResult`
- `JobAttempts.record_waiting_fatal_failure(self, request, known_secrets) -> JobMutationResult &#124; None`

静态import / dot-source：`__future__`、`collections.abc`、`product.backend.core.errors`、`product.backend.core.lifecycle`、`product.backend.infra.runtime.jobs.events`、`product.backend.infra.runtime.jobs.models`、`product.backend.infra.runtime.jobs.targets`、`product.backend.infra.storage`、`secrets`

### `product/backend/infra/runtime/jobs/dispatch.py`

[打开源码](../../../../../../../product/backend/infra/runtime/jobs/dispatch.py) · Python AST；作用域内import不表示每次调用均执行。

- `WORKER_LOG_MAX_BYTES`
- `WORKER_LOG_BACKUPS`
- `class WorkerDispatcher`
- `WorkerDispatcher.start(self, job_id, lease_owner, secret_names) -> subprocess.Popen[Any]`
- `WorkerDispatcher.wait(self, job_id, process, known_secrets, timeout_seconds) -> StagedAttempt`
- `WorkerDispatcher.wait_recording(self, job_id, process, timeout_seconds) -> JobRecord`
- `WorkerDispatcher.close_process(process, timeout) -> None`

静态import / dot-source：`__future__`、`collections.abc`、`dataclasses`、`hashlib`、`json`、`os`、`pathlib`、`product.backend.core.errors`、`product.backend.core.identifiers`、`product.backend.core.lifecycle`、`product.backend.infra.artifacts.run_packages`、`product.backend.infra.runtime.paths`、`product.backend.infra.runtime.process.environment`、`product.backend.infra.runtime.process.tree`、`product.backend.infra.runtime.worker.lifetime`、`product.backend.infra.storage`、`product.protocols`、`pydantic`、`re`、`subprocess`、`sys`、`time`、`typing`

### `product/backend/infra/runtime/jobs/events.py`

[打开源码](../../../../../../../product/backend/infra/runtime/jobs/events.py) · Python AST；作用域内import不表示每次调用均执行。

- `append_job_event(work, job, event_type, source_state, target_state, occurred_at_us, metadata) -> None`

静态import / dot-source：`__future__`、`product.backend.core.lifecycle`、`product.backend.infra.runtime.jobs.models`、`product.backend.infra.storage`

### `product/backend/infra/runtime/jobs/factory.py`

[打开源码](../../../../../../../product/backend/infra/runtime/jobs/factory.py) · Python AST；作用域内import不表示每次调用均执行。

- `class WorkerHandlerFactory`
- `WorkerHandlerFactory.build_registry(self, lease_owner, environ) -> JobHandlerRegistry`

静态import / dot-source：`__future__`、`collections.abc`、`pathlib`、`product.backend.infra.artifacts.run_packages`、`product.backend.infra.recording.request_store`、`product.backend.infra.runtime.jobs.attempts`、`product.backend.infra.runtime.jobs.handlers`、`product.backend.infra.runtime.jobs.target_handlers.recording`、`product.backend.infra.runtime.jobs.targets`、`product.backend.infra.storage`、`作用域内：product.backend.infra.runtime.check_runner.supervisor`、`作用域内：product.backend.infra.runtime.proof_runner.supervisor`

### `product/backend/infra/runtime/jobs/handlers.py`

[打开源码](../../../../../../../product/backend/infra/runtime/jobs/handlers.py) · Python AST；作用域内import不表示每次调用均执行。

- `class JobHandler`
- `JobHandler.run_job(self, job_id) -> ResultT_co &#124; None`
- `class JobAttemptPort`
- `JobAttemptPort.claim_in_work(self, work, request, known_secrets) -> ClaimedJob &#124; None`
- `JobAttemptPort.claim(self, request, known_secrets) -> ClaimedJob &#124; None`
- `JobAttemptPort.renew_lease(self, request, known_secrets) -> JobMutationResult`
- `JobAttemptPort.complete_cancellation(self, request, known_secrets) -> CancellationResult`
- `JobAttemptPort.record_retryable_failure(self, request, known_secrets) -> JobMutationResult`
- `JobAttemptPort.record_fatal_failure(self, request, known_secrets) -> JobMutationResult`
- `JobAttemptPort.record_waiting_fatal_failure(self, request, known_secrets) -> JobMutationResult &#124; None`
- `class JobHandlerRegistry`
- `JobHandlerRegistry.register(self, target_type, factory, operation_types) -> None`
- `JobHandlerRegistry.register_auxiliary(self, name, factory) -> None`
- `JobHandlerRegistry.resolve_auxiliary(self, name) -> JobHandler[Any]`
- `JobHandlerRegistry.resolve(self, job) -> JobHandler[Any]`

静态import / dot-source：`__future__`、`collections.abc`、`product.backend.core.errors`、`product.backend.infra.runtime.jobs.models`、`product.backend.infra.runtime.jobs.targets`、`product.backend.infra.storage`、`typing`

### `product/backend/infra/runtime/jobs/models.py`

[打开源码](../../../../../../../product/backend/infra/runtime/jobs/models.py) · Python AST；作用域内import不表示每次调用均执行。

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
- `RetryPolicy.validate_bounds(self) -> RetryPolicy`
- `class SubmitJob`
- `class ClaimJob`
- `class RenewLease`
- `RenewLease.validate_new_deadline(self) -> RenewLease`
- `class RequestCancellation`
- `class WaitingFatalFailure`
- `class FencedJobMutation`
- `class CompleteCancellation`
- `class RetryableFailure`
- `class FatalFailure`
- `class RecoveryScan`
- `class ConfirmRecovery`
- `ConfirmRecovery.validate_proof_reason(self) -> ConfirmRecovery`
- `class JobSubmissionResult`
- `class ClaimedJob`
- `ClaimedJob.validate_target(self) -> ClaimedJob`
- `class JobMutationResult`
- `JobMutationResult.validate_target(self) -> JobMutationResult`
- `class CancellationResult`
- `class RecoveryCandidate`
- `RecoveryCandidate.validate_target(self) -> RecoveryCandidate`
- `validate_control_request(request, known_secrets) -> None`
- `checked_time_add(left, right) -> int`
- `compute_retry_available_at(policy, jitter_source, now_us, attempt) -> int`

静态import / dot-source：`__future__`、`collections.abc`、`enum`、`product.backend.core.errors`、`product.backend.core.identifiers`、`product.backend.infra.storage`、`product.protocols.runner`、`pydantic`、`typing`

### `product/backend/infra/runtime/jobs/queue.py`

[打开源码](../../../../../../../product/backend/infra/runtime/jobs/queue.py) · Python AST；作用域内import不表示每次调用均执行。

- `_TERMINAL_JOB_STATES`
- `class JobQueue`
- `JobQueue.submit(self, request, known_secrets, precondition, on_created) -> JobSubmissionResult`
- `JobQueue.request_cancellation(self, request, known_secrets, work) -> CancellationResult`

静态import / dot-source：`__future__`、`collections.abc`、`product.backend.core.errors`、`product.backend.core.lifecycle`、`product.backend.infra.runtime.jobs.events`、`product.backend.infra.runtime.jobs.models`、`product.backend.infra.runtime.jobs.targets`、`product.backend.infra.storage`、`uuid`、`作用域内：contextlib`

### `product/backend/infra/runtime/jobs/reconciliation.py`

[打开源码](../../../../../../../product/backend/infra/runtime/jobs/reconciliation.py) · Python AST；作用域内import不表示每次调用均执行。

- `class ReconciliationResult`
- `class RunReconciler`
- `RunReconciler.reconcile(self, known_secrets) -> ReconciliationResult`

静态import / dot-source：`__future__`、`collections.abc`、`os`、`pathlib`、`product.backend.core.errors`、`product.backend.core.lifecycle`、`product.backend.infra.artifacts.run_packages`、`product.backend.infra.artifacts.run_publication`、`product.backend.infra.runtime.paths`、`product.backend.infra.storage`、`pydantic`、`time`、`typing`、`uuid`

### `product/backend/infra/runtime/jobs/recovery.py`

[打开源码](../../../../../../../product/backend/infra/runtime/jobs/recovery.py) · Python AST；作用域内import不表示每次调用均执行。

- `_TERMINAL_JOB_STATES`
- `class JobRecovery`
- `JobRecovery.list_recovery_candidates(self, request, known_secrets) -> tuple[RecoveryCandidate, ...]`
- `JobRecovery.confirm_recovery(self, request, known_secrets) -> JobMutationResult`

静态import / dot-source：`__future__`、`collections.abc`、`product.backend.core.errors`、`product.backend.core.lifecycle`、`product.backend.infra.runtime.jobs.events`、`product.backend.infra.runtime.jobs.models`、`product.backend.infra.runtime.jobs.targets`、`product.backend.infra.storage`、`secrets`

### `product/backend/infra/runtime/jobs/requests/__init__.py`

[打开源码](../../../../../../../product/backend/infra/runtime/jobs/requests/__init__.py) · Python AST；作用域内import不表示每次调用均执行。


### `product/backend/infra/runtime/jobs/requests/checks.py`

[打开源码](../../../../../../../product/backend/infra/runtime/jobs/requests/checks.py) · Python AST；作用域内import不表示每次调用均执行。

- `class CheckRequestStore`
- `CheckRequestStore.path_for(self, job_id, config_hash) -> Path`
- `CheckRequestStore.write(self, job_id, request) -> tuple[str, bool]`
- `CheckRequestStore.load(self, job_id, expected_hash) -> PersistedExecutionRequestV3`
- `CheckRequestStore.write_bundle(self, job_id, bundle) -> tuple[str, bool]`
- `CheckRequestStore.load_bundle(self, job_id, expected_hash) -> CheckRuntimeBundle`
- `CheckRequestStore.remove_if_matches(self, job_id, request_hash, config_hash) -> None`

静态import / dot-source：`__future__`、`hashlib`、`hmac`、`logging`、`os`、`pathlib`、`product.backend.core.errors`、`product.backend.infra.runtime.paths`、`product.protocols.checks.check_runtime`、`product.protocols.checks.execution_request`、`re`、`uuid`

### `product/backend/infra/runtime/jobs/requests/execution.py`

[打开源码](../../../../../../../product/backend/infra/runtime/jobs/requests/execution.py) · Python AST；作用域内import不表示每次调用均执行。

- `class ExecutionRequestStore`
- `ExecutionRequestStore.write(self, job_id, request, known_secrets) -> tuple[str, bool]`
- `ExecutionRequestStore.load(self, job_id, expected_hash, known_secrets) -> PersistedExecutionRequest`
- `ExecutionRequestStore.load_historical(self, job_id, expected_hash, known_secrets) -> ExecutionRequestDocument`
- `ExecutionRequestStore.remove_if_matches(self, job_id, request_hash) -> None`
- `ExecutionRequestStore.path_for(self, job_id) -> Path`

静态import / dot-source：`__future__`、`collections.abc`、`hashlib`、`hmac`、`os`、`pathlib`、`product.backend.core.errors`、`product.backend.core.identifiers`、`product.backend.infra.runtime.paths`、`product.protocols`、`product.protocols.runner.execution_request`、`re`、`uuid`

### `product/backend/infra/runtime/jobs/target_handlers/__init__.py`

[打开源码](../../../../../../../product/backend/infra/runtime/jobs/target_handlers/__init__.py) · Python AST；作用域内import不表示每次调用均执行。


### `product/backend/infra/runtime/jobs/target_handlers/proof_preflight.py`

[打开源码](../../../../../../../product/backend/infra/runtime/jobs/target_handlers/proof_preflight.py) · Python AST；作用域内import不表示每次调用均执行。

- `class ProofPreflightTargetHandler`
- `ProofPreflightTargetHandler.load(self, work, job)`
- `ProofPreflightTargetHandler.advance_after_claim(self, work, job, now_us)`
- `ProofPreflightTargetHandler.finish(self, work, job, now_us, outcome)`
- `proof_preflight_targets()`

静态import / dot-source：`product.backend.core.errors`、`product.backend.infra.runtime.jobs.targets`、`product.protocols.preparation.proof_sources`

### `product/backend/infra/runtime/jobs/target_handlers/recording.py`

[打开源码](../../../../../../../product/backend/infra/runtime/jobs/target_handlers/recording.py) · Python AST；作用域内import不表示每次调用均执行。

- `_CANCEL_PATH_ENV`
- `_ATTEMPT_DIR_ENV`
- `class RecordingSubmissionPort`
- `RecordingSubmissionPort.consume_result(self, job_id, lease_owner, fencing_token, result, now_us, known_secrets) -> Any`
- `class RecordingJobHandler`
- `RecordingJobHandler.run_job(self, job_id) -> Any &#124; None`
- `class RecordingJobTargetHandler`
- `RecordingJobTargetHandler.load(self, work, job) -> tuple[RunRecord &#124; None, RecordingRecord &#124; None]`
- `RecordingJobTargetHandler.advance_after_claim(self, work, job, now_us) -> tuple[RunRecord &#124; None, RecordingRecord &#124; None]`
- `RecordingJobTargetHandler.finish(self, work, job, now_us, outcome) -> tuple[RunRecord &#124; None, RecordingRecord &#124; None]`

静态import / dot-source：`__future__`、`collections.abc`、`logging`、`os`、`pathlib`、`product.backend.core.errors`、`product.backend.core.lifecycle`、`product.backend.core.recording.models`、`product.backend.infra.recording.control`、`product.backend.infra.recording.request_store`、`product.backend.infra.runtime.jobs.handlers`、`product.backend.infra.runtime.jobs.models`、`product.backend.infra.runtime.jobs.targets`、`product.backend.infra.runtime.paths`、`product.backend.infra.runtime.process.control`、`product.backend.infra.runtime.process.environment`、`product.backend.infra.runtime.process.tree`、`product.backend.infra.storage`、`product.protocols`、`subprocess`、`tempfile`、`time`、`typing`

### `product/backend/infra/runtime/jobs/target_handlers/runtime_load.py`

[打开源码](../../../../../../../product/backend/infra/runtime/jobs/target_handlers/runtime_load.py) · Python AST；作用域内import不表示每次调用均执行。

- `class RuntimeLoadTargetHandler`
- `RuntimeLoadTargetHandler.load(self, work, job)`
- `RuntimeLoadTargetHandler.advance_after_claim(self, work, job, now_us)`
- `RuntimeLoadTargetHandler.finish(self, work, job, now_us, outcome)`
- `runtime_load_targets()`

静态import / dot-source：`product.backend.core.errors`、`product.backend.infra.runtime.jobs.targets`、`product.protocols.runtime.node_runtime`

### `product/backend/infra/runtime/jobs/target_handlers/verification.py`

[打开源码](../../../../../../../product/backend/infra/runtime/jobs/target_handlers/verification.py) · Python AST；作用域内import不表示每次调用均执行。

- `_LOGGER`
- `class ResultFinalizerPort`
- `ResultFinalizerPort.finalize(self, run_id) -> Any`
- `class VerificationRunJobHandler`
- `VerificationRunJobHandler.run_job(self, job_id) -> StagedAttempt &#124; None`

静态import / dot-source：`__future__`、`collections.abc`、`logging`、`pathlib`、`product.backend.core.errors`、`product.backend.infra.artifacts.run_packages`、`product.backend.infra.artifacts.run_publication`、`product.backend.infra.runtime.jobs.attempts`、`product.backend.infra.runtime.jobs.handlers`、`product.backend.infra.runtime.jobs.reconciliation`、`product.backend.infra.runtime.jobs.requests.execution`、`product.backend.infra.runtime.runner.supervisor`、`product.backend.infra.storage`、`typing`

### `product/backend/infra/runtime/jobs/targets.py`

[打开源码](../../../../../../../product/backend/infra/runtime/jobs/targets.py) · Python AST；作用域内import不表示每次调用均执行。

- `class JobTargetType`
- `JobTargetType.from_job(cls, job) -> JobTargetType`
- `class JobTargetOutcome`
- `class JobTargetHandler`
- `JobTargetHandler.load(self, work, job) -> tuple[RunRecord &#124; None, RecordingRecord &#124; None]`
- `JobTargetHandler.advance_after_claim(self, work, job, now_us) -> tuple[RunRecord &#124; None, RecordingRecord &#124; None]`
- `JobTargetHandler.finish(self, work, job, now_us, outcome) -> tuple[RunRecord &#124; None, RecordingRecord &#124; None]`
- `class JobTargetRegistry`
- `JobTargetRegistry.target_types(self) -> tuple[JobTargetType, ...]`
- `JobTargetRegistry.register(self, target_type, handler) -> None`
- `JobTargetRegistry.resolve(self, job) -> JobTargetHandler`
- `JobTargetRegistry.load(self, work, job) -> tuple[RunRecord &#124; None, RecordingRecord &#124; None]`
- `JobTargetRegistry.advance_after_claim(self, work, job, now_us) -> tuple[RunRecord &#124; None, RecordingRecord &#124; None]`
- `JobTargetRegistry.finish(self, work, job, now_us, outcome) -> tuple[RunRecord &#124; None, RecordingRecord &#124; None]`
- `class RunJobTargetHandler`
- `RunJobTargetHandler.load(self, work, job) -> tuple[RunRecord &#124; None, RecordingRecord &#124; None]`
- `RunJobTargetHandler.advance_after_claim(self, work, job, now_us) -> tuple[RunRecord &#124; None, RecordingRecord &#124; None]`
- `RunJobTargetHandler.finish(self, work, job, now_us, outcome) -> tuple[RunRecord &#124; None, RecordingRecord &#124; None]`
- `default_run_job_targets() -> JobTargetRegistry`
- `recording_job_targets() -> JobTargetRegistry`
- `class CheckJobTargetHandler`
- `CheckJobTargetHandler.load(self, work, job)`
- `CheckJobTargetHandler.advance_after_claim(self, work, job, now_us)`
- `CheckJobTargetHandler.finish(self, work, job, now_us, outcome)`
- `current_check_and_recording_targets() -> JobTargetRegistry`

静态import / dot-source：`__future__`、`enum`、`product.backend.core.errors`、`product.backend.core.lifecycle`、`product.backend.infra.storage`、`typing`、`作用域内：product.backend.infra.runtime.jobs.target_handlers.proof_preflight`、`作用域内：product.backend.infra.runtime.jobs.target_handlers.recording`

<!-- GENERATED:END -->
