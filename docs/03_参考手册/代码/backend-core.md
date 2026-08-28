# 自动代码参考：后端 Core

> 生成区域只描述当前代码结构；职责与安全理由由模块参考和任务指南维护。

<!-- GENERATED:START -->

<!-- 此区域由 scripts/docs/generate.py 从 product/backend/core/ 读取。 -->

### `product/backend/core/application_understanding.py`
- `canonical_role_key(value) -> str`
- `candidate_id(kind, canonical_key) -> str`
- `class UnderstandingModel`
- `class CandidateDecision`
- `class CandidateOrigin`
- `class CandidateConfidence`
- `class ActionRiskHint`
- `class CandidateEvidence`
- `class RoleCandidate`
- `class ActionCandidate`
- `class ApplicationUnderstanding`
主要 import / dot-source：`__future__`, `enum`, `hashlib`, `product.backend.core.identifiers`, `pydantic`, `re`, `typing`

### `product/backend/core/contracts/analysis/assessment.py`
- `assess_contract(contract, candidates, source_issues, available_observations, unexecutable_rule_ids) -> ContractReviewAssessment`
主要 import / dot-source：`__future__`, `collections.abc`, `product.backend.core.contracts.analysis.canonical`, `product.backend.core.contracts.analysis.merge`, `product.backend.core.contracts.analysis.models`, `product.backend.core.contracts.models`

### `product/backend/core/contracts/analysis/canonical.py`
- `contract_analysis_sha256(value) -> str`
主要 import / dot-source：`__future__`, `collections.abc`, `enum`, `hashlib`, `json`, `product.backend.core.contracts.analysis.models`, `product.backend.core.contracts.models`, `pydantic`, `re`, `typing`

### `product/backend/core/contracts/analysis/diff.py`
- `diff_contract_versions(before, after) -> ContractVersionDiff`
主要 import / dot-source：`__future__`, `product.backend.core.contracts.analysis.canonical`, `product.backend.core.contracts.analysis.models`, `product.backend.core.contracts.models`, `product.backend.core.errors`

### `product/backend/core/contracts/analysis/drift.py`
- `class DriftType`
- `class VerifiedBehaviorFingerprint`
- `class DriftEntry`
- `class DriftReport`
- `build_drift_report(contract, requirements, requirement_candidates, available_rule_ids, capability_candidates, unexecutable_rule_ids, available_observations, accepted_behavior, current_behavior, analysis_issues) -> DriftReport`
主要 import / dot-source：`__future__`, `enum`, `product.backend.core.contracts.analysis.canonical`, `product.backend.core.contracts.analysis.models`, `product.backend.core.contracts.models`, `product.backend.core.errors`, `product.backend.core.identifiers`, `product.backend.core.verification.permissions`, `pydantic`, `typing`

### `product/backend/core/contracts/analysis/merge.py`
- `merge_candidates(candidates) -> CandidateMergeResult`
主要 import / dot-source：`__future__`, `collections.abc`, `product.backend.core.contracts.analysis.canonical`, `product.backend.core.contracts.analysis.models`, `product.backend.core.contracts.models`

### `product/backend/core/contracts/analysis/models.py`
- `class AnalysisModel`
- `class AnalysisSeverity`
- `class AnalysisReasonCode`
- `class AnalysisIssue`
- `class CandidateBatch`
- `class MergedCandidate`
- `class CandidateMergeResult`
- `class ContractReviewAssessment`
- `class RuleDiff`
- `class ProvenanceDelta`
- `class ContractVersionDiff`
主要 import / dot-source：`__future__`, `enum`, `product.backend.core.contracts.models`, `product.backend.core.identifiers`, `product.backend.core.lifecycle`, `product.backend.core.verification.permissions`, `pydantic`, `typing`

### `product/backend/core/contracts/analysis/sources/fastapi_ast.py`
- `parse_fastapi_source_candidates(project_id, source, source_locator, content_sha256) -> CandidateBatch`
主要 import / dot-source：`__future__`, `ast`, `hashlib`, `product.backend.core.contracts.analysis.canonical`, `product.backend.core.contracts.analysis.models`, `product.backend.core.contracts.analysis.sources.openapi`, `product.backend.core.contracts.models`, `product.backend.core.http_routes`

### `product/backend/core/contracts/analysis/sources/openapi.py`
- `_SENSITIVE_FIELD`
- `_OPENAPI_MAX_BYTES`
- `build_openapi_candidates(project_id, document, source_locator, max_bytes) -> CandidateBatch`
主要 import / dot-source：`__future__`, `collections.abc`, `json`, `product.backend.core.contracts.analysis.canonical`, `product.backend.core.contracts.analysis.models`, `product.backend.core.contracts.models`, `product.backend.core.http_routes`, `re`, `typing`

