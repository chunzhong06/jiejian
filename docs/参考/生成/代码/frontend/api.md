# 自动代码参考：frontend/api

> 自动生成。当前源码结构与注册投影，不代表运行验收或完整调用图。

<!-- GENERATED:START -->

### `product/frontend/src/api/applications/controlledRuntime.ts`

[打开源码](../../../../../product/frontend/src/api/applications/controlledRuntime.ts) · JS/TS词法提取；re-export、条件和动态表达式需读源码确认。

- `RuntimeOperation`
- `RuntimePreview`
- `RuntimeState`
- `controlledRuntimeApi`

静态import / dot-source：`../http`

### `product/frontend/src/api/applications/experience.ts`

[打开源码](../../../../../product/frontend/src/api/applications/experience.ts) · JS/TS词法提取；re-export、条件和动态表达式需读源码确认。

- `CompetitionValidationSummaryDto`
- `CompetitionValidationSummaryViewDto`
- `OfficialDevelopmentJourneyDto`
- `OfficialExperienceDto`
- `OfficialScenarioVersion`
- `experienceApi`

静态import / dot-source：`../boundaries/businessBoundaries`、`../checks/repairs`、`../http`

### `product/frontend/src/api/applications/onboarding.ts`

[打开源码](../../../../../product/frontend/src/api/applications/onboarding.ts) · JS/TS词法提取；re-export、条件和动态表达式需读源码确认。

- `DiscoveryCandidate`
- `DiscoveryHint`
- `DiscoveryResult`
- `onboardingApi`

静态import / dot-source：`../http`

### `product/frontend/src/api/applications/projects.ts`

[打开源码](../../../../../product/frontend/src/api/applications/projects.ts) · JS/TS词法提取；re-export、条件和动态表达式需读源码确认。

- `ActionCandidateDto`
- `ApplicationConnectionDto`
- `ApplicationUnderstandingDto`
- `CandidateEvidenceDto`
- `CandidateSelection`
- `EndpointCandidateDto`
- `EndpointDiscoveryDto`
- `ProjectDto`
- `RoleCandidateDto`
- `projectsApi`

静态import / dot-source：`../http`、`./onboarding`

### `product/frontend/src/api/assistance/assistant.ts`

[打开源码](../../../../../product/frontend/src/api/assistance/assistant.ts) · JS/TS词法提取；re-export、条件和动态表达式需读源码确认。

- `AssistantEntity`
- `AssistantFocus`
- `AssistantSuggestion`
- `AssistantSurfaceView`
- `ProjectAssistantSurface`
- `assistantApi`

静态import / dot-source：`../http`

### `product/frontend/src/api/assistance/llm.ts`

[打开源码](../../../../../product/frontend/src/api/assistance/llm.ts) · JS/TS词法提取；re-export、条件和动态表达式需读源码确认。

- `AIAssistanceSettings`
- `LLMConnectionStatus`
- `LLMModelCatalog`
- `LLMModelOption`
- `LLMProfile`
- `LLMProfileWrite`
- `LLMProvider`
- `llmApi`

静态import / dot-source：`../http`

### `product/frontend/src/api/boundaries/businessBoundaries.ts`

[打开源码](../../../../../product/frontend/src/api/boundaries/businessBoundaries.ts) · JS/TS词法提取；re-export、条件和动态表达式需读源码确认。

- `BoundaryCandidateDto`
- `BoundaryConfidence`
- `BoundaryDecisionDto`
- `BoundaryDraftViewDto`
- `BoundaryEditorDto`
- `BoundaryMaintenanceActionDto`
- `BoundaryMaintenanceActorDto`
- `BoundaryMaintenanceCandidateOptionDto`
- `BoundaryMaintenanceCommandDto`
- `BoundaryMaintenanceDraftDto`
- `BoundaryMaintenancePermissionDto`
- `BoundaryProposalChangeSummaryDto`
- `BoundaryProposalCommandDto`
- `BoundaryProposalDto`
- `BoundaryProposalListDto`
- `BoundaryProposalReviewDto`
- `BoundaryProposalViewDto`
- `BoundaryReviewValueDto`
- `BusinessActionRevisionDto`
- `BusinessActorRevisionDto`
- `BusinessBoundaryViewDto`
- `BusinessEffectKind`
- `ImplementationInspectionDto`
- `PermissionBoundaryStatusDto`
- `PermissionIntentRevisionDto`
- `ProposedActionDto`
- `ProposedActorDto`
- `ProposedEffectDto`
- `ProposedPermissionDto`
- `businessBoundariesApi`

静态import / dot-source：`../http`

### `product/frontend/src/api/boundaries/permissionDrafts.ts`

[打开源码](../../../../../product/frontend/src/api/boundaries/permissionDrafts.ts) · JS/TS词法提取；re-export、条件和动态表达式需读源码确认。

