# 自动代码参考：后端 API 与 CLI

> 生成区域只描述当前代码结构；职责与安全理由由能力映射和任务指南维护。

<!-- GENERATED:START -->

<!-- 此区域由 scripts/docs/generate.py 从 product/backend/api/、product/backend/cli/ 读取。 -->

### `product/backend/api/__init__.py`
主要 import / dot-source：`.app`

### `product/backend/api/app.py`
- `create_app(var_dir, control_origin, control_session_token, frontend_dir, start_worker, llm_transport, llm_secret_store, secret_store, environ, clock_us, folder_selector, shutdown_callback, official_sample_root) -> FastAPI`
主要 import / dot-source：`__future__`, `asyncio`, `fastapi`, `fastapi.exceptions`, `logging`, `pathlib`, `product.backend`, `product.backend.api.errors`, `product.backend.api.frontend`, `product.backend.api.local_control`, `product.backend.api.mcp`, `product.backend.api.routers.applications.experience`, `product.backend.api.routers.applications.onboarding`, `product.backend.api.routers.applications.projects`, `product.backend.api.routers.boundaries.business_boundaries`, `product.backend.api.routers.boundaries.permission_drafts`, `product.backend.api.routers.changes.development`, `product.backend.api.routers.changes.source_changes`, `product.backend.api.routers.checks.checks`, `product.backend.api.routers.checks.results`, `product.backend.api.routers.checks.runs`, `product.backend.api.routers.preparation.preparation`, `product.backend.api.routers.preparation.recordings`, `product.backend.api.routers.preparation.supplemental_materials`, `product.backend.api.routers.preparation.test_identities`, `product.backend.api.routers.system.assistant`, `product.backend.api.routers.system.llm`, `product.backend.api.routers.system.mcp_access`, `product.backend.api.routers.system.system`, `product.backend.api.routers.workspace`, `product.backend.composition`, `product.backend.core.errors`, `product.backend.workflows.agent_access.service`, `pydantic`, `time`, `uuid`

### `product/backend/api/envelope.py`
- `class ApiModel`
- `class ApiResponse`
- `data_response(value, status_code) -> JSONResponse`
主要 import / dot-source：`__future__`, `fastapi.responses`, `pydantic`, `typing`

### `product/backend/api/errors.py`
- `jiejian_error_handler(request, exc) -> JSONResponse`
- `request_validation_error_handler(request, exc) -> JSONResponse`
- `validation_error_handler(request, exc) -> JSONResponse`
主要 import / dot-source：`__future__`, `fastapi`, `fastapi.exceptions`, `fastapi.responses`, `product.backend.core.errors`, `pydantic`

### `product/backend/api/frontend.py`
- `class ProductStaticFiles`
主要 import / dot-source：`fastapi.staticfiles`, `re`

### `product/backend/api/local_control.py`
- `class LocalControlDecision`
- `class LocalControlGuard`
主要 import / dot-source：`__future__`, `dataclasses`, `fastapi`, `fastapi.responses`, `hmac`, `product.backend.core.errors`, `secrets`, `urllib.parse`

### `product/backend/api/mcp/__init__.py`
主要 import / dot-source：`product.backend.api.mcp.server`

### `product/backend/api/mcp/errors.py`
- `_T`
- `_ACCESS_ERROR_CODES`
- `require_mcp_level(access, ctx, required_level, project_id) -> None`
主要 import / dot-source：`__future__`, `collections.abc`, `mcp`, `mcp.server.mcpserver`, `product.backend.core.errors`, `product.backend.workflows.agent_access.service`, `pydantic`, `typing`

### `product/backend/api/mcp/preparation.py`
- `public_preparation(value)`
- `register_preparation_tools(server, context, access, require_level, invoke, client_name)`
主要 import / dot-source：`json`, `mcp.server.mcpserver`, `product.backend.workflows.agent_access.service`, `product.backend.workflows.preparation.proofs.commands`, `typing`

