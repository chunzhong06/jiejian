# 自动代码参考：后端 Workflows

> 生成区域只描述当前代码结构；职责与安全理由由能力映射和任务指南维护。

<!-- GENERATED:START -->

<!-- 此区域由 scripts/docs/generate.py 从 product/backend/workflows/ 读取。 -->

### `product/backend/workflows/agent_access/service.py`
- `MCP_PAIRING_SECRET_REF`
- `class MCPAccessLevel`
- `class MCPConnectionState`
- `_LEVEL_ORDER`
- `class MCPProjectGrant`
- `class MCPAccessView`
- `class MCPAccessCredentialView`
- `class MCPAccessController`
主要 import / dot-source：`__future__`, `collections.abc`, `enum`, `hmac`, `product.backend.core.errors`, `product.backend.infra.secrets`, `pydantic`, `secrets`, `threading`, `time`, `typing`

### `product/backend/workflows/application_understanding/analysis/__init__.py`
主要 import / dot-source：`.analyzer`, `.models`

### `product/backend/workflows/application_understanding/analysis/analyzer.py`
- `class ApplicationUnderstandingAnalyzer`
主要 import / dot-source：`.javascript`, `.models`, `.openapi`, `.python`, `__future__`, `collections.abc`, `hashlib`, `os`, `pathlib`, `product.backend.core.applications.models`, `product.backend.core.changes.models`, `product.backend.core.errors`, `product.backend.workflows.onboarding.discovery`, `re`

### `product/backend/workflows/application_understanding/analysis/javascript.py`
- `class JavaScriptAnalysisMixin`
主要 import / dot-source：`.models`, `__future__`, `product.backend.core.applications.models`, `product.backend.core.http_routes`

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
主要 import / dot-source：`__future__`, `ast`, `collections.abc`, `hashlib`, `json`, `os`, `pathlib`, `product.backend.core.applications.models`, `product.backend.core.changes.models`, `product.backend.core.errors`, `product.backend.core.http_routes`, `product.backend.workflows.onboarding.discovery`, `pydantic`, `re`, `yaml`

### `product/backend/workflows/application_understanding/analysis/openapi.py`
- `class OpenApiAnalysisMixin`
主要 import / dot-source：`.models`, `__future__`, `collections.abc`, `json`, `product.backend.core.applications.models`, `product.backend.core.http_routes`, `product.backend.workflows.onboarding.discovery`, `yaml`

### `product/backend/workflows/application_understanding/analysis/python.py`
- `class PythonAnalysisMixin`
主要 import / dot-source：`.models`, `__future__`, `ast`, `product.backend.core.applications.models`, `product.backend.core.http_routes`

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
主要 import / dot-source：`__future__`, `collections.abc`, `hashlib`, `os`, `pathlib`, `product.backend.core.applications.models`, `product.backend.core.changes.models`, `product.backend.core.errors`, `product.backend.core.lifecycle`, `product.backend.infra.storage`, `product.backend.workflows.application_understanding.analysis.analyzer`, `product.backend.workflows.application_understanding.endpoints`, `product.backend.workflows.onboarding.discovery`, `product.backend.workflows.onboarding.models`, `product.protocols`, `pydantic`, `re`, `time`, `typing`

### `product/backend/workflows/assistant/__init__.py`
主要 import / dot-source：`product.backend.workflows.assistant.diagnosis`, `product.backend.workflows.assistant.templates`

### `product/backend/workflows/assistant/cache.py`
- `class AssistantCache`
主要 import / dot-source：`__future__`, `hashlib`, `json`, `os`, `pathlib`, `product.backend.core.errors`, `product.backend.workflows.assistant.templates`, `tempfile`, `typing`

### `product/backend/workflows/assistant/current_surfaces.py`
- `CURRENT_ASSISTANT_TEMPLATES`
- `class PreparationAssistantSurfaceResolver`
主要 import / dot-source：`__future__`, `collections`, `product.backend.core.applications.models`, `product.backend.core.boundaries.entities`, `product.backend.core.errors`, `product.backend.core.identifiers`, `product.backend.core.recording.models`, `product.backend.workflows.assistant.surfaces`, `product.backend.workflows.assistant.templates`, `product.backend.workflows.preparation.models`, `product.backend.workflows.recording.source`, `re`, `urllib.parse`

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

### `product/backend/workflows/assistant/service.py`
- `class AssistantStatus`
- `class AssistantSurfaceView`
- `class AssistantService`
主要 import / dot-source：`__future__`, `collections.abc`, `enum`, `product.backend.core.errors`, `product.backend.infra.llm.adapters.base`, `product.backend.infra.llm.profiles`, `product.backend.workflows.assistant.cache`, `product.backend.workflows.assistant.surfaces`, `product.backend.workflows.assistant.templates`, `pydantic`, `re`, `threading`, `time`

### `product/backend/workflows/assistant/surfaces.py`
- `class ResolvedAssistantSurface`
- `class AssistantSurfaceResolver`
主要 import / dot-source：`.templates`, `__future__`, `collections.abc`, `dataclasses`, `typing`

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

### `product/backend/workflows/business_boundaries/__init__.py`
主要 import / dot-source：`.models`, `.service`

### `product/backend/workflows/business_boundaries/candidates/drafting.py`
- `_OPTION_ID_PATTERN`
- `_MAX_OPTIONS`
- `_MAX_SUGGESTIONS`
- `_MAX_QUOTE_CHARS`
- `class PermissionDraftStatus`
- `class PermissionDraftSuggestionView`
- `class PermissionDraftIssueView`
- `class PermissionDraftView`
- `class PermissionDraftService`
主要 import / dot-source：`__future__`, `dataclasses`, `enum`, `json`, `product.backend.core.boundaries.entities`, `product.backend.core.boundaries.permissions`, `product.backend.core.boundaries.semantics`, `product.backend.core.errors`, `product.backend.infra.llm.adapters.base`, `pydantic`, `re`, `unicodedata`, `uuid`

### `product/backend/workflows/business_boundaries/candidates/rule_candidates.py`
- `class RuleCandidateService`
主要 import / dot-source：`__future__`, `json`, `product.backend.core.boundaries.entities`, `product.backend.core.boundaries.rule_candidates`, `product.backend.core.errors`, `product.backend.workflows.business_boundaries.models`, `pydantic`, `time`, `uuid`

### `product/backend/workflows/business_boundaries/fingerprints.py`
- `candidate_source_snapshot(kind, candidate) -> CandidateSourceSnapshot`
- `legacy_candidate_source_snapshot(kind, candidate) -> CandidateSourceSnapshot`
- `implementation_candidate_snapshot(source) -> ImplementationCandidateSnapshot`
主要 import / dot-source：`__future__`, `product.backend.core.applications.models`, `product.backend.core.boundaries.entities`, `product.backend.core.boundaries.proposals`

