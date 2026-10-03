# 自动代码参考：前端

> 生成区域只描述当前代码结构；职责与安全理由由能力映射和任务指南维护。

<!-- GENERATED:START -->

<!-- 此区域由 scripts/docs/generate.py 从 product/frontend/src/ 读取。 -->

### `product/frontend/src/api/applications/controlledRuntime.ts`
- `RuntimeOperation`
- `RuntimePreview`
- `RuntimeState`
- `controlledRuntimeApi`
主要 import / dot-source：`../http`

### `product/frontend/src/api/applications/experience.ts`
- `CompetitionValidationSummaryDto`
- `CompetitionValidationSummaryViewDto`
- `OfficialDevelopmentJourneyDto`
- `OfficialExperienceDto`
- `OfficialScenarioVersion`
- `experienceApi`
主要 import / dot-source：`../boundaries/businessBoundaries`, `../checks/repairs`, `../http`

### `product/frontend/src/api/applications/onboarding.ts`
- `DiscoveryCandidate`
- `DiscoveryHint`
- `DiscoveryResult`
- `onboardingApi`
主要 import / dot-source：`../http`

### `product/frontend/src/api/applications/projects.ts`
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
主要 import / dot-source：`../http`, `./onboarding`

### `product/frontend/src/api/assistance/assistant.ts`
- `AssistantEntity`
- `AssistantFocus`
- `AssistantSuggestion`
- `AssistantSurfaceView`
- `ProjectAssistantSurface`
- `assistantApi`
主要 import / dot-source：`../http`

### `product/frontend/src/api/assistance/llm.ts`
- `AIAssistanceSettings`
- `LLMConnectionStatus`
- `LLMModelCatalog`
- `LLMModelOption`
- `LLMProfile`
- `LLMProfileWrite`
- `LLMProvider`
- `llmApi`
主要 import / dot-source：`../http`

### `product/frontend/src/api/boundaries/businessBoundaries.ts`
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
主要 import / dot-source：`../http`

### `product/frontend/src/api/boundaries/permissionDrafts.ts`
- `PermissionDraftSuggestion`
- `PermissionDraftView`
- `permissionDraftsApi`
主要 import / dot-source：`../http`, `./businessBoundaries`

### `product/frontend/src/api/boundaries/ruleCandidates.ts`
- `RuleCandidateContext`
- `RuleCandidateView`
- `ruleCandidatesApi`
主要 import / dot-source：`../http`, `./businessBoundaries`

### `product/frontend/src/api/boundaries/ruleDetails.ts`
- `RuleDetails`
- `ruleDetailsApi`
主要 import / dot-source：`../http`

### `product/frontend/src/api/changes/development.ts`
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
主要 import / dot-source：`../http`, `./sourceChanges`

### `product/frontend/src/api/changes/sourceChanges.ts`
- `RegistrationPreview`
- `SourceChangeViewDto`
- `sourceChangesApi`
主要 import / dot-source：`../checks/repairs`, `../http`, `./development`

### `product/frontend/src/api/changes/sourceIdentity.ts`
- `SourceIdentity`
- `sourceIdentityApi`
主要 import / dot-source：`../http`

### `product/frontend/src/api/checks/currentChecks.ts`
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
主要 import / dot-source：`../http`, `./repairs`

### `product/frontend/src/api/checks/repairs.ts`
- `ProjectRepair`
- `RepairComparisonRow`
- `RepairContract`
- `RepairReference`
- `RepairStatus`
- `RepairVerification`
- `repairLabels`
- `repairReference`
- `repairsApi`
主要 import / dot-source：`../http`

### `product/frontend/src/api/http.test.ts`
主要 import / dot-source：`./http`, `vitest`

### `product/frontend/src/api/http.ts`
- `ApiEnvelope`
- `ErrorDiagnosis`
- `ApiError`
- `request`

### `product/frontend/src/api/preparation/jobs.ts`
- `CancelJobDto`
- `JobEventDto`
- `jobsApi`
主要 import / dot-source：`../http`

### `product/frontend/src/api/preparation/preparation.ts`
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
主要 import / dot-source：`../boundaries/businessBoundaries`, `../http`

### `product/frontend/src/api/preparation/preparationGuidance.ts`
- `PreparationGuidance`
- `PreparationMaterialAdvice`
- `PreparationNextAction`

### `product/frontend/src/api/preparation/proofSources.ts`
- `AdoptionPreview`
- `ProofConfig`
- `ProofContext`
- `ProofOperationKind`
- `ProofReceipt`
- `ProofReport`
- `ProofSource`
- `proofSourcesApi`
主要 import / dot-source：`../http`, `./preparationGuidance`

### `product/frontend/src/api/preparation/recordings.ts`
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
主要 import / dot-source：`../http`

### `product/frontend/src/api/preparation/supplementalMaterials.ts`
- `MaterialPreview`
- `SupplementalDocument`
- `SupplementalMaterial`
- `supplementalMaterialsApi`
主要 import / dot-source：`../http`

### `product/frontend/src/api/preparation/testIdentities.ts`
- `IdentityPreparationDto`
- `IdentityPreparationStatus`
- `TestIdentityAuthMethod`
- `TestIdentityDto`
- `TestIdentityStatus`
- `testIdentitiesApi`
主要 import / dot-source：`../http`

### `product/frontend/src/api/system/mcp.ts`
- `MCPAccessCredentialView`
- `MCPAccessLevel`
- `MCPAccessView`
- `MCPConnectionState`
- `MCPProjectGrant`
- `mcpAccessApi`
主要 import / dot-source：`../http`

### `product/frontend/src/api/system/system.test.ts`
主要 import / dot-source：`./system`, `vitest`

