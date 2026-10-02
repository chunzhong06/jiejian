# 自动代码参考：前端

> 生成区域只描述当前代码结构；职责与安全理由由能力映射和任务指南维护。

<!-- GENERATED:START -->

<!-- 此区域由 scripts/docs/generate.py 从 product/frontend/src/ 读取。 -->

### `product/frontend/src/api/assistant.ts`
- `AssistantEntity`
- `AssistantFocus`
- `AssistantSuggestion`
- `AssistantSurfaceView`
- `ProjectAssistantSurface`
- `assistantApi`
主要 import / dot-source：`./http`

### `product/frontend/src/api/businessBoundaries.ts`
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
主要 import / dot-source：`./http`

### `product/frontend/src/api/controlledRuntime.ts`
- `RuntimeOperation`
- `RuntimePreview`
- `RuntimeState`
- `controlledRuntimeApi`
主要 import / dot-source：`./http`

### `product/frontend/src/api/currentChecks.ts`
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
主要 import / dot-source：`./http`, `./repairs`

### `product/frontend/src/api/development.ts`
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
主要 import / dot-source：`./http`, `./sourceChanges`

### `product/frontend/src/api/experience.ts`
- `CompetitionValidationSummaryDto`
- `CompetitionValidationSummaryViewDto`
- `OfficialDevelopmentJourneyDto`
- `OfficialExperienceDto`
- `OfficialScenarioVersion`
- `experienceApi`
主要 import / dot-source：`./businessBoundaries`, `./http`, `./repairs`

### `product/frontend/src/api/http.test.ts`
主要 import / dot-source：`./http`, `vitest`

### `product/frontend/src/api/http.ts`
- `ApiEnvelope`
- `ErrorDiagnosis`
- `ApiError`
- `request`

### `product/frontend/src/api/jobs.ts`
- `CancelJobDto`
- `JobEventDto`
- `jobsApi`
主要 import / dot-source：`./http`

### `product/frontend/src/api/llm.ts`
- `AIAssistanceSettings`
- `LLMConnectionStatus`
- `LLMModelCatalog`
- `LLMModelOption`
- `LLMProfile`
- `LLMProfileWrite`
- `LLMProvider`
- `llmApi`
主要 import / dot-source：`./http`

### `product/frontend/src/api/mcp.ts`
- `MCPAccessCredentialView`
- `MCPAccessLevel`
- `MCPAccessView`
- `MCPConnectionState`
- `MCPProjectGrant`
- `mcpAccessApi`
主要 import / dot-source：`./http`

### `product/frontend/src/api/onboarding.ts`
- `DiscoveryCandidate`
- `DiscoveryHint`
- `DiscoveryResult`
- `onboardingApi`
主要 import / dot-source：`./http`

### `product/frontend/src/api/permissionDrafts.ts`
- `PermissionDraftSuggestion`
- `PermissionDraftView`
- `permissionDraftsApi`
主要 import / dot-source：`./businessBoundaries`, `./http`

### `product/frontend/src/api/preparation.ts`
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
主要 import / dot-source：`./businessBoundaries`, `./http`

### `product/frontend/src/api/preparationGuidance.ts`
- `PreparationGuidance`
- `PreparationMaterialAdvice`
- `PreparationNextAction`

### `product/frontend/src/api/projects.ts`
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
主要 import / dot-source：`./http`, `./onboarding`

### `product/frontend/src/api/proofSources.ts`
- `AdoptionPreview`
- `ProofConfig`
- `ProofContext`
- `ProofOperationKind`
- `ProofReceipt`
- `ProofReport`
- `ProofSource`
- `proofSourcesApi`
主要 import / dot-source：`./http`, `./preparationGuidance`

### `product/frontend/src/api/recordings.ts`
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
主要 import / dot-source：`./http`

### `product/frontend/src/api/repairs.ts`
- `ProjectRepair`
- `RepairComparisonRow`
- `RepairContract`
- `RepairReference`
- `RepairStatus`
- `RepairVerification`
- `repairLabels`
- `repairReference`
- `repairsApi`
主要 import / dot-source：`./http`

### `product/frontend/src/api/ruleCandidates.ts`
- `RuleCandidateContext`
- `RuleCandidateView`
- `ruleCandidatesApi`
主要 import / dot-source：`./businessBoundaries`, `./http`

### `product/frontend/src/api/ruleDetails.ts`
- `RuleDetails`
- `ruleDetailsApi`
主要 import / dot-source：`./http`

### `product/frontend/src/api/sourceChanges.ts`
- `RegistrationPreview`
- `SourceChangeViewDto`
- `sourceChangesApi`
主要 import / dot-source：`./development`, `./http`, `./repairs`

### `product/frontend/src/api/sourceIdentity.ts`
- `SourceIdentity`
- `sourceIdentityApi`
主要 import / dot-source：`./http`

### `product/frontend/src/api/supplementalMaterials.ts`
- `MaterialPreview`
- `SupplementalDocument`
- `SupplementalMaterial`
- `supplementalMaterialsApi`
主要 import / dot-source：`./http`

### `product/frontend/src/api/system.test.ts`
主要 import / dot-source：`./system`, `vitest`

### `product/frontend/src/api/system.ts`
- `MaintenanceEntry`
- `MaintenanceOperation`
- `MaintenanceOperationResult`
- `MaintenanceStatus`
- `SystemStatus`
- `systemApi`
主要 import / dot-source：`./http`