### `product/backend/workflows/business_boundaries/inspection.py`
- `class ActorImplementationInspection`
- `class ActionImplementationInspection`
- `inspect_actor_binding(actor_id, actor_revision, binding, understanding) -> ActorImplementationInspection`
- `inspect_action_binding(action_id, action_revision, binding, understanding) -> ActionImplementationInspection`
主要 import / dot-source：`__future__`, `product.backend.core.applications.models`, `product.backend.core.boundaries.entities`, `product.backend.core.boundaries.proposals`, `product.backend.core.identifiers`, `product.backend.workflows.business_boundaries.fingerprints`, `pydantic`, `typing`

### `product/backend/workflows/business_boundaries/models.py`
- `class BoundaryWorkflowModel`
- `class BoundaryProposalCommand`
- `class BoundaryDraftCandidate`
- `class BoundaryDraftView`
- `class BoundaryMaintenanceCandidateOption`
- `class BoundaryMaintenanceActorItem`
- `class BoundaryMaintenanceActionItem`
- `class BoundaryMaintenancePermissionItem`
- `class BoundaryMaintenanceCommand`
- `class BoundaryMaintenanceDraftView`
- `class BoundaryProposalChangeSummary`
- `class BoundaryReviewEffect`
- `class BoundaryReviewValue`
- `class BoundaryReviewItem`
- `class BoundaryProposalReview`
- `class BoundaryProposalView`
- `class BoundaryProposalListView`
- `class OfficialBoundaryActorSummary`
- `class OfficialBoundaryEffectSummary`
- `class OfficialBoundaryActionSummary`
- `class OfficialBoundaryPermissionSummary`
- `class OfficialBoundaryRecipe`
- `class PermissionBoundaryStatus`
- `class BusinessBoundaryView`
- `class BoundaryPendingProposal`
- `class BoundaryEditorView`
主要 import / dot-source：`__future__`, `product.backend.core.boundaries.entities`, `product.backend.core.boundaries.permissions`, `product.backend.core.boundaries.proposals`, `product.backend.core.boundaries.semantics`, `product.backend.core.identifiers`, `product.backend.workflows.business_boundaries.inspection`, `pydantic`, `typing`

### `product/backend/workflows/business_boundaries/proposals/maintenance.py`
- `boundary_state_fingerprint(project_id, actors, actions, permissions, policy_epoch) -> str`
- `build_maintenance_draft(project_id, actor_roots, action_roots, actors, actions, permissions, actor_inspections, action_inspections, understanding, policy_epoch) -> BoundaryMaintenanceDraftView`
- `maintenance_to_proposal_command(project_id, command, actor_roots, action_roots, actors, actions, permissions, policy_epoch) -> BoundaryProposalCommand`
- `proposal_change_summary(proposal, permissions, actor_bindings, action_bindings) -> BoundaryProposalChangeSummary`
主要 import / dot-source：`__future__`, `product.backend.core.applications.models`, `product.backend.core.boundaries.entities`, `product.backend.core.boundaries.permissions`, `product.backend.core.boundaries.proposals`, `product.backend.core.errors`, `product.backend.workflows.business_boundaries.inspection`, `product.backend.workflows.business_boundaries.models`

### `product/backend/workflows/business_boundaries/proposals/official_recipe.py`
- `OFFICIAL_BOUNDARY_PROVENANCE`
- `_OWNER`
- `_MEMBER`
- `_EXPORT`
- `_VIEW`
- `_EXPORT_EFFECT`
- `_VIEW_EFFECT`
- `official_boundary_recipe() -> OfficialBoundaryRecipe`
主要 import / dot-source：`__future__`, `product.backend.core.boundaries.entities`, `product.backend.core.boundaries.permissions`, `product.backend.core.boundaries.proposals`, `product.backend.core.boundaries.semantics`, `product.backend.workflows.business_boundaries.models`

### `product/backend/workflows/business_boundaries/proposals/planning.py`
主要 import / dot-source：`__future__`, `dataclasses`, `product.backend.core.applications.models`, `product.backend.core.boundaries.approval`, `product.backend.core.boundaries.entities`, `product.backend.core.boundaries.permissions`, `product.backend.core.boundaries.proposals`, `product.backend.core.errors`, `product.backend.infra.storage`, `product.backend.workflows.business_boundaries.proposals`, `uuid`

### `product/backend/workflows/business_boundaries/proposals/review.py`
- `proposal_review(work, proposal) -> BoundaryProposalReview`
主要 import / dot-source：`__future__`, `product.backend.core.boundaries.proposals`, `product.backend.infra.storage`, `product.backend.workflows.business_boundaries.models`

### `product/backend/workflows/business_boundaries/proposals/sources.py`
主要 import / dot-source：`__future__`, `product.backend.core.applications.models`, `product.backend.core.boundaries.entities`, `product.backend.core.boundaries.proposals`, `product.backend.core.errors`, `product.backend.workflows.business_boundaries.fingerprints`, `product.backend.workflows.business_boundaries.models`, `product.backend.workflows.business_boundaries.proposals`

### `product/backend/workflows/business_boundaries/proposals/validation.py`
主要 import / dot-source：`__future__`, `product.backend.core.applications.models`, `product.backend.core.boundaries.entities`, `product.backend.core.boundaries.proposals`, `product.backend.core.errors`, `product.backend.infra.storage`

### `product/backend/workflows/business_boundaries/reading/permissions.py`
- `class PermissionIntentViewModel`
- `class PermissionIntentCellStatus`
- `class PermissionIntentCellView`
- `class PermissionIntentActionView`
- `class PermissionIntentMatrixView`
- `class PermissionIntentHistoryView`
- `class PermissionIntentService`
主要 import / dot-source：`__future__`, `collections.abc`, `enum`, `product.backend.core.boundaries.permissions`, `product.backend.core.errors`, `product.backend.infra.storage`, `pydantic`

### `product/backend/workflows/business_boundaries/reading/queries.py`
- `current_permission_intents(latest, actors, actions) -> tuple[tuple[PermissionIntentRevision, ...], tuple[PermissionIntentRevision, ...]]`
主要 import / dot-source：`__future__`, `dataclasses`, `product.backend.core.applications.models`, `product.backend.core.boundaries.entities`, `product.backend.core.boundaries.permissions`, `product.backend.core.boundaries.proposals`, `product.backend.core.errors`, `product.backend.core.preparation.requirements`, `product.backend.infra.storage`, `product.backend.workflows.business_boundaries.inspection`, `product.backend.workflows.business_boundaries.models`, `product.backend.workflows.business_boundaries.proposals`, `product.backend.workflows.business_boundaries.proposals.maintenance`, `product.backend.workflows.business_boundaries.proposals.review`

### `product/backend/workflows/business_boundaries/reading/rule_details.py`
- `class BusinessRuleDetails`
主要 import / dot-source：`product.backend.core.errors`

