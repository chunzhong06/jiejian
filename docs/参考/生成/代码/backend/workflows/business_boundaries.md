# 自动代码参考：backend/workflows/business_boundaries

> 自动生成。当前源码结构与注册投影，不代表运行验收或完整调用图。

<!-- GENERATED:START -->

### `product/backend/workflows/business_boundaries/__init__.py`

[打开源码](../../../../../../product/backend/workflows/business_boundaries/__init__.py) · Python AST；作用域内import不表示每次调用均执行。


静态import / dot-source：`.models`、`.service`

### `product/backend/workflows/business_boundaries/candidates/__init__.py`

[打开源码](../../../../../../product/backend/workflows/business_boundaries/candidates/__init__.py) · Python AST；作用域内import不表示每次调用均执行。


### `product/backend/workflows/business_boundaries/candidates/drafting.py`

[打开源码](../../../../../../product/backend/workflows/business_boundaries/candidates/drafting.py) · Python AST；作用域内import不表示每次调用均执行。

- `_OPTION_ID_PATTERN`
- `_MAX_OPTIONS`
- `_MAX_SUGGESTIONS`
- `_MAX_QUOTE_CHARS`
- `class PermissionDraftStatus`
- `class PermissionDraftSuggestionView`
- `class PermissionDraftIssueView`
- `class PermissionDraftView`
- `class PermissionDraftService`
- `PermissionDraftService.draft(self, project_id, human_text) -> PermissionDraftView`

静态import / dot-source：`__future__`、`dataclasses`、`enum`、`json`、`product.backend.core.boundaries.entities`、`product.backend.core.boundaries.permissions`、`product.backend.core.boundaries.semantics`、`product.backend.core.errors`、`product.backend.infra.llm.adapters.base`、`pydantic`、`re`、`unicodedata`、`uuid`

### `product/backend/workflows/business_boundaries/candidates/rule_candidates.py`

[打开源码](../../../../../../product/backend/workflows/business_boundaries/candidates/rule_candidates.py) · Python AST；作用域内import不表示每次调用均执行。

- `class RuleCandidateService`
- `RuleCandidateService.context(self, project_id, offset)`
- `RuleCandidateService.save(self, project_id, command, submitted_via)`
- `RuleCandidateService.show(self, project_id, candidate_id, revision)`
- `RuleCandidateService.operation(self, project_id, kind, operation_id)`
- `RuleCandidateService.propose(self, project_id, candidate_id, revision, operation_id)`

静态import / dot-source：`__future__`、`json`、`product.backend.core.boundaries.entities`、`product.backend.core.boundaries.rule_candidates`、`product.backend.core.errors`、`product.backend.workflows.business_boundaries.models`、`pydantic`、`time`、`uuid`

### `product/backend/workflows/business_boundaries/fingerprints.py`

[打开源码](../../../../../../product/backend/workflows/business_boundaries/fingerprints.py) · Python AST；作用域内import不表示每次调用均执行。

- `candidate_source_snapshot(kind, candidate) -> CandidateSourceSnapshot`
- `legacy_candidate_source_snapshot(kind, candidate) -> CandidateSourceSnapshot`
- `implementation_candidate_snapshot(source) -> ImplementationCandidateSnapshot`

静态import / dot-source：`__future__`、`product.backend.core.applications.models`、`product.backend.core.boundaries.entities`、`product.backend.core.boundaries.proposals`

### `product/backend/workflows/business_boundaries/inspection.py`

[打开源码](../../../../../../product/backend/workflows/business_boundaries/inspection.py) · Python AST；作用域内import不表示每次调用均执行。

- `class ActorImplementationInspection`
- `class ActionImplementationInspection`
- `inspect_actor_binding(actor_id, actor_revision, binding, understanding) -> ActorImplementationInspection`
- `inspect_action_binding(action_id, action_revision, binding, understanding) -> ActionImplementationInspection`

静态import / dot-source：`__future__`、`product.backend.core.applications.models`、`product.backend.core.boundaries.entities`、`product.backend.core.boundaries.proposals`、`product.backend.core.identifiers`、`product.backend.workflows.business_boundaries.fingerprints`、`pydantic`、`typing`

