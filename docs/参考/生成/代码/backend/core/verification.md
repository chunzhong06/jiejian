# 自动代码参考：backend/core/verification

> 自动生成。当前源码结构与注册投影，不代表运行验收或完整调用图。

<!-- GENERATED:START -->

### `product/backend/core/verification/__init__.py`

[打开源码](../../../../../../product/backend/core/verification/__init__.py) · Python AST；作用域内import不表示每次调用均执行。


### `product/backend/core/verification/behavior_differential.py`

[打开源码](../../../../../../product/backend/core/verification/behavior_differential.py) · Python AST；作用域内import不表示每次调用均执行。

- `class BehaviorDifferentialModel`
- `class EvidenceSufficiency`
- `class BehaviorDifferenceKind`
- `class NormalizedSecurityEffect`
- `class BehaviorSnapshot`
- `BehaviorSnapshot.validate_fingerprint(self) -> BehaviorSnapshot`
- `class BehaviorDifference`
- `class BehaviorDifferentialResult`
- `BehaviorDifferentialResult.validate_result(self) -> BehaviorDifferentialResult`
- `normalize_evidence_behavior(evidence, contract_fingerprint, workflow_fingerprint, baseline_fingerprint) -> BehaviorSnapshot`
- `compare_behavior_snapshots(before, after) -> BehaviorDifferentialResult`

静态import / dot-source：`__future__`、`enum`、`product.backend.core.lifecycle`、`product.backend.core.verification.facts`、`product.backend.core.verification.permissions`、`product.protocols.runner`、`pydantic`、`typing`

### `product/backend/core/verification/breakpoints.py`

[打开源码](../../../../../../product/backend/core/verification/breakpoints.py) · Python AST；作用域内import不表示每次调用均执行。

- `_PUBLIC_ID`
- `_REASON_CODE`
- `class BreakpointType`
- `class BreakpointPrecision`
- `class BreakpointResult`
- `BreakpointResult.validate_unique_ids(cls, values) -> tuple[str, ...]`
- `BreakpointResult.validate_amplifiers(cls, values) -> tuple[BreakpointType, ...]`
- `BreakpointResult.validate_reason_codes(cls, values) -> tuple[str, ...]`
- `BreakpointResult.validate_precision_shape(self) -> BreakpointResult`
- `class BreakpointLocator`
- `BreakpointLocator.locate_current(self, action, twin, allow_facts, deny_facts, allow_trace, deny_trace, identities, trace_namespace, allow_evidence_refs, deny_evidence_refs) -> BreakpointResult &#124; None`
- `BreakpointLocator.locate(self, contract, differential_plan, allow_trace, deny_trace, allow_effect_facts, deny_effect_facts, evidence_refs) -> BreakpointResult &#124; None`

静态import / dot-source：`__future__`、`dataclasses`、`enum`、`product.backend.core.verification.checks`、`product.backend.core.verification.continuity`、`product.backend.core.verification.differential`、`product.backend.core.verification.facts`、`product.backend.core.verification.permissions`、`product.backend.core.verification.trace`、`product.protocols.checks.check_runtime`、`product.protocols.checks.execution_request`、`pydantic`、`re`

### `product/backend/core/verification/checks.py`

[打开源码](../../../../../../product/backend/core/verification/checks.py) · Python AST；作用域内import不表示每次调用均执行。

- `class CheckEffectFact`
- `class CheckProofObservation`
- `project_check_effect_facts(case, observations) -> tuple[CheckEffectFact, ...]`
- `class CheckDecisionInput`
- `CheckDecisionInput.validate_proof_associations(self)`
- `class CheckDecision`
- `evaluate_check_case(facts) -> CheckDecision`
- `aggregate_check_verdict(verdicts, planned_case_count, has_gaps) -> RunVerdict`

静态import / dot-source：`__future__`、`collections.abc`、`product.backend.core.lifecycle`、`product.protocols.checks.execution_request`、`pydantic`、`typing`

### `product/backend/core/verification/continuity.py`

[打开源码](../../../../../../product/backend/core/verification/continuity.py) · Python AST；作用域内import不表示每次调用均执行。

