# 自动代码参考：后端 Storage

> 生成区域只描述当前代码结构；职责与安全理由由模块参考和任务指南维护。

<!-- GENERATED:START -->

<!-- 此区域由 scripts/docs/generate.py 从 product/backend/infra/storage/ 读取。 -->

### `product/backend/infra/storage/__init__.py`
主要 import / dot-source：`.action_preparation`, `.application_understanding`, `.base`, `.contracts`, `.db`, `.execution.jobs`, `.execution.runs`, `.execution_profiles`, `.llm`, `.projects`, `.recordings`, `.results.evidence`, `.results.finalizations`, `.results.findings`, `.results.gating`, `.setup`, `.source_changes`, `.unit_of_work`

### `product/backend/infra/storage/action_preparation.py`
- `class ActionExecutionBindingRow`
- `class ActionResourceBindingRow`
- `class ActionEvidenceBindingRow`
- `class ActionRecoveryBindingRow`
- `_ROWS`
- `_JSON_FIELDS`
- `class ActionPreparationRepository`
主要 import / dot-source：`__future__`, `collections.abc`, `json`, `product.backend.core.action_preparation`, `product.backend.core.errors`, `product.backend.infra.storage.base`, `sqlalchemy`, `sqlalchemy.orm`

### `product/backend/infra/storage/application_understanding.py`
- `class ApplicationUnderstandingRow`
- `class ApplicationUnderstandingRepository`
主要 import / dot-source：`__future__`, `collections.abc`, `json`, `product.backend.core.application_understanding`, `product.backend.core.errors`, `product.backend.infra.storage.base`, `sqlalchemy`, `sqlalchemy.orm`

### `product/backend/infra/storage/base.py`
- `NAMING_CONVENTION`
- `class Base`
- `_METADATA_KEY`
- `_SENSITIVE_METADATA_KEY`
- `_INLINE_SECRET`
- `class StorageRecord`
- `ensure_storage_payload_safe(value, known_secrets) -> None`
主要 import / dot-source：`__future__`, `collections.abc`, `json`, `product.backend.core.errors`, `pydantic`, `re`, `sqlalchemy`, `sqlalchemy.exc`, `sqlalchemy.orm`, `typing`

### `product/backend/infra/storage/business_boundaries.py`
- `class BusinessActorRevisionRow`
- `class BusinessActorRow`
- `class BusinessActionRevisionRow`
- `class BusinessActionRow`
- `class BoundaryProposalRow`
- `class BoundaryProposalDecisionRow`
- `class ActorImplementationBindingRow`
- `class ActionImplementationBindingRow`
- `class BusinessBoundaryRepository`
主要 import / dot-source：`__future__`, `collections.abc`, `product.backend.core.boundary_proposal`, `product.backend.core.business_boundary`, `product.backend.infra.storage.base`, `sqlalchemy`, `sqlalchemy.orm`

### `product/backend/infra/storage/contracts.py`
- `class ContractVersionRow`
- `class ContractVersionRepository`
主要 import / dot-source：`__future__`, `collections.abc`, `json`, `product.backend.core.contracts.models`, `product.backend.core.errors`, `product.backend.core.lifecycle`, `product.backend.core.verification.permissions`, `product.backend.infra.storage.base`, `sqlalchemy`, `sqlalchemy.orm`

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
主要 import / dot-source：`__future__`, `collections.abc`, `product.backend.core.errors`, `product.backend.core.lifecycle`, `product.backend.infra.storage.execution.jobs`, `product.backend.infra.storage.execution.runs`, `product.backend.infra.storage.recordings`, `sqlalchemy`, `sqlalchemy.exc`, `sqlalchemy.orm`, `typing`

### `product/backend/infra/storage/execution/jobs.py`
- `class JobRow`
- `class JobEventRow`
- `class JobRecord`
- `class JobEventRecord`
- `class JobRepository`
- `class JobEventRepository`
主要 import / dot-source：`__future__`, `collections.abc`, `hashlib`, `json`, `product.backend.core.errors`, `product.backend.core.identifiers`, `product.backend.core.lifecycle`, `product.backend.core.recording`, `product.backend.core.verification.permissions`, `product.backend.infra.storage.base`, `product.protocols`, `pydantic`, `re`, `sqlalchemy`, `sqlalchemy.exc`, `sqlalchemy.orm`, `time`, `typing`

### `product/backend/infra/storage/execution/runs.py`
- `class RunRow`
- `class RunRecord`
- `class RunRepository`
主要 import / dot-source：`__future__`, `collections.abc`, `hashlib`, `json`, `product.backend.core.errors`, `product.backend.core.identifiers`, `product.backend.core.lifecycle`, `product.backend.core.recording`, `product.backend.core.verification.permissions`, `product.backend.infra.storage.base`, `product.protocols`, `pydantic`, `re`, `sqlalchemy`, `sqlalchemy.exc`, `sqlalchemy.orm`, `time`, `typing`

### `product/backend/infra/storage/execution_profiles.py`
- `class ExecutionProfileRow`
- `class ExecutionProfileRecord`
- `class ExecutionProfileRepository`
主要 import / dot-source：`__future__`, `collections.abc`, `product.backend.core.errors`, `product.backend.core.identifiers`, `product.backend.infra.storage.base`, `pydantic`, `sqlalchemy`, `sqlalchemy.orm`