### `product/frontend/src/api/testIdentities.ts`
- `IdentityPreparationDto`
- `IdentityPreparationStatus`
- `TestIdentityAuthMethod`
- `TestIdentityDto`
- `TestIdentityStatus`
- `testIdentitiesApi`
主要 import / dot-source：`./http`

### `product/frontend/src/api/workspace.ts`
- `ActionWorkspaceDto`
- `ActorWorkspaceDto`
- `PrimaryTaskDto`
- `PrimaryTaskKind`
- `WorkspaceAreaDto`
- `WorkspaceConnectionDto`
- `WorkspaceProjectDto`
- `WorkspaceViewDto`
- `workspaceApi`
主要 import / dot-source：`./businessBoundaries`, `./currentChecks`, `./http`, `./repairs`

### `product/frontend/src/app/AppHeader.tsx`
- `AppHeader`
- `aiStatusLabel`
- `mcpStatusLabel`
- `systemStatusLabel`
主要 import / dot-source：`../api/llm`, `../api/mcp`, `../api/projects`, `../api/system`, `./ThemeContext`, `./navigation/ApplicationSwitcher`, `@ant-design/icons`, `antd`, `react`

### `product/frontend/src/app/browserState.ts`
- `browserState`
主要 import / dot-source：`../api/projects`, `../api/recordings`

### `product/frontend/src/app/buildIdentity.ts`
- `frontendBuildId`
- `frontendIdentityState`
主要 import / dot-source：`../api/system`

### `product/frontend/src/app/ControlShell.test.tsx`
主要 import / dot-source：`../api/experience`, `../api/workspace`, `./ControlShell`, `./ThemeContext`, `./tasks/TaskContinuity`, `@testing-library/react`, `react`, `vitest`

### `product/frontend/src/app/ControlShell.tsx`
- `ControlShell`
主要 import / dot-source：`../api/experience`, `../api/http`, `../api/mcp`, `../api/projects`, `../api/system`, `../api/workspace`, `../features/access/AccessPage`, `../features/boundaries/BusinessBoundaryPage`, `../features/changes/ChangesPage`, `../features/checks/CurrentTestsPage`, `../features/environment/EnvironmentPage`, `../features/environment/OfficialDevelopmentJourney`, `../features/environment/OfficialSamplePanel`, `../features/history/CheckHistoryPage`, `../features/settings/LLMSettingsDrawer`, `../features/system/RuntimePage`, `../features/tools/ToolsPage`, `../features/workspace/WorkbenchPage`, `./AppHeader`, `./FrontendBuildNotice`, `./NotificationCenter`, `./RetainedWorkPages`, `./navigation/ModuleNavigation`, `./presentation`, `./shell/ErrorRecovery`, `./tasks/TaskContinuity`, `./useCheckActivity`, `./useProjectWorkspace`, `./useSystemStatus`, `antd`, `react`, `react-router-dom`

### `product/frontend/src/app/FrontendBuildNotice.test.tsx`
主要 import / dot-source：`./FrontendBuildNotice`, `./buildIdentity`, `@testing-library/react`, `vitest`

### `product/frontend/src/app/FrontendBuildNotice.tsx`
- `FrontendBuildNotice`
主要 import / dot-source：`../api/system`, `./buildIdentity`, `@ant-design/icons`, `antd`, `react`

### `product/frontend/src/app/navigation/AgentNavigation.tsx`
- `CollaborationView`
- `AgentNavigation`

### `product/frontend/src/app/navigation/AgentPageHeader.tsx`
- `AgentPageHeader`
主要 import / dot-source：`../../shared/ui/Editorial`, `./AgentNavigation`, `antd`, `react`

### `product/frontend/src/app/navigation/ApplicationSwitcher.tsx`
- `ApplicationSwitcher`
主要 import / dot-source：`../../api/projects`, `@ant-design/icons`, `antd`

### `product/frontend/src/app/navigation/ModuleNavigation.tsx`
- `DesktopModuleNavigation`
- `MobileModuleNavigation`
主要 import / dot-source：`../../api/system`, `../../api/workspace`, `../AppHeader`, `../presentation`, `@ant-design/icons`, `antd`

### `product/frontend/src/app/navigation/ProductShellComponents.test.tsx`
主要 import / dot-source：`../../shared/ui/TaskActionBar`, `./ApplicationSwitcher`, `./ModuleNavigation`, `@testing-library/react`, `vitest`

### `product/frontend/src/app/NotificationCenter.test.tsx`
主要 import / dot-source：`../api/http`, `./NotificationCenter`, `@testing-library/react`, `vitest`

### `product/frontend/src/app/NotificationCenter.tsx`
- `NotificationItem`
- `NotificationCenter`
- `enqueueNotification`
- `isNotificationError`
- `notificationDurationMs`
- `notificationKey`
- `removeExpiredNotifications`
- `useNotificationExpiry`
主要 import / dot-source：`../api/http`, `@ant-design/icons`, `antd`, `react`

### `product/frontend/src/app/presentation.ts`
- `AppRoute`
- `ProductAreaRoute`
- `formatTimestamp`
- `lifecycleLabel`
- `lifecycleLabels`
- `normalizeRoute`
- `productAreas`
- `verdictLabel`
- `verdictLabels`

### `product/frontend/src/app/RetainedWorkPages.test.tsx`
主要 import / dot-source：`./RetainedWorkPages`, `@testing-library/react`, `react`, `vitest`

### `product/frontend/src/app/RetainedWorkPages.tsx`
- `RetainedWorkPages`
- `WorkPageVisible`
主要 import / dot-source：`react`

