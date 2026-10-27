# Storage 的稳定公共导入面；ORM 映射由 orm_registry 显式登记。

from product.backend.infrastructure.storage.base import Base, MetadataValue, NAMING_CONVENTION, StorageRecord, ensure_storage_payload_safe
from product.backend.infrastructure.storage.applications.application_understanding import ApplicationUnderstandingRepository
from product.backend.infrastructure.storage.preparation.action_preparation import ActionPreparationRepository
from product.backend.infrastructure.storage.results.evidence import EvidenceIndexRecord, EvidenceIndexRepository
from product.backend.infrastructure.storage.execution.jobs import JobEventRecord, JobEventRepository, JobRecord, JobRepository
from product.backend.infrastructure.storage.applications.projects import ProjectRecord, ProjectRepository
from product.backend.infrastructure.storage.preparation.recordings import FlowDraftRevisionRecord, FlowDraftRevisionRepository, RecordingRecord, RecordingRepository
from product.backend.infrastructure.storage.changes.source_changes import SourceChangeRepository
from product.backend.infrastructure.storage.execution.runs import RunRecord, RunRepository
from product.backend.infrastructure.storage.boundaries.permission_intents import PermissionIntentRepository
from product.backend.infrastructure.storage.preparation.test_identities import TestIdentityRepository
from product.backend.infrastructure.storage.db import SQLITE_BUSY_TIMEOUT_MS, create_session_factory, create_sqlite_engine, default_database_path, prepare_database
from product.backend.infrastructure.storage.unit_of_work import StorageUnitOfWork

__all__ = [
    "Base", "MetadataValue", "NAMING_CONVENTION", "StorageRecord", "ensure_storage_payload_safe",
    "ApplicationUnderstandingRepository",
    "EvidenceIndexRecord", "EvidenceIndexRepository",
    "JobEventRecord", "JobEventRepository", "JobRecord", "JobRepository",
    "ProjectRecord", "ProjectRepository",
    "FlowDraftRevisionRecord", "FlowDraftRevisionRepository", "RecordingRecord", "RecordingRepository",
    "RunRecord", "RunRepository", "SQLITE_BUSY_TIMEOUT_MS", "create_session_factory",
    "create_sqlite_engine", "default_database_path", "prepare_database", "StorageUnitOfWork",
    "TestIdentityRepository", "ActionPreparationRepository", "PermissionIntentRepository",
    "SourceChangeRepository",
]
