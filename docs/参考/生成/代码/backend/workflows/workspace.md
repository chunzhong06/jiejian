# 自动代码参考：backend/workflows/workspace

> 自动生成。当前源码结构与注册投影，不代表运行验收或完整调用图。

<!-- GENERATED:START -->

### `product/backend/workflows/workspace/__init__.py`

[打开源码](../../../../../../product/backend/workflows/workspace/__init__.py) · Python AST；作用域内import不表示每次调用均执行。


静态import / dot-source：`product.backend.workflows.workspace.models`、`product.backend.workflows.workspace.service`

### `product/backend/workflows/workspace/models.py`

[打开源码](../../../../../../product/backend/workflows/workspace/models.py) · Python AST；作用域内import不表示每次调用均执行。

- `class WorkspaceModel`
- `class WorkspaceProjectView`
- `class WorkspaceConnectionView`
- `class ActorWorkspaceView`
- `class ActionWorkspaceView`
- `class PrimaryTaskView`
- `class WorkspaceAreaView`
- `class WorkspaceLatestResult`
- `class WorkspaceSourceChange`
- `class WorkspaceJourneyStep`
- `class WorkspaceJourney`
- `class WorkspaceDevelopment`
- `class WorkspaceView`

静态import / dot-source：`__future__`、`product.backend.core.boundaries.entities`、`product.backend.core.boundaries.permissions`、`product.backend.core.boundaries.proposals`、`product.backend.core.identifiers`、`product.backend.core.lifecycle`、`product.backend.workflows.business_boundaries.inspection`、`product.backend.workflows.business_boundaries.models`、`product.backend.workflows.checks.reading.results`、`product.backend.workflows.projects.repair`、`product.protocols`、`pydantic`、`typing`

### `product/backend/workflows/workspace/presentation.py`

[打开源码](../../../../../../product/backend/workflows/workspace/presentation.py) · Python AST；作用域内import不表示每次调用均执行。

- `_TASK_PRESENTATION`
- `task_view(task_kind, title, why_now, user_responsibility, system_will_do, route, facts, business_action_id, business_actor_id, can_execute, **context) -> PrimaryTaskView`
- `journey_view(connection, boundary_attention, preparation_complete, task, result, change, active)`
- `action_view(action, boundary, inspection, actor_inspection_by_id, permission_status) -> ActionWorkspaceView`
- `endpoint_status(understanding) -> str`
- `source_status(understanding) -> str`
- `area_views(boundary_attention, preparation_complete) -> tuple[WorkspaceAreaView, ...]`
- `boundary_views(boundary, pending)`
- `development_view(facts)`

静态import / dot-source：`__future__`、`product.backend.core.applications.models`、`product.backend.core.boundaries.entities`、`product.backend.core.boundaries.semantics`、`product.backend.workflows.workspace.models`、`作用域内：product.backend.workflows.checks.repairs.repair_text`、`作用域内：product.backend.workflows.workspace.models`

### `product/backend/workflows/workspace/reading.py`

[打开源码](../../../../../../product/backend/workflows/workspace/reading.py) · Python AST；作用域内import不表示每次调用均执行。

- `class WorkspaceCheckReaders`
- `class WorkspaceCheckFacts`
- `class WorkspaceDevelopmentFacts`
- `class WorkspaceReader`
- `WorkspaceReader.validate_connections(self)`
- `WorkspaceReader.project(self, project_id)`
- `WorkspaceReader.checks(self, project_id, boundary, understanding)`
- `WorkspaceReader.source_drifted(self, project_id, understanding)`
- `WorkspaceReader.development_facts(self, project_id)`
- `WorkspaceReader.preparation(self, project_id)`
- `class PreparationReading`
- `PreparationReading.resumable(self, recording, prepared_ids)`
- `PreparationReading.parent_for(self, action)`

静态import / dot-source：`__future__`、`collections.abc`、`contextlib`、`dataclasses`、`product.backend.core.development`、`product.backend.core.errors`、`product.backend.core.recording.models`、`product.backend.workflows.checks.reading.story_text`、`product.backend.workflows.preparation.models`、`product.backend.workflows.recording.source`、`product.backend.workflows.workspace.models`、`typing`、`作用域内：product.backend.workflows.changes.service`、`作用域内：product.backend.workflows.checks.reading.results`、`作用域内：product.backend.workflows.checks.service`、`作用域内：product.backend.workflows.projects.repair`

### `product/backend/workflows/workspace/service.py`

[打开源码](../../../../../../product/backend/workflows/workspace/service.py) · Python AST；作用域内import不表示每次调用均执行。

- `class WorkspaceService`
- `WorkspaceService.validate_connections(self)`
- `WorkspaceService.get(self, project_id) -> WorkspaceView`

静态import / dot-source：`__future__`、`product.backend.workflows.workspace.models`、`product.backend.workflows.workspace.presentation`、`product.backend.workflows.workspace.reading`、`product.backend.workflows.workspace.tasks`

### `product/backend/workflows/workspace/tasks.py`

[打开源码](../../../../../../product/backend/workflows/workspace/tasks.py) · Python AST；作用域内import不表示每次调用均执行。

- `class CheckPreviewRequired`
- `boundary_task(understanding, boundary, pending) -> PrimaryTaskView &#124; None`
- `allow_control_task(preparation)`
- `PREPARATION_TEXTS`
- `class PreparationTaskSelection`
- `PreparationTaskSelection.add(self, priority, kind, slot, can_execute, text, route, **context)`
- `PreparationTaskSelection.resume_recording(self, recording)`
- `PreparationTaskSelection.prepare_missing(self)`
- `PreparationTaskSelection.complete_materials(self, parent)`
- `current_check_task(task, drifted, latest_result, preview_can_execute)`
- `development_task(primary_task, facts, boundary_attention, active_check, preview)`

静态import / dot-source：`__future__`、`dataclasses`、`product.backend.core.applications.models`、`product.backend.core.boundaries.entities`、`product.backend.core.recording.models`、`product.backend.workflows.business_boundaries.models`、`product.backend.workflows.checks.repairs.repair_text`、`product.backend.workflows.preparation.demonstrations`、`product.backend.workflows.preparation.models`、`product.backend.workflows.workspace.models`、`product.backend.workflows.workspace.presentation`

<!-- GENERATED:END -->