### `product/frontend/src/app/shell/ErrorRecovery.tsx`
- `ErrorRecovery`
主要 import / dot-source：`../../api/http`, `antd`

### `product/frontend/src/app/taskDestination.test.ts`
主要 import / dot-source：`../api/workspace`, `./taskDestination`, `vitest`

### `product/frontend/src/app/taskDestination.ts`
- `taskDestination`
主要 import / dot-source：`../api/workspace`

### `product/frontend/src/app/tasks/TaskContinuity.tsx`
- `TaskGuardContext`
- `TaskJourney`
- `TaskReceipt`
- `useTaskGuard`
主要 import / dot-source：`../../api/workspace`, `../RetainedWorkPages`, `antd`, `react`

### `product/frontend/src/app/theme.ts`
- `ResolvedTheme`
- `createProductTheme`
- `darkDesignTokens`
- `lightDesignTokens`
主要 import / dot-source：`../shared/ui/tokens`, `antd`

### `product/frontend/src/app/ThemeContext.test.tsx`
主要 import / dot-source：`../shared/ui/tokens`, `./ThemeContext`, `@testing-library/react`, `antd`, `vitest`

### `product/frontend/src/app/ThemeContext.tsx`
- `ThemeMode`
- `ProductThemeProvider`
- `useThemeMode`
主要 import / dot-source：`../shared/ui/tokens`, `./theme`, `antd`, `antd/locale/zh_CN`, `react`

### `product/frontend/src/app/useCheckActivity.test.ts`
主要 import / dot-source：`../api/currentChecks`, `./useCheckActivity`, `@testing-library/react`, `vitest`

### `product/frontend/src/app/useCheckActivity.ts`
- `useCheckActivity`
主要 import / dot-source：`../api/currentChecks`, `./presentation`, `react`

### `product/frontend/src/app/useLiveRead.test.ts`
主要 import / dot-source：`./useLiveRead`, `@testing-library/react`, `vitest`

### `product/frontend/src/app/useLiveRead.ts`
- `useLiveRead`
主要 import / dot-source：`../api/http`, `react`

### `product/frontend/src/app/useProjectWorkspace.test.ts`
主要 import / dot-source：`../api/workspace`, `./browserState`, `./useProjectWorkspace`, `@testing-library/react`, `vitest`

### `product/frontend/src/app/useProjectWorkspace.ts`
- `useProjectWorkspace`
主要 import / dot-source：`../api/experience`, `../api/http`, `../api/projects`, `../api/workspace`, `./browserState`, `./useLiveRead`, `react`

### `product/frontend/src/app/useSystemStatus.ts`
- `useSystemStatus`
主要 import / dot-source：`../api/llm`, `../api/system`, `react`

### `product/frontend/src/features/access/AccessPage.test.tsx`
主要 import / dot-source：`./AccessPage`, `@testing-library/react`, `vitest`

### `product/frontend/src/features/access/AccessPage.tsx`
- `AccessPage`
主要 import / dot-source：`../../api/projects`, `../../api/workspace`, `../../shared/ui/Editorial`, `./ApplicationSetup`, `antd`, `react`

### `product/frontend/src/features/access/ApplicationSetup.test.tsx`
主要 import / dot-source：`./ApplicationSetup`, `@testing-library/react`, `vitest`

### `product/frontend/src/features/access/ApplicationSetup.tsx`
- `ApplicationSetup`
主要 import / dot-source：`../../api/http`, `../../api/onboarding`, `../../api/projects`, `../../api/workspace`, `../../app/tasks/TaskContinuity`, `../../shared/ui/StatusBadge`, `../../shared/ui/TaskActionBar`, `../assistant/AssistantPanel`, `./CandidateReview`, `./ConnectionSupport`, `./ControlledRuntimePanel`, `@ant-design/icons`, `antd`, `react`

### `product/frontend/src/features/access/CandidateReview.test.tsx`
主要 import / dot-source：`../../api/projects`, `./CandidateReview`, `@testing-library/react`, `vitest`

### `product/frontend/src/features/access/CandidateReview.tsx`
- `CandidateReview`
主要 import / dot-source：`../../api/projects`, `../../app/tasks/TaskContinuity`, `antd`, `react`

### `product/frontend/src/features/access/ConnectionSupport.tsx`
- `ConnectionSupport`
主要 import / dot-source：`../../shared/ui/StatusBadge`

### `product/frontend/src/features/access/ControlledRuntimePanel.test.tsx`
主要 import / dot-source：`./ControlledRuntimePanel`, `@testing-library/react`, `vitest`

### `product/frontend/src/features/access/ControlledRuntimePanel.tsx`
- `ApplicationRuntimeSettings`
- `ControlledRuntimePanel`
主要 import / dot-source：`../../api/controlledRuntime`, `../../api/http`, `../../api/projects`, `../../shared/ui/StatusBadge`, `antd`, `react`

### `product/frontend/src/features/assistant/AssistantPanel.test.tsx`
主要 import / dot-source：`./AssistantPanel`, `@testing-library/react`, `vitest`

### `product/frontend/src/features/assistant/AssistantPanel.tsx`
- `AssistantPanel`
主要 import / dot-source：`../../api/assistant`, `../../api/http`, `antd`, `react`

### `product/frontend/src/features/boundaries/BusinessBoundaryPage.test.tsx`
主要 import / dot-source：`../../api/businessBoundaries`, `./BusinessBoundaryPage`, `./proposals/BoundaryProposalEditor`, `@testing-library/react`, `vitest`

