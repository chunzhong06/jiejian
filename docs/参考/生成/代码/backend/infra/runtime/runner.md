# 自动代码参考：backend/infra/runtime/runner

> 自动生成。当前源码结构与注册投影，不代表运行验收或完整调用图。

<!-- GENERATED:START -->

### `product/backend/infra/runtime/runner/__init__.py`

[打开源码](../../../../../../../product/backend/infra/runtime/runner/__init__.py) · Python AST；作用域内import不表示每次调用均执行。


### `product/backend/infra/runtime/runner/__main__.py`

[打开源码](../../../../../../../product/backend/infra/runtime/runner/__main__.py) · Python AST；作用域内import不表示每次调用均执行。

- `main() -> int`

静态import / dot-source：`__future__`、`argparse`、`pathlib`、`product.backend.infra.runtime.runner.executor`

### `product/backend/infra/runtime/runner/case_orchestrator.py`

[打开源码](../../../../../../../product/backend/infra/runtime/runner/case_orchestrator.py) · Python AST；作用域内import不表示每次调用均执行。

- `class CaseResult`
- `class CaseExecutionFailure`
- `class CaseOrchestrator`
- `CaseOrchestrator.run(self, session, case, action, verify, finding_pre_identity, twin, twin_role, allow_control_valid, baseline_validate, baseline_invalid, requirements_to_run) -> Any`

静态import / dot-source：`__future__`、`dataclasses`、`product.backend.core.errors`、`product.backend.core.lifecycle`、`product.backend.core.verification.differential`、`product.backend.core.verification.facts`、`product.backend.core.verification.permissions.coverage`、`product.backend.infra.execution.port`、`product.backend.infra.observers.coordinator`、`product.protocols`、`product.protocols.runner.execution`、`typing`

### `product/backend/infra/runtime/runner/composition.py`

[打开源码](../../../../../../../product/backend/infra/runtime/runner/composition.py) · Python AST；作用域内import不表示每次调用均执行。

- `RUNNER_EXIT_OK`
- `RUNNER_EXIT_PROTOCOL`
- `RUNNER_EXIT_INTERNAL`
- `RUNNER_EXIT_WRITE`
- `_SAFETY_STOP_CODES`
- `build_target_runtime_registry() -> TargetRuntimeRegistry`
- `execute_attempt(input_path, staging_dir, environ, finished_at_us) -> int`

静态import / dot-source：`__future__`、`collections.abc`、`dataclasses`、`hashlib`、`os`、`pathlib`、`product.backend.core.errors`、`product.backend.core.lifecycle`、`product.backend.core.verification.differential`、`product.backend.infra.execution.port`、`product.backend.infra.execution.registry`、`product.backend.infra.execution.web.runtime`、`product.backend.infra.runtime.runner.case_orchestrator`、`product.backend.infra.runtime.runner.executor`、`product.backend.infra.runtime.runner.progress`、`product.backend.infra.runtime.runner.result_builder`、`product.backend.infra.runtime.runner.staging`、`product.protocols`、`pydantic`、`time`

### `product/backend/infra/runtime/runner/executor.py`

[打开源码](../../../../../../../product/backend/infra/runtime/runner/executor.py) · Python AST；作用域内import不表示每次调用均执行。

- `class RunnerExecutor`
- `RunnerExecutor.close(self) -> None`
- `RunnerExecutor.run_case(self, case, twin, twin_role, allow_control_valid) -> CaseResult`
- `execute_runner_attempt(input_path, staging_dir, environ, finished_at_us) -> int`

静态import / dot-source：`__future__`、`collections.abc`、`hashlib`、`pathlib`、`product.backend.core.lifecycle`、`product.backend.core.verification.differential`、`product.backend.core.verification.facts`、`product.backend.core.verification.permissions`、`product.backend.core.verification.permissions.evaluation`、`product.backend.infra.execution.port`、`product.backend.infra.observers.coordinator`、`product.backend.infra.observers.effect_projector`、`product.backend.infra.runtime.runner.case_orchestrator`、`product.protocols`、`作用域内：product.backend.infra.runtime.runner.composition`

### `product/backend/infra/runtime/runner/progress.py`

[打开源码](../../../../../../../product/backend/infra/runtime/runner/progress.py) · Python AST；作用域内import不表示每次调用均执行。

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
- `RunnerProgressEvent.validate_business_ids(self) -> RunnerProgressEvent`
- `class RunnerProgressWriter`
- `RunnerProgressWriter.enabled(self) -> bool`
- `RunnerProgressWriter.record(self, case_id, action_id, twin_role, phase, state, recorded_at_us) -> bool`
- `RunnerProgressWriter.close(self) -> None`
- `class RunnerProgressReader`
- `RunnerProgressReader.read(self, job) -> tuple[RunnerProgressEvent, ...]`

静态import / dot-source：`__future__`、`enum`、`json`、`pathlib`、`product.backend.infra.artifacts.run_packages`、`product.backend.infra.storage`、`pydantic`、`re`、`typing`

### `product/backend/infra/runtime/runner/result_builder.py`

[打开源码](../../../../../../../product/backend/infra/runtime/runner/result_builder.py) · Python AST；作用域内import不表示每次调用均执行。

- `evidence_from_case(document, case_result) -> Evidence`
- `run_verdict(evidence, has_gaps) -> RunVerdict`

静态import / dot-source：`__future__`、`collections.abc`、`product.backend.core.lifecycle`、`product.protocols`

### `product/backend/infra/runtime/runner/staging.py`

[打开源码](../../../../../../../product/backend/infra/runtime/runner/staging.py) · Python AST；作用域内import不表示每次调用均执行。

- `atomic_write(path, data) -> None`
- `write_evidence(staging, evidence, known_secrets) -> StagedArtifact`

静态import / dot-source：`__future__`、`hashlib`、`os`、`pathlib`、`product.backend.core.errors`、`product.protocols`、`uuid`

### `product/backend/infra/runtime/runner/supervisor.py`

[打开源码](../../../../../../../product/backend/infra/runtime/runner/supervisor.py) · Python AST；作用域内import不表示每次调用均执行。

- `class RunnerSupervisor`
- `RunnerSupervisor.run_job(self, job_id) -> StagedAttempt &#124; None`

静态import / dot-source：`__future__`、`collections.abc`、`hashlib`、`json`、`logging`、`os`、`pathlib`、`product.backend.core.errors`、`product.backend.core.lifecycle`、`product.backend.infra.artifacts.run_packages`、`product.backend.infra.artifacts.run_publication`、`product.backend.infra.runtime.jobs.attempts`、`product.backend.infra.runtime.jobs.models`、`product.backend.infra.runtime.jobs.requests.execution`、`product.backend.infra.runtime.paths`、`product.backend.infra.runtime.process.control`、`product.backend.infra.runtime.process.environment`、`product.backend.infra.runtime.process.tree`、`product.backend.infra.storage`、`product.protocols`、`subprocess`、`time`、`typing`、`uuid`

<!-- GENERATED:END -->
