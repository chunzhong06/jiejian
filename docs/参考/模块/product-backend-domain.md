# product/backend/domain 模块

<!-- generated:modules -->

[返回总索引](../模块索引.md)

按目录定位后读取对应小节；每个文件有独立标题，源码链接用于核对声明与直接消费者。行数和公开声明由静态提取，不表示运行验收。

按目录定位：[根目录](#根目录)（9 个文件）、[applications](#applications)（2 个文件）、[boundaries](#boundaries)（11 个文件）、[changes](#changes)（2 个文件）、[checks](#checks)（6 个文件）、[identities](#identities)（2 个文件）、[preparation](#preparation)（4 个文件）、[recording](#recording)（2 个文件）、[reports](#reports)（2 个文件）、[verification](#verification)（8 个文件）、[verification/breakpoints](#verificationbreakpoints)（5 个文件）、[verification/permissions](#verificationpermissions)（4 个文件）。

## 根目录

### __init__.py

[源码](../../../product/backend/domain/__init__.py)（1 行）。公开声明：包、内部机制或样式。

### canonical.py

[源码](../../../product/backend/domain/canonical.py)（15 行）。公开声明：`canonical_sha256`。

### development.py

[源码](../../../product/backend/domain/development.py)（130 行）。公开声明：`DevelopmentTask`、`DevelopmentContext`、`DevelopmentAcceptance`、`DevelopmentDelivery`、`DevelopmentReceipt`、`RuntimeActivationReceipt`、`NodeRuntimeActivationReceipt`。

### errors.py

[源码](../../../product/backend/domain/errors.py)（219 行）。公开声明：`ErrorCode`、`JiejianError`。

### failures.py

[源码](../../../product/backend/domain/failures.py)（37 行）。公开声明：`ErrorKind`、`failure_kind`、`failure_recovery`。

### http_routes.py

[源码](../../../product/backend/domain/http_routes.py)（18 行）。公开声明：`safe_route_path`。

### identifiers.py

[源码](../../../product/backend/domain/identifiers.py)（12 行）。公开声明：包、内部机制或样式。

### lifecycle.py

[源码](../../../product/backend/domain/lifecycle.py)（57 行）。公开声明：`ProjectStatus`、`ContractStatus`、`RunLifecycle`、`RunVerdict`、`CaseVerdict`、`JobState`、`DomainModel`。

### redaction.py

[源码](../../../product/backend/domain/redaction.py)（68 行）。公开声明：`is_sensitive_key`、`redact`、`redact_known_secrets`。

## applications

### applications/__init__.py

[源码](../../../product/backend/domain/applications/__init__.py)（1 行）。公开声明：包、内部机制或样式。

### applications/models.py

[源码](../../../product/backend/domain/applications/models.py)（183 行）。公开声明：`canonical_role_key`、`candidate_id`、`UnderstandingModel`、`CandidateDecision`、`CandidateOrigin`、`CandidateConfidence`、`ActionRiskHint`、`CandidateSelection`等。

## boundaries

### boundaries/__init__.py

[源码](../../../product/backend/domain/boundaries/__init__.py)（1 行）。公开声明：包、内部机制或样式。

### boundaries/approval.py

[源码](../../../product/backend/domain/boundaries/approval.py)（42 行）。公开声明：`HumanApprovalChannel`、`HumanApproval`。

### boundaries/candidate_reviews.py

[源码](../../../product/backend/domain/boundaries/candidate_reviews.py)（236 行）。公开声明：`BoundaryReviewCommand`、`BoundaryReviewRecord`、`boundary_review_items`、`BoundaryReviewGap`、`ReviewDependencies`、`ReviewSuggestion`、`ContextualBoundaryReviewCommand`、`SavedReviewSuggestion`等。

### boundaries/candidate_scenarios.py

[源码](../../../product/backend/domain/boundaries/candidate_scenarios.py)（157 行）。公开声明：`normalized_rule_text`、`RuleScenarioOption`、`RuleScenarioInput`、`RuleScenario`、`freeze_scenario`、`scenario_dependencies`、`RuleCandidateDecide`、`RuleCandidateDecision`等。

### boundaries/candidate_scope.py

[源码](../../../product/backend/domain/boundaries/candidate_scope.py)（220 行）。公开声明：`RequirementSource`、`ScopeDecisionCommand`、`ScopeDecision`、`ScopeBatchChoice`、`ScopeBatchCommand`、`ScopeReference`、`scope_decision_fingerprint`、`scope_items`等。

### boundaries/entities.py

[源码](../../../product/backend/domain/boundaries/entities.py)（372 行）。公开声明：`BoundaryModel`、`BusinessRevisionState`、`BusinessActionOperationKind`、`ImplementationBindingStatus`、`ImplementationCandidateSnapshot`、`boundary_sha256`、`trimmed_text`、`BusinessEffectDefinition`等。

### boundaries/permissions.py

[源码](../../../product/backend/domain/boundaries/permissions.py)（146 行）。公开声明：`PermissionIntentModel`、`PermissionIntentRelation`、`PermissionIntentEffectiveState`、`permission_relation_consistent`、`permission_intent_sha256`、`PermissionIntentSemantic`、`PermissionIntentRevision`、`ProjectPolicyState`。

### boundaries/proposals.py

[源码](../../../product/backend/domain/boundaries/proposals.py)（329 行）。公开声明：`ProposalWriteMode`、`ProposalCandidateKind`、`BoundaryDecisionKind`、`CandidateSourceSnapshot`、`BoundarySourceSnapshot`、`ProposedEffectItem`、`ProposedActorItem`、`ProposedActionItem`等。

### boundaries/rule_candidates.py

[源码](../../../product/backend/domain/boundaries/rule_candidates.py)（243 行）。公开声明：`RuleExample`、`CandidateContentFields`、`RuleCandidateContentInput`、`RuleCandidateContent`、`freeze_candidate_content`、`ScopedCandidateContentInput`、`ScopedCandidateContent`、`RuleCandidateRevision`等。

### boundaries/rule_preview.py

[源码](../../../product/backend/domain/boundaries/rule_preview.py)（41 行）。公开声明：`ApprovedRuleReference`、`ApprovedRuleSet`、`ProposalRuleSet`、`CandidateRuleSet`、`RuleSituation`、`RulePreviewCommand`。

### boundaries/semantics.py

[源码](../../../product/backend/domain/boundaries/semantics.py)（21 行）。公开声明：`PermissionExpectation`、`BusinessEffectKind`。

## changes

### changes/__init__.py

[源码](../../../product/backend/domain/changes/__init__.py)（1 行）。公开声明：包、内部机制或样式。

### changes/models.py

[源码](../../../product/backend/domain/changes/models.py)（387 行）。公开声明：`SourceChangeModel`、`normalize_relative_source_path`、`SourceFileFingerprint`、`source_fingerprint`、`source_snapshot_id`、`SourceRevisionSnapshot`、`ChangeManifest`、`SourceChangeSet`等。

## checks

### checks/__init__.py

[源码](../../../product/backend/domain/checks/__init__.py)（1 行）。公开声明：包、内部机制或样式。

### checks/batch_requests.py

[源码](../../../product/backend/domain/checks/batch_requests.py)（56 行）。公开声明：`batch_request`。

### checks/plan.py

[源码](../../../product/backend/domain/checks/plan.py)（274 行）。公开声明：`RegisteredEffectProofCapability`、`PreparedIdentityAssignment`、`CheckPlanGap`、`CheckCase`、`CheckTwin`、`ActionCheckPlan`、`ProjectCheckPlan`、`PreparedActionInput`等。

### checks/repair.py

[源码](../../../product/backend/domain/checks/repair.py)（289 行）。公开声明：`CurrentRepairReference`、`RepairCaseIdentity`、`repair_case_identity`、`repair_evidence_standards`、`RepairCaseRequirement`、`CurrentRepairContract`、`repair_context`、`current_request_permissions`等。

### checks/scenarios.py

[源码](../../../product/backend/domain/checks/scenarios.py)（125 行）。公开声明：`scenario_http_budget`、`compile_business_scenario`。

### checks/selection.py

[源码](../../../product/backend/domain/checks/selection.py)（65 行）。公开声明：`permission_key`、`resolve_selected_permissions`、`select_assurance`、`select_action_input`、`references`。

## identities

### identities/__init__.py

[源码](../../../product/backend/domain/identities/__init__.py)（1 行）。公开声明：包、内部机制或样式。

### identities/models.py

[源码](../../../product/backend/domain/identities/models.py)（177 行）。公开声明：`TestIdentityModel`、`TestIdentityAuthMethod`、`IdentityVerificationConfig`、`AuthenticationProfile`、`IdentityVerificationSnapshot`、`TestIdentityCookie`、`TestIdentity`、`identity_source_fingerprint`。

## preparation

### preparation/__init__.py

[源码](../../../product/backend/domain/preparation/__init__.py)（1 行）。公开声明：包、内部机制或样式。

### preparation/bindings.py

[源码](../../../product/backend/domain/preparation/bindings.py)（270 行）。公开声明：`ResourceInjectionKind`、`ActionEvidenceKind`、`ResourceInjection`、`RecordedRequestTemplate`、`contains_resource_slot`、`RegisteredObserverReference`、`ActionExecutionBinding`、`ActionResourceBinding`等。

### preparation/requirements.py

[源码](../../../product/backend/domain/preparation/requirements.py)（376 行）。公开声明：`AllocationMode`、`AssuranceStatus`、`PermissionIdentity`、`IdentityRequirementSlot`、`PermissionIdentitySlots`、`IdentityRequirementPlan`、`ActionResourceRequirement`、`EffectEvidenceRequirement`等。

### preparation/suggestions.py

[源码](../../../product/backend/domain/preparation/suggestions.py)（188 行）。公开声明：`ApprovedMaterialTarget`、`CandidateMaterialTarget`、`SuggestionSource`、`IdentitySuggestion`、`ExecutionSuggestion`、`ResourceFieldRequirement`、`ResourceSuggestion`、`EvidenceSuggestion`等。

## recording

### recording/__init__.py

[源码](../../../product/backend/domain/recording/__init__.py)（1 行）。公开声明：包、内部机制或样式。

### recording/models.py

[源码](../../../product/backend/domain/recording/models.py)（268 行）。公开声明：`RecordingState`、`RecordingPurpose`、`RecordingTerminalState`、`RecordingReasonCode`、`RecordingModel`、`RecordingStateEvent`、`Recording`、`transition_recording_state`。

## reports

### reports/__init__.py

[源码](../../../product/backend/domain/reports/__init__.py)（1 行）。公开声明：包、内部机制或样式。

### reports/repair.py

[源码](../../../product/backend/domain/reports/repair.py)（299 行）。公开声明：`RepairModel`、`RepairContractReference`、`RepairIntentIdentity`、`RepairAllowControlIdentity`、`RepairRegressionControlIdentity`、`RepairEvidenceStandard`、`RepairContract`、`RepairRequirementView`等。

## verification

### verification/__init__.py

[源码](../../../product/backend/domain/verification/__init__.py)（1 行）。公开声明：包、内部机制或样式。

### verification/async_progress.py

[源码](../../../product/backend/domain/verification/async_progress.py)（11 行）。公开声明：`task_transition`。

### verification/business_facts.py

[源码](../../../product/backend/domain/verification/business_facts.py)（148 行）。公开声明：`verified_principals`、`reduce_creation_facts`、`reduce_record_facts`、`reduce_disclosure_facts`、`reduce_file_facts`。

### verification/checks.py

[源码](../../../product/backend/domain/verification/checks.py)（181 行）。公开声明：`CheckEffectFact`、`CheckProofObservation`、`project_check_effect_facts`、`CheckDecisionInput`、`CheckDecision`、`evaluate_check_case`、`aggregate_check_verdict`、`resolved_control_verdict`。

### verification/continuity.py

[源码](../../../product/backend/domain/verification/continuity.py)（261 行）。公开声明：`AuthorizationContinuityState`、`AuthorizationEffectReference`、`AuthorizationContinuityAssessment`、`assess_check_authorization_continuity`、`assess_authorization_continuity`。

### verification/differential.py

[源码](../../../product/backend/domain/verification/differential.py)（229 行）。公开声明：`TwinPlanGapCode`、`TwinExecutionRole`、`PermissionMutationDescriptor`、`TwinInvariantSpecification`、`PermissionTwin`、`TwinPlanGap`、`DifferentialExperimentPlan`、`build_differential_experiment_plan`。

### verification/facts.py

[源码](../../../product/backend/domain/verification/facts.py)（244 行）。公开声明：`FactModel`、`TargetType`、`ExecutionOutcome`、`ObservedEffect`、`TemporalClosure`、`ExecutionFact`、`ObservationFact`、`DisclosureProof`等。

### verification/trace.py

[源码](../../../product/backend/domain/verification/trace.py)（230 行）。公开声明：`TraceCorrelationKind`、`TraceAuthorizationDecision`、`TraceEventKind`、`TraceAuthorityScope`、`TraceEvent`、`ExecutionTrace`。

## verification/breakpoints

### verification/breakpoints/__init__.py

[源码](../../../product/backend/domain/verification/breakpoints/__init__.py)（5 行）。公开声明：包、内部机制或样式。

### verification/breakpoints/causality.py

[源码](../../../product/backend/domain/verification/breakpoints/causality.py)（441 行）。公开声明：包、内部机制或样式。

### verification/breakpoints/graph.py

[源码](../../../product/backend/domain/verification/breakpoints/graph.py)（122 行）。公开声明：包、内部机制或样式。

### verification/breakpoints/locator.py

[源码](../../../product/backend/domain/verification/breakpoints/locator.py)（327 行）。公开声明：`BreakpointLocator`。

### verification/breakpoints/models.py

[源码](../../../product/backend/domain/verification/breakpoints/models.py)（150 行）。公开声明：`BreakpointType`、`BreakpointPrecision`、`BreakpointResult`。

## verification/permissions

### verification/permissions/__init__.py

[源码](../../../product/backend/domain/verification/permissions/__init__.py)（71 行）。公开声明：包、内部机制或样式。

### verification/permissions/contract.py

[源码](../../../product/backend/domain/verification/permissions/contract.py)（542 行）。公开声明：`PermissionContract`、`parse_permission_contract`、`NormalizedPermissionCase`、`NormalizedPermissionPlan`、`canonical_json_bytes`、`permission_model_sha256`、`compile_permission_plan`。

### verification/permissions/coverage.py

[源码](../../../product/backend/domain/verification/permissions/coverage.py)（639 行）。公开声明：`CoverageGapCode`、`EliminatedReason`、`CoverageStatus`、`RetentionReason`、`PermissionMutationCase`、`CoverageRecord`、`CoverageGap`、`EliminatedCandidate`等。

### verification/permissions/models.py

[源码](../../../product/backend/domain/verification/permissions/models.py)（314 行）。公开声明：`PermissionModel`、`RelationType`、`SecurityEffectDefinition`、`CoverageDimension`、`BatchAuthorizationMode`、`WorkflowTransition`、`sorted_unique_values`、`validate_intent_text`等。