### `product/frontend/src/features/boundaries/BusinessBoundaryPage.tsx`
- `BusinessBoundaryPage`
主要 import / dot-source：`../../api/businessBoundaries`, `../../api/http`, `../../api/projects`, `../../app/tasks/TaskContinuity`, `../../shared/ui/Editorial`, `../../shared/ui/PageTaskHeader`, `../../shared/ui/SearchField`, `../../shared/ui/StatusBadge`, `./RuleCandidatesPanel`, `./RuleDetailsPanel`, `./definitions/CurrentBoundaryObjects`, `./draft/BoundaryMaintenanceEditor`, `./draft/boundaryLabels`, `./proposals/BoundaryProposalEditor`, `./proposals/BoundaryProposalReview`, `antd`, `react`

### `product/frontend/src/features/boundaries/definitions/BoundaryObjectsWorkspace.tsx`
- `DraftAction`
- `DraftEffect`
- `ObjectDrafts`
- `BoundaryObjectsWorkspace`
主要 import / dot-source：`../../../api/businessBoundaries`, `../../../shared/ui/SearchField`, `../../../shared/ui/StatusBadge`, `../draft/boundaryLabels`, `./ImplementationSelector`, `antd`, `react`

### `product/frontend/src/features/boundaries/definitions/CurrentBoundaryObjects.tsx`
- `BoundaryEditFocus`
- `CurrentBoundaryObjects`
主要 import / dot-source：`../../../api/businessBoundaries`, `../../../shared/ui/SearchField`, `../../../shared/ui/StatusBadge`, `antd`, `react`

### `product/frontend/src/features/boundaries/definitions/ImplementationSelector.tsx`
- `ImplementationSelector`
主要 import / dot-source：`../../../api/businessBoundaries`, `../../assistant/AssistantPanel`, `../draft/boundaryLabels`, `antd`

### `product/frontend/src/features/boundaries/draft/boundaryLabels.ts`
- `confidenceLabels`
- `effectKindLabels`
- `expectationLabels`
- `relationLabels`
主要 import / dot-source：`../../../api/businessBoundaries`

### `product/frontend/src/features/boundaries/draft/BoundaryMaintenanceEditor.test.tsx`
主要 import / dot-source：`../../../api/businessBoundaries`, `./BoundaryMaintenanceEditor`, `@testing-library/react`, `vitest`

### `product/frontend/src/features/boundaries/draft/BoundaryMaintenanceEditor.tsx`
- `BoundaryMaintenanceEditor`
主要 import / dot-source：`../../../api/businessBoundaries`, `../../../api/permissionDrafts`, `../../../app/tasks/TaskContinuity`, `../../../shared/ui/SearchField`, `../../../shared/ui/StatusBadge`, `../definitions/BoundaryObjectsWorkspace`, `../definitions/CurrentBoundaryObjects`, `../rules/PermissionRuleForm`, `./PermissionDraftAssist`, `antd`, `react`

### `product/frontend/src/features/boundaries/draft/PermissionDraftAssist.tsx`
- `PermissionDraftAssist`
主要 import / dot-source：`../../../api/businessBoundaries`, `../../../api/permissionDrafts`, `./boundaryLabels`, `antd`, `react`

### `product/frontend/src/features/boundaries/proposals/BoundaryProposalEditor.tsx`
- `BoundaryProposalEditor`
主要 import / dot-source：`../../../api/businessBoundaries`, `../../../app/tasks/TaskContinuity`, `../../../shared/ui/Editorial`, `../../../shared/ui/StatusBadge`, `../draft/boundaryLabels`, `../rules/PermissionRuleForm`, `antd`, `react`

### `product/frontend/src/features/boundaries/proposals/BoundaryProposalReview.test.tsx`
主要 import / dot-source：`../../../api/businessBoundaries`, `./BoundaryProposalReview`, `@testing-library/react`, `vitest`

### `product/frontend/src/features/boundaries/proposals/BoundaryProposalReview.tsx`
- `BoundaryProposalReview`
主要 import / dot-source：`../../../api/businessBoundaries`, `../../../shared/ui/StatusBadge`, `../draft/boundaryLabels`, `antd`, `react`

### `product/frontend/src/features/boundaries/RuleCandidatesPanel.test.tsx`
主要 import / dot-source：`../../api/http`, `./RuleCandidatesPanel`, `@testing-library/react`, `vitest`

### `product/frontend/src/features/boundaries/RuleCandidatesPanel.tsx`
- `RuleCandidatesPanel`
主要 import / dot-source：`../../api/http`, `../../api/ruleCandidates`, `../../app/tasks/TaskContinuity`, `../../shared/ui/StatusBadge`, `../../shared/ui/TaskActionBar`, `antd`, `react`

### `product/frontend/src/features/boundaries/RuleDetailsPanel.test.tsx`
主要 import / dot-source：`./RuleDetailsPanel`, `@testing-library/react`, `vitest`

### `product/frontend/src/features/boundaries/RuleDetailsPanel.tsx`
- `RuleDetailsPanel`
主要 import / dot-source：`../../api/ruleDetails`, `../../app/presentation`, `../../shared/ui/Editorial`, `../../shared/ui/StatusBadge`, `../../shared/ui/TaskActionBar`, `antd`, `react`

### `product/frontend/src/features/boundaries/rules/PermissionRuleForm.tsx`
- `PermissionRuleForm`
主要 import / dot-source：`../../../api/businessBoundaries`, `../../../app/tasks/TaskContinuity`, `../draft/boundaryLabels`, `antd`, `react`

