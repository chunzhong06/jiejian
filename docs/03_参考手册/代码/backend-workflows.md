# 自动代码参考：后端 Workflows

> 生成区域只描述当前代码结构；职责与安全理由由模块参考和任务指南维护。

<!-- GENERATED:START -->

<!-- 此区域由 scripts/docs/generate.py 从 product/backend/workflows/ 读取。 -->

### `product/backend/workflows/application_understanding/analysis/__init__.py`
主要 import / dot-source：`.analyzer`, `.models`

### `product/backend/workflows/application_understanding/analysis/analyzer.py`
- `class ApplicationUnderstandingAnalyzer`
主要 import / dot-source：`.javascript`, `.models`, `.openapi`, `.python`, `__future__`, `collections.abc`, `hashlib`, `os`, `pathlib`, `product.backend.core.application_understanding`, `product.backend.core.errors`, `product.backend.workflows.onboarding.discovery`, `re`

### `product/backend/workflows/application_understanding/analysis/javascript.py`
- `class JavaScriptAnalysisMixin`
主要 import / dot-source：`.models`, `__future__`, `product.backend.core.application_understanding`, `product.backend.core.http_routes`

### `product/backend/workflows/application_understanding/analysis/models.py`
- `_IGNORED_DIRECTORIES`
- `_SOURCE_SUFFIXES`
- `_OPENAPI_NAMES`
- `_SENSITIVE_FILE`
- `_ROLE_CONTEXT`
- `_ROLE_CLASS`
- `_ROLE_GUARD`
- `_JS_ROLE_STRUCTURE`
- `_JS_STRING`
- `_JS_ROUTE`
- `_JS_REQUEST`
- `_FETCH_REQUEST`
- `_CONFIDENCE_RANK`
- `_METHOD_LABEL`
- `class AnalysisModel`
- `class SourceAnalysisLimits`
- `class ApplicationAnalysisResult`
主要 import / dot-source：`__future__`, `ast`, `collections.abc`, `hashlib`, `json`, `os`, `pathlib`, `product.backend.core.application_understanding`, `product.backend.core.contracts.analysis.models`, `product.backend.core.contracts.analysis.sources.openapi`, `product.backend.core.errors`, `product.backend.core.http_routes`, `product.backend.workflows.onboarding.discovery`, `pydantic`, `re`, `yaml`

### `product/backend/workflows/application_understanding/analysis/openapi.py`
- `class OpenApiAnalysisMixin`
主要 import / dot-source：`.models`, `__future__`, `collections.abc`, `json`, `product.backend.core.application_understanding`, `product.backend.core.contracts.analysis.models`, `product.backend.core.contracts.analysis.sources.openapi`, `product.backend.core.http_routes`, `product.backend.workflows.onboarding.discovery`, `yaml`

### `product/backend/workflows/application_understanding/analysis/python.py`
- `class PythonAnalysisMixin`
主要 import / dot-source：`.models`, `__future__`, `ast`, `product.backend.core.application_understanding`, `product.backend.core.http_routes`

### `product/backend/workflows/application_understanding/endpoints.py`
- `_CONFIG_NAMES`
- `_IGNORED_DIRECTORIES`
- `_URL_LITERAL`
- `_PORT_LITERAL`
- `_COMMAND_PORT`
- `_SOURCE_RANK`
- `_FRAMEWORK_DEFAULTS`
- `class EndpointModel`
- `class EndpointDiscoveryLimits`
- `class EndpointProbeObservation`
- `class EndpointCandidate`
- `class EndpointDiscoveryResult`
- `normalize_loopback_endpoint(value) -> str`
- `class TargetEndpointDiscovery`
主要 import / dot-source：`__future__`, `collections.abc`, `hashlib`, `http.client`, `json`, `os`, `pathlib`, `product.backend.core.errors`, `product.backend.workflows.onboarding.discovery`, `pydantic`, `re`, `socket`, `typing`, `urllib.parse`, `yaml`

### `product/backend/workflows/application_understanding/service.py`
- `class ApplicationConnectionView`
- `class ApplicationUnderstandingService`
主要 import / dot-source：`__future__`, `collections.abc`, `hashlib`, `os`, `pathlib`, `product.backend.core.application_understanding`, `product.backend.core.errors`, `product.backend.core.lifecycle`, `product.backend.infra.storage`, `product.backend.workflows.application_understanding.analysis.analyzer`, `product.backend.workflows.application_understanding.endpoints`, `product.backend.workflows.onboarding.discovery`, `product.backend.workflows.onboarding.models`, `product.protocols`, `pydantic`, `re`, `time`, `typing`

### `product/backend/workflows/assistant/__init__.py`
主要 import / dot-source：`product.backend.workflows.assistant.diagnosis`, `product.backend.workflows.assistant.guidance`, `product.backend.workflows.assistant.templates`

### `product/backend/workflows/assistant/cache.py`
- `class AssistantCache`
主要 import / dot-source：`__future__`, `hashlib`, `json`, `os`, `pathlib`, `product.backend.core.errors`, `product.backend.workflows.assistant.templates`, `tempfile`, `typing`

