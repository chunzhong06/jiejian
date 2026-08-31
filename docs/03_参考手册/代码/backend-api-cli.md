# 自动代码参考：后端 API 与 CLI

> 生成区域只描述当前代码结构；职责与安全理由由模块参考和任务指南维护。

<!-- GENERATED:START -->

<!-- 此区域由 scripts/docs/generate.py 从 product/backend/api/、product/backend/cli/ 读取。 -->

### `product/backend/api/__init__.py`
主要 import / dot-source：`.app`

### `product/backend/api/app.py`
- `create_app(var_dir, control_origin, control_session_token, frontend_dir, start_worker, llm_transport, llm_secret_store, secret_store, environ, clock_us, folder_selector, shutdown_callback, official_sample_root) -> FastAPI`
主要 import / dot-source：`__future__`, `asyncio`, `fastapi`, `fastapi.exceptions`, `fastapi.staticfiles`, `logging`, `pathlib`, `product.backend`, `product.backend.api.errors`, `product.backend.api.local_control`, `product.backend.api.mcp`, `product.backend.api.routers.assistant`, `product.backend.api.routers.checks`, `product.backend.api.routers.experience`, `product.backend.api.routers.gating`, `product.backend.api.routers.jobs`, `product.backend.api.routers.llm`, `product.backend.api.routers.mcp_access`, `product.backend.api.routers.onboarding`, `product.backend.api.routers.permission_intents`, `product.backend.api.routers.projects`, `product.backend.api.routers.recordings`, `product.backend.api.routers.results`, `product.backend.api.routers.runs`, `product.backend.api.routers.source_changes`, `product.backend.api.routers.system`, `product.backend.api.routers.test_identities`, `product.backend.core.errors`, `product.backend.infra.runtime.worker.supervisor`, `product.backend.workflows.context`, `product.backend.workflows.mcp_access`, `pydantic`, `time`, `uuid`

### `product/backend/api/envelope.py`
- `class ApiModel`
- `class ApiResponse`
- `data_response(value, status_code) -> JSONResponse`
主要 import / dot-source：`__future__`, `fastapi.responses`, `pydantic`, `typing`

### `product/backend/api/errors.py`
- `jiejian_error_handler(request, exc) -> JSONResponse`
- `request_validation_error_handler(request, exc) -> JSONResponse`
- `validation_error_handler(request, exc) -> JSONResponse`
主要 import / dot-source：`__future__`, `fastapi`, `fastapi.exceptions`, `fastapi.responses`, `product.backend.core.errors`, `product.backend.workflows.assistant.diagnosis`, `pydantic`

### `product/backend/api/local_control.py`
- `class LocalControlDecision`
- `class LocalControlGuard`
主要 import / dot-source：`__future__`, `dataclasses`, `fastapi`, `fastapi.responses`, `hmac`, `product.backend.core.errors`, `secrets`, `urllib.parse`

### `product/backend/api/mcp.py`
- `_T`
- `_ACCESS_ERROR_CODES`
- `class MCPProtectedEffectInput`
- `class MCPPermissionIntentSemanticInput`
- `class MCPRepairContractReferenceInput`
- `require_mcp_level(access, ctx, required_level, project_id) -> None`
- `class MCPBearerGuard`
- `class MCPPathAdapter`
- `class MCPControl`
- `build_mcp_control(context, workers, access, control_origin, control_host) -> MCPControl`
主要 import / dot-source：`__future__`, `collections.abc`, `dataclasses`, `mcp`, `mcp.server`, `mcp.server.context`, `mcp.server.mcpserver`, `mcp.server.transport_security`, `product.backend`, `product.backend.core.errors`, `product.backend.core.permission_intent`, `product.backend.core.repair`, `product.backend.core.verification.permissions`, `product.backend.infra.runtime.diagnostics`, `product.backend.infra.runtime.jobs.models`, `product.backend.infra.runtime.worker.supervisor`, `product.backend.workflows.context`, `product.backend.workflows.mcp_access`, `product.backend.workflows.official_sample`, `pydantic`, `starlette.datastructures`, `starlette.responses`, `starlette.types`, `time`, `typing`

### `product/backend/api/routers/assistant.py`
- `class ProjectAssistantSurface`
- `_PROJECT_TEMPLATE`
- `class AssistantGenerateRequest`
- `class ErrorAssistantRequest`
- `build_assistant_router(context) -> APIRouter`
主要 import / dot-source：`__future__`, `enum`, `fastapi`, `product.backend.api.envelope`, `product.backend.workflows.assistant.diagnosis`, `product.backend.workflows.assistant.templates`, `product.backend.workflows.context`, `pydantic`, `typing`

### `product/backend/api/routers/checks.py`
- `class CheckSubmitRequest`
- `class CheckPrepareRequest`
- `build_checks_router(context) -> APIRouter`
主要 import / dot-source：`__future__`, `fastapi`, `product.backend.api.envelope`, `product.backend.workflows.context`, `pydantic`, `typing`

