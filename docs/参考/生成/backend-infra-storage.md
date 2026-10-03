# 自动代码参考：后端 Storage

> 生成区域只描述当前代码结构；职责与安全理由由能力映射和任务指南维护。

<!-- GENERATED:START -->

<!-- 此区域由 scripts/docs/generate.py 从 product/backend/infra/storage/ 读取。 -->

### `product/backend/infra/storage/__init__.py`
主要 import / dot-source：`.base`, `.db`, `.execution.jobs`, `.execution.runs`, `.results.evidence`, `.results.finalizations`, `.results.findings`, `.results.gating`, `.unit_of_work`, `product.backend.infra.storage.applications.application_understanding`, `product.backend.infra.storage.applications.projects`, `product.backend.infra.storage.boundaries.contracts`, `product.backend.infra.storage.boundaries.permission_intents`, `product.backend.infra.storage.changes.source_changes`, `product.backend.infra.storage.execution.profiles`, `product.backend.infra.storage.preparation.action_preparation`, `product.backend.infra.storage.preparation.recordings`, `product.backend.infra.storage.preparation.test_identities`, `product.backend.infra.storage.settings.llm`

### `product/backend/infra/storage/applications/application_understanding.py`
- `class ApplicationUnderstandingRow`
- `class ApplicationUnderstandingRepository`
主要 import / dot-source：`__future__`, `collections.abc`, `json`, `product.backend.core.applications.models`, `product.backend.core.errors`, `product.backend.infra.storage.base`, `sqlalchemy`, `sqlalchemy.orm`

### `product/backend/infra/storage/applications/projects.py`
- `class ProjectRow`
- `class ProjectRecord`
- `class ProjectRepository`
主要 import / dot-source：`__future__`, `collections.abc`, `hashlib`, `json`, `product.backend.core.errors`, `product.backend.core.identifiers`, `product.backend.core.lifecycle`, `product.backend.core.recording.models`, `product.backend.core.verification.permissions`, `product.backend.infra.storage.base`, `product.protocols`, `pydantic`, `re`, `sqlalchemy`, `sqlalchemy.exc`, `sqlalchemy.orm`, `time`, `typing`

### `product/backend/infra/storage/base.py`
- `NAMING_CONVENTION`
- `class Base`
- `_METADATA_KEY`
- `_SENSITIVE_METADATA_KEY`
- `_INLINE_SECRET`
- `class StorageRecord`
- `ensure_storage_payload_safe(value, known_secrets) -> None`
主要 import / dot-source：`__future__`, `collections.abc`, `json`, `product.backend.core.errors`, `pydantic`, `re`, `sqlalchemy`, `sqlalchemy.exc`, `sqlalchemy.orm`, `typing`

### `product/backend/infra/storage/boundaries/business_boundaries.py`
- `class BusinessActorRevisionRow`
- `class BusinessActorRow`
- `class BusinessActionRevisionRow`
- `class BusinessActionRow`
- `class BoundaryProposalRow`
- `class BoundaryProposalDecisionRow`
- `class ActorImplementationBindingRow`
- `class ActionImplementationBindingRow`
- `class BusinessBoundaryRepository`
主要 import / dot-source：`__future__`, `collections.abc`, `product.backend.core.boundaries.entities`, `product.backend.core.boundaries.proposals`, `product.backend.infra.storage.base`, `sqlalchemy`, `sqlalchemy.orm`

### `product/backend/infra/storage/boundaries/contracts.py`
- `class ContractVersionRow`
- `class ContractVersionRepository`
主要 import / dot-source：`__future__`, `collections.abc`, `json`, `product.backend.core.contracts.models`, `product.backend.core.errors`, `product.backend.core.lifecycle`, `product.backend.core.verification.permissions`, `product.backend.infra.storage.base`, `sqlalchemy`, `sqlalchemy.orm`

### `product/backend/infra/storage/boundaries/permission_intents.py`
- `class PermissionIntentRevisionRow`
- `class ProjectPolicyStateRow`
- `class PermissionIntentRepository`
主要 import / dot-source：`__future__`, `collections.abc`, `json`, `product.backend.core.boundaries.permissions`, `product.backend.infra.storage.base`, `sqlalchemy`, `sqlalchemy.orm`

### `product/backend/infra/storage/boundaries/rule_candidates.py`
- `class RuleCandidateRow`
- `class RuleCandidateRevisionRow`
- `class RuleCandidateProposalRow`
- `class RuleCandidateReceiptRow`
- `class RuleCandidateRepository`
主要 import / dot-source：`__future__`, `product.backend.core.boundaries.rule_candidates`, `product.backend.core.errors`, `product.backend.infra.storage.base`, `sqlalchemy`, `sqlalchemy.orm`

