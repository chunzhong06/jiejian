# product/backend/domain 模块

<!-- generated:modules -->

[返回总索引](../模块索引.md)

| 文件 | 行数 | 公开声明 |
| --- | ---: | --- |
| [product/backend/domain/__init__.py](../../../product/backend/domain/__init__.py) | 1 | 包、内部机制或样式 |
| [product/backend/domain/applications/__init__.py](../../../product/backend/domain/applications/__init__.py) | 1 | 包、内部机制或样式 |
| [product/backend/domain/applications/models.py](../../../product/backend/domain/applications/models.py) | 183 | canonical_role_key、candidate_id、UnderstandingModel、CandidateDecision、CandidateOrigin、CandidateConfidence、ActionRiskHint、CandidateSelection等 |
| [product/backend/domain/boundaries/__init__.py](../../../product/backend/domain/boundaries/__init__.py) | 1 | 包、内部机制或样式 |
| [product/backend/domain/boundaries/approval.py](../../../product/backend/domain/boundaries/approval.py) | 42 | HumanApprovalChannel、HumanApproval |
| [product/backend/domain/boundaries/candidate_reviews.py](../../../product/backend/domain/boundaries/candidate_reviews.py) | 236 | BoundaryReviewCommand、BoundaryReviewRecord、boundary_review_items、BoundaryReviewGap、ReviewDependencies、ReviewSuggestion、ContextualBoundaryReviewCommand、SavedReviewSuggestion等 |
| [product/backend/domain/boundaries/candidate_scenarios.py](../../../product/backend/domain/boundaries/candidate_scenarios.py) | 157 | normalized_rule_text、RuleScenarioOption、RuleScenarioInput、RuleScenario、freeze_scenario、scenario_dependencies、RuleCandidateDecide、RuleCandidateDecision等 |
| [product/backend/domain/boundaries/candidate_scope.py](../../../product/backend/domain/boundaries/candidate_scope.py) | 220 | RequirementSource、ScopeDecisionCommand、ScopeDecision、ScopeBatchChoice、ScopeBatchCommand、ScopeReference、scope_decision_fingerprint、scope_items等 |
| [product/backend/domain/boundaries/entities.py](../../../product/backend/domain/boundaries/entities.py) | 374 | BoundaryModel、BusinessRevisionState、BusinessActionOperationKind、ImplementationBindingStatus、ImplementationCandidateSnapshot、boundary_sha256、BusinessEffectDefinition、BusinessActor等 |
| [product/backend/domain/boundaries/permissions.py](../../../product/backend/domain/boundaries/permissions.py) | 146 | PermissionIntentModel、PermissionIntentRelation、PermissionIntentEffectiveState、permission_relation_consistent、permission_intent_sha256、PermissionIntentSemantic、PermissionIntentRevision、ProjectPolicyState |
| [product/backend/domain/boundaries/proposals.py](../../../product/backend/domain/boundaries/proposals.py) | 329 | ProposalWriteMode、ProposalCandidateKind、BoundaryDecisionKind、CandidateSourceSnapshot、BoundarySourceSnapshot、ProposedEffectItem、ProposedActorItem、ProposedActionItem等 |
| [product/backend/domain/boundaries/rule_candidates.py](../../../product/backend/domain/boundaries/rule_candidates.py) | 243 | RuleExample、CandidateContentFields、RuleCandidateContentInput、RuleCandidateContent、freeze_candidate_content、ScopedCandidateContentInput、ScopedCandidateContent、RuleCandidateRevision等 |
| [product/backend/domain/boundaries/rule_preview.py](../../../product/backend/domain/boundaries/rule_preview.py) | 41 | ApprovedRuleReference、ApprovedRuleSet、ProposalRuleSet、CandidateRuleSet、RuleSituation、RulePreviewCommand |
| [product/backend/domain/boundaries/semantics.py](../../../product/backend/domain/boundaries/semantics.py) | 21 | PermissionExpectation、BusinessEffectKind |
| [product/backend/domain/changes/__init__.py](../../../product/backend/domain/changes/__init__.py) | 1 | 包、内部机制或样式 |
| [product/backend/domain/changes/models.py](../../../product/backend/domain/changes/models.py) | 396 | SourceChangeModel、normalize_relative_source_path、SourceFileFingerprint、source_fingerprint、source_snapshot_id、SourceRevisionSnapshot、ChangeManifest、SourceChangeSet等 |
| [product/backend/domain/checks/__init__.py](../../../product/backend/domain/checks/__init__.py) | 1 | 包、内部机制或样式 |
| [product/backend/domain/checks/plan.py](../../../product/backend/domain/checks/plan.py) | 272 | RegisteredEffectProofCapability、PreparedIdentityAssignment、CheckPlanGap、CheckCase、CheckTwin、ActionCheckPlan、ProjectCheckPlan、PreparedActionInput等 |
| [product/backend/domain/checks/repair.py](../../../product/backend/domain/checks/repair.py) | 274 | CurrentRepairReference、RepairCaseIdentity、repair_case_identity、repair_evidence_standards、RepairCaseRequirement、CurrentRepairContract、repair_context、current_request_permissions等 |
| [product/backend/domain/checks/selection.py](../../../product/backend/domain/checks/selection.py) | 65 | permission_key、resolve_selected_permissions、select_assurance、select_action_input、references |
| [product/backend/domain/contracts/__init__.py](../../../product/backend/domain/contracts/__init__.py) | 1 | 包、内部机制或样式 |
| [product/backend/domain/contracts/models.py](../../../product/backend/domain/contracts/models.py) | 127 | ContractSourceType、ContractAuditAction、GovernanceModel、SourceReference、ContractProvenance、ContractAuditEntry、ContractVersion |
| [product/backend/domain/development.py](../../../product/backend/domain/development.py) | 130 | DevelopmentTask、DevelopmentContext、DevelopmentAcceptance、DevelopmentDelivery、DevelopmentReceipt、RuntimeActivationReceipt、NodeRuntimeActivationReceipt |
| [product/backend/domain/errors.py](../../../product/backend/domain/errors.py) | 206 | ErrorCode、JiejianError |
| [product/backend/domain/http_routes.py](../../../product/backend/domain/http_routes.py) | 18 | safe_route_path |
| [product/backend/domain/identifiers.py](../../../product/backend/domain/identifiers.py) | 12 | 包、内部机制或样式 |
| [product/backend/domain/identities/__init__.py](../../../product/backend/domain/identities/__init__.py) | 1 | 包、内部机制或样式 |
| [product/backend/domain/identities/models.py](../../../product/backend/domain/identities/models.py) | 177 | TestIdentityModel、TestIdentityAuthMethod、IdentityVerificationConfig、AuthenticationProfile、IdentityVerificationSnapshot、TestIdentityCookie、TestIdentity、identity_source_fingerprint |
| [product/backend/domain/lifecycle.py](../../../product/backend/domain/lifecycle.py) | 57 | ProjectStatus、ContractStatus、RunLifecycle、RunVerdict、CaseVerdict、JobState、DomainModel |
| [product/backend/domain/preparation/__init__.py](../../../product/backend/domain/preparation/__init__.py) | 1 | 包、内部机制或样式 |
| [product/backend/domain/preparation/bindings.py](../../../product/backend/domain/preparation/bindings.py) | 270 | ResourceInjectionKind、ActionEvidenceKind、ResourceInjection、RecordedRequestTemplate、contains_resource_slot、RegisteredObserverReference、ActionExecutionBinding、ActionResourceBinding等 |
| [product/backend/domain/preparation/requirements.py](../../../product/backend/domain/preparation/requirements.py) | 367 | AllocationMode、AssuranceStatus、PermissionIdentity、IdentityRequirementSlot、PermissionIdentitySlots、IdentityRequirementPlan、ActionResourceRequirement、EffectEvidenceRequirement等 |
| [product/backend/domain/preparation/suggestions.py](../../../product/backend/domain/preparation/suggestions.py) | 188 | ApprovedMaterialTarget、CandidateMaterialTarget、SuggestionSource、IdentitySuggestion、ExecutionSuggestion、ResourceFieldRequirement、ResourceSuggestion、EvidenceSuggestion等 |
| [product/backend/domain/recording/__init__.py](../../../product/backend/domain/recording/__init__.py) | 1 | 包、内部机制或样式 |
| [product/backend/domain/recording/models.py](../../../product/backend/domain/recording/models.py) | 268 | RecordingState、RecordingPurpose、RecordingTerminalState、RecordingReasonCode、RecordingModel、RecordingStateEvent、Recording、transition_recording_state |
| [product/backend/domain/redaction.py](../../../product/backend/domain/redaction.py) | 68 | is_sensitive_key、redact、redact_known_secrets |
| [product/backend/domain/reports/__init__.py](../../../product/backend/domain/reports/__init__.py) | 1 | 包、内部机制或样式 |
| [product/backend/domain/reports/repair.py](../../../product/backend/domain/reports/repair.py) | 299 | RepairModel、RepairContractReference、RepairIntentIdentity、RepairAllowControlIdentity、RepairRegressionControlIdentity、RepairEvidenceStandard、RepairContract、RepairRequirementView等 |
| [product/backend/domain/verification/__init__.py](../../../product/backend/domain/verification/__init__.py) | 1 | 包、内部机制或样式 |
| [product/backend/domain/verification/breakpoints/__init__.py](../../../product/backend/domain/verification/breakpoints/__init__.py) | 5 | 包、内部机制或样式 |
| [product/backend/domain/verification/breakpoints/causality.py](../../../product/backend/domain/verification/breakpoints/causality.py) | 441 | 包、内部机制或样式 |
| [product/backend/domain/verification/breakpoints/graph.py](../../../product/backend/domain/verification/breakpoints/graph.py) | 122 | 包、内部机制或样式 |
| [product/backend/domain/verification/breakpoints/locator.py](../../../product/backend/domain/verification/breakpoints/locator.py) | 327 | BreakpointLocator |
| [product/backend/domain/verification/breakpoints/models.py](../../../product/backend/domain/verification/breakpoints/models.py) | 150 | BreakpointType、BreakpointPrecision、BreakpointResult |
| [product/backend/domain/verification/business_facts.py](../../../product/backend/domain/verification/business_facts.py) | 128 | verified_principals、reduce_creation_facts、reduce_record_facts、reduce_disclosure_facts、reduce_file_facts |
| [product/backend/domain/verification/checks.py](../../../product/backend/domain/verification/checks.py) | 172 | CheckEffectFact、CheckProofObservation、project_check_effect_facts、CheckDecisionInput、CheckDecision、evaluate_check_case、aggregate_check_verdict |
| [product/backend/domain/verification/continuity.py](../../../product/backend/domain/verification/continuity.py) | 261 | AuthorizationContinuityState、AuthorizationEffectReference、AuthorizationContinuityAssessment、assess_check_authorization_continuity、assess_authorization_continuity |
| [product/backend/domain/verification/differential.py](../../../product/backend/domain/verification/differential.py) | 229 | TwinPlanGapCode、TwinExecutionRole、PermissionMutationDescriptor、TwinInvariantSpecification、PermissionTwin、TwinPlanGap、DifferentialExperimentPlan、build_differential_experiment_plan |
| [product/backend/domain/verification/facts.py](../../../product/backend/domain/verification/facts.py) | 244 | FactModel、TargetType、ExecutionOutcome、ObservedEffect、TemporalClosure、ExecutionFact、ObservationFact、DisclosureProof等 |
| [product/backend/domain/verification/permissions/__init__.py](../../../product/backend/domain/verification/permissions/__init__.py) | 71 | 包、内部机制或样式 |
| [product/backend/domain/verification/permissions/contract.py](../../../product/backend/domain/verification/permissions/contract.py) | 542 | PermissionContract、parse_permission_contract、NormalizedPermissionCase、NormalizedPermissionPlan、canonical_json_bytes、permission_model_sha256、compile_permission_plan |
| [product/backend/domain/verification/permissions/coverage.py](../../../product/backend/domain/verification/permissions/coverage.py) | 639 | CoverageGapCode、EliminatedReason、CoverageStatus、RetentionReason、PermissionMutationCase、CoverageRecord、CoverageGap、EliminatedCandidate等 |
| [product/backend/domain/verification/permissions/models.py](../../../product/backend/domain/verification/permissions/models.py) | 311 | PermissionModel、RelationType、SecurityEffectDefinition、CoverageDimension、BatchAuthorizationMode、WorkflowTransition、sorted_unique_values、validate_intent_text等 |
| [product/backend/domain/verification/trace.py](../../../product/backend/domain/verification/trace.py) | 230 | TraceCorrelationKind、TraceAuthorizationDecision、TraceEventKind、TraceAuthorityScope、TraceEvent、ExecutionTrace |