### `product/backend/api/routers/experience.py`
- `build_experience_router(context) -> APIRouter`
- `class OfficialSampleStartRequest`
- `class OfficialSampleBehaviorRequest`
主要 import / dot-source：`__future__`, `fastapi`, `product.backend.api.envelope`, `product.backend.workflows.context`, `product.backend.workflows.official_sample`, `pydantic`, `typing`

### `product/backend/api/routers/gating.py`
- `build_gating_router(context) -> APIRouter`
- `class BaselineAcceptRequest`
- `class GateEvaluateRequest`
主要 import / dot-source：`__future__`, `fastapi`, `product.backend.api.envelope`, `product.backend.workflows.context`, `pydantic`, `typing`

### `product/backend/api/routers/jobs.py`
- `build_jobs_router(context) -> APIRouter`
主要 import / dot-source：`__future__`, `asyncio`, `collections.abc`, `fastapi`, `fastapi.responses`, `json`, `product.backend.api.envelope`, `product.backend.core.errors`, `product.backend.core.lifecycle`, `product.backend.core.redaction`, `product.backend.infra.runtime.jobs.models`, `product.backend.workflows.context`, `time`

### `product/backend/api/routers/llm.py`
- `build_llm_router(context) -> APIRouter`
- `class LLMSettingsRequest`
- `class LLMModelDiscoverRequest`
- `class LLMProfileBase`
- `class LLMProfileCreateRequest`
- `class LLMProfileUpdateRequest`
- `class LLMDefaultProfileRequest`
主要 import / dot-source：`__future__`, `fastapi`, `product.backend.api.envelope`, `product.backend.infra.llm.catalog`, `product.backend.infra.llm.config`, `product.backend.workflows.context`, `pydantic`, `typing`

### `product/backend/api/routers/mcp_access.py`
- `class MCPProjectGrantRequest`
- `build_mcp_access_router(context, access) -> APIRouter`
主要 import / dot-source：`__future__`, `fastapi`, `product.backend.api.envelope`, `product.backend.workflows.context`, `product.backend.workflows.mcp_access`, `typing`

### `product/backend/api/routers/onboarding.py`
- `class OnboardingInspectRequest`
- `build_onboarding_router(context) -> APIRouter`
主要 import / dot-source：`__future__`, `fastapi`, `product.backend.api.envelope`, `product.backend.workflows.context`, `pydantic`, `typing`

### `product/backend/api/routers/permission_intents.py`
- `class PermissionIntentCellTarget`
- `class PermissionIntentApprovalRequest`
- `class PermissionIntentProposalApprovalRequest`
- `class PermissionIntentProposalDecisionRequest`
- `build_permission_intents_router(context) -> APIRouter`
主要 import / dot-source：`__future__`, `fastapi`, `product.backend.api.envelope`, `product.backend.core.permission_intent`, `product.backend.core.verification.permissions`, `product.backend.workflows.context`, `pydantic`, `typing`

### `product/backend/api/routers/projects.py`
- `build_projects_router(context) -> APIRouter`
- `class ApplicationConnectRequest`
- `class EndpointConfirmationRequest`
- `class SourceAnalysisAuthorizationRequest`
- `class SourceAnalysisRequest`
- `class CandidateDecisionRequest`
- `class ManualRoleRequest`
- `class ManualActionRequest`
主要 import / dot-source：`__future__`, `fastapi`, `product.backend.api.envelope`, `product.backend.core.application_understanding`, `product.backend.workflows.context`, `pydantic`, `typing`

### `product/backend/api/routers/recordings.py`
- `build_recordings_router(context) -> APIRouter`
- `class RecordingCreateRequest`
- `class ReviewRequest`
- `class FinalizeRequest`
- `class ActionSafetySetupConfirmRequest`
主要 import / dot-source：`__future__`, `fastapi`, `json`, `product.backend.api.envelope`, `product.backend.core.application_understanding`, `product.backend.core.errors`, `product.backend.core.lifecycle`, `product.backend.core.recording`, `product.backend.workflows.context`, `product.backend.workflows.recording.safety_setup`, `product.backend.workflows.test_identities`, `product.protocols`, `pydantic`, `time`, `typing`

### `product/backend/api/routers/results.py`
- `class GateReportRequest`
- `build_results_router(context, results) -> APIRouter`
主要 import / dot-source：`__future__`, `fastapi`, `fastapi.responses`, `product.backend.api.envelope`, `product.backend.workflows.context`, `product.backend.workflows.results.published`, `pydantic`, `typing`

### `product/backend/api/routers/runs.py`
- `build_runs_router(context, results) -> APIRouter`
- `class RunCreateRequest`
主要 import / dot-source：`__future__`, `fastapi`, `product.backend.api.envelope`, `product.backend.core.errors`, `product.backend.core.lifecycle`, `product.backend.infra.storage`, `product.backend.workflows.context`, `product.backend.workflows.results.published`, `pydantic`, `typing`

### `product/backend/api/routers/source_changes.py`
- `build_source_changes_router(context) -> APIRouter`
主要 import / dot-source：`__future__`, `fastapi`, `product.backend.api.envelope`, `product.backend.core.errors`, `product.backend.workflows.context`

