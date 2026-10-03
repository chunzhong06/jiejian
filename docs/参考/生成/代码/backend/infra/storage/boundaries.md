# 自动代码参考：backend/infra/storage/boundaries

> 自动生成。当前源码结构与注册投影，不代表运行验收或完整调用图。

<!-- GENERATED:START -->

### `product/backend/infra/storage/boundaries/__init__.py`

[打开源码](../../../../../../../product/backend/infra/storage/boundaries/__init__.py) · Python AST；作用域内import不表示每次调用均执行。


### `product/backend/infra/storage/boundaries/business_boundaries.py`

[打开源码](../../../../../../../product/backend/infra/storage/boundaries/business_boundaries.py) · Python AST；作用域内import不表示每次调用均执行。

- `class BusinessActorRevisionRow`
- `class BusinessActorRow`
- `class BusinessActionRevisionRow`
- `class BusinessActionRow`
- `class BoundaryProposalRow`
- `class BoundaryProposalDecisionRow`
- `class ActorImplementationBindingRow`
- `class ActionImplementationBindingRow`
- `class BusinessBoundaryRepository`
- `BusinessBoundaryRepository.add_actor(self, actor) -> None`
- `BusinessBoundaryRepository.replace_actor(self, actor) -> None`
- `BusinessBoundaryRepository.actor(self, actor_id) -> BusinessActor &#124; None`
- `BusinessBoundaryRepository.add_actor_revision(self, revision) -> None`
- `BusinessBoundaryRepository.actor_revision(self, actor_id, revision) -> BusinessActorRevision &#124; None`
- `BusinessBoundaryRepository.list_actor_revisions(self, project_id) -> tuple[BusinessActorRevision, ...]`
- `BusinessBoundaryRepository.list_actors(self, project_id) -> tuple[BusinessActor, ...]`
- `BusinessBoundaryRepository.add_action(self, action) -> None`
- `BusinessBoundaryRepository.replace_action(self, action) -> None`
- `BusinessBoundaryRepository.action(self, action_id) -> BusinessAction &#124; None`
- `BusinessBoundaryRepository.add_action_revision(self, revision) -> None`
- `BusinessBoundaryRepository.action_revision(self, action_id, revision) -> BusinessActionRevision &#124; None`
- `BusinessBoundaryRepository.list_action_revisions(self, project_id) -> tuple[BusinessActionRevision, ...]`
- `BusinessBoundaryRepository.list_actions(self, project_id) -> tuple[BusinessAction, ...]`
- `BusinessBoundaryRepository.add_proposal(self, proposal) -> None`
- `BusinessBoundaryRepository.get_proposal(self, proposal_id) -> BoundaryProposalBundle &#124; None`
- `BusinessBoundaryRepository.list_proposals(self, project_id) -> tuple[BoundaryProposalBundle, ...]`
- `BusinessBoundaryRepository.add_decision(self, decision) -> None`
- `BusinessBoundaryRepository.decision_for_proposal(self, proposal_id) -> BoundaryProposalDecision &#124; None`
- `BusinessBoundaryRepository.replace_actor_binding(self, binding) -> None`
- `BusinessBoundaryRepository.actor_binding(self, actor_id, revision) -> ActorImplementationBinding &#124; None`
- `BusinessBoundaryRepository.replace_action_binding(self, binding) -> None`
- `BusinessBoundaryRepository.action_binding(self, action_id, revision) -> ActionImplementationBinding &#124; None`

静态import / dot-source：`__future__`、`collections.abc`、`product.backend.core.boundaries.entities`、`product.backend.core.boundaries.proposals`、`product.backend.infra.storage.base`、`sqlalchemy`、`sqlalchemy.orm`、`作用域内：json`

### `product/backend/infra/storage/boundaries/contracts.py`

[打开源码](../../../../../../../product/backend/infra/storage/boundaries/contracts.py) · Python AST；作用域内import不表示每次调用均执行。

- `class ContractVersionRow`
- `class ContractVersionRepository`
- `ContractVersionRepository.add(self, contract) -> None`
- `ContractVersionRepository.get(self, project_id, contract_id, version) -> ContractVersion &#124; None`
- `ContractVersionRepository.get_active(self, project_id, contract_id) -> ContractVersion &#124; None`
- `ContractVersionRepository.list_for_contract(self, project_id, contract_id) -> tuple[ContractVersion, ...]`
- `ContractVersionRepository.list_for_project(self, project_id) -> tuple[ContractVersion, ...]`
- `ContractVersionRepository.replace(self, contract) -> None`

静态import / dot-source：`__future__`、`collections.abc`、`json`、`product.backend.core.contracts.models`、`product.backend.core.errors`、`product.backend.core.lifecycle`、`product.backend.core.verification.permissions`、`product.backend.infra.storage.base`、`sqlalchemy`、`sqlalchemy.orm`

### `product/backend/infra/storage/boundaries/permission_intents.py`

[打开源码](../../../../../../../product/backend/infra/storage/boundaries/permission_intents.py) · Python AST；作用域内import不表示每次调用均执行。

- `class PermissionIntentRevisionRow`
- `class ProjectPolicyStateRow`
- `class PermissionIntentRepository`
- `PermissionIntentRepository.policy_state(self, project_id) -> ProjectPolicyState &#124; None`
- `PermissionIntentRepository.replace_policy_state(self, state) -> None`
- `PermissionIntentRepository.add_revision(self, revision) -> None`
- `PermissionIntentRepository.get_revision(self, intent_id, revision) -> PermissionIntentRevision &#124; None`
- `PermissionIntentRepository.latest(self, intent_id) -> PermissionIntentRevision &#124; None`
- `PermissionIntentRepository.list_history(self, project_id) -> tuple[PermissionIntentRevision, ...]`
- `PermissionIntentRepository.list_revisions(self, project_id) -> tuple[PermissionIntentRevision, ...]`
- `PermissionIntentRepository.list_latest(self, project_id) -> tuple[PermissionIntentRevision, ...]`

静态import / dot-source：`__future__`、`collections.abc`、`json`、`product.backend.core.boundaries.permissions`、`product.backend.infra.storage.base`、`sqlalchemy`、`sqlalchemy.orm`

### `product/backend/infra/storage/boundaries/rule_candidates.py`

[打开源码](../../../../../../../product/backend/infra/storage/boundaries/rule_candidates.py) · Python AST；作用域内import不表示每次调用均执行。

- `class RuleCandidateRow`
- `class RuleCandidateRevisionRow`
- `class RuleCandidateProposalRow`
- `class RuleCandidateReceiptRow`
- `class RuleCandidateRepository`
- `RuleCandidateRepository.get(self, project_id, candidate_id, revision)`
- `RuleCandidateRepository.list(self, project_id, offset, limit)`
- `RuleCandidateRepository.append(self, value, expected_revision)`
- `RuleCandidateRepository.proposal_id(self, candidate_id, revision)`
- `RuleCandidateRepository.link_proposal(self, candidate_id, revision, proposal_id)`
- `RuleCandidateRepository.receipt(self, project_id, kind, operation_id)`
- `RuleCandidateRepository.add_receipt(self, project_id, kind, operation_id, fingerprint, value)`

静态import / dot-source：`__future__`、`product.backend.core.boundaries.rule_candidates`、`product.backend.core.errors`、`product.backend.infra.storage.base`、`sqlalchemy`、`sqlalchemy.orm`

<!-- GENERATED:END -->
