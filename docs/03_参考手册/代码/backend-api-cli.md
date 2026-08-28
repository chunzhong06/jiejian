# 自动代码参考：后端 API 与 CLI

> 生成区域只描述当前代码结构；职责与安全理由由模块参考和任务指南维护。

<!-- GENERATED:START -->

<!-- 此区域由 scripts/docs/generate.py 从 product/backend/api/、product/backend/cli/ 读取。 -->

### `product/backend/api/__init__.py`
主要 import / dot-source：`.app`

### `product/backend/api/app.py`
- `create_app(var_dir, control_origin, control_session_token, frontend_dir, start_worker, llm_transport, llm_secret_store, secret_store, environ, clock_us, folder_selector, shutdown_callback, official_sample_root) -> FastAPI`
主要 import / dot-source：`__future__`, `asyncio`, `fastapi`, `fastapi.exceptions`, `fastapi.staticfiles`, `logging`, `pathlib`, `product.backend`, `product.backend.api.errors`, `product.backend.api.local_control`, `product.backend.api.routers.assistant`, `product.backend.api.routers.checks`, `product.backend.api.routers.contracts`, `product.backend.api.routers.execution_profiles`, `product.backend.api.routers.experience`, `product.backend.api.routers.gating`, `product.backend.api.routers.jobs`, `product.backend.api.routers.llm`, `product.backend.api.routers.onboarding`, `product.backend.api.routers.permission_intents`, `product.backend.api.routers.projects`, `product.backend.api.routers.recordings`, `product.backend.api.routers.results`, `product.backend.api.routers.runs`, `product.backend.api.routers.system`, `product.backend.api.routers.test_identities`, `product.backend.core.errors`, `product.backend.infra.runtime.worker.supervisor`, `product.backend.workflows.context`, `pydantic`, `time`, `uuid`

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

### `product/backend/api/routers/assistant.py`
- `class AssistantRefreshRequest`
- `build_assistant_router(context) -> APIRouter`
主要 import / dot-source：`__future__`, `fastapi`, `product.backend.api.envelope`, `product.backend.workflows.context`, `typing`

### `product/backend/api/routers/checks.py`
- `class CheckSubmitRequest`
- `build_checks_router(context) -> APIRouter`
主要 import / dot-source：`__future__`, `fastapi`, `product.backend.api.envelope`, `product.backend.workflows.context`, `pydantic`, `typing`

### `product/backend/api/routers/contracts.py`
- `build_contracts_router(context) -> APIRouter`
- `class RequirementCreateRequest`
- `class CandidateDeriveRequest`
- `class ContractDraftRequest`
- `class ContractRevisionRequest`
- `class GovernanceActorRequest`
主要 import / dot-source：`__future__`, `fastapi`, `json`, `product.backend.api.envelope`, `product.backend.core.verification.permissions`, `product.backend.workflows.context`, `pydantic`, `typing`

### `product/backend/api/routers/execution_profiles.py`
- `build_execution_profiles_router(context) -> APIRouter`
- `class ExecutionProfileCreateRequest`
主要 import / dot-source：`__future__`, `fastapi`, `pathlib`, `product.backend.api.envelope`, `product.backend.workflows.context`, `pydantic`, `typing`

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
- `class LLMProfileResponse`
- `class LLMDefaultProfileRequest`
主要 import / dot-source：`__future__`, `fastapi`, `product.backend.api.envelope`, `product.backend.infra.llm.catalog`, `product.backend.infra.llm.config`, `product.backend.workflows.context`, `pydantic`, `typing`

### `product/backend/api/routers/onboarding.py`
- `class OnboardingInspectRequest`
- `build_onboarding_router(context) -> APIRouter`
主要 import / dot-source：`__future__`, `fastapi`, `product.backend.api.envelope`, `product.backend.workflows.context`, `pydantic`, `typing`

### `product/backend/api/routers/permission_intents.py`
- `class PermissionIntentConfirmRequest`
- `class SecuritySetupCompileRequest`
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
主要 import / dot-source：`__future__`, `fastapi`, `json`, `product.backend.api.envelope`, `product.backend.core.application_understanding`, `product.backend.core.errors`, `product.backend.core.lifecycle`, `product.backend.workflows.context`, `product.backend.workflows.recording.safety_setup`, `product.backend.workflows.test_identities`, `product.protocols`, `pydantic`, `time`, `typing`