### `product/backend/workflows/assistant/diagnosis.py`
- `class ErrorArea`
- `class ErrorPhase`
- `class ErrorIntervention`
- `class RecoveryAction`
- `class ErrorDiagnosisContext`
- `class ErrorDiagnosis`
- `_SELF_TARGET`
- `_SESSION_EXPIRED`
- `_OBSERVER_INCOMPLETE`
- `_EXACT_PRESENTATIONS`
- `_CLEANUP_WARNINGS`
- `diagnose_error(context) -> ErrorDiagnosis`
主要 import / dot-source：`__future__`, `enum`, `product.backend.core.errors`, `product.backend.core.lifecycle`, `product.protocols.runner`, `pydantic`, `typing`

### `product/backend/workflows/assistant/guidance.py`
- `class GuidancePhase`
- `class GuidanceOptionKind`
- `class GuidancePriorityTier`
- `class GuidanceOption`
- `class GuidanceSnapshot`
- `class GuidanceQueryService`
- `_ROUTE_RANK`
- `_ROUTE_PRESENTATION`
- `_NEXT_ACTION`
- `build_guidance_snapshot(readiness, preview) -> GuidanceSnapshot`
主要 import / dot-source：`__future__`, `collections.abc`, `enum`, `hashlib`, `json`, `product.backend.core.errors`, `product.backend.workflows.projects.readiness`, `product.backend.workflows.security_setup.checks`, `pydantic`, `re`, `typing`

### `product/backend/workflows/assistant/service.py`
- `class AssistantStatus`
- `class AssistantSurfaceView`
- `class AssistantService`
主要 import / dot-source：`__future__`, `collections.abc`, `enum`, `product.backend.core.errors`, `product.backend.infra.llm.adapters.base`, `product.backend.infra.llm.profiles`, `product.backend.workflows.assistant.cache`, `product.backend.workflows.assistant.diagnosis`, `product.backend.workflows.assistant.surfaces`, `product.backend.workflows.assistant.templates`, `pydantic`, `re`, `threading`, `time`

### `product/backend/workflows/assistant/surfaces.py`
- `PROJECT_ASSISTANT_TEMPLATES`
- `class ResolvedAssistantSurface`
- `class AssistantSurfaceResolver`
主要 import / dot-source：`__future__`, `collections.abc`, `dataclasses`, `hashlib`, `json`, `product.backend.core.application_understanding`, `product.backend.core.errors`, `product.backend.workflows.assistant.diagnosis`, `product.backend.workflows.assistant.templates`

### `product/backend/workflows/assistant/templates.py`
- `class AssistantTemplateId`
- `class AssistantEntityType`
- `class AssistantSuggestionKind`
- `class AssistantTemplateSpec`
- `class AssistantFact`
- `class AssistantEntity`
- `class AssistantSurfaceInput`
- `class AssistantSuggestion`
- `class AssistantResult`
- `ASSISTANT_SAFETY_INSTRUCTIONS`
- `ASSISTANT_TEMPLATES`
- `build_surface_input(template_id, subject_id, facts, entities) -> AssistantSurfaceInput`
- `render_assistant_prompt(value) -> str`
- `assistant_result_json_schema(value) -> dict[str, object]`
- `parse_assistant_result(raw, surface_input) -> AssistantResult`
主要 import / dot-source：`__future__`, `collections.abc`, `enum`, `json`, `product.backend.core.errors`, `pydantic`, `re`, `typing`

### `product/backend/workflows/context.py`
- `class ApplicationCore`
主要 import / dot-source：`__future__`, `collections.abc`, `functools`, `os`, `pathlib`, `product.backend.infra.llm.adapters.httpx_transport`, `product.backend.infra.llm.profiles`, `product.backend.infra.recording.request_store`, `product.backend.infra.runtime.jobs.attempts`, `product.backend.infra.runtime.jobs.queue`, `product.backend.infra.runtime.jobs.recording`, `product.backend.infra.runtime.jobs.requests`, `product.backend.infra.runtime.jobs.targets`, `product.backend.infra.runtime.maintenance`, `product.backend.infra.runtime.paths`, `product.backend.infra.runtime.runner.progress`, `product.backend.infra.samples`, `product.backend.infra.secrets`, `product.backend.infra.storage`, `product.backend.workflows.application_understanding.service`, `product.backend.workflows.control`, `product.backend.workflows.official_sample`, `product.backend.workflows.onboarding.workflow`, `product.backend.workflows.permission_intents`, `product.backend.workflows.projects.catalog`, `product.backend.workflows.projects.lifecycle`, `product.backend.workflows.projects.readiness`, `product.backend.workflows.recording.credentials`, `product.backend.workflows.recording.lifecycle`, `product.backend.workflows.recording.project_submission`, `product.backend.workflows.recording.run_service`, `product.backend.workflows.recording.safety_setup`, `product.backend.workflows.recording.submission`, `product.backend.workflows.results.services`, `product.backend.workflows.runs.execution`, `product.backend.workflows.runs.submission`, `product.backend.workflows.security_setup`, `product.backend.workflows.security_setup.local_observer_registry`, `product.backend.workflows.test_identities`, `typing`