### `product/backend/api/mcp/server.py`
- `_REQUEST_CLIENT`
- `class MCPControl`
- `build_mcp_control(context, access, control_origin, control_host) -> MCPControl`
主要 import / dot-source：`__future__`, `collections.abc`, `contextvars`, `dataclasses`, `json`, `mcp.server`, `mcp.server.context`, `mcp.server.mcpserver`, `mcp.server.transport_security`, `product.backend`, `product.backend.api.mcp.errors`, `product.backend.api.mcp.transport`, `product.backend.api.mcp.views`, `product.backend.composition`, `product.backend.core.boundaries.rule_candidates`, `product.backend.core.checks.repair`, `product.backend.core.development`, `product.backend.core.errors`, `product.backend.infra.runtime.diagnostics`, `product.backend.workflows.agent_access.service`, `starlette.types`, `typing`

### `product/backend/api/mcp/transport.py`
- `class MCPBearerGuard`
- `class MCPPathAdapter`
主要 import / dot-source：`__future__`, `product.backend.api.mcp.errors`, `product.backend.core.errors`, `product.backend.workflows.agent_access.service`, `starlette.datastructures`, `starlette.responses`, `starlette.types`

### `product/backend/api/mcp/views.py`
主要 import / dot-source：`__future__`, `pydantic`, `typing`

### `product/backend/api/routers/applications/current_experience.py`
- `build_current_experience_router() -> APIRouter`
主要 import / dot-source：`__future__`, `fastapi`, `product.backend.api.envelope`

### `product/backend/api/routers/applications/experience.py`
- `build_experience_router(context) -> APIRouter`
- `class OfficialSampleStartRequest`
- `class OfficialSampleStopRequest`
- `class OfficialSampleVersionRequest`
- `class OfficialObservationRequest`
主要 import / dot-source：`__future__`, `fastapi`, `product.backend.api.envelope`, `product.backend.composition`, `product.backend.core.checks.repair`, `product.backend.workflows.examples.environment`, `typing`

### `product/backend/api/routers/applications/onboarding.py`
- `class OnboardingInspectRequest`
- `build_onboarding_router(context) -> APIRouter`
主要 import / dot-source：`__future__`, `fastapi`, `product.backend.api.envelope`, `product.backend.composition`, `pydantic`, `typing`

### `product/backend/api/routers/applications/projects.py`
- `build_projects_router(context) -> APIRouter`
- `class RuntimePreviewRequest`
- `class RuntimeStartRequest`
- `class RuntimeStopRequest`
- `class ApplicationConnectRequest`
- `class EndpointConfirmationRequest`
- `class SourceAnalysisAuthorizationRequest`
- `class SourceAnalysisRequest`
- `class CandidateBatchDecisionRequest`
- `class CandidateDecisionRequest`
- `class ManualRoleRequest`
- `class ManualActionRequest`
主要 import / dot-source：`__future__`, `fastapi`, `product.backend.api.envelope`, `product.backend.composition`, `product.backend.core.applications.models`, `pydantic`, `typing`

### `product/backend/api/routers/boundaries/business_boundaries.py`
- `class BoundaryProposalCreateRequest`
- `class BoundaryDecisionRequest`
- `class RuleCandidateSaveRequest`
- `class RuleCandidateProposalRequest`
- `class BoundaryMaintenanceCreateRequest`
- `build_business_boundaries_router(context) -> APIRouter`
主要 import / dot-source：`__future__`, `fastapi`, `fastapi.encoders`, `json`, `product.backend.api.envelope`, `product.backend.composition`, `product.backend.core.boundaries.proposals`, `product.backend.core.boundaries.rule_candidates`, `product.backend.workflows.business_boundaries`, `pydantic`, `typing`

### `product/backend/api/routers/boundaries/permission_drafts.py`
- `class PermissionDraftRequest`
- `build_permission_drafts_router(context) -> APIRouter`
主要 import / dot-source：`fastapi`, `product.backend.api.envelope`, `pydantic`, `typing`

### `product/backend/api/routers/boundaries/permission_intents.py`
- `class PermissionIntentCellTarget`
- `class PermissionIntentApprovalRequest`
- `class PermissionIntentProposalApprovalRequest`
- `class PermissionIntentProposalDecisionRequest`
- `class PermissionDraftRequest`
- `build_permission_intents_router(context) -> APIRouter`
主要 import / dot-source：`__future__`, `fastapi`, `product.backend.api.envelope`, `product.backend.composition`, `product.backend.core.boundaries.permissions`, `product.backend.core.verification.permissions`, `pydantic`, `typing`