### `product/frontend/src/api/system/system.ts`
- `MaintenanceEntry`
- `MaintenanceOperation`
- `MaintenanceOperationResult`
- `MaintenanceStatus`
- `SystemStatus`
- `systemApi`
主要 import / dot-source：`../http`

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
主要 import / dot-source：`./boundaries/businessBoundaries`, `./checks/currentChecks`, `./checks/repairs`, `./http`

### `product/frontend/src/app/navigation/ApplicationSwitcher.tsx`
- `ApplicationSwitcher`
主要 import / dot-source：`../../api/applications/projects`, `@ant-design/icons`, `antd`

### `product/frontend/src/app/navigation/ModuleNavigation.tsx`
- `DesktopModuleNavigation`
- `MobileModuleNavigation`
主要 import / dot-source：`../../api/system/system`, `../../api/workspace`, `../shell/AppHeader`, `./routes`, `@ant-design/icons`, `antd`

### `product/frontend/src/app/navigation/ProductShellComponents.test.tsx`
主要 import / dot-source：`../../shared/ui/TaskActionBar`, `./ApplicationSwitcher`, `./ModuleNavigation`, `@testing-library/react`, `vitest`

### `product/frontend/src/app/navigation/routes.ts`
- `AppRoute`
- `ProductAreaRoute`
- `normalizeRoute`
- `productAreas`

### `product/frontend/src/app/notifications/FrontendBuildNotice.test.tsx`
主要 import / dot-source：`../../shared/runtime/buildIdentity`, `./FrontendBuildNotice`, `@testing-library/react`, `vitest`

### `product/frontend/src/app/notifications/FrontendBuildNotice.tsx`
- `FrontendBuildNotice`
主要 import / dot-source：`../../api/system/system`, `../../shared/runtime/buildIdentity`, `@ant-design/icons`, `antd`, `react`

### `product/frontend/src/app/notifications/NotificationCenter.test.tsx`
主要 import / dot-source：`../../api/http`, `./NotificationCenter`, `@testing-library/react`, `vitest`

### `product/frontend/src/app/notifications/NotificationCenter.tsx`
- `NotificationItem`
- `NotificationCenter`
- `enqueueNotification`
- `isNotificationError`
- `notificationDurationMs`
- `notificationKey`
- `removeExpiredNotifications`
- `useNotificationExpiry`
主要 import / dot-source：`../../api/http`, `@ant-design/icons`, `antd`, `react`

### `product/frontend/src/app/shell/AppHeader.tsx`
- `AppHeader`
- `aiStatusLabel`
- `mcpStatusLabel`
- `systemStatusLabel`
主要 import / dot-source：`../../api/applications/projects`, `../../api/assistance/llm`, `../../api/system/mcp`, `../../api/system/system`, `../navigation/ApplicationSwitcher`, `../theme/ThemeContext`, `@ant-design/icons`, `antd`, `react`

### `product/frontend/src/app/shell/ControlShell.test.tsx`
主要 import / dot-source：`../../api/applications/experience`, `../../api/workspace`, `../../shared/runtime/editGuard`, `../theme/ThemeContext`, `./ControlShell`, `@testing-library/react`, `react`, `vitest`

### `product/frontend/src/app/shell/ControlShell.tsx`
- `ControlShell`
主要 import / dot-source：`../../api/applications/experience`, `../../api/applications/projects`, `../../api/http`, `../../api/system/mcp`, `../../api/system/system`, `../../api/workspace`, `../../features/access/AccessPage`, `../../features/boundaries/BusinessBoundaryPage`, `../../features/changes/ChangesPage`, `../../features/checks/CurrentTestsPage`, `../../features/environment/EnvironmentPage`, `../../features/environment/OfficialDevelopmentJourney`, `../../features/environment/OfficialSamplePanel`, `../../features/history/CheckHistoryPage`, `../../features/settings/LLMSettingsDrawer`, `../../features/system/RuntimePage`, `../../features/tools/ToolsPage`, `../../features/workspace/WorkbenchPage`, `../../shared/runtime/editGuard`, `../navigation/ModuleNavigation`, `../navigation/routes`, `../notifications/FrontendBuildNotice`, `../notifications/NotificationCenter`, `../state/useCheckActivity`, `../state/useProjectWorkspace`, `../state/useSystemStatus`, `./AppHeader`, `./ErrorRecovery`, `./RetainedWorkPages`, `antd`, `react`, `react-router-dom`

### `product/frontend/src/app/shell/ErrorRecovery.tsx`
- `ErrorRecovery`
主要 import / dot-source：`../../api/http`, `antd`

### `product/frontend/src/app/shell/RetainedWorkPages.test.tsx`
主要 import / dot-source：`./RetainedWorkPages`, `@testing-library/react`, `react`, `vitest`

### `product/frontend/src/app/shell/RetainedWorkPages.tsx`
- `RetainedWorkPages`
主要 import / dot-source：`../../shared/runtime/visibility`, `react`

### `product/frontend/src/app/state/useCheckActivity.test.ts`
主要 import / dot-source：`../../api/checks/currentChecks`, `./useCheckActivity`, `@testing-library/react`, `vitest`

### `product/frontend/src/app/state/useCheckActivity.ts`
- `useCheckActivity`
主要 import / dot-source：`../../api/checks/currentChecks`, `../../shared/presentation/execution`, `react`

### `product/frontend/src/app/state/useProjectWorkspace.test.ts`
主要 import / dot-source：`../../api/workspace`, `../../shared/runtime/browserState`, `./useProjectWorkspace`, `@testing-library/react`, `vitest`

### `product/frontend/src/app/state/useProjectWorkspace.ts`
- `useProjectWorkspace`
主要 import / dot-source：`../../api/applications/experience`, `../../api/applications/projects`, `../../api/http`, `../../api/workspace`, `../../shared/runtime/browserState`, `../../shared/runtime/useLiveRead`, `react`