### `product/backend/workflows/contracts/analysis.py`
- `_SOURCE_FILE_MAX_BYTES`
- `_DENIED_PATH_MARKERS`
- `class ContractAnalysis`
- `class ContractHistorySource`
- `class ContractHistoryResolution`
主要 import / dot-source：`__future__`, `enum`, `hashlib`, `pathlib`, `product.backend.core.contracts.analysis.assessment`, `product.backend.core.contracts.analysis.canonical`, `product.backend.core.contracts.analysis.diff`, `product.backend.core.contracts.analysis.drift`, `product.backend.core.contracts.analysis.merge`, `product.backend.core.contracts.analysis.models`, `product.backend.core.contracts.analysis.sources.fastapi_ast`, `product.backend.core.contracts.analysis.sources.openapi`, `product.backend.core.contracts.analysis.sources.requirement`, `product.backend.core.contracts.models`, `product.backend.core.errors`, `product.backend.core.identifiers`, `product.backend.core.verification.permissions`, `product.backend.infra.runtime.jobs.requests`, `product.backend.infra.storage`, `product.backend.workflows.contracts.flow_candidates`, `product.backend.workflows.recording.flow_compiler`, `product.protocols.flow_draft`, `product.protocols.recording_flow`, `pydantic`, `typing`

### `product/backend/workflows/contracts/flow_candidates.py`
- `build_flow_candidates(project_id, flow) -> CandidateBatch`
主要 import / dot-source：`__future__`, `product.backend.core.contracts.analysis.canonical`, `product.backend.core.contracts.analysis.models`, `product.backend.core.contracts.models`, `product.protocols.recording_flow`

### `product/backend/workflows/contracts/governance.py`
- `class ContractGovernance`
主要 import / dot-source：`__future__`, `collections.abc`, `product.backend.core.contracts.analysis.assessment`, `product.backend.core.contracts.lifecycle`, `product.backend.core.contracts.models`, `product.backend.core.errors`, `product.backend.core.lifecycle`, `product.backend.core.verification.permissions`, `product.backend.infra.storage`, `time`, `uuid`

### `product/backend/workflows/contracts/http_binding_candidates.py`
- `_HTTP_METHODS`
- `_OPENAPI_MAX_BYTES`
- `_PATH_FIELD`
- `build_recording_http_binding_candidates(flow) -> HttpBindingCandidateBatch`
- `build_openapi_http_binding_candidates(document, source_locator, max_bytes) -> HttpBindingCandidateBatch`
主要 import / dot-source：`__future__`, `collections.abc`, `json`, `product.backend.core.verification.permissions`, `product.protocols.http_binding_candidate`, `product.protocols.recording_flow`, `re`, `typing`

### `product/backend/workflows/contracts/setup_minimizer.py`
- `class SetupMinimizationModel`
- `class SetupMinimizationInvariant`
- `class SetupMinimizationResult`
- `minimize_failure_setup(workflow, case, security_effect_fingerprint, reproduces) -> SetupMinimizationResult`
主要 import / dot-source：`__future__`, `collections.abc`, `product.backend.core.verification.permissions`, `product.backend.core.verification.permissions.coverage`, `product.protocols.web.workflow`, `pydantic`, `typing`

### `product/backend/workflows/contracts/workbench.py`
- `class WorkbenchModel`
- `class CandidateDerivationResult`
- `class ContractWorkbenchSnapshot`
- `class ContractWorkbench`
主要 import / dot-source：`__future__`, `collections.abc`, `product.backend.core.contracts.analysis.canonical`, `product.backend.core.contracts.analysis.drift`, `product.backend.core.contracts.analysis.models`, `product.backend.core.contracts.models`, `product.backend.core.errors`, `product.backend.core.lifecycle`, `product.backend.core.verification.permissions`, `product.backend.infra.storage`, `product.backend.workflows.contracts.analysis`, `product.backend.workflows.contracts.governance`, `product.backend.workflows.projects.catalog`, `pydantic`, `typing`

### `product/backend/workflows/control.py`
- `class ProductFlowQuery`
- `class ProductResultQuery`
- `class ProductProjectSummary`
- `class ProductStepView`
- `class ProductNextAction`
- `class ProductResultSummary`
- `class ProductStatusView`
- `_STEP_DEFINITIONS`
- `class ProductStatusService`
主要 import / dot-source：`__future__`, `collections.abc`, `product.backend.core.errors`, `product.backend.core.lifecycle`, `product.backend.workflows.projects.readiness`, `product.protocols`, `pydantic`, `typing`

### `product/backend/workflows/mcp_access.py`
- `MCP_PAIRING_SECRET_REF`
- `class MCPAccessLevel`
- `_LEVEL_ORDER`
- `class MCPProjectGrant`
- `class MCPAccessView`
- `class MCPAccessCredentialView`
- `class MCPAccessController`
主要 import / dot-source：`__future__`, `collections.abc`, `enum`, `hmac`, `product.backend.core.errors`, `product.backend.infra.secrets`, `pydantic`, `secrets`, `threading`, `time`, `typing`

