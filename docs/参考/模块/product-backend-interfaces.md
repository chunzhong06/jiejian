# product/backend/interfaces 模块

<!-- generated:modules -->

[返回总索引](../模块索引.md)

| 文件 | 行数 | 公开声明 |
| --- | ---: | --- |
| [product/backend/interfaces/__init__.py](../../../product/backend/interfaces/__init__.py) | 1 | 包、内部机制或样式 |
| [product/backend/interfaces/cli/__init__.py](../../../product/backend/interfaces/cli/__init__.py) | 5 | 包、内部机制或样式 |
| [product/backend/interfaces/cli/__main__.py](../../../product/backend/interfaces/cli/__main__.py) | 7 | 包、内部机制或样式 |
| [product/backend/interfaces/cli/app.py](../../../product/backend/interfaces/cli/app.py) | 115 | root、main |
| [product/backend/interfaces/cli/bootstrap.py](../../../product/backend/interfaces/cli/bootstrap.py) | 72 | CliOptions、runtime_settings、application_scope、default_frontend_dir |
| [product/backend/interfaces/cli/commands/__init__.py](../../../product/backend/interfaces/cli/commands/__init__.py) | 1 | 包、内部机制或样式 |
| [product/backend/interfaces/cli/commands/system.py](../../../product/backend/interfaces/cli/commands/system.py) | 325 | GuiBrowser、ServeReadinessStatus、serve_command、doctor_command、maintenance_clean_assistant_command、maintenance_clean_logs_command、maintenance_clean_temporary_command、maintenance_clean_all_command等 |
| [product/backend/interfaces/cli/gui_browser.py](../../../product/backend/interfaces/cli/gui_browser.py) | 142 | GuiBrowserSession、open_gui_browser |
| [product/backend/interfaces/cli/gui_console.py](../../../product/backend/interfaces/cli/gui_console.py) | 131 | console_key_reader、console_input_mode、launcher_key_reader、run_gui_console |
| [product/backend/interfaces/cli/localization.py](../../../product/backend/interfaces/cli/localization.py) | 82 | ChineseHelpFormatter、configure_cli_localization |
| [product/backend/interfaces/cli/presentation.py](../../../product/backend/interfaces/cli/presentation.py) | 525 | configure_presentation、presentation_mode、emit_human、emit_doctor、emit_command、emit_json、fail、human_wait |
| [product/backend/interfaces/http/__init__.py](../../../product/backend/interfaces/http/__init__.py) | 5 | 包、内部机制或样式 |
| [product/backend/interfaces/http/app.py](../../../product/backend/interfaces/http/app.py) | 239 | create_app |
| [product/backend/interfaces/http/envelope.py](../../../product/backend/interfaces/http/envelope.py) | 25 | ApiModel、ApiResponse、data_response |
| [product/backend/interfaces/http/errors.py](../../../product/backend/interfaces/http/errors.py) | 123 | jiejian_error_handler、validation_error_handler |
| [product/backend/interfaces/http/frontend.py](../../../product/backend/interfaces/http/frontend.py) | 32 | ProductStaticFiles |
| [product/backend/interfaces/http/local_control.py](../../../product/backend/interfaces/http/local_control.py) | 114 | LocalControlDecision、LocalControlGuard |
| [product/backend/interfaces/http/mcp/__init__.py](../../../product/backend/interfaces/http/mcp/__init__.py) | 4 | 包、内部机制或样式 |
| [product/backend/interfaces/http/mcp/collaboration.py](../../../product/backend/interfaces/http/mcp/collaboration.py) | 81 | register_collaboration_tools |
| [product/backend/interfaces/http/mcp/errors.py](../../../product/backend/interfaces/http/mcp/errors.py) | 161 | require_mcp_level |
| [product/backend/interfaces/http/mcp/preparation.py](../../../product/backend/interfaces/http/mcp/preparation.py) | 117 | public_preparation、register_preparation_tools |
| [product/backend/interfaces/http/mcp/server.py](../../../product/backend/interfaces/http/mcp/server.py) | 362 | MCPControl、build_mcp_control |
| [product/backend/interfaces/http/mcp/transport.py](../../../product/backend/interfaces/http/mcp/transport.py) | 46 | MCPBearerGuard、MCPPathAdapter |
| [product/backend/interfaces/http/mcp/views.py](../../../product/backend/interfaces/http/mcp/views.py) | 72 | 包、内部机制或样式 |
| [product/backend/interfaces/http/routers/__init__.py](../../../product/backend/interfaces/http/routers/__init__.py) | 1 | 包、内部机制或样式 |
| [product/backend/interfaces/http/routers/applications/__init__.py](../../../product/backend/interfaces/http/routers/applications/__init__.py) | 1 | 包、内部机制或样式 |
| [product/backend/interfaces/http/routers/applications/experience.py](../../../product/backend/interfaces/http/routers/applications/experience.py) | 130 | build_experience_router、OfficialSampleStartRequest、OfficialSampleStopRequest、OfficialSampleVersionRequest、OfficialBoundaryChoice、OfficialObservationRequest |
| [product/backend/interfaces/http/routers/applications/onboarding.py](../../../product/backend/interfaces/http/routers/applications/onboarding.py) | 34 | OnboardingInspectRequest、build_onboarding_router |
| [product/backend/interfaces/http/routers/applications/projects.py](../../../product/backend/interfaces/http/routers/applications/projects.py) | 319 | build_projects_router、RuntimeSqliteTableInput、RuntimeSqliteInput、RuntimePreviewRequest、RuntimeStartRequest、RuntimeStopRequest、ApplicationConnectRequest、ApplicationConnectionPreviewRequest等 |
| [product/backend/interfaces/http/routers/applications/workbench.py](../../../product/backend/interfaces/http/routers/applications/workbench.py) | 109 | CreateApplication、SaveEnvironment、AttachSource、ActivateEnvironment、ImportPreview、ImportAccept、SourceAnnotation、SourceProposal等 |
| [product/backend/interfaces/http/routers/boundaries/__init__.py](../../../product/backend/interfaces/http/routers/boundaries/__init__.py) | 1 | 包、内部机制或样式 |
| [product/backend/interfaces/http/routers/boundaries/business_boundaries.py](../../../product/backend/interfaces/http/routers/boundaries/business_boundaries.py) | 319 | BoundaryProposalCreateRequest、BoundaryDecisionRequest、RuleCandidateSaveRequest、RuleCandidateProposalRequest、BoundaryReviewRequest、ScopeBatchChoiceRequest、ScopeBatchRequest、CoverageLinkRequest等 |
| [product/backend/interfaces/http/routers/changes/__init__.py](../../../product/backend/interfaces/http/routers/changes/__init__.py) | 1 | 包、内部机制或样式 |
| [product/backend/interfaces/http/routers/changes/development.py](../../../product/backend/interfaces/http/routers/changes/development.py) | 104 | TaskCreateRequest、TaskReviseRequest、TaskFinishRequest、RuntimeLoadRequest、build_development_router |
| [product/backend/interfaces/http/routers/changes/source_changes.py](../../../product/backend/interfaces/http/routers/changes/source_changes.py) | 105 | SourceChangeCreateRequest、SourceChangeRegistrationRequest、build_source_changes_router |
| [product/backend/interfaces/http/routers/checks/__init__.py](../../../product/backend/interfaces/http/routers/checks/__init__.py) | 1 | 包、内部机制或样式 |
| [product/backend/interfaces/http/routers/checks/checks.py](../../../product/backend/interfaces/http/routers/checks/checks.py) | 44 | CheckScopeRequest、build_checks_router |
| [product/backend/interfaces/http/routers/checks/results.py](../../../product/backend/interfaces/http/routers/checks/results.py) | 40 | build_results_router |
| [product/backend/interfaces/http/routers/checks/runs.py](../../../product/backend/interfaces/http/routers/checks/runs.py) | 89 | require_local_history_session、RunCreateRequest、build_runs_router |
| [product/backend/interfaces/http/routers/preparation/__init__.py](../../../product/backend/interfaces/http/routers/preparation/__init__.py) | 1 | 包、内部机制或样式 |
| [product/backend/interfaces/http/routers/preparation/flow_trials.py](../../../product/backend/interfaces/http/routers/preparation/flow_trials.py) | 34 | build_flow_trials_router |
| [product/backend/interfaces/http/routers/preparation/preparation.py](../../../product/backend/interfaces/http/routers/preparation/preparation.py) | 127 | AllowControlSelectionRequest、build_preparation_router |
| [product/backend/interfaces/http/routers/preparation/proof_sources.py](../../../product/backend/interfaces/http/routers/preparation/proof_sources.py) | 191 | require_local_proof_session、SavePreparationSuggestionRequest、SqliteCandidateRequest、json_command、build_proof_sources_router |
| [product/backend/interfaces/http/routers/preparation/recordings.py](../../../product/backend/interfaces/http/routers/preparation/recordings.py) | 277 | build_recordings_router、RecordingCreateRequest、ReviewRequest、FinalizeRequest |
| [product/backend/interfaces/http/routers/preparation/supplemental_materials.py](../../../product/backend/interfaces/http/routers/preparation/supplemental_materials.py) | 57 | MaterialPreviewRequest、MaterialCreateRequest、MaterialWithdrawRequest、MaterialRevisionRequest、build_supplemental_material_router |
| [product/backend/interfaces/http/routers/preparation/test_identities.py](../../../product/backend/interfaces/http/routers/preparation/test_identities.py) | 159 | TestIdentityCreateRequest、TestIdentityResetRequest、TestIdentityLoginRequest、AuthenticationRequest、build_test_identities_router |
| [product/backend/interfaces/http/routers/system/__init__.py](../../../product/backend/interfaces/http/routers/system/__init__.py) | 1 | 包、内部机制或样式 |
| [product/backend/interfaces/http/routers/system/agent_workflow.py](../../../product/backend/interfaces/http/routers/system/agent_workflow.py) | 93 | TaskDecision、TaskAnswer、TaskControl、build_agent_workflow_router |
| [product/backend/interfaces/http/routers/system/mcp_access.py](../../../product/backend/interfaces/http/routers/system/mcp_access.py) | 93 | ClientConnectRequest、MCPProjectGrantRequest、build_mcp_access_router |
| [product/backend/interfaces/http/routers/system/system.py](../../../product/backend/interfaces/http/routers/system/system.py) | 213 | build_system_router、HealthResponse、ReadyResponse、MaintenanceOperationRequest、UpdatePreviewRequest |
| [product/backend/interfaces/http/routers/workspace.py](../../../product/backend/interfaces/http/routers/workspace.py) | 25 | build_workspace_router |
| [product/backend/interfaces/worker/__init__.py](../../../product/backend/interfaces/worker/__init__.py) | 1 | 包、内部机制或样式 |
| [product/backend/interfaces/worker/job.py](../../../product/backend/interfaces/worker/job.py) | 190 | main |
| [product/backend/interfaces/worker/runtime.py](../../../product/backend/interfaces/worker/runtime.py) | 110 | run、main |