### `product/backend/workflows/business_boundaries/service.py`
- `class BusinessBoundaryService`
主要 import / dot-source：`__future__`, `collections.abc`, `contextlib`, `product.backend.core.applications.models`, `product.backend.core.boundaries.approval`, `product.backend.core.boundaries.entities`, `product.backend.core.boundaries.permissions`, `product.backend.core.boundaries.proposals`, `product.backend.core.errors`, `product.backend.infra.storage`, `product.backend.workflows.business_boundaries.inspection`, `product.backend.workflows.business_boundaries.models`, `product.backend.workflows.business_boundaries.proposals`, `product.backend.workflows.business_boundaries.proposals.maintenance`, `product.backend.workflows.business_boundaries.reading`, `time`, `uuid`

### `product/backend/workflows/changes/__init__.py`
主要 import / dot-source：`.service`

### `product/backend/workflows/changes/identity.py`
- `class SourceIdentityRecord`
- `class SourceIdentityComparison`
- `class SourceIdentityReader`
主要 import / dot-source：`__future__`, `product.backend.core.errors`, `product.backend.infra.source_identity`, `product.protocols.checks.execution_request`, `pydantic`, `time`, `typing`

### `product/backend/workflows/changes/observations.py`
- `class CodeObservationService`
主要 import / dot-source：`__future__`, `product.backend.core.errors`, `product.backend.infra.source_identity`, `time`, `uuid`

### `product/backend/workflows/changes/service.py`
- `class SourceRevalidationInspection`
- `class CurrentChangeView`
- `permission_refs(boundary)`
- `class PreparedSourceChange`
- `class CurrentSourceChangeService`
主要 import / dot-source：`__future__`, `collections.abc`, `dataclasses`, `product.backend.core.changes.models`, `product.backend.core.checks.plan`, `product.backend.core.checks.repair`, `product.backend.core.errors`, `product.protocols.checks.execution_request`, `pydantic`, `time`, `typing`, `uuid`

### `product/backend/workflows/checks/local_observer_wiring.py`
- `_MAX_DESCRIPTOR_BYTES`
- `_SECRET_REF`
- `_ID`
- `_AZURE_ACCOUNT`
- `class LocalObserverWiring`
- `load_local_observer_wiring(descriptor_path, var_dir, action_id, expected_origin, expected_resource_id, resource_mismatch_is_disabled) -> LocalObserverWiring | None`
主要 import / dot-source：`__future__`, `dataclasses`, `hashlib`, `json`, `pathlib`, `product.backend.core.errors`, `product.protocols`, `re`, `typing`, `urllib.parse`

### `product/backend/workflows/checks/reading/observation_reading.py`
- `class ObservationReading`
- `observation_reading(item, source_type) -> ObservationReading`
主要 import / dot-source：`__future__`, `product.protocols.checks.check_result`, `product.protocols.checks.execution_request`, `typing`

### `product/backend/workflows/checks/reading/results.py`
- `class CheckRunView`
- `class CheckJobView`
- `class CheckProgressCaseView`
- `class CheckProgressView`
- `class CheckRunStatus`
- `class CheckHistoryCursor`
- `class CheckHistoryItem`
- `class CheckHistoryPage`
- `class CheckResultReader`
主要 import / dot-source：`__future__`, `hashlib`, `product.backend.core.errors`, `product.backend.core.identifiers`, `product.backend.core.lifecycle`, `product.backend.infra.artifacts.checks.check_packages`, `product.backend.infra.artifacts.checks.check_validation`, `product.backend.infra.runtime.jobs.requests.checks`, `product.backend.infra.runtime.paths`, `product.protocols.checks.check_result`, `product.protocols.checks.execution_request`, `pydantic`, `typing`

### `product/backend/workflows/checks/reading/story.py`
- `class StoryIdentity`
- `class StoryEffect`
- `class StoryControl`
- `class FactComparison`
- `class EvidenceExplanation`
- `class StoryTraceEvent`
- `class StoryExecutionPath`
- `class StoryProofCoverage`
- `class ActionResultStory`
- `class ResultStory`
- `class CheckStoryBuilder`
主要 import / dot-source：`__future__`, `product.backend.core.checks.repair`, `product.backend.core.lifecycle`, `product.backend.core.verification.breakpoints`, `product.backend.core.verification.checks`, `product.backend.core.verification.trace`, `product.backend.workflows.checks.reading.observation_reading`, `product.backend.workflows.checks.reading.story_text`, `product.backend.workflows.checks.repairs.repair_presentation`, `product.protocols.checks.check_result`, `product.protocols.checks.execution_request`, `pydantic`, `typing`

### `product/backend/workflows/checks/reading/story_text.py`
- `JUDGEMENTS`
- `EXECUTION_LABELS`
- `EFFECT_LABELS`
- `PRECISION_LABELS`
- `CLAIM_BOUNDARIES`

### `product/backend/workflows/checks/registry.py`
- `class RegisteredCheckIdentity`
- `class RegisteredResourceWindow`
- `class RegisteredAuxiliarySource`
- `class RegisteredCheckProof`
- `class CheckRuntimeRegistration`
- `class CheckRuntimeRegistry`
主要 import / dot-source：`__future__`, `product.backend.core.boundaries.entities`, `product.backend.core.checks.plan`, `product.backend.core.errors`, `product.backend.core.preparation.bindings`, `product.protocols.checks.check_runtime`, `product.protocols.checks.execution_request`, `product.protocols.observer`, `product.protocols.web.target`, `pydantic`, `threading`

### `product/backend/workflows/checks/repairs/repair.py`
- `build_current_repair_contract(package, source_case_id, breakpoint)`
- `class CurrentRepairService`
主要 import / dot-source：`__future__`, `product.backend.core.checks.repair`, `product.backend.core.errors`, `product.backend.core.lifecycle`, `product.protocols.checks.execution_request`

### `product/backend/workflows/checks/repairs/repair_presentation.py`
- `class RepairComparisonRow`
- `build_repair_comparison(contract, source, current) -> tuple[RepairComparisonRow, ...]`
主要 import / dot-source：`__future__`, `product.backend.core.checks.repair`, `product.backend.core.errors`, `product.backend.core.lifecycle`, `product.protocols.checks.execution_request`, `typing`

### `product/backend/workflows/checks/repairs/repair_text.py`
- `REPAIR_STATUS_LABELS`
- `CHANGE_IMPACT_LABELS`
- `REPAIR_REQUIREMENTS`
- `CURRENT_TASK_TEXT`

### `product/backend/workflows/checks/runtime_bundle.py`
- `recorded_request_template(template) -> HttpRequestTemplate`
- `class CheckRuntimeBuilder`
- `derive_target_classifiers(config, specs, identities)`
主要 import / dot-source：`__future__`, `collections.abc`, `hashlib`, `json`, `product.backend.core.checks.plan`, `product.backend.core.errors`, `product.backend.core.preparation.bindings`, `product.backend.infra.artifacts.checks.check_packages`, `product.backend.infra.recording.request_store`, `product.backend.workflows.recording.lifecycle`, `product.backend.workflows.recording.source`, `product.protocols.checks.check_runtime`, `product.protocols.observer`, `product.protocols.recording.flow_draft`, `product.protocols.recording.recording_flow`, `product.protocols.runtime.node_runtime`, `product.protocols.web.request`, `product.protocols.web.response`, `typing`, `urllib.parse`