### `product/backend/api/routers/system.py`
- `build_system_router(context, workers, shutdown_callback) -> APIRouter`
- `class HealthResponse`
- `class ReadyResponse`
- `class MaintenanceOperationRequest`
主要 import / dot-source：`__future__`, `fastapi`, `fastapi.responses`, `product.backend`, `product.backend.api.envelope`, `product.backend.core.errors`, `product.backend.infra.runtime.diagnostics`, `product.backend.infra.runtime.worker.supervisor`, `product.backend.infra.storage`, `product.backend.workflows.context`, `typing`

### `product/backend/api/routers/test_identities.py`
- `class TestIdentityCreateRequest`
- `class IdentityPreparationCommand`
- `build_test_identities_router(context) -> APIRouter`
主要 import / dot-source：`__future__`, `fastapi`, `product.backend.api.envelope`, `product.backend.workflows.context`, `pydantic`, `typing`

### `product/backend/cli/__init__.py`
主要 import / dot-source：`.app`

### `product/backend/cli/__main__.py`
主要 import / dot-source：`product.backend.cli`

### `product/backend/cli/app.py`
- `root(context, var_dir, json_output, version) -> None`
- `main() -> None`
主要 import / dot-source：`__future__`, `pathlib`, `product.backend`, `product.backend.cli.bootstrap`, `product.backend.cli.commands.control`, `product.backend.cli.commands.system`, `product.backend.cli.localization`, `product.backend.cli.presentation`, `product.backend.core.errors`, `product.backend.infra.runtime.process.identity`, `sys`, `typer`, `uuid`

### `product/backend/cli/bootstrap.py`
- `class CliOptions`
- `runtime_settings(context) -> Settings`
- `application_scope(context, environ) -> Iterator[object]`
- `default_frontend_dir() -> Path`
主要 import / dot-source：`__future__`, `collections.abc`, `contextlib`, `dataclasses`, `pathlib`, `product.backend.infra.runtime.logging`, `product.backend.infra.runtime.settings`, `typer`

### `product/backend/cli/commands/control.py`
- `status_command(context, project_id) -> None`
- `application_list_command(context) -> None`
- `application_show_command(context, project_id) -> None`
- `application_remove_command(context, project_id, confirmed) -> None`
- `source_change_list_command(context, project_id, limit) -> None`
- `source_change_show_command(context, project_id, change_id) -> None`
- `check_preview_command(context, project_id, change_id) -> None`
- `check_prepare_command(context, project_id, change_id) -> None`
- `check_cancel_command(context, project_id) -> None`
- `check_run_command(context, project_id, change_id) -> None`
- `result_show_command(context, run_id, project_id) -> None`
- `result_report_command(context, run_id, report_id) -> None`
- `history_command(context, project_id) -> None`
主要 import / dot-source：`__future__`, `product.backend.cli.bootstrap`, `product.backend.cli.presentation`, `product.backend.core.errors`, `product.backend.core.lifecycle`, `product.backend.infra.runtime.jobs.models`, `time`, `typer`, `uuid`

### `product/backend/cli/commands/system.py`
- `class ServeReadinessStatus`
- `serve_command(context, host, port, open_browser, frontend_dir, official_sample_root) -> None`
- `doctor_command(context) -> None`
- `maintenance_clean_assistant_command(context, confirm) -> None`
- `maintenance_clean_logs_command(context, confirm) -> None`
- `maintenance_clean_temporary_command(context, confirm) -> None`
- `maintenance_clean_all_command(context, confirm) -> None`
- `maintenance_repair_command(context, confirm) -> None`
主要 import / dot-source：`__future__`, `enum`, `logging`, `os`, `pathlib`, `product.backend.cli.bootstrap`, `product.backend.cli.presentation`, `product.backend.core.errors`, `product.backend.infra.runtime.diagnostics`, `time`, `typer`

### `product/backend/cli/localization.py`
- `class ChineseHelpFormatter`
- `configure_cli_localization() -> None`
主要 import / dot-source：`__future__`, `collections.abc`, `re`, `typer`

### `product/backend/cli/presentation.py`
- `configure_presentation(mode, machine_only) -> None`
- `set_command_mode(mode) -> None`
- `force_machine_mode() -> None`
- `presentation_mode(context) -> str`
- `_FIELD_LABELS`
- `_DOCTOR_LABELS`
- `emit_human(payload) -> None`
- `emit_doctor(report) -> None`
- `emit_result_presentation(presentation) -> None`
- `emit_status(status) -> None`
- `emit_command(kind, data, next_actions, warnings, human) -> None`
- `emit_json(payload) -> None`
- `fail(error) -> NoReturn`
- `human_wait(message)`
主要 import / dot-source：`__future__`, `click`, `collections.abc`, `contextlib`, `json`, `product.backend.core.errors`, `product.backend.workflows.results.presentation`, `threading`, `typer`, `typing`, `uuid`

<!-- GENERATED:END -->
