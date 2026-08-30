# 自动代码参考：前端

> 生成区域只描述当前代码结构；职责与安全理由由模块参考和任务指南维护。

<!-- GENERATED:START -->

<!-- 此区域由 scripts/docs/generate.py 从 product/frontend/src/ 读取。 -->

### `product/frontend/src/api/assistant.ts`
- `AssistantEntity`
- `AssistantSuggestion`
- `AssistantSurfaceView`
- `ProjectAssistantSurface`
- `assistantApi`
主要 import / dot-source：`./http`

### `product/frontend/src/api/checks.ts`
- `CheckPreviewActionDto`
- `CheckPreviewDto`
- `CheckPreviewGapDto`
- `CheckPreviewItemDto`
- `CheckSubmissionDto`
- `checksApi`
主要 import / dot-source：`./http`, `./runs`

### `product/frontend/src/api/contracts.ts`
- `PermissionActionDto`
- `PermissionBatchExpectationDto`
- `PermissionBatchRuleDto`
- `PermissionContractDto`
- `PermissionEndpointDto`
- `PermissionRelationDto`
- `PermissionResourceDto`
- `PermissionRuleDto`
- `PermissionSubjectDto`
- `SecurityEffectDto`

### `product/frontend/src/api/experience.ts`
- `OfficialExperienceDto`
- `OfficialExperienceMode`
- `experienceApi`
主要 import / dot-source：`./http`

### `product/frontend/src/api/http.test.ts`
主要 import / dot-source：`./http`, `vitest`

### `product/frontend/src/api/http.ts`
- `ApiEnvelope`
- `ErrorDiagnosis`
- `ApiError`
- `request`

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
- `MCPProjectGrant`
- `mcpAccessApi`
主要 import / dot-source：`./http`

### `product/frontend/src/api/onboarding.ts`
- `DiscoveryCandidate`
- `DiscoveryHint`
- `DiscoveryResult`
- `onboardingApi`
主要 import / dot-source：`./http`

### `product/frontend/src/api/permissionIntents.ts`
- `PermissionIntentActionDto`
- `PermissionIntentCellDto`
- `PermissionIntentExpectation`
- `PermissionIntentImplementationRebindDto`
- `PermissionIntentMatrixDto`
- `PermissionIntentProposalDto`
- `PermissionIntentProposalListDto`
- `PermissionIntentSemanticChangeDto`
- `ProtectedEffectDto`
- `SecuritySetupCompileResultDto`
- `permissionIntentsApi`
主要 import / dot-source：`./http`

### `product/frontend/src/api/projects.ts`
- `ActionCandidateDto`
- `ApplicationConnectionDto`
- `ApplicationUnderstandingDto`
- `CandidateEvidenceDto`
- `EndpointCandidateDto`
- `EndpointDiscoveryDto`
- `ProductNextActionDto`
- `ProductStatusDto`
- `ProjectDto`
- `ProjectReadinessDto`
- `RoleCandidateDto`
- `projectsApi`
主要 import / dot-source：`./http`, `./onboarding`

### `product/frontend/src/api/recordings.ts`
- `ActionSafetySetupDto`
- `ActionSafetySetupViewDto`
- `ConfirmActionSafetySetupInput`
- `FlowDraftDto`
- `FlowDraftStepDto`
- `FlowDraftVariableDto`
- `FlowDraftVariableSourceDto`
- `ObservationCandidateDto`
- `RecordingActionDto`
- `RecordingDto`
- `RecordingJobDto`
- `RecordingReviewCommand`
- `RecordingSetupDto`
- `RecordingTestIdentityDto`
- `RecordingViewDto`
- `RecoveryCandidateDto`
- `SecurityEffectCandidateDto`
- `TestResourceCandidateDto`
- `recordingsApi`
主要 import / dot-source：`./http`

### `product/frontend/src/api/results.ts`
- `EvidenceCaseSnapshotDto`
- `EvidenceDto`
- `ExecutionFactDto`
- `ExecutionTraceDto`
- `FindingDto`
- `FindingIdentityDto`
- `FindingOccurrenceDto`
- `HistoryChangeDto`
- `HistoryComparisonDto`
- `HistoryViewDto`
- `ObservationFactDto`
- `RepairContractReferenceDto`
- `RepairRequirementDto`
- `RepairVerificationDto`
- `ReportDto`
- `ResultChangeVerificationDto`
- `ResultDiagnosisDto`
- `ResultDiagnosisImpactDto`
- `ResultDiagnosisWitnessDto`
- `ResultEvidenceSourceDto`
- `ResultPresentationDto`
- `ResultPresentationIssueDto`
- `ResultRelevantIntentDto`
- `SecurityEffectFactDto`
- `TraceEventDto`
- `resultsApi`
主要 import / dot-source：`./http`