- `PermissionDraftSuggestion`
- `PermissionDraftView`
- `permissionDraftsApi`

静态import / dot-source：`../http`、`./businessBoundaries`

### `product/frontend/src/api/boundaries/ruleCandidates.ts`

[打开源码](../../../../../product/frontend/src/api/boundaries/ruleCandidates.ts) · JS/TS词法提取；re-export、条件和动态表达式需读源码确认。

- `RuleCandidateContext`
- `RuleCandidateView`
- `ruleCandidatesApi`

静态import / dot-source：`../http`、`./businessBoundaries`

### `product/frontend/src/api/boundaries/ruleDetails.ts`

[打开源码](../../../../../product/frontend/src/api/boundaries/ruleDetails.ts) · JS/TS词法提取；re-export、条件和动态表达式需读源码确认。

- `RuleDetails`
- `ruleDetailsApi`

静态import / dot-source：`../http`

### `product/frontend/src/api/changes/development.ts`

[打开源码](../../../../../product/frontend/src/api/changes/development.ts) · JS/TS词法提取；re-export、条件和动态表达式需读源码确认。

- `DeliveryDetails`
- `DeliveryPage`
- `DeliverySubmission`
- `DevelopmentContext`
- `DevelopmentDelivery`
- `DevelopmentReceipt`
- `DevelopmentTask`
- `DevelopmentView`
- `OperationKind`
- `RuntimeActivationReceipt`
- `TaskHistoryItem`
- `TaskHistoryPage`
- `developmentApi`
- `newOperationId`

静态import / dot-source：`../http`、`./sourceChanges`

### `product/frontend/src/api/changes/sourceChanges.ts`

[打开源码](../../../../../product/frontend/src/api/changes/sourceChanges.ts) · JS/TS词法提取；re-export、条件和动态表达式需读源码确认。

- `RegistrationPreview`
- `SourceChangeViewDto`
- `sourceChangesApi`

静态import / dot-source：`../checks/repairs`、`../http`、`./development`

### `product/frontend/src/api/changes/sourceIdentity.ts`

[打开源码](../../../../../product/frontend/src/api/changes/sourceIdentity.ts) · JS/TS词法提取；re-export、条件和动态表达式需读源码确认。

- `SourceIdentity`
- `sourceIdentityApi`

静态import / dot-source：`../http`

### `product/frontend/src/api/checks/currentChecks.ts`

[打开源码](../../../../../product/frontend/src/api/checks/currentChecks.ts) · JS/TS词法提取；re-export、条件和动态表达式需读源码确认。

- `ActionResultStory`
- `CheckBreakpoint`
- `CheckEvidence`
- `CheckHistoryCursor`
- `CheckHistoryItem`
- `CheckHistoryPage`
- `CheckHistoryQuery`
- `CheckObservation`
- `CheckOutcome`
- `CheckPreview`
- `CheckProgressCase`
- `CheckStatus`
- `CheckVerdict`
- `EvidenceExplanation`
- `ObservationReading`
- `ResultStory`
- `StoryExecutionPath`
- `StoryIdentity`
- `StoryProofCoverage`
- `StoryTraceEvent`
- `currentChecksApi`

静态import / dot-source：`../http`、`./repairs`

### `product/frontend/src/api/checks/repairs.ts`

[打开源码](../../../../../product/frontend/src/api/checks/repairs.ts) · JS/TS词法提取；re-export、条件和动态表达式需读源码确认。

- `ProjectRepair`
- `RepairComparisonRow`
- `RepairContract`
- `RepairReference`
- `RepairStatus`
- `RepairVerification`
- `repairLabels`
- `repairReference`
- `repairsApi`

静态import / dot-source：`../http`

### `product/frontend/src/api/http.test.ts`

[打开源码](../../../../../product/frontend/src/api/http.test.ts) · JS/TS词法提取；re-export、条件和动态表达式需读源码确认。


静态import / dot-source：`./http`、`vitest`

### `product/frontend/src/api/http.ts`

[打开源码](../../../../../product/frontend/src/api/http.ts) · JS/TS词法提取；re-export、条件和动态表达式需读源码确认。

- `ApiEnvelope`
- `ApiError`
- `ErrorDiagnosis`
- `request`

### `product/frontend/src/api/preparation/jobs.ts`

[打开源码](../../../../../product/frontend/src/api/preparation/jobs.ts) · JS/TS词法提取；re-export、条件和动态表达式需读源码确认。

- `CancelJobDto`
- `JobEventDto`
- `jobsApi`

静态import / dot-source：`../http`

### `product/frontend/src/api/preparation/preparation.ts`

[打开源码](../../../../../product/frontend/src/api/preparation/preparation.ts) · JS/TS词法提取；re-export、条件和动态表达式需读源码确认。

