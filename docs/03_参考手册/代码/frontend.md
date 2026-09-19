# 自动代码参考：前端

> 生成区域只描述当前代码结构；职责与安全理由由模块参考和任务指南维护。

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
- `BoundaryProposalViewDto`
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
- `ResultStory`
- `StoryExecutionPath`
- `StoryIdentity`
- `StoryProofCoverage`
- `StoryTraceEvent`
- `currentChecksApi`
主要 import / dot-source：`./http`, `./repairs`

### `product/frontend/src/api/experience.ts`
- `CompetitionValidationSummaryDto`
- `CompetitionValidationSummaryViewDto`
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
- `PermissionReference`
- `PreparationItem`
- `PreparationStatus`
- `PreparationView`
- `preparationApi`
主要 import / dot-source：`./businessBoundaries`, `./http`

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

### `product/frontend/src/api/sourceChanges.ts`
- `SourceChangeViewDto`
- `sourceChangesApi`
主要 import / dot-source：`./http`, `./repairs`

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
主要 import / dot-source：`../api/llm`, `../api/mcp`, `../api/projects`, `../api/system`, `../components/ApplicationSwitcher`, `./ThemeContext`, `@ant-design/icons`, `antd`, `react`

### `product/frontend/src/app/browserState.ts`
- `browserState`
主要 import / dot-source：`../api/projects`, `../api/recordings`

### `product/frontend/src/app/ControlShell.test.tsx`
主要 import / dot-source：`../api/workspace`, `../components/TaskContinuity`, `./ControlShell`, `./ThemeContext`, `@testing-library/react`, `react`, `vitest`

### `product/frontend/src/app/ControlShell.tsx`
- `ControlShell`
主要 import / dot-source：`../api/experience`, `../api/http`, `../api/mcp`, `../api/projects`, `../api/system`, `../api/workspace`, `../components/ErrorRecovery`, `../components/ModuleNavigation`, `../components/TaskContinuity`, `../features/access/AccessPage`, `../features/boundaries/BusinessBoundaryPage`, `../features/changes/ChangesPage`, `../features/settings/LLMSettingsDrawer`, `../features/system/RuntimePage`, `../features/testing/CheckHistoryPage`, `../features/testing/CurrentTestsPage`, `../features/tools/ToolsPage`, `../features/workspace/OfficialSamplePanel`, `../features/workspace/WorkbenchPage`, `./AppHeader`, `./NotificationCenter`, `./RetainedWorkPages`, `./presentation`, `./useCheckActivity`, `./useProjectWorkspace`, `./useSystemStatus`, `antd`, `react`, `react-router-dom`

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
主要 import / dot-source：`../api/http`, `antd`, `react`

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

### `product/frontend/src/app/taskDestination.test.ts`
主要 import / dot-source：`../api/workspace`, `./taskDestination`, `vitest`

### `product/frontend/src/app/taskDestination.ts`
- `taskDestination`
主要 import / dot-source：`../api/workspace`

### `product/frontend/src/app/theme.ts`
- `ResolvedTheme`
- `createProductTheme`
- `darkDesignTokens`
- `lightDesignTokens`
主要 import / dot-source：`../shared/ui/tokens`, `antd`

### `product/frontend/src/app/ThemeContext.test.tsx`
主要 import / dot-source：`../shared/ui/tokens`, `./ThemeContext`, `@testing-library/react`, `vitest`

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

### `product/frontend/src/app/useProjectWorkspace.test.ts`
主要 import / dot-source：`../api/workspace`, `./useProjectWorkspace`, `@testing-library/react`, `vitest`

### `product/frontend/src/app/useProjectWorkspace.ts`
- `useProjectWorkspace`
主要 import / dot-source：`../api/http`, `../api/projects`, `../api/workspace`, `./browserState`, `react`

### `product/frontend/src/app/useSystemStatus.ts`
- `useSystemStatus`
主要 import / dot-source：`../api/llm`, `../api/system`, `react`

### `product/frontend/src/components/ApplicationSwitcher.tsx`
- `ApplicationSwitcher`
主要 import / dot-source：`../api/projects`, `@ant-design/icons`, `antd`

### `product/frontend/src/components/AssistantPanel.test.tsx`
主要 import / dot-source：`./AssistantPanel`, `@testing-library/react`, `vitest`

### `product/frontend/src/components/AssistantPanel.tsx`
- `AssistantPanel`
主要 import / dot-source：`../api/assistant`, `../api/http`, `antd`, `react`

### `product/frontend/src/components/ErrorRecovery.tsx`
- `ErrorRecovery`
主要 import / dot-source：`../api/http`, `antd`

