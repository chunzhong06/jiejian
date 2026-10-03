# 自动代码参考：backend/infra/storage/execution

> 自动生成。当前源码结构与注册投影，不代表运行验收或完整调用图。

<!-- GENERATED:START -->

### `product/backend/infra/storage/execution/__init__.py`

[打开源码](../../../../../../../product/backend/infra/storage/execution/__init__.py) · Python AST；作用域内import不表示每次调用均执行。


### `product/backend/infra/storage/execution/job_control.py`

[打开源码](../../../../../../../product/backend/infra/storage/execution/job_control.py) · Python AST；作用域内import不表示每次调用均执行。

- `_NONTERMINAL_RUNS`
- `class JobControlRepository`
- `JobControlRepository.claim(self, job_id, lease_owner, now_us, lease_expires_at_us, target_types) -> JobRecord &#124; None`
- `JobControlRepository.advance_run_after_claim(self, run_id, now_us) -> RunRecord &#124; None`
- `JobControlRepository.renew_lease(self, job_id, lease_owner, fencing_token, now_us, lease_expires_at_us) -> JobRecord &#124; None`
- `JobControlRepository.set_cancel_requested_at_if_absent(self, job_id, now_us) -> tuple[JobRecord &#124; None, bool]`
- `JobControlRepository.cancel_waiting(self, job_id, now_us) -> JobRecord &#124; None`
- `JobControlRepository.complete_running_cancellation(self, job_id, lease_owner, fencing_token, now_us) -> JobRecord &#124; None`
- `JobControlRepository.record_running_failure(self, job_id, lease_owner, fencing_token, now_us, target_state, available_at_us) -> JobRecord &#124; None`
- `JobControlRepository.record_waiting_failure(self, job_id, now_us) -> JobRecord &#124; None`
- `JobControlRepository.list_expired_running(self, now_us, limit, target_types) -> tuple[JobRecord, ...]`
- `JobControlRepository.confirm_recovery(self, job_id, lease_owner, fencing_token, now_us, target_state, available_at_us) -> JobRecord &#124; None`
- `JobControlRepository.transition_run_terminal(self, run_id, target, now_us) -> RunRecord &#124; None`
- `JobControlRepository.complete_published_result(self, job_id, run_id, attempt, lease_owner, fencing_token, lifecycle, verdict, completed_at_us, require_active_lease, request_hash, published_at_us) -> tuple[JobRecord, RunRecord] &#124; None`
- `JobControlRepository.complete_recording_result(self, job_id, recording_id, attempt, lease_owner, fencing_token, completed_at_us) -> JobRecord &#124; None`
- `JobControlRepository.complete_runtime_load(self, job_id, load_id, request_hash, attempt, lease_owner, fencing_token, now_us) -> JobRecord &#124; None`
- `JobControlRepository.complete_preflight(self, job_id, preflight_id, request_hash, attempt, lease_owner, fencing_token, now_us) -> JobRecord &#124; None`

静态import / dot-source：`__future__`、`collections.abc`、`product.backend.core.errors`、`product.backend.core.lifecycle`、`product.backend.infra.storage.execution.jobs`、`product.backend.infra.storage.execution.runs`、`product.backend.infra.storage.preparation.recordings`、`sqlalchemy`、`sqlalchemy.exc`、`sqlalchemy.orm`、`typing`

### `product/backend/infra/storage/execution/jobs.py`

[打开源码](../../../../../../../product/backend/infra/storage/execution/jobs.py) · Python AST；作用域内import不表示每次调用均执行。

- `class JobRow`
- `class JobEventRow`
- `class JobRecord`
- `JobRecord.validate_job_fields(self) -> JobRecord`
- `class JobEventRecord`
- `JobEventRecord.validate_metadata(cls, value) -> Mapping[str, MetadataValue]`
- `class JobRepository`
- `JobRepository.add(self, record) -> None`
- `JobRepository.get(self, job_id) -> JobRecord &#124; None`
- `JobRepository.get_by_idempotency(self, project_id, operation_type, idempotency_key) -> JobRecord &#124; None`
- `JobRepository.get_by_run(self, run_id) -> JobRecord &#124; None`
- `JobRepository.get_by_recording(self, recording_id) -> JobRecord &#124; None`
- `JobRepository.get_by_preflight(self, preflight_id) -> JobRecord &#124; None`
- `JobRepository.get_by_runtime_load(self, load_id) -> JobRecord &#124; None`
- `JobRepository.list_for_project(self, project_id) -> tuple[JobRecord, ...]`
- `JobRepository.next_pending(self, now_us, target_types) -> JobRecord &#124; None`
- `class JobEventRepository`
- `JobEventRepository.append(self, record) -> None`
- `JobEventRepository.list_for_job(self, job_id) -> tuple[JobEventRecord, ...]`

静态import / dot-source：`__future__`、`collections.abc`、`hashlib`、`json`、`product.backend.core.errors`、`product.backend.core.identifiers`、`product.backend.core.lifecycle`、`product.backend.core.recording.models`、`product.backend.core.verification.permissions`、`product.backend.infra.storage.base`、`product.protocols`、`pydantic`、`re`、`sqlalchemy`、`sqlalchemy.exc`、`sqlalchemy.orm`、`time`、`typing`

### `product/backend/infra/storage/execution/profiles.py`

[打开源码](../../../../../../../product/backend/infra/storage/execution/profiles.py) · Python AST；作用域内import不表示每次调用均执行。

- `class ExecutionProfileRow`
- `class ExecutionProfileRecord`
- `ExecutionProfileRecord.validate_time(self) -> ExecutionProfileRecord`
- `class ExecutionProfileRepository`
- `ExecutionProfileRepository.add(self, record) -> None`
- `ExecutionProfileRepository.get(self, profile_id) -> ExecutionProfileRecord &#124; None`
- `ExecutionProfileRepository.list_for_project(self, project_id) -> tuple[ExecutionProfileRecord, ...]`
- `ExecutionProfileRepository.replace(self, record) -> None`

静态import / dot-source：`__future__`、`collections.abc`、`product.backend.core.errors`、`product.backend.core.identifiers`、`product.backend.infra.storage.base`、`pydantic`、`sqlalchemy`、`sqlalchemy.orm`

### `product/backend/infra/storage/execution/runs.py`

[打开源码](../../../../../../../product/backend/infra/storage/execution/runs.py) · Python AST；作用域内import不表示每次调用均执行。

- `class RunRow`
- `class RunRecord`
- `RunRecord.validate_run_matrix(self) -> RunRecord`
- `class RunRepository`
- `RunRepository.add(self, record) -> None`
- `RunRepository.get(self, run_id) -> RunRecord &#124; None`
- `RunRepository.list_for_project(self, project_id) -> tuple[RunRecord, ...]`
- `RunRepository.page_for_project(self, project_id, limit, before_created_at_us, before_run_id, lifecycles) -> tuple[RunRecord, ...]`
- `RunRepository.has_after_for_project(self, project_id, created_at_us, run_id) -> bool`
- `RunRepository.list_finished_for_project(self, project_id) -> tuple[RunRecord, ...]`

静态import / dot-source：`__future__`、`collections.abc`、`hashlib`、`json`、`product.backend.core.errors`、`product.backend.core.identifiers`、`product.backend.core.lifecycle`、`product.backend.core.recording.models`、`product.backend.core.verification.permissions`、`product.backend.infra.storage.base`、`product.protocols`、`pydantic`、`re`、`sqlalchemy`、`sqlalchemy.exc`、`sqlalchemy.orm`、`time`、`typing`

<!-- GENERATED:END -->