### `product/backend/workflows/official_sample.py`
- `class OfficialExperienceMode`
- `class OfficialExperienceView`
- `_IDENTITY_MAPPING`
- `class OfficialSampleExperience`
主要 import / dot-source：`__future__`, `dataclasses`, `enum`, `product.backend.core.application_understanding`, `product.backend.core.errors`, `product.backend.core.test_identity`, `product.backend.infra.samples`, `product.backend.infra.secrets`, `product.backend.workflows.application_understanding.service`, `product.backend.workflows.control`, `product.backend.workflows.security_setup.local_observer_registry`, `product.backend.workflows.test_identities`, `pydantic`, `threading`, `time`

### `product/backend/workflows/onboarding/discovery.py`
- `_ALLOWED_NAMES`
- `_AUTH_DEPENDENCY_MARKERS`
- `_SCRIPT_NAME`
- `_IGNORED_DIRECTORY_NAMES`
- `_READ_BUDGET_MESSAGE`
- `is_reparse_point(path) -> bool`
- `canonical_folder(path) -> Path`
- `discover_folder(path, limits) -> DiscoveryResult`
主要 import / dot-source：`__future__`, `json`, `os`, `pathlib`, `product.backend.core.errors`, `product.backend.workflows.onboarding.models`, `re`, `stat`, `tomllib`, `typing`

### `product/backend/workflows/onboarding/folder_picker_process.py`
- `show_directory_dialog(platform_name, tk_module, filedialog_module) -> str`
- `main() -> int`
主要 import / dot-source：`__future__`, `json`, `os`, `product.backend.workflows.onboarding.models`, `typing`

### `product/backend/workflows/onboarding/models.py`
- `class OnboardingModel`
- `class DiscoveryLimits`
- `class DiscoveryCandidate`
- `class DiscoveryHint`
- `class DiscoveryMissingItem`
- `class DiscoveryWarning`
- `class DiscoveryResult`
- `class FolderSelectionResult`
主要 import / dot-source：`__future__`, `pydantic`, `typing`

### `product/backend/workflows/onboarding/workflow.py`
- `class FolderSelector`
- `class SystemFolderSelector`
- `class OnboardingWorkflow`
主要 import / dot-source：`__future__`, `collections.abc`, `json`, `os`, `pathlib`, `product.backend.core.errors`, `product.backend.infra.runtime.paths`, `product.backend.infra.runtime.process.environment`, `product.backend.workflows.onboarding.discovery`, `product.backend.workflows.onboarding.models`, `subprocess`, `threading`, `typing`

### `product/backend/workflows/permission_intents.py`
- `class PermissionIntentViewModel`
- `class PermissionIntentCellStatus`
- `class PermissionIntentCellView`
- `class PermissionIntentActionView`
- `class PermissionIntentMatrixView`
- `class PermissionIntentExecution`
- `class PermissionIntentService`
主要 import / dot-source：`__future__`, `collections.abc`, `enum`, `product.backend.core.application_understanding`, `product.backend.core.errors`, `product.backend.core.permission_intent`, `product.backend.core.test_setup`, `product.backend.core.verification.permissions`, `product.backend.infra.storage`, `product.backend.workflows.recording.safety_setup`, `product.backend.workflows.test_identities`, `pydantic`, `time`

### `product/backend/workflows/projects/catalog.py`
- `class ProjectCatalog`
主要 import / dot-source：`__future__`, `collections.abc`, `pathlib`, `product.backend.core.errors`, `product.backend.core.lifecycle`, `product.backend.infra.storage`, `product.protocols`, `time`

### `product/backend/workflows/projects/lifecycle.py`
- `_ACTIVE_JOB_STATES`
- `_ACTIVE_RUN_STATES`
- `_TERMINAL_RECORDING_STATES`
- `class ProjectLifecycleService`
主要 import / dot-source：`__future__`, `collections.abc`, `product.backend.core.errors`, `product.backend.core.lifecycle`, `product.backend.core.recording`, `product.backend.infra.storage`, `product.backend.workflows.test_identities`, `time`

### `product/backend/workflows/projects/readiness.py`
- `class ReadinessModel`
- `class ActiveTaskView`
- `class ActionPermissionReadinessView`
- `class ProjectReadinessView`
- `class ProjectReadinessService`
主要 import / dot-source：`__future__`, `collections.abc`, `product.backend.core.application_understanding`, `product.backend.core.errors`, `product.backend.core.lifecycle`, `product.backend.core.recording`, `product.backend.infra.storage`, `pydantic`, `typing`

### `product/backend/workflows/recording/__init__.py`
主要 import / dot-source：`.credentials`

### `product/backend/workflows/recording/credentials.py`
- `class RuntimeSecretVault`
- `class RecordingCredentialProvider`
主要 import / dot-source：`__future__`, `collections.abc`, `product.backend.core.errors`, `product.backend.core.test_identity`, `product.backend.infra.secrets`, `product.backend.workflows.test_identities`, `product.protocols`, `threading`

### `product/backend/workflows/recording/flow_compiler.py`
- `_SENSITIVE_FIELD`
- `class FlowDraftCompiler`
- `compile_flow_bindings(flow, profile) -> tuple[WebTargetDefinition, tuple[HttpWorkflowBinding, ...]]`
主要 import / dot-source：`__future__`, `collections.abc`, `product.backend.core.errors`, `product.protocols.flow_draft`, `product.protocols.recording_flow`, `product.protocols.web.profile`, `product.protocols.web.target`, `product.protocols.web.workflow`, `pydantic`, `re`, `typing`, `urllib.parse`