### `product/backend/infra/storage/llm.py`
- `class LLMProfileRow`
- `class AIAssistanceSettingsRow`
- `class LLMProfileRepository`
- `class AIAssistanceSettingsRepository`
主要 import / dot-source：`__future__`, `collections.abc`, `product.backend.core.errors`, `product.backend.infra.llm.config`, `product.backend.infra.storage.base`, `sqlalchemy`, `sqlalchemy.orm`

### `product/backend/infra/storage/orm_registry.py`
- `_STORAGE_ORM_MODULES`
- `load_storage_orm_mappings() -> None`
主要 import / dot-source：`__future__`, `importlib`

### `product/backend/infra/storage/projects.py`
- `class ProjectRow`
- `class ProjectRecord`
- `class ProjectRepository`
主要 import / dot-source：`__future__`, `collections.abc`, `hashlib`, `json`, `product.backend.core.errors`, `product.backend.core.identifiers`, `product.backend.core.lifecycle`, `product.backend.core.recording`, `product.backend.core.verification.permissions`, `product.backend.infra.storage.base`, `product.protocols`, `pydantic`, `re`, `sqlalchemy`, `sqlalchemy.exc`, `sqlalchemy.orm`, `time`, `typing`

### `product/backend/infra/storage/recordings.py`
- `class RecordingRow`
- `class FlowDraftRevisionRow`
- `class RecordingRecord`
- `class FlowDraftRevisionRecord`
- `class RecordingRepository`
- `class FlowDraftRevisionRepository`
主要 import / dot-source：`__future__`, `collections.abc`, `hashlib`, `json`, `product.backend.core.business_boundary`, `product.backend.core.errors`, `product.backend.core.identifiers`, `product.backend.core.lifecycle`, `product.backend.core.recording`, `product.backend.core.verification.permissions`, `product.backend.infra.storage.base`, `product.protocols`, `pydantic`, `re`, `sqlalchemy`, `sqlalchemy.exc`, `sqlalchemy.orm`, `time`, `typing`

### `product/backend/infra/storage/results/evidence.py`
- `class EvidenceIndexRow`
- `class EvidenceIndexRecord`
- `class EvidenceIndexRepository`
主要 import / dot-source：`__future__`, `collections.abc`, `hashlib`, `json`, `product.backend.core.errors`, `product.backend.core.identifiers`, `product.backend.core.lifecycle`, `product.backend.core.recording`, `product.backend.core.verification.permissions`, `product.backend.infra.storage.base`, `product.protocols`, `pydantic`, `re`, `sqlalchemy`, `sqlalchemy.exc`, `sqlalchemy.orm`, `time`, `typing`

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

### `product/backend/infra/storage/setup/__init__.py`
主要 import / dot-source：`.permission_intents`, `.test_identities`

### `product/backend/infra/storage/setup/permission_intents.py`
- `class PermissionIntentRevisionRow`
- `class ProjectPolicyStateRow`
- `class PermissionIntentRepository`
主要 import / dot-source：`__future__`, `collections.abc`, `json`, `product.backend.core.permission_intent`, `product.backend.infra.storage.base`, `sqlalchemy`, `sqlalchemy.orm`

### `product/backend/infra/storage/setup/test_identities.py`
- `class TestIdentityRow`
- `class TestIdentityCookieRow`
- `class TestIdentityRepository`
主要 import / dot-source：`__future__`, `collections.abc`, `product.backend.core.errors`, `product.backend.core.test_identity`, `product.backend.infra.storage.base`, `sqlalchemy`, `sqlalchemy.orm`

### `product/backend/infra/storage/source_changes.py`
- `class SourceRevisionSnapshotRow`
- `class ChangeManifestRow`
- `class SourceChangeSetRow`
- `class ChangeImpactAssessmentRow`
- `class SourceChangeRepository`
主要 import / dot-source：`__future__`, `collections.abc`, `json`, `product.backend.core.errors`, `product.backend.core.repair`, `product.backend.core.source_changes`, `product.backend.infra.storage.base`, `sqlalchemy`, `sqlalchemy.orm`

### `product/backend/infra/storage/unit_of_work.py`
- `class StorageUnitOfWork`
主要 import / dot-source：`__future__`, `collections.abc`, `product.backend.core.errors`, `product.backend.infra.storage.action_preparation`, `product.backend.infra.storage.application_understanding`, `product.backend.infra.storage.business_boundaries`, `product.backend.infra.storage.contracts`, `product.backend.infra.storage.execution.job_control`, `product.backend.infra.storage.execution.jobs`, `product.backend.infra.storage.execution.runs`, `product.backend.infra.storage.execution_profiles`, `product.backend.infra.storage.llm`, `product.backend.infra.storage.projects`, `product.backend.infra.storage.recordings`, `product.backend.infra.storage.results.evidence`, `product.backend.infra.storage.results.finalizations`, `product.backend.infra.storage.results.findings`, `product.backend.infra.storage.results.gating`, `product.backend.infra.storage.setup`, `product.backend.infra.storage.source_changes`, `sqlalchemy.exc`, `sqlalchemy.orm`, `types`

<!-- GENERATED:END -->
