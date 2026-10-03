# 自动代码参考：backend/workflows/changes

> 自动生成。当前源码结构与注册投影，不代表运行验收或完整调用图。

<!-- GENERATED:START -->

### `product/backend/workflows/changes/__init__.py`

[打开源码](../../../../../../product/backend/workflows/changes/__init__.py) · Python AST；作用域内import不表示每次调用均执行。


静态import / dot-source：`.service`

### `product/backend/workflows/changes/identity.py`

[打开源码](../../../../../../product/backend/workflows/changes/identity.py) · Python AST；作用域内import不表示每次调用均执行。

- `class SourceIdentityRecord`
- `class SourceIdentityComparison`
- `class SourceIdentityReader`
- `SourceIdentityReader.for_change(self, project_id, change_id) -> SourceIdentityComparison`
- `SourceIdentityReader.for_run(self, project_id, run_id) -> SourceIdentityComparison`

静态import / dot-source：`__future__`、`product.backend.core.errors`、`product.backend.infra.source_identity`、`product.protocols.checks.execution_request`、`pydantic`、`time`、`typing`

### `product/backend/workflows/changes/observations.py`

[打开源码](../../../../../../product/backend/workflows/changes/observations.py) · Python AST；作用域内import不表示每次调用均执行。

- `class CodeObservationService`
- `CodeObservationService.capture(self, project_id, source_fingerprint)`
- `CodeObservationService.attach_run(self, work, run)`

静态import / dot-source：`__future__`、`product.backend.core.errors`、`product.backend.infra.source_identity`、`time`、`uuid`

### `product/backend/workflows/changes/service.py`

[打开源码](../../../../../../product/backend/workflows/changes/service.py) · Python AST；作用域内import不表示每次调用均执行。

- `class SourceRevalidationInspection`
- `class CurrentChangeView`
- `permission_refs(boundary)`
- `class PreparedSourceChange`
- `class CurrentSourceChangeService`
- `CurrentSourceChangeService.set_dependencies(self, plan_reader, repair_resolver)`
- `CurrentSourceChangeService.validate_connections(self)`
- `CurrentSourceChangeService.submit(self, project_id, reason, claimed_paths, repair_reference, submitted_by)`
- `CurrentSourceChangeService.prepare_change(self, project_id, reason, claimed_paths, repair_reference, submitted_by)`
- `CurrentSourceChangeService.write_prepared_change(self, work, prepared, baseline_snapshot_id)`
- `CurrentSourceChangeService.get(self, project_id, change_id)`
- `CurrentSourceChangeService.list(self, project_id, limit)`
- `CurrentSourceChangeService.latest(self, project_id)`
- `CurrentSourceChangeService.latest_for_repair(self, project_id, reference)`
- `CurrentSourceChangeService.context(self, project_id, change_id)`
- `CurrentSourceChangeService.view(self, project_id, change_id)`
- `CurrentSourceChangeService.inspect_revalidation(self, project_id, change_id)`

静态import / dot-source：`__future__`、`collections.abc`、`dataclasses`、`product.backend.core.changes.models`、`product.backend.core.checks.plan`、`product.backend.core.checks.repair`、`product.backend.core.errors`、`product.protocols.checks.execution_request`、`pydantic`、`time`、`typing`、`uuid`、`作用域内：product.backend.core.checks.repair`、`作用域内：product.backend.workflows.changes.observations`、`作用域内：product.backend.workflows.checks.service`

<!-- GENERATED:END -->