### `product/backend/workflows/recording/lifecycle.py`
- `class RecordingStatusView`
- `class RecordingFinalizationView`
- `class RecordingLifecycle`
主要 import / dot-source：`__future__`, `collections.abc`, `hashlib`, `json`, `os`, `pathlib`, `product.backend.core.errors`, `product.backend.core.lifecycle`, `product.backend.core.recording`, `product.backend.infra.artifacts.run_packages`, `product.backend.infra.recording.control`, `product.backend.infra.runtime.paths`, `product.backend.infra.storage`, `product.backend.workflows.recording.flow_compiler`, `product.backend.workflows.recording.review`, `product.protocols`, `product.protocols.recording_flow`, `pydantic`, `typing`, `uuid`

### `product/backend/workflows/recording/processing.py`
- `_UI_KINDS`
- `_HTTP_METHODS`
- `_SENSITIVE_FIELD`
- `class FlowDraftProcessor`
主要 import / dot-source：`__future__`, `collections.abc`, `dataclasses`, `hashlib`, `json`, `product.backend.core.errors`, `product.backend.core.redaction`, `product.protocols.flow_draft`, `product.protocols.recording`, `product.protocols.web.workflow`, `re`, `typing`, `urllib.parse`

### `product/backend/workflows/recording/project_submission.py`
- `class ProjectRecordingSubmission`
- `class ProjectRecordingService`
主要 import / dot-source：`__future__`, `dataclasses`, `product.backend.core.application_understanding`, `product.backend.core.errors`, `product.backend.core.lifecycle`, `product.backend.workflows.recording.submission`, `product.backend.workflows.test_identities`, `product.protocols`, `time`, `uuid`

### `product/backend/workflows/recording/review.py`
- `class FlowDraftReviewer`
主要 import / dot-source：`__future__`, `collections.abc`, `product.backend.core.errors`, `product.protocols.flow_draft`, `product.protocols.web.workflow`, `pydantic`, `re`, `typing`, `urllib.parse`

### `product/backend/workflows/recording/run_service.py`
- `class RecordingRunService`
主要 import / dot-source：`__future__`, `collections.abc`, `os`, `pathlib`, `product.backend.core.errors`, `product.backend.infra.runtime.jobs.dispatch`, `product.backend.infra.storage`, `product.backend.workflows.recording.submission`, `product.protocols`, `time`

### `product/backend/workflows/recording/safety_candidates.py`
- `_MUTATING_METHODS`
- `_SUCCESS_MIN`
- `_SUCCESS_MAX`
主要 import / dot-source：`__future__`, `collections`, `json`, `product.backend.core.application_understanding`, `product.backend.core.errors`, `product.backend.core.test_setup`, `product.backend.core.verification.permissions`, `product.backend.infra.storage`, `product.protocols`, `product.protocols.recording`, `product.protocols.web.workflow`, `pydantic`, `typing`, `urllib.parse`

### `product/backend/workflows/recording/safety_setup.py`
- `_MUTATING_METHODS`
- `_SUCCESS_MIN`
- `_SUCCESS_MAX`
- `class SafetySetupModel`
- `class TestResourceCandidateView`
- `class ObservationCandidateView`
- `class RecoveryCandidateView`
- `class SecurityEffectCandidateView`
- `class ConfirmActionSafetySetup`
- `class ActionSafetySetupView`
- `class ActionSafetySetupService`
主要 import / dot-source：`.safety_candidates`, `__future__`, `collections.abc`, `dataclasses`, `pathlib`, `product.backend.core.application_understanding`, `product.backend.core.errors`, `product.backend.core.recording`, `product.backend.core.test_setup`, `product.backend.core.verification.permissions`, `product.backend.infra.recording.request_store`, `product.backend.infra.storage`, `product.backend.workflows.recording.lifecycle`, `product.backend.workflows.test_identities`, `product.protocols`, `product.protocols.recording`, `product.protocols.recording_flow`, `pydantic`, `time`, `typing`

### `product/backend/workflows/recording/sanitization.py`
- `_MAX_STRUCTURED_DEPTH`
- `_MAX_CAPTURED_HEADERS`
- `_MAX_CAPTURED_HEADER_VALUE_CHARS`
- `_SENSITIVE_FIELD`
- `class RecordingSanitizer`
主要 import / dot-source：`__future__`, `collections.abc`, `json`, `product.backend.core.redaction`, `product.protocols.recording`, `re`, `typing`, `urllib.parse`

### `product/backend/workflows/recording/submission.py`
- `class RecordingApplicationModel`
- `class SubmitRecording`
- `class RecordingSubmissionResult`
- `class RecordingCompletionResult`
- `recording_target_scope(endpoint) -> WebTargetScope`
- `class RecordingSubmission`
主要 import / dot-source：`__future__`, `collections.abc`, `hashlib`, `product.backend.core.errors`, `product.backend.core.identifiers`, `product.backend.core.lifecycle`, `product.backend.core.recording`, `product.backend.infra.recording.request_store`, `product.backend.infra.runtime.jobs.events`, `product.backend.infra.runtime.jobs.handlers`, `product.backend.infra.runtime.jobs.models`, `product.backend.infra.storage`, `product.backend.workflows.recording.processing`, `product.protocols`, `product.protocols.web.target`, `pydantic`, `typing`, `urllib.parse`, `uuid`