- `ActionPreparation`
- `AllowControlRequirement`
- `EffectMaterialSummary`
- `EvidenceMaterialDetail`
- `IdentitySlot`
- `MaterialChange`
- `MaterialDetails`
- `MaterialPreview`
- `MaterialReceipt`
- `MaterialRecordingContext`
- `MaterialReference`
- `PermissionReference`
- `PreparationDraft`
- `PreparationItem`
- `PreparationStatus`
- `PreparationView`
- `preparationApi`

静态import / dot-source：`../boundaries/businessBoundaries`、`../http`

### `product/frontend/src/api/preparation/preparationGuidance.ts`

[打开源码](../../../../../product/frontend/src/api/preparation/preparationGuidance.ts) · JS/TS词法提取；re-export、条件和动态表达式需读源码确认。

- `PreparationGuidance`
- `PreparationMaterialAdvice`
- `PreparationNextAction`

### `product/frontend/src/api/preparation/proofSources.ts`

[打开源码](../../../../../product/frontend/src/api/preparation/proofSources.ts) · JS/TS词法提取；re-export、条件和动态表达式需读源码确认。

- `AdoptionPreview`
- `ProofConfig`
- `ProofContext`
- `ProofOperationKind`
- `ProofReceipt`
- `ProofReport`
- `ProofSource`
- `proofSourcesApi`

静态import / dot-source：`../http`、`./preparationGuidance`

### `product/frontend/src/api/preparation/recordings.ts`

[打开源码](../../../../../product/frontend/src/api/preparation/recordings.ts) · JS/TS词法提取；re-export、条件和动态表达式需读源码确认。

- `FlowDraftDto`
- `FlowDraftStepDto`
- `FlowDraftVariableDto`
- `FlowDraftVariableSourceDto`
- `RecordingActionDto`
- `RecordingCreateInput`
- `RecordingDto`
- `RecordingJobDto`
- `RecordingReviewCommand`
- `RecordingSetupDto`
- `RecordingTestIdentityDto`
- `RecordingViewDto`
- `SupplementChoiceDto`
- `recordingsApi`

静态import / dot-source：`../http`

### `product/frontend/src/api/preparation/supplementalMaterials.ts`

[打开源码](../../../../../product/frontend/src/api/preparation/supplementalMaterials.ts) · JS/TS词法提取；re-export、条件和动态表达式需读源码确认。

- `MaterialPreview`
- `SupplementalDocument`
- `SupplementalMaterial`
- `supplementalMaterialsApi`

静态import / dot-source：`../http`

### `product/frontend/src/api/preparation/testIdentities.ts`

[打开源码](../../../../../product/frontend/src/api/preparation/testIdentities.ts) · JS/TS词法提取；re-export、条件和动态表达式需读源码确认。

- `IdentityPreparationDto`
- `IdentityPreparationStatus`
- `TestIdentityAuthMethod`
- `TestIdentityDto`
- `TestIdentityStatus`
- `testIdentitiesApi`

静态import / dot-source：`../http`

### `product/frontend/src/api/system/mcp.ts`

[打开源码](../../../../../product/frontend/src/api/system/mcp.ts) · JS/TS词法提取；re-export、条件和动态表达式需读源码确认。

- `MCPAccessCredentialView`
- `MCPAccessLevel`
- `MCPAccessView`
- `MCPConnectionState`
- `MCPProjectGrant`
- `mcpAccessApi`

静态import / dot-source：`../http`

### `product/frontend/src/api/system/system.test.ts`

[打开源码](../../../../../product/frontend/src/api/system/system.test.ts) · JS/TS词法提取；re-export、条件和动态表达式需读源码确认。


静态import / dot-source：`./system`、`vitest`

### `product/frontend/src/api/system/system.ts`

[打开源码](../../../../../product/frontend/src/api/system/system.ts) · JS/TS词法提取；re-export、条件和动态表达式需读源码确认。

- `MaintenanceEntry`
- `MaintenanceOperation`
- `MaintenanceOperationResult`
- `MaintenanceStatus`
- `SystemStatus`
- `systemApi`

静态import / dot-source：`../http`

### `product/frontend/src/api/workspace.ts`

[打开源码](../../../../../product/frontend/src/api/workspace.ts) · JS/TS词法提取；re-export、条件和动态表达式需读源码确认。

- `ActionWorkspaceDto`
- `ActorWorkspaceDto`
- `PrimaryTaskDto`
- `PrimaryTaskKind`
- `WorkspaceAreaDto`
- `WorkspaceConnectionDto`
- `WorkspaceProjectDto`
- `WorkspaceViewDto`
- `workspaceApi`

静态import / dot-source：`./boundaries/businessBoundaries`、`./checks/currentChecks`、`./checks/repairs`、`./http`

<!-- GENERATED:END -->
