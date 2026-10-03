# 自动代码参考：backend/core/boundaries

> 自动生成。当前源码结构与注册投影，不代表运行验收或完整调用图。

<!-- GENERATED:START -->

### `product/backend/core/boundaries/__init__.py`

[打开源码](../../../../../../product/backend/core/boundaries/__init__.py) · Python AST；作用域内import不表示每次调用均执行。


### `product/backend/core/boundaries/approval.py`

[打开源码](../../../../../../product/backend/core/boundaries/approval.py) · Python AST；作用域内import不表示每次调用均执行。

- `class HumanApprovalChannel`
- `class HumanApproval`
- `HumanApproval.validate_text(cls, value, info) -> str`
- `HumanApproval.validate_local_user(self) -> HumanApproval`

静态import / dot-source：`__future__`、`enum`、`pydantic`

### `product/backend/core/boundaries/entities.py`

[打开源码](../../../../../../product/backend/core/boundaries/entities.py) · Python AST；作用域内import不表示每次调用均执行。

- `ACTOR_ID_PATTERN`
- `ACTION_ID_PATTERN`
- `EFFECT_ID_PATTERN`
- `SOURCE_PROPOSAL_ID_PATTERN`
- `_PROJECTION_PATH`
- `class BoundaryModel`
- `class BusinessRevisionState`
- `class BusinessActionOperationKind`
- `class ImplementationBindingStatus`
- `class ImplementationCandidateSnapshot`
- `boundary_sha256(payload) -> str`
- `class BusinessEffectDefinition`
- `BusinessEffectDefinition.validate_text(cls, value, info) -> str &#124; None`
- `BusinessEffectDefinition.normalize_projection(cls, values) -> tuple[str, ...]`
- `BusinessEffectDefinition.validate_effect_kind(self) -> BusinessEffectDefinition`
- `BusinessEffectDefinition.business_payload(self) -> dict[str, Any]`
- `class BusinessActor`
- `BusinessActor.validate_times(self) -> BusinessActor`
- `class BusinessActorRevision`
- `BusinessActorRevision.validate_text(cls, value, info) -> str`
- `BusinessActorRevision.semantic_payload(self) -> dict[str, Any]`
- `BusinessActorRevision.validate_revision(self) -> BusinessActorRevision`
- `class BusinessAction`
- `BusinessAction.validate_times(self) -> BusinessAction`
- `class BusinessActionRevision`
- `BusinessActionRevision.validate_text(cls, value, info) -> str`
- `BusinessActionRevision.normalize_effect_catalog(cls, values) -> tuple[BusinessEffectDefinition, ...]`
- `BusinessActionRevision.semantic_payload(self) -> dict[str, Any]`
- `BusinessActionRevision.validate_revision(self) -> BusinessActionRevision`
- `class ActorImplementationBinding`
- `ActorImplementationBinding.normalize_candidates(cls, values) -> tuple[str, ...]`
- `ActorImplementationBinding.validate_binding(self) -> ActorImplementationBinding`
- `class ActionImplementationBinding`
- `ActionImplementationBinding.normalize_candidates(cls, values) -> tuple[str, ...]`
- `ActionImplementationBinding.validate_binding(self) -> ActionImplementationBinding`

静态import / dot-source：`__future__`、`enum`、`hashlib`、`json`、`product.backend.core.boundaries.approval`、`product.backend.core.boundaries.semantics`、`product.backend.core.identifiers`、`pydantic`、`re`、`typing`

### `product/backend/core/boundaries/permissions.py`

[打开源码](../../../../../../product/backend/core/boundaries/permissions.py) · Python AST；作用域内import不表示每次调用均执行。

- `_INTENT_ID_PATTERN`
- `class PermissionIntentModel`
- `class PermissionIntentRelation`
- `class PermissionIntentEffectiveState`
- `permission_relation_consistent(relation, subject, owner) -> bool`
- `permission_intent_sha256(payload) -> str`
- `class PermissionIntentSemantic`
- `PermissionIntentSemantic.normalize_effect_ids(cls, values) -> tuple[str, ...]`
- `PermissionIntentSemantic.canonical_payload(self) -> dict[str, Any]`
- `class PermissionIntentRevision`
- `PermissionIntentRevision.validate_revision(self) -> PermissionIntentRevision`
- `class ProjectPolicyState`

静态import / dot-source：`__future__`、`enum`、`hashlib`、`json`、`product.backend.core.boundaries.approval`、`product.backend.core.boundaries.entities`、`product.backend.core.boundaries.semantics`、`product.backend.core.identifiers`、`pydantic`、`re`、`typing`

