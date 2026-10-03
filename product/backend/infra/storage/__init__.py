# Storage 的稳定公共导入面；ORM 映射由 orm_registry 显式登记。

from .base import Base, MetadataValue, NAMING_CONVENTION, StorageRecord, ensure_storage_payload_safe
from product.backend.infra.storage.applications.application_understanding import ApplicationUnderstandingRepository
from product.backend.infra.storage.preparation.action_preparation import ActionPreparationRepository
from product.backend.infra.storage.boundaries.contracts import ContractVersionRepository
from .results.evidence import EvidenceIndexRecord, EvidenceIndexRepository
from .results.findings import FindingOccurrenceRecord, FindingRecord, FindingRepository
from .results.finalizations import BaseReportFinalizationState, FindingFinalizationState, RunFinalizationRecord, RunFinalizationRepository
from .results.gating import GateResultRecord, GatingRepository, RegressionBaselineRecord
from .execution.jobs import JobEventRecord, JobEventRepository, JobRecord, JobRepository
from product.backend.infra.storage.settings.llm import AIAssistanceSettingsRepository, LLMProfileRepository
from product.backend.infra.storage.execution.profiles import ExecutionProfileRecord, ExecutionProfileRepository
from product.backend.infra.storage.applications.projects import ProjectRecord, ProjectRepository
from product.backend.infra.storage.preparation.recordings import FlowDraftRevisionRecord, FlowDraftRevisionRepository, RecordingRecord, RecordingRepository
from product.backend.infra.storage.changes.source_changes import SourceChangeRepository
from .execution.runs import RunRecord, RunRepository
from product.backend.infra.storage.boundaries.permission_intents import PermissionIntentRepository
from product.backend.infra.storage.preparation.test_identities import TestIdentityRepository
from .db import SQLITE_BUSY_TIMEOUT_MS, create_session_factory, create_sqlite_engine, default_database_path, upgrade_database
from .unit_of_work import StorageUnitOfWork

__all__ = [
    "Base", "MetadataValue", "NAMING_CONVENTION", "StorageRecord", "ensure_storage_payload_safe",
    "ApplicationUnderstandingRepository", "ContractVersionRepository",
    "EvidenceIndexRecord", "EvidenceIndexRepository", "FindingRecord", "FindingOccurrenceRecord", "FindingRepository",
    "FindingFinalizationState", "BaseReportFinalizationState", "RunFinalizationRecord", "RunFinalizationRepository",
    "GateResultRecord", "GatingRepository", "RegressionBaselineRecord",
    "JobEventRecord", "JobEventRepository", "JobRecord", "JobRepository", "LLMProfileRepository", "AIAssistanceSettingsRepository",
    "ExecutionProfileRecord", "ExecutionProfileRepository", "ProjectRecord", "ProjectRepository",
    "FlowDraftRevisionRecord", "FlowDraftRevisionRepository", "RecordingRecord", "RecordingRepository",
    "RunRecord", "RunRepository", "SQLITE_BUSY_TIMEOUT_MS", "create_session_factory",
    "create_sqlite_engine", "default_database_path", "upgrade_database", "StorageUnitOfWork",
    "TestIdentityRepository", "ActionPreparationRepository", "PermissionIntentRepository",
    "SourceChangeRepository",
]