### `product/backend/core/contracts/analysis/sources/requirement.py`
- `parse_requirement(requirement) -> CandidateBatch`
主要 import / dot-source：`__future__`, `product.backend.core.contracts.analysis.canonical`, `product.backend.core.contracts.analysis.models`, `product.backend.core.contracts.models`, `pydantic`, `shlex`

### `product/backend/core/contracts/execution_binding.py`
- `resolve_execution_contract(record, governed) -> PermissionContract`
主要 import / dot-source：`__future__`, `product.backend.core.errors`, `product.backend.core.lifecycle`, `product.backend.core.verification.permissions`, `typing`

### `product/backend/core/contracts/lifecycle.py`
- `_CONTRACT_TRANSITIONS`
- `transition_contract_version(contract, target, actor, occurred_at_us) -> ContractVersion`
- `revise_contract_version(active, snapshot, provenance, actor, occurred_at_us) -> ContractVersion`
主要 import / dot-source：`product.backend.core.contracts.models`, `product.backend.core.errors`, `product.backend.core.lifecycle`, `product.backend.core.verification.permissions`

### `product/backend/core/contracts/models.py`
- `class ContractSourceType`
- `class ContractAuditAction`
- `class GovernanceModel`
- `class SourceReference`
- `class Requirement`
- `class LLMGenerationMetadata`
- `class CandidateRiskKind`
- `class CandidateSuggestion`
- `class ContractCandidate`
- `class ContractProvenance`
- `class ContractAuditEntry`
- `class ContractVersion`
主要 import / dot-source：`__future__`, `enum`, `product.backend.core.identifiers`, `product.backend.core.lifecycle`, `product.backend.core.verification.permissions`, `pydantic`, `typing`

### `product/backend/core/errors.py`
- `class ErrorCode`
- `class LLMWireErrorCode`
- `LLM_WIRE_TO_INTERNAL`
- `class JiejianError`
主要 import / dot-source：`__future__`, `enum`, `product.backend.core.redaction`, `typing`

### `product/backend/core/http_routes.py`
- `HTTP_METHODS`
- `safe_route_path(path) -> bool`
主要 import / dot-source：`__future__`

### `product/backend/core/identifiers.py`
- `PROJECT_ID_PATTERN`
- `LONG_SLUG_ID_PATTERN`
- `RUN_ID_PATTERN`
- `JOB_ID_PATTERN`
- `RECORDING_ID_PATTERN`
- `TEST_IDENTITY_ID_PATTERN`
- `EVIDENCE_ID_PATTERN`
- `SHA256_PATTERN`
- `REQUIREMENT_ID_PATTERN`
- `CANDIDATE_ID_PATTERN`

### `product/backend/core/lifecycle.py`
- `class ProjectStatus`
- `class ContractStatus`
- `class RunLifecycle`
- `class RunVerdict`
- `class CaseLifecycle`
- `class CaseVerdict`
- `class JobState`
- `class DomainModel`
主要 import / dot-source：`__future__`, `enum`, `pydantic`, `typing`

### `product/backend/core/permission_intent.py`
- `_ACTION_ID_PATTERN`
- `_ROLE_ID_PATTERN`
- `_INTENT_ID_PATTERN`
- `class PermissionIntentModel`
- `class PermissionIntentRelation`
- `permission_intent_sha256(payload) -> str`
- `class PermissionIntent`
主要 import / dot-source：`__future__`, `enum`, `hashlib`, `json`, `product.backend.core.identifiers`, `product.backend.core.verification.permissions`, `pydantic`, `typing`

### `product/backend/core/recording.py`
- `_REASON_CODE`
- `class RecordingState`
- `class RecordingTerminalState`
- `class RecordingReasonCode`
- `class RecordingModel`
- `class RecordingStateEvent`
- `class Recording`
- `_TRANSITIONS`
- `transition_recording_state(recording, target, operator, occurred_at_us, reason_code, pending_terminal_state) -> Recording`
主要 import / dot-source：`__future__`, `enum`, `product.backend.core.errors`, `product.backend.core.identifiers`, `pydantic`, `re`, `typing`

### `product/backend/core/redaction.py`
- `REDACTED`
- `_SENSITIVE_KEY`
- `_BEARER`
- `_ASSIGNMENT`
- `redact(value) -> Any`
- `redact_known_secrets(value, secrets) -> Any`
主要 import / dot-source：`__future__`, `collections.abc`, `re`, `typing`

### `product/backend/core/reporting.py`
- `_REPORT_CSS`
- `render_json(report) -> bytes`
- `render_html(report) -> bytes`
- `render_sarif(report) -> bytes`
- `render_junit(report) -> bytes`
- `render_format(report, output_format) -> bytes`
主要 import / dot-source：`__future__`, `datetime`, `html`, `json`, `product.protocols.report`, `xml.sax.saxutils`