### `product/backend/workflows/checks/service.py`
- `class CheckPreview`
- `class CheckService`
主要 import / dot-source：`__future__`, `collections.abc`, `hashlib`, `json`, `logging`, `product.backend.core.checks.plan`, `product.backend.core.errors`, `product.backend.infra.artifacts.checks.check_validation`, `product.backend.infra.runtime.jobs.models`, `product.backend.infra.runtime.jobs.requests.checks`, `product.protocols.checks.check_runtime`, `product.protocols.checks.execution_request`, `pydantic`, `threading`, `time`, `typing`, `uuid`

### `product/backend/workflows/contracts/governance.py`
- `class ContractGovernance`
主要 import / dot-source：`__future__`, `collections.abc`, `product.backend.core.contracts.lifecycle`, `product.backend.core.contracts.models`, `product.backend.core.errors`, `product.backend.core.lifecycle`, `product.backend.core.verification.permissions`, `product.backend.infra.storage`, `time`

### `product/backend/workflows/development/__init__.py`
主要 import / dot-source：`product.backend.workflows.development.service`

### `product/backend/workflows/development/operations.py`
- `operation_fingerprint(project_id, kind, operation_id, payload)`
- `require_active_task_version(work, project_id, task_id, expected_version)`
主要 import / dot-source：`hashlib`, `json`, `product.backend.core.errors`, `re`

### `product/backend/workflows/development/reading.py`
- `class DevelopmentReader`
主要 import / dot-source：`__future__`, `product.backend.core.changes.models`, `product.backend.core.errors`

### `product/backend/workflows/development/service.py`
- `class DevelopmentService`
主要 import / dot-source：`__future__`, `product.backend.core.development`, `product.backend.core.errors`, `product.backend.workflows.changes.service`, `product.backend.workflows.development.operations`, `product.backend.workflows.development.reading`, `time`, `uuid`

### `product/backend/workflows/examples/environment.py`
- `class OfficialScenarioVersion`
- `class OfficialExperienceView`
- `class OfficialSampleExperience`
主要 import / dot-source：`__future__`, `dataclasses`, `enum`, `json`, `product.backend.core.checks.repair`, `product.backend.core.errors`, `product.backend.core.identities.models`, `product.backend.core.preparation.bindings`, `product.backend.infra.samples`, `product.backend.infra.secrets`, `product.backend.workflows.business_boundaries.proposals.official_recipe`, `product.backend.workflows.checks.local_observer_wiring`, `product.backend.workflows.checks.registry`, `product.backend.workflows.examples.materials`, `product.backend.workflows.examples.preset_delivery`, `product.backend.workflows.examples.recovery`, `product.backend.workflows.preparation.supplemental.contract`, `product.backend.workflows.test_identities`, `product.protocols.checks.check_runtime`, `product.protocols.checks.execution_request`, `product.protocols.observer`, `pydantic`, `threading`, `time`, `typing`, `uuid`

### `product/backend/workflows/examples/journey.py`
- `class OfficialDevelopmentJourney`
- `build_development_journey(current, reader, understanding, boundaries, repairs, development)`
主要 import / dot-source：`.preset_delivery`, `product.backend.core.errors`, `product.protocols.checks.execution_request`, `typing`

### `product/backend/workflows/examples/materials.py`
- `SAMPLE_PROJECT_ID`
- `SAMPLE_RESOURCE_ID`
- `EXPORT_ACTION_KEY`
- `VIEW_ACTION_KEY`
- `class OfficialScenarioInstaller`
主要 import / dot-source：`__future__`, `collections.abc`, `hashlib`, `itertools`, `json`, `pathlib`, `product.backend.core.errors`, `product.backend.core.recording.models`, `product.backend.infra.runtime.jobs.attempts`, `product.backend.infra.runtime.jobs.models`, `product.backend.workflows.recording.credentials`, `product.backend.workflows.recording.lifecycle`, `product.backend.workflows.recording.project_submission`, `product.backend.workflows.recording.submission`, `product.protocols`

### `product/backend/workflows/examples/preset_delivery.py`
- `preset_operation(experience_id, stage)`
- `prepare_preset_task(service, current)`
- `register_preset_delivery(service, current, version, reference, understanding, created)`
- `preset_change_id(service, current, stage)`
主要 import / dot-source：`hashlib`, `product.backend.core.errors`

### `product/backend/workflows/examples/recovery.py`
- `class SampleRecovery`
主要 import / dot-source：`product.backend.core.errors`, `product.backend.infra.runtime.process.tree`, `uuid`

### `product/backend/workflows/examples/validation_summary.py`
- `_SUMMARY_FILE`
- `_MAX_SUMMARY_BYTES`
- `class PublishedCompetitionValidationSummary`
- `class CompetitionValidationSummaryView`
- `class CompetitionValidationSummaryQuery`
主要 import / dot-source：`__future__`, `json`, `pathlib`, `product.backend.infra.runtime.paths`, `pydantic`, `typing`

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

### `product/backend/workflows/preparation/__init__.py`
主要 import / dot-source：`product.backend.workflows.preparation.service`

### `product/backend/workflows/preparation/bindings/recording_candidates.py`
- `class RecordedPreparationCandidate`
- `request_event(recording, step)`
- `resource_value(event, candidate) -> str`
- `flow_resource_injection(flow, candidate) -> ResourceInjection`
- `supplement_candidates(recording, draft, actual_resource_id) -> tuple[RecordedPreparationCandidate, ...]`
- `choose_supplement_candidate(recording, draft, actual_resource_id)`
主要 import / dot-source：`__future__`, `json`, `product.backend.core.boundaries.entities`, `product.backend.core.errors`, `product.backend.core.preparation.bindings`, `product.backend.core.recording.models`, `product.protocols.recording.events`, `product.protocols.web.workflow`, `pydantic`, `re`, `typing`, `urllib.parse`

### `product/backend/workflows/preparation/bindings/reuse.py`
- `recorded_material_reusable(work, binding, understanding, var_dir)`
主要 import / dot-source：`product.backend.infra.observers.records.source_contracts`

### `product/backend/workflows/preparation/bindings/service.py`
- `class RegisteredEffectProofReader`
- `class PreparationBindingService`
主要 import / dot-source：`__future__`, `contextlib`, `hashlib`, `json`, `pathlib`, `product.backend.core.boundaries.entities`, `product.backend.core.checks.plan`, `product.backend.core.errors`, `product.backend.core.preparation.bindings`, `product.backend.core.recording.models`, `product.backend.workflows.business_boundaries.inspection`, `product.backend.workflows.preparation.bindings.recording_candidates`, `product.backend.workflows.preparation.bindings.sources`, `product.backend.workflows.preparation.models`, `product.backend.workflows.recording.source`, `product.backend.workflows.test_identities.service`, `typing`