### `product/frontend/src/components/ModuleNavigation.tsx`
- `DesktopModuleNavigation`
- `MobileModuleNavigation`
主要 import / dot-source：`../api/system`, `../api/workspace`, `../app/AppHeader`, `../app/presentation`, `@ant-design/icons`, `antd`, `react`

### `product/frontend/src/components/PageTaskHeader.test.tsx`
主要 import / dot-source：`./PageTaskHeader`, `@testing-library/react`, `vitest`

### `product/frontend/src/components/PageTaskHeader.tsx`
- `PageTaskHeader`
主要 import / dot-source：`antd`

### `product/frontend/src/components/ProductShellComponents.test.tsx`
主要 import / dot-source：`./ApplicationSwitcher`, `./ModuleNavigation`, `./TaskActionBar`, `@testing-library/react`, `vitest`

### `product/frontend/src/components/TaskActionBar.tsx`
- `TaskActionBar`
主要 import / dot-source：`antd`

### `product/frontend/src/components/TaskContinuity.tsx`
- `TaskGuardContext`
- `TaskJourney`
- `TaskReceipt`
- `useTaskGuard`
主要 import / dot-source：`../api/workspace`, `../app/RetainedWorkPages`, `antd`, `react`

### `product/frontend/src/features/access/AccessPage.test.tsx`
主要 import / dot-source：`./AccessPage`, `@testing-library/react`, `vitest`

### `product/frontend/src/features/access/AccessPage.tsx`
- `AccessPage`
主要 import / dot-source：`../../api/projects`, `../../api/workspace`, `../../shared/ui/Editorial`, `./ApplicationSetup`, `antd`

### `product/frontend/src/features/access/ApplicationSetup.test.tsx`
主要 import / dot-source：`./ApplicationSetup`, `@testing-library/react`, `vitest`

### `product/frontend/src/features/access/ApplicationSetup.tsx`
- `ApplicationSetup`
主要 import / dot-source：`../../api/http`, `../../api/onboarding`, `../../api/projects`, `../../api/workspace`, `../../components/AssistantPanel`, `../../components/TaskActionBar`, `../../components/TaskContinuity`, `./CandidateReview`, `antd`, `react`

### `product/frontend/src/features/access/CandidateReview.test.tsx`
主要 import / dot-source：`../../api/projects`, `./CandidateReview`, `@testing-library/react`, `vitest`

### `product/frontend/src/features/access/CandidateReview.tsx`
- `CandidateReview`
主要 import / dot-source：`../../api/projects`, `../../components/TaskContinuity`, `antd`, `react`

### `product/frontend/src/features/boundaries/boundaryLabels.ts`
- `confidenceLabels`
- `effectKindLabels`
- `expectationLabels`
- `relationLabels`
主要 import / dot-source：`../../api/businessBoundaries`

### `product/frontend/src/features/boundaries/BoundaryMaintenanceEditor.test.tsx`
主要 import / dot-source：`../../api/businessBoundaries`, `./BoundaryMaintenanceEditor`, `@testing-library/react`, `vitest`

### `product/frontend/src/features/boundaries/BoundaryMaintenanceEditor.tsx`
- `BoundaryMaintenanceEditor`
主要 import / dot-source：`../../api/businessBoundaries`, `../../api/permissionDrafts`, `../../components/AssistantPanel`, `../../components/TaskContinuity`, `./PermissionDraftAssist`, `./PermissionRuleForm`, `./boundaryLabels`, `antd`, `react`

### `product/frontend/src/features/boundaries/BoundaryProposalEditor.tsx`
- `BoundaryProposalEditor`
主要 import / dot-source：`../../api/businessBoundaries`, `../../components/TaskContinuity`, `../../shared/ui/Editorial`, `./PermissionRuleForm`, `./boundaryLabels`, `antd`, `react`

### `product/frontend/src/features/boundaries/BoundaryProposalReview.tsx`
- `BoundaryProposalReview`
主要 import / dot-source：`../../api/businessBoundaries`, `./boundaryLabels`, `antd`, `react`

### `product/frontend/src/features/boundaries/BusinessBoundaryPage.test.tsx`
主要 import / dot-source：`../../api/businessBoundaries`, `./BoundaryProposalEditor`, `./BusinessBoundaryPage`, `@testing-library/react`, `vitest`

### `product/frontend/src/features/boundaries/BusinessBoundaryPage.tsx`
- `BusinessBoundaryPage`
主要 import / dot-source：`../../api/businessBoundaries`, `../../api/http`, `../../api/projects`, `../../components/PageTaskHeader`, `../../components/TaskContinuity`, `../../shared/ui/Editorial`, `./BoundaryMaintenanceEditor`, `./BoundaryProposalEditor`, `./BoundaryProposalReview`, `./boundaryLabels`, `antd`, `react`