### `product/frontend/src/app/state/useSystemStatus.ts`
- `useSystemStatus`
主要 import / dot-source：`../../api/assistance/llm`, `../../api/system/system`, `react`

### `product/frontend/src/app/theme/theme.ts`
- `ResolvedTheme`
- `createProductTheme`
- `darkDesignTokens`
- `lightDesignTokens`
主要 import / dot-source：`../../shared/ui/tokens`, `antd`

### `product/frontend/src/app/theme/ThemeContext.test.tsx`
主要 import / dot-source：`../../shared/ui/tokens`, `./ThemeContext`, `@testing-library/react`, `antd`, `vitest`

### `product/frontend/src/app/theme/ThemeContext.tsx`
- `ThemeMode`
- `ProductThemeProvider`
- `useThemeMode`
主要 import / dot-source：`../../shared/ui/tokens`, `./theme`, `antd`, `antd/locale/zh_CN`, `react`

### `product/frontend/src/features/access/AccessPage.test.tsx`
主要 import / dot-source：`./AccessPage`, `@testing-library/react`, `vitest`

### `product/frontend/src/features/access/AccessPage.tsx`
- `AccessPage`
主要 import / dot-source：`../../api/applications/projects`, `../../api/workspace`, `../../shared/ui/Editorial`, `./ApplicationSetup`, `antd`, `react`

### `product/frontend/src/features/access/ApplicationSetup.test.tsx`
主要 import / dot-source：`./ApplicationSetup`, `@testing-library/react`, `vitest`

### `product/frontend/src/features/access/ApplicationSetup.tsx`
- `ApplicationSetup`
主要 import / dot-source：`../../api/applications/onboarding`, `../../api/applications/projects`, `../../api/http`, `../../api/workspace`, `../../shared/runtime/editGuard`, `../../shared/ui/StatusBadge`, `../../shared/ui/TaskActionBar`, `../assistant/AssistantPanel`, `./CandidateReview`, `./ConnectionSupport`, `./ControlledRuntimePanel`, `@ant-design/icons`, `antd`, `react`

### `product/frontend/src/features/access/CandidateReview.test.tsx`
主要 import / dot-source：`../../api/applications/projects`, `./CandidateReview`, `@testing-library/react`, `vitest`

### `product/frontend/src/features/access/CandidateReview.tsx`
- `CandidateReview`
主要 import / dot-source：`../../api/applications/projects`, `../../shared/runtime/editGuard`, `../../shared/ui/TaskReceipt`, `antd`, `react`

### `product/frontend/src/features/access/ConnectionSupport.tsx`
- `ConnectionSupport`
主要 import / dot-source：`../../shared/ui/StatusBadge`

### `product/frontend/src/features/access/ControlledRuntimePanel.test.tsx`
主要 import / dot-source：`./ControlledRuntimePanel`, `@testing-library/react`, `vitest`

### `product/frontend/src/features/access/ControlledRuntimePanel.tsx`
- `ApplicationRuntimeSettings`
- `ControlledRuntimePanel`
主要 import / dot-source：`../../api/applications/controlledRuntime`, `../../api/applications/projects`, `../../api/http`, `../../shared/ui/StatusBadge`, `antd`, `react`

### `product/frontend/src/features/assistant/AssistantPanel.test.tsx`
主要 import / dot-source：`./AssistantPanel`, `@testing-library/react`, `vitest`

### `product/frontend/src/features/assistant/AssistantPanel.tsx`
- `AssistantPanel`
主要 import / dot-source：`../../api/assistance/assistant`, `../../api/http`, `antd`, `react`

### `product/frontend/src/features/boundaries/BusinessBoundaryPage.test.tsx`
主要 import / dot-source：`../../api/boundaries/businessBoundaries`, `./BusinessBoundaryPage`, `./proposals/BoundaryProposalEditor`, `@testing-library/react`, `vitest`

### `product/frontend/src/features/boundaries/BusinessBoundaryPage.tsx`
- `BusinessBoundaryPage`
主要 import / dot-source：`../../api/applications/projects`, `../../api/boundaries/businessBoundaries`, `../../api/http`, `../../shared/runtime/editGuard`, `../../shared/ui/Editorial`, `../../shared/ui/PageTaskHeader`, `../../shared/ui/SearchField`, `../../shared/ui/StatusBadge`, `../../shared/ui/TaskReceipt`, `./RuleCandidatesPanel`, `./RuleDetailsPanel`, `./definitions/CurrentBoundaryObjects`, `./draft/BoundaryMaintenanceEditor`, `./draft/boundaryLabels`, `./proposals/BoundaryProposalEditor`, `./proposals/BoundaryProposalReview`, `antd`, `react`

### `product/frontend/src/features/boundaries/definitions/BoundaryObjectsWorkspace.tsx`
- `DraftAction`
- `DraftEffect`
- `ObjectDrafts`
- `BoundaryObjectsWorkspace`
主要 import / dot-source：`../../../api/boundaries/businessBoundaries`, `../../../shared/ui/SearchField`, `../../../shared/ui/StatusBadge`, `../draft/boundaryLabels`, `./ImplementationSelector`, `antd`, `react`

### `product/frontend/src/features/boundaries/definitions/CurrentBoundaryObjects.tsx`
- `BoundaryEditFocus`
- `CurrentBoundaryObjects`
主要 import / dot-source：`../../../api/boundaries/businessBoundaries`, `../../../shared/ui/SearchField`, `../../../shared/ui/StatusBadge`, `antd`, `react`

### `product/frontend/src/features/boundaries/definitions/ImplementationSelector.tsx`
- `ImplementationSelector`
主要 import / dot-source：`../../../api/boundaries/businessBoundaries`, `../../assistant/AssistantPanel`, `../draft/boundaryLabels`, `antd`

