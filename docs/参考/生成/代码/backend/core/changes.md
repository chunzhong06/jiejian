# 自动代码参考：backend/core/changes

> 自动生成。当前源码结构与注册投影，不代表运行验收或完整调用图。

<!-- GENERATED:START -->

### `product/backend/core/changes/__init__.py`

[打开源码](../../../../../../product/backend/core/changes/__init__.py) · Python AST；作用域内import不表示每次调用均执行。


### `product/backend/core/changes/models.py`

[打开源码](../../../../../../product/backend/core/changes/models.py) · Python AST；作用域内import不表示每次调用均执行。

- `_SNAPSHOT_ID_PATTERN`
- `_CHANGE_ID_PATTERN`
- `_INTENT_ID_PATTERN`
- `_DRIVE_PATH`
- `_REASON_CODE`
- `class SourceChangeModel`
- `normalize_relative_source_path(value) -> str`
- `class SourceFileFingerprint`
- `SourceFileFingerprint.validate_relative_path(cls, value) -> str`
- `source_fingerprint(files) -> str`
- `source_snapshot_id(project_id, fingerprint) -> str`
- `class SourceRevisionSnapshot`
- `SourceRevisionSnapshot.validate_snapshot(self) -> SourceRevisionSnapshot`
- `class ChangeManifest`
- `ChangeManifest.validate_text(cls, value) -> str`
- `ChangeManifest.validate_claimed_paths(cls, values) -> tuple[str, ...]`
- `class SourceChangeSet`
- `SourceChangeSet.validate_paths(cls, values) -> tuple[str, ...]`
- `SourceChangeSet.canonical_payload(self) -> dict[str, Any]`
- `SourceChangeSet.changed_paths(self) -> tuple[str, ...]`
- `SourceChangeSet.validate_change_set(self) -> SourceChangeSet`
- `class IntentChangeImpact`
- `IntentChangeImpact.validate_relevant_paths(cls, values) -> tuple[str, ...]`
- `IntentChangeImpact.validate_reason_codes(cls, values) -> tuple[str, ...]`
- `IntentChangeImpact.validate_message(self) -> IntentChangeImpact`
- `class ChangeImpactAssessment`
- `ChangeImpactAssessment.validate_reason_codes(cls, values) -> tuple[str, ...]`
- `ChangeImpactAssessment.canonical_payload(self) -> dict[str, Any]`
- `ChangeImpactAssessment.validate_assessment(self) -> ChangeImpactAssessment`
- `class RevalidationPlan`
- `RevalidationPlan.validate_required_intent_ids(cls, values) -> tuple[str, ...]`
- `source_change_fingerprint(payload) -> str`
- `change_impact_fingerprint(payload) -> str`
- `class CurrentChangeManifest`
- `class CurrentActionChangeImpact`
- `CurrentActionChangeImpact.validate_paths(cls, values)`
- `class CurrentChangeAssessmentPayload`
- `CurrentChangeAssessmentPayload.validate_sets(self)`
- `class CurrentChangeAssessment`
- `CurrentChangeAssessment.validate_content(self)`
- `build_current_change_set(manifest, baseline, current) -> SourceChangeSet`

静态import / dot-source：`__future__`、`hashlib`、`json`、`product.backend.core.checks.repair`、`product.backend.core.identifiers`、`product.backend.core.reports.repair`、`product.protocols.checks.execution_request`、`pydantic`、`re`、`typing`

<!-- GENERATED:END -->
