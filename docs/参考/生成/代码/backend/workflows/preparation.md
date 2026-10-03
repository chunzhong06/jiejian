# 自动代码参考：backend/workflows/preparation

> 自动生成。当前源码结构与注册投影，不代表运行验收或完整调用图。

<!-- GENERATED:START -->

### `product/backend/workflows/preparation/__init__.py`

[打开源码](../../../../../../product/backend/workflows/preparation/__init__.py) · Python AST；作用域内import不表示每次调用均执行。


静态import / dot-source：`product.backend.workflows.preparation.service`

### `product/backend/workflows/preparation/bindings/__init__.py`

[打开源码](../../../../../../product/backend/workflows/preparation/bindings/__init__.py) · Python AST；作用域内import不表示每次调用均执行。


### `product/backend/workflows/preparation/bindings/recording_candidates.py`

[打开源码](../../../../../../product/backend/workflows/preparation/bindings/recording_candidates.py) · Python AST；作用域内import不表示每次调用均执行。

- `class RecordedPreparationCandidate`
- `request_event(recording, step)`
- `resource_value(event, candidate) -> str`
- `flow_resource_injection(flow, candidate) -> ResourceInjection`
- `supplement_candidates(recording, draft, actual_resource_id) -> tuple[RecordedPreparationCandidate, ...]`
- `choose_supplement_candidate(recording, draft, actual_resource_id)`

静态import / dot-source：`__future__`、`json`、`product.backend.core.boundaries.entities`、`product.backend.core.errors`、`product.backend.core.preparation.bindings`、`product.backend.core.recording.models`、`product.protocols.recording.events`、`product.protocols.web.workflow`、`pydantic`、`re`、`typing`、`urllib.parse`

### `product/backend/workflows/preparation/bindings/reuse.py`

[打开源码](../../../../../../product/backend/workflows/preparation/bindings/reuse.py) · Python AST；作用域内import不表示每次调用均执行。

- `recorded_material_reusable(work, binding, understanding, var_dir)`

静态import / dot-source：`product.backend.infra.observers.records.source_contracts`

### `product/backend/workflows/preparation/bindings/service.py`

[打开源码](../../../../../../product/backend/workflows/preparation/bindings/service.py) · Python AST；作用域内import不表示每次调用均执行。

- `class RegisteredEffectProofReader`
- `RegisteredEffectProofReader.capability(self, project_id, reference, effect_id) -> RegisteredEffectProofCapability &#124; None`
- `class PreparationBindingService`
- `PreparationBindingService.describe_evidence(self, action, views)`
- `PreparationBindingService.proof_capabilities(self, project_id, evidence)`
- `PreparationBindingService.accept_recording(self, work, recording, draft_record, flow, now_us)`
- `PreparationBindingService.build_recording_bindings(self, work, recording, draft_record, flow, now_us)`
- `PreparationBindingService.candidates(self, recording_id)`
- `PreparationBindingService.register_observer(self, recording_id, effect_id, reference, now_us)`
- `PreparationBindingService.inspect(self, action, contract, identities, work) -> ActionTechnicalPreparationView`
- `PreparationBindingService.inspect_item(self, work, binding, action, understanding, missing_reason)`

静态import / dot-source：`__future__`、`contextlib`、`hashlib`、`json`、`pathlib`、`product.backend.core.boundaries.entities`、`product.backend.core.checks.plan`、`product.backend.core.errors`、`product.backend.core.preparation.bindings`、`product.backend.core.recording.models`、`product.backend.workflows.business_boundaries.inspection`、`product.backend.workflows.preparation.bindings.recording_candidates`、`product.backend.workflows.preparation.bindings.sources`、`product.backend.workflows.preparation.models`、`product.backend.workflows.recording.source`、`product.backend.workflows.test_identities.service`、`typing`、`作用域内：product.backend.workflows.preparation.materials.evidence_models`

### `product/backend/workflows/preparation/bindings/sources.py`

[打开源码](../../../../../../product/backend/workflows/preparation/bindings/sources.py) · Python AST；作用域内import不表示每次调用均执行。

- `class RegisteredObserverReader`
- `RegisteredObserverReader.contains(self, project_id, reference) -> bool`
- `class BindingSourceInspector`
- `BindingSourceInspector.reasons(self, work, binding, action, understanding)`
- `binding_source_fields(work, action, identity, understanding, now_us, owner_id)`