### `product/frontend/src/features/boundaries/draft/boundaryLabels.ts`
- `confidenceLabels`
- `effectKindLabels`
- `expectationLabels`
- `relationLabels`
主要 import / dot-source：`../../../api/boundaries/businessBoundaries`

### `product/frontend/src/features/boundaries/draft/BoundaryMaintenanceEditor.test.tsx`
主要 import / dot-source：`../../../api/boundaries/businessBoundaries`, `./BoundaryMaintenanceEditor`, `@testing-library/react`, `vitest`

### `product/frontend/src/features/boundaries/draft/BoundaryMaintenanceEditor.tsx`
- `BoundaryMaintenanceEditor`
主要 import / dot-source：`../../../api/boundaries/businessBoundaries`, `../../../api/boundaries/permissionDrafts`, `../../../shared/runtime/editGuard`, `../../../shared/ui/SearchField`, `../../../shared/ui/StatusBadge`, `../definitions/BoundaryObjectsWorkspace`, `../definitions/CurrentBoundaryObjects`, `../rules/PermissionRuleForm`, `./PermissionDraftAssist`, `antd`, `react`

### `product/frontend/src/features/boundaries/draft/PermissionDraftAssist.tsx`
- `PermissionDraftAssist`
主要 import / dot-source：`../../../api/boundaries/businessBoundaries`, `../../../api/boundaries/permissionDrafts`, `./boundaryLabels`, `antd`, `react`

### `product/frontend/src/features/boundaries/proposals/BoundaryProposalEditor.tsx`
- `BoundaryProposalEditor`
主要 import / dot-source：`../../../api/boundaries/businessBoundaries`, `../../../shared/runtime/editGuard`, `../../../shared/ui/Editorial`, `../../../shared/ui/StatusBadge`, `../../../shared/ui/TaskReceipt`, `../draft/boundaryLabels`, `../rules/PermissionRuleForm`, `antd`, `react`

### `product/frontend/src/features/boundaries/proposals/BoundaryProposalReview.test.tsx`
主要 import / dot-source：`../../../api/boundaries/businessBoundaries`, `./BoundaryProposalReview`, `@testing-library/react`, `vitest`

### `product/frontend/src/features/boundaries/proposals/BoundaryProposalReview.tsx`
- `BoundaryProposalReview`
主要 import / dot-source：`../../../api/boundaries/businessBoundaries`, `../../../shared/ui/StatusBadge`, `../draft/boundaryLabels`, `antd`, `react`

### `product/frontend/src/features/boundaries/RuleCandidatesPanel.test.tsx`
主要 import / dot-source：`../../api/http`, `./RuleCandidatesPanel`, `@testing-library/react`, `vitest`

### `product/frontend/src/features/boundaries/RuleCandidatesPanel.tsx`
- `RuleCandidatesPanel`
主要 import / dot-source：`../../api/boundaries/ruleCandidates`, `../../api/http`, `../../shared/runtime/editGuard`, `../../shared/ui/StatusBadge`, `../../shared/ui/TaskActionBar`, `antd`, `react`

### `product/frontend/src/features/boundaries/RuleDetailsPanel.test.tsx`
主要 import / dot-source：`./RuleDetailsPanel`, `@testing-library/react`, `vitest`

### `product/frontend/src/features/boundaries/RuleDetailsPanel.tsx`
- `RuleDetailsPanel`
主要 import / dot-source：`../../api/boundaries/ruleDetails`, `../../shared/format/time`, `../../shared/ui/Editorial`, `../../shared/ui/StatusBadge`, `../../shared/ui/TaskActionBar`, `antd`, `react`

### `product/frontend/src/features/boundaries/rules/PermissionRuleForm.tsx`
- `PermissionRuleForm`
主要 import / dot-source：`../../../api/boundaries/businessBoundaries`, `../../../shared/runtime/editGuard`, `../draft/boundaryLabels`, `antd`, `react`

### `product/frontend/src/features/changes/ChangesPage.test.tsx`
主要 import / dot-source：`./ChangesPage`, `@testing-library/react`, `vitest`

### `product/frontend/src/features/changes/ChangesPage.tsx`
- `ChangesPage`
主要 import / dot-source：`../../api/applications/projects`, `../../api/changes/development`, `../../api/changes/sourceChanges`, `../../api/checks/repairs`, `../../api/http`, `../../shared/format/time`, `../../shared/runtime/useLiveRead`, `../../shared/runtime/visibility`, `../../shared/ui/Editorial`, `../../shared/ui/StatusBadge`, `./delivery/DeliveryFacts`, `./delivery/SourceIdentityPanel`, `./registration/ChangeRegistration`, `./repair/RepairDelivery`, `./runtime/ChangeRuntimeAction`, `antd`, `react`

### `product/frontend/src/features/changes/delivery/DeliveryFacts.test.tsx`
主要 import / dot-source：`../../../api/changes/sourceChanges`, `../tasks/TaskRecords`, `./DeliveryFacts`, `@testing-library/react`, `vitest`

### `product/frontend/src/features/changes/delivery/DeliveryFacts.tsx`
- `DeliveryFacts`
主要 import / dot-source：`../../../api/changes/development`, `../../../api/changes/sourceChanges`, `../../../api/checks/repairs`, `../../../api/http`, `../../../shared/runtime/useLiveRead`, `antd`, `react`

### `product/frontend/src/features/changes/delivery/SourceIdentityPanel.test.tsx`
主要 import / dot-source：`../../../api/http`, `./SourceIdentityPanel`, `@testing-library/react`, `vitest`

