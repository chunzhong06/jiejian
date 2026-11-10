# product/backend/application 模块

<!-- generated:modules -->

[返回总索引](../模块索引.md)

按目录定位后读取对应小节；每个文件有独立标题，源码链接用于核对声明与直接消费者。行数和公开声明由静态提取，不表示运行验收。

按目录定位：[根目录](#根目录)（2 个文件）、[agent_access](#agent_access)（13 个文件）、[application_understanding](#application_understanding)（6 个文件）、[application_understanding/analysis](#application_understandinganalysis)（8 个文件）、[business_boundaries](#business_boundaries)（5 个文件）、[business_boundaries/candidates](#business_boundariescandidates)（8 个文件）、[business_boundaries/proposals](#business_boundariesproposals)（7 个文件）、[business_boundaries/reading](#business_boundariesreading)（4 个文件）、[changes](#changes)（4 个文件）、[checks](#checks)（9 个文件）、[checks/reading](#checksreading)（6 个文件）、[checks/repairs](#checksrepairs)（4 个文件）、[development](#development)（4 个文件）、[examples](#examples)（10 个文件）、[onboarding](#onboarding)（5 个文件）、[preparation](#preparation)（11 个文件）、[preparation/bindings](#preparationbindings)（5 个文件）、[preparation/guidance](#preparationguidance)（5 个文件）、[preparation/materials](#preparationmaterials)（4 个文件）、[preparation/proofs](#preparationproofs)（9 个文件）、[preparation/supplemental](#preparationsupplemental)（3 个文件）、[projects](#projects)（5 个文件）、[recording](#recording)（13 个文件）、[runtime](#runtime)（6 个文件）、[test_identities](#test_identities)（8 个文件）、[workspace](#workspace)（7 个文件）。

## 根目录

### __init__.py

[源码](../../../product/backend/application/__init__.py)（1 行）。公开声明：包、内部机制或样式。

### reading.py

[源码](../../../product/backend/application/reading.py)（44 行）。公开声明：`projection_read`、`projected_once`、`accepted_once`。

## agent_access

### agent_access/__init__.py

[源码](../../../product/backend/application/agent_access/__init__.py)（1 行）。公开声明：包、内部机制或样式。

### agent_access/capabilities.py

[源码](../../../product/backend/application/agent_access/capabilities.py)（779 行）。公开声明：`Capability`、`parameters`、`ProductCapabilities`。

### agent_access/client_config.py

[源码](../../../product/backend/application/agent_access/client_config.py)（203 行）。公开声明：`ConnectionProblem`、`read_config`、`json_patch`、`toml_patch`、`dsh_patch`、`trae_link`、`dsh_needs_startup_update`、`connection_matches`。

### agent_access/connection_files.py

[源码](../../../product/backend/application/agent_access/connection_files.py)（78 行）。公开声明：`ConnectionProfile`、`ConnectionReceipt`、`ConnectionBackup`、`protect`、`unprotect`、`atomic_write`、`read_profile`。

### agent_access/connections.py

[源码](../../../product/backend/application/agent_access/connections.py)（201 行）。公开声明：`AgentConnections`。

### agent_access/connector.py

[源码](../../../product/backend/application/agent_access/connector.py)（275 行）。公开声明：`ResumeRejected`、`IdleInput`、`relay`、`main`。

### agent_access/dsh_schema.py

[源码](../../../product/backend/application/agent_access/dsh_schema.py)（160 行）。公开声明：`DshSchemaError`、`project_schema`、`DshToolSchemas`。

### agent_access/execution.py

[源码](../../../product/backend/application/agent_access/execution.py)（263 行）。公开声明：`StartAgent`、`AgentExecution`。

### agent_access/github_issues.py

[源码](../../../product/backend/application/agent_access/github_issues.py)（82 行）。公开声明：`IssueSource`、`IssueDelivery`、`IssueCollaboration`。

### agent_access/handoff.py

[源码](../../../product/backend/application/agent_access/handoff.py)（73 行）。公开声明：`HandoffInput`、`ParameterHandoff`、`StepHandoff`、`EvidenceHandoff`、`FlowHandoff`、`ProofHandoff`、`ScenarioHandoff`。

### agent_access/service.py

[源码](../../../product/backend/application/agent_access/service.py)（349 行）。公开声明：`MCPAccessLevel`、`MCPConnectionState`、`MCPProjectGrant`、`MCPAccessView`、`MCPAccessCredentialView`、`MCPAccessController`。

### agent_access/tasks.py

[源码](../../../product/backend/application/agent_access/tasks.py)（497 行）。公开声明：`TaskInput`、`CreateCollaboration`、`CollaborationAction`、`CollaborationQuestion`、`CollaborationFollowup`、`CollaborationTasks`。

### agent_access/workflow.py

[源码](../../../product/backend/application/agent_access/workflow.py)（84 行）。公开声明：`AgentWorkflowContext`。

## application_understanding

### application_understanding/__init__.py

[源码](../../../product/backend/application/application_understanding/__init__.py)（1 行）。公开声明：包、内部机制或样式。

### application_understanding/endpoints.py

[源码](../../../product/backend/application/application_understanding/endpoints.py)（438 行）。公开声明：`EndpointModel`、`EndpointDiscoveryLimits`、`EndpointProbeObservation`、`EndpointCandidate`、`EndpointDiscoveryResult`、`normalize_loopback_endpoint`、`TargetEndpointDiscovery`。

### application_understanding/environments.py

[源码](../../../product/backend/application/application_understanding/environments.py)（130 行）。公开声明：`ApplicationEnvironments`。

### application_understanding/imports.py

[源码](../../../product/backend/application/application_understanding/imports.py)（199 行）。公开声明：`source_error`、`normalize_source`。

### application_understanding/service.py

[源码](../../../product/backend/application/application_understanding/service.py)（679 行）。公开声明：`ApplicationConnectionView`、`ApplicationUnderstandingService`。

### application_understanding/sources.py

[源码](../../../product/backend/application/application_understanding/sources.py)（161 行）。公开声明：`ApplicationSources`。

## application_understanding/analysis

### application_understanding/analysis/__init__.py

[源码](../../../product/backend/application/application_understanding/analysis/__init__.py)（17 行）。公开声明：包、内部机制或样式。

### application_understanding/analysis/analyzer.py

[源码](../../../product/backend/application/application_understanding/analysis/analyzer.py)（172 行）。公开声明：`ApplicationUnderstandingAnalyzer`。

### application_understanding/analysis/findings.py

[源码](../../../product/backend/application/application_understanding/analysis/findings.py)（193 行）。公开声明：`CandidateCollector`。

### application_understanding/analysis/javascript.py

[源码](../../../product/backend/application/application_understanding/analysis/javascript.py)（77 行）。公开声明：`analyze_javascript`。

### application_understanding/analysis/models.py

[源码](../../../product/backend/application/application_understanding/analysis/models.py)（41 行）。公开声明：`AnalysisModel`、`SourceAnalysisLimits`、`SqliteTableSuggestion`、`SqliteSetupSuggestions`、`ApplicationAnalysisResult`。

### application_understanding/analysis/openapi.py

[源码](../../../product/backend/application/application_understanding/analysis/openapi.py)（145 行）。公开声明：`analyze_openapi`。

### application_understanding/analysis/python.py

[源码](../../../product/backend/application/application_understanding/analysis/python.py)（218 行）。公开声明：`analyze_python`。

### application_understanding/analysis/sqlite_setup.py

[源码](../../../product/backend/application/application_understanding/analysis/sqlite_setup.py)（72 行）。公开声明：`sqlite_setup_suggestions`。

## business_boundaries

### business_boundaries/__init__.py

[源码](../../../product/backend/application/business_boundaries/__init__.py)（29 行）。公开声明：包、内部机制或样式。

### business_boundaries/fingerprints.py

[源码](../../../product/backend/application/business_boundaries/fingerprints.py)（78 行）。公开声明：`candidate_source_snapshot`、`legacy_candidate_source_snapshot`、`implementation_candidate_snapshot`。

### business_boundaries/inspection.py

[源码](../../../product/backend/application/business_boundaries/inspection.py)（205 行）。公开声明：`ActorImplementationInspection`、`ActionImplementationInspection`、`inspect_actor_binding`、`inspect_action_binding`。

### business_boundaries/models.py

[源码](../../../product/backend/application/business_boundaries/models.py)（343 行）。公开声明：`BoundaryWorkflowModel`、`BoundaryProposalCommand`、`BoundaryDraftCandidate`、`BoundaryDraftView`、`BoundaryMaintenanceCandidateOption`、`BoundaryMaintenanceActorItem`、`BoundaryMaintenanceActionItem`、`BoundaryMaintenancePermissionItem`等。

### business_boundaries/service.py

[源码](../../../product/backend/application/business_boundaries/service.py)（507 行）。公开声明：`BusinessBoundaryService`。

## business_boundaries/candidates

### business_boundaries/candidates/__init__.py

[源码](../../../product/backend/application/business_boundaries/candidates/__init__.py)（1 行）。公开声明：包、内部机制或样式。

### business_boundaries/candidates/corrections.py

[源码](../../../product/backend/application/business_boundaries/candidates/corrections.py)（43 行）。公开声明：`carry_assistance`。

### business_boundaries/candidates/coverage.py

[源码](../../../product/backend/application/business_boundaries/candidates/coverage.py)（102 行）。公开声明：`coverage_items`、`path_shape`、`coverage_ready`、`frozen_requirement_scope`。

### business_boundaries/candidates/decisions.py

[源码](../../../product/backend/application/business_boundaries/candidates/decisions.py)（203 行）。公开声明：`scenario_state`、`decision_digest`、`pending_scenario_issues`、`selected_permission_issues`、`check_candidate_edit`、`validate_approval_source`、`save_approval_mappings`。

### business_boundaries/candidates/preview.py

[源码](../../../product/backend/application/business_boundaries/candidates/preview.py)（77 行）。公开声明：`preview_rules`。

### business_boundaries/candidates/reviews.py

[源码](../../../product/backend/application/business_boundaries/candidates/reviews.py)（67 行）。公开声明：`project_review_gaps`、`protect_review_sources`。

### business_boundaries/candidates/rule_candidates.py

[源码](../../../product/backend/application/business_boundaries/candidates/rule_candidates.py)（507 行）。公开声明：`RuleCandidateService`。

### business_boundaries/candidates/scope.py

[源码](../../../product/backend/application/business_boundaries/candidates/scope.py)（109 行）。公开声明：`merge_content`、`decide_scope_content`、`decide_scope_batch_content`、`protect_scope`、`issue_tasks`。

## business_boundaries/proposals

### business_boundaries/proposals/__init__.py

[源码](../../../product/backend/application/business_boundaries/proposals/__init__.py)（1 行）。公开声明：包、内部机制或样式。

### business_boundaries/proposals/maintenance.py

[源码](../../../product/backend/application/business_boundaries/proposals/maintenance.py)（750 行）。公开声明：`boundary_state_fingerprint`、`build_maintenance_draft`、`maintenance_to_proposal_command`、`proposal_change_summary`。

### business_boundaries/proposals/official_recipe.py

[源码](../../../product/backend/application/business_boundaries/proposals/official_recipe.py)（210 行）。公开声明：`official_boundary_recipe`。

### business_boundaries/proposals/planning.py

[源码](../../../product/backend/application/business_boundaries/proposals/planning.py)（361 行）。公开声明：包、内部机制或样式。

### business_boundaries/proposals/review.py

[源码](../../../product/backend/application/business_boundaries/proposals/review.py)（97 行）。公开声明：`proposal_review`。

### business_boundaries/proposals/sources.py

[源码](../../../product/backend/application/business_boundaries/proposals/sources.py)（225 行）。公开声明：包、内部机制或样式。

### business_boundaries/proposals/validation.py

[源码](../../../product/backend/application/business_boundaries/proposals/validation.py)（46 行）。公开声明：包、内部机制或样式。

## business_boundaries/reading

### business_boundaries/reading/__init__.py

[源码](../../../product/backend/application/business_boundaries/reading/__init__.py)（1 行）。公开声明：包、内部机制或样式。

### business_boundaries/reading/permissions.py

[源码](../../../product/backend/application/business_boundaries/reading/permissions.py)（102 行）。公开声明：`PermissionIntentViewModel`、`PermissionIntentCellStatus`、`PermissionIntentCellView`、`PermissionIntentActionView`、`PermissionIntentMatrixView`、`PermissionIntentHistoryView`、`PermissionIntentService`。

### business_boundaries/reading/queries.py

[源码](../../../product/backend/application/business_boundaries/reading/queries.py)（292 行）。公开声明：`current_permission_intents`。

### business_boundaries/reading/rule_details.py

[源码](../../../product/backend/application/business_boundaries/reading/rule_details.py)（77 行）。公开声明：`BusinessRuleDetails`。

## changes

### changes/__init__.py

[源码](../../../product/backend/application/changes/__init__.py)（4 行）。公开声明：包、内部机制或样式。

### changes/identity.py

[源码](../../../product/backend/application/changes/identity.py)（94 行）。公开声明：`SourceIdentityRecord`、`SourceIdentityComparison`、`SourceIdentityReader`。

### changes/observations.py

[源码](../../../product/backend/application/changes/observations.py)（43 行）。公开声明：`CodeObservationService`。

### changes/service.py

[源码](../../../product/backend/application/changes/service.py)（285 行）。公开声明：`SourceRevalidationInspection`、`CurrentChangeView`、`permission_refs`、`PreparedSourceChange`、`CurrentSourceChangeService`。

## checks

### checks/__init__.py

[源码](../../../product/backend/application/checks/__init__.py)（1 行）。公开声明：包、内部机制或样式。

### checks/history.py

[源码](../../../product/backend/application/checks/history.py)（108 行）。公开声明：`MaintainHistory`、`CheckHistoryService`。

### checks/local_observer_wiring.py

[源码](../../../product/backend/application/checks/local_observer_wiring.py)（273 行）。公开声明：`LocalObserverWiring`、`load_local_observer_wiring`。

### checks/registry.py

[源码](../../../product/backend/application/checks/registry.py)（169 行）。公开声明：`RegisteredCheckIdentity`、`RegisteredResourceWindow`、`RegisteredAuxiliarySource`、`RegisteredCheckProof`、`CheckRuntimeRegistration`、`CheckRuntimeRegistry`。

### checks/routine_execution.py

[源码](../../../product/backend/application/checks/routine_execution.py)（282 行）。公开声明：`SaveRoutineRevision`、`BindRoutine`、`bound_assets`、`missing_requirements`、`RoutineExecution`。

### checks/routine_progress.py

[源码](../../../product/backend/application/checks/routine_progress.py)（50 行）。公开声明：`RoutineRequirementProgress`、`requirement_progress`。

### checks/routines.py

[源码](../../../product/backend/application/checks/routines.py)（67 行）。公开声明：`SaveCheckRoutine`、`CheckRoutines`。

### checks/runtime_bundle.py

[源码](../../../product/backend/application/checks/runtime_bundle.py)（330 行）。公开声明：`recorded_request_template`、`CheckRuntimeBuilder`、`derive_target_classifiers`。

### checks/service.py

[源码](../../../product/backend/application/checks/service.py)（453 行）。公开声明：`ExternalRecheckCommand`、`CheckPreview`、`CheckService`。

## checks/reading

### checks/reading/__init__.py

[源码](../../../product/backend/application/checks/reading/__init__.py)（1 行）。公开声明：包、内部机制或样式。

### checks/reading/comparison.py

[源码](../../../product/backend/application/checks/reading/comparison.py)（239 行）。公开声明：`ComparisonRun`、`ComparisonObservation`、`ComparisonItem`、`RunComparison`、`classify_change`、`CheckComparisonService`。

### checks/reading/observation_reading.py

[源码](../../../product/backend/application/checks/reading/observation_reading.py)（66 行）。公开声明：`ObservationReading`、`observation_reading`。

### checks/reading/records.py

[源码](../../../product/backend/application/checks/reading/records.py)（288 行）。公开声明：`RecordLink`、`EvidenceRecordIndex`、`VerificationSection`、`EvidenceRecordView`、`record_index`、`record_view`。

### checks/reading/results.py

[源码](../../../product/backend/application/checks/reading/results.py)（438 行）。公开声明：`CheckRunView`、`CheckJobView`、`CheckProgressCaseView`、`CheckProgressView`、`CheckRunStatus`、`CheckContinuation`、`CheckHistoryCursor`、`CheckHistoryItem`等。

### checks/reading/story.py

[源码](../../../product/backend/application/checks/reading/story.py)（440 行）。公开声明：`StoryIdentity`、`StoryEffect`、`StoryControl`、`FactComparison`、`EvidenceExplanation`、`StoryTraceEvent`、`StoryExecutionPath`、`StoryRequestActivity`等。

## checks/repairs

### checks/repairs/__init__.py

[源码](../../../product/backend/application/checks/repairs/__init__.py)（1 行）。公开声明：包、内部机制或样式。

### checks/repairs/repair.py

[源码](../../../product/backend/application/checks/repairs/repair.py)（166 行）。公开声明：`build_current_repair_contract`、`CurrentRepairService`。

### checks/repairs/repair_presentation.py

[源码](../../../product/backend/application/checks/repairs/repair_presentation.py)（83 行）。公开声明：`RepairComparisonRow`、`RepairReview`、`build_repair_comparison`。

### checks/repairs/repair_text.py

[源码](../../../product/backend/application/checks/repairs/repair_text.py)（30 行）。公开声明：包、内部机制或样式。

## development

### development/__init__.py

[源码](../../../product/backend/application/development/__init__.py)（4 行）。公开声明：包、内部机制或样式。

### development/operations.py

[源码](../../../product/backend/application/development/operations.py)（20 行）。公开声明：`operation_fingerprint`、`require_active_task_version`。

### development/reading.py

[源码](../../../product/backend/application/development/reading.py)（176 行）。公开声明：`DevelopmentReader`。

### development/service.py

[源码](../../../product/backend/application/development/service.py)（275 行）。公开声明：`DevelopmentService`。

## examples

### examples/__init__.py

[源码](../../../product/backend/application/examples/__init__.py)（1 行）。公开声明：包、内部机制或样式。

### examples/environment.py

[源码](../../../product/backend/application/examples/environment.py)（642 行）。公开声明：`OfficialBoundaryDraft`、`OfficialScenarioVersion`、`OfficialExperienceView`、`OfficialSampleExperience`。

### examples/gallery_materials.py

[源码](../../../product/backend/application/examples/gallery_materials.py)（128 行）。公开声明：`prepare_gallery_materials`、`prepare_gallery_content`。

### examples/gallery_preparation.py

[源码](../../../product/backend/application/examples/gallery_preparation.py)（46 行）。公开声明：`advance_gallery_preparation`。

### examples/gallery_recipe.py

[源码](../../../product/backend/application/examples/gallery_recipe.py)（55 行）。公开声明：`gallery_recipe`。

### examples/journey.py

[源码](../../../product/backend/application/examples/journey.py)（65 行）。公开声明：`OfficialDevelopmentJourney`、`build_development_journey`。

### examples/materials.py

[源码](../../../product/backend/application/examples/materials.py)（251 行）。公开声明：`OfficialScenarioInstaller`。

### examples/node_environment.py

[源码](../../../product/backend/application/examples/node_environment.py)（473 行）。公开声明：`NodeOfficialSampleExperience`。

### examples/preset_delivery.py

[源码](../../../product/backend/application/examples/preset_delivery.py)（48 行）。公开声明：`preset_operation`、`prepare_preset_task`、`register_preset_delivery`、`preset_change_id`。

### examples/recovery.py

[源码](../../../product/backend/application/examples/recovery.py)（71 行）。公开声明：`SampleRecovery`。

## onboarding

### onboarding/__init__.py

[源码](../../../product/backend/application/onboarding/__init__.py)（1 行）。公开声明：包、内部机制或样式。

### onboarding/discovery.py

[源码](../../../product/backend/application/onboarding/discovery.py)（402 行）。公开声明：`is_reparse_point`、`canonical_folder`、`discover_folder`。

### onboarding/folder_picker_process.py

[源码](../../../product/backend/application/onboarding/folder_picker_process.py)（83 行）。公开声明：`show_directory_dialog`、`main`。

### onboarding/models.py

[源码](../../../product/backend/application/onboarding/models.py)（80 行）。公开声明：`OnboardingModel`、`DiscoveryLimits`、`DiscoveryCandidate`、`DiscoveryHint`、`DiscoveryMissingItem`、`DiscoveryWarning`、`DiscoveryResult`、`FolderSelectionResult`。

### onboarding/workflow.py

[源码](../../../product/backend/application/onboarding/workflow.py)（194 行）。公开声明：`FolderSelector`、`SystemFolderSelector`、`OnboardingWorkflow`。

## preparation

### preparation/__init__.py

[源码](../../../product/backend/application/preparation/__init__.py)（5 行）。公开声明：包、内部机制或样式。

### preparation/batches.py

[源码](../../../product/backend/application/preparation/batches.py)（360 行）。公开声明：`BatchSource`、`PreparationBatchPlan`、`StartPreparationBatch`、`PreparationBatchService`。

### preparation/business_scenarios.py

[源码](../../../product/backend/application/preparation/business_scenarios.py)（76 行）。公开声明：`BusinessScenarioService`。

### preparation/demonstrations.py

[源码](../../../product/backend/application/preparation/demonstrations.py)（40 行）。公开声明：`LegalActionDemonstration`、`legal_demonstrations`。

### preparation/flow_inputs.py

[源码](../../../product/backend/application/preparation/flow_inputs.py)（29 行）。公开声明：`validate_public_flow_inputs`。

### preparation/flow_trials.py

[源码](../../../product/backend/application/preparation/flow_trials.py)（181 行）。公开声明：`TrialSelection`、`StartFlowTrial`、`FlowTrialService`。

### preparation/models.py

[源码](../../../product/backend/application/preparation/models.py)（103 行）。公开声明：`RuleCaseDataSelection`、`PreparationStatus`、`PreparationItemView`、`IdentitySlotPreparationView`、`IdentityPreparationView`、`ResourcePreparationView`、`EffectEvidencePreparationView`、`ActionTechnicalPreparationView`等。

### preparation/operation_flows.py

[源码](../../../product/backend/application/preparation/operation_flows.py)（235 行）。公开声明：`execution_material`、`OperationFlowService`。

### preparation/operation_sources.py

[源码](../../../product/backend/application/preparation/operation_sources.py)（29 行）。公开声明：`source_request_current`、`load_operation_material`。

### preparation/service.py

[源码](../../../product/backend/application/preparation/service.py)（424 行）。公开声明：`preparation_recommendation`、`BoundaryReader`、`IdentityReader`、`PreparationBindingReader`、`PreparationService`。

### preparation/trial_jobs.py

[源码](../../../product/backend/application/preparation/trial_jobs.py)（83 行）。公开声明：`TrialReading`、`read_trial_facts`、`recovery_gaps_from_facts`、`trial_recovery_gaps`、`FlowTrialJobs`。

## preparation/bindings

### preparation/bindings/__init__.py

[源码](../../../product/backend/application/preparation/bindings/__init__.py)（1 行）。公开声明：包、内部机制或样式。

### preparation/bindings/recording_candidates.py

[源码](../../../product/backend/application/preparation/bindings/recording_candidates.py)（189 行）。公开声明：`RecordedPreparationCandidate`、`request_event`、`resource_value`、`recorded_resource_value`、`flow_resource_injection`、`supplement_candidates`、`choose_supplement_candidate`。

### preparation/bindings/reuse.py

[源码](../../../product/backend/application/preparation/bindings/reuse.py)（60 行）。公开声明：`material_reuse_read`、`recorded_material_reusable`、`material_fact`。

### preparation/bindings/service.py

[源码](../../../product/backend/application/preparation/bindings/service.py)（271 行）。公开声明：`RegisteredEffectProofReader`、`PreparationBindingService`。

### preparation/bindings/sources.py

[源码](../../../product/backend/application/preparation/bindings/sources.py)（152 行）。公开声明：`RegisteredObserverReader`、`BindingSourceInspector`、`binding_source_fields`。

## preparation/guidance

### preparation/guidance/__init__.py

[源码](../../../product/backend/application/preparation/guidance/__init__.py)（1 行）。公开声明：包、内部机制或样式。

### preparation/guidance/models.py

[源码](../../../product/backend/application/preparation/guidance/models.py)（74 行）。公开声明：`PreparationNextAction`、`PreparationMaterialAdvice`、`ProofSourceAdvice`、`PreparationActionProgress`、`PreparationProgress`、`PreparationGuidance`。

### preparation/guidance/service.py

[源码](../../../product/backend/application/preparation/guidance/service.py)（268 行）。公开声明：`PreparationGuidanceService`。

### preparation/guidance/suggestion_targets.py

[源码](../../../product/backend/application/preparation/guidance/suggestion_targets.py)（129 行）。公开声明：`approved_target`、`resolve_target`、`validate_existing_references`。

### preparation/guidance/suggestions.py

[源码](../../../product/backend/application/preparation/guidance/suggestions.py)（236 行）。公开声明：`PreparationSuggestionService`。

## preparation/materials

### preparation/materials/__init__.py

[源码](../../../product/backend/application/preparation/materials/__init__.py)（1 行）。公开声明：包、内部机制或样式。

### preparation/materials/evidence.py

[源码](../../../product/backend/application/preparation/materials/evidence.py)（51 行）。公开声明：`EffectMaterialSummary`、`EvidenceMaterialDetail`、`evidence_details`。

### preparation/materials/models.py

[源码](../../../product/backend/application/preparation/materials/models.py)（42 行）。公开声明：`MaterialReference`、`MaterialChange`、`PreparationDraft`。

### preparation/materials/service.py

[源码](../../../product/backend/application/preparation/materials/service.py)（253 行）。公开声明：`PreparationMaterialService`。

## preparation/proofs

### preparation/proofs/__init__.py

[源码](../../../product/backend/application/preparation/proofs/__init__.py)（1 行）。公开声明：包、内部机制或样式。

### preparation/proofs/artifact_inputs.py

[源码](../../../product/backend/application/preparation/proofs/artifact_inputs.py)（94 行）。公开声明：`UploadProofArtifact`、`CancelProofArtifact`、`ProofArtifactPreparation`。

### preparation/proofs/capture_jobs.py

[源码](../../../product/backend/application/preparation/proofs/capture_jobs.py)（139 行）。公开声明：`capture_inputs_current`、`capture_recovery_gaps`、`ReferenceCaptureJobs`。

### preparation/proofs/capture_plan.py

[源码](../../../product/backend/application/preparation/proofs/capture_plan.py)（96 行）。公开声明：`CaptureSelection`、`build_capture_plan`。

### preparation/proofs/capture_service.py

[源码](../../../product/backend/application/preparation/proofs/capture_service.py)（86 行）。公开声明：`StartReferenceCapture`、`CancelReferenceCapture`、`ReferenceCaptureService`。

### preparation/proofs/commands.py

[源码](../../../product/backend/application/preparation/proofs/commands.py)（46 行）。公开声明：`ProofOperation`、`SaveProofSource`、`StartProofPreflight`、`GrantProofScope`、`MaintainDatabaseSource`、`AdoptProofSource`、`CancelProofPreflight`、`RevokeProofScope`。

### preparation/proofs/jobs.py

[源码](../../../product/backend/application/preparation/proofs/jobs.py)（92 行）。公开声明：`ProofPreflightJobs`。

### preparation/proofs/registration.py

[源码](../../../product/backend/application/preparation/proofs/registration.py)（32 行）。公开声明：`runtime_registration`。

### preparation/proofs/service.py

[源码](../../../product/backend/application/preparation/proofs/service.py)（687 行）。公开声明：`PreparationFacts`、`ProofPreparationService`。

## preparation/supplemental

### preparation/supplemental/__init__.py

[源码](../../../product/backend/application/preparation/supplemental/__init__.py)（1 行）。公开声明：包、内部机制或样式。

### preparation/supplemental/contract.py

[源码](../../../product/backend/application/preparation/supplemental/contract.py)（58 行）。公开声明：`MaterialModel`、`SupplementalRecord`、`SupplementalDocument`、`validate_material_payload`、`material_fingerprint`、`request_uuid`。

### preparation/supplemental/service.py

[源码](../../../product/backend/application/preparation/supplemental/service.py)（108 行）。公开声明：`SupplementalMaterialService`。

## projects

### projects/__init__.py

[源码](../../../product/backend/application/projects/__init__.py)（9 行）。公开声明：包、内部机制或样式。

### projects/catalog.py

[源码](../../../product/backend/application/projects/catalog.py)（43 行）。公开声明：`ProjectCatalog`。

### projects/lifecycle.py

[源码](../../../product/backend/application/projects/lifecycle.py)（113 行）。公开声明：`ProjectLifecycleService`。

### projects/repair.py

[源码](../../../product/backend/application/projects/repair.py)（252 行）。公开声明：`RepairHistoryEvent`、`CurrentRepairTask`、`ProjectRepair`、`ResolvedRepairTask`、`CurrentProjectRepairService`。

### projects/rules.py

[源码](../../../product/backend/application/projects/rules.py)（72 行）。公开声明：`RuleWorkspaceService`。

## recording

### recording/__init__.py

[源码](../../../product/backend/application/recording/__init__.py)（6 行）。公开声明：包、内部机制或样式。

### recording/credentials.py

[源码](../../../product/backend/application/recording/credentials.py)（156 行）。公开声明：`RuntimeSecretVault`、`RecordingCredentialProvider`。

### recording/draft_models.py

[源码](../../../product/backend/application/recording/draft_models.py)（37 行）。公开声明：包、内部机制或样式。

### recording/draft_resources.py

[源码](../../../product/backend/application/recording/draft_resources.py)（87 行）。公开声明：包、内部机制或样式。

### recording/draft_values.py

[源码](../../../product/backend/application/recording/draft_values.py)（152 行）。公开声明：包、内部机制或样式。

### recording/flow_compiler.py

[源码](../../../product/backend/application/recording/flow_compiler.py)（314 行）。公开声明：`FlowDraftCompiler`。

### recording/json_locations.py

[源码](../../../product/backend/application/recording/json_locations.py)（14 行）。公开声明：`read_json_location`。

### recording/lifecycle.py

[源码](../../../product/backend/application/recording/lifecycle.py)（348 行）。公开声明：`RecordingStatusView`、`RecordingFinalizationView`、`RecordingLifecycle`。

### recording/processing.py

[源码](../../../product/backend/application/recording/processing.py)（161 行）。公开声明：`FlowDraftProcessor`。

### recording/project_submission.py

[源码](../../../product/backend/application/recording/project_submission.py)（307 行）。公开声明：`ProjectRecordingSubmission`、`ProjectRecordingService`。

### recording/review.py

[源码](../../../product/backend/application/recording/review.py)（293 行）。公开声明：`FlowDraftReviewer`。

### recording/source.py

[源码](../../../product/backend/application/recording/source.py)（163 行）。公开声明：`current_recording_instance`、`recording_endpoint_fingerprint`、`recording_source_fingerprint`、`require_recording_source`、`require_persisted_recording_source`。

### recording/submission.py

[源码](../../../product/backend/application/recording/submission.py)（630 行）。公开声明：`RecordingApplicationModel`、`SubmitRecording`、`RecordingSubmissionResult`、`RecordingCompletionResult`、`recording_target_scope`、`RecordingSubmission`。

## runtime

### runtime/__init__.py

[源码](../../../product/backend/application/runtime/__init__.py)（1 行）。公开声明：包、内部机制或样式。

### runtime/activation.py

[源码](../../../product/backend/application/runtime/activation.py)（111 行）。公开声明：`RuntimeActivationService`。

### runtime/load_jobs.py

[源码](../../../product/backend/application/runtime/load_jobs.py)（85 行）。公开声明：`RuntimeLoadJobs`。

### runtime/node_activation.py

[源码](../../../product/backend/application/runtime/node_activation.py)（82 行）。公开声明：`NodeRuntimeActivation`。

### runtime/ports.py

[源码](../../../product/backend/application/runtime/ports.py)（47 行）。公开声明：`RuntimeProvider`、`ProjectRuntimePorts`。

### runtime/setup.py

[源码](../../../product/backend/application/runtime/setup.py)（280 行）。公开声明：`NodeStartPreview`、`NodeRuntimeSetup`。

## test_identities

### test_identities/__init__.py

[源码](../../../product/backend/application/test_identities/__init__.py)（15 行）。公开声明：包、内部机制或样式。

### test_identities/execution.py

[源码](../../../product/backend/application/test_identities/execution.py)（124 行）。公开声明：`TestIdentityExecutionCredentials`。

### test_identities/freezing.py

[源码](../../../product/backend/application/test_identities/freezing.py)（16 行）。公开声明：`freeze_check_identity`。

### test_identities/login_execution.py

[源码](../../../product/backend/application/test_identities/login_execution.py)（926 行）。公开声明：`IdentityLoginSupervisor`、`IdentityPreparationHandler`。

### test_identities/models.py

[源码](../../../product/backend/application/test_identities/models.py)（32 行）。公开声明：`IdentityPreparationStatus`、`IdentityPreparationView`。

### test_identities/preparation.py

[源码](../../../product/backend/application/test_identities/preparation.py)（272 行）。公开声明：`IdentityPreparationManager`。

### test_identities/service.py

[源码](../../../product/backend/application/test_identities/service.py)（401 行）。公开声明：`TestIdentityStatus`、`PreparedLoginState`、`TestIdentityView`、`TestIdentityService`。

### test_identities/source.py

[源码](../../../product/backend/application/test_identities/source.py)（47 行）。公开声明：`preparation_source`。

## workspace

### workspace/__init__.py

[源码](../../../product/backend/application/workspace/__init__.py)（23 行）。公开声明：包、内部机制或样式。

### workspace/models.py

[源码](../../../product/backend/application/workspace/models.py)（224 行）。公开声明：`WorkspaceModel`、`WorkspaceProjectView`、`WorkspaceConnectionView`、`ActorWorkspaceView`、`ActionWorkspaceView`、`PrimaryTaskView`、`PreparationWorkAction`、`PreparationWorkView`等。

### workspace/presentation.py

[源码](../../../product/backend/application/workspace/presentation.py)（287 行）。公开声明：`task_view`、`journey_view`、`action_view`、`endpoint_status`、`source_status`、`area_views`、`boundary_views`、`development_view`。

### workspace/progress.py

[源码](../../../product/backend/application/workspace/progress.py)（92 行）。公开声明：`ApplicationProgress`。

### workspace/reading.py

[源码](../../../product/backend/application/workspace/reading.py)（152 行）。公开声明：`WorkspaceCheckReaders`、`WorkspaceCheckFacts`、`WorkspaceDevelopmentFacts`、`WorkspaceReader`、`PreparationReading`。

### workspace/service.py

[源码](../../../product/backend/application/workspace/service.py)（96 行）。公开声明：`WorkspaceService`。

### workspace/tasks.py

[源码](../../../product/backend/application/workspace/tasks.py)（395 行）。公开声明：`CheckPreviewRequired`、`boundary_task`、`allow_control_task`、`PreparationTaskSelection`、`current_check_task`、`development_task`。