### `product/backend/workflows/business_boundaries/models.py`

[打开源码](../../../../../../product/backend/workflows/business_boundaries/models.py) · Python AST；作用域内import不表示每次调用均执行。

- `class BoundaryWorkflowModel`
- `class BoundaryProposalCommand`
- `class BoundaryDraftCandidate`
- `class BoundaryDraftView`
- `class BoundaryMaintenanceCandidateOption`
- `BoundaryMaintenanceCandidateOption.validate_candidate_id(self) -> BoundaryMaintenanceCandidateOption`
- `class BoundaryMaintenanceActorItem`
- `BoundaryMaintenanceActorItem.normalize_sources(cls, values) -> tuple[str, ...]`
- `BoundaryMaintenanceActorItem.validate_identity(self) -> BoundaryMaintenanceActorItem`
- `class BoundaryMaintenanceActionItem`
- `BoundaryMaintenanceActionItem.normalize_sources(cls, values) -> tuple[str, ...]`
- `BoundaryMaintenanceActionItem.normalize_effects(cls, values) -> tuple[ProposedEffectItem, ...]`
- `BoundaryMaintenanceActionItem.validate_identity(self) -> BoundaryMaintenanceActionItem`
- `class BoundaryMaintenancePermissionItem`
- `BoundaryMaintenancePermissionItem.normalize_effect_refs(cls, values) -> tuple[str, ...]`
- `BoundaryMaintenancePermissionItem.validate_identity(self) -> BoundaryMaintenancePermissionItem`
- `class BoundaryMaintenanceCommand`
- `BoundaryMaintenanceCommand.normalize_items(cls, values) -> tuple[object, ...]`
- `class BoundaryMaintenanceDraftView`
- `class BoundaryProposalChangeSummary`
- `class BoundaryReviewEffect`
- `class BoundaryReviewValue`
- `class BoundaryReviewItem`
- `class BoundaryProposalReview`
- `class BoundaryProposalView`
- `class BoundaryProposalListView`
- `class OfficialBoundaryActorSummary`
- `class OfficialBoundaryEffectSummary`
- `class OfficialBoundaryActionSummary`
- `class OfficialBoundaryPermissionSummary`
- `class OfficialBoundaryRecipe`
- `class PermissionBoundaryStatus`
- `class BusinessBoundaryView`
- `class BoundaryPendingProposal`
- `class BoundaryEditorView`

静态import / dot-source：`__future__`、`product.backend.core.boundaries.entities`、`product.backend.core.boundaries.permissions`、`product.backend.core.boundaries.proposals`、`product.backend.core.boundaries.semantics`、`product.backend.core.identifiers`、`product.backend.workflows.business_boundaries.inspection`、`pydantic`、`typing`

### `product/backend/workflows/business_boundaries/proposals/__init__.py`

[打开源码](../../../../../../product/backend/workflows/business_boundaries/proposals/__init__.py) · Python AST；作用域内import不表示每次调用均执行。


### `product/backend/workflows/business_boundaries/proposals/maintenance.py`

[打开源码](../../../../../../product/backend/workflows/business_boundaries/proposals/maintenance.py) · Python AST；作用域内import不表示每次调用均执行。

- `boundary_state_fingerprint(project_id, actors, actions, permissions, policy_epoch) -> str`
- `build_maintenance_draft(project_id, actor_roots, action_roots, actors, actions, permissions, actor_inspections, action_inspections, understanding, policy_epoch) -> BoundaryMaintenanceDraftView`
- `maintenance_to_proposal_command(project_id, command, actor_roots, action_roots, actors, actions, permissions, policy_epoch) -> BoundaryProposalCommand`
- `proposal_change_summary(proposal, permissions, actor_bindings, action_bindings) -> BoundaryProposalChangeSummary`