### `product/frontend/src/features/changes/delivery/SourceIdentityPanel.tsx`
- `SourceIdentityPanel`
主要 import / dot-source：`../../../api/changes/sourceIdentity`, `../../../api/http`, `../../../shared/format/time`, `@ant-design/icons`, `antd`, `react`

### `product/frontend/src/features/changes/pendingOperations.ts`
- `clearPendingOperation`
- `readPendingOperation`
- `savePendingOperation`

### `product/frontend/src/features/changes/registration/ChangeRegistration.tsx`
- `ChangeRegistration`
主要 import / dot-source：`../../../api/changes/development`, `../../../api/changes/sourceChanges`, `../../../api/checks/repairs`, `../../../api/http`, `../pendingOperations`, `antd`, `react`

### `product/frontend/src/features/changes/repair/RepairComparison.test.tsx`
主要 import / dot-source：`../../../api/checks/repairs`, `./RepairComparison`, `@testing-library/react`, `vitest`

### `product/frontend/src/features/changes/repair/RepairComparison.tsx`
- `RepairComparison`
主要 import / dot-source：`../../../api/checks/repairs`, `antd`

### `product/frontend/src/features/changes/repair/RepairDelivery.test.tsx`
主要 import / dot-source：`../../../api/checks/repairs`, `./RepairDelivery`, `@testing-library/react`, `vitest`

### `product/frontend/src/features/changes/repair/RepairDelivery.tsx`
- `RepairTask`
- `RepairDelivery`
主要 import / dot-source：`../../../api/changes/sourceChanges`, `../../../api/checks/repairs`, `../../../shared/ui/Editorial`, `./RepairComparison`, `antd`, `react`

### `product/frontend/src/features/changes/runtime/ChangeRuntimeAction.test.tsx`
主要 import / dot-source：`../../../api/changes/development`, `./ChangeRuntimeAction`, `@testing-library/react`, `vitest`

### `product/frontend/src/features/changes/runtime/ChangeRuntimeAction.tsx`
- `ChangeRuntimeAction`
主要 import / dot-source：`../../../api/changes/development`, `../../../api/http`, `../pendingOperations`, `antd`, `react`

### `product/frontend/src/features/changes/tasks/DevelopmentTaskPanel.test.tsx`
主要 import / dot-source：`../../../api/changes/development`, `./DevelopmentTaskPanel`, `@testing-library/react`, `vitest`

### `product/frontend/src/features/changes/tasks/DevelopmentTaskPanel.tsx`
- `DevelopmentTaskPanel`
主要 import / dot-source：`../../../api/changes/development`, `../../../api/http`, `../../../shared/format/time`, `../../../shared/ui/StatusBadge`, `../pendingOperations`, `antd`, `react`

### `product/frontend/src/features/changes/tasks/TaskRecords.tsx`
- `TaskDeliveryIndex`
- `TaskHistory`
主要 import / dot-source：`../../../api/changes/development`, `../../../api/http`, `../../../shared/format/time`, `antd`, `react`

### `product/frontend/src/features/checks/CurrentTestsPage.test.tsx`
主要 import / dot-source：`../../api/checks/currentChecks`, `../../api/http`, `../../api/workspace`, `../../testing/fixtures/results`, `./CurrentTestsPage`, `@testing-library/react`, `vitest`

### `product/frontend/src/features/checks/CurrentTestsPage.tsx`
- `CurrentTestsPage`
主要 import / dot-source：`../../api/checks/currentChecks`, `../../api/http`, `../../shared/presentation/execution`, `../../shared/runtime/editGuard`, `../../shared/runtime/useLiveRead`, `../../shared/runtime/visibility`, `../../shared/ui/Editorial`, `../../shared/ui/TaskActionBar`, `../changes/delivery/SourceIdentityPanel`, `../preparation/PreparationPage`, `../results/CurrentResultStory`, `../results/overview/ResultOverview`, `antd`, `react`

### `product/frontend/src/features/environment/EnvironmentHistory.test.tsx`
主要 import / dot-source：`./EnvironmentHistory`, `@testing-library/react`, `react`, `vitest`

### `product/frontend/src/features/environment/EnvironmentHistory.tsx`
- `EnvironmentHistory`
主要 import / dot-source：`../../api/applications/projects`, `../../api/checks/currentChecks`, `../../api/http`, `../../shared/ui/Editorial`, `../changes/delivery/SourceIdentityPanel`, `../history/CheckHistoryPage`, `../results/CurrentResultStory`, `antd`, `react`

### `product/frontend/src/features/environment/EnvironmentPage.test.tsx`
主要 import / dot-source：`./EnvironmentPage`, `@testing-library/react`, `vitest`

### `product/frontend/src/features/environment/EnvironmentPage.tsx`
- `EnvironmentPage`
主要 import / dot-source：`../../api/applications/experience`, `../../api/applications/projects`, `../../api/http`, `../../api/system/system`, `../../api/workspace`, `../../shared/format/time`, `../../shared/ui/Editorial`, `../access/ControlledRuntimePanel`, `./EnvironmentHistory`, `./OfficialSamplePanel`, `@ant-design/icons`, `antd`, `react`

### `product/frontend/src/features/environment/OfficialDevelopmentJourney.test.tsx`
主要 import / dot-source：`../../api/applications/experience`, `./OfficialDevelopmentJourney`, `@testing-library/react`, `vitest`

### `product/frontend/src/features/environment/OfficialDevelopmentJourney.tsx`
- `OfficialDevelopmentJourney`
主要 import / dot-source：`../../api/applications/experience`, `../../api/checks/repairs`, `../../api/http`, `../../shared/runtime/useLiveRead`, `../../shared/runtime/visibility`, `antd`, `react`

### `product/frontend/src/features/environment/OfficialSamplePanel.test.tsx`
主要 import / dot-source：`../../api/applications/experience`, `./OfficialSamplePanel`, `@testing-library/react`, `vitest`

