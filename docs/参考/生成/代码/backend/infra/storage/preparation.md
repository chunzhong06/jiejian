# 自动代码参考：backend/infra/storage/preparation

> 自动生成。当前源码结构与注册投影，不代表运行验收或完整调用图。

<!-- GENERATED:START -->

### `product/backend/infra/storage/preparation/__init__.py`

[打开源码](../../../../../../../product/backend/infra/storage/preparation/__init__.py) · Python AST；作用域内import不表示每次调用均执行。


### `product/backend/infra/storage/preparation/action_preparation.py`

[打开源码](../../../../../../../product/backend/infra/storage/preparation/action_preparation.py) · Python AST；作用域内import不表示每次调用均执行。

- `class ActionExecutionBindingRow`
- `class ActionResourceBindingRow`
- `class ActionEvidenceBindingRow`
- `class ActionRecoveryBindingRow`
- `_ROWS`
- `_JSON_FIELDS`
- `class ActionAllowControlBindingRow`
- `class ActionPreparationRepository`
- `ActionPreparationRepository.replace(self, binding) -> None`
- `ActionPreparationRepository.allow_controls(self, project_id) -> tuple[ActionAllowControlBinding, ...]`
- `ActionPreparationRepository.replace_allow_control(self, binding) -> None`
- `ActionPreparationRepository.execution(self, action_id, revision) -> ActionExecutionBinding &#124; None`
- `ActionPreparationRepository.resource(self, action_id, revision, owner_id) -> ActionResourceBinding &#124; None`
- `ActionPreparationRepository.resources(self, action_id, revision) -> tuple[ActionResourceBinding, ...]`
- `ActionPreparationRepository.evidence(self, action_id, revision, effect_id) -> ActionEvidenceBinding &#124; None`
- `ActionPreparationRepository.recovery(self, action_id, revision) -> ActionRecoveryBinding &#124; None`

静态import / dot-source：`__future__`、`collections.abc`、`json`、`product.backend.core.errors`、`product.backend.core.preparation.bindings`、`product.backend.core.preparation.requirements`、`product.backend.infra.storage.base`、`sqlalchemy`、`sqlalchemy.orm`

### `product/backend/infra/storage/preparation/preparation_recovery.py`

[打开源码](../../../../../../../product/backend/infra/storage/preparation/preparation_recovery.py) · Python AST；作用域内import不表示每次调用均执行。

- `class PreparationReceiptRow`
- `class PreparationDraftRow`
- `class PreparationCandidateRecordingRow`
- `class PreparationRecoveryRepository`
- `PreparationRecoveryRepository.mark_candidate_recording(self, recording_id)`
- `PreparationRecoveryRepository.candidate_recording(self, recording_id)`
- `PreparationRecoveryRepository.receipt(self, operation_id, project_id, operation_kind)`
- `PreparationRecoveryRepository.add_receipt(self, value, operation_kind)`
- `PreparationRecoveryRepository.draft(self, project_id)`
- `PreparationRecoveryRepository.save_draft(self, project_id, draft)`

静态import / dot-source：`json`、`product.backend.core.errors`、`product.backend.infra.storage.base`、`sqlalchemy`、`sqlalchemy.orm`

### `product/backend/infra/storage/preparation/proof_sources.py`

[打开源码](../../../../../../../product/backend/infra/storage/preparation/proof_sources.py) · Python AST；作用域内import不表示每次调用均执行。

- `class ProofSourceRow`
- `class ProofSourceRevisionRow`
- `class ProofReadScopeRow`
- `class ProofPreflightRow`
- `class ProofSourceRepository`
- `ProofSourceRepository.source(self, project_id, source_id, revision)`
- `ProofSourceRepository.list(self, project_id, offset, limit)`
- `ProofSourceRepository.save(self, value, expected_revision)`
- `ProofSourceRepository.adoption(self, project_id, source_id)`
- `ProofSourceRepository.adopt(self, value)`
- `ProofSourceRepository.scope(self, project_id, scope_id)`
- `ProofSourceRepository.scopes(self, project_id)`
- `ProofSourceRepository.add_scope(self, value)`
- `ProofSourceRepository.revoke(self, project_id, scope_id, now)`
- `ProofSourceRepository.add_preflight(self, value)`
- `ProofSourceRepository.preflight(self, project_id, preflight_id)`
- `ProofSourceRepository.preflights(self, project_id, source_id, revision, limit)`
- `ProofSourceRepository.report_hash(self, project_id, preflight_id)`
- `ProofSourceRepository.publish(self, project_id, preflight_id, report_hash)`