静态import / dot-source：`__future__`、`product.backend.core.applications.models`、`product.backend.core.boundaries.entities`、`product.backend.core.boundaries.permissions`、`product.backend.core.boundaries.proposals`、`product.backend.core.errors`、`product.backend.workflows.business_boundaries.inspection`、`product.backend.workflows.business_boundaries.models`

### `product/backend/workflows/business_boundaries/proposals/official_recipe.py`

[打开源码](../../../../../../product/backend/workflows/business_boundaries/proposals/official_recipe.py) · Python AST；作用域内import不表示每次调用均执行。

- `OFFICIAL_BOUNDARY_PROVENANCE`
- `_OWNER`
- `_MEMBER`
- `_EXPORT`
- `_VIEW`
- `_EXPORT_EFFECT`
- `_VIEW_EFFECT`
- `official_boundary_recipe() -> OfficialBoundaryRecipe`

静态import / dot-source：`__future__`、`product.backend.core.boundaries.entities`、`product.backend.core.boundaries.permissions`、`product.backend.core.boundaries.proposals`、`product.backend.core.boundaries.semantics`、`product.backend.workflows.business_boundaries.models`

### `product/backend/workflows/business_boundaries/proposals/planning.py`

[打开源码](../../../../../../product/backend/workflows/business_boundaries/proposals/planning.py) · Python AST；作用域内import不表示每次调用均执行。


静态import / dot-source：`__future__`、`dataclasses`、`product.backend.core.applications.models`、`product.backend.core.boundaries.approval`、`product.backend.core.boundaries.entities`、`product.backend.core.boundaries.permissions`、`product.backend.core.boundaries.proposals`、`product.backend.core.errors`、`product.backend.infra.storage`、`product.backend.workflows.business_boundaries.proposals`、`uuid`

### `product/backend/workflows/business_boundaries/proposals/review.py`

[打开源码](../../../../../../product/backend/workflows/business_boundaries/proposals/review.py) · Python AST；作用域内import不表示每次调用均执行。

- `proposal_review(work, proposal) -> BoundaryProposalReview`

静态import / dot-source：`__future__`、`product.backend.core.boundaries.proposals`、`product.backend.infra.storage`、`product.backend.workflows.business_boundaries.models`

### `product/backend/workflows/business_boundaries/proposals/sources.py`

[打开源码](../../../../../../product/backend/workflows/business_boundaries/proposals/sources.py) · Python AST；作用域内import不表示每次调用均执行。


静态import / dot-source：`__future__`、`product.backend.core.applications.models`、`product.backend.core.boundaries.entities`、`product.backend.core.boundaries.proposals`、`product.backend.core.errors`、`product.backend.workflows.business_boundaries.fingerprints`、`product.backend.workflows.business_boundaries.models`、`product.backend.workflows.business_boundaries.proposals`

### `product/backend/workflows/business_boundaries/proposals/validation.py`

[打开源码](../../../../../../product/backend/workflows/business_boundaries/proposals/validation.py) · Python AST；作用域内import不表示每次调用均执行。


静态import / dot-source：`__future__`、`product.backend.core.applications.models`、`product.backend.core.boundaries.entities`、`product.backend.core.boundaries.proposals`、`product.backend.core.errors`、`product.backend.infra.storage`

### `product/backend/workflows/business_boundaries/reading/__init__.py`

[打开源码](../../../../../../product/backend/workflows/business_boundaries/reading/__init__.py) · Python AST；作用域内import不表示每次调用均执行。


### `product/backend/workflows/business_boundaries/reading/permissions.py`

[打开源码](../../../../../../product/backend/workflows/business_boundaries/reading/permissions.py) · Python AST；作用域内import不表示每次调用均执行。

- `class PermissionIntentViewModel`
- `class PermissionIntentCellStatus`
- `class PermissionIntentCellView`
- `class PermissionIntentActionView`
- `class PermissionIntentMatrixView`
- `class PermissionIntentHistoryView`
- `class PermissionIntentService`
- `PermissionIntentService.current_intents(self, project_id) -> tuple[PermissionIntentRevision, ...]`
- `PermissionIntentService.history(self, project_id, intent_id) -> PermissionIntentHistoryView`
- `PermissionIntentService.matrix(self, project_id) -> PermissionIntentMatrixView`
- `PermissionIntentService.policy_snapshot(self, project_id)`