### `product/frontend/src/features/changes/ChangeRegistration.tsx`
- `ChangeRegistration`
主要 import / dot-source：`../../api/development`, `../../api/http`, `../../api/repairs`, `../../api/sourceChanges`, `./pendingOperations`, `antd`, `react`

### `product/frontend/src/features/changes/ChangeRuntimeAction.test.tsx`
主要 import / dot-source：`../../api/development`, `./ChangeRuntimeAction`, `@testing-library/react`, `vitest`

### `product/frontend/src/features/changes/ChangeRuntimeAction.tsx`
- `ChangeRuntimeAction`
主要 import / dot-source：`../../api/development`, `../../api/http`, `./pendingOperations`, `antd`, `react`

### `product/frontend/src/features/changes/ChangesPage.test.tsx`
主要 import / dot-source：`./ChangesPage`, `@testing-library/react`, `vitest`

### `product/frontend/src/features/changes/ChangesPage.tsx`
- `ChangesPage`
主要 import / dot-source：`../../api/development`, `../../api/http`, `../../api/projects`, `../../api/repairs`, `../../api/sourceChanges`, `../../app/RetainedWorkPages`, `../../app/presentation`, `../../app/useLiveRead`, `../../shared/ui/Editorial`, `../../shared/ui/StatusBadge`, `./ChangeRegistration`, `./ChangeRuntimeAction`, `./DeliveryFacts`, `./RepairDelivery`, `./SourceIdentityPanel`, `antd`, `react`

### `product/frontend/src/features/changes/DeliveryFacts.test.tsx`
主要 import / dot-source：`../../api/sourceChanges`, `./DeliveryFacts`, `./TaskRecords`, `@testing-library/react`, `vitest`

### `product/frontend/src/features/changes/DeliveryFacts.tsx`
- `DeliveryFacts`
主要 import / dot-source：`../../api/development`, `../../api/http`, `../../api/repairs`, `../../api/sourceChanges`, `../../app/useLiveRead`, `antd`, `react`

### `product/frontend/src/features/changes/DevelopmentTaskPanel.test.tsx`
主要 import / dot-source：`../../api/development`, `./DevelopmentTaskPanel`, `@testing-library/react`, `vitest`

### `product/frontend/src/features/changes/DevelopmentTaskPanel.tsx`
- `DevelopmentTaskPanel`
主要 import / dot-source：`../../api/development`, `../../api/http`, `../../app/presentation`, `../../shared/ui/StatusBadge`, `./pendingOperations`, `antd`, `react`

### `product/frontend/src/features/changes/pendingOperations.ts`
- `clearPendingOperation`
- `readPendingOperation`
- `savePendingOperation`

### `product/frontend/src/features/changes/RepairComparison.test.tsx`
主要 import / dot-source：`../../api/repairs`, `./RepairComparison`, `@testing-library/react`, `vitest`

### `product/frontend/src/features/changes/RepairComparison.tsx`
- `RepairComparison`
主要 import / dot-source：`../../api/repairs`, `antd`

### `product/frontend/src/features/changes/RepairDelivery.test.tsx`
主要 import / dot-source：`../../api/repairs`, `./RepairDelivery`, `@testing-library/react`, `vitest`

### `product/frontend/src/features/changes/RepairDelivery.tsx`
- `RepairTask`
- `RepairDelivery`
主要 import / dot-source：`../../api/repairs`, `../../api/sourceChanges`, `../../shared/ui/Editorial`, `./RepairComparison`, `antd`, `react`

### `product/frontend/src/features/changes/SourceIdentityPanel.test.tsx`
主要 import / dot-source：`../../api/http`, `./SourceIdentityPanel`, `@testing-library/react`, `vitest`

### `product/frontend/src/features/changes/SourceIdentityPanel.tsx`
- `SourceIdentityPanel`
主要 import / dot-source：`../../api/http`, `../../api/sourceIdentity`, `../../app/presentation`, `@ant-design/icons`, `antd`, `react`

### `product/frontend/src/features/changes/TaskRecords.tsx`
- `TaskDeliveryIndex`
- `TaskHistory`
主要 import / dot-source：`../../api/development`, `../../api/http`, `../../app/presentation`, `antd`, `react`

### `product/frontend/src/features/checks/CurrentTestsPage.test.tsx`
主要 import / dot-source：`../../api/currentChecks`, `../../api/http`, `../../api/workspace`, `../results/testing.fixtures`, `./CurrentTestsPage`, `@testing-library/react`, `vitest`

### `product/frontend/src/features/checks/CurrentTestsPage.tsx`
- `CurrentTestsPage`
主要 import / dot-source：`../../api/currentChecks`, `../../api/http`, `../../app/RetainedWorkPages`, `../../app/presentation`, `../../app/tasks/TaskContinuity`, `../../app/useLiveRead`, `../../shared/ui/Editorial`, `../../shared/ui/TaskActionBar`, `../changes/SourceIdentityPanel`, `../preparation/PreparationPage`, `../results/CurrentResultStory`, `../results/ResultOverview`, `antd`, `react`

### `product/frontend/src/features/environment/EnvironmentHistory.test.tsx`
主要 import / dot-source：`./EnvironmentHistory`, `@testing-library/react`, `react`, `vitest`

### `product/frontend/src/features/environment/EnvironmentHistory.tsx`
- `EnvironmentHistory`
主要 import / dot-source：`../../api/currentChecks`, `../../api/http`, `../../api/projects`, `../../shared/ui/Editorial`, `../changes/SourceIdentityPanel`, `../history/CheckHistoryPage`, `../results/CurrentResultStory`, `antd`, `react`