### `product/frontend/src/features/environment/OfficialSamplePanel.tsx`
- `OfficialSamplePanel`
主要 import / dot-source：`../../api/applications/experience`, `../../api/http`, `../../shared/ui/StatusBadge`, `antd`, `react`

### `product/frontend/src/features/history/CheckHistoryPage.test.tsx`
主要 import / dot-source：`../../api/checks/currentChecks`, `../../shared/runtime/visibility`, `./CheckHistoryPage`, `@testing-library/react`, `react`, `vitest`

### `product/frontend/src/features/history/CheckHistoryPage.tsx`
- `CheckHistoryPage`
主要 import / dot-source：`../../api/applications/projects`, `../../api/checks/currentChecks`, `../../api/http`, `../../shared/format/time`, `../../shared/presentation/execution`, `../../shared/runtime/useLiveRead`, `../../shared/runtime/visibility`, `../../shared/ui/Editorial`, `../../shared/ui/SearchField`, `../../shared/ui/StatusBadge`, `antd`, `react`

### `product/frontend/src/features/identities/TestIdentityPage.test.tsx`
主要 import / dot-source：`../../api/boundaries/businessBoundaries`, `../../api/preparation/testIdentities`, `./TestIdentityPage`, `@testing-library/react`, `vitest`

### `product/frontend/src/features/identities/TestIdentityPage.tsx`
- `TestIdentityPage`
主要 import / dot-source：`../../api/applications/projects`, `../../api/boundaries/businessBoundaries`, `../../api/http`, `../../api/preparation/testIdentities`, `../../api/workspace`, `../../shared/runtime/editGuard`, `../../shared/ui/Editorial`, `../../shared/ui/StatusBadge`, `../../shared/ui/TaskActionBar`, `../../shared/ui/TaskReceipt`, `antd`, `react`

### `product/frontend/src/features/preparation/evidence/EvidenceMaterials.test.tsx`
主要 import / dot-source：`../../../api/preparation/preparation`, `./EvidenceMaterials`, `@testing-library/react`, `vitest`

### `product/frontend/src/features/preparation/evidence/EvidenceMaterials.tsx`
- `EvidenceMaterials`
主要 import / dot-source：`../../../api/http`, `../../../api/preparation/preparation`, `../../../shared/ui/Editorial`, `../supplemental/SupplementalMaterials`, `@ant-design/icons`, `antd`, `react`

### `product/frontend/src/features/preparation/materials/MaterialEditor.test.tsx`
主要 import / dot-source：`./MaterialEditor`, `@testing-library/react`, `vitest`

### `product/frontend/src/features/preparation/materials/MaterialEditor.tsx`
- `MaterialEditor`
- `materialName`
主要 import / dot-source：`../../../api/http`, `../../../api/preparation/preparation`, `../../../shared/runtime/editGuard`, `../../../shared/ui/Editorial`, `antd`, `react`

### `product/frontend/src/features/preparation/materials/MaterialOverview.tsx`
- `MaterialOverview`
主要 import / dot-source：`../../../api/preparation/preparation`, `../../../api/preparation/preparationGuidance`, `../../../shared/ui/StatusBadge`, `@ant-design/icons`, `antd`, `react`

### `product/frontend/src/features/preparation/PreparationPage.test.tsx`
主要 import / dot-source：`../../api/preparation/preparation`, `../../api/workspace`, `./PreparationPage`, `@testing-library/react`, `vitest`

### `product/frontend/src/features/preparation/PreparationPage.tsx`
- `PreparationPage`
主要 import / dot-source：`../../api/applications/projects`, `../../api/http`, `../../api/preparation/preparation`, `../../api/preparation/preparationGuidance`, `../../api/preparation/proofSources`, `../../api/preparation/testIdentities`, `../../api/workspace`, `../../shared/navigation/taskDestination`, `../../shared/runtime/editGuard`, `../../shared/runtime/useLiveRead`, `../../shared/runtime/visibility`, `../../shared/ui/Editorial`, `../../shared/ui/TaskActionBar`, `../../shared/ui/TaskReceipt`, `../assistant/AssistantPanel`, `../identities/TestIdentityPage`, `../recording/RecordingPage`, `./evidence/EvidenceMaterials`, `./materials/MaterialEditor`, `./materials/MaterialOverview`, `./proof-sources/ProofSourcesPanel`, `antd`, `react`

### `product/frontend/src/features/preparation/proof-sources/proofSourceOperations.test.ts`
主要 import / dot-source：`./proofSourceOperations`, `vitest`

### `product/frontend/src/features/preparation/proof-sources/proofSourceOperations.ts`
- `PendingProofOperation`
- `clearProofOperation`
- `readProofOperation`
- `saveProofOperation`
主要 import / dot-source：`../../../api/preparation/proofSources`

### `product/frontend/src/features/preparation/proof-sources/ProofSourcesPanel.test.tsx`
主要 import / dot-source：`./ProofSourcesPanel`, `@testing-library/react`, `vitest`

### `product/frontend/src/features/preparation/proof-sources/ProofSourcesPanel.tsx`
- `ProofSourcesPanel`
主要 import / dot-source：`../../../api/preparation/proofSources`, `../../../shared/runtime/editGuard`, `../../../shared/ui/Editorial`, `../../../shared/ui/StatusBadge`, `../../../shared/ui/TaskActionBar`, `./useProofSources`, `antd`, `react`

### `product/frontend/src/features/preparation/proof-sources/useProofSources.ts`
- `useProofSources`
主要 import / dot-source：`../../../api/http`, `../../../api/preparation/proofSources`, `./proofSourceOperations`, `react`