静态import / dot-source：`__future__`、`pathlib`、`product.backend.core.boundaries.entities`、`product.backend.core.errors`、`product.backend.core.preparation.bindings`、`product.backend.core.recording.models`、`product.backend.workflows.business_boundaries.inspection`、`product.backend.workflows.preparation.bindings.recording_candidates`、`product.backend.workflows.recording.source`、`typing`、`作用域内：product.backend.workflows.preparation.bindings.reuse`、`作用域内：product.backend.workflows.recording.lifecycle`

### `product/backend/workflows/preparation/demonstrations.py`

[打开源码](../../../../../../product/backend/workflows/preparation/demonstrations.py) · Python AST；作用域内import不表示每次调用均执行。

- `class LegalActionDemonstration`
- `legal_demonstrations(contract, permissions, identities)`

静态import / dot-source：`product.backend.core.boundaries.entities`、`product.backend.core.boundaries.semantics`、`product.backend.core.preparation.requirements`、`product.backend.workflows.preparation.models`

### `product/backend/workflows/preparation/guidance/__init__.py`

[打开源码](../../../../../../product/backend/workflows/preparation/guidance/__init__.py) · Python AST；作用域内import不表示每次调用均执行。


### `product/backend/workflows/preparation/guidance/models.py`

[打开源码](../../../../../../product/backend/workflows/preparation/guidance/models.py) · Python AST；作用域内import不表示每次调用均执行。

- `class PreparationNextAction`
- `class PreparationMaterialAdvice`
- `class ProofSourceAdvice`
- `class PreparationGuidance`

静态import / dot-source：`product.backend.core.boundaries.entities`、`pydantic`、`typing`

### `product/backend/workflows/preparation/guidance/service.py`

[打开源码](../../../../../../product/backend/workflows/preparation/guidance/service.py) · Python AST；作用域内import不表示每次调用均执行。

- `PREPARATION_TASKS`
- `REASONS`
- `class PreparationGuidanceService`
- `PreparationGuidanceService.context(self, project_id)`

静态import / dot-source：`product.backend.workflows.preparation.guidance.models`、`urllib.parse`

### `product/backend/workflows/preparation/materials/__init__.py`

[打开源码](../../../../../../product/backend/workflows/preparation/materials/__init__.py) · Python AST；作用域内import不表示每次调用均执行。


### `product/backend/workflows/preparation/materials/evidence.py`

[打开源码](../../../../../../product/backend/workflows/preparation/materials/evidence.py) · Python AST；作用域内import不表示每次调用均执行。

- `evidence_details(service, project_id, action_id) -> EvidenceMaterialDetail`

静态import / dot-source：`product.backend.core.errors`、`product.backend.workflows.preparation.materials.evidence_models`、`product.backend.workflows.preparation.models`

### `product/backend/workflows/preparation/materials/evidence_models.py`

[打开源码](../../../../../../product/backend/workflows/preparation/materials/evidence_models.py) · Python AST；作用域内import不表示每次调用均执行。

- `class EffectMaterialSummary`
- `class EvidenceMaterialDetail`

静态import / dot-source：`product.backend.core.boundaries.entities`、`product.backend.workflows.preparation.models`、`pydantic`、`typing`

### `product/backend/workflows/preparation/materials/models.py`

[打开源码](../../../../../../product/backend/workflows/preparation/materials/models.py) · Python AST；作用域内import不表示每次调用均执行。

- `class MaterialReference`
- `class MaterialChange`
- `class PreparationDraft`
- `PreparationDraft.coherent_context(self)`

静态import / dot-source：`product.backend.core.boundaries.entities`、`pydantic`、`typing`

### `product/backend/workflows/preparation/materials/service.py`

[打开源码](../../../../../../product/backend/workflows/preparation/materials/service.py) · Python AST；作用域内import不表示每次调用均执行。

- `class PreparationMaterialService`
- `PreparationMaterialService.details(self, project_id, reference)`
- `PreparationMaterialService.preview(self, project_id, command)`
- `PreparationMaterialService.apply(self, project_id, command)`
- `PreparationMaterialService.receipt(self, project_id, operation_id)`
- `PreparationMaterialService.draft(self, project_id)`
- `PreparationMaterialService.save_draft(self, project_id, draft)`

静态import / dot-source：`json`、`product.backend.core.boundaries.entities`、`product.backend.core.errors`、`product.backend.core.preparation.bindings`、`product.backend.core.recording.models`、`product.backend.workflows.preparation.materials.models`、`product.backend.workflows.recording.lifecycle`、`time`、`作用域内：product.backend.workflows.business_boundaries.inspection`、`作用域内：product.backend.workflows.preparation.demonstrations`、`作用域内：product.backend.workflows.recording.source`