静态import / dot-source：`__future__`、`collections.abc`、`enum`、`product.backend.core.boundaries.permissions`、`product.backend.core.errors`、`product.backend.infra.storage`、`pydantic`

### `product/backend/workflows/business_boundaries/reading/queries.py`

[打开源码](../../../../../../product/backend/workflows/business_boundaries/reading/queries.py) · Python AST；作用域内import不表示每次调用均执行。

- `current_permission_intents(latest, actors, actions) -> tuple[tuple[PermissionIntentRevision, ...], tuple[PermissionIntentRevision, ...]]`

静态import / dot-source：`__future__`、`dataclasses`、`product.backend.core.applications.models`、`product.backend.core.boundaries.entities`、`product.backend.core.boundaries.permissions`、`product.backend.core.boundaries.proposals`、`product.backend.core.errors`、`product.backend.core.preparation.requirements`、`product.backend.infra.storage`、`product.backend.workflows.business_boundaries.inspection`、`product.backend.workflows.business_boundaries.models`、`product.backend.workflows.business_boundaries.proposals`、`product.backend.workflows.business_boundaries.proposals.maintenance`、`product.backend.workflows.business_boundaries.proposals.review`

### `product/backend/workflows/business_boundaries/reading/rule_details.py`

[打开源码](../../../../../../product/backend/workflows/business_boundaries/reading/rule_details.py) · Python AST；作用域内import不表示每次调用均执行。

- `class BusinessRuleDetails`
- `BusinessRuleDetails.read(self, project_id, intent_id, revision)`

静态import / dot-source：`product.backend.core.errors`

### `product/backend/workflows/business_boundaries/service.py`

[打开源码](../../../../../../product/backend/workflows/business_boundaries/service.py) · Python AST；作用域内import不表示每次调用均执行。

- `class BusinessBoundaryService`
- `BusinessBoundaryService.preview_from_discovery(self, project_id) -> BoundaryDraftView`
- `BusinessBoundaryService.create_proposal(self, project_id, command) -> BoundaryProposalView`
- `BusinessBoundaryService.create_initial_proposal(self, project_id, command) -> BoundaryProposalView`
- `BusinessBoundaryService.maintenance_draft(self, project_id, work, allow_empty) -> BoundaryMaintenanceDraftView`
- `BusinessBoundaryService.create_maintenance_proposal(self, project_id, command, work, allow_initial) -> BoundaryProposalView`
- `BusinessBoundaryService.proposals(self, project_id, pending_only) -> BoundaryProposalListView`
- `BusinessBoundaryService.editor(self, project_id) -> BoundaryEditorView`
- `BusinessBoundaryService.proposal(self, project_id, proposal_id) -> BoundaryProposalView`
- `BusinessBoundaryService.approve(self, project_id, proposal_id, expected_fingerprint, reason) -> BusinessBoundaryView`
- `BusinessBoundaryService.reject(self, project_id, proposal_id, expected_fingerprint, reason) -> BoundaryProposalView`
- `BusinessBoundaryService.view(self, project_id, work) -> BusinessBoundaryView`
- `BusinessBoundaryService.actor_revision(self, project_id, actor_id, revision) -> BusinessActorRevision`

静态import / dot-source：`__future__`、`collections.abc`、`contextlib`、`product.backend.core.applications.models`、`product.backend.core.boundaries.approval`、`product.backend.core.boundaries.entities`、`product.backend.core.boundaries.permissions`、`product.backend.core.boundaries.proposals`、`product.backend.core.errors`、`product.backend.infra.storage`、`product.backend.workflows.business_boundaries.inspection`、`product.backend.workflows.business_boundaries.models`、`product.backend.workflows.business_boundaries.proposals`、`product.backend.workflows.business_boundaries.proposals.maintenance`、`product.backend.workflows.business_boundaries.reading`、`time`、`uuid`、`作用域内：contextlib`

<!-- GENERATED:END -->
