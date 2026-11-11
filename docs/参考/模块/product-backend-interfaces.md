# product/backend/interfaces 模块

<!-- generated:modules -->

[返回总索引](../模块索引.md)

按目录定位后读取对应小节；每个文件有独立标题，源码链接用于核对声明与直接消费者。行数和公开声明由静态提取，不表示运行验收。

按目录定位：[根目录](#根目录)（1 个文件）、[cli](#cli)（9 个文件）、[cli/commands](#clicommands)（3 个文件）、[http](#http)（7 个文件）、[http/mcp](#httpmcp)（7 个文件）、[http/routers](#httprouters)（2 个文件）、[http/routers/applications](#httproutersapplications)（5 个文件）、[http/routers/boundaries](#httproutersboundaries)（2 个文件）、[http/routers/changes](#httprouterschanges)（3 个文件）、[http/routers/checks](#httprouterschecks)（4 个文件）、[http/routers/preparation](#httprouterspreparation)（9 个文件）、[http/routers/system](#httprouterssystem)（4 个文件）、[worker](#worker)（3 个文件）。

## 根目录

### __init__.py

[源码](../../../product/backend/interfaces/__init__.py)（1 行）。公开声明：包、内部机制或样式。

## cli

### cli/__init__.py

[源码](../../../product/backend/interfaces/cli/__init__.py)（5 行）。公开声明：包、内部机制或样式。

### cli/__main__.py

[源码](../../../product/backend/interfaces/cli/__main__.py)（7 行）。公开声明：包、内部机制或样式。

### cli/app.py

[源码](../../../product/backend/interfaces/cli/app.py)（117 行）。公开声明：`root`、`main`。

### cli/bootstrap.py

[源码](../../../product/backend/interfaces/cli/bootstrap.py)（72 行）。公开声明：`CliOptions`、`runtime_settings`、`application_scope`、`default_frontend_dir`。

### cli/check_client.py

[源码](../../../product/backend/interfaces/cli/check_client.py)（127 行）。公开声明：`CheckClient`、`execution_exit`。

### cli/gui_browser.py

[源码](../../../product/backend/interfaces/cli/gui_browser.py)（142 行）。公开声明：`GuiBrowserSession`、`open_gui_browser`。

### cli/gui_console.py

[源码](../../../product/backend/interfaces/cli/gui_console.py)（131 行）。公开声明：`console_key_reader`、`console_input_mode`、`launcher_key_reader`、`run_gui_console`。

### cli/localization.py

[源码](../../../product/backend/interfaces/cli/localization.py)（82 行）。公开声明：`ChineseHelpFormatter`、`configure_cli_localization`。

### cli/presentation.py

[源码](../../../product/backend/interfaces/cli/presentation.py)（525 行）。公开声明：`configure_presentation`、`presentation_mode`、`emit_human`、`emit_doctor`、`emit_command`、`emit_json`、`fail`、`human_wait`。

## cli/commands

### cli/commands/__init__.py

[源码](../../../product/backend/interfaces/cli/commands/__init__.py)（1 行）。公开声明：包、内部机制或样式。

### cli/commands/checks.py

[源码](../../../product/backend/interfaces/cli/commands/checks.py)（141 行）。公开声明：`preview`、`run`、`request`、`execute`、`status`、`wait`、`cancel`。

### cli/commands/system.py

[源码](../../../product/backend/interfaces/cli/commands/system.py)（347 行）。公开声明：`GuiBrowser`、`ServeReadinessStatus`、`serve_command`、`doctor_command`、`maintenance_clean_assistant_command`、`maintenance_clean_logs_command`、`maintenance_clean_temporary_command`、`maintenance_clean_all_command`等。

## http

### http/__init__.py

[源码](../../../product/backend/interfaces/http/__init__.py)（5 行）。公开声明：包、内部机制或样式。

### http/app.py

[源码](../../../product/backend/interfaces/http/app.py)（250 行）。公开声明：`create_app`。

### http/body.py

[源码](../../../product/backend/interfaces/http/body.py)（67 行）。公开声明：`BodyBudgetExceeded`、`body_budget_error`、`read_bounded_body`、`ApiBodyBudget`。

### http/envelope.py

[源码](../../../product/backend/interfaces/http/envelope.py)（34 行）。公开声明：`ApiModel`、`ApiResponse`、`data_response`。

### http/errors.py

[源码](../../../product/backend/interfaces/http/errors.py)（67 行）。公开声明：`jiejian_error_handler`、`validation_error_handler`。

### http/frontend.py

[源码](../../../product/backend/interfaces/http/frontend.py)（32 行）。公开声明：`ProductStaticFiles`。

### http/local_control.py

[源码](../../../product/backend/interfaces/http/local_control.py)（114 行）。公开声明：`LocalControlDecision`、`LocalControlGuard`。

## http/mcp

### http/mcp/__init__.py

[源码](../../../product/backend/interfaces/http/mcp/__init__.py)（4 行）。公开声明：包、内部机制或样式。

### http/mcp/collaboration.py

[源码](../../../product/backend/interfaces/http/mcp/collaboration.py)（81 行）。公开声明：`register_collaboration_tools`。

### http/mcp/errors.py

[源码](../../../product/backend/interfaces/http/mcp/errors.py)（162 行）。公开声明：`require_mcp_level`。

### http/mcp/preparation.py

[源码](../../../product/backend/interfaces/http/mcp/preparation.py)（117 行）。公开声明：`public_preparation`、`register_preparation_tools`。

### http/mcp/server.py

[源码](../../../product/backend/interfaces/http/mcp/server.py)（365 行）。公开声明：`MCPControl`、`build_mcp_control`。

### http/mcp/transport.py

[源码](../../../product/backend/interfaces/http/mcp/transport.py)（46 行）。公开声明：`MCPBearerGuard`、`MCPPathAdapter`。

### http/mcp/views.py

[源码](../../../product/backend/interfaces/http/mcp/views.py)（72 行）。公开声明：包、内部机制或样式。

## http/routers

### http/routers/__init__.py

[源码](../../../product/backend/interfaces/http/routers/__init__.py)（1 行）。公开声明：包、内部机制或样式。

### http/routers/workspace.py

[源码](../../../product/backend/interfaces/http/routers/workspace.py)（30 行）。公开声明：`build_workspace_router`。

## http/routers/applications

### http/routers/applications/__init__.py

[源码](../../../product/backend/interfaces/http/routers/applications/__init__.py)（1 行）。公开声明：包、内部机制或样式。

### http/routers/applications/experience.py

[源码](../../../product/backend/interfaces/http/routers/applications/experience.py)（135 行）。公开声明：`build_experience_router`、`OfficialSampleStartRequest`、`OfficialSampleStopRequest`、`OfficialSampleVersionRequest`、`OfficialBoundaryChoice`、`OfficialObservationRequest`。

### http/routers/applications/onboarding.py

[源码](../../../product/backend/interfaces/http/routers/applications/onboarding.py)（34 行）。公开声明：`OnboardingInspectRequest`、`build_onboarding_router`。

### http/routers/applications/projects.py

[源码](../../../product/backend/interfaces/http/routers/applications/projects.py)（341 行）。公开声明：`DatabaseCredentialRequest`、`build_projects_router`、`RuntimeSqliteTableInput`、`RuntimeSqliteInput`、`RuntimePreviewRequest`、`RuntimeStartRequest`、`RuntimeStopRequest`、`ApplicationConnectRequest`等。

### http/routers/applications/workbench.py

[源码](../../../product/backend/interfaces/http/routers/applications/workbench.py)（118 行）。公开声明：`CreateApplication`、`SaveEnvironment`、`AttachSource`、`ActivateEnvironment`、`ImportPreview`、`ImportAccept`、`SourceAnnotation`、`SourceProposal`等。

## http/routers/boundaries

### http/routers/boundaries/__init__.py

[源码](../../../product/backend/interfaces/http/routers/boundaries/__init__.py)（1 行）。公开声明：包、内部机制或样式。

### http/routers/boundaries/business_boundaries.py

[源码](../../../product/backend/interfaces/http/routers/boundaries/business_boundaries.py)（319 行）。公开声明：`BoundaryProposalCreateRequest`、`BoundaryDecisionRequest`、`RuleCandidateSaveRequest`、`RuleCandidateProposalRequest`、`BoundaryReviewRequest`、`ScopeBatchChoiceRequest`、`ScopeBatchRequest`、`CoverageLinkRequest`等。

## http/routers/changes

### http/routers/changes/__init__.py

[源码](../../../product/backend/interfaces/http/routers/changes/__init__.py)（1 行）。公开声明：包、内部机制或样式。

### http/routers/changes/development.py

[源码](../../../product/backend/interfaces/http/routers/changes/development.py)（105 行）。公开声明：`TaskCreateRequest`、`TaskReviseRequest`、`TaskFinishRequest`、`RuntimeLoadRequest`、`build_development_router`。

### http/routers/changes/source_changes.py

[源码](../../../product/backend/interfaces/http/routers/changes/source_changes.py)（110 行）。公开声明：`SourceChangeCreateRequest`、`SourceChangeRegistrationRequest`、`build_source_changes_router`。

## http/routers/checks

### http/routers/checks/__init__.py

[源码](../../../product/backend/interfaces/http/routers/checks/__init__.py)（1 行）。公开声明：包、内部机制或样式。

### http/routers/checks/checks.py

[源码](../../../product/backend/interfaces/http/routers/checks/checks.py)（99 行）。公开声明：`CheckScopeRequest`、`build_checks_router`。

### http/routers/checks/results.py

[源码](../../../product/backend/interfaces/http/routers/checks/results.py)（41 行）。公开声明：`build_results_router`。

### http/routers/checks/runs.py

[源码](../../../product/backend/interfaces/http/routers/checks/runs.py)（104 行）。公开声明：`RunSubmissionProjection`、`require_local_history_session`、`RunCreateRequest`、`build_runs_router`。

## http/routers/preparation

### http/routers/preparation/__init__.py

[源码](../../../product/backend/interfaces/http/routers/preparation/__init__.py)（1 行）。公开声明：包、内部机制或样式。

### http/routers/preparation/business_scenarios.py

[源码](../../../product/backend/interfaces/http/routers/preparation/business_scenarios.py)（36 行）。公开声明：`build_business_scenarios_router`。

### http/routers/preparation/flow_trials.py

[源码](../../../product/backend/interfaces/http/routers/preparation/flow_trials.py)（34 行）。公开声明：`build_flow_trials_router`。

### http/routers/preparation/preparation.py

[源码](../../../product/backend/interfaces/http/routers/preparation/preparation.py)（134 行）。公开声明：`AllowControlSelectionRequest`、`build_preparation_router`。

### http/routers/preparation/projections.py

[源码](../../../product/backend/interfaces/http/routers/preparation/projections.py)（66 行）。公开声明：`FlowEffectProjection`、`FlowActionProjection`、`FlowRecordingProjection`、`FlowRevisionProjection`、`OperationContextProjection`、`ProofAdoptionProjection`。

### http/routers/preparation/proof_sources.py

[源码](../../../product/backend/interfaces/http/routers/preparation/proof_sources.py)（234 行）。公开声明：`require_local_proof_session`、`SavePreparationSuggestionRequest`、`json_command`、`SqliteCandidateRequest`、`DatabaseCandidateRequest`、`FileCandidateRequest`、`build_proof_sources_router`。

### http/routers/preparation/recordings.py

[源码](../../../product/backend/interfaces/http/routers/preparation/recordings.py)（272 行）。公开声明：`build_recordings_router`、`RecordingCreateRequest`、`ReviewRequest`、`FinalizeRequest`。

### http/routers/preparation/supplemental_materials.py

[源码](../../../product/backend/interfaces/http/routers/preparation/supplemental_materials.py)（57 行）。公开声明：`MaterialPreviewRequest`、`MaterialCreateRequest`、`MaterialWithdrawRequest`、`MaterialRevisionRequest`、`build_supplemental_material_router`。

### http/routers/preparation/test_identities.py

[源码](../../../product/backend/interfaces/http/routers/preparation/test_identities.py)（160 行）。公开声明：`TestIdentityCreateRequest`、`TestIdentityResetRequest`、`TestIdentityLoginRequest`、`AuthenticationRequest`、`build_test_identities_router`。

## http/routers/system

### http/routers/system/__init__.py

[源码](../../../product/backend/interfaces/http/routers/system/__init__.py)（1 行）。公开声明：包、内部机制或样式。

### http/routers/system/agent_workflow.py

[源码](../../../product/backend/interfaces/http/routers/system/agent_workflow.py)（93 行）。公开声明：`TaskDecision`、`TaskAnswer`、`TaskControl`、`build_agent_workflow_router`。

### http/routers/system/mcp_access.py

[源码](../../../product/backend/interfaces/http/routers/system/mcp_access.py)（93 行）。公开声明：`ClientConnectRequest`、`MCPProjectGrantRequest`、`build_mcp_access_router`。

### http/routers/system/system.py

[源码](../../../product/backend/interfaces/http/routers/system/system.py)（213 行）。公开声明：`build_system_router`、`HealthResponse`、`ReadyResponse`、`MaintenanceOperationRequest`、`UpdatePreviewRequest`。

## worker

### worker/__init__.py

[源码](../../../product/backend/interfaces/worker/__init__.py)（1 行）。公开声明：包、内部机制或样式。

### worker/job.py

[源码](../../../product/backend/interfaces/worker/job.py)（198 行）。公开声明：`main`。

### worker/runtime.py

[源码](../../../product/backend/interfaces/worker/runtime.py)（110 行）。公开声明：`run`、`main`。