- `_PUBLIC_ID`
- `_REASON_CODE`
- `class AuthorizationContinuityState`
- `class AuthorizationEffectReference`
- `class AuthorizationContinuityAssessment`
- `AuthorizationContinuityAssessment.validate_unique_effects(cls, values) -> tuple[AuthorizationEffectReference, ...]`
- `AuthorizationContinuityAssessment.validate_reason_codes(cls, values) -> tuple[str, ...]`
- `AuthorizationContinuityAssessment.validate_state_shape(self) -> AuthorizationContinuityAssessment`
- `assess_check_authorization_continuity(action, facts) -> AuthorizationContinuityAssessment`
- `assess_authorization_continuity(contract, twin, effect_facts) -> AuthorizationContinuityAssessment`

静态import / dot-source：`__future__`、`enum`、`product.backend.core.verification.checks`、`product.backend.core.verification.differential`、`product.backend.core.verification.facts`、`product.backend.core.verification.permissions`、`product.protocols.checks.execution_request`、`pydantic`、`re`

### `product/backend/core/verification/differential.py`

[打开源码](../../../../../../product/backend/core/verification/differential.py) · Python AST；作用域内import不表示每次调用均执行。

- `class TwinPlanGapCode`
- `class TwinExecutionRole`
- `class PermissionMutationDescriptor`
- `class TwinInvariantSpecification`
- `class PermissionTwin`
- `PermissionTwin.validate_twin(self) -> PermissionTwin`
- `class TwinPlanGap`
- `class DifferentialExperimentPlan`
- `DifferentialExperimentPlan.validate_plan(self) -> DifferentialExperimentPlan`
- `build_differential_experiment_plan(contract, coverage, workflow_fingerprints, effect_fingerprints, observer_fingerprint, baseline_fingerprints, normalization_version) -> DifferentialExperimentPlan`

静态import / dot-source：`__future__`、`collections.abc`、`enum`、`product.backend.core.verification.permissions`、`product.backend.core.verification.permissions.coverage`、`pydantic`、`typing`

### `product/backend/core/verification/facts.py`

[打开源码](../../../../../../product/backend/core/verification/facts.py) · Python AST；作用域内import不表示每次调用均执行。

- `_ID`
- `_HEX`
- `_REASON`
- `class FactModel`
- `class TargetType`
- `class ExecutionOutcome`
- `class ObservedEffect`
- `class TemporalClosure`
- `class ExecutionFact`
- `ExecutionFact.validate_reasons(self) -> ExecutionFact`
- `class ObservationFact`
- `ObservationFact.validate_observation(self) -> ObservationFact`
- `class DisclosureProof`
- `class SecurityEffectFact`
- `SecurityEffectFact.validate_effect_fact(self) -> SecurityEffectFact`
- `aggregate_security_effect(effect, resource_id, required_requirement_ids, corroborating_requirement_ids, observations, baseline_integrity, disclosure_proof) -> SecurityEffectFact`

静态import / dot-source：`__future__`、`enum`、`product.backend.core.verification.permissions`、`pydantic`、`re`、`typing`

### `product/backend/core/verification/findings.py`

[打开源码](../../../../../../product/backend/core/verification/findings.py) · Python AST；作用域内import不表示每次调用均执行。

- `_FINDING_ID`
- `_OCCURRENCE_ID`
- `_SAFE_TEXT`
- `_SECRET_TEXT`
- `class FindingIdentity`
- `FindingIdentity.normalize_scalar(cls, value, info) -> str`
- `FindingIdentity.normalize_tokens(cls, value, info) -> tuple[str, ...]`
- `FindingIdentity.canonical_payload(self) -> dict[str, Any]`
- `FindingIdentity.stable_key_sha256(self) -> str`
- `FindingIdentity.finding_id(self) -> str`
- `class FindingInput`
- `FindingInput.validate_input(self) -> FindingInput`
- `class OccurrenceStatus`
- `class Finding`
- `Finding.validate_identity(self) -> Finding`
- `class FindingOccurrence`
- `FindingOccurrence.normalize_evidence_refs(cls, values) -> tuple[str, ...]`
- `FindingOccurrence.validate_occurrence(self) -> FindingOccurrence`
- `occurrence_id_for(finding_id, run_id) -> str`

静态import / dot-source：`__future__`、`enum`、`hashlib`、`json`、`product.backend.core.identifiers`、`product.backend.core.lifecycle`、`pydantic`、`re`、`typing`

### `product/backend/core/verification/gating.py`

[打开源码](../../../../../../product/backend/core/verification/gating.py) · Python AST；作用域内import不表示每次调用均执行。

