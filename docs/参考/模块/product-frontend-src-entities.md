# product/frontend/src/entities 模块

<!-- generated:modules -->

[返回总索引](../模块索引.md)

按目录定位后读取对应小节；每个文件有独立标题，源码链接用于核对声明与直接消费者。行数和公开声明由静态提取，不表示运行验收。

按目录定位：[application/api](#applicationapi)（4 个文件）、[check/api](#checkapi)（4 个文件）、[check](#check)（1 个文件）、[check/model](#checkmodel)（1 个文件）、[check/ui](#checkui)（10 个文件）、[permission/api](#permissionapi)（3 个文件）、[permission/ui](#permissionui)（4 个文件）、[preparation/api](#preparationapi)（10 个文件）、[preparation/ui](#preparationui)（11 个文件）、[runtime/api](#runtimeapi)（3 个文件）、[runtime/model](#runtimemodel)（1 个文件）、[runtime/ui](#runtimeui)（2 个文件）、[source-change/api](#source-changeapi)（2 个文件）、[source-change/ui](#source-changeui)（4 个文件）、[workspace/api](#workspaceapi)（1 个文件）、[workspace](#workspace)（2 个文件）。

## application/api

### application/api/experience.ts

[源码](../../../product/frontend/src/entities/application/api/experience.ts)（102 行）。公开声明：`CompetitionValidationSummaryDto`、`CompetitionValidationSummaryViewDto`、`OfficialBoundaryDraftDto`、`OfficialDevelopmentJourneyDto`、`OfficialExperienceDto`、`OfficialScenarioVersion`、`experienceApi`。

### application/api/onboarding.ts

[源码](../../../product/frontend/src/entities/application/api/onboarding.ts)（41 行）。公开声明：`DiscoveryCandidate`、`DiscoveryHint`、`DiscoveryResult`、`onboardingApi`、`selectFolderPath`。

### application/api/projects.ts

[源码](../../../product/frontend/src/entities/application/api/projects.ts)（164 行）。公开声明：`ActionCandidateDto`、`ApplicationActivity`、`ApplicationConnectionDto`、`ApplicationReadiness`、`ApplicationUnderstandingDto`、`CandidateEvidenceDto`、`CandidateSelection`、`ConnectionChoice`等。

### application/api/workbench.ts

[源码](../../../product/frontend/src/entities/application/api/workbench.ts)（29 行）。公开声明：`ApiSource`、`ApplicationEnvironment`、`EnvironmentContext`、`EnvironmentImpact`、`ImportPreview`、`SourceAnnotation`、`SourceRequest`、`SourcesContext`等。

## check/api

### check/api/comparison.ts

[源码](../../../product/frontend/src/entities/check/api/comparison.ts)（15 行）。公开声明：`ChangeKind`、`ComparisonItem`、`ComparisonObservation`、`ComparisonRun`、`RunComparison`、`comparisonApi`。

### check/api/currentChecks.ts

[源码](../../../product/frontend/src/entities/check/api/currentChecks.ts)（175 行）。公开声明：`ActionResultStory`、`ActivityEvent`、`CheckBreakpoint`、`CheckContinuation`、`CheckEvidence`、`CheckHistoryCursor`、`CheckHistoryItem`、`CheckHistoryPage`等。

### check/api/repairs.ts

[源码](../../../product/frontend/src/entities/check/api/repairs.ts)（27 行）。公开声明：`ProjectRepair`、`RepairComparisonRow`、`RepairContract`、`RepairHistoryEvent`、`RepairReference`、`RepairStatus`、`RepairVerification`、`repairLabels`等。

### check/api/routines.ts

[源码](../../../product/frontend/src/entities/check/api/routines.ts)（32 行）。公开声明：`BindRoutine`、`CheckRoutine`、`LegacySelection`、`RoutineAsset`、`RoutineBinding`、`RoutineBindingPreview`、`RoutineCatalog`、`RoutineLimits`等。

## check

### check/issueDestination.ts

[源码](../../../product/frontend/src/entities/check/issueDestination.ts)（14 行）。公开声明：`issueDestination`。

## check/model

### check/model/checks.ts

[源码](../../../product/frontend/src/entities/check/model/checks.ts)（62 行）。公开声明：`Tone`、`actual`、`gaps`、`judgement`、`judgementLabels`、`owner`、`repairGap`、`requirement`等。

## check/ui

### check/ui/AgentHandoff.tsx

[源码](../../../product/frontend/src/entities/check/ui/AgentHandoff.tsx)（32 行）。公开声明：`AgentHandoff`。

### check/ui/ExternalRecheck.tsx

[源码](../../../product/frontend/src/entities/check/ui/ExternalRecheck.tsx)（53 行）。公开声明：`ExternalRecheck`。

### check/ui/LegacyRepairRedirect.tsx

[源码](../../../product/frontend/src/entities/check/ui/LegacyRepairRedirect.tsx)（14 行）。公开声明：`LegacyRepairRedirect`。

### check/ui/recheck.css

[源码](../../../product/frontend/src/entities/check/ui/recheck.css)（4 行）。公开声明：包、内部机制或样式。

### check/ui/RepairTask.css

[源码](../../../product/frontend/src/entities/check/ui/RepairTask.css)（23 行）。公开声明：包、内部机制或样式。

### check/ui/RepairTask.tsx

[源码](../../../product/frontend/src/entities/check/ui/RepairTask.tsx)（75 行）。公开声明：`RepairTask`。

### check/ui/RoutineBindingRequirements.tsx

[源码](../../../product/frontend/src/entities/check/ui/RoutineBindingRequirements.tsx)（75 行）。公开声明：`RoutineBindingRequirements`。

### check/ui/RoutineHandoff.tsx

[源码](../../../product/frontend/src/entities/check/ui/RoutineHandoff.tsx)（31 行）。公开声明：`RoutineHandoff`。

### check/ui/RoutinePreparation.tsx

[源码](../../../product/frontend/src/entities/check/ui/RoutinePreparation.tsx)（47 行）。公开声明：`RoutinePreparation`。

### check/ui/RoutineRunContext.tsx

[源码](../../../product/frontend/src/entities/check/ui/RoutineRunContext.tsx)（16 行）。公开声明：`RoutineRunContext`。

## permission/api

### permission/api/businessBoundaries.ts

[源码](../../../product/frontend/src/entities/permission/api/businessBoundaries.ts)（252 行）。公开声明：`BoundaryCandidateDto`、`BoundaryConfidence`、`BoundaryDecisionDto`、`BoundaryDraftViewDto`、`BoundaryEditorDto`、`BoundaryMaintenanceActionDto`、`BoundaryMaintenanceActorDto`、`BoundaryMaintenanceCandidateOptionDto`等。

### permission/api/ruleCandidates.ts

[源码](../../../product/frontend/src/entities/permission/api/ruleCandidates.ts)（70 行）。公开声明：`BoundaryChoice`、`BoundaryReview`、`BoundaryReviewGap`、`CandidateTask`、`CoverageChoice`、`MeaningChoice`、`RequirementSource`、`ReviewDependencies`等。

### permission/api/ruleWorkspace.ts

[源码](../../../product/frontend/src/entities/permission/api/ruleWorkspace.ts)（17 行）。公开声明：`RuleHistory`、`RuleItem`、`RuleState`、`RuleWorkspace`、`ruleWorkspaceApi`。

## permission/ui

### permission/ui/FieldMutation.tsx

[源码](../../../product/frontend/src/entities/permission/ui/FieldMutation.tsx)（27 行）。公开声明：`FieldMutationEditor`、`fieldMutationLabel`、`validFieldMutation`。

### permission/ui/ProposalQueue.css

[源码](../../../product/frontend/src/entities/permission/ui/ProposalQueue.css)（10 行）。公开声明：包、内部机制或样式。

### permission/ui/ProposalQueue.tsx

[源码](../../../product/frontend/src/entities/permission/ui/ProposalQueue.tsx)（34 行）。公开声明：`ProposalQueue`、`RequirementQueue`。

### permission/ui/RuleConditions.tsx

[源码](../../../product/frontend/src/entities/permission/ui/RuleConditions.tsx)（78 行）。公开声明：`RuleConditionFields`、`RuleConditionsEditor`、`conditionLabels`、`relationshipNames`。

## preparation/api

### preparation/api/batches.ts

[源码](../../../product/frontend/src/entities/preparation/api/batches.ts)（13 行）。公开声明：`PreparationBatch`、`PreparationBatchPlan`、`preparationBatchesApi`。

### preparation/api/businessScenarios.ts

[源码](../../../product/frontend/src/entities/preparation/api/businessScenarios.ts)（21 行）。公开声明：`AvailableScenarioCase`、`BusinessScenario`、`FrozenBusinessScenario`、`ScenarioContext`、`ScenarioExperiment`、`ScenarioInvocation`、`ScenarioItem`、`ScenarioListing`等。

### preparation/api/flowTrials.ts

[源码](../../../product/frontend/src/entities/preparation/api/flowTrials.ts)（16 行）。公开声明：`FlowTrial`、`TrialPlan`、`TrialPreview`、`TrialReport`、`TrialSelection`、`flowTrialsApi`。

### preparation/api/operationFlows.ts

[源码](../../../product/frontend/src/entities/preparation/api/operationFlows.ts)（23 行）。公开声明：`ApiCandidate`、`ApiSourceReference`、`EntityEvidence`、`FlowStep`、`OperationContext`、`OperationDirectory`、`OperationFlow`、`operationFlowsApi`。

### preparation/api/preparation.ts

[源码](../../../product/frontend/src/entities/preparation/api/preparation.ts)（88 行）。公开声明：`ActionPreparation`、`AllowControlRequirement`、`EffectMaterialSummary`、`EvidenceMaterialDetail`、`IdentitySlot`、`MaterialChange`、`MaterialDetails`、`MaterialPreview`等。

### preparation/api/preparationGuidance.ts

[源码](../../../product/frontend/src/entities/preparation/api/preparationGuidance.ts)（22 行）。公开声明：`PreparationGuidance`、`PreparationMaterialAdvice`、`PreparationNextAction`。

### preparation/api/preparationSuggestions.ts

[源码](../../../product/frontend/src/entities/preparation/api/preparationSuggestions.ts)（14 行）。公开声明：`MaterialSuggestion`、`PreparationSuggestionContext`、`PreparationSuggestionView`、`SuggestedMaterial`、`SuggestionItemView`。

### preparation/api/proofSources.ts

[源码](../../../product/frontend/src/entities/preparation/api/proofSources.ts)（76 行）。公开声明：`AdoptionPreview`、`ArtifactManifest`、`AsyncExportMapping`、`CapturePlan`、`CaptureSelection`、`CaptureStatus`、`ProofConfig`、`ProofContext`等。

### preparation/api/recordings.ts

[源码](../../../product/frontend/src/entities/preparation/api/recordings.ts)（146 行）。公开声明：`FlowDraftDto`、`FlowDraftStepDto`、`FlowDraftVariableDto`、`FlowDraftVariableSourceDto`、`RecordingActionDto`、`RecordingCreateInput`、`RecordingDto`、`RecordingJobDto`等。

### preparation/api/testIdentities.ts

[源码](../../../product/frontend/src/entities/preparation/api/testIdentities.ts)（86 行）。公开声明：`AuthenticationOptions`、`AuthenticationProfile`、`IdentityPreparationDto`、`IdentityPreparationStatus`、`IdentityVerification`、`TestIdentityAuthMethod`、`TestIdentityDto`、`TestIdentityStatus`等。

## preparation/ui

### preparation/ui/AsyncExportFields.tsx

[源码](../../../product/frontend/src/entities/preparation/ui/AsyncExportFields.tsx)（36 行）。公开声明：`AsyncExportFields`、`asyncExportReady`、`emptyAsyncExport`。

### preparation/ui/EntityEvidenceEditor.tsx

[源码](../../../product/frontend/src/entities/preparation/ui/EntityEvidenceEditor.tsx)（10 行）。公开声明：`EntityEvidenceEditor`、`EvidenceEffect`。

### preparation/ui/flow-comparison.css

[源码](../../../product/frontend/src/entities/preparation/ui/flow-comparison.css)（8 行）。公开声明：包、内部机制或样式。

### preparation/ui/FlowCandidateReview.tsx

[源码](../../../product/frontend/src/entities/preparation/ui/FlowCandidateReview.tsx)（51 行）。公开声明：`FlowCandidateReview`、`FlowComparison`、`FlowComparisonBaseline`、`flowDraftKey`。

### preparation/ui/flowDraft.ts

[源码](../../../product/frontend/src/entities/preparation/ui/flowDraft.ts)（35 行）。公开声明：`FlowDraftAction`、`FlowEditorDraft`、`flowDraftReducer`。

### preparation/ui/flowInputs.ts

[源码](../../../product/frontend/src/entities/preparation/ui/flowInputs.ts)（110 行）。公开声明：`EditableStep`、`FlowParameter`、`InputLocation`、`InputSource`、`compileSteps`、`decodeSteps`、`newParameter`、`sensitiveParameter`。

### preparation/ui/FlowRequestInputs.tsx

[源码](../../../product/frontend/src/entities/preparation/ui/FlowRequestInputs.tsx)（51 行）。公开声明：`FlowRequestInputs`。

### preparation/ui/FlowTrialPanel.tsx

[源码](../../../product/frontend/src/entities/preparation/ui/FlowTrialPanel.tsx)（105 行）。公开声明：`FlowTrialPanel`。

### preparation/ui/operation-flow.css

[源码](../../../product/frontend/src/entities/preparation/ui/operation-flow.css)（136 行）。公开声明：包、内部机制或样式。

### preparation/ui/OperationFlowEditor.tsx

[源码](../../../product/frontend/src/entities/preparation/ui/OperationFlowEditor.tsx)（198 行）。公开声明：`OperationFlowEditor`。

### preparation/ui/RelationshipMapping.tsx

[源码](../../../product/frontend/src/entities/preparation/ui/RelationshipMapping.tsx)（45 行）。公开声明：`RelationshipMapping`、`emptyRelationshipMapping`、`relationshipMappingFields`、`relationshipMappingReady`。

## runtime/api

### runtime/api/collaboration.ts

[源码](../../../product/frontend/src/entities/runtime/api/collaboration.ts)（35 行）。公开声明：`CollaborationCapability`、`CollaborationCheck`、`CollaborationEditor`、`CollaborationExecutor`、`CollaborationOperation`、`CollaborationPurpose`、`CollaborationTask`、`FlowHandoff`等。

### runtime/api/mcp.ts

[源码](../../../product/frontend/src/entities/runtime/api/mcp.ts)（61 行）。公开声明：`AgentClient`、`AgentConnection`、`MCPAccessCredentialView`、`MCPAccessLevel`、`MCPAccessView`、`MCPConnectionState`、`MCPProjectGrant`、`agentClients`等。

### runtime/api/system.ts

[源码](../../../product/frontend/src/entities/runtime/api/system.ts)（75 行）。公开声明：`ExitReceipt`、`MaintenanceEntry`、`MaintenanceOperation`、`MaintenanceOperationResult`、`MaintenanceStatus`、`RuntimeDiagnostics`、`SystemStatus`、`UpdateInfo`等。

## runtime/model

### runtime/model/handoff.ts

[源码](../../../product/frontend/src/entities/runtime/model/handoff.ts)（54 行）。公开声明：`HandoffContext`、`clearSubmittedDraft`、`discardProjectEditorDrafts`、`editorDraft`、`editorDraftGeneration`、`rememberEditorDraft`、`requestCollaboration`、`routeReferences`等。

## runtime/ui

### runtime/ui/CollaborationComposer.tsx

[源码](../../../product/frontend/src/entities/runtime/ui/CollaborationComposer.tsx)（26 行）。公开声明：`CollaborationComposer`。

### runtime/ui/CollaborationEntry.tsx

[源码](../../../product/frontend/src/entities/runtime/ui/CollaborationEntry.tsx)（54 行）。公开声明：`CollaborationEntry`。

## source-change/api

### source-change/api/development.ts

[源码](../../../product/frontend/src/entities/source-change/api/development.ts)（32 行）。公开声明：`DeliveryDetails`、`DeliveryPage`、`DeliverySubmission`、`DevelopmentContext`、`DevelopmentDelivery`、`DevelopmentReceipt`、`DevelopmentTask`、`DevelopmentView`等。

### source-change/api/sourceChanges.ts

[源码](../../../product/frontend/src/entities/source-change/api/sourceChanges.ts)（23 行）。公开声明：`RegistrationPreview`、`RuleChangeTarget`、`SourceChangeViewDto`、`sourceChangesApi`。

## source-change/ui

### source-change/ui/ChangePreview.tsx

[源码](../../../product/frontend/src/entities/source-change/ui/ChangePreview.tsx)（7 行）。公开声明：`ChangePreview`。

### source-change/ui/ChangeRegistration.tsx

[源码](../../../product/frontend/src/entities/source-change/ui/ChangeRegistration.tsx)（86 行）。公开声明：`ChangeRegistration`、`changeTargetOptions`。

### source-change/ui/RuntimeActivation.tsx

[源码](../../../product/frontend/src/entities/source-change/ui/RuntimeActivation.tsx)（41 行）。公开声明：`RuntimeActivation`。

### source-change/ui/styles.css

[源码](../../../product/frontend/src/entities/source-change/ui/styles.css)（39 行）。公开声明：包、内部机制或样式。

## workspace/api

### workspace/api/workspace.ts

[源码](../../../product/frontend/src/entities/workspace/api/workspace.ts)（134 行）。公开声明：`ActionWorkspaceDto`、`ActorWorkspaceDto`、`PrimaryTaskDto`、`PrimaryTaskKind`、`WorkspaceAreaDto`、`WorkspaceConnectionDto`、`WorkspaceProjectDto`、`WorkspaceViewDto`等。

## workspace

### workspace/PreparationNext.tsx

[源码](../../../product/frontend/src/entities/workspace/PreparationNext.tsx)（16 行）。公开声明：`PreparationNext`。

### workspace/taskDestination.ts

[源码](../../../product/frontend/src/entities/workspace/taskDestination.ts)（27 行）。公开声明：`taskDestination`。