### `product/backend/workflows/preparation/models.py`

[打开源码](../../../../../../product/backend/workflows/preparation/models.py) · Python AST；作用域内import不表示每次调用均执行。

- `class PreparationStatus`
- `class PreparationItemView`
- `class IdentitySlotPreparationView`
- `class IdentityPreparationView`
- `class ResourcePreparationView`
- `class EffectEvidencePreparationView`
- `class ActionTechnicalPreparationView`
- `class ActionPreparationView`
- `class PreparationView`

静态import / dot-source：`enum`、`product.backend.core.boundaries.entities`、`product.backend.core.boundaries.permissions`、`product.backend.core.preparation.requirements`、`pydantic`

### `product/backend/workflows/preparation/planning.py`

[打开源码](../../../../../../product/backend/workflows/preparation/planning.py) · Python AST；作用域内import不表示每次调用均执行。

- `current_plan(service, project_id, engine_version, config_fingerprint)`

静态import / dot-source：`product.backend.core.checks.plan`、`product.backend.core.errors`、`product.backend.workflows.preparation.models`、`product.backend.workflows.recording.source`、`作用域内：product.backend.core.preparation.requirements`

### `product/backend/workflows/preparation/proofs/__init__.py`

[打开源码](../../../../../../product/backend/workflows/preparation/proofs/__init__.py) · Python AST；作用域内import不表示每次调用均执行。


### `product/backend/workflows/preparation/proofs/commands.py`

[打开源码](../../../../../../product/backend/workflows/preparation/proofs/commands.py) · Python AST；作用域内import不表示每次调用均执行。

- `class ProofOperation`
- `class SaveProofSource`
- `class StartProofPreflight`
- `class GrantProofScope`
- `class AdoptProofSource`
- `class CancelProofPreflight`
- `class RevokeProofScope`

静态import / dot-source：`product.protocols.preparation.proof_sources`、`product.protocols.runtime.runtime_identity`、`pydantic`、`typing`

### `product/backend/workflows/preparation/proofs/jobs.py`

[打开源码](../../../../../../product/backend/workflows/preparation/proofs/jobs.py) · Python AST；作用域内import不表示每次调用均执行。

- `class ProofPreflightJobs`
- `ProofPreflightJobs.submit(self, work, request, operation_id)`
- `ProofPreflightJobs.publish(self, report, known_secrets)`
- `ProofPreflightJobs.read(self, work, project_id, preflight_id)`

静态import / dot-source：`product.backend.core.errors`、`product.backend.core.lifecycle`、`product.backend.infra.artifacts.proof_reports`、`product.backend.infra.runtime.jobs.events`、`product.backend.infra.runtime.jobs.models`、`product.backend.infra.storage`、`product.protocols.preparation.proof_sources`、`uuid`、`作用域内：collections`、`作用域内：product.protocols.preparation.proof_sources`、`动态引用：time`

### `product/backend/workflows/preparation/proofs/registration.py`

[打开源码](../../../../../../product/backend/workflows/preparation/proofs/registration.py) · Python AST；作用域内import不表示每次调用均执行。

- `runtime_registration(project_id, sources)`

静态import / dot-source：`product.backend.workflows.checks.registry`、`product.protocols.observer`

### `product/backend/workflows/preparation/proofs/service.py`

[打开源码](../../../../../../product/backend/workflows/preparation/proofs/service.py) · Python AST；作用域内import不表示每次调用均执行。

- `class PreparationFacts`
- `class ProofPreparationService`
- `ProofPreparationService.bind_authority_checker(self, checker)`
- `ProofPreparationService.context(self, project_id)`
- `ProofPreparationService.show(self, project_id, source_id)`
- `ProofPreparationService.receipt(self, project_id, kind, operation_id)`
- `ProofPreparationService.save(self, project_id, command, submitted_via, client_name)`
- `ProofPreparationService.grant_scope(self, project_id, command)`
- `ProofPreparationService.start(self, project_id, command, authority_id)`
- `ProofPreparationService.status(self, project_id, preflight_id)`
- `ProofPreparationService.adoption_preview(self, project_id, source_id, preflight_id)`
- `ProofPreparationService.adopt(self, project_id, command)`
- `ProofPreparationService.active_sources(self, project_id)`
- `ProofPreparationService.runtime_registration(self, project_id)`
- `ProofPreparationService.frozen_sources(self, project_id)`
- `ProofPreparationService.job_authorized(self, job)`
- `ProofPreparationService.cancel(self, project_id, command)`
- `ProofPreparationService.revoke_scope(self, project_id, command)`
- `ProofPreparationService.cancel_unauthorized(self)`