### `product/frontend/src/features/preparation/supplemental/SupplementalMaterials.test.tsx`
主要 import / dot-source：`../../../api/http`, `./SupplementalMaterials`, `@testing-library/react`, `vitest`

### `product/frontend/src/features/preparation/supplemental/SupplementalMaterials.tsx`
- `SupplementalMaterials`
主要 import / dot-source：`../../../api/http`, `../../../api/preparation/supplementalMaterials`, `../../../shared/format/time`, `../../../shared/runtime/editGuard`, `../../../shared/ui/Editorial`, `../../../shared/ui/StatusBadge`, `@ant-design/icons`, `antd`, `react`

### `product/frontend/src/features/recording/FlowDraftReview.tsx`
- `FlowDraftReview`
主要 import / dot-source：`../../api/preparation/recordings`, `antd`

### `product/frontend/src/features/recording/RecordingCaptureCard.tsx`
- `RecordingCaptureCard`
- `captureLabel`
主要 import / dot-source：`../../api/preparation/jobs`, `../../api/preparation/recordings`, `../../shared/presentation/execution`, `../../shared/runtime/browserState`, `../../shared/ui/StatusBadge`, `antd`, `react`

### `product/frontend/src/features/recording/RecordingPage.test.tsx`
主要 import / dot-source：`../../api/workspace`, `./RecordingPage`, `@testing-library/react`, `vitest`

### `product/frontend/src/features/recording/RecordingPage.tsx`
- `RecordingPage`
主要 import / dot-source：`../../api/applications/projects`, `../../api/http`, `../../api/preparation/jobs`, `../../api/preparation/preparation`, `../../api/preparation/recordings`, `../../api/workspace`, `../../shared/runtime/browserState`, `../../shared/runtime/editGuard`, `../../shared/ui/Editorial`, `../../shared/ui/TaskActionBar`, `../../shared/ui/TaskReceipt`, `../assistant/AssistantPanel`, `./FlowDraftReview`, `./RecordingCaptureCard`, `antd`, `react`

### `product/frontend/src/features/results/CurrentResultStory.test.tsx`
主要 import / dot-source：`../../api/checks/currentChecks`, `../../shared/runtime/visibility`, `../../testing/fixtures/results`, `./CurrentResultStory`, `@testing-library/react`, `vitest`

### `product/frontend/src/features/results/CurrentResultStory.tsx`
- `CurrentResultStory`
主要 import / dot-source：`../../api/checks/currentChecks`, `../../api/http`, `../../shared/format/time`, `../../shared/runtime/visibility`, `../../shared/ui/Editorial`, `../assistant/AssistantPanel`, `./investigation/DiagnosisSummary`, `./investigation/ExecutionPath`, `./investigation/tracePresentation`, `./observations/ObservationSources`, `./observations/observationPresentation`, `./overview/ProofCoverage`, `./overview/ResultOverview`, `antd`, `react`

### `product/frontend/src/features/results/investigation/DiagnosisSummary.test.tsx`
主要 import / dot-source：`../../../testing/fixtures/results`, `./DiagnosisSummary`, `@testing-library/react`, `vitest`

### `product/frontend/src/features/results/investigation/DiagnosisSummary.tsx`
- `DiagnosisSummary`
主要 import / dot-source：`../../../api/checks/currentChecks`, `./tracePresentation`, `@ant-design/icons`, `antd`

### `product/frontend/src/features/results/investigation/ExecutionPath.test.tsx`
主要 import / dot-source：`../../../api/checks/currentChecks`, `../../../testing/fixtures/results`, `./ExecutionPath`, `@testing-library/react`, `vitest`

### `product/frontend/src/features/results/investigation/ExecutionPath.tsx`
- `ExecutionPath`
主要 import / dot-source：`../../../api/checks/currentChecks`, `./tracePresentation`, `@ant-design/icons`, `react`

### `product/frontend/src/features/results/investigation/tracePresentation.ts`
- `breakpointLabels`
- `precisionDescriptions`
- `precisionLabels`
- `traceEventContext`
- `traceEventLabel`
- `traceKindLabels`
- `traceLimitations`
主要 import / dot-source：`../../../api/checks/currentChecks`

### `product/frontend/src/features/results/observations/observationPresentation.test.ts`
主要 import / dot-source：`../../../testing/fixtures/results`, `./observationPresentation`, `vitest`

### `product/frontend/src/features/results/observations/observationPresentation.ts`
- `observationGroups`
- `observationStatus`
- `phaseLabels`
- `sourceLabels`
- `sourceReading`
主要 import / dot-source：`../../../api/checks/currentChecks`

### `product/frontend/src/features/results/observations/ObservationSources.test.tsx`
主要 import / dot-source：`../../../api/checks/currentChecks`, `../../../testing/fixtures/results`, `./ObservationSources`, `./observationPresentation`, `@testing-library/react`, `vitest`

### `product/frontend/src/features/results/observations/ObservationSources.tsx`
- `ObservationSources`
主要 import / dot-source：`../../../api/checks/currentChecks`, `../../../shared/ui/StatusBadge`, `./observationPresentation`, `antd`

### `product/frontend/src/features/results/overview/ProofCoverage.tsx`
- `ProofCoverage`
主要 import / dot-source：`../../../api/checks/currentChecks`, `antd`

### `product/frontend/src/features/results/overview/ResultOverview.tsx`
- `BusinessEffects`
- `ResultBadge`
- `ResultOverviewHeader`
- `ResultScope`
- `caseJudgement`
- `resourceOwner`
主要 import / dot-source：`../../../api/checks/currentChecks`, `../../../api/checks/repairs`, `../../../shared/runtime/visibility`, `../../../shared/ui/StatusBadge`, `antd`, `react`

