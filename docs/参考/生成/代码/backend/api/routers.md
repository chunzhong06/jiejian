# 自动代码参考：backend/api/routers

> 自动生成。当前源码结构与注册投影，不代表运行验收或完整调用图。

<!-- GENERATED:START -->

### `product/backend/api/routers/__init__.py`

[打开源码](../../../../../../product/backend/api/routers/__init__.py) · Python AST；作用域内import不表示每次调用均执行。


### `product/backend/api/routers/applications/__init__.py`

[打开源码](../../../../../../product/backend/api/routers/applications/__init__.py) · Python AST；作用域内import不表示每次调用均执行。


### `product/backend/api/routers/applications/current_experience.py`

[打开源码](../../../../../../product/backend/api/routers/applications/current_experience.py) · Python AST；作用域内import不表示每次调用均执行。

- `build_current_experience_router() -> APIRouter`

静态import / dot-source：`__future__`、`fastapi`、`product.backend.api.envelope`

### `product/backend/api/routers/applications/experience.py`

[打开源码](../../../../../../product/backend/api/routers/applications/experience.py) · Python AST；作用域内import不表示每次调用均执行。

- `build_experience_router(context) -> APIRouter`
- `class OfficialSampleStartRequest`
- `class OfficialSampleStopRequest`
- `class OfficialSampleVersionRequest`
- `class OfficialObservationRequest`

静态import / dot-source：`__future__`、`fastapi`、`product.backend.api.envelope`、`product.backend.composition`、`product.backend.core.checks.repair`、`product.backend.workflows.examples.environment`、`typing`

### `product/backend/api/routers/applications/onboarding.py`

[打开源码](../../../../../../product/backend/api/routers/applications/onboarding.py) · Python AST；作用域内import不表示每次调用均执行。

- `class OnboardingInspectRequest`
- `build_onboarding_router(context) -> APIRouter`

静态import / dot-source：`__future__`、`fastapi`、`product.backend.api.envelope`、`product.backend.composition`、`pydantic`、`typing`

### `product/backend/api/routers/applications/projects.py`

[打开源码](../../../../../../product/backend/api/routers/applications/projects.py) · Python AST；作用域内import不表示每次调用均执行。

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

静态import / dot-source：`__future__`、`fastapi`、`product.backend.api.envelope`、`product.backend.composition`、`product.backend.core.applications.models`、`pydantic`、`typing`

### `product/backend/api/routers/boundaries/__init__.py`

[打开源码](../../../../../../product/backend/api/routers/boundaries/__init__.py) · Python AST；作用域内import不表示每次调用均执行。


### `product/backend/api/routers/boundaries/business_boundaries.py`

[打开源码](../../../../../../product/backend/api/routers/boundaries/business_boundaries.py) · Python AST；作用域内import不表示每次调用均执行。

- `class BoundaryProposalCreateRequest`
- `BoundaryProposalCreateRequest.to_command(self) -> BoundaryProposalCommand`
- `class BoundaryDecisionRequest`
- `class RuleCandidateSaveRequest`
- `RuleCandidateSaveRequest.to_command(self) -> RuleCandidateSave`
- `class RuleCandidateProposalRequest`
- `class BoundaryMaintenanceCreateRequest`
- `BoundaryMaintenanceCreateRequest.to_command(self) -> BoundaryMaintenanceCommand`
- `build_business_boundaries_router(context) -> APIRouter`

静态import / dot-source：`__future__`、`fastapi`、`fastapi.encoders`、`json`、`product.backend.api.envelope`、`product.backend.composition`、`product.backend.core.boundaries.proposals`、`product.backend.core.boundaries.rule_candidates`、`product.backend.workflows.business_boundaries`、`pydantic`、`typing`

### `product/backend/api/routers/boundaries/permission_drafts.py`

[打开源码](../../../../../../product/backend/api/routers/boundaries/permission_drafts.py) · Python AST；作用域内import不表示每次调用均执行。

- `class PermissionDraftRequest`
- `build_permission_drafts_router(context) -> APIRouter`