### `product/backend/workflows/preparation/bindings/sources.py`
- `class RegisteredObserverReader`
- `class BindingSourceInspector`
- `binding_source_fields(work, action, identity, understanding, now_us, owner_id)`
主要 import / dot-source：`__future__`, `pathlib`, `product.backend.core.boundaries.entities`, `product.backend.core.errors`, `product.backend.core.preparation.bindings`, `product.backend.core.recording.models`, `product.backend.workflows.business_boundaries.inspection`, `product.backend.workflows.preparation.bindings.recording_candidates`, `product.backend.workflows.recording.source`, `typing`

### `product/backend/workflows/preparation/demonstrations.py`
- `class LegalActionDemonstration`
- `legal_demonstrations(contract, permissions, identities)`
主要 import / dot-source：`product.backend.core.boundaries.entities`, `product.backend.core.boundaries.semantics`, `product.backend.core.preparation.requirements`, `product.backend.workflows.preparation.models`

### `product/backend/workflows/preparation/guidance/models.py`
- `class PreparationNextAction`
- `class PreparationMaterialAdvice`
- `class ProofSourceAdvice`
- `class PreparationGuidance`
主要 import / dot-source：`product.backend.core.boundaries.entities`, `pydantic`, `typing`

### `product/backend/workflows/preparation/guidance/service.py`
- `PREPARATION_TASKS`
- `REASONS`
- `class PreparationGuidanceService`
主要 import / dot-source：`product.backend.workflows.preparation.guidance.models`, `urllib.parse`

### `product/backend/workflows/preparation/materials/evidence.py`
- `evidence_details(service, project_id, action_id) -> EvidenceMaterialDetail`
主要 import / dot-source：`product.backend.core.errors`, `product.backend.workflows.preparation.materials.evidence_models`, `product.backend.workflows.preparation.models`

### `product/backend/workflows/preparation/materials/evidence_models.py`
- `class EffectMaterialSummary`
- `class EvidenceMaterialDetail`
主要 import / dot-source：`product.backend.core.boundaries.entities`, `product.backend.workflows.preparation.models`, `pydantic`, `typing`

### `product/backend/workflows/preparation/materials/models.py`
- `class MaterialReference`
- `class MaterialChange`
- `class PreparationDraft`
主要 import / dot-source：`product.backend.core.boundaries.entities`, `pydantic`, `typing`

### `product/backend/workflows/preparation/materials/service.py`
- `class PreparationMaterialService`
主要 import / dot-source：`json`, `product.backend.core.boundaries.entities`, `product.backend.core.errors`, `product.backend.core.preparation.bindings`, `product.backend.core.recording.models`, `product.backend.workflows.preparation.materials.models`, `product.backend.workflows.recording.lifecycle`, `time`

### `product/backend/workflows/preparation/models.py`
- `class PreparationStatus`
- `class PreparationItemView`
- `class IdentitySlotPreparationView`
- `class IdentityPreparationView`
- `class ResourcePreparationView`
- `class EffectEvidencePreparationView`
- `class ActionTechnicalPreparationView`
- `class ActionPreparationView`
- `class PreparationView`
主要 import / dot-source：`enum`, `product.backend.core.boundaries.entities`, `product.backend.core.boundaries.permissions`, `product.backend.core.preparation.requirements`, `pydantic`

### `product/backend/workflows/preparation/planning.py`
- `current_plan(service, project_id, engine_version, config_fingerprint)`
主要 import / dot-source：`product.backend.core.checks.plan`, `product.backend.core.errors`, `product.backend.workflows.preparation.models`, `product.backend.workflows.recording.source`

### `product/backend/workflows/preparation/proofs/commands.py`
- `class ProofOperation`
- `class SaveProofSource`
- `class StartProofPreflight`
- `class GrantProofScope`
- `class AdoptProofSource`
- `class CancelProofPreflight`
- `class RevokeProofScope`
主要 import / dot-source：`product.protocols.preparation.proof_sources`, `product.protocols.runtime.runtime_identity`, `pydantic`, `typing`

### `product/backend/workflows/preparation/proofs/jobs.py`
- `class ProofPreflightJobs`
主要 import / dot-source：`product.backend.core.errors`, `product.backend.core.lifecycle`, `product.backend.infra.artifacts.proof_reports`, `product.backend.infra.runtime.jobs.events`, `product.backend.infra.runtime.jobs.models`, `product.backend.infra.storage`, `product.protocols.preparation.proof_sources`, `uuid`

### `product/backend/workflows/preparation/proofs/registration.py`
- `runtime_registration(project_id, sources)`
主要 import / dot-source：`product.backend.workflows.checks.registry`, `product.protocols.observer`

### `product/backend/workflows/preparation/proofs/service.py`
- `class PreparationFacts`
- `class ProofPreparationService`
主要 import / dot-source：`dataclasses`, `product.backend.core.applications.models`, `product.backend.core.boundaries.entities`, `product.backend.core.errors`, `product.backend.core.identities.models`, `product.backend.core.lifecycle`, `product.backend.core.preparation.bindings`, `product.backend.infra.observers.records.source_contracts`, `product.backend.infra.runtime.jobs.models`, `product.backend.workflows.business_boundaries.inspection`, `product.backend.workflows.business_boundaries.models`, `product.backend.workflows.recording.source`, `product.protocols.checks.check_runtime`, `product.protocols.preparation.proof_sources`, `product.protocols.runtime.node_runtime`, `product.protocols.web.request`, `product.protocols.web.target`, `time`, `uuid`

### `product/backend/workflows/preparation/service.py`
- `class BoundaryReader`
- `class IdentityReader`
- `class PreparationBindingReader`
- `class PreparationService`
主要 import / dot-source：`__future__`, `product.backend.core.boundaries.entities`, `product.backend.core.errors`, `product.backend.core.preparation.requirements`, `product.backend.workflows.business_boundaries.models`, `product.backend.workflows.preparation.models`, `product.backend.workflows.test_identities.service`, `time`, `typing`

### `product/backend/workflows/preparation/supplemental/contract.py`
- `class MaterialModel`
- `class SupplementalRecord`
- `class SupplementalDocument`
- `validate_material_payload(value, known_secrets)`
- `material_fingerprint(value)`
- `request_uuid(value)`
主要 import / dot-source：`__future__`, `hashlib`, `product.backend.core.errors`, `product.backend.infra.storage.base`, `pydantic`, `re`, `typing`, `uuid`

### `product/backend/workflows/preparation/supplemental/service.py`
- `class SupplementalMaterialService`
主要 import / dot-source：`__future__`, `hashlib`, `product.backend.core.errors`, `product.backend.infra.storage.base`, `product.backend.workflows.preparation.supplemental.contract`, `threading`, `time`, `uuid`

### `product/backend/workflows/projects/__init__.py`
主要 import / dot-source：`.catalog`, `.lifecycle`