### `product/frontend/src/features/environment/EnvironmentPage.test.tsx`
主要 import / dot-source：`./EnvironmentPage`, `@testing-library/react`, `vitest`

### `product/frontend/src/features/environment/EnvironmentPage.tsx`
- `EnvironmentPage`
主要 import / dot-source：`../../api/experience`, `../../api/http`, `../../api/projects`, `../../api/system`, `../../api/workspace`, `../../app/presentation`, `../../shared/ui/Editorial`, `../access/ControlledRuntimePanel`, `./EnvironmentHistory`, `./OfficialSamplePanel`, `@ant-design/icons`, `antd`, `react`

### `product/frontend/src/features/environment/OfficialDevelopmentJourney.test.tsx`
主要 import / dot-source：`../../api/experience`, `./OfficialDevelopmentJourney`, `@testing-library/react`, `vitest`

### `product/frontend/src/features/environment/OfficialDevelopmentJourney.tsx`
- `OfficialDevelopmentJourney`
主要 import / dot-source：`../../api/experience`, `../../api/http`, `../../api/repairs`, `../../app/RetainedWorkPages`, `../../app/useLiveRead`, `antd`, `react`

### `product/frontend/src/features/environment/OfficialSamplePanel.test.tsx`
主要 import / dot-source：`../../api/experience`, `./OfficialSamplePanel`, `@testing-library/react`, `vitest`

### `product/frontend/src/features/environment/OfficialSamplePanel.tsx`
- `OfficialSamplePanel`
主要 import / dot-source：`../../api/experience`, `../../api/http`, `../../shared/ui/StatusBadge`, `antd`, `react`

### `product/frontend/src/features/history/CheckHistoryPage.test.tsx`
主要 import / dot-source：`../../api/currentChecks`, `../../app/RetainedWorkPages`, `./CheckHistoryPage`, `@testing-library/react`, `react`, `vitest`

### `product/frontend/src/features/history/CheckHistoryPage.tsx`
- `CheckHistoryPage`
主要 import / dot-source：`../../api/currentChecks`, `../../api/http`, `../../api/projects`, `../../app/RetainedWorkPages`, `../../app/presentation`, `../../app/useLiveRead`, `../../shared/ui/Editorial`, `../../shared/ui/SearchField`, `../../shared/ui/StatusBadge`, `antd`, `react`

### `product/frontend/src/features/identities/TestIdentityPage.test.tsx`
主要 import / dot-source：`../../api/businessBoundaries`, `../../api/testIdentities`, `./TestIdentityPage`, `@testing-library/react`, `vitest`

### `product/frontend/src/features/identities/TestIdentityPage.tsx`
- `TestIdentityPage`
主要 import / dot-source：`../../api/businessBoundaries`, `../../api/http`, `../../api/projects`, `../../api/testIdentities`, `../../api/workspace`, `../../app/tasks/TaskContinuity`, `../../shared/ui/Editorial`, `../../shared/ui/StatusBadge`, `../../shared/ui/TaskActionBar`, `antd`, `react`

### `product/frontend/src/features/preparation/EvidenceMaterials.test.tsx`
主要 import / dot-source：`../../api/preparation`, `./EvidenceMaterials`, `@testing-library/react`, `vitest`

### `product/frontend/src/features/preparation/EvidenceMaterials.tsx`
- `EvidenceMaterials`
主要 import / dot-source：`../../api/http`, `../../api/preparation`, `../../shared/ui/Editorial`, `./SupplementalMaterials`, `@ant-design/icons`, `antd`, `react`

### `product/frontend/src/features/preparation/MaterialEditor.test.tsx`
主要 import / dot-source：`./MaterialEditor`, `@testing-library/react`, `vitest`

### `product/frontend/src/features/preparation/MaterialEditor.tsx`
- `MaterialEditor`
- `materialName`
主要 import / dot-source：`../../api/http`, `../../api/preparation`, `../../app/tasks/TaskContinuity`, `../../shared/ui/Editorial`, `antd`, `react`

### `product/frontend/src/features/preparation/MaterialOverview.tsx`
- `MaterialOverview`
主要 import / dot-source：`../../api/preparation`, `../../api/preparationGuidance`, `../../shared/ui/StatusBadge`, `@ant-design/icons`, `antd`, `react`

### `product/frontend/src/features/preparation/PreparationPage.test.tsx`
主要 import / dot-source：`../../api/preparation`, `../../api/workspace`, `./PreparationPage`, `@testing-library/react`, `vitest`

### `product/frontend/src/features/preparation/PreparationPage.tsx`
- `PreparationPage`
主要 import / dot-source：`../../api/http`, `../../api/preparation`, `../../api/preparationGuidance`, `../../api/projects`, `../../api/proofSources`, `../../api/testIdentities`, `../../api/workspace`, `../../app/RetainedWorkPages`, `../../app/taskDestination`, `../../app/tasks/TaskContinuity`, `../../app/useLiveRead`, `../../shared/ui/Editorial`, `../../shared/ui/TaskActionBar`, `../assistant/AssistantPanel`, `../identities/TestIdentityPage`, `../recording/RecordingPage`, `./EvidenceMaterials`, `./MaterialEditor`, `./MaterialOverview`, `./ProofSourcesPanel`, `antd`, `react`

### `product/frontend/src/features/preparation/ProofSourcesPanel.test.tsx`
主要 import / dot-source：`./ProofSourcesPanel`, `@testing-library/react`, `vitest`