### `product/backend/infra/storage/changes/code_observations.py`
- `class CodeObservationRow`
- `class ChangeCodeObservationRow`
- `class RunCodeObservationRow`
- `class CodeObservationRepository`
主要 import / dot-source：`__future__`, `product.backend.core.errors`, `product.backend.infra.storage.base`, `sqlalchemy`, `sqlalchemy.orm`

### `product/backend/infra/storage/changes/development.py`
- `class DevelopmentTaskRow`
- `class DevelopmentContextRow`
- `class DevelopmentAcceptanceRow`
- `class DevelopmentDeliveryRow`
- `class DevelopmentReceiptRow`
- `class DevelopmentCheckRunRow`
- `class DevelopmentRepository`
主要 import / dot-source：`json`, `product.backend.core.development`, `product.backend.core.errors`, `product.backend.infra.storage.base`, `sqlalchemy`, `sqlalchemy.orm`

### `product/backend/infra/storage/changes/source_changes.py`
- `class SourceRevisionSnapshotRow`
- `class ChangeManifestRow`
- `class SourceChangeSetRow`
- `class ChangeImpactAssessmentRow`
- `class SourceChangeRepository`
主要 import / dot-source：`__future__`, `collections.abc`, `json`, `product.backend.core.changes.models`, `product.backend.core.errors`, `product.backend.core.reports.repair`, `product.backend.infra.storage.base`, `sqlalchemy`, `sqlalchemy.orm`

### `product/backend/infra/storage/db.py`
- `SQLITE_BUSY_TIMEOUT_MS`
- `_BASE_MIGRATION_REVISION`
- `_MAINTENANCE_MIGRATION_REVISION`
- `_CURRENT_MIGRATION_REVISION`
- `_LEGACY_1_X_MIGRATION_REVISIONS`
- `_INCOMPATIBLE_DATABASE_MESSAGE`
- `_EXPECTED_TRIGGER_SQL`
- `default_database_path(var_dir) -> Path`
- `configure_sqlite_engine(engine) -> None`
- `create_sqlite_engine(database_path) -> Engine`
- `create_session_factory(engine) -> sessionmaker[Session]`
- `upgrade_database(database_path) -> None`
- `require_current_database(database_path) -> None`
主要 import / dot-source：`__future__`, `alembic`, `alembic.config`, `collections`, `collections.abc`, `contextlib`, `importlib.resources`, `json`, `pathlib`, `product.backend.core.errors`, `product.backend.infra.runtime.paths`, `product.backend.infra.storage.base`, `product.backend.infra.storage.orm_registry`, `sqlalchemy`, `sqlalchemy.exc`, `sqlalchemy.orm`, `sqlalchemy.pool`, `sqlite3`, `tempfile`

### `product/backend/infra/storage/execution/job_control.py`
- `_NONTERMINAL_RUNS`
- `class JobControlRepository`
主要 import / dot-source：`__future__`, `collections.abc`, `product.backend.core.errors`, `product.backend.core.lifecycle`, `product.backend.infra.storage.execution.jobs`, `product.backend.infra.storage.execution.runs`, `product.backend.infra.storage.preparation.recordings`, `sqlalchemy`, `sqlalchemy.exc`, `sqlalchemy.orm`, `typing`

### `product/backend/infra/storage/execution/jobs.py`
- `class JobRow`
- `class JobEventRow`
- `class JobRecord`
- `class JobEventRecord`
- `class JobRepository`
- `class JobEventRepository`
主要 import / dot-source：`__future__`, `collections.abc`, `hashlib`, `json`, `product.backend.core.errors`, `product.backend.core.identifiers`, `product.backend.core.lifecycle`, `product.backend.core.recording.models`, `product.backend.core.verification.permissions`, `product.backend.infra.storage.base`, `product.protocols`, `pydantic`, `re`, `sqlalchemy`, `sqlalchemy.exc`, `sqlalchemy.orm`, `time`, `typing`

### `product/backend/infra/storage/execution/profiles.py`
- `class ExecutionProfileRow`
- `class ExecutionProfileRecord`
- `class ExecutionProfileRepository`
主要 import / dot-source：`__future__`, `collections.abc`, `product.backend.core.errors`, `product.backend.core.identifiers`, `product.backend.infra.storage.base`, `pydantic`, `sqlalchemy`, `sqlalchemy.orm`