静态import / dot-source：`fastapi`、`product.backend.api.envelope`、`pydantic`、`typing`

### `product/backend/api/routers/boundaries/permission_intents.py`

[打开源码](../../../../../../product/backend/api/routers/boundaries/permission_intents.py) · Python AST；作用域内import不表示每次调用均执行。

- `class PermissionIntentCellTarget`
- `class PermissionIntentApprovalRequest`
- `PermissionIntentApprovalRequest.validate_reason(cls, value) -> str &#124; None`
- `class PermissionIntentProposalApprovalRequest`
- `PermissionIntentProposalApprovalRequest.validate_reason(cls, value) -> str &#124; None`
- `class PermissionIntentProposalDecisionRequest`
- `class PermissionDraftRequest`
- `PermissionDraftRequest.validate_text(cls, value) -> str`
- `build_permission_intents_router(context) -> APIRouter`

静态import / dot-source：`__future__`、`fastapi`、`product.backend.api.envelope`、`product.backend.composition`、`product.backend.core.boundaries.permissions`、`product.backend.core.verification.permissions`、`pydantic`、`typing`

### `product/backend/api/routers/changes/__init__.py`

[打开源码](../../../../../../product/backend/api/routers/changes/__init__.py) · Python AST；作用域内import不表示每次调用均执行。


### `product/backend/api/routers/changes/development.py`

[打开源码](../../../../../../product/backend/api/routers/changes/development.py) · Python AST；作用域内import不表示每次调用均执行。

- `class TaskCreateRequest`
- `class TaskReviseRequest`
- `class TaskFinishRequest`
- `class RuntimeLoadRequest`
- `build_development_router(context)`

静态import / dot-source：`fastapi`、`product.backend.api.envelope`、`product.backend.core.development`、`pydantic`、`typing`

### `product/backend/api/routers/changes/source_changes.py`

[打开源码](../../../../../../product/backend/api/routers/changes/source_changes.py) · Python AST；作用域内import不表示每次调用均执行。

- `class SourceChangeCreateRequest`
- `class SourceChangeRegistrationRequest`
- `build_source_changes_router(context) -> APIRouter`

静态import / dot-source：`__future__`、`fastapi`、`product.backend.api.envelope`、`product.backend.composition`、`product.backend.core.checks.repair`、`product.backend.core.development`、`product.backend.core.errors`、`product.protocols.checks.execution_request`、`pydantic`、`typing`

### `product/backend/api/routers/checks/__init__.py`

[打开源码](../../../../../../product/backend/api/routers/checks/__init__.py) · Python AST；作用域内import不表示每次调用均执行。


### `product/backend/api/routers/checks/checks.py`

[打开源码](../../../../../../product/backend/api/routers/checks/checks.py) · Python AST；作用域内import不表示每次调用均执行。

- `build_checks_router(context) -> APIRouter`

静态import / dot-source：`fastapi`、`product.backend.api.envelope`、`product.backend.composition`

### `product/backend/api/routers/checks/gating.py`

[打开源码](../../../../../../product/backend/api/routers/checks/gating.py) · Python AST；作用域内import不表示每次调用均执行。

- `build_gating_router(context) -> APIRouter`
- `class BaselineAcceptRequest`
- `BaselineAcceptRequest.require_text(cls, value) -> str`
- `class GateEvaluateRequest`

静态import / dot-source：`__future__`、`fastapi`、`product.backend.api.envelope`、`product.backend.composition`、`pydantic`、`typing`、`作用域内：product.backend.core.verification.gating`

### `product/backend/api/routers/checks/jobs.py`

[打开源码](../../../../../../product/backend/api/routers/checks/jobs.py) · Python AST；作用域内import不表示每次调用均执行。

- `build_jobs_router(context) -> APIRouter`

静态import / dot-source：`__future__`、`asyncio`、`collections.abc`、`fastapi`、`fastapi.responses`、`json`、`product.backend.api.envelope`、`product.backend.composition`、`product.backend.core.errors`、`product.backend.core.lifecycle`、`product.backend.core.redaction`、`product.backend.infra.runtime.jobs.models`、`time`

