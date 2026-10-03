# 自动代码参考：backend/workflows/projects

> 自动生成。当前源码结构与注册投影，不代表运行验收或完整调用图。

<!-- GENERATED:START -->

### `product/backend/workflows/projects/__init__.py`

[打开源码](../../../../../../product/backend/workflows/projects/__init__.py) · Python AST；作用域内import不表示每次调用均执行。


静态import / dot-source：`.catalog`、`.lifecycle`

### `product/backend/workflows/projects/catalog.py`

[打开源码](../../../../../../product/backend/workflows/projects/catalog.py) · Python AST；作用域内import不表示每次调用均执行。

- `class ProjectCatalog`
- `ProjectCatalog.list(self, include_archived) -> tuple[ProjectRecord, ...]`
- `ProjectCatalog.get(self, project_id) -> ProjectRecord`
- `ProjectCatalog.list_for_display(self, include_archived) -> list[dict]`
- `ProjectCatalog.current_observations(self, project_id) -> tuple[str, ...]`

静态import / dot-source：`__future__`、`collections.abc`、`product.backend.core.errors`、`product.backend.core.lifecycle`、`product.backend.infra.storage`

### `product/backend/workflows/projects/lifecycle.py`

[打开源码](../../../../../../product/backend/workflows/projects/lifecycle.py) · Python AST；作用域内import不表示每次调用均执行。

- `_ACTIVE_JOB_STATES`
- `_ACTIVE_RUN_STATES`
- `_TERMINAL_RECORDING_STATES`
- `class ProjectLifecycleService`
- `ProjectLifecycleService.archive(self, project_id) -> ProjectRecord`

静态import / dot-source：`__future__`、`collections.abc`、`product.backend.core.errors`、`product.backend.core.lifecycle`、`product.backend.core.recording.models`、`product.backend.infra.storage`、`product.backend.workflows.test_identities`、`time`

### `product/backend/workflows/projects/repair.py`

[打开源码](../../../../../../product/backend/workflows/projects/repair.py) · Python AST；作用域内import不表示每次调用均执行。

- `class CurrentRepairTask`
- `class ProjectRepair`
- `class CurrentProjectRepairService`
- `CurrentProjectRepairService.evaluate(self, project_id)`

静态import / dot-source：`__future__`、`product.backend.core.checks.repair`、`product.backend.core.lifecycle`、`product.backend.workflows.checks.repairs.repair_presentation`、`product.protocols.checks.execution_request`、`pydantic`、`typing`、`作用域内：product.backend.workflows.changes.service`

<!-- GENERATED:END -->