### `product/backend/workflows/results/__init__.py`
主要 import / dot-source：`.history`, `.presentation`

### `product/backend/workflows/results/finalizer.py`
- `class ResultFinalizer`
主要 import / dot-source：`__future__`, `collections.abc`, `contextlib`, `pathlib`, `product.backend.core.errors`, `product.backend.core.lifecycle`, `product.backend.infra.artifacts.run_publication`, `product.backend.infra.runtime.paths`, `product.backend.infra.runtime.process.lock`, `product.backend.infra.storage`, `product.backend.workflows.results.findings`, `product.backend.workflows.results.published`, `time`

### `product/backend/workflows/results/findings.py`
- `_SEVERITY_ORDER`
- `class FindingMaterializer`
- `class FindingQueries`
- `finding_inputs(reader, view) -> tuple[FindingInput, ...]`
主要 import / dot-source：`__future__`, `collections`, `collections.abc`, `hashlib`, `json`, `product.backend.core.errors`, `product.backend.core.lifecycle`, `product.backend.core.verification.findings`, `product.backend.infra.storage`, `product.backend.infra.storage.results.findings`, `product.backend.workflows.results.published`, `product.protocols`, `time`, `typing`

### `product/backend/workflows/results/gating.py`
- `class RegressionGate`
主要 import / dot-source：`__future__`, `collections.abc`, `json`, `product.backend.core.errors`, `product.backend.core.lifecycle`, `product.backend.core.verification.behavior_differential`, `product.backend.core.verification.gating`, `product.backend.core.verification.permissions`, `product.backend.infra.storage.results.gating`, `product.backend.workflows.results.findings`, `product.backend.workflows.results.published`, `product.protocols`, `time`, `typing`

### `product/backend/workflows/results/history.py`
- `class HistoryChangeStatus`
- `class HistoryChange`
- `class HistoryComparison`
- `class HistoryView`
- `class HistoryComparisonBuilder`
- `_STATUS_VIEW`
主要 import / dot-source：`__future__`, `enum`, `product.backend.core.errors`, `product.backend.core.lifecycle`, `product.backend.workflows.results.presentation`, `pydantic`

### `product/backend/workflows/results/presentation.py`
- `class PresentedCaseVerdict`
- `class ResultEvidenceSource`
- `class ResultPresentationIssue`
- `class ResultPresentation`
- `class ResultPresentationBuilder`
- `build_result_presentation(view, snapshot, finding_views) -> ResultPresentation`
- `_ROLE_LABELS`
- `_ACTION_LABELS`
- `_RESOURCE_LABELS`
- `_RELATION_LABELS`
- `_SOURCE_PRESENTATION`
主要 import / dot-source：`__future__`, `enum`, `product.backend.core.errors`, `product.backend.core.lifecycle`, `product.backend.core.verification.facts`, `product.backend.core.verification.trace`, `product.backend.workflows.results.trace`, `product.protocols.observer`, `pydantic`, `typing`

### `product/backend/workflows/results/published.py`
- `class PublishedRunView`
- `class PublishedResultReader`
主要 import / dot-source：`__future__`, `collections.abc`, `dataclasses`, `hashlib`, `json`, `pathlib`, `product.backend.core.errors`, `product.backend.core.lifecycle`, `product.backend.core.redaction`, `product.backend.infra.artifacts.run_packages`, `product.backend.infra.runtime.jobs.requests`, `product.backend.infra.runtime.paths`, `product.backend.infra.storage`, `product.backend.workflows.assistant`, `product.protocols`, `typing`

### `product/backend/workflows/results/reporting.py`
- `class ReportBuilder`
主要 import / dot-source：`__future__`, `collections.abc`, `json`, `pathlib`, `product.backend.core.errors`, `product.backend.core.lifecycle`, `product.backend.core.verification.gating`, `product.backend.infra.artifacts.report_reader`, `product.backend.infra.artifacts.report_store`, `product.backend.infra.storage`, `product.backend.workflows.results.published`, `product.protocols`, `product.protocols.report`, `typing`

### `product/backend/workflows/results/services.py`
- `class ResultServices`
- `build_result_services(var_dir, uow_factory, clock_us) -> ResultServices`
主要 import / dot-source：`__future__`, `dataclasses`, `pathlib`, `product.backend.infra.storage`, `product.backend.workflows.results.finalizer`, `product.backend.workflows.results.findings`, `product.backend.workflows.results.gating`, `product.backend.workflows.results.history`, `product.backend.workflows.results.presentation`, `product.backend.workflows.results.published`, `product.backend.workflows.results.reporting`, `typing`