### `product/frontend/src/features/boundaries/PermissionDraftAssist.tsx`
- `PermissionDraftAssist`
主要 import / dot-source：`../../api/businessBoundaries`, `../../api/permissionDrafts`, `./boundaryLabels`, `antd`, `react`

### `product/frontend/src/features/boundaries/PermissionRuleForm.tsx`
- `PermissionRuleForm`
主要 import / dot-source：`../../api/businessBoundaries`, `../../components/TaskContinuity`, `./boundaryLabels`, `antd`, `react`

### `product/frontend/src/features/changes/ChangesPage.test.tsx`
主要 import / dot-source：`./ChangesPage`, `@testing-library/react`, `vitest`

### `product/frontend/src/features/changes/ChangesPage.tsx`
- `ChangesPage`
主要 import / dot-source：`../../api/http`, `../../api/projects`, `../../api/repairs`, `../../api/sourceChanges`, `../../api/workspace`, `../../app/RetainedWorkPages`, `../../app/presentation`, `../../app/taskDestination`, `../../shared/ui/Editorial`, `./RepairComparison`, `antd`, `react`

### `product/frontend/src/features/changes/RepairComparison.test.tsx`
主要 import / dot-source：`../../api/repairs`, `./RepairComparison`, `@testing-library/react`, `vitest`

### `product/frontend/src/features/changes/RepairComparison.tsx`
- `RepairComparison`
主要 import / dot-source：`../../api/repairs`, `antd`

### `product/frontend/src/features/identities/TestIdentityPage.test.tsx`
主要 import / dot-source：`../../api/businessBoundaries`, `../../api/testIdentities`, `./TestIdentityPage`, `@testing-library/react`, `vitest`

### `product/frontend/src/features/identities/TestIdentityPage.tsx`
- `TestIdentityPage`
主要 import / dot-source：`../../api/businessBoundaries`, `../../api/http`, `../../api/projects`, `../../api/testIdentities`, `../../api/workspace`, `../../components/TaskActionBar`, `../../components/TaskContinuity`, `../../shared/ui/Editorial`, `antd`, `react`

### `product/frontend/src/features/preparation/EvidenceMaterials.test.tsx`
主要 import / dot-source：`../../api/preparation`, `./EvidenceMaterials`, `@testing-library/react`, `vitest`

### `product/frontend/src/features/preparation/EvidenceMaterials.tsx`
- `EvidenceMaterials`
主要 import / dot-source：`../../api/http`, `../../api/preparation`, `../../shared/ui/Editorial`, `@ant-design/icons`, `antd`, `react`

### `product/frontend/src/features/preparation/PreparationPage.test.tsx`
主要 import / dot-source：`../../api/preparation`, `../../api/workspace`, `./PreparationPage`, `@testing-library/react`, `vitest`

### `product/frontend/src/features/preparation/PreparationPage.tsx`
- `PreparationPage`
主要 import / dot-source：`../../api/http`, `../../api/preparation`, `../../api/projects`, `../../api/testIdentities`, `../../api/workspace`, `../../app/taskDestination`, `../../components/AssistantPanel`, `../../components/TaskActionBar`, `../../components/TaskContinuity`, `../../shared/ui/Editorial`, `../identities/TestIdentityPage`, `../recording/RecordingPage`, `./EvidenceMaterials`, `antd`, `react`

### `product/frontend/src/features/recording/FlowDraftReview.tsx`
- `FlowDraftReview`
主要 import / dot-source：`../../api/recordings`, `antd`

### `product/frontend/src/features/recording/RecordingCaptureCard.tsx`
- `RecordingCaptureCard`
- `captureLabel`
主要 import / dot-source：`../../api/jobs`, `../../api/recordings`, `../../app/browserState`, `../../app/presentation`, `antd`, `react`

### `product/frontend/src/features/recording/RecordingPage.test.tsx`
主要 import / dot-source：`../../api/workspace`, `./RecordingPage`, `@testing-library/react`, `vitest`

### `product/frontend/src/features/recording/RecordingPage.tsx`
- `RecordingPage`
主要 import / dot-source：`../../api/http`, `../../api/jobs`, `../../api/projects`, `../../api/recordings`, `../../api/workspace`, `../../app/browserState`, `../../components/AssistantPanel`, `../../components/TaskActionBar`, `../../components/TaskContinuity`, `../../shared/ui/Editorial`, `./FlowDraftReview`, `./RecordingCaptureCard`, `antd`, `react`

### `product/frontend/src/features/settings/LLMSettingsDrawer.test.tsx`
主要 import / dot-source：`./LLMSettingsDrawer`, `@testing-library/react`, `vitest`

### `product/frontend/src/features/settings/LLMSettingsDrawer.tsx`
- `LLMSettingsDrawer`
主要 import / dot-source：`../../api/http`, `../../api/llm`, `antd`, `react`

