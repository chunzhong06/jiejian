# 自动代码参考：backend/infra/storage/runtime

> 自动生成。当前源码结构与注册投影，不代表运行验收或完整调用图。

<!-- GENERATED:START -->

### `product/backend/infra/storage/runtime/__init__.py`

[打开源码](../../../../../../../product/backend/infra/storage/runtime/__init__.py) · Python AST；作用域内import不表示每次调用均执行。


### `product/backend/infra/storage/runtime/environment_operations.py`

[打开源码](../../../../../../../product/backend/infra/storage/runtime/environment_operations.py) · Python AST；作用域内import不表示每次调用均执行。

- `class EnvironmentOperationRow`
- `class EnvironmentOperationRepository`
- `EnvironmentOperationRepository.get(self, operation_id)`
- `EnvironmentOperationRepository.save(self, value)`
- `EnvironmentOperationRepository.list(self, limit)`

静态import / dot-source：`product.backend.infra.storage.base`、`sqlalchemy`、`sqlalchemy.orm`

### `product/backend/infra/storage/runtime/runtime_loads.py`

[打开源码](../../../../../../../product/backend/infra/storage/runtime/runtime_loads.py) · Python AST；作用域内import不表示每次调用均执行。

- `class RuntimeLoadRow`
- `class RuntimeLoadRepository`
- `RuntimeLoadRepository.get(self, load_id) -> NodeRuntimeLoadRequest &#124; None`
- `RuntimeLoadRepository.operation(self, project_id, operation_id) -> NodeRuntimeLoadRequest &#124; None`
- `RuntimeLoadRepository.latest(self, project_id) -> NodeRuntimeLoadRequest &#124; None`
- `RuntimeLoadRepository.add(self, request) -> None`
- `RuntimeLoadRepository.successful_for_source(self, project_id, source_fingerprint)`
- `RuntimeLoadRepository.receipt(self, load_id) -> NodeRuntimeLoadReceipt &#124; None`
- `RuntimeLoadRepository.publish(self, receipt) -> None`

静态import / dot-source：`product.backend.core.errors`、`product.backend.infra.storage.base`、`product.protocols.runtime.node_runtime`、`sqlalchemy`、`sqlalchemy.orm`

### `product/backend/infra/storage/runtime/sample_workspaces.py`

[打开源码](../../../../../../../product/backend/infra/storage/runtime/sample_workspaces.py) · Python AST；作用域内import不表示每次调用均执行。

- `class SampleWorkspaceRow`
- `class SampleInstanceRow`
- `class SampleReconciliationRow`
- `class SampleWorkspaceRepository`
- `SampleWorkspaceRepository.latest(self)`
- `SampleWorkspaceRepository.for_project(self, project_id)`
- `SampleWorkspaceRepository.save(self, value)`
- `SampleWorkspaceRepository.add_instance(self, instance_id, workspace_id, identity, created_at_us)`
- `SampleWorkspaceRepository.instance(self, workspace_id)`
- `SampleWorkspaceRepository.observe(self, value)`
- `SampleWorkspaceRepository.observation(self, instance_id)`

静态import / dot-source：`json`、`product.backend.infra.storage.base`、`sqlalchemy`、`sqlalchemy.orm`

<!-- GENERATED:END -->