### `product/backend/api/routers/checks/results.py`

[打开源码](../../../../../../product/backend/api/routers/checks/results.py) · Python AST；作用域内import不表示每次调用均执行。

- `build_results_router(context) -> APIRouter`

静态import / dot-source：`fastapi`、`product.backend.api.envelope`、`product.backend.composition`

### `product/backend/api/routers/checks/runs.py`

[打开源码](../../../../../../product/backend/api/routers/checks/runs.py) · Python AST；作用域内import不表示每次调用均执行。

- `class RunCreateRequest`
- `build_runs_router(context) -> APIRouter`

静态import / dot-source：`__future__`、`fastapi`、`product.backend.api.envelope`、`product.backend.composition`、`product.backend.core.identifiers`、`product.backend.core.lifecycle`、`pydantic`、`typing`

### `product/backend/api/routers/preparation/__init__.py`

[打开源码](../../../../../../product/backend/api/routers/preparation/__init__.py) · Python AST；作用域内import不表示每次调用均执行。


### `product/backend/api/routers/preparation/preparation.py`

[打开源码](../../../../../../product/backend/api/routers/preparation/preparation.py) · Python AST；作用域内import不表示每次调用均执行。

- `class AllowControlSelectionRequest`
- `build_preparation_router(context) -> APIRouter`

静态import / dot-source：`fastapi`、`product.backend.api.envelope`、`product.backend.core.preparation.requirements`、`product.backend.workflows.preparation.materials.models`、`pydantic`、`typing`、`作用域内：product.backend.api.routers.preparation.proof_sources`

### `product/backend/api/routers/preparation/proof_sources.py`

[打开源码](../../../../../../product/backend/api/routers/preparation/proof_sources.py) · Python AST；作用域内import不表示每次调用均执行。

- `require_local_proof_session(request)`
- `build_proof_sources_router(context)`

静态import / dot-source：`fastapi`、`product.backend.api.envelope`、`product.backend.workflows.preparation.proofs.commands`、`typing`

### `product/backend/api/routers/preparation/recordings.py`

[打开源码](../../../../../../product/backend/api/routers/preparation/recordings.py) · Python AST；作用域内import不表示每次调用均执行。

- `build_recordings_router(context) -> APIRouter`
- `class RecordingCreateRequest`
- `RecordingCreateRequest.validate_purpose(self)`
- `class ReviewRequest`
- `class FinalizeRequest`

静态import / dot-source：`__future__`、`fastapi`、`json`、`product.backend.api.envelope`、`product.backend.composition`、`product.backend.core.boundaries.entities`、`product.backend.core.errors`、`product.backend.core.lifecycle`、`product.backend.core.recording.models`、`product.backend.infra.runtime.jobs.models`、`product.backend.workflows.test_identities`、`product.protocols`、`pydantic`、`time`、`typing`

### `product/backend/api/routers/preparation/supplemental_materials.py`

[打开源码](../../../../../../product/backend/api/routers/preparation/supplemental_materials.py) · Python AST；作用域内import不表示每次调用均执行。

- `class MaterialPreviewRequest`
- `class MaterialCreateRequest`
- `class MaterialWithdrawRequest`
- `class MaterialRevisionRequest`
- `build_supplemental_material_router(context)`

静态import / dot-source：`fastapi`、`product.backend.api.envelope`、`product.backend.workflows.preparation.supplemental.contract`、`pydantic`

### `product/backend/api/routers/preparation/test_identities.py`

[打开源码](../../../../../../product/backend/api/routers/preparation/test_identities.py) · Python AST；作用域内import不表示每次调用均执行。

- `class TestIdentityCreateRequest`
- `class TestIdentityResetRequest`
- `build_test_identities_router(context) -> APIRouter`

静态import / dot-source：`__future__`、`fastapi`、`product.backend.api.envelope`、`product.backend.composition`、`pydantic`、`typing`