### `product/backend/infra/storage/execution/runs.py`
- `class RunRow`
- `class RunRecord`
- `class RunRepository`
主要 import / dot-source：`__future__`, `collections.abc`, `hashlib`, `json`, `product.backend.core.errors`, `product.backend.core.identifiers`, `product.backend.core.lifecycle`, `product.backend.core.recording.models`, `product.backend.core.verification.permissions`, `product.backend.infra.storage.base`, `product.protocols`, `pydantic`, `re`, `sqlalchemy`, `sqlalchemy.exc`, `sqlalchemy.orm`, `time`, `typing`

### `product/backend/infra/storage/orm_registry.py`
- `_STORAGE_ORM_MODULES`
- `load_storage_orm_mappings() -> None`
主要 import / dot-source：`__future__`, `importlib`

### `product/backend/infra/storage/preparation/action_preparation.py`
- `class ActionExecutionBindingRow`
- `class ActionResourceBindingRow`
- `class ActionEvidenceBindingRow`
- `class ActionRecoveryBindingRow`
- `_ROWS`
- `_JSON_FIELDS`
- `class ActionAllowControlBindingRow`
- `class ActionPreparationRepository`
主要 import / dot-source：`__future__`, `collections.abc`, `json`, `product.backend.core.errors`, `product.backend.core.preparation.bindings`, `product.backend.core.preparation.requirements`, `product.backend.infra.storage.base`, `sqlalchemy`, `sqlalchemy.orm`

### `product/backend/infra/storage/preparation/preparation_recovery.py`
- `class PreparationReceiptRow`
- `class PreparationDraftRow`
- `class PreparationCandidateRecordingRow`
- `class PreparationRecoveryRepository`
主要 import / dot-source：`json`, `product.backend.core.errors`, `product.backend.infra.storage.base`, `sqlalchemy`, `sqlalchemy.orm`

### `product/backend/infra/storage/preparation/proof_sources.py`
- `class ProofSourceRow`
- `class ProofSourceRevisionRow`
- `class ProofReadScopeRow`
- `class ProofPreflightRow`
- `class ProofSourceRepository`
主要 import / dot-source：`product.backend.core.errors`, `product.backend.infra.storage.base`, `product.protocols.preparation.proof_sources`, `sqlalchemy`, `sqlalchemy.orm`

### `product/backend/infra/storage/preparation/recordings.py`
- `class RecordingRow`
- `class FlowDraftRevisionRow`
- `class RecordingRecord`
- `class FlowDraftRevisionRecord`
- `class RecordingRepository`
- `class FlowDraftRevisionRepository`
主要 import / dot-source：`__future__`, `collections.abc`, `hashlib`, `json`, `product.backend.core.boundaries.entities`, `product.backend.core.errors`, `product.backend.core.identifiers`, `product.backend.core.lifecycle`, `product.backend.core.recording.models`, `product.backend.core.verification.permissions`, `product.backend.infra.storage.base`, `product.protocols`, `pydantic`, `re`, `sqlalchemy`, `sqlalchemy.exc`, `sqlalchemy.orm`, `time`, `typing`

### `product/backend/infra/storage/preparation/supplemental_materials.py`
- `class SupplementalMaterialRevisionRow`
- `class SupplementalMaterialReceiptRow`
- `class SupplementalMaterialRepository`
主要 import / dot-source：`__future__`, `json`, `product.backend.infra.storage.base`, `sqlalchemy`, `sqlalchemy.orm`

### `product/backend/infra/storage/preparation/test_identities.py`
- `class TestIdentityRow`
- `class TestIdentityCookieRow`
- `class TestIdentityRepository`
主要 import / dot-source：`__future__`, `collections.abc`, `product.backend.core.errors`, `product.backend.core.identities.models`, `product.backend.infra.storage.base`, `sqlalchemy`, `sqlalchemy.orm`

### `product/backend/infra/storage/results/check_publications.py`
- `class CheckPublicationRow`
- `class CheckPublicationRecord`
- `class CheckPublicationRepository`
主要 import / dot-source：`product.backend.infra.storage.base`, `pydantic`, `sqlalchemy`, `sqlalchemy.orm`

### `product/backend/infra/storage/results/evidence.py`
- `class EvidenceIndexRow`
- `class EvidenceIndexRecord`
- `class EvidenceIndexRepository`
主要 import / dot-source：`__future__`, `collections.abc`, `hashlib`, `json`, `product.backend.core.errors`, `product.backend.core.identifiers`, `product.backend.core.lifecycle`, `product.backend.core.recording.models`, `product.backend.core.verification.permissions`, `product.backend.infra.storage.base`, `product.protocols`, `pydantic`, `re`, `sqlalchemy`, `sqlalchemy.exc`, `sqlalchemy.orm`, `time`, `typing`