### `product/backend/api/routers/changes/development.py`
- `class TaskCreateRequest`
- `class TaskReviseRequest`
- `class TaskFinishRequest`
- `class RuntimeLoadRequest`
- `build_development_router(context)`
主要 import / dot-source：`fastapi`, `product.backend.api.envelope`, `product.backend.core.development`, `pydantic`, `typing`

### `product/backend/api/routers/changes/source_changes.py`
- `class SourceChangeCreateRequest`
- `class SourceChangeRegistrationRequest`
- `build_source_changes_router(context) -> APIRouter`
主要 import / dot-source：`__future__`, `fastapi`, `product.backend.api.envelope`, `product.backend.composition`, `product.backend.core.checks.repair`, `product.backend.core.development`, `product.backend.core.errors`, `product.protocols.checks.execution_request`, `pydantic`, `typing`

### `product/backend/api/routers/checks/checks.py`
- `build_checks_router(context) -> APIRouter`
主要 import / dot-source：`fastapi`, `product.backend.api.envelope`, `product.backend.composition`

### `product/backend/api/routers/checks/gating.py`
- `build_gating_router(context) -> APIRouter`
- `class BaselineAcceptRequest`
- `class GateEvaluateRequest`
主要 import / dot-source：`__future__`, `fastapi`, `product.backend.api.envelope`, `product.backend.composition`, `pydantic`, `typing`

### `product/backend/api/routers/checks/jobs.py`
- `build_jobs_router(context) -> APIRouter`
主要 import / dot-source：`__future__`, `asyncio`, `collections.abc`, `fastapi`, `fastapi.responses`, `json`, `product.backend.api.envelope`, `product.backend.composition`, `product.backend.core.errors`, `product.backend.core.lifecycle`, `product.backend.core.redaction`, `product.backend.infra.runtime.jobs.models`, `time`

### `product/backend/api/routers/checks/results.py`
- `build_results_router(context) -> APIRouter`
主要 import / dot-source：`fastapi`, `product.backend.api.envelope`, `product.backend.composition`

### `product/backend/api/routers/checks/runs.py`
- `class RunCreateRequest`
- `build_runs_router(context) -> APIRouter`
主要 import / dot-source：`__future__`, `fastapi`, `product.backend.api.envelope`, `product.backend.composition`, `product.backend.core.identifiers`, `product.backend.core.lifecycle`, `pydantic`, `typing`

### `product/backend/api/routers/preparation/preparation.py`
- `class AllowControlSelectionRequest`
- `build_preparation_router(context) -> APIRouter`
主要 import / dot-source：`fastapi`, `product.backend.api.envelope`, `product.backend.core.preparation.requirements`, `product.backend.workflows.preparation.materials.models`, `pydantic`, `typing`

### `product/backend/api/routers/preparation/proof_sources.py`
- `require_local_proof_session(request)`
- `build_proof_sources_router(context)`
主要 import / dot-source：`fastapi`, `product.backend.api.envelope`, `product.backend.workflows.preparation.proofs.commands`, `typing`

### `product/backend/api/routers/preparation/recordings.py`
- `build_recordings_router(context) -> APIRouter`
- `class RecordingCreateRequest`
- `class ReviewRequest`
- `class FinalizeRequest`
主要 import / dot-source：`__future__`, `fastapi`, `json`, `product.backend.api.envelope`, `product.backend.composition`, `product.backend.core.boundaries.entities`, `product.backend.core.errors`, `product.backend.core.lifecycle`, `product.backend.core.recording.models`, `product.backend.infra.runtime.jobs.models`, `product.backend.workflows.test_identities`, `product.protocols`, `pydantic`, `time`, `typing`

### `product/backend/api/routers/preparation/supplemental_materials.py`
- `class MaterialPreviewRequest`
- `class MaterialCreateRequest`
- `class MaterialWithdrawRequest`
- `class MaterialRevisionRequest`
- `build_supplemental_material_router(context)`
主要 import / dot-source：`fastapi`, `product.backend.api.envelope`, `product.backend.workflows.preparation.supplemental.contract`, `pydantic`