### `product/backend/api/routers/system/__init__.py`

[打开源码](../../../../../../product/backend/api/routers/system/__init__.py) · Python AST；作用域内import不表示每次调用均执行。


### `product/backend/api/routers/system/assistant.py`

[打开源码](../../../../../../product/backend/api/routers/system/assistant.py) · Python AST；作用域内import不表示每次调用均执行。

- `class ProjectAssistantSurface`
- `_PROJECT_TEMPLATE`
- `class AssistantGenerateRequest`
- `class AssistantFocus`
- `build_assistant_router(context) -> APIRouter`

静态import / dot-source：`__future__`、`enum`、`fastapi`、`product.backend.api.envelope`、`product.backend.core.boundaries.entities`、`product.backend.core.identifiers`、`product.backend.workflows.assistant.templates`、`pydantic`、`typing`

### `product/backend/api/routers/system/llm.py`

[打开源码](../../../../../../product/backend/api/routers/system/llm.py) · Python AST；作用域内import不表示每次调用均执行。

- `build_llm_router(context) -> APIRouter`
- `class LLMSettingsRequest`
- `class LLMModelDiscoverRequest`
- `LLMModelDiscoverRequest.parse_provider(cls, value) -> LLMProviderType`
- `LLMModelDiscoverRequest.validate_provider_base(self) -> LLMModelDiscoverRequest`
- `class LLMProfileBase`
- `LLMProfileBase.parse_provider(cls, value) -> LLMProviderType`
- `LLMProfileBase.validate_base_url(cls, value, info) -> str &#124; None`
- `LLMProfileBase.validate_secret_reference(cls, value) -> str &#124; None`
- `LLMProfileBase.validate_formal_provider_base(self) -> LLMProfileBase`
- `class LLMProfileCreateRequest`
- `LLMProfileCreateRequest.validate_secret_input(self) -> LLMProfileCreateRequest`
- `class LLMProfileUpdateRequest`
- `LLMProfileUpdateRequest.validate_secret_input(self) -> LLMProfileUpdateRequest`
- `LLMProfileUpdateRequest.validate_base_url_syntax(cls, value) -> str &#124; None`
- `LLMProfileUpdateRequest.validate_secret_reference(cls, value) -> str &#124; None`
- `class LLMDefaultProfileRequest`

静态import / dot-source：`__future__`、`fastapi`、`product.backend.api.envelope`、`product.backend.composition`、`product.backend.infra.llm.catalog`、`product.backend.infra.llm.config`、`pydantic`、`typing`

### `product/backend/api/routers/system/mcp_access.py`

[打开源码](../../../../../../product/backend/api/routers/system/mcp_access.py) · Python AST；作用域内import不表示每次调用均执行。

- `class MCPProjectGrantRequest`
- `build_mcp_access_router(context, access) -> APIRouter`

静态import / dot-source：`__future__`、`fastapi`、`product.backend.api.envelope`、`product.backend.composition`、`product.backend.workflows.agent_access.service`、`typing`

### `product/backend/api/routers/system/system.py`

[打开源码](../../../../../../product/backend/api/routers/system/system.py) · Python AST；作用域内import不表示每次调用均执行。

- `build_system_router(context, shutdown_callback) -> APIRouter`
- `class HealthResponse`
- `class ReadyResponse`
- `class MaintenanceOperationRequest`

静态import / dot-source：`__future__`、`fastapi`、`fastapi.responses`、`product.backend`、`product.backend.api.envelope`、`product.backend.composition`、`product.backend.core.errors`、`product.backend.infra.runtime.diagnostics`、`product.backend.infra.runtime.frontend_assets`、`product.backend.infra.storage`、`typing`

### `product/backend/api/routers/workspace.py`

[打开源码](../../../../../../product/backend/api/routers/workspace.py) · Python AST；作用域内import不表示每次调用均执行。

- `build_workspace_router(context) -> APIRouter`

静态import / dot-source：`fastapi`、`product.backend.api.envelope`、`product.backend.composition`

<!-- GENERATED:END -->