### `product/backend/infra/storage/results/finalizations.py`
- `class FindingFinalizationState`
- `class BaseReportFinalizationState`
- `class RunFinalizationRow`
- `class RunFinalizationRecord`
- `class RunFinalizationRepository`
主要 import / dot-source：`__future__`, `enum`, `product.backend.core.errors`, `product.backend.core.identifiers`, `product.backend.infra.storage.base`, `pydantic`, `sqlalchemy`, `sqlalchemy.orm`, `typing`

### `product/backend/infra/storage/results/findings.py`
- `class FindingRow`
- `class FindingOccurrenceRow`
- `class FindingRecord`
- `class FindingOccurrenceRecord`
- `class FindingRepository`
主要 import / dot-source：`__future__`, `collections.abc`, `product.backend.core.errors`, `product.backend.infra.storage.base`, `sqlalchemy`, `sqlalchemy.orm`

### `product/backend/infra/storage/results/gating.py`
- `class RegressionBaselineRow`
- `class GateResultRow`
- `class RegressionBaselineRecord`
- `class GateResultRecord`
- `class GatingRepository`
主要 import / dot-source：`__future__`, `collections.abc`, `product.backend.infra.storage.base`, `sqlalchemy`, `sqlalchemy.orm`

### `product/backend/infra/storage/runtime/environment_operations.py`
- `class EnvironmentOperationRow`
- `class EnvironmentOperationRepository`
主要 import / dot-source：`product.backend.infra.storage.base`, `sqlalchemy`, `sqlalchemy.orm`

### `product/backend/infra/storage/runtime/runtime_loads.py`
- `class RuntimeLoadRow`
- `class RuntimeLoadRepository`
主要 import / dot-source：`product.backend.core.errors`, `product.backend.infra.storage.base`, `product.protocols.runtime.node_runtime`, `sqlalchemy`, `sqlalchemy.orm`

### `product/backend/infra/storage/runtime/sample_workspaces.py`
- `class SampleWorkspaceRow`
- `class SampleInstanceRow`
- `class SampleReconciliationRow`
- `class SampleWorkspaceRepository`
主要 import / dot-source：`json`, `product.backend.infra.storage.base`, `sqlalchemy`, `sqlalchemy.orm`

### `product/backend/infra/storage/settings/llm.py`
- `class LLMProfileRow`
- `class AIAssistanceSettingsRow`
- `class LLMProfileRepository`
- `class AIAssistanceSettingsRepository`
主要 import / dot-source：`__future__`, `collections.abc`, `product.backend.core.errors`, `product.backend.infra.llm.config`, `product.backend.infra.storage.base`, `sqlalchemy`, `sqlalchemy.orm`

### `product/backend/infra/storage/unit_of_work.py`
- `class StorageUnitOfWork`
主要 import / dot-source：`__future__`, `collections.abc`, `product.backend.core.errors`, `product.backend.infra.storage.applications.application_understanding`, `product.backend.infra.storage.applications.projects`, `product.backend.infra.storage.boundaries.business_boundaries`, `product.backend.infra.storage.boundaries.contracts`, `product.backend.infra.storage.boundaries.permission_intents`, `product.backend.infra.storage.boundaries.rule_candidates`, `product.backend.infra.storage.changes.code_observations`, `product.backend.infra.storage.changes.development`, `product.backend.infra.storage.changes.source_changes`, `product.backend.infra.storage.execution.job_control`, `product.backend.infra.storage.execution.jobs`, `product.backend.infra.storage.execution.profiles`, `product.backend.infra.storage.execution.runs`, `product.backend.infra.storage.preparation.action_preparation`, `product.backend.infra.storage.preparation.preparation_recovery`, `product.backend.infra.storage.preparation.proof_sources`, `product.backend.infra.storage.preparation.recordings`, `product.backend.infra.storage.preparation.supplemental_materials`, `product.backend.infra.storage.preparation.test_identities`, `product.backend.infra.storage.results.check_publications`, `product.backend.infra.storage.results.evidence`, `product.backend.infra.storage.results.finalizations`, `product.backend.infra.storage.results.findings`, `product.backend.infra.storage.results.gating`, `product.backend.infra.storage.runtime.environment_operations`, `product.backend.infra.storage.runtime.runtime_loads`, `product.backend.infra.storage.runtime.sample_workspaces`, `product.backend.infra.storage.settings.llm`, `sqlalchemy.exc`, `sqlalchemy.orm`, `types`

<!-- GENERATED:END -->
