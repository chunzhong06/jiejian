# 自动代码参考：backend/workflows/runtime

> 自动生成。当前源码结构与注册投影，不代表运行验收或完整调用图。

<!-- GENERATED:START -->

### `product/backend/workflows/runtime/__init__.py`

[打开源码](../../../../../../product/backend/workflows/runtime/__init__.py) · Python AST；作用域内import不表示每次调用均执行。


### `product/backend/workflows/runtime/activation.py`

[打开源码](../../../../../../product/backend/workflows/runtime/activation.py) · Python AST；作用域内import不表示每次调用均执行。

- `class RuntimeActivationService`
- `RuntimeActivationService.receipt(self, project_id, operation_id)`
- `RuntimeActivationService.activate(self, project_id, delivery_id, operation_id, expected_version)`

静态import / dot-source：`product.backend.core.development`、`product.backend.core.errors`、`product.backend.workflows.development.operations`、`threading`、`作用域内：product.backend.workflows.runtime.node_activation`

### `product/backend/workflows/runtime/load_jobs.py`

[打开源码](../../../../../../product/backend/workflows/runtime/load_jobs.py) · Python AST；作用域内import不表示每次调用均执行。

- `class RuntimeLoadJobs`
- `RuntimeLoadJobs.submit(self, request, validate_current, work)`
- `RuntimeLoadJobs.operation(self, project_id, operation_id)`
- `RuntimeLoadJobs.publish(self, job_id, attempt, lease_owner, fencing_token, receipt)`
- `RuntimeLoadJobs.read_in_work(work, request)`

静态import / dot-source：`contextlib`、`product.backend.core.errors`、`product.backend.core.lifecycle`、`product.backend.infra.runtime.jobs.events`、`product.backend.infra.runtime.jobs.models`、`product.backend.infra.storage`、`product.protocols.runtime.node_runtime`、`uuid`

### `product/backend/workflows/runtime/node_activation.py`

[打开源码](../../../../../../product/backend/workflows/runtime/node_activation.py) · Python AST；作用域内import不表示每次调用均执行。

- `class NodeRuntimeActivation`
- `NodeRuntimeActivation.activate(self, project_id, delivery_id, operation_id, expected_version)`
- `NodeRuntimeActivation.receipt(self, project_id, operation_id)`

静态import / dot-source：`product.backend.core.development`、`product.backend.core.errors`、`product.backend.core.lifecycle`、`product.backend.infra.runtime.process.controlled.node_owned`、`product.backend.workflows.development.operations`

### `product/backend/workflows/runtime/ports.py`

[打开源码](../../../../../../product/backend/workflows/runtime/ports.py) · Python AST；作用域内import不表示每次调用均执行。

- `class RuntimeProvider`
- `class ProjectRuntimePorts`
- `ProjectRuntimePorts.reference(self, project_id) -> RuntimeReference &#124; None`
- `ProjectRuntimePorts.load_delivery(self, project_id, source_fingerprint) -> RuntimeReference`

静态import / dot-source：`__future__`、`collections.abc`、`dataclasses`、`product.backend.core.errors`、`product.protocols.runtime.node_runtime`、`product.protocols.runtime.runtime_identity`

### `product/backend/workflows/runtime/setup.py`

[打开源码](../../../../../../product/backend/workflows/runtime/setup.py) · Python AST；作用域内import不表示每次调用均执行。

- `class NodeStartPreview`
- `class NodeRuntimeSetup`
- `NodeRuntimeSetup.preview(self, project_id, entry, port, revision, consent_source_read)`
- `NodeRuntimeSetup.start(self, project_id, entry, port, revision, preview_fingerprint, operation_id, consent_execute, work)`
- `NodeRuntimeSetup.state(self, project_id)`
- `NodeRuntimeSetup.operation(self, project_id, operation_id)`
- `NodeRuntimeSetup.cancel(self, project_id, operation_id)`
- `NodeRuntimeSetup.owns_project(self, project_id)`
- `NodeRuntimeSetup.reference(self, project_id)`
- `NodeRuntimeSetup.require_loaded_delivery(self, project_id, source_fingerprint)`
- `NodeRuntimeSetup.stop(self, project_id, instance_id)`

静态import / dot-source：`__future__`、`hashlib`、`json`、`pathlib`、`product.backend.core.errors`、`product.backend.core.lifecycle`、`product.backend.infra.runtime.jobs.models`、`product.backend.infra.runtime.jobs.queue`、`product.backend.infra.runtime.jobs.target_handlers.runtime_load`、`product.backend.infra.runtime.process.controlled.artifact`、`product.backend.infra.runtime.process.controlled.node_owned`、`product.backend.workflows.runtime.load_jobs`、`product.protocols.runtime.node_runtime`、`product.protocols.runtime.runtime_identity`、`pydantic`、`time`、`urllib.parse`、`uuid`

<!-- GENERATED:END -->