### `product/frontend/src/api/runs.ts`
- `CancelJobDto`
- `JobEventDto`
- `JobProgressDto`
- `RunDto`
- `RunnerProgressEventDto`
- `runsApi`
主要 import / dot-source：`./http`

### `product/frontend/src/api/sourceChanges.ts`
- `SourceChangeViewDto`
- `sourceChangesApi`
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

### `product/frontend/src/app/AppHeader.tsx`
- `AppHeader`
- `aiStatusLabel`
- `mcpStatusLabel`
- `systemStatusLabel`
主要 import / dot-source：`../api/llm`, `../api/mcp`, `../api/projects`, `../api/system`, `../components/ApplicationSwitcher`, `@ant-design/icons`, `antd`

### `product/frontend/src/app/browserState.ts`
- `browserState`
主要 import / dot-source：`../api/projects`, `../api/recordings`

### `product/frontend/src/app/ControlShell.test.tsx`
主要 import / dot-source：`./AppHeader`, `./ControlShell`, `@testing-library/react`, `vitest`

### `product/frontend/src/app/ControlShell.tsx`
- `ControlShell`
主要 import / dot-source：`../api/experience`, `../api/http`, `../api/mcp`, `../api/projects`, `../api/sourceChanges`, `../api/system`, `../components/ErrorRecovery`, `../components/JudgeGuideBar`, `../components/ProcessNavigation`, `../features/access/AccessPage`, `../features/checks/CheckHistoryPage`, `../features/checks/CheckResultsPage`, `../features/checks/PermissionCheckPage`, `../features/identities/TestIdentityPage`, `../features/recording/RecordingPage`, `../features/settings/LLMSettingsDrawer`, `../features/settings/ModelServicePage`, `../features/system/RuntimePage`, `../features/tools/ToolsPage`, `../features/workspace/WorkbenchPage`, `./AppHeader`, `./NotificationCenter`, `./presentation`, `./useProjectWorkspace`, `./useSystemStatus`, `antd`, `react`, `react-router-dom`

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
- `ProcessRoute`
- `ProcessStepState`
- `expectationLabel`
- `expectationLabels`
- `formatTimestamp`
- `gateDecisionLabel`
- `gateDecisionLabels`
- `integrityLabel`
- `integrityLabels`
- `lifecycleLabel`
- `lifecycleLabels`
- `normalizeRoute`
- `occurrenceStatusLabel`
- `occurrenceStatusLabels`
- `processSteps`
- `productStatusLabel`
- `productTermLabel`
- `severityLabel`
- `severityLabels`
- `verdictLabel`
- `verdictLabels`

### `product/frontend/src/app/theme.ts`
- `productTheme`
主要 import / dot-source：`antd`

### `product/frontend/src/app/useProjectWorkspace.ts`
- `useProjectWorkspace`
主要 import / dot-source：`../api/http`, `../api/projects`, `../api/runs`, `./browserState`, `react`

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
主要 import / dot-source：`../api/http`, `./AssistantPanel`, `antd`

### `product/frontend/src/components/JudgeGuideBar.test.tsx`
主要 import / dot-source：`./JudgeGuideBar`, `@testing-library/react`, `vitest`

### `product/frontend/src/components/JudgeGuideBar.tsx`
- `JudgeGuideBar`
主要 import / dot-source：`../api/experience`, `../api/projects`, `antd`

### `product/frontend/src/components/PageTaskHeader.test.tsx`
主要 import / dot-source：`./PageTaskHeader`, `@testing-library/react`, `vitest`

### `product/frontend/src/components/PageTaskHeader.tsx`
- `PageTaskHeader`
主要 import / dot-source：`antd`

### `product/frontend/src/components/ProcessNavigation.tsx`
- `DesktopProcessNavigation`
- `MobileProcessNavigation`
主要 import / dot-source：`../api/projects`, `../app/presentation`, `@ant-design/icons`, `antd`, `react`

### `product/frontend/src/components/ProductShellComponents.test.tsx`
主要 import / dot-source：`./ApplicationSwitcher`, `./ProcessNavigation`, `./TaskActionBar`, `@testing-library/react`, `vitest`

### `product/frontend/src/components/TaskActionBar.tsx`
- `TaskActionBar`
主要 import / dot-source：`antd`