### `product/frontend/src/features/preparation/ProofSourcesPanel.tsx`
- `ProofSourcesPanel`
主要 import / dot-source：`../../api/http`, `../../api/proofSources`, `../../app/tasks/TaskContinuity`, `../../shared/ui/Editorial`, `../../shared/ui/StatusBadge`, `../../shared/ui/TaskActionBar`, `antd`, `react`

### `product/frontend/src/features/preparation/SupplementalMaterials.test.tsx`
主要 import / dot-source：`../../api/http`, `./SupplementalMaterials`, `@testing-library/react`, `vitest`

### `product/frontend/src/features/preparation/SupplementalMaterials.tsx`
- `SupplementalMaterials`
主要 import / dot-source：`../../api/http`, `../../api/supplementalMaterials`, `../../app/presentation`, `../../app/tasks/TaskContinuity`, `../../shared/ui/Editorial`, `../../shared/ui/StatusBadge`, `@ant-design/icons`, `antd`, `react`

### `product/frontend/src/features/recording/FlowDraftReview.tsx`
- `FlowDraftReview`
主要 import / dot-source：`../../api/recordings`, `antd`

### `product/frontend/src/features/recording/RecordingCaptureCard.tsx`
- `RecordingCaptureCard`
- `captureLabel`
主要 import / dot-source：`../../api/jobs`, `../../api/recordings`, `../../app/browserState`, `../../app/presentation`, `../../shared/ui/StatusBadge`, `antd`, `react`

### `product/frontend/src/features/recording/RecordingPage.test.tsx`
主要 import / dot-source：`../../api/workspace`, `./RecordingPage`, `@testing-library/react`, `vitest`

### `product/frontend/src/features/recording/RecordingPage.tsx`
- `RecordingPage`
主要 import / dot-source：`../../api/http`, `../../api/jobs`, `../../api/preparation`, `../../api/projects`, `../../api/recordings`, `../../api/workspace`, `../../app/browserState`, `../../app/tasks/TaskContinuity`, `../../shared/ui/Editorial`, `../../shared/ui/TaskActionBar`, `../assistant/AssistantPanel`, `./FlowDraftReview`, `./RecordingCaptureCard`, `antd`, `react`

### `product/frontend/src/features/results/CurrentResultStory.test.tsx`
主要 import / dot-source：`../../api/currentChecks`, `../../app/RetainedWorkPages`, `./CurrentResultStory`, `./testing.fixtures`, `@testing-library/react`, `vitest`

### `product/frontend/src/features/results/CurrentResultStory.tsx`
- `CurrentResultStory`
主要 import / dot-source：`../../api/currentChecks`, `../../api/http`, `../../app/RetainedWorkPages`, `../../app/presentation`, `../../shared/ui/Editorial`, `../assistant/AssistantPanel`, `./DiagnosisSummary`, `./ExecutionPath`, `./ObservationSources`, `./ProofCoverage`, `./ResultOverview`, `./observationPresentation`, `./tracePresentation`, `antd`, `react`

### `product/frontend/src/features/results/DiagnosisSummary.test.tsx`
主要 import / dot-source：`./DiagnosisSummary`, `./testing.fixtures`, `@testing-library/react`, `vitest`

### `product/frontend/src/features/results/DiagnosisSummary.tsx`
- `DiagnosisSummary`
主要 import / dot-source：`../../api/currentChecks`, `./tracePresentation`, `@ant-design/icons`, `antd`

### `product/frontend/src/features/results/ExecutionPath.test.tsx`
主要 import / dot-source：`../../api/currentChecks`, `./ExecutionPath`, `./testing.fixtures`, `@testing-library/react`, `vitest`

### `product/frontend/src/features/results/ExecutionPath.tsx`
- `ExecutionPath`
主要 import / dot-source：`../../api/currentChecks`, `./tracePresentation`, `@ant-design/icons`, `react`

### `product/frontend/src/features/results/observationPresentation.test.ts`
主要 import / dot-source：`./observationPresentation`, `./testing.fixtures`, `vitest`

### `product/frontend/src/features/results/observationPresentation.ts`
- `observationGroups`
- `observationStatus`
- `phaseLabels`
- `sourceLabels`
- `sourceReading`
主要 import / dot-source：`../../api/currentChecks`

### `product/frontend/src/features/results/ObservationSources.test.tsx`
主要 import / dot-source：`../../api/currentChecks`, `./ObservationSources`, `./observationPresentation`, `./testing.fixtures`, `@testing-library/react`, `vitest`

### `product/frontend/src/features/results/ObservationSources.tsx`
- `ObservationSources`
主要 import / dot-source：`../../api/currentChecks`, `../../shared/ui/StatusBadge`, `./observationPresentation`, `antd`

### `product/frontend/src/features/results/ProofCoverage.tsx`
- `ProofCoverage`
主要 import / dot-source：`../../api/currentChecks`, `antd`

### `product/frontend/src/features/results/ResultOverview.tsx`
- `BusinessEffects`
- `ResultBadge`
- `ResultOverviewHeader`
- `ResultScope`
- `caseJudgement`
- `resourceOwner`
主要 import / dot-source：`../../api/currentChecks`, `../../api/repairs`, `../../app/RetainedWorkPages`, `../../shared/ui/StatusBadge`, `antd`, `react`

### `product/frontend/src/features/results/testing.fixtures.ts`
主要 import / dot-source：`../../api/currentChecks`