### `product/backend/api/routers/results.py`
- `class GateReportRequest`
- `build_results_router(context, results) -> APIRouter`
主要 import / dot-source：`__future__`, `fastapi`, `fastapi.responses`, `product.backend.api.envelope`, `product.backend.workflows.context`, `product.backend.workflows.results.published`, `pydantic`, `typing`

### `product/backend/api/routers/runs.py`
- `build_runs_router(context, results) -> APIRouter`
- `class RunCreateRequest`
主要 import / dot-source：`__future__`, `fastapi`, `product.backend.api.envelope`, `product.backend.core.errors`, `product.backend.core.lifecycle`, `product.backend.infra.storage`, `product.backend.workflows.context`, `product.backend.workflows.results.published`, `pydantic`, `typing`

### `product/backend/api/routers/system.py`
- `build_system_router(context, workers, shutdown_callback) -> APIRouter`
- `class HealthResponse`
- `class ReadyResponse`
- `class CacheOperationRequest`
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
- `root(context, config, var_dir, log_level, trace_id, json_output, human_output, verbose, version) -> None`
- `main() -> None`
主要 import / dot-source：`__future__`, `pathlib`, `product.backend`, `product.backend.cli.bootstrap`, `product.backend.cli.commands.contracts`, `product.backend.cli.commands.control`, `product.backend.cli.commands.gating`, `product.backend.cli.commands.projects`, `product.backend.cli.commands.recordings`, `product.backend.cli.commands.runs`, `product.backend.cli.commands.system`, `product.backend.cli.presentation`, `product.backend.core.errors`, `product.backend.infra.runtime.process.identity`, `sys`, `typer`, `uuid`

### `product/backend/cli/bootstrap.py`
- `class CliOptions`
- `runtime_settings(context) -> Settings`
- `application_scope(context, environ) -> Iterator[object]`
- `default_frontend_dir() -> Path`
主要 import / dot-source：`__future__`, `collections.abc`, `contextlib`, `dataclasses`, `pathlib`, `product.backend.infra.runtime.logging`, `product.backend.infra.runtime.settings`, `typer`

### `product/backend/cli/commands/contracts.py`
- `contract_validate_command(path) -> None`
- `contract_workspace_command(context, profile_path) -> None`
- `contract_requirement_add_command(context, profile_path, text, tag, actor) -> None`
- `contract_derive_command(context, profile_path, requirement, actor) -> None`
- `contract_draft_command(context, profile_path, contract_id, snapshot_path, actor) -> None`
- `contract_revise_command(context, profile_path, contract_id, snapshot_path, actor) -> None`
- `contract_transition_command(context, profile_path, contract_id, version, action, actor) -> None`
- `contract_assessment_command(context, profile_path, contract_id, version) -> None`
- `contract_diff_command(context, profile_path, contract_id, version, from_version) -> None`
- `contract_drift_command(context, profile_path, contract_id, version) -> None`
- `contract_history_command(context, run_id) -> None`
主要 import / dot-source：`__future__`, `contextlib`, `pathlib`, `product.backend.cli.bootstrap`, `product.backend.cli.presentation`, `product.backend.core.errors`, `product.backend.core.verification.permissions`, `typer`, `typing`