### `product/frontend/src/features/access/AccessPage.test.tsx`
主要 import / dot-source：`./AccessPage`, `@testing-library/react`, `vitest`

### `product/frontend/src/features/access/AccessPage.tsx`
- `AccessPage`
主要 import / dot-source：`../../api/projects`, `../../components/PageTaskHeader`, `./ApplicationSetup`

### `product/frontend/src/features/access/ApplicationSetup.test.tsx`
主要 import / dot-source：`./ApplicationSetup`, `@testing-library/react`, `vitest`

### `product/frontend/src/features/access/ApplicationSetup.tsx`
- `ApplicationSetup`
主要 import / dot-source：`../../api/http`, `../../api/onboarding`, `../../api/projects`, `../../components/AssistantPanel`, `../../components/TaskActionBar`, `antd`, `react`

### `product/frontend/src/features/checks/CheckHistoryPage.test.tsx`
主要 import / dot-source：`./CheckHistoryPage`, `@testing-library/react`, `vitest`

### `product/frontend/src/features/checks/CheckHistoryPage.tsx`
- `CheckHistoryPage`
主要 import / dot-source：`../../api/http`, `../../api/results`, `../../app/presentation`, `../../components/PageTaskHeader`, `../../components/TaskActionBar`, `antd`, `react`

### `product/frontend/src/features/checks/CheckProgress.test.tsx`
主要 import / dot-source：`./CheckProgress`, `@testing-library/react`, `vitest`

### `product/frontend/src/features/checks/CheckProgress.tsx`
- `CheckProgress`
主要 import / dot-source：`../../api/checks`, `../../api/http`, `../../api/runs`, `../../app/browserState`, `../../app/presentation`, `antd`, `react`

### `product/frontend/src/features/checks/CheckResultsPage.test.tsx`
主要 import / dot-source：`./CheckResultsPage`, `@testing-library/react`, `vitest`

### `product/frontend/src/features/checks/CheckResultsPage.tsx`
- `CheckResultsPage`
主要 import / dot-source：`../../api/http`, `../../api/results`, `../../api/runs`, `../../app/presentation`, `../../components/AssistantPanel`, `../../components/PageTaskHeader`, `../../components/TaskActionBar`, `./EvidenceTimeline`, `./ReportPanel`, `antd`, `react`

### `product/frontend/src/features/checks/EvidenceTimeline.test.tsx`
主要 import / dot-source：`./EvidenceTimeline`, `@testing-library/react`, `vitest`

### `product/frontend/src/features/checks/EvidenceTimeline.tsx`
- `EvidenceTimeline`
主要 import / dot-source：`../../api/http`, `../../api/results`, `../../app/presentation`, `antd`, `react`

### `product/frontend/src/features/checks/PermissionCheckPage.test.tsx`
主要 import / dot-source：`./PermissionCheckPage`, `@testing-library/react`, `vitest`

### `product/frontend/src/features/checks/PermissionCheckPage.tsx`
- `PermissionCheckPage`
主要 import / dot-source：`../../api/checks`, `../../api/http`, `../../api/permissionIntents`, `../../api/projects`, `../../api/runs`, `../../app/presentation`, `../../components/AssistantPanel`, `../../components/PageTaskHeader`, `../../components/TaskActionBar`, `./CheckProgress`, `antd`, `react`

### `product/frontend/src/features/checks/ReportPanel.test.tsx`
主要 import / dot-source：`./ReportPanel`, `@testing-library/react`, `vitest`

### `product/frontend/src/features/checks/ReportPanel.tsx`
- `ReportPanel`
主要 import / dot-source：`../../api/http`, `../../api/results`, `../../api/runs`, `../../app/presentation`, `@ant-design/icons`, `antd`, `react`

### `product/frontend/src/features/identities/TestIdentityPage.test.tsx`
主要 import / dot-source：`../../api/projects`, `../../api/testIdentities`, `./TestIdentityPage`, `@testing-library/react`, `vitest`

### `product/frontend/src/features/identities/TestIdentityPage.tsx`
- `TestIdentityPage`
主要 import / dot-source：`../../api/http`, `../../api/projects`, `../../api/testIdentities`, `../../components/AssistantPanel`, `../../components/PageTaskHeader`, `../../components/TaskActionBar`, `antd`, `react`

### `product/frontend/src/features/permissions/explorer/PermissionExplorer.tsx`
- `PermissionExplorer`
主要 import / dot-source：`../../../api/contracts`, `./PermissionGraph`, `./PermissionMatrix`, `./projection`, `antd`, `react`

