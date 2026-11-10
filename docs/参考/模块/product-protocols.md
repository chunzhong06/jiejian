# product/protocols 模块

<!-- generated:modules -->

[返回总索引](../模块索引.md)

按目录定位后读取对应小节；每个文件有独立标题，源码链接用于核对声明与直接消费者。行数和公开声明由静态提取，不表示运行验收。

按目录定位：[根目录](#根目录)（4 个文件）、[checks](#checks)（14 个文件）、[observer](#observer)（5 个文件）、[preparation](#preparation)（9 个文件）、[recording](#recording)（5 个文件）、[runner](#runner)（6 个文件）、[runtime](#runtime)（12 个文件）、[web](#web)（9 个文件）。

## 根目录

### __init__.py

[源码](../../../product/protocols/__init__.py)（1 行）。公开声明：包、内部机制或样式。

### codec.py

[源码](../../../product/protocols/codec.py)（64 行）。公开声明：`encode_json`、`content_hash`、`decode_json`、`decode_document`。

### report.py

[源码](../../../product/protocols/report.py)（590 行）。公开声明：`ReportModel`、`ReportEvidenceRef`、`ReportFinding`、`ReportObserverStatus`、`ReportRuntime`、`ReportArtifact`、`ArtifactSummaryStatus`、`ArtifactSummary`等。

### schema.py

[源码](../../../product/protocols/schema.py)（178 行）。公开声明：`SchemaEntry`、`render_schema`、`synchronize_schemas`、`main`。

## checks

### checks/__init__.py

[源码](../../../product/protocols/checks/__init__.py)（1 行）。公开声明：包、内部机制或样式。

### checks/business_facts.py

[源码](../../../product/protocols/checks/business_facts.py)（293 行）。公开声明：`FactProofReference`、`CommittedFieldChange`、`CommittedStateFact`、`IdentityCheckFact`、`AnonymousCheckFact`、`FieldContentComparison`、`FieldDisclosureFact`、`ArtifactManifestReference`等。

### checks/check_publication.py

[源码](../../../product/protocols/checks/check_publication.py)（42 行）。公开声明：`CheckPublishedFile`、`CheckPublicationManifest`。

### checks/check_result.py

[源码](../../../product/protocols/checks/check_result.py)（311 行）。公开声明：`check_request_marker`、`CheckAssetReference`、`CheckRunnerInput`、`CheckRunnerProgress`、`CheckObservation`、`ScenarioResourceBinding`、`CheckCaseOutcome`、`CheckEvidence`等。

### checks/check_runtime.py

[源码](../../../product/protocols/checks/check_runtime.py)（449 行）。公开声明：`CheckBudget`、`CheckFlowStep`、`CheckAuxiliarySource`、`CheckProofConfig`、`CheckRecoveryConfig`、`CheckActionConfig`、`async_completion_candidates`、`ExternalWebRuntime`等。

### checks/conditions.py

[源码](../../../product/protocols/checks/conditions.py)（107 行）。公开声明：`ConditionModel`、`PermissionConditions`、`ObservedPermissionConditions`、`match_permission_conditions`、`collected_conditions_status`、`permission_conditions_overlap`。

### checks/execution_request.py

[源码](../../../product/protocols/checks/execution_request.py)（534 行）。公开声明：`WireModel`、`PermissionReference`、`FrozenPermission`、`ExecutionAssetReference`、`RecordedProofReference`、`ObserverProofReference`、`OperationProofReference`、`EffectProofRequirement`等。

### checks/field_mutation.py

[源码](../../../product/protocols/checks/field_mutation.py)（55 行）。公开声明：`FieldMutationRequirement`、`same_scalar`、`mutation_happened`。

### checks/identity.py

[源码](../../../product/protocols/checks/identity.py)（44 行）。公开声明：`CheckIdentityVerification`、`CheckIdentity`。

### checks/relationships.py

[源码](../../../product/protocols/checks/relationships.py)（221 行）。公开声明：`RelationshipModel`、`RelationshipRequirement`、`RelationshipEdge`、`RelationshipGrant`、`RelationshipSnapshot`、`ObservedRelationship`、`observe_relationship`。

### checks/routine_reference.py

[源码](../../../product/protocols/checks/routine_reference.py)（15 行）。公开声明：`RoutineReference`、`FrozenRoutineReference`。

### checks/routines.py

[源码](../../../product/protocols/checks/routines.py)（128 行）。公开声明：`RoutineValue`、`RoutineScope`、`RoutineLimits`、`RoutineActor`、`RoutineAction`、`RoutineRequirement`、`CheckRoutineDocument`、`RoutineBoundAsset`等。

### checks/scenario_execution.py

[源码](../../../product/protocols/checks/scenario_execution.py)（58 行）。公开声明：`ScenarioNodeProgress`、`ScenarioExecutionJournal`。

### checks/scenarios.py

[源码](../../../product/protocols/checks/scenarios.py)（218 行）。公开声明：`ScenarioModel`、`ScenarioPermission`、`ScenarioItem`、`BatchInvocation`、`ScenarioInvocation`、`ScenarioExperiment`、`BusinessScenarioRevision`、`FrozenScenarioInvocation`等。

## observer

### observer/__init__.py

[源码](../../../product/protocols/observer/__init__.py)（1 行）。公开声明：包、内部机制或样式。

### observer/codec.py

[源码](../../../product/protocols/observer/codec.py)（53 行）。公开声明：`canonical_json_bytes`、`observer_canonical_sha256`、`parse_observer_json`。

### observer/config.py

[源码](../../../product/protocols/observer/config.py)（551 行）。公开声明：`ObserverModel`、`ObserverType`、`ObservationPhase`、`ObservationCompleteness`、`CausalityStatus`、`ProvenanceType`、`ObserverOutcomeStatus`、`OwnerApiLocator`等。

### observer/invocation.py

[源码](../../../product/protocols/observer/invocation.py)（124 行）。公开声明：`Correlation`、`AuditLogStartCursor`、`ObserverInvocation`、`AsyncTaskObserverInvocation`、`AuditLogObserverInvocation`、`ObservationWindow`。

### observer/result.py

[源码](../../../product/protocols/observer/result.py)（214 行）。公开声明：`NormalizedState`、`build_normalized_state`、`ObservationProvenance`、`ObservationEnvelope`、`ObserverOutcome`、`evaluate_observer_outcome`。

## preparation

### preparation/__init__.py

[源码](../../../product/protocols/preparation/__init__.py)（1 行）。公开声明：包、内部机制或样式。

### preparation/api_source.py

[源码](../../../product/protocols/preparation/api_source.py)（70 行）。公开声明：`SourceParameter`、`SourceRequest`、`ApiSourceReference`、`ApiSourceDocument`、`ApiImportDocument`、`parse_source_document`。

### preparation/flow_trial.py

[源码](../../../product/protocols/preparation/flow_trial.py)（97 行）。公开声明：`TrialCase`、`FlowTrialRuntime`、`FlowTrialPlan`、`FlowTrialRequest`、`FlowTrialRunnerInput`、`FlowTrialStep`、`FlowTrialReport`。

### preparation/http_entity.py

[源码](../../../product/protocols/preparation/http_entity.py)（37 行）。公开声明：`HttpEntityQuery`、`HttpEntityEvidence`。

### preparation/operation_flow.py

[源码](../../../product/protocols/preparation/operation_flow.py)（140 行）。公开声明：`operation_resource_injection`、`OperationFlow`、`OperationFlowDraft`。

### preparation/proof_artifacts.py

[源码](../../../product/protocols/preparation/proof_artifacts.py)（34 行）。公开声明：`ProofArtifactInput`。

### preparation/proof_sources.py

[源码](../../../product/protocols/preparation/proof_sources.py)（596 行）。公开声明：`safe_source_path`、`SourceIdentityClaim`、`ProofSourceConfig`、`safe_identity_path`、`ManagedIdentityClaim`、`RelationshipSourceMapping`、`ManagedProofSourceConfig`、`source_identity_paths`等。

### preparation/reference_capture.py

[源码](../../../product/protocols/preparation/reference_capture.py)（190 行）。公开声明：`CaptureActionConfig`、`CaptureRuntimeConfig`、`CaptureResourceSource`、`CaptureCase`、`CaptureRecoveryReference`、`ReferenceCaptureBaseline`、`ReferenceCapturePlan`、`ReferenceCaptureRequest`等。

### preparation/test_identity_preparation.py

[源码](../../../product/protocols/preparation/test_identity_preparation.py)（165 行）。公开声明：`IdentityPreparationResultType`、`IdentityPreparationRequest`、`PreparedCookieRef`、`IdentityPreparationResult`、`canonical_identity_preparation_json_bytes`、`parse_identity_preparation_request`、`parse_identity_preparation_result`。

## recording

### recording/__init__.py

[源码](../../../product/protocols/recording/__init__.py)（1 行）。公开声明：包、内部机制或样式。

### recording/created_resource.py

[源码](../../../product/protocols/recording/created_resource.py)（77 行）。公开声明：`resource_identifier`、`location_resource`、`response_object_candidates`。

### recording/events.py

[源码](../../../product/protocols/recording/events.py)（547 行）。公开声明：`RecordingProtocolModel`、`RecordingRunnerResultType`、`RecordingCleanupStatus`、`RecordingEventKind`、`RecordingAuthMethod`、`RecordingBudget`、`RecordingCookieRef`、`RecordingSessionRef`等。

### recording/flow_draft.py

[源码](../../../product/protocols/recording/flow_draft.py)（469 行）。公开声明：`FlowDraftProtocolModel`、`FlowDraftVariableStatus`、`FlowDraftVariableSource`、`FlowDraftVariable`、`FlowDraftResourceCandidate`、`FlowDraftStep`、`FlowDraft`、`ConfirmFlowDraftVariableChoice`等。

### recording/recording_flow.py

[源码](../../../product/protocols/recording/recording_flow.py)（150 行）。公开声明：`RecordingFlowModel`、`FlowVariableSource`、`FlowStep`、`Flow`。

## runner

### runner/__init__.py

[源码](../../../product/protocols/runner/__init__.py)（1 行）。公开声明：包、内部机制或样式。

### runner/codec.py

[源码](../../../product/protocols/runner/codec.py)（109 行）。公开声明：`canonical_runner_json_bytes`、`canonical_runner_sha256`、`parse_runner_input`、`parse_runner_result`、`parse_evidence`。

### runner/evidence.py

[源码](../../../product/protocols/runner/evidence.py)（213 行）。公开声明：`Evidence`、`build_evidence`。

### runner/execution.py

[源码](../../../product/protocols/runner/execution.py)（105 行）。公开声明：`ProtocolModel`、`ExecutionBudget`、`SubjectExecutionBinding`、`ObserverRequirementKind`、`EffectClosurePolicy`、`EffectBinding`、`ObserverRequirementBinding`。

### runner/input.py

[源码](../../../product/protocols/runner/input.py)（160 行）。公开声明：`RunnerResultType`、`CleanupStatus`、`RunnerFailurePhase`、`CleanupIssueCode`、`ResourceInjection`、`RunnerInput`。

### runner/result.py

[源码](../../../product/protocols/runner/result.py)（228 行）。公开声明：`CleanupIssue`、`CleanupResult`、`RunnerError`、`StagedArtifact`、`RunnerResult`。

## runtime

### runtime/__init__.py

[源码](../../../product/protocols/runtime/__init__.py)（1 行）。公开声明：包、内部机制或样式。

### runtime/creation_records.py

[源码](../../../product/protocols/runtime/creation_records.py)（58 行）。公开声明：`ScopedRecordSeed`、`RecordRemove`、`CreationMember`、`CreationEvent`、`CreationView`。

### runtime/database_capture.py

[源码](../../../product/protocols/runtime/database_capture.py)（40 行）。公开声明：`database_secret_name`、`DatabaseCapture`。

### runtime/database_installation.py

[源码](../../../product/protocols/runtime/database_installation.py)（24 行）。公开声明：`DatabaseInstallation`。

### runtime/frontend_assets.py

[源码](../../../product/protocols/runtime/frontend_assets.py)（30 行）。公开声明：`FrontendAsset`、`FrontendAssetManifest`。

### runtime/node_runtime.py

[源码](../../../product/protocols/runtime/node_runtime.py)（164 行）。公开声明：`SqliteTableCapture`、`SqliteDatabaseCapture`、`NodePackagePlan`、`NodeRuntimeManifest`、`NodeRuntimeLoadRequest`、`NodeRuntimeReference`、`NodeBuildArtifact`、`NodeRuntimeLoadReceipt`等。

### runtime/portable_release.py

[源码](../../../product/protocols/runtime/portable_release.py)（19 行）。公开声明：`PortableReleaseManifest`。

### runtime/portable_update.py

[源码](../../../product/protocols/runtime/portable_update.py)（67 行）。公开声明：`PortableUpdateFile`、`PortableWorkspaceIdentity`、`PortableUpdateManifest`、`PortableUpdateOperation`、`PortableExitReceipt`。

### runtime/record_trace.py

[源码](../../../product/protocols/runtime/record_trace.py)（73 行）。公开声明：`RecordTraceInput`、`RecordTraceWrite`、`RecordTraceEvent`、`RecordTraceReceipt`、`RecordTraceLog`。

### runtime/request_activity.py

[源码](../../../product/protocols/runtime/request_activity.py)（69 行）。公开声明：`ActivityEvent`、`RequestActivity`。

### runtime/runtime_identity.py

[源码](../../../product/protocols/runtime/runtime_identity.py)（109 行）。公开声明：`RuntimeModel`、`RuntimeFile`、`runtime_source_fingerprint`、`RuntimeLaunchManifest`、`runtime_manifest_fingerprint`、`RuntimeLaunchReceipt`、`ControlledRuntimeReference`、`RuntimeCorrespondence`等。

### runtime/transaction_records.py

[源码](../../../product/protocols/runtime/transaction_records.py)（190 行）。公开声明：`bounded_record_data`、`RecordChange`、`RecordSeed`、`RecordSnapshot`、`RecordTransition`、`RecordProviderReference`、`RecordProofRequest`、`RecordRequestScope`等。

## web

### web/__init__.py

[源码](../../../product/protocols/web/__init__.py)（93 行）。公开声明：包、内部机制或样式。

### web/base.py

[源码](../../../product/protocols/web/base.py)（6 行）。公开声明：`ProtocolModel`。

### web/environment.py

[源码](../../../product/protocols/web/environment.py)（47 行）。公开声明：`FrozenEnvironment`、`EnvironmentDocument`、`parse_environment_document`。

### web/identity.py

[源码](../../../product/protocols/web/identity.py)（359 行）。公开声明：`HttpIdentityKind`、`IdentityBootstrapRequest`、`AuthTargetScope`、`AnonymousIdentityBinding`、`BearerIdentityBinding`、`StaticHeaderCredential`、`StaticHeadersIdentityBinding`、`CookieSessionIdentityBinding`等。

### web/profile.py

[源码](../../../product/protocols/web/profile.py)（540 行）。公开声明：`WebExecutionSnapshot`、`required_web_secret_refs`、`WebExecutionProfile`、`canonical_web_execution_profile_json_bytes`、`web_execution_profile_sha256`、`parse_web_execution_profile`。

### web/request.py

[源码](../../../product/protocols/web/request.py)（368 行）。公开声明：`HttpBodyKind`、`ValueSlotSource`、`ValueSlotConsumer`、`ValueType`、`ValueSlot`、`HttpParameter`、`MultipartPart`、`EmptyBody`等。

### web/response.py

[源码](../../../product/protocols/web/response.py)（305 行）。公开声明：`ResponseExtractorKind`、`HttpPredicateKind`、`HttpOutcome`、`ResponseExtractor`、`HttpPredicate`、`HttpOutcomeClassifier`。

### web/target.py

[源码](../../../product/protocols/web/target.py)（112 行）。公开声明：`WebTargetScope`、`WebTargetDefinition`。

### web/workflow.py

[源码](../../../product/protocols/web/workflow.py)（275 行）。公开声明：`WorkflowStepPurpose`、`WorkflowFailurePolicy`、`ResetStrategyKind`、`BaselineIntegrityMode`、`LogicalResourceSlot`、`BaselineProjection`、`ResetEndpointStrategy`、`UniqueResourceWorkflowResetStrategy`等。