### `product/frontend/src/features/settings/MCPAccessCard.test.tsx`
主要 import / dot-source：`./MCPAccessCard`, `@testing-library/react`, `vitest`

### `product/frontend/src/features/settings/MCPAccessCard.tsx`
- `MCPAccessCard`
主要 import / dot-source：`../../api/http`, `../../api/mcp`, `antd`, `react`

### `product/frontend/src/features/system/RuntimePage.test.tsx`
主要 import / dot-source：`../../api/system`, `./RuntimePage`, `@testing-library/react`, `vitest`

### `product/frontend/src/features/system/RuntimePage.tsx`
- `RuntimePage`
主要 import / dot-source：`../../api/llm`, `../../api/system`, `antd`, `react`

### `product/frontend/src/features/testing/CheckHistoryPage.test.tsx`
主要 import / dot-source：`../../api/currentChecks`, `./CheckHistoryPage`, `@testing-library/react`, `react`, `vitest`

### `product/frontend/src/features/testing/CheckHistoryPage.tsx`
- `CheckHistoryPage`
主要 import / dot-source：`../../api/currentChecks`, `../../api/http`, `../../api/projects`, `../../app/presentation`, `../../shared/ui/Editorial`, `antd`, `react`

### `product/frontend/src/features/testing/CurrentResultStory.test.tsx`
主要 import / dot-source：`../../app/RetainedWorkPages`, `./CurrentResultStory`, `./testing.fixtures`, `@testing-library/react`, `vitest`

### `product/frontend/src/features/testing/CurrentResultStory.tsx`
- `CurrentResultStory`
主要 import / dot-source：`../../api/currentChecks`, `../../api/http`, `../../api/repairs`, `../../app/RetainedWorkPages`, `../../app/presentation`, `../../components/AssistantPanel`, `../../shared/ui/Editorial`, `../changes/RepairComparison`, `./ExecutionPath`, `./ProofCoverage`, `@ant-design/icons`, `antd`, `react`

### `product/frontend/src/features/testing/CurrentTestsPage.test.tsx`
主要 import / dot-source：`../../api/currentChecks`, `./CurrentTestsPage`, `./testing.fixtures`, `@testing-library/react`, `vitest`

### `product/frontend/src/features/testing/CurrentTestsPage.tsx`
- `CurrentTestsPage`
主要 import / dot-source：`../../api/currentChecks`, `../../api/http`, `../../app/presentation`, `../../components/TaskActionBar`, `../../components/TaskContinuity`, `../../shared/ui/Editorial`, `../preparation/PreparationPage`, `./CurrentResultStory`, `antd`, `react`

### `product/frontend/src/features/testing/ExecutionPath.test.tsx`
主要 import / dot-source：`../../api/currentChecks`, `./ExecutionPath`, `./testing.fixtures`, `@testing-library/react`, `vitest`

### `product/frontend/src/features/testing/ExecutionPath.tsx`
- `ExecutionPath`
- `traceKindLabels`
主要 import / dot-source：`../../api/currentChecks`, `@ant-design/icons`, `react`

### `product/frontend/src/features/testing/ProofCoverage.tsx`
- `ProofCoverage`
主要 import / dot-source：`../../api/currentChecks`, `antd`

### `product/frontend/src/features/testing/testing.fixtures.ts`
主要 import / dot-source：`../../api/currentChecks`

### `product/frontend/src/features/tools/ToolsPage.test.tsx`
主要 import / dot-source：`./ToolsPage`, `@testing-library/react`, `vitest`

### `product/frontend/src/features/tools/ToolsPage.tsx`
- `ToolsPage`
主要 import / dot-source：`../../api/http`, `../../api/mcp`, `../../api/projects`, `../../components/PageTaskHeader`, `../settings/MCPAccessCard`, `antd`

### `product/frontend/src/features/workspace/OfficialSamplePanel.test.tsx`
主要 import / dot-source：`../../api/experience`, `./OfficialSamplePanel`, `@testing-library/react`, `vitest`

### `product/frontend/src/features/workspace/OfficialSamplePanel.tsx`
- `OfficialSamplePanel`
主要 import / dot-source：`../../api/experience`, `../../api/http`, `../../api/repairs`, `antd`, `react`

### `product/frontend/src/features/workspace/WorkbenchPage.test.tsx`
主要 import / dot-source：`../../api/workspace`, `./WorkbenchPage`, `@testing-library/react`, `vitest`

### `product/frontend/src/features/workspace/WorkbenchPage.tsx`
- `WorkbenchContext`
- `WorkbenchPage`
主要 import / dot-source：`../../api/experience`, `../../api/mcp`, `../../api/projects`, `../../api/system`, `../../api/workspace`, `../../app/presentation`, `../../app/taskDestination`, `../../shared/ui/Editorial`, `antd`, `react`

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