### `product/backend/workflows/results/trace.py`
- `_SEMANTIC_KEYS`
- `_FIXED_DENY_KEYS`
- `_DOWNSTREAM_KEYS`
- `build_execution_traces(snapshot, evidence_items) -> tuple[ExecutionTrace, ...]`
- `build_execution_trace(snapshot, evidence) -> ExecutionTrace`
主要 import / dot-source：`__future__`, `collections.abc`, `product.backend.core.verification.trace`, `product.protocols.observer`, `pydantic`, `typing`

### `product/backend/workflows/runs/execution.py`
- `class ExecutionWorkflow`
主要 import / dot-source：`__future__`, `collections.abc`, `hashlib`, `pathlib`, `product.backend`, `product.backend.core.contracts.execution_binding`, `product.backend.core.errors`, `product.backend.core.verification.permissions.coverage`, `product.backend.infra.runtime.jobs.dispatch`, `product.backend.infra.runtime.jobs.models`, `product.backend.infra.runtime.jobs.requests`, `product.backend.infra.storage`, `product.backend.workflows.runs.submission`, `product.protocols`, `product.protocols.web.profile`, `time`, `typing`

### `product/backend/workflows/runs/submission.py`
- `class SubmitExecution`
- `class RunSubmission`
主要 import / dot-source：`__future__`, `collections.abc`, `product.backend`, `product.backend.core.errors`, `product.backend.core.identifiers`, `product.backend.core.lifecycle`, `product.backend.infra.runtime.jobs.models`, `product.backend.infra.runtime.jobs.queue`, `product.backend.infra.runtime.jobs.requests`, `product.backend.infra.storage`, `pydantic`, `typing`, `uuid`

### `product/backend/workflows/security_setup/__init__.py`
主要 import / dot-source：`.checks`, `.compiler`

### `product/backend/workflows/security_setup/checks.py`
- `class CheckPreviewGap`
- `class CheckPreviewItem`
- `class CheckPreviewAction`
- `class CheckPreview`
- `class CheckWorkflow`
- `_GAP_PRESENTATION`
主要 import / dot-source：`__future__`, `collections.abc`, `product.backend.core.errors`, `product.backend.core.verification.permissions`, `product.backend.workflows.permission_intents`, `product.backend.workflows.runs.execution`, `product.backend.workflows.security_setup.compiler`, `pydantic`, `typing`

### `product/backend/workflows/security_setup/compiler.py`
- `_CONTRACT_RESOURCE_ID`
- `_ACTOR`
- `_WORKFLOW_STATE`
- `class SecuritySetupCompiler`
主要 import / dot-source：`.contract_builder`, `.profile_builder`, `__future__`, `collections.abc`, `dataclasses`, `hashlib`, `json`, `pathlib`, `product.backend.core.contracts.models`, `product.backend.core.errors`, `product.backend.core.lifecycle`, `product.backend.core.permission_intent`, `product.backend.core.test_identity`, `product.backend.core.test_setup`, `product.backend.core.verification.permissions`, `product.backend.infra.storage`, `product.backend.workflows.contracts.governance`, `product.backend.workflows.permission_intents`, `product.backend.workflows.recording.lifecycle`, `product.backend.workflows.runs.execution`, `product.backend.workflows.security_setup.local_observer_wiring`, `product.backend.workflows.security_setup.models`, `product.backend.workflows.test_identities`, `product.protocols`, `product.protocols.recording_flow`, `product.protocols.web.workflow`, `pydantic`, `re`, `time`, `typing`, `urllib.parse`

### `product/backend/workflows/security_setup/contract_builder.py`
- `_CONTRACT_RESOURCE_ID`
- `_ACTOR`
- `_WORKFLOW_STATE`
- `class ContractBuilderMixin`
主要 import / dot-source：`__future__`, `collections.abc`, `dataclasses`, `hashlib`, `json`, `os`, `pathlib`, `product.backend.core.contracts.models`, `product.backend.core.errors`, `product.backend.core.lifecycle`, `product.backend.core.permission_intent`, `product.backend.core.test_identity`, `product.backend.core.test_setup`, `product.backend.core.verification.permissions`, `product.backend.infra.storage`, `product.backend.workflows.contracts.governance`, `product.backend.workflows.permission_intents`, `product.backend.workflows.recording.lifecycle`, `product.backend.workflows.runs.execution`, `product.backend.workflows.security_setup.local_observer_wiring`, `product.backend.workflows.security_setup.models`, `product.backend.workflows.test_identities`, `product.protocols`, `product.protocols.recording_flow`, `product.protocols.web.workflow`, `pydantic`, `re`, `time`, `typing`, `urllib.parse`

### `product/backend/workflows/security_setup/local_observer_registry.py`
- `_EXPERIENCE_ID`
- `class LocalObserverEnvironment`
- `class LocalObserverEnvironmentRegistry`
主要 import / dot-source：`__future__`, `dataclasses`, `pathlib`, `product.backend.core.errors`, `re`, `threading`, `urllib.parse`