### `product/backend/api/routers/preparation/test_identities.py`
- `class TestIdentityCreateRequest`
- `class TestIdentityResetRequest`
- `build_test_identities_router(context) -> APIRouter`
主要 import / dot-source：`__future__`, `fastapi`, `product.backend.api.envelope`, `product.backend.composition`, `pydantic`, `typing`

### `product/backend/api/routers/system/assistant.py`
- `class ProjectAssistantSurface`
- `_PROJECT_TEMPLATE`
- `class AssistantGenerateRequest`
- `class AssistantFocus`
- `build_assistant_router(context) -> APIRouter`
主要 import / dot-source：`__future__`, `enum`, `fastapi`, `product.backend.api.envelope`, `product.backend.core.boundaries.entities`, `product.backend.core.identifiers`, `product.backend.workflows.assistant.templates`, `pydantic`, `typing`

### `product/backend/api/routers/system/llm.py`
- `build_llm_router(context) -> APIRouter`
- `class LLMSettingsRequest`
- `class LLMModelDiscoverRequest`
- `class LLMProfileBase`
- `class LLMProfileCreateRequest`
- `class LLMProfileUpdateRequest`
- `class LLMDefaultProfileRequest`
主要 import / dot-source：`__future__`, `fastapi`, `product.backend.api.envelope`, `product.backend.composition`, `product.backend.infra.llm.catalog`, `product.backend.infra.llm.config`, `pydantic`, `typing`

### `product/backend/api/routers/system/mcp_access.py`
- `class MCPProjectGrantRequest`
- `build_mcp_access_router(context, access) -> APIRouter`
主要 import / dot-source：`__future__`, `fastapi`, `product.backend.api.envelope`, `product.backend.composition`, `product.backend.workflows.agent_access.service`, `typing`

### `product/backend/api/routers/system/system.py`
- `build_system_router(context, shutdown_callback) -> APIRouter`
- `class HealthResponse`
- `class ReadyResponse`
- `class MaintenanceOperationRequest`
主要 import / dot-source：`__future__`, `fastapi`, `fastapi.responses`, `product.backend`, `product.backend.api.envelope`, `product.backend.composition`, `product.backend.core.errors`, `product.backend.infra.runtime.diagnostics`, `product.backend.infra.runtime.frontend_assets`, `product.backend.infra.storage`, `typing`

### `product/backend/api/routers/workspace.py`
- `build_workspace_router(context) -> APIRouter`
主要 import / dot-source：`fastapi`, `product.backend.api.envelope`, `product.backend.composition`

### `product/backend/cli/__init__.py`
主要 import / dot-source：`.app`

### `product/backend/cli/__main__.py`
主要 import / dot-source：`product.backend.cli`

### `product/backend/cli/app.py`
- `root(context, var_dir, json_output, version) -> None`
- `main() -> None`
主要 import / dot-source：`__future__`, `pathlib`, `product.backend`, `product.backend.cli.bootstrap`, `product.backend.cli.commands.system`, `product.backend.cli.localization`, `product.backend.cli.presentation`, `product.backend.core.errors`, `product.backend.infra.runtime.process.controlled.identity`, `sys`, `typer`, `uuid`

### `product/backend/cli/bootstrap.py`
- `class CliOptions`
- `runtime_settings(context) -> Settings`
- `application_scope(context, environ) -> Iterator[object]`
- `default_frontend_dir() -> Path`
主要 import / dot-source：`__future__`, `collections.abc`, `contextlib`, `dataclasses`, `pathlib`, `product.backend.infra.runtime.logging`, `product.backend.infra.runtime.settings`, `typer`

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
- `emit_command(kind, data, next_actions, warnings, human) -> None`
- `emit_json(payload) -> None`
- `fail(error) -> NoReturn`
- `human_wait(message)`
主要 import / dot-source：`__future__`, `click`, `collections.abc`, `contextlib`, `json`, `product.backend.core.errors`, `threading`, `typer`, `typing`, `uuid`

<!-- GENERATED:END -->