静态import / dot-source：`product.backend.core.errors`、`product.backend.infra.storage.base`、`product.protocols.preparation.proof_sources`、`sqlalchemy`、`sqlalchemy.orm`

### `product/backend/infra/storage/preparation/recordings.py`

[打开源码](../../../../../../../product/backend/infra/storage/preparation/recordings.py) · Python AST；作用域内import不表示每次调用均执行。

- `class RecordingRow`
- `class FlowDraftRevisionRow`
- `class RecordingRecord`
- `RecordingRecord.validate_recording_lifecycle(self) -> RecordingRecord`
- `RecordingRecord.to_domain(self) -> Recording`
- `RecordingRecord.from_domain(cls, recording, flow_id, browser_events) -> RecordingRecord`
- `class FlowDraftRevisionRecord`
- `FlowDraftRevisionRecord.validate_draft_identity(self) -> FlowDraftRevisionRecord`
- `class RecordingRepository`
- `RecordingRepository.add(self, record) -> None`
- `RecordingRepository.replace(self, record) -> None`
- `RecordingRepository.get(self, recording_id) -> RecordingRecord &#124; None`
- `RecordingRepository.list_for_project(self, project_id) -> tuple[RecordingRecord, ...]`
- `class FlowDraftRevisionRepository`
- `FlowDraftRevisionRepository.add(self, record) -> None`
- `FlowDraftRevisionRepository.list_for_recording(self, recording_id) -> tuple[FlowDraftRevisionRecord, ...]`
- `FlowDraftRevisionRepository.latest(self, recording_id) -> FlowDraftRevisionRecord &#124; None`

静态import / dot-source：`__future__`、`collections.abc`、`hashlib`、`json`、`product.backend.core.boundaries.entities`、`product.backend.core.errors`、`product.backend.core.identifiers`、`product.backend.core.lifecycle`、`product.backend.core.recording.models`、`product.backend.core.verification.permissions`、`product.backend.infra.storage.base`、`product.protocols`、`pydantic`、`re`、`sqlalchemy`、`sqlalchemy.exc`、`sqlalchemy.orm`、`time`、`typing`、`作用域内：product.protocols.recording.flow_draft`、`作用域内：product.protocols.recording.recording_legacy`

### `product/backend/infra/storage/preparation/supplemental_materials.py`

[打开源码](../../../../../../../product/backend/infra/storage/preparation/supplemental_materials.py) · Python AST；作用域内import不表示每次调用均执行。

- `class SupplementalMaterialRevisionRow`
- `class SupplementalMaterialReceiptRow`
- `class SupplementalMaterialRepository`
- `SupplementalMaterialRepository.get(self, material_id, revision)`
- `SupplementalMaterialRepository.receipt(self, project_id, request_id)`
- `SupplementalMaterialRepository.add(self, value, request_id, content_fingerprint)`
- `SupplementalMaterialRepository.list(self, project_id, action_id, material_id, limit, before_revision)`

静态import / dot-source：`__future__`、`json`、`product.backend.infra.storage.base`、`sqlalchemy`、`sqlalchemy.orm`

### `product/backend/infra/storage/preparation/test_identities.py`

[打开源码](../../../../../../../product/backend/infra/storage/preparation/test_identities.py) · Python AST；作用域内import不表示每次调用均执行。

- `class TestIdentityRow`
- `class TestIdentityCookieRow`
- `class TestIdentityRepository`
- `TestIdentityRepository.add(self, record) -> None`
- `TestIdentityRepository.get(self, identity_id) -> TestIdentity &#124; None`
- `TestIdentityRepository.list_for_project(self, project_id) -> tuple[TestIdentity, ...]`
- `TestIdentityRepository.replace(self, record) -> None`
- `TestIdentityRepository.delete(self, identity_id) -> None`

静态import / dot-source：`__future__`、`collections.abc`、`product.backend.core.errors`、`product.backend.core.identities.models`、`product.backend.infra.storage.base`、`sqlalchemy`、`sqlalchemy.orm`

<!-- GENERATED:END -->
