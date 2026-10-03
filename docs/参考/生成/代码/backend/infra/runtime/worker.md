# 自动代码参考：backend/infra/runtime/worker

> 自动生成。当前源码结构与注册投影，不代表运行验收或完整调用图。

<!-- GENERATED:START -->

### `product/backend/infra/runtime/worker/__init__.py`

[打开源码](../../../../../../../product/backend/infra/runtime/worker/__init__.py) · Python AST；作用域内import不表示每次调用均执行。

- `_EXPORTS`

静态import / dot-source：`importlib`、`动态引用：未静态确定`

### `product/backend/infra/runtime/worker/lifetime.py`

[打开源码](../../../../../../../product/backend/infra/runtime/worker/lifetime.py) · Python AST；作用域内import不表示每次调用均执行。

- `worker_lifetime_path(var_dir, job_id) -> Path`
- `worker_tree_identity_path(var_dir, job_id) -> Path`
- `worker_tree_name(job_id, lease_owner) -> str`
- `write_worker_tree_identity(var_dir, job_id, lease_owner, controller) -> None`
- `class WorkerLifetimeLock`
- `WorkerLifetimeLock.acquire(cls, var_dir, job_id, lease_owner) -> WorkerLifetimeLock`
- `WorkerLifetimeLock.execution_has_exited(var_dir, job_id, lease_owner) -> bool`
- `WorkerLifetimeLock.release(self) -> None`

静态import / dot-source：`__future__`、`dataclasses`、`hashlib`、`json`、`os`、`pathlib`、`product.backend.core.identifiers`、`product.backend.infra.runtime.paths`、`product.backend.infra.runtime.process.lock`、`product.backend.infra.runtime.process.tree`、`typing`、`作用域内：re`

### `product/backend/infra/runtime/worker/process.py`

[打开源码](../../../../../../../product/backend/infra/runtime/worker/process.py) · Python AST；作用域内import不表示每次调用均执行。

- `main() -> int`

静态import / dot-source：`__future__`、`argparse`、`logging`、`os`、`pathlib`、`sys`、`threading`、`time`、`typing`、`作用域内：product.backend.composition.worker`、`作用域内：product.backend.core.errors`、`作用域内：product.backend.core.lifecycle`、`作用域内：product.backend.infra.runtime.jobs.models`、`作用域内：product.backend.infra.runtime.logging`、`作用域内：product.backend.infra.runtime.process.controlled.identity`、`作用域内：product.backend.infra.runtime.service_lifetime`、`作用域内：product.backend.infra.runtime.worker.lifetime`

### `product/backend/infra/runtime/worker/runtime_process.py`

[打开源码](../../../../../../../product/backend/infra/runtime/worker/runtime_process.py) · Python AST；作用域内import不表示每次调用均执行。

- `run(var_dir, job_id, lease_owner, control_session_id, node_executable) -> int`
- `main()`

静态import / dot-source：`__future__`、`argparse`、`os`、`pathlib`、`product.backend.core.errors`、`product.backend.core.lifecycle`、`product.backend.infra.runtime.jobs.models`、`product.backend.infra.runtime.process.controlled.node_owned`、`product.backend.infra.runtime.worker.lifetime`、`product.protocols.runtime.node_runtime`、`time`、`作用域内：product.backend.composition.worker`、`作用域内：product.backend.infra.runtime.process.controlled.identity`

### `product/backend/infra/runtime/worker/runtime_supervisor.py`

[打开源码](../../../../../../../product/backend/infra/runtime/worker/runtime_supervisor.py) · Python AST；作用域内import不表示每次调用均执行。

- `_LOGGER`
- `class LocalRuntimeSupervisor`
- `LocalRuntimeSupervisor.start(self)`
- `LocalRuntimeSupervisor.stop(self)`
- `LocalRuntimeSupervisor.stop_project(self, project_id, expected_instance_id)`
- `LocalRuntimeSupervisor.tick(self)`

静态import / dot-source：`__future__`、`dataclasses`、`logging`、`pathlib`、`product.backend.core.errors`、`product.backend.core.lifecycle`、`product.backend.infra.runtime.jobs.attempts`、`product.backend.infra.runtime.jobs.models`、`product.backend.infra.runtime.jobs.recovery`、`product.backend.infra.runtime.jobs.target_handlers.runtime_load`、`product.backend.infra.runtime.process.environment`、`product.backend.infra.runtime.process.tree`、`product.backend.infra.runtime.worker.lifetime`、`subprocess`、`threading`、`time`、`uuid`

### `product/backend/infra/runtime/worker/supervisor.py`

[打开源码](../../../../../../../product/backend/infra/runtime/worker/supervisor.py) · Python AST；作用域内import不表示每次调用均执行。

- `class LocalWorkerSupervisor`
- `LocalWorkerSupervisor.start(self) -> None`
- `LocalWorkerSupervisor.is_running(self) -> bool`
- `LocalWorkerSupervisor.capabilities(self) -> tuple[str, ...]`
- `LocalWorkerSupervisor.recovered_jobs(self) -> int`
- `LocalWorkerSupervisor.stop(self, timeout) -> None`

静态import / dot-source：`__future__`、`logging`、`pathlib`、`product.backend.core.errors`、`product.backend.core.lifecycle`、`product.backend.infra.execution.web.check_runtime`、`product.backend.infra.recording.request_store`、`product.backend.infra.runtime.jobs.attempts`、`product.backend.infra.runtime.jobs.dispatch`、`product.backend.infra.runtime.jobs.models`、`product.backend.infra.runtime.jobs.queue`、`product.backend.infra.runtime.jobs.recovery`、`product.backend.infra.runtime.jobs.requests.checks`、`product.backend.infra.runtime.jobs.targets`、`product.backend.infra.runtime.paths`、`product.backend.infra.runtime.process.tree`、`product.backend.infra.runtime.worker.lifetime`、`product.backend.infra.storage`、`product.protocols`、`threading`、`time`、`uuid`、`作用域内：product.backend.infra.artifacts.checks.check_packages`、`作用域内：product.backend.infra.artifacts.checks.check_publication`、`作用域内：product.backend.infra.runtime.jobs.models`

<!-- GENERATED:END -->