### `product/backend/cli/commands/control.py`
- `status_command(context, project_id) -> None`
- `app_list_command(context, include_archived) -> None`
- `app_show_command(context, project_id) -> None`
- `app_connect_command(context, source_root, name) -> None`
- `app_remove_command(context, project_id, confirmed) -> None`
- `app_discover_command(context, project_id) -> None`
- `app_confirm_endpoint_command(context, project_id, endpoint, revision) -> None`
- `app_authorize_source_command(context, project_id, revision) -> None`
- `app_analyze_command(context, project_id, revision) -> None`
- `app_decide_role_command(context, project_id, candidate_id, decision, revision, display_name) -> None`
- `app_decide_action_command(context, project_id, candidate_id, decision, revision, display_name) -> None`
- `app_add_role_command(context, project_id, display_name, revision) -> None`
- `app_add_action_command(context, project_id, display_name, revision, risk_hint) -> None`
- `account_list_command(context, project_id) -> None`
- `account_show_command(context, identity_id) -> None`
- `account_create_command(context, project_id, role_candidate_id, label) -> None`
- `account_prepare_command(context, identity_id) -> None`
- `account_preparation_command(context, preparation_id) -> None`
- `account_confirm_command(context, preparation_id) -> None`
- `account_cancel_command(context, preparation_id) -> None`
- `account_reset_command(context, identity_id) -> None`
- `account_delete_command(context, identity_id, confirm) -> None`
- `flow_list_command(context, project_id) -> None`
- `flow_show_command(context, recording_id) -> None`
- `flow_record_command(context, project_id, action_candidate_id, test_identity_id, duration_seconds) -> None`
- `flow_capture_start_command(context, recording_id) -> None`
- `flow_capture_stop_command(context, recording_id) -> None`
- `flow_finalize_command(context, recording_id) -> None`
- `flow_safety_command(context, recording_id) -> None`
- `check_permissions_command(context, project_id) -> None`
- `check_set_permission_command(context, project_id, action_candidate_id, subject_role_candidate_id, resource_owner_role_candidate_id, relation, expectation, actor) -> None`
- `check_preview_command(context, project_id) -> None`
- `check_prepare_command(context, project_id, actor) -> None`
- `check_cancel_command(context, project_id) -> None`
- `check_run_command(context, project_id, idempotency_key) -> None`
- `result_show_command(context, run_id, project_id) -> None`
- `result_reports_command(context, run_id) -> None`
- `result_evidence_command(context, run_id, project_id) -> None`
- `result_report_command(context, run_id, report_id) -> None`
- `result_repair_command(context, run_id) -> None`
- `history_show_command(context, project_id) -> None`
- `settings_show_command(context) -> None`
- `settings_test_command(context, profile_name) -> None`
主要 import / dot-source：`__future__`, `os`, `pathlib`, `product.backend.cli.bootstrap`, `product.backend.cli.presentation`, `product.backend.core.application_understanding`, `product.backend.core.errors`, `product.backend.core.lifecycle`, `product.backend.core.permission_intent`, `product.backend.core.verification.permissions`, `product.backend.infra.runtime.jobs.models`, `sys`, `time`, `typer`, `uuid`

### `product/backend/cli/commands/gating.py`
- `baseline_accept_command(context, run_id, actor, reason) -> None`
- `gate_evaluate_command(context, baseline_id, run_id, minimum_severity) -> None`
- `gate_result_command(context, gate_result_id) -> None`
主要 import / dot-source：`__future__`, `product.backend.cli.bootstrap`, `product.backend.cli.presentation`, `product.backend.core.errors`, `product.backend.core.verification.gating`, `typer`

### `product/backend/cli/commands/projects.py`
- `project_validate_command(path) -> None`
主要 import / dot-source：`__future__`, `pathlib`, `product.backend.cli.presentation`, `product.backend.core.errors`, `product.protocols`, `typer`

### `product/backend/cli/commands/recordings.py`
- `recording_start_command(context, profile_path, action_candidate_id, test_identity_id, duration_seconds, headless) -> None`
- `recording_status_command(context, recording_id) -> None`
- `recording_review_command(context, recording_id, command_path) -> None`
- `recording_finalize_command(context, recording_id) -> None`
- `recording_replay_command(context, recording_id, profile_path, runs) -> None`
主要 import / dot-source：`__future__`, `os`, `pathlib`, `product.backend.cli.bootstrap`, `product.backend.cli.presentation`, `product.backend.core.errors`, `product.backend.core.recording`, `product.backend.workflows.recording.flow_compiler`, `product.backend.workflows.recording.submission`, `product.protocols`, `time`, `typer`, `uuid`

### `product/backend/cli/commands/runs.py`
- `run_command(context, profile_path, accept_source_changes) -> None`
主要 import / dot-source：`__future__`, `os`, `pathlib`, `product.backend.cli.bootstrap`, `product.backend.cli.presentation`, `product.backend.core.errors`, `product.protocols`, `typer`, `uuid`

### `product/backend/cli/commands/system.py`
- `class ServeReadinessStatus`
- `serve_command(context, host, port, open_browser, frontend_dir, official_sample_root) -> None`
- `doctor_command(context) -> None`
- `cache_status_command(context) -> None`
- `cache_clean_command(context, confirm) -> None`
- `runtime_repair_command(context, confirm) -> None`
主要 import / dot-source：`__future__`, `enum`, `logging`, `os`, `pathlib`, `product.backend.cli.bootstrap`, `product.backend.cli.presentation`, `product.backend.core.errors`, `product.backend.infra.runtime.diagnostics`, `time`, `typer`

### `product/backend/cli/presentation.py`
- `configure_presentation(mode, machine_only, verbose) -> None`
- `set_command_mode(mode) -> None`
- `force_machine_mode() -> None`
- `presentation_mode(context) -> str`
- `verbose_enabled() -> bool`
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
