# 自动代码参考：backend/workflows/development

> 自动生成。当前源码结构与注册投影，不代表运行验收或完整调用图。

<!-- GENERATED:START -->

### `product/backend/workflows/development/__init__.py`

[打开源码](../../../../../../product/backend/workflows/development/__init__.py) · Python AST；作用域内import不表示每次调用均执行。


静态import / dot-source：`product.backend.workflows.development.service`

### `product/backend/workflows/development/operations.py`

[打开源码](../../../../../../product/backend/workflows/development/operations.py) · Python AST；作用域内import不表示每次调用均执行。

- `operation_fingerprint(project_id, kind, operation_id, payload)`
- `require_active_task_version(work, project_id, task_id, expected_version)`

静态import / dot-source：`hashlib`、`json`、`product.backend.core.errors`、`re`

### `product/backend/workflows/development/reading.py`

[打开源码](../../../../../../product/backend/workflows/development/reading.py) · Python AST；作用域内import不表示每次调用均执行。

- `class DevelopmentReader`
- `DevelopmentReader.bind_runtime_reader(self, reader)`
- `DevelopmentReader.validate_connections(self)`
- `DevelopmentReader.history(self, project_id, before_task_id, limit)`
- `DevelopmentReader.delivery_page(self, project_id, task_id, before_ordinal, limit)`
- `DevelopmentReader.delivery_details(self, project_id, change_id)`
- `DevelopmentReader.delivery_verification(self, project_id, delivery_id)`
- `DevelopmentReader.receipt(self, project_id, kind, operation_id)`
- `DevelopmentReader.task(self, project_id, task_id)`
- `DevelopmentReader.list(self, project_id, limit)`
- `DevelopmentReader.context(self, project_id, context_id)`
- `DevelopmentReader.active(self, project_id)`
- `DevelopmentReader.view(self, project_id, task_id)`

静态import / dot-source：`__future__`、`product.backend.core.changes.models`、`product.backend.core.errors`

### `product/backend/workflows/development/service.py`

[打开源码](../../../../../../product/backend/workflows/development/service.py) · Python AST；作用域内import不表示每次调用均执行。

- `class DevelopmentService`
- `DevelopmentService.bind_runtime_reader(self, reader)`
- `DevelopmentService.validate_connections(self)`
- `DevelopmentService.history(self, project_id, before_task_id, limit)`
- `DevelopmentService.delivery_page(self, project_id, task_id, before_ordinal, limit)`
- `DevelopmentService.delivery_details(self, project_id, change_id)`
- `DevelopmentService.attach_check_run(self, work, run, change_id)`
- `DevelopmentService.delivery_verification(self, project_id, delivery_id)`
- `DevelopmentService.receipt(self, project_id, kind, operation_id)`
- `DevelopmentService.task(self, project_id, task_id)`
- `DevelopmentService.list(self, project_id, limit)`
- `DevelopmentService.context(self, project_id, context_id)`
- `DevelopmentService.active(self, project_id)`
- `DevelopmentService.view(self, project_id, task_id)`
- `DevelopmentService.create(self, project_id, operation_id, title, goal, expected_version)`
- `DevelopmentService.revise(self, project_id, task_id, operation_id, expected_version, title, goal)`
- `DevelopmentService.accept(self, project_id, task_id, operation_id, expected_version, context_id, client_name)`
- `DevelopmentService.deliver(self, project_id, task_id, operation_id, expected_version, context_id, reason, claimed_paths, repair_reference, submitted_by)`
- `DevelopmentService.registration_preview(self, project_id)`
- `DevelopmentService.register_change(self, project_id, operation_id, expected_registration_fingerprint, reason, claimed_paths, submitted_by, repair_reference)`
- `DevelopmentService.finish(self, project_id, task_id, operation_id, expected_version, cancel)`

静态import / dot-source：`__future__`、`product.backend.core.development`、`product.backend.core.errors`、`product.backend.workflows.changes.service`、`product.backend.workflows.development.operations`、`product.backend.workflows.development.reading`、`time`、`uuid`

<!-- GENERATED:END -->