### `product/backend/workflows/projects/catalog.py`
- `class ProjectCatalog`
主要 import / dot-source：`__future__`, `collections.abc`, `product.backend.core.errors`, `product.backend.core.lifecycle`, `product.backend.infra.storage`

### `product/backend/workflows/projects/lifecycle.py`
- `_ACTIVE_JOB_STATES`
- `_ACTIVE_RUN_STATES`
- `_TERMINAL_RECORDING_STATES`
- `class ProjectLifecycleService`
主要 import / dot-source：`__future__`, `collections.abc`, `product.backend.core.errors`, `product.backend.core.lifecycle`, `product.backend.core.recording.models`, `product.backend.infra.storage`, `product.backend.workflows.test_identities`, `time`

### `product/backend/workflows/projects/repair.py`
- `class CurrentRepairTask`
- `class ProjectRepair`
- `class CurrentProjectRepairService`
主要 import / dot-source：`__future__`, `product.backend.core.checks.repair`, `product.backend.core.lifecycle`, `product.backend.workflows.checks.repairs.repair_presentation`, `product.protocols.checks.execution_request`, `pydantic`, `typing`

### `product/backend/workflows/recording/__init__.py`
主要 import / dot-source：`.credentials`

### `product/backend/workflows/recording/credentials.py`
- `class RuntimeSecretVault`
- `class RecordingCredentialProvider`
主要 import / dot-source：`__future__`, `collections.abc`, `product.backend.core.errors`, `product.backend.core.identities.models`, `product.backend.infra.secrets`, `product.backend.workflows.test_identities`, `product.protocols`, `threading`

### `product/backend/workflows/recording/flow_compiler.py`
- `_SENSITIVE_FIELD`
- `class FlowDraftCompiler`
主要 import / dot-source：`__future__`, `collections.abc`, `product.backend.core.errors`, `product.protocols.recording.flow_draft`, `product.protocols.recording.recording_flow`, `product.protocols.web.workflow`, `pydantic`, `re`, `typing`, `urllib.parse`

### `product/backend/workflows/recording/lifecycle.py`
- `class RecordingStatusView`
- `class RecordingFinalizationView`
- `class RecordingLifecycle`
主要 import / dot-source：`__future__`, `collections.abc`, `hashlib`, `json`, `os`, `pathlib`, `product.backend.core.errors`, `product.backend.core.lifecycle`, `product.backend.core.recording.models`, `product.backend.infra.artifacts.run_packages`, `product.backend.infra.recording.control`, `product.backend.infra.runtime.paths`, `product.backend.infra.storage`, `product.backend.workflows.recording.flow_compiler`, `product.backend.workflows.recording.review`, `product.protocols`, `product.protocols.recording.recording_flow`, `pydantic`, `typing`, `uuid`

### `product/backend/workflows/recording/processing.py`
- `_UI_KINDS`
- `_HTTP_METHODS`
- `_SENSITIVE_FIELD`
- `_OPAQUE_BUSINESS_VALUE`
- `class FlowDraftProcessor`
主要 import / dot-source：`__future__`, `collections.abc`, `dataclasses`, `hashlib`, `json`, `product.backend.core.errors`, `product.backend.core.recording.models`, `product.backend.core.redaction`, `product.protocols.recording.events`, `product.protocols.recording.flow_draft`, `product.protocols.web.workflow`, `re`, `typing`, `urllib.parse`

### `product/backend/workflows/recording/project_submission.py`
- `class ProjectRecordingSubmission`
- `class ProjectRecordingService`
主要 import / dot-source：`__future__`, `dataclasses`, `product.backend.core.boundaries.entities`, `product.backend.core.errors`, `product.backend.core.lifecycle`, `product.backend.core.recording.models`, `product.backend.workflows.recording.source`, `product.backend.workflows.recording.submission`, `product.backend.workflows.test_identities`, `product.backend.workflows.test_identities.service`, `product.protocols`, `time`, `uuid`

### `product/backend/workflows/recording/review.py`
- `class FlowDraftReviewer`
主要 import / dot-source：`__future__`, `collections.abc`, `product.backend.core.errors`, `product.protocols.recording.flow_draft`, `product.protocols.web.workflow`, `pydantic`, `re`, `typing`, `urllib.parse`

### `product/backend/workflows/recording/run_service.py`
- `class RecordingRunService`
主要 import / dot-source：`__future__`, `collections.abc`, `os`, `pathlib`, `product.backend.core.errors`, `product.backend.infra.runtime.jobs.dispatch`, `product.backend.infra.storage`, `product.backend.workflows.recording.submission`, `product.protocols`, `time`

### `product/backend/workflows/recording/source.py`
- `identity_source_fingerprint(identity)`
- `current_recording_instance(work, project_id)`
- `recording_endpoint_fingerprint(understanding, controlled_instance_id)`
- `recording_source_fingerprint(action, identity, understanding, action_binding, actor_binding, owner, owner_actor_binding, controlled_instance_id)`
- `require_recording_source(work, request, historical_source, reused_source_fingerprint)`
- `require_persisted_recording_source(work, recording, var_dir, reused_source_fingerprint)`
主要 import / dot-source：`product.backend.core.boundaries.entities`, `product.backend.core.errors`, `product.backend.core.recording.models`, `product.backend.workflows.business_boundaries.inspection`

### `product/backend/workflows/recording/submission.py`
- `class RecordingApplicationModel`
- `class SubmitRecording`
- `class RecordingSubmissionResult`
- `class RecordingCompletionResult`
- `recording_target_scope(endpoint) -> WebTargetScope`
- `class RecordingSubmission`
主要 import / dot-source：`__future__`, `collections.abc`, `hashlib`, `product.backend.core.errors`, `product.backend.core.identifiers`, `product.backend.core.lifecycle`, `product.backend.core.recording.models`, `product.backend.infra.recording.request_store`, `product.backend.infra.runtime.jobs.events`, `product.backend.infra.runtime.jobs.handlers`, `product.backend.infra.runtime.jobs.models`, `product.backend.infra.storage`, `product.backend.workflows.recording.processing`, `product.backend.workflows.recording.source`, `product.protocols`, `product.protocols.web.target`, `pydantic`, `time`, `typing`, `urllib.parse`, `uuid`

### `product/backend/workflows/reports/__init__.py`
主要 import / dot-source：`product.backend.workflows.reports.presentation`

### `product/backend/workflows/reports/finalizer.py`
- `class ResultFinalizer`
主要 import / dot-source：`__future__`, `collections.abc`, `contextlib`, `pathlib`, `product.backend.core.errors`, `product.backend.core.lifecycle`, `product.backend.infra.artifacts.run_publication`, `product.backend.infra.runtime.paths`, `product.backend.infra.runtime.process.lock`, `product.backend.infra.storage`, `product.backend.workflows.reports.findings`, `product.backend.workflows.reports.published`, `time`