静态import / dot-source：`dataclasses`、`product.backend.core.applications.models`、`product.backend.core.boundaries.entities`、`product.backend.core.errors`、`product.backend.core.identities.models`、`product.backend.core.lifecycle`、`product.backend.core.preparation.bindings`、`product.backend.infra.observers.records.source_contracts`、`product.backend.infra.runtime.jobs.models`、`product.backend.workflows.business_boundaries.inspection`、`product.backend.workflows.business_boundaries.models`、`product.backend.workflows.recording.source`、`product.protocols.checks.check_runtime`、`product.protocols.preparation.proof_sources`、`product.protocols.runtime.node_runtime`、`product.protocols.web.request`、`product.protocols.web.target`、`time`、`uuid`、`作用域内：product.backend.core.preparation.bindings`、`作用域内：product.backend.workflows.preparation.bindings.sources`、`作用域内：product.backend.workflows.preparation.proofs.registration`、`作用域内：product.protocols.preparation.proof_sources`

### `product/backend/workflows/preparation/service.py`

[打开源码](../../../../../../product/backend/workflows/preparation/service.py) · Python AST；作用域内import不表示每次调用均执行。

- `class BoundaryReader`
- `BoundaryReader.view(self, project_id, work) -> BusinessBoundaryView`
- `class IdentityReader`
- `IdentityReader.list(self, project_id) -> tuple[TestIdentityView, ...]`
- `class PreparationBindingReader`
- `PreparationBindingReader.inspect(self, action, contract, identities, work) -> ActionTechnicalPreparationView`
- `class PreparationService`
- `PreparationService.evidence_details(self, project_id, action_id)`
- `PreparationService.current_plan(self, project_id, engine_version, config_fingerprint)`
- `PreparationService.build_execution_request_v3(self, project_id, engine_version, config_fingerprint, budget_fingerprint, change_context, repair_context)`
- `PreparationService.select_allow_control(self, project_id, deny_permission, selected_allow_permission, expected_selection_fingerprint)`
- `PreparationService.get(self, project_id) -> PreparationView`

静态import / dot-source：`__future__`、`product.backend.core.boundaries.entities`、`product.backend.core.errors`、`product.backend.core.preparation.requirements`、`product.backend.workflows.business_boundaries.models`、`product.backend.workflows.preparation.models`、`product.backend.workflows.test_identities.service`、`time`、`typing`、`作用域内：json`、`作用域内：product.backend.workflows.preparation.demonstrations`、`作用域内：product.backend.workflows.preparation.materials.evidence`、`作用域内：product.backend.workflows.preparation.planning`、`作用域内：product.protocols.checks.execution_request`

### `product/backend/workflows/preparation/supplemental/__init__.py`

[打开源码](../../../../../../product/backend/workflows/preparation/supplemental/__init__.py) · Python AST；作用域内import不表示每次调用均执行。


### `product/backend/workflows/preparation/supplemental/contract.py`

[打开源码](../../../../../../product/backend/workflows/preparation/supplemental/contract.py) · Python AST；作用域内import不表示每次调用均执行。

- `class MaterialModel`
- `class SupplementalRecord`
- `class SupplementalDocument`
- `SupplementalDocument.safe_document(self)`
- `validate_material_payload(value, known_secrets)`
- `material_fingerprint(value)`
- `request_uuid(value)`

静态import / dot-source：`__future__`、`hashlib`、`product.backend.core.errors`、`product.backend.infra.storage.base`、`pydantic`、`re`、`typing`、`uuid`

### `product/backend/workflows/preparation/supplemental/service.py`

[打开源码](../../../../../../product/backend/workflows/preparation/supplemental/service.py) · Python AST；作用域内import不表示每次调用均执行。

- `class SupplementalMaterialService`
- `SupplementalMaterialService.preview(self, project_id, action_id, document)`
- `SupplementalMaterialService.create(self, project_id, action_id, document, expected_fingerprint, request_id)`
- `SupplementalMaterialService.revise(self, project_id, action_id, material_id, expected_revision, request_id, **labels)`
- `SupplementalMaterialService.withdraw(self, project_id, action_id, material_id, expected_revision, request_id)`
- `SupplementalMaterialService.list(self, project_id, action_id, material_id, limit, before_revision)`

静态import / dot-source：`__future__`、`hashlib`、`product.backend.core.errors`、`product.backend.infra.storage.base`、`product.backend.workflows.preparation.supplemental.contract`、`threading`、`time`、`uuid`

<!-- GENERATED:END -->
