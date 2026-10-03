# 自动代码参考：backend/infra/storage/changes

> 自动生成。当前源码结构与注册投影，不代表运行验收或完整调用图。

<!-- GENERATED:START -->

### `product/backend/infra/storage/changes/__init__.py`

[打开源码](../../../../../../../product/backend/infra/storage/changes/__init__.py) · Python AST；作用域内import不表示每次调用均执行。


### `product/backend/infra/storage/changes/code_observations.py`

[打开源码](../../../../../../../product/backend/infra/storage/changes/code_observations.py) · Python AST；作用域内import不表示每次调用均执行。

- `class CodeObservationRow`
- `class ChangeCodeObservationRow`
- `class RunCodeObservationRow`
- `class CodeObservationRepository`
- `CodeObservationRepository.add_link(self, value, kind, target_id, project_id, source_fingerprint)`
- `CodeObservationRepository.for_target(self, project_id, kind, target_id)`

静态import / dot-source：`__future__`、`product.backend.core.errors`、`product.backend.infra.storage.base`、`sqlalchemy`、`sqlalchemy.orm`

### `product/backend/infra/storage/changes/development.py`

[打开源码](../../../../../../../product/backend/infra/storage/changes/development.py) · Python AST；作用域内import不表示每次调用均执行。

- `class DevelopmentTaskRow`
- `class DevelopmentContextRow`
- `class DevelopmentAcceptanceRow`
- `class DevelopmentDeliveryRow`
- `class DevelopmentReceiptRow`
- `class DevelopmentCheckRunRow`
- `class DevelopmentRepository`
- `DevelopmentRepository.task(self, project_id, task_id)`
- `DevelopmentRepository.active(self, project_id)`
- `DevelopmentRepository.tasks(self, project_id, limit, before)`
- `DevelopmentRepository.add_task(self, value)`
- `DevelopmentRepository.replace_task(self, value, expected_version)`
- `DevelopmentRepository.context(self, project_id, context_id)`
- `DevelopmentRepository.add_context(self, value)`
- `DevelopmentRepository.first_context(self, project_id, task_id)`
- `DevelopmentRepository.acceptance(self, project_id, context_id)`
- `DevelopmentRepository.add_acceptance(self, value)`
- `DevelopmentRepository.deliveries(self, project_id, task_id, limit, before_ordinal)`
- `DevelopmentRepository.add_delivery(self, value)`
- `DevelopmentRepository.delivery(self, project_id, delivery_id)`
- `DevelopmentRepository.delivery_for_change(self, project_id, change_id)`
- `DevelopmentRepository.add_check_run(self, delivery_id, run_id, created_at_us)`
- `DevelopmentRepository.latest_check_run(self, project_id, delivery_id)`
- `DevelopmentRepository.runtime_receipt(self, project_id, operation_id)`
- `DevelopmentRepository.finish_runtime_receipt(self, before, value)`
- `DevelopmentRepository.receipt(self, project_id, kind, operation_id)`
- `DevelopmentRepository.add_receipt(self, value)`

静态import / dot-source：`json`、`product.backend.core.development`、`product.backend.core.errors`、`product.backend.infra.storage.base`、`sqlalchemy`、`sqlalchemy.orm`

### `product/backend/infra/storage/changes/source_changes.py`

[打开源码](../../../../../../../product/backend/infra/storage/changes/source_changes.py) · Python AST；作用域内import不表示每次调用均执行。

- `class SourceRevisionSnapshotRow`
- `class ChangeManifestRow`
- `class SourceChangeSetRow`
- `class ChangeImpactAssessmentRow`
- `class SourceChangeRepository`
- `SourceChangeRepository.add_current_change(self, manifest, change_set, assessment) -> None`
- `SourceChangeRepository.current_change(self, project_id, change_id)`
- `SourceChangeRepository.current_changes(self, project_id, limit)`
- `SourceChangeRepository.latest_current_for_repair(self, project_id, reference)`
- `SourceChangeRepository.add_snapshot(self, snapshot) -> None`
- `SourceChangeRepository.snapshot_for_fingerprint(self, project_id, fingerprint) -> SourceRevisionSnapshot &#124; None`
- `SourceChangeRepository.snapshot(self, snapshot_id) -> SourceRevisionSnapshot &#124; None`
- `SourceChangeRepository.add_change(self, manifest, change_set, assessment) -> None`
- `SourceChangeRepository.manifest(self, change_id) -> ChangeManifest &#124; None`
- `SourceChangeRepository.change_set(self, change_id) -> SourceChangeSet &#124; None`
- `SourceChangeRepository.assessment(self, change_id) -> ChangeImpactAssessment &#124; None`
- `SourceChangeRepository.latest_assessment(self, project_id) -> ChangeImpactAssessment &#124; None`
- `SourceChangeRepository.latest_manifest_for_repair(self, project_id, reference) -> ChangeManifest &#124; None`
- `SourceChangeRepository.list_assessments(self, project_id, limit) -> tuple[ChangeImpactAssessment, ...]`

静态import / dot-source：`__future__`、`collections.abc`、`json`、`product.backend.core.changes.models`、`product.backend.core.errors`、`product.backend.core.reports.repair`、`product.backend.infra.storage.base`、`sqlalchemy`、`sqlalchemy.orm`、`作用域内：product.backend.core.changes.models`

<!-- GENERATED:END -->