### `product/backend/workflows/reports/findings.py`
- `_SEVERITY_ORDER`
- `class FindingMaterializer`
- `class FindingQueries`
- `finding_inputs(reader, view) -> tuple[FindingInput, ...]`
主要 import / dot-source：`__future__`, `collections`, `collections.abc`, `hashlib`, `json`, `product.backend.core.errors`, `product.backend.core.lifecycle`, `product.backend.core.verification.findings`, `product.backend.infra.storage`, `product.backend.infra.storage.results.findings`, `product.backend.workflows.reports.published`, `product.protocols`, `time`, `typing`

### `product/backend/workflows/reports/gating.py`
- `class RegressionGate`
主要 import / dot-source：`__future__`, `collections.abc`, `json`, `product.backend.core.errors`, `product.backend.core.lifecycle`, `product.backend.core.verification.behavior_differential`, `product.backend.core.verification.gating`, `product.backend.core.verification.permissions`, `product.backend.infra.storage.results.gating`, `product.backend.workflows.reports.findings`, `product.backend.workflows.reports.published`, `product.protocols`, `time`, `typing`

### `product/backend/workflows/reports/presentation/__init__.py`
主要 import / dot-source：`product.backend.core.verification.breakpoints`, `product.backend.workflows.reports.presentation.builder`, `product.backend.workflows.reports.presentation.explanations`, `product.backend.workflows.reports.presentation.models`

### `product/backend/workflows/reports/presentation/builder.py`
- `class ResultPresentationBuilder`
- `build_result_presentation(view, snapshot, finding_views, permission_policy, change_context) -> ResultPresentation`
- `_POLICY_RELATION_TEXT`
- `locate_published_breakpoints(snapshot, evidence_items, traces_by_case) -> dict[tuple[str, str], BreakpointResult]`
- `_WITNESS_LABELS`
- `_BREAKPOINT_LABELS`
- `_TRACE_KIND_LABELS`
主要 import / dot-source：`__future__`, `enum`, `product.backend.core.errors`, `product.backend.core.lifecycle`, `product.backend.core.reports.repair`, `product.backend.core.verification.breakpoints`, `product.backend.core.verification.continuity`, `product.backend.core.verification.facts`, `product.backend.core.verification.trace`, `product.backend.workflows.reports.presentation.explanations`, `product.backend.workflows.reports.presentation.models`, `product.backend.workflows.reports.trace`, `product.protocols.observer`, `product.protocols.runner.execution_request`, `pydantic`, `typing`

### `product/backend/workflows/reports/presentation/explanations.py`
- `_ROLE_LABELS`
- `_ACTION_LABELS`
- `_RESOURCE_LABELS`
- `_RELATION_LABELS`
- `_SOURCE_PRESENTATION`
- `_SOURCE_STEPS`
- `_SOURCE_LIMITS`
- `_SOURCE_FOUND_FACTS`
- `_SOURCE_SUPPORTED_CLAIMS`
主要 import / dot-source：`__future__`, `product.backend.core.lifecycle`, `product.backend.core.reports.repair`, `product.backend.core.verification.breakpoints`, `product.backend.core.verification.facts`, `product.backend.core.verification.trace`, `product.backend.workflows.reports.presentation.models`, `product.protocols.observer`, `product.protocols.runner.execution_request`, `typing`

### `product/backend/workflows/reports/presentation/models.py`
- `class PresentedCaseVerdict`
- `class ResultEvidenceSource`
- `class ResultWitnessItem`
- `class ResultConfirmedImpact`
- `class ResultDiagnosis`
- `class ResultClaimBoundary`
- `class ResultEvidenceExplanation`
- `class ResultPresentationIssue`
- `class ResultRelevantIntent`
- `class ResultChangeVerification`
- `class ResultPresentation`
主要 import / dot-source：`__future__`, `enum`, `product.backend.core.lifecycle`, `product.backend.core.reports.repair`, `product.backend.core.verification.breakpoints`, `product.backend.core.verification.continuity`, `product.backend.core.verification.facts`, `product.backend.core.verification.trace`, `product.protocols.observer`, `pydantic`, `typing`

### `product/backend/workflows/reports/published.py`
- `class PublishedRunView`
- `class PublishedResultReader`
主要 import / dot-source：`__future__`, `collections.abc`, `dataclasses`, `hashlib`, `json`, `pathlib`, `product.backend.core.errors`, `product.backend.core.lifecycle`, `product.backend.core.redaction`, `product.backend.infra.artifacts.run_packages`, `product.backend.infra.runtime.jobs.requests.execution`, `product.backend.infra.runtime.paths`, `product.backend.infra.storage`, `product.backend.workflows.assistant`, `product.protocols`, `product.protocols.runner.execution_request`, `typing`

### `product/backend/workflows/reports/repair.py`
- `class RepairContractService`
主要 import / dot-source：`__future__`, `hashlib`, `json`, `product.backend.core.errors`, `product.backend.core.lifecycle`, `product.backend.core.reports.repair`, `product.backend.core.verification.continuity`, `product.backend.core.verification.differential`, `product.backend.core.verification.facts`, `product.backend.core.verification.permissions`, `product.backend.workflows.reports.presentation`, `product.backend.workflows.reports.trace`, `product.protocols.runner.execution_request`, `typing`

### `product/backend/workflows/reports/reporting.py`
- `class ReportBuilder`
主要 import / dot-source：`__future__`, `collections.abc`, `json`, `pathlib`, `product.backend.core.errors`, `product.backend.core.lifecycle`, `product.backend.core.verification.gating`, `product.backend.infra.artifacts.reports.report_reader`, `product.backend.infra.artifacts.reports.report_store`, `product.backend.infra.storage`, `product.backend.workflows.reports.published`, `product.protocols`, `product.protocols.report`, `typing`

### `product/backend/workflows/reports/trace.py`
- `build_execution_traces(snapshot, evidence_items) -> tuple[ExecutionTrace, ...]`
- `build_execution_trace(snapshot, evidence) -> ExecutionTrace`
主要 import / dot-source：`__future__`, `collections.abc`, `product.backend.core.verification.trace`, `product.protocols.observer`, `pydantic`, `typing`

### `product/backend/workflows/runtime/activation.py`
- `class RuntimeActivationService`
主要 import / dot-source：`product.backend.core.development`, `product.backend.core.errors`, `product.backend.workflows.development.operations`, `threading`

### `product/backend/workflows/runtime/load_jobs.py`
- `class RuntimeLoadJobs`
主要 import / dot-source：`contextlib`, `product.backend.core.errors`, `product.backend.core.lifecycle`, `product.backend.infra.runtime.jobs.events`, `product.backend.infra.runtime.jobs.models`, `product.backend.infra.storage`, `product.protocols.runtime.node_runtime`, `uuid`

### `product/backend/workflows/runtime/node_activation.py`
- `class NodeRuntimeActivation`
主要 import / dot-source：`product.backend.core.development`, `product.backend.core.errors`, `product.backend.core.lifecycle`, `product.backend.infra.runtime.process.controlled.node_owned`, `product.backend.workflows.development.operations`

