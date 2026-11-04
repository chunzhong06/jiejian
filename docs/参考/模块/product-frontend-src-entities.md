# product/frontend/src/entities 模块

<!-- generated:modules -->

[返回总索引](../模块索引.md)

| 文件 | 行数 | 公开声明 |
| --- | ---: | --- |
| [product/frontend/src/entities/application/api/experience.ts](../../../product/frontend/src/entities/application/api/experience.ts) | 99 | CompetitionValidationSummaryDto、CompetitionValidationSummaryViewDto、OfficialDevelopmentJourneyDto、OfficialExperienceDto、OfficialScenarioVersion、experienceApi |
| [product/frontend/src/entities/application/api/onboarding.ts](../../../product/frontend/src/entities/application/api/onboarding.ts) | 33 | DiscoveryCandidate、DiscoveryHint、DiscoveryResult、onboardingApi |
| [product/frontend/src/entities/application/api/projects.ts](../../../product/frontend/src/entities/application/api/projects.ts) | 162 | ActionCandidateDto、ApplicationActivity、ApplicationConnectionDto、ApplicationReadiness、ApplicationUnderstandingDto、CandidateEvidenceDto、CandidateSelection、ConnectionChoice等 |
| [product/frontend/src/entities/application/api/workbench.ts](../../../product/frontend/src/entities/application/api/workbench.ts) | 25 | ApiSource、ApplicationEnvironment、EnvironmentContext、ImportPreview、SourceAnnotation、SourceRequest、SourcesContext、TargetScope等 |
| [product/frontend/src/entities/check/api/currentChecks.ts](../../../product/frontend/src/entities/check/api/currentChecks.ts) | 163 | ActionResultStory、ActivityEvent、CheckBreakpoint、CheckEvidence、CheckHistoryCursor、CheckHistoryItem、CheckHistoryPage、CheckHistoryQuery等 |
| [product/frontend/src/entities/check/api/repairs.ts](../../../product/frontend/src/entities/check/api/repairs.ts) | 26 | ProjectRepair、RepairComparisonRow、RepairContract、RepairHistoryEvent、RepairReference、RepairStatus、RepairVerification、repairLabels等 |
| [product/frontend/src/entities/check/model/checks.ts](../../../product/frontend/src/entities/check/model/checks.ts) | 67 | Tone、actual、gaps、judgement、judgementLabels、owner、repairGap、requirement等 |
| [product/frontend/src/entities/check/ui/AgentHandoff.tsx](../../../product/frontend/src/entities/check/ui/AgentHandoff.tsx) | 30 | AgentHandoff |
| [product/frontend/src/entities/check/ui/ExternalRecheck.tsx](../../../product/frontend/src/entities/check/ui/ExternalRecheck.tsx) | 47 | ExternalRecheck |
| [product/frontend/src/entities/permission/api/businessBoundaries.ts](../../../product/frontend/src/entities/permission/api/businessBoundaries.ts) | 246 | BoundaryCandidateDto、BoundaryConfidence、BoundaryDecisionDto、BoundaryDraftViewDto、BoundaryEditorDto、BoundaryMaintenanceActionDto、BoundaryMaintenanceActorDto、BoundaryMaintenanceCandidateOptionDto等 |
| [product/frontend/src/entities/permission/api/ruleCandidates.ts](../../../product/frontend/src/entities/permission/api/ruleCandidates.ts) | 70 | BoundaryChoice、BoundaryReview、BoundaryReviewGap、CandidateTask、CoverageChoice、MeaningChoice、RequirementSource、ReviewDependencies等 |
| [product/frontend/src/entities/permission/api/ruleWorkspace.ts](../../../product/frontend/src/entities/permission/api/ruleWorkspace.ts) | 17 | RuleHistory、RuleItem、RuleState、RuleWorkspace、ruleWorkspaceApi |
| [product/frontend/src/entities/permission/ui/RuleConditions.tsx](../../../product/frontend/src/entities/permission/ui/RuleConditions.tsx) | 35 | RuleConditionsEditor、conditionLabels |
| [product/frontend/src/entities/preparation/api/batches.ts](../../../product/frontend/src/entities/preparation/api/batches.ts) | 13 | PreparationBatch、PreparationBatchPlan、preparationBatchesApi |
| [product/frontend/src/entities/preparation/api/flowTrials.ts](../../../product/frontend/src/entities/preparation/api/flowTrials.ts) | 16 | FlowTrial、TrialPlan、TrialPreview、TrialReport、TrialSelection、flowTrialsApi |
| [product/frontend/src/entities/preparation/api/operationFlows.ts](../../../product/frontend/src/entities/preparation/api/operationFlows.ts) | 17 | ApiCandidate、ApiSourceReference、EntityEvidence、FlowStep、OperationContext、OperationFlow、operationFlowsApi |
| [product/frontend/src/entities/preparation/api/preparation.ts](../../../product/frontend/src/entities/preparation/api/preparation.ts) | 87 | ActionPreparation、AllowControlRequirement、EffectMaterialSummary、EvidenceMaterialDetail、IdentitySlot、MaterialChange、MaterialDetails、MaterialPreview等 |
| [product/frontend/src/entities/preparation/api/preparationGuidance.ts](../../../product/frontend/src/entities/preparation/api/preparationGuidance.ts) | 22 | PreparationGuidance、PreparationMaterialAdvice、PreparationNextAction |
| [product/frontend/src/entities/preparation/api/preparationSuggestions.ts](../../../product/frontend/src/entities/preparation/api/preparationSuggestions.ts) | 17 | MaterialSuggestion、MaterialSuggestionKind、PreparationSuggestionContext、PreparationSuggestionView、SuggestedMaterial、SuggestionItemView、preparationSuggestionsApi |
| [product/frontend/src/entities/preparation/api/proofSources.ts](../../../product/frontend/src/entities/preparation/api/proofSources.ts) | 58 | AdoptionPreview、ArtifactManifest、CapturePlan、CaptureSelection、CaptureStatus、ProofConfig、ProofContext、ProofOperationKind等 |
| [product/frontend/src/entities/preparation/api/recordings.ts](../../../product/frontend/src/entities/preparation/api/recordings.ts) | 146 | FlowDraftDto、FlowDraftStepDto、FlowDraftVariableDto、FlowDraftVariableSourceDto、RecordingActionDto、RecordingCreateInput、RecordingDto、RecordingJobDto等 |
| [product/frontend/src/entities/preparation/api/testIdentities.ts](../../../product/frontend/src/entities/preparation/api/testIdentities.ts) | 86 | AuthenticationOptions、AuthenticationProfile、IdentityPreparationDto、IdentityPreparationStatus、IdentityVerification、TestIdentityAuthMethod、TestIdentityDto、TestIdentityStatus等 |
| [product/frontend/src/entities/preparation/ui/EntityEvidenceEditor.tsx](../../../product/frontend/src/entities/preparation/ui/EntityEvidenceEditor.tsx) | 10 | EntityEvidenceEditor、EvidenceEffect |
| [product/frontend/src/entities/preparation/ui/FlowCandidateReview.tsx](../../../product/frontend/src/entities/preparation/ui/FlowCandidateReview.tsx) | 34 | FlowCandidateReview、FlowEditorDraft、flowDraftKey |
| [product/frontend/src/entities/preparation/ui/flowInputs.ts](../../../product/frontend/src/entities/preparation/ui/flowInputs.ts) | 110 | EditableStep、FlowParameter、InputLocation、InputSource、compileSteps、decodeSteps、newParameter、sensitiveParameter |
| [product/frontend/src/entities/preparation/ui/FlowRequestInputs.tsx](../../../product/frontend/src/entities/preparation/ui/FlowRequestInputs.tsx) | 51 | FlowRequestInputs |
| [product/frontend/src/entities/preparation/ui/FlowTrialPanel.tsx](../../../product/frontend/src/entities/preparation/ui/FlowTrialPanel.tsx) | 93 | FlowTrialPanel |
| [product/frontend/src/entities/preparation/ui/operation-flow.css](../../../product/frontend/src/entities/preparation/ui/operation-flow.css) | 159 | 包、内部机制或样式 |
| [product/frontend/src/entities/preparation/ui/OperationFlowEditor.tsx](../../../product/frontend/src/entities/preparation/ui/OperationFlowEditor.tsx) | 153 | OperationFlowEditor |
| [product/frontend/src/entities/runtime/api/collaboration.ts](../../../product/frontend/src/entities/runtime/api/collaboration.ts) | 34 | CollaborationCapability、CollaborationCheck、CollaborationEditor、CollaborationExecutor、CollaborationOperation、CollaborationPurpose、CollaborationTask、FlowHandoff等 |
| [product/frontend/src/entities/runtime/api/mcp.ts](../../../product/frontend/src/entities/runtime/api/mcp.ts) | 61 | AgentClient、AgentConnection、MCPAccessCredentialView、MCPAccessLevel、MCPAccessView、MCPConnectionState、MCPProjectGrant、agentClients等 |
| [product/frontend/src/entities/runtime/api/system.ts](../../../product/frontend/src/entities/runtime/api/system.ts) | 75 | ExitReceipt、MaintenanceEntry、MaintenanceOperation、MaintenanceOperationResult、MaintenanceStatus、RuntimeDiagnostics、SystemStatus、UpdateInfo等 |
| [product/frontend/src/entities/runtime/model/handoff.ts](../../../product/frontend/src/entities/runtime/model/handoff.ts) | 36 | HandoffContext、editorDraft、rememberEditorDraft、requestCollaboration、routeReferences、useCurrentHandoff、useHandoffContext |
| [product/frontend/src/entities/runtime/ui/CollaborationComposer.tsx](../../../product/frontend/src/entities/runtime/ui/CollaborationComposer.tsx) | 26 | CollaborationComposer |
| [product/frontend/src/entities/runtime/ui/CollaborationEntry.tsx](../../../product/frontend/src/entities/runtime/ui/CollaborationEntry.tsx) | 54 | CollaborationEntry |
| [product/frontend/src/entities/source-change/api/development.ts](../../../product/frontend/src/entities/source-change/api/development.ts) | 33 | DeliveryDetails、DeliveryPage、DeliverySubmission、DevelopmentContext、DevelopmentDelivery、DevelopmentReceipt、DevelopmentTask、DevelopmentView等 |
| [product/frontend/src/entities/source-change/api/sourceChanges.ts](../../../product/frontend/src/entities/source-change/api/sourceChanges.ts) | 23 | RegistrationPreview、RuleChangeTarget、SourceChangeViewDto、sourceChangesApi |
| [product/frontend/src/entities/source-change/ui/ChangePreview.tsx](../../../product/frontend/src/entities/source-change/ui/ChangePreview.tsx) | 7 | ChangePreview |
| [product/frontend/src/entities/source-change/ui/ChangeRegistration.tsx](../../../product/frontend/src/entities/source-change/ui/ChangeRegistration.tsx) | 86 | ChangeRegistration、changeTargetOptions |
| [product/frontend/src/entities/source-change/ui/RuntimeActivation.tsx](../../../product/frontend/src/entities/source-change/ui/RuntimeActivation.tsx) | 41 | RuntimeActivation |
| [product/frontend/src/entities/source-change/ui/styles.css](../../../product/frontend/src/entities/source-change/ui/styles.css) | 33 | 包、内部机制或样式 |
| [product/frontend/src/entities/workspace/api/workspace.ts](../../../product/frontend/src/entities/workspace/api/workspace.ts) | 132 | ActionWorkspaceDto、ActorWorkspaceDto、PrimaryTaskDto、PrimaryTaskKind、WorkspaceAreaDto、WorkspaceConnectionDto、WorkspaceProjectDto、WorkspaceViewDto等 |