### `product/backend/core/boundaries/proposals.py`

[打开源码](../../../../../../product/backend/core/boundaries/proposals.py) · Python AST；作用域内import不表示每次调用均执行。

- `PROPOSAL_ID_PATTERN`
- `DECISION_ID_PATTERN`
- `ACTOR_ITEM_ID_PATTERN`
- `ACTION_ITEM_ID_PATTERN`
- `EFFECT_ITEM_ID_PATTERN`
- `PERMISSION_ITEM_ID_PATTERN`
- `INTENT_ID_PATTERN`
- `class ProposalWriteMode`
- `class ProposalCandidateKind`
- `class BoundaryDecisionKind`
- `class CandidateSourceSnapshot`
- `CandidateSourceSnapshot.validate_candidate_id(self) -> CandidateSourceSnapshot`
- `class BoundarySourceSnapshot`
- `BoundarySourceSnapshot.normalize_candidates(cls, values) -> tuple[CandidateSourceSnapshot, ...]`
- `class ProposedEffectItem`
- `ProposedEffectItem.validate_text(cls, value, info) -> str &#124; None`
- `ProposedEffectItem.normalize_projection(cls, values) -> tuple[str, ...]`
- `ProposedEffectItem.validate_projection_kind(self) -> ProposedEffectItem`
- `class ProposedActorItem`
- `ProposedActorItem.validate_text(cls, value, info) -> str`
- `ProposedActorItem.normalize_sources(cls, values) -> tuple[str, ...]`
- `ProposedActorItem.validate_item(self) -> ProposedActorItem`
- `class ProposedActionItem`
- `ProposedActionItem.validate_text(cls, value, info) -> str`
- `ProposedActionItem.normalize_sources(cls, values) -> tuple[str, ...]`
- `ProposedActionItem.normalize_effects(cls, values) -> tuple[ProposedEffectItem, ...]`
- `ProposedActionItem.validate_item(self) -> ProposedActionItem`
- `class ProposedPermissionItem`
- `ProposedPermissionItem.normalize_effect_refs(cls, values) -> tuple[str, ...]`
- `ProposedPermissionItem.validate_item(self) -> ProposedPermissionItem`
- `class BoundaryProposalBundle`
- `BoundaryProposalBundle.normalize_items(cls, values) -> tuple[Any, ...]`
- `BoundaryProposalBundle.validate_questions(cls, values) -> tuple[str, ...]`
- `BoundaryProposalBundle.validate_provenance(cls, value) -> str`
- `BoundaryProposalBundle.fingerprint_payload(self) -> dict[str, Any]`
- `BoundaryProposalBundle.validate_bundle(self) -> BoundaryProposalBundle`
- `class BoundaryProposalDecision`
- `BoundaryProposalDecision.validate_text(cls, value, info) -> str`
- `BoundaryProposalDecision.validate_decider(self) -> BoundaryProposalDecision`

静态import / dot-source：`__future__`、`enum`、`product.backend.core.boundaries.entities`、`product.backend.core.boundaries.permissions`、`product.backend.core.boundaries.semantics`、`product.backend.core.identifiers`、`pydantic`、`re`、`typing`

### `product/backend/core/boundaries/rule_candidates.py`

[打开源码](../../../../../../product/backend/core/boundaries/rule_candidates.py) · Python AST；作用域内import不表示每次调用均执行。

- `CANDIDATE_ID_PATTERN`
- `BASIS_ID_PATTERN`
- `OPERATION_ID_PATTERN`
- `class RuleExample`
- `RuleExample.require_mapping_or_limitation(self) -> RuleExample`
- `class RuleCandidateContent`
- `RuleCandidateContent.bounded_original(cls, value) -> str`
- `RuleCandidateContent.bounded_questions(cls, values) -> tuple[str, ...]`
- `RuleCandidateContent.unique_items(self) -> RuleCandidateContent`
- `class RuleCandidateRevision`
- `class RuleCandidateSave`
- `RuleCandidateSave.paired_revision(self) -> RuleCandidateSave`

静态import / dot-source：`__future__`、`product.backend.core.boundaries.entities`、`product.backend.core.boundaries.proposals`、`product.backend.core.identifiers`、`pydantic`、`typing`

### `product/backend/core/boundaries/semantics.py`

[打开源码](../../../../../../product/backend/core/boundaries/semantics.py) · Python AST；作用域内import不表示每次调用均执行。

- `class PermissionExpectation`
- `class BusinessEffectKind`

静态import / dot-source：`enum`

<!-- GENERATED:END -->