- `_TOKEN`
- `_ACTOR`
- `_SECRET`
- `_SEVERITY_ORDER`
- `gate_canonical_sha256(value) -> str`
- `class GateDecision`
- `class BaselineFindingRef`
- `BaselineFindingRef.validate_evidence_ids(cls, values) -> tuple[str, ...]`
- `class RegressionBaseline`
- `RegressionBaseline.validate_tokens(cls, value, info) -> str`
- `RegressionBaseline.validate_token_lists(cls, values, info) -> tuple[str, ...]`
- `RegressionBaseline.validate_actor(cls, value) -> str`
- `RegressionBaseline.validate_reason(cls, value) -> str`
- `RegressionBaseline.validate_baseline(self) -> RegressionBaseline`
- `class GateFinding`
- `class GateFacts`
- `GateFacts.validate_fact_tokens(cls, value, info) -> str &#124; None`
- `GateFacts.validate_fact_lists(cls, values, info) -> tuple[str, ...]`
- `class GatePolicy`
- `class GateReason`
- `GateReason.validate_subject(cls, value) -> str`
- `class GateResult`
- `baseline_id_for(project_id, run_id, request_snapshot_sha256, coverage_digest) -> str`
- `gate_input_hash(baseline_id, facts, policy) -> str`
- `gate_result_id_for(baseline_id, run_id, policy_version, input_hash) -> str`
- `evaluate_gate(baseline, facts, policy) -> GateResult`

静态import / dot-source：`__future__`、`collections.abc`、`enum`、`hashlib`、`json`、`product.backend.core.lifecycle`、`pydantic`、`re`、`typing`

### `product/backend/core/verification/permissions/__init__.py`

[打开源码](../../../../../../product/backend/core/verification/permissions/__init__.py) · Python AST；作用域内import不表示每次调用均执行。

- `_LAZY_EXPORTS`

静态import / dot-source：`.contract`、`.models`、`importlib`、`动态引用：.coverage`、`动态引用：.evaluation`

### `product/backend/core/verification/permissions/contract.py`

[打开源码](../../../../../../product/backend/core/verification/permissions/contract.py) · Python AST；作用域内import不表示每次调用均执行。

- `_ID_PATTERN`
- `_TEXT_PATTERN`
- `_STATE_PATTERN`
- `_HEX_PATTERN`
- `_SECRET_OR_URL`
- `class PermissionContract`
- `PermissionContract.reject_forbidden_contract_text(cls, value) -> str`
- `PermissionContract.normalize_declared_ids(cls, values, info) -> tuple[str, ...]`
- `PermissionContract.validate_references(self) -> PermissionContract`
- `parse_permission_contract(raw) -> PermissionContract`
- `class NormalizedPermissionCase`
- `class NormalizedPermissionPlan`
- `NormalizedPermissionPlan.normalize_cases(self) -> NormalizedPermissionPlan`
- `canonical_json_bytes(value) -> bytes`
- `permission_model_sha256(value) -> str`
- `compile_permission_plan(contract, engine_version, seed) -> NormalizedPermissionPlan`

静态import / dot-source：`.models`、`__future__`、`collections.abc`、`enum`、`hashlib`、`json`、`pydantic`、`re`、`typing`

### `product/backend/core/verification/permissions/coverage.py`

[打开源码](../../../../../../product/backend/core/verification/permissions/coverage.py) · Python AST；作用域内import不表示每次调用均执行。

- `class CoverageGapCode`
- `class EliminatedReason`
- `class CoverageStatus`
- `class RetentionReason`
- `class PermissionMutationCase`
- `PermissionMutationCase.validate_shape(self) -> PermissionMutationCase`
- `class CoverageRecord`
- `CoverageRecord.validate_target(self) -> CoverageRecord`
- `class CoverageGap`
- `CoverageGap.validate_target(self) -> CoverageGap`
- `class EliminatedCandidate`
- `class PermissionMutationPlan`
- `PermissionMutationPlan.validate_counts(self) -> PermissionMutationPlan`
- `build_permission_coverage_plan(contract, engine_version, seed, case_budget, available_subject_ids, available_resource_ids, available_observations, max_relation_depth) -> PermissionMutationPlan`

静态import / dot-source：`.contract`、`.models`、`__future__`、`collections`、`dataclasses`、`enum`、`pydantic`、`typing`

### `product/backend/core/verification/permissions/evaluation.py`

[打开源码](../../../../../../product/backend/core/verification/permissions/evaluation.py) · Python AST；作用域内import不表示每次调用均执行。