### `product/backend/core/test_identity.py`
- `_ROLE_CANDIDATE_ID_PATTERN`
- `_SECRET_REF_PATTERN`
- `class TestIdentityModel`
- `class TestIdentityAuthMethod`
- `class TestIdentityCookie`
- `class TestIdentity`
主要 import / dot-source：`__future__`, `enum`, `product.backend.core.identifiers`, `pydantic`

### `product/backend/core/test_setup.py`
- `_ACTION_ID_PATTERN`
- `_TEST_RESOURCE_ID_PATTERN`
- `_OBSERVATION_BINDING_ID_PATTERN`
- `_RECOVERY_BINDING_ID_PATTERN`
- `_EFFECT_CONFIRMATION_ID_PATTERN`
- `_FLOW_ID_PATTERN`
- `_STEP_ID_PATTERN`
- `_RESOURCE_VALUE`
- `_RESOURCE_TYPE`
- `_PROJECTION_PATH`
- `_UNSAFE_TEXT`
- `class TestSetupModel`
- `class TestResourceRelation`
- `class ResourceValueConsumer`
- `class ObservationBindingKind`
- `class RecoveryBindingKind`
- `test_setup_sha256(kind, payload) -> str`
- `class TestResource`
- `class ObservationBinding`
- `class RecoveryBinding`
- `class SecurityEffectConfirmation`
- `class ActionSafetySetup`
主要 import / dot-source：`__future__`, `enum`, `hashlib`, `json`, `product.backend.core.identifiers`, `product.backend.core.redaction`, `product.backend.core.verification.permissions`, `pydantic`, `re`, `typing`, `urllib.parse`

### `product/backend/core/verification/behavior_differential.py`
- `class BehaviorDifferentialModel`
- `class EvidenceSufficiency`
- `class BehaviorDifferenceKind`
- `class NormalizedSecurityEffect`
- `class BehaviorSnapshot`
- `class BehaviorDifference`
- `class BehaviorDifferentialResult`
- `normalize_evidence_behavior(evidence, contract_fingerprint, workflow_fingerprint, baseline_fingerprint) -> BehaviorSnapshot`
- `compare_behavior_snapshots(before, after) -> BehaviorDifferentialResult`
主要 import / dot-source：`__future__`, `enum`, `product.backend.core.lifecycle`, `product.backend.core.verification.facts`, `product.backend.core.verification.permissions`, `product.protocols.runner`, `pydantic`, `typing`

### `product/backend/core/verification/collision.py`
- `class CollisionModel`
- `class CollisionAnomaly`
- `class CollisionClue`
- `class CollisionBudget`
- `class CollisionObservation`
- `class CollisionTrial`
- `class CollisionExperimentResult`
- `classify_collision_trials(sequential_semantics_valid, expected_repetitions, trials) -> CollisionExperimentResult`
主要 import / dot-source：`__future__`, `collections`, `enum`, `product.backend.core.lifecycle`, `pydantic`, `typing`

### `product/backend/core/verification/differential.py`
- `class TwinPlanGapCode`
- `class TwinExecutionRole`
- `class PermissionMutationDescriptor`
- `class TwinInvariantSpecification`
- `class PermissionTwin`
- `class TwinPlanGap`
- `class DifferentialExperimentPlan`
- `build_differential_experiment_plan(contract, coverage, workflow_fingerprints, effect_fingerprints, observer_fingerprint, baseline_fingerprints, normalization_version) -> DifferentialExperimentPlan`
主要 import / dot-source：`__future__`, `collections.abc`, `enum`, `product.backend.core.verification.permissions`, `product.backend.core.verification.permissions.coverage`, `pydantic`, `typing`

### `product/backend/core/verification/facts.py`
- `_ID`
- `_HEX`
- `_REASON`
- `class FactModel`
- `class TargetType`
- `class ExecutionOutcome`
- `class ObservedEffect`
- `class TemporalClosure`
- `class ExecutionFact`
- `class ObservationFact`
- `class DisclosureProof`
- `class SecurityEffectFact`
- `aggregate_security_effect(effect, resource_id, required_requirement_ids, corroborating_requirement_ids, observations, baseline_integrity, disclosure_proof) -> SecurityEffectFact`
主要 import / dot-source：`__future__`, `enum`, `product.backend.core.verification.permissions`, `pydantic`, `re`, `typing`