### `product/backend/workflows/security_setup/local_observer_wiring.py`
- `_MAX_DESCRIPTOR_BYTES`
- `_SECRET_REF`
- `_ID`
- `_AZURE_ACCOUNT`
- `class LocalObserverWiring`
- `load_local_observer_wiring(descriptor_path, var_dir, action_id, expected_origin, expected_resource_id) -> LocalObserverWiring | None`
主要 import / dot-source：`__future__`, `dataclasses`, `hashlib`, `json`, `pathlib`, `product.backend.core.errors`, `product.backend.workflows.security_setup.models`, `product.protocols`, `re`, `typing`, `urllib.parse`

### `product/backend/workflows/security_setup/models.py`
- `_CONTRACT_RESOURCE_ID`
- `_ACTOR`
- `_WORKFLOW_STATE`
- `class SecuritySetupCompileResult`
主要 import / dot-source：`__future__`, `collections.abc`, `dataclasses`, `hashlib`, `json`, `os`, `pathlib`, `product.backend.core.contracts.models`, `product.backend.core.errors`, `product.backend.core.lifecycle`, `product.backend.core.permission_intent`, `product.backend.core.test_identity`, `product.backend.core.test_setup`, `product.backend.core.verification.permissions`, `product.backend.infra.storage`, `product.backend.workflows.contracts.governance`, `product.backend.workflows.permission_intents`, `product.backend.workflows.recording.lifecycle`, `product.backend.workflows.runs.execution`, `product.backend.workflows.test_identities`, `product.protocols`, `product.protocols.recording_flow`, `product.protocols.web.workflow`, `pydantic`, `re`, `time`, `typing`, `urllib.parse`

### `product/backend/workflows/security_setup/profile_builder.py`
- `_CONTRACT_RESOURCE_ID`
- `_ACTOR`
- `_WORKFLOW_STATE`
- `class ProfileBuilderMixin`
主要 import / dot-source：`__future__`, `collections.abc`, `dataclasses`, `hashlib`, `json`, `os`, `pathlib`, `product.backend.core.contracts.models`, `product.backend.core.errors`, `product.backend.core.lifecycle`, `product.backend.core.permission_intent`, `product.backend.core.test_identity`, `product.backend.core.test_setup`, `product.backend.core.verification.permissions`, `product.backend.infra.storage`, `product.backend.workflows.contracts.governance`, `product.backend.workflows.permission_intents`, `product.backend.workflows.recording.lifecycle`, `product.backend.workflows.runs.execution`, `product.backend.workflows.security_setup.local_observer_wiring`, `product.backend.workflows.security_setup.models`, `product.backend.workflows.test_identities`, `product.protocols`, `product.protocols.recording_flow`, `product.protocols.web.workflow`, `pydantic`, `re`, `time`, `typing`, `urllib.parse`

### `product/backend/workflows/test_identities/__init__.py`
主要 import / dot-source：`product.backend.workflows.test_identities.execution`, `product.backend.workflows.test_identities.preparation`, `product.backend.workflows.test_identities.service`

### `product/backend/workflows/test_identities/execution.py`
- `_ENVIRONMENT_NAME`
- `class TestIdentityExecutionCredentials`
主要 import / dot-source：`__future__`, `collections.abc`, `product.backend.core.errors`, `product.backend.core.test_identity`, `product.backend.infra.secrets`, `product.backend.workflows.test_identities.service`, `product.protocols`, `re`

### `product/backend/workflows/test_identities/preparation.py`
- `class IdentityPreparationStatus`
- `class IdentityPreparationView`
- `class IdentityPreparationManager`
主要 import / dot-source：`__future__`, `collections.abc`, `dataclasses`, `enum`, `json`, `pathlib`, `product.backend.core.errors`, `product.backend.core.test_identity`, `product.backend.infra.identity.control`, `product.backend.infra.runtime.paths`, `product.backend.infra.runtime.process.environment`, `product.backend.infra.runtime.process.tree`, `product.backend.infra.secrets`, `product.backend.workflows.test_identities.service`, `product.protocols`, `product.protocols.web.target`, `pydantic`, `shutil`, `subprocess`, `threading`, `time`, `urllib.parse`, `uuid`

### `product/backend/workflows/test_identities/service.py`
- `class TestIdentityStatus`
- `class PreparedLoginState`
- `class TestIdentityView`
- `class TestIdentityService`
主要 import / dot-source：`__future__`, `collections.abc`, `enum`, `product.backend.core.application_understanding`, `product.backend.core.errors`, `product.backend.core.identifiers`, `product.backend.core.test_identity`, `product.backend.infra.secrets.store`, `product.backend.infra.storage`, `pydantic`, `time`, `uuid`

### `product/backend/workflows/worker_container.py`
- `class WorkerContainer`
主要 import / dot-source：`__future__`, `collections.abc`, `functools`, `os`, `pathlib`, `product.backend.infra.artifacts.run_publication`, `product.backend.infra.runtime.jobs.attempts`, `product.backend.infra.runtime.jobs.factory`, `product.backend.infra.runtime.jobs.queue`, `product.backend.infra.runtime.jobs.reconciliation`, `product.backend.infra.runtime.jobs.recording`, `product.backend.infra.runtime.jobs.requests`, `product.backend.infra.runtime.jobs.targets`, `product.backend.infra.runtime.paths`, `product.backend.infra.storage`, `product.backend.workflows.results.services`

<!-- GENERATED:END -->