### `product/frontend/src/features/settings/LLMSettingsDrawer.test.tsx`
主要 import / dot-source：`./LLMSettingsDrawer`, `@testing-library/react`, `vitest`

### `product/frontend/src/features/settings/LLMSettingsDrawer.tsx`
- `LLMSettingsDrawer`
主要 import / dot-source：`../../api/assistance/llm`, `../../api/http`, `../../shared/ui/StatusBadge`, `antd`, `react`

### `product/frontend/src/features/system/RuntimePage.test.tsx`
主要 import / dot-source：`../../api/system/system`, `./RuntimePage`, `@testing-library/react`, `vitest`

### `product/frontend/src/features/system/RuntimePage.tsx`
- `RuntimePage`
主要 import / dot-source：`../../api/assistance/llm`, `../../api/system/system`, `../../shared/runtime/buildIdentity`, `../../shared/ui/Editorial`, `../../shared/ui/StatusBadge`, `antd`, `react`

### `product/frontend/src/features/tools/AgentPageHeader.tsx`
- `AgentPageHeader`
主要 import / dot-source：`../../shared/ui/Editorial`, `antd`

### `product/frontend/src/features/tools/clientGuides.ts`
- `ClientGuide`
- `MCPClientKey`
- `clientGuide`
- `clientOptions`

### `product/frontend/src/features/tools/MCPAccessCard.test.tsx`
主要 import / dot-source：`./MCPAccessCard`, `@testing-library/react`, `vitest`

### `product/frontend/src/features/tools/MCPAccessCard.tsx`
- `MCPAccessCard`
主要 import / dot-source：`../../api/http`, `../../api/system/mcp`, `../../shared/ui/StatusBadge`, `./clientGuides`, `antd`, `react`

### `product/frontend/src/features/tools/ToolsPage.test.tsx`
主要 import / dot-source：`./ToolsPage`, `@testing-library/react`, `vitest`

### `product/frontend/src/features/tools/ToolsPage.tsx`
- `ToolsPage`
主要 import / dot-source：`../../api/applications/projects`, `../../api/http`, `../../api/system/mcp`, `../../shared/ui/Editorial`, `./AgentPageHeader`, `./MCPAccessCard`

### `product/frontend/src/features/workspace/PermissionAcceptance.test.tsx`
主要 import / dot-source：`../../testing/fixtures/results`, `./PermissionAcceptance`, `@testing-library/react`, `vitest`

### `product/frontend/src/features/workspace/PermissionAcceptance.tsx`
- `PermissionAcceptance`
主要 import / dot-source：`../../api/checks/currentChecks`, `../../api/http`, `../../shared/runtime/useLiveRead`, `antd`, `react`

### `product/frontend/src/features/workspace/WorkbenchPage.test.tsx`
主要 import / dot-source：`../../api/checks/currentChecks`, `../../api/workspace`, `../../testing/fixtures/results`, `./WorkbenchPage`, `@testing-library/react`, `vitest`

### `product/frontend/src/features/workspace/WorkbenchPage.tsx`
- `WorkbenchPage`
主要 import / dot-source：`../../api/applications/experience`, `../../api/applications/projects`, `../../api/checks/currentChecks`, `../../api/http`, `../../api/preparation/preparation`, `../../api/system/mcp`, `../../api/system/system`, `../../api/workspace`, `../../shared/navigation/taskDestination`, `../../shared/runtime/useLiveRead`, `../../shared/ui/Editorial`, `antd`, `react`

### `product/frontend/src/main.tsx`
主要 import / dot-source：`./app/shell/ControlShell`, `./app/theme/ThemeContext`, `react`, `react-dom/client`

### `product/frontend/src/shared/format/time.ts`
- `formatTimestamp`

### `product/frontend/src/shared/navigation/taskDestination.test.ts`
主要 import / dot-source：`../../api/workspace`, `./taskDestination`, `vitest`

### `product/frontend/src/shared/navigation/taskDestination.ts`
- `taskDestination`
主要 import / dot-source：`../../api/workspace`

### `product/frontend/src/shared/presentation/execution.ts`
- `lifecycleLabel`
- `lifecycleLabels`
- `verdictLabel`
- `verdictLabels`

### `product/frontend/src/shared/runtime/browserState.ts`
- `browserState`
主要 import / dot-source：`../../api/applications/projects`, `../../api/preparation/recordings`

### `product/frontend/src/shared/runtime/buildIdentity.ts`
- `frontendBuildId`
- `frontendIdentityState`
主要 import / dot-source：`../../api/system/system`

### `product/frontend/src/shared/runtime/editGuard.ts`
- `TaskGuardContext`
- `useTaskGuard`
主要 import / dot-source：`./visibility`, `react`

### `product/frontend/src/shared/runtime/useLiveRead.test.ts`
主要 import / dot-source：`./useLiveRead`, `@testing-library/react`, `vitest`

### `product/frontend/src/shared/runtime/useLiveRead.ts`
- `useLiveRead`
主要 import / dot-source：`../../api/http`, `react`

### `product/frontend/src/shared/runtime/visibility.ts`
- `WorkPageVisible`
主要 import / dot-source：`react`

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

### `product/frontend/src/shared/ui/TaskReceipt.tsx`
- `TaskReceipt`
主要 import / dot-source：`antd`

### `product/frontend/src/shared/ui/tokens.test.ts`
主要 import / dot-source：`./tokens`, `vitest`

### `product/frontend/src/shared/ui/tokens.ts`
- `ProductTheme`
- `designTokens`
- `metrics`
- `palettes`
- `productCssVariables`

### `product/frontend/src/testing/fixtures/results.ts`
主要 import / dot-source：`../../api/checks/currentChecks`

### `product/frontend/src/testing/setup.ts`
主要 import / dot-source：`@testing-library/react`, `vitest`

<!-- GENERATED:END -->