- `class PermissionEvaluationModel`
- `class CaseDecisionInput`
- `CaseDecisionInput.validate_case_input(self) -> CaseDecisionInput`
- `class PermissionEvaluationReasonCode`
- `evaluate_permission_case(input_data) -> tuple[CaseVerdict, tuple[str, ...]]`

静态import / dot-source：`.models`、`__future__`、`enum`、`product.backend.core.lifecycle`、`product.backend.core.verification.differential`、`product.backend.core.verification.facts`、`product.backend.core.verification.permissions.coverage`、`pydantic`

### `product/backend/core/verification/permissions/models.py`

[打开源码](../../../../../../product/backend/core/verification/permissions/models.py) · Python AST；作用域内import不表示每次调用均执行。

- `_ID_PATTERN`
- `_TEXT_PATTERN`
- `_STATE_PATTERN`
- `_HEX_PATTERN`
- `_SECRET_OR_URL`
- `class PermissionModel`
- `class RelationType`
- `class SecurityEffectDefinition`
- `SecurityEffectDefinition.reject_forbidden_effect_text(cls, value, info) -> str &#124; None`
- `SecurityEffectDefinition.normalize_protected_fields(cls, values) -> tuple[str, ...]`
- `SecurityEffectDefinition.validate_effect(self) -> SecurityEffectDefinition`
- `class CoverageDimension`
- `class BatchAuthorizationMode`
- `class WorkflowTransition`
- `WorkflowTransition.normalize_allowed_from_states(cls, values) -> tuple[str, ...]`
- `class SubjectDefinition`
- `SubjectDefinition.reject_forbidden_text(cls, value, info) -> str &#124; None`
- `SubjectDefinition.normalize_roles(cls, values) -> tuple[str, ...]`
- `class ActionDefinition`
- `ActionDefinition.reject_forbidden_action_text(cls, value) -> str`
- `ActionDefinition.normalize_effect_ids(cls, values) -> tuple[str, ...]`
- `class ResourceDefinition`
- `ResourceDefinition.reject_forbidden_resource_text(cls, value, info) -> str &#124; None`
- `class RelationEndpoint`
- `RelationEndpoint.reject_forbidden_endpoint_text(cls, value) -> str`
- `class RelationFact`
- `RelationFact.reject_forbidden_relation_text(cls, value) -> str`
- `class PermissionContext`
- `PermissionContext.normalize_context_values(cls, values, info) -> tuple[str, ...]`
- `class PermissionRule`
- `PermissionRule.reject_forbidden_rule_text(cls, value, info) -> str`
- `PermissionRule.normalize_relation_path(cls, values) -> tuple[str, ...]`
- `PermissionRule.normalize_observations(cls, values) -> tuple[str, ...]`
- `PermissionRule.normalize_coverage_dimensions(cls, values) -> tuple[CoverageDimension, ...]`
- `class BatchResourceExpectation`
- `BatchResourceExpectation.validate_batch_relation_path(cls, values) -> tuple[str, ...]`
- `class BatchPermissionRule`
- `BatchPermissionRule.normalize_batch_observations(cls, values) -> tuple[str, ...]`
- `BatchPermissionRule.normalize_batch_dimensions(cls, values) -> tuple[CoverageDimension, ...]`
- `BatchPermissionRule.require_bulk_dimension(self) -> BatchPermissionRule`

静态import / dot-source：`__future__`、`collections.abc`、`enum`、`hashlib`、`json`、`product.backend.core.boundaries.semantics`、`pydantic`、`re`、`typing`

### `product/backend/core/verification/trace.py`

[打开源码](../../../../../../product/backend/core/verification/trace.py) · Python AST；作用域内import不表示每次调用均执行。

- `_PUBLIC_ID`
- `_SEMANTIC_KEY`
- `_REASON_CODE`
- `_INLINE_SECRET`
- `class TraceCorrelationKind`
- `class TraceAuthorizationDecision`
- `class TraceEventKind`
- `class TraceAuthorityScope`
- `TraceAuthorityScope.validate_scope(self) -> TraceAuthorityScope`
- `class TraceEvent`
- `TraceEvent.validate_event(self) -> TraceEvent`
- `class ExecutionTrace`
- `ExecutionTrace.validate_reason_codes(cls, values) -> tuple[str, ...]`
- `ExecutionTrace.validate_trace(self) -> ExecutionTrace`

静态import / dot-source：`__future__`、`enum`、`heapq`、`pydantic`、`re`、`typing`

<!-- GENERATED:END -->