### `product/backend/workflows/runtime/ports.py`
- `class RuntimeProvider`
- `class ProjectRuntimePorts`
主要 import / dot-source：`__future__`, `collections.abc`, `dataclasses`, `product.backend.core.errors`, `product.protocols.runtime.node_runtime`, `product.protocols.runtime.runtime_identity`

### `product/backend/workflows/runtime/setup.py`
- `class NodeStartPreview`
- `class NodeRuntimeSetup`
主要 import / dot-source：`__future__`, `hashlib`, `json`, `pathlib`, `product.backend.core.errors`, `product.backend.core.lifecycle`, `product.backend.infra.runtime.jobs.models`, `product.backend.infra.runtime.jobs.queue`, `product.backend.infra.runtime.jobs.target_handlers.runtime_load`, `product.backend.infra.runtime.process.controlled.artifact`, `product.backend.infra.runtime.process.controlled.node_owned`, `product.backend.workflows.runtime.load_jobs`, `product.protocols.runtime.node_runtime`, `product.protocols.runtime.runtime_identity`, `pydantic`, `time`, `urllib.parse`, `uuid`

### `product/backend/workflows/test_identities/__init__.py`
主要 import / dot-source：`product.backend.workflows.test_identities.service`

### `product/backend/workflows/test_identities/execution.py`
- `_ENVIRONMENT_NAME`
- `class TestIdentityExecutionCredentials`
主要 import / dot-source：`__future__`, `collections.abc`, `product.backend.core.errors`, `product.backend.core.identities.models`, `product.backend.infra.secrets`, `product.backend.workflows.test_identities.service`, `product.protocols`, `re`

### `product/backend/workflows/test_identities/preparation.py`
- `class IdentityPreparationStatus`
- `class IdentityPreparationView`
- `class IdentityPreparationManager`
主要 import / dot-source：`__future__`, `collections.abc`, `dataclasses`, `enum`, `json`, `pathlib`, `product.backend.core.boundaries.entities`, `product.backend.core.errors`, `product.backend.core.identities.models`, `product.backend.infra.identity.control`, `product.backend.infra.runtime.paths`, `product.backend.infra.runtime.process.environment`, `product.backend.infra.runtime.process.tree`, `product.backend.infra.secrets`, `product.backend.workflows.test_identities.service`, `product.protocols`, `product.protocols.web.target`, `pydantic`, `re`, `shutil`, `subprocess`, `threading`, `time`, `urllib.parse`, `uuid`

### `product/backend/workflows/test_identities/service.py`
- `class TestIdentityStatus`
- `class PreparedLoginState`
- `class TestIdentityView`
- `class TestIdentityService`
主要 import / dot-source：`__future__`, `collections.abc`, `enum`, `product.backend.core.boundaries.entities`, `product.backend.core.errors`, `product.backend.core.identifiers`, `product.backend.core.identities.models`, `product.backend.infra.secrets.store`, `product.backend.infra.storage`, `pydantic`, `time`, `uuid`

### `product/backend/workflows/workspace/__init__.py`
主要 import / dot-source：`product.backend.workflows.workspace.models`, `product.backend.workflows.workspace.service`

### `product/backend/workflows/workspace/models.py`
- `class WorkspaceModel`
- `class WorkspaceProjectView`
- `class WorkspaceConnectionView`
- `class ActorWorkspaceView`
- `class ActionWorkspaceView`
- `class PrimaryTaskView`
- `class WorkspaceAreaView`
- `class WorkspaceLatestResult`
- `class WorkspaceSourceChange`
- `class WorkspaceJourneyStep`
- `class WorkspaceJourney`
- `class WorkspaceDevelopment`
- `class WorkspaceView`
主要 import / dot-source：`__future__`, `product.backend.core.boundaries.entities`, `product.backend.core.boundaries.permissions`, `product.backend.core.boundaries.proposals`, `product.backend.core.identifiers`, `product.backend.core.lifecycle`, `product.backend.workflows.business_boundaries.inspection`, `product.backend.workflows.business_boundaries.models`, `product.backend.workflows.checks.reading.results`, `product.backend.workflows.projects.repair`, `product.protocols`, `pydantic`, `typing`

### `product/backend/workflows/workspace/presentation.py`
- `_TASK_PRESENTATION`
- `task_view(task_kind, title, why_now, user_responsibility, system_will_do, route, facts, business_action_id, business_actor_id, can_execute, **context) -> PrimaryTaskView`
- `journey_view(connection, boundary_attention, preparation_complete, task, result, change, active)`
- `action_view(action, boundary, inspection, actor_inspection_by_id, permission_status) -> ActionWorkspaceView`
- `endpoint_status(understanding) -> str`
- `source_status(understanding) -> str`
- `area_views(boundary_attention, preparation_complete) -> tuple[WorkspaceAreaView, ...]`
- `boundary_views(boundary, pending)`
- `development_view(facts)`
主要 import / dot-source：`__future__`, `product.backend.core.applications.models`, `product.backend.core.boundaries.entities`, `product.backend.core.boundaries.semantics`, `product.backend.workflows.workspace.models`

### `product/backend/workflows/workspace/reading.py`
- `class WorkspaceCheckReaders`
- `class WorkspaceCheckFacts`
- `class WorkspaceDevelopmentFacts`
- `class WorkspaceReader`
- `class PreparationReading`
主要 import / dot-source：`__future__`, `collections.abc`, `contextlib`, `dataclasses`, `product.backend.core.development`, `product.backend.core.errors`, `product.backend.core.recording.models`, `product.backend.workflows.checks.reading.story_text`, `product.backend.workflows.preparation.models`, `product.backend.workflows.recording.source`, `product.backend.workflows.workspace.models`, `typing`

### `product/backend/workflows/workspace/service.py`
- `class WorkspaceService`
主要 import / dot-source：`__future__`, `product.backend.workflows.workspace.models`, `product.backend.workflows.workspace.presentation`, `product.backend.workflows.workspace.reading`, `product.backend.workflows.workspace.tasks`

### `product/backend/workflows/workspace/tasks.py`
- `class CheckPreviewRequired`
- `boundary_task(understanding, boundary, pending) -> PrimaryTaskView | None`
- `allow_control_task(preparation)`
- `PREPARATION_TEXTS`
- `class PreparationTaskSelection`
- `current_check_task(task, drifted, latest_result, preview_can_execute)`
- `development_task(primary_task, facts, boundary_attention, active_check, preview)`
主要 import / dot-source：`__future__`, `dataclasses`, `product.backend.core.applications.models`, `product.backend.core.boundaries.entities`, `product.backend.core.recording.models`, `product.backend.workflows.business_boundaries.models`, `product.backend.workflows.checks.repairs.repair_text`, `product.backend.workflows.preparation.demonstrations`, `product.backend.workflows.preparation.models`, `product.backend.workflows.workspace.models`, `product.backend.workflows.workspace.presentation`

<!-- GENERATED:END -->