### `product/frontend/src/features/permissions/explorer/PermissionGraph.tsx`
- `PermissionGraph`
主要 import / dot-source：`../../../api/contracts`, `../../../app/presentation`, `./projection`, `./types`, `antd`, `react`

### `product/frontend/src/features/permissions/explorer/PermissionMatrix.tsx`
- `PermissionMatrix`
主要 import / dot-source：`../../../app/presentation`, `./types`, `antd`, `react`

### `product/frontend/src/features/permissions/explorer/projection.test.ts`
主要 import / dot-source：`../../../api/contracts`, `./projection`, `vitest`

### `product/frontend/src/features/permissions/explorer/projection.ts`
- `buildFocusedRelationshipGraph`
- `buildGlobalRelationshipGraph`
- `buildPermissionMatrix`
- `expandPermissionRules`
主要 import / dot-source：`../../../api/contracts`, `../../../app/presentation`, `./types`

### `product/frontend/src/features/permissions/explorer/types.ts`
- `ExpandedPermissionRule`
- `PermissionCellState`
- `PermissionMatrixCell`
- `PermissionMatrixModel`
- `PermissionMatrixRow`
- `RelationshipEdge`
- `RelationshipGraphModel`
- `RelationshipNode`
主要 import / dot-source：`../../../api/contracts`

### `product/frontend/src/features/recording/ActionSafetySetupCard.tsx`
- `ActionSafetySetupCard`
主要 import / dot-source：`../../api/recordings`, `antd`, `react`

### `product/frontend/src/features/recording/FlowDraftReview.tsx`
- `FlowDraftReview`
主要 import / dot-source：`../../api/recordings`, `antd`

### `product/frontend/src/features/recording/RecordingCaptureCard.tsx`
- `RecordingCaptureCard`
- `captureLabel`
主要 import / dot-source：`../../api/recordings`, `../../api/runs`, `../../app/browserState`, `../../app/presentation`, `antd`, `react`

### `product/frontend/src/features/recording/RecordingPage.test.tsx`
主要 import / dot-source：`./RecordingPage`, `@testing-library/react`, `vitest`

### `product/frontend/src/features/recording/RecordingPage.tsx`
- `RecordingPage`
主要 import / dot-source：`../../api/http`, `../../api/projects`, `../../api/recordings`, `../../api/runs`, `../../app/browserState`, `../../components/AssistantPanel`, `../../components/PageTaskHeader`, `../../components/TaskActionBar`, `./ActionSafetySetupCard`, `./FlowDraftReview`, `./RecordingCaptureCard`, `./RecordingSetupCard`, `antd`, `react`

### `product/frontend/src/features/recording/RecordingSetupCard.tsx`
- `RecordingSetupCard`
主要 import / dot-source：`../../api/recordings`, `antd`

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

### `product/frontend/src/features/settings/ModelServicePage.tsx`
- `ModelServicePage`
主要 import / dot-source：`../../api/llm`, `antd`

### `product/frontend/src/features/system/RuntimePage.test.tsx`
主要 import / dot-source：`../../api/system`, `./RuntimePage`, `@testing-library/react`, `vitest`

### `product/frontend/src/features/system/RuntimePage.tsx`
- `RuntimePage`
主要 import / dot-source：`../../api/llm`, `../../api/system`, `antd`, `react`

### `product/frontend/src/features/tools/ToolsPage.test.tsx`
主要 import / dot-source：`./ToolsPage`, `@testing-library/react`, `vitest`

### `product/frontend/src/features/tools/ToolsPage.tsx`
- `ToolsPage`
主要 import / dot-source：`../../api/http`, `../../api/mcp`, `../../api/projects`, `../../components/PageTaskHeader`, `../settings/MCPAccessCard`, `antd`

### `product/frontend/src/features/workspace/WorkbenchPage.test.tsx`
主要 import / dot-source：`./WorkbenchPage`, `@testing-library/react`, `vitest`

### `product/frontend/src/features/workspace/WorkbenchPage.tsx`
- `WorkbenchPage`
主要 import / dot-source：`../../api/experience`, `../../api/mcp`, `../../api/projects`, `../../api/runs`, `../../api/sourceChanges`, `../../api/system`, `../../app/presentation`, `../../components/AssistantPanel`, `../../components/PageTaskHeader`, `antd`, `react`

### `product/frontend/src/main.tsx`
主要 import / dot-source：`./app/ControlShell`, `./app/theme`, `antd`, `antd/locale/zh_CN`, `react`, `react-dom/client`

### `product/frontend/src/test-setup.ts`
主要 import / dot-source：`@testing-library/react`, `vitest`

<!-- GENERATED:END -->
