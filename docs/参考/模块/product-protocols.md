# product/protocols 模块

<!-- generated:modules -->

[返回总索引](../模块索引.md)

| 文件 | 行数 | 公开声明 |
| --- | ---: | --- |
| [product/protocols/__init__.py](../../../product/protocols/__init__.py) | 1 | 包、内部机制或样式 |
| [product/protocols/checks/__init__.py](../../../product/protocols/checks/__init__.py) | 1 | 包、内部机制或样式 |
| [product/protocols/checks/business_facts.py](../../../product/protocols/checks/business_facts.py) | 260 | FactProofReference、CommittedFieldChange、CommittedStateFact、IdentityCheckFact、AnonymousCheckFact、FieldContentComparison、FieldDisclosureFact、ArtifactManifestReference等 |
| [product/protocols/checks/check_publication.py](../../../product/protocols/checks/check_publication.py) | 42 | CheckPublishedFile、CheckPublicationManifest |
| [product/protocols/checks/check_result.py](../../../product/protocols/checks/check_result.py) | 300 | check_request_marker、CheckAssetReference、CheckRunnerInput、CheckRunnerProgress、CheckObservation、CheckCaseOutcome、CheckEvidence、CheckCaseResult等 |
| [product/protocols/checks/check_runtime.py](../../../product/protocols/checks/check_runtime.py) | 430 | CheckBudget、CheckFlowStep、CheckAuxiliarySource、CheckProofConfig、CheckRecoveryConfig、CheckActionConfig、async_completion_candidates、ExternalWebRuntime等 |
| [product/protocols/checks/conditions.py](../../../product/protocols/checks/conditions.py) | 90 | ConditionModel、PermissionConditions、ObservedPermissionConditions、match_permission_conditions、collected_conditions_status、permission_conditions_overlap |
| [product/protocols/checks/execution_request.py](../../../product/protocols/checks/execution_request.py) | 508 | WireModel、content_hash、PermissionReference、FrozenPermission、ExecutionAssetReference、RecordedProofReference、ObserverProofReference、OperationProofReference等 |
| [product/protocols/checks/identity.py](../../../product/protocols/checks/identity.py) | 44 | CheckIdentityVerification、CheckIdentity |
| [product/protocols/codec.py](../../../product/protocols/codec.py) | 58 | encode_json、decode_json、decode_document |
| [product/protocols/observer/__init__.py](../../../product/protocols/observer/__init__.py) | 1 | 包、内部机制或样式 |
| [product/protocols/observer/codec.py](../../../product/protocols/observer/codec.py) | 53 | canonical_json_bytes、observer_canonical_sha256、parse_observer_json |
| [product/protocols/observer/config.py](../../../product/protocols/observer/config.py) | 551 | ObserverModel、ObserverType、ObservationPhase、ObservationCompleteness、CausalityStatus、ProvenanceType、ObserverOutcomeStatus、OwnerApiLocator等 |
| [product/protocols/observer/invocation.py](../../../product/protocols/observer/invocation.py) | 124 | Correlation、AuditLogStartCursor、ObserverInvocation、AsyncTaskObserverInvocation、AuditLogObserverInvocation、ObservationWindow |
| [product/protocols/observer/result.py](../../../product/protocols/observer/result.py) | 214 | NormalizedState、build_normalized_state、ObservationProvenance、ObservationEnvelope、ObserverOutcome、evaluate_observer_outcome |
| [product/protocols/preparation/__init__.py](../../../product/protocols/preparation/__init__.py) | 1 | 包、内部机制或样式 |
| [product/protocols/preparation/api_source.py](../../../product/protocols/preparation/api_source.py) | 70 | SourceParameter、SourceRequest、ApiSourceReference、ApiSourceDocument、ApiImportDocument、parse_source_document |
| [product/protocols/preparation/flow_trial.py](../../../product/protocols/preparation/flow_trial.py) | 97 | TrialCase、FlowTrialRuntime、FlowTrialPlan、FlowTrialRequest、FlowTrialRunnerInput、FlowTrialStep、FlowTrialReport |
| [product/protocols/preparation/http_entity.py](../../../product/protocols/preparation/http_entity.py) | 37 | HttpEntityQuery、HttpEntityEvidence |
| [product/protocols/preparation/operation_flow.py](../../../product/protocols/preparation/operation_flow.py) | 140 | operation_resource_injection、OperationFlow、OperationFlowDraft |
| [product/protocols/preparation/proof_artifacts.py](../../../product/protocols/preparation/proof_artifacts.py) | 34 | ProofArtifactInput |
| [product/protocols/preparation/proof_sources.py](../../../product/protocols/preparation/proof_sources.py) | 484 | safe_source_path、SourceIdentityClaim、ProofSourceConfig、safe_identity_path、ManagedIdentityClaim、ManagedProofSourceConfig、source_identity_paths、source_read_paths等 |
| [product/protocols/preparation/reference_capture.py](../../../product/protocols/preparation/reference_capture.py) | 190 | CaptureActionConfig、CaptureRuntimeConfig、CaptureResourceSource、CaptureCase、CaptureRecoveryReference、ReferenceCaptureBaseline、ReferenceCapturePlan、ReferenceCaptureRequest等 |
| [product/protocols/preparation/test_identity_preparation.py](../../../product/protocols/preparation/test_identity_preparation.py) | 165 | IdentityPreparationResultType、IdentityPreparationRequest、PreparedCookieRef、IdentityPreparationResult、canonical_identity_preparation_json_bytes、parse_identity_preparation_request、parse_identity_preparation_result |
| [product/protocols/recording/__init__.py](../../../product/protocols/recording/__init__.py) | 1 | 包、内部机制或样式 |
| [product/protocols/recording/created_resource.py](../../../product/protocols/recording/created_resource.py) | 77 | resource_identifier、location_resource、response_object_candidates |
| [product/protocols/recording/events.py](../../../product/protocols/recording/events.py) | 547 | RecordingProtocolModel、RecordingRunnerResultType、RecordingCleanupStatus、RecordingEventKind、RecordingAuthMethod、RecordingBudget、RecordingCookieRef、RecordingSessionRef等 |
| [product/protocols/recording/flow_draft.py](../../../product/protocols/recording/flow_draft.py) | 469 | FlowDraftProtocolModel、FlowDraftVariableStatus、FlowDraftVariableSource、FlowDraftVariable、FlowDraftResourceCandidate、FlowDraftStep、FlowDraft、ConfirmFlowDraftVariableChoice等 |
| [product/protocols/recording/recording_flow.py](../../../product/protocols/recording/recording_flow.py) | 150 | RecordingFlowModel、FlowVariableSource、FlowStep、Flow |
| [product/protocols/report.py](../../../product/protocols/report.py) | 590 | ReportModel、ReportEvidenceRef、ReportFinding、ReportObserverStatus、ReportRuntime、ReportArtifact、ArtifactSummaryStatus、ArtifactSummary等 |
| [product/protocols/runner/__init__.py](../../../product/protocols/runner/__init__.py) | 1 | 包、内部机制或样式 |
| [product/protocols/runner/codec.py](../../../product/protocols/runner/codec.py) | 109 | canonical_runner_json_bytes、canonical_runner_sha256、parse_runner_input、parse_runner_result、parse_evidence |
| [product/protocols/runner/evidence.py](../../../product/protocols/runner/evidence.py) | 235 | Evidence、build_evidence |
| [product/protocols/runner/execution.py](../../../product/protocols/runner/execution.py) | 105 | ProtocolModel、ExecutionBudget、SubjectExecutionBinding、ObserverRequirementKind、EffectClosurePolicy、EffectBinding、ObserverRequirementBinding |
| [product/protocols/runner/input.py](../../../product/protocols/runner/input.py) | 160 | RunnerResultType、CleanupStatus、RunnerFailurePhase、CleanupIssueCode、ResourceInjection、RunnerInput |
| [product/protocols/runner/result.py](../../../product/protocols/runner/result.py) | 228 | CleanupIssue、CleanupResult、RunnerError、StagedArtifact、RunnerResult |
| [product/protocols/runtime/__init__.py](../../../product/protocols/runtime/__init__.py) | 1 | 包、内部机制或样式 |
| [product/protocols/runtime/creation_records.py](../../../product/protocols/runtime/creation_records.py) | 58 | ScopedRecordSeed、RecordRemove、CreationMember、CreationEvent、CreationView |
| [product/protocols/runtime/frontend_assets.py](../../../product/protocols/runtime/frontend_assets.py) | 30 | FrontendAsset、FrontendAssetManifest |
| [product/protocols/runtime/node_runtime.py](../../../product/protocols/runtime/node_runtime.py) | 158 | SqliteTableCapture、SqliteDatabaseCapture、NodePackagePlan、NodeRuntimeManifest、NodeRuntimeLoadRequest、NodeRuntimeReference、NodeBuildArtifact、NodeRuntimeLoadReceipt等 |
| [product/protocols/runtime/portable_release.py](../../../product/protocols/runtime/portable_release.py) | 19 | PortableReleaseManifest |
| [product/protocols/runtime/portable_update.py](../../../product/protocols/runtime/portable_update.py) | 67 | PortableUpdateFile、PortableWorkspaceIdentity、PortableUpdateManifest、PortableUpdateOperation、PortableExitReceipt |
| [product/protocols/runtime/record_trace.py](../../../product/protocols/runtime/record_trace.py) | 73 | RecordTraceInput、RecordTraceWrite、RecordTraceEvent、RecordTraceReceipt、RecordTraceLog |
| [product/protocols/runtime/request_activity.py](../../../product/protocols/runtime/request_activity.py) | 69 | ActivityEvent、RequestActivity |
| [product/protocols/runtime/runtime_identity.py](../../../product/protocols/runtime/runtime_identity.py) | 109 | RuntimeModel、RuntimeFile、runtime_source_fingerprint、RuntimeLaunchManifest、runtime_manifest_fingerprint、RuntimeLaunchReceipt、ControlledRuntimeReference、RuntimeCorrespondence等 |
| [product/protocols/runtime/transaction_records.py](../../../product/protocols/runtime/transaction_records.py) | 180 | bounded_record_data、RecordChange、RecordSeed、RecordSnapshot、RecordTransition、RecordProviderReference、RecordProofRequest、RecordRequestScope等 |
| [product/protocols/schema.py](../../../product/protocols/schema.py) | 173 | SchemaEntry、render_schema、synchronize_schemas、main |
| [product/protocols/web/__init__.py](../../../product/protocols/web/__init__.py) | 93 | 包、内部机制或样式 |
| [product/protocols/web/base.py](../../../product/protocols/web/base.py) | 6 | ProtocolModel |
| [product/protocols/web/environment.py](../../../product/protocols/web/environment.py) | 47 | FrozenEnvironment、EnvironmentDocument、parse_environment_document |
| [product/protocols/web/identity.py](../../../product/protocols/web/identity.py) | 359 | HttpIdentityKind、IdentityBootstrapRequest、AuthTargetScope、AnonymousIdentityBinding、BearerIdentityBinding、StaticHeaderCredential、StaticHeadersIdentityBinding、CookieSessionIdentityBinding等 |
| [product/protocols/web/profile.py](../../../product/protocols/web/profile.py) | 540 | WebExecutionSnapshot、required_web_secret_refs、WebExecutionProfile、canonical_web_execution_profile_json_bytes、web_execution_profile_sha256、parse_web_execution_profile |
| [product/protocols/web/request.py](../../../product/protocols/web/request.py) | 368 | HttpBodyKind、ValueSlotSource、ValueSlotConsumer、ValueType、ValueSlot、HttpParameter、MultipartPart、EmptyBody等 |
| [product/protocols/web/response.py](../../../product/protocols/web/response.py) | 305 | ResponseExtractorKind、HttpPredicateKind、HttpOutcome、ResponseExtractor、HttpPredicate、HttpOutcomeClassifier |
| [product/protocols/web/target.py](../../../product/protocols/web/target.py) | 112 | WebTargetScope、WebTargetDefinition |
| [product/protocols/web/workflow.py](../../../product/protocols/web/workflow.py) | 275 | WorkflowStepPurpose、WorkflowFailurePolicy、ResetStrategyKind、BaselineIntegrityMode、LogicalResourceSlot、BaselineProjection、ResetEndpointStrategy、UniqueResourceWorkflowResetStrategy等 |