### `product/frontend/src/features/results/tracePresentation.ts`
- `breakpointLabels`
- `precisionDescriptions`
- `precisionLabels`
- `traceEventContext`
- `traceEventLabel`
- `traceKindLabels`
- `traceLimitations`
主要 import / dot-source：`../../api/currentChecks`

### `product/frontend/src/features/settings/LLMSettingsDrawer.test.tsx`
主要 import / dot-source：`./LLMSettingsDrawer`, `@testing-library/react`, `vitest`

### `product/frontend/src/features/settings/LLMSettingsDrawer.tsx`
- `LLMSettingsDrawer`
主要 import / dot-source：`../../api/http`, `../../api/llm`, `../../shared/ui/StatusBadge`, `antd`, `react`

### `product/frontend/src/features/system/RuntimePage.test.tsx`
主要 import / dot-source：`../../api/system`, `./RuntimePage`, `@testing-library/react`, `vitest`

### `product/frontend/src/features/system/RuntimePage.tsx`
- `RuntimePage`
主要 import / dot-source：`../../api/llm`, `../../api/system`, `../../app/buildIdentity`, `../../shared/ui/Editorial`, `../../shared/ui/StatusBadge`, `antd`, `react`

### `product/frontend/src/features/tools/clientGuides.ts`
- `ClientGuide`
- `MCPClientKey`
- `clientGuide`
- `clientOptions`

### `product/frontend/src/features/tools/MCPAccessCard.test.tsx`
主要 import / dot-source：`./MCPAccessCard`, `@testing-library/react`, `vitest`

### `product/frontend/src/features/tools/MCPAccessCard.tsx`
- `MCPAccessCard`
主要 import / dot-source：`../../api/http`, `../../api/mcp`, `../../shared/ui/StatusBadge`, `./clientGuides`, `antd`, `react`

### `product/frontend/src/features/tools/ToolsPage.test.tsx`
主要 import / dot-source：`./ToolsPage`, `@testing-library/react`, `vitest`

### `product/frontend/src/features/tools/ToolsPage.tsx`
- `ToolsPage`
主要 import / dot-source：`../../api/http`, `../../api/mcp`, `../../api/projects`, `../../app/navigation/AgentPageHeader`, `../../shared/ui/Editorial`, `./MCPAccessCard`

### `product/frontend/src/features/workspace/PermissionAcceptance.test.tsx`
主要 import / dot-source：`../results/testing.fixtures`, `./PermissionAcceptance`, `@testing-library/react`, `vitest`

### `product/frontend/src/features/workspace/PermissionAcceptance.tsx`
- `PermissionAcceptance`
主要 import / dot-source：`../../api/currentChecks`, `../../api/http`, `../../app/useLiveRead`, `antd`, `react`

### `product/frontend/src/features/workspace/WorkbenchPage.test.tsx`
主要 import / dot-source：`../../api/currentChecks`, `../../api/workspace`, `../results/testing.fixtures`, `./WorkbenchPage`, `@testing-library/react`, `vitest`

### `product/frontend/src/features/workspace/WorkbenchPage.tsx`
- `WorkbenchPage`
主要 import / dot-source：`../../api/currentChecks`, `../../api/experience`, `../../api/http`, `../../api/mcp`, `../../api/preparation`, `../../api/projects`, `../../api/system`, `../../api/workspace`, `../../app/taskDestination`, `../../app/useLiveRead`, `../../shared/ui/Editorial`, `antd`, `react`

### `product/frontend/src/main.tsx`
主要 import / dot-source：`./app/ControlShell`, `./app/ThemeContext`, `react`, `react-dom/client`

### `product/frontend/src/shared/ui/Editorial.test.tsx`
主要 import / dot-source：`./Editorial`, `@testing-library/react`, `vitest`

### `product/frontend/src/shared/ui/Editorial.tsx`
- `FlowStep`
- `EditorialHeader`
- `EditorialPage`
- `EvidenceSurface`
- `FlowSpine`
- `MarginNote`
- `RuleSentence`
- `TaskFocus`
主要 import / dot-source：`antd`, `react`

### `product/frontend/src/shared/ui/PageTaskHeader.test.tsx`
主要 import / dot-source：`./PageTaskHeader`, `@testing-library/react`, `vitest`

### `product/frontend/src/shared/ui/PageTaskHeader.tsx`
- `PageTaskHeader`
主要 import / dot-source：`./Editorial`, `./StatusBadge`

### `product/frontend/src/shared/ui/SearchField.tsx`
- `SearchField`
主要 import / dot-source：`@ant-design/icons`, `antd`

### `product/frontend/src/shared/ui/StatusBadge.test.tsx`
主要 import / dot-source：`./StatusBadge`, `@testing-library/react`, `vitest`

### `product/frontend/src/shared/ui/StatusBadge.tsx`
- `StatusTone`
- `StatusBadge`
主要 import / dot-source：`react`

### `product/frontend/src/shared/ui/TaskActionBar.test.tsx`
主要 import / dot-source：`./TaskActionBar`, `@testing-library/react`, `vitest`

### `product/frontend/src/shared/ui/TaskActionBar.tsx`
- `TaskActionBar`
主要 import / dot-source：`./tokens`, `antd`

### `product/frontend/src/shared/ui/tokens.test.ts`
主要 import / dot-source：`./tokens`, `vitest`

### `product/frontend/src/shared/ui/tokens.ts`
- `ProductTheme`
- `designTokens`
- `metrics`
- `palettes`
- `productCssVariables`

### `product/frontend/src/test-setup.ts`
主要 import / dot-source：`@testing-library/react`, `vitest`

<!-- GENERATED:END -->