### `product/backend/core/verification/findings.py`
- `_FINDING_ID`
- `_OCCURRENCE_ID`
- `_SAFE_TEXT`
- `_SECRET_TEXT`
- `class FindingIdentity`
- `class FindingInput`
- `class OccurrenceStatus`
- `class Finding`
- `class FindingOccurrence`
- `occurrence_id_for(finding_id, run_id) -> str`
主要 import / dot-source：`__future__`, `enum`, `hashlib`, `json`, `product.backend.core.identifiers`, `product.backend.core.lifecycle`, `pydantic`, `re`, `typing`

### `product/backend/core/verification/gating.py`
- `_TOKEN`
- `_ACTOR`
- `_SECRET`
- `_SEVERITY_ORDER`
- `gate_canonical_sha256(value) -> str`
- `class GateDecision`
- `class BaselineFindingRef`
- `class RegressionBaseline`
- `class GateFinding`
- `class GateFacts`
- `class GatePolicy`
- `class GateReason`
- `class GateResult`
- `baseline_id_for(project_id, run_id, request_snapshot_sha256, coverage_digest) -> str`
- `gate_input_hash(baseline_id, facts, policy) -> str`
- `gate_result_id_for(baseline_id, run_id, policy_version, input_hash) -> str`
- `evaluate_gate(baseline, facts, policy) -> GateResult`
主要 import / dot-source：`__future__`, `collections.abc`, `enum`, `hashlib`, `json`, `product.backend.core.lifecycle`, `pydantic`, `re`, `typing`

### `product/backend/core/verification/permissions/__init__.py`
- `_LAZY_EXPORTS`
主要 import / dot-source：`.contract`, `.models`, `importlib`

### `product/backend/core/verification/permissions/contract.py`
- `_ID_PATTERN`
- `_TEXT_PATTERN`
- `_STATE_PATTERN`
- `_HEX_PATTERN`
- `_SECRET_OR_URL`
- `class PermissionContract`
- `parse_permission_contract(raw) -> PermissionContract`
- `class NormalizedPermissionCase`
- `class NormalizedPermissionPlan`
- `canonical_json_bytes(value) -> bytes`
- `permission_model_sha256(value) -> str`
- `compile_permission_plan(contract, engine_version, seed) -> NormalizedPermissionPlan`
主要 import / dot-source：`.models`, `__future__`, `collections.abc`, `enum`, `hashlib`, `json`, `pydantic`, `re`, `typing`

### `product/backend/core/verification/permissions/coverage.py`
- `class CoverageGapCode`
- `class EliminatedReason`
- `class CoverageStatus`
- `class RetentionReason`
- `class PermissionMutationCase`
- `class CoverageRecord`
- `class CoverageGap`
- `class EliminatedCandidate`
- `class PermissionMutationPlan`
- `build_permission_coverage_plan(contract, engine_version, seed, case_budget, available_subject_ids, available_resource_ids, available_observations, max_relation_depth) -> PermissionMutationPlan`
主要 import / dot-source：`.contract`, `.models`, `__future__`, `collections`, `dataclasses`, `enum`, `pydantic`, `typing`

### `product/backend/core/verification/permissions/evaluation.py`
- `class PermissionEvaluationModel`
- `class CaseDecisionInput`
- `class PermissionEvaluationReasonCode`
- `evaluate_permission_case(input_data) -> tuple[CaseVerdict, tuple[str, ...]]`
主要 import / dot-source：`.models`, `__future__`, `enum`, `product.backend.core.lifecycle`, `product.backend.core.verification.differential`, `product.backend.core.verification.facts`, `product.backend.core.verification.permissions.coverage`, `pydantic`

### `product/backend/core/verification/permissions/models.py`
- `_ID_PATTERN`
- `_TEXT_PATTERN`
- `_STATE_PATTERN`
- `_HEX_PATTERN`
- `_SECRET_OR_URL`
- `class PermissionModel`
- `class RelationType`
- `class PermissionExpectation`
- `class SecurityEffectKind`
- `class SecurityEffectDefinition`
- `class CoverageDimension`
- `class BatchAuthorizationMode`
- `class WorkflowTransition`
- `class SubjectDefinition`
- `class ActionDefinition`
- `class ResourceDefinition`
- `class RelationEndpoint`
- `class RelationFact`
- `class PermissionContext`
- `class PermissionRule`
- `class BatchResourceExpectation`
- `class BatchPermissionRule`
主要 import / dot-source：`__future__`, `collections.abc`, `enum`, `hashlib`, `json`, `pydantic`, `re`, `typing`

### `product/backend/core/verification/sql_trace.py`
- `class SqlTraceModel`
- `sql_trace_advisory_sha256(value) -> str`
- `class SqlStatementKind`
- `class SqlTraceEvent`
- `class SqlTraceAdvisory`
主要 import / dot-source：`__future__`, `enum`, `product.backend.core.verification.permissions`, `pydantic`, `typing`

<!-- GENERATED:END -->
