# =============================================================================
# Storage Unit of Work
#
# 定位
#   应用服务与具体 Repository 之间的显式事务及资源所有权边界
#
# 职责
#   组合聚合仓储｜统一 commit/rollback｜关闭 Session 并映射持久化错误
#
# 调用链
#   Application / Execution services → StorageUnitOfWork → Repositories / Session
# =============================================================================

from __future__ import annotations

from collections.abc import Sequence
from types import TracebackType

from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from ..errors import ErrorCode, JiejianError
from .job_control import JobControlRepository
from .repositories.contracts import (
    ContractCandidateRepository,
    ContractVersionRepository,
    RequirementRepository,
)
from .repositories.llm import LLMProfileRepository
from .repositories.permission_profiles import PermissionExecutionProfileRepository
from .repositories.evidence import EvidenceIndexRepository
from .repositories.findings import FindingRepository
from .repositories.gating import GatingRepository
from .repositories.jobs import JobEventRepository, JobRepository
from .repositories.projects import ProjectRepository
from .repositories.recordings import (
    FlowDraftRevisionRepository,
    RecordingRepository,
)
from .repositories.runs import RunRepository


class StorageUnitOfWork:
    """一个实例只承载一个显式事务；退出时不会隐式提交。"""

    projects: ProjectRepository
    requirements: RequirementRepository
    contract_candidates: ContractCandidateRepository
    contract_versions: ContractVersionRepository
    runs: RunRepository
    recordings: RecordingRepository
    flow_drafts: FlowDraftRevisionRepository
    jobs: JobRepository
    job_events: JobEventRepository
    job_control: JobControlRepository
    evidence: EvidenceIndexRepository
    llm_profiles: LLMProfileRepository
    permission_execution_profiles: PermissionExecutionProfileRepository
    findings: FindingRepository
    gating: GatingRepository

    def __init__(
        self,
        session_factory: sessionmaker[Session],
        *,
        known_secrets: Sequence[str] = (),
    ) -> None:
        self._session_factory = session_factory
        self._known_secrets = tuple(secret for secret in known_secrets if secret)
        self._session: Session | None = None
        self._committed = False

    def begin(self) -> StorageUnitOfWork:
        if self._session is not None:
            raise JiejianError(ErrorCode.STORAGE_STATE, "事务已经开始")
        session = self._session_factory()
        session.begin()
        self._session = session
        self._committed = False
        self.projects = ProjectRepository(session, self._known_secrets)
        self.requirements = RequirementRepository(session, self._known_secrets)
        self.contract_candidates = ContractCandidateRepository(
            session, self._known_secrets
        )
        self.contract_versions = ContractVersionRepository(
            session, self._known_secrets
        )
        self.runs = RunRepository(session, self._known_secrets)
        self.recordings = RecordingRepository(session, self._known_secrets)
        self.flow_drafts = FlowDraftRevisionRepository(
            session,
            self._known_secrets,
        )
        self.jobs = JobRepository(session, self._known_secrets)
        self.job_events = JobEventRepository(session, self._known_secrets)
        self.job_control = JobControlRepository(session, self._known_secrets)
        self.evidence = EvidenceIndexRepository(session, self._known_secrets)
        self.llm_profiles = LLMProfileRepository(session, self._known_secrets)
        self.permission_execution_profiles = PermissionExecutionProfileRepository(
            session, self._known_secrets
        )
        self.findings = FindingRepository(session, self._known_secrets)
        self.gating = GatingRepository(session, self._known_secrets)
        return self

    def commit(self) -> None:
        session = self._require_session()
        if self._committed:
            raise JiejianError(ErrorCode.STORAGE_STATE, "事务已经提交")
        try:
            session.commit()
        except IntegrityError:
            session.rollback()
            raise JiejianError(
                ErrorCode.STORAGE_CONSTRAINT,
                "数据库约束拒绝写入",
            ) from None
        except SQLAlchemyError:
            session.rollback()
            raise JiejianError(ErrorCode.STORAGE_FAILURE, "数据库操作失败") from None
        self._committed = True

    def rollback(self) -> None:
        session = self._require_session()
        try:
            session.rollback()
        except SQLAlchemyError:
            raise JiejianError(ErrorCode.STORAGE_FAILURE, "数据库回滚失败") from None

    def close(self) -> None:
        if self._session is None:
            return
        try:
            if self._session.in_transaction():
                self._session.rollback()
            self._session.close()
        except SQLAlchemyError:
            raise JiejianError(ErrorCode.STORAGE_FAILURE, "数据库关闭失败") from None
        finally:
            self._session = None
            self._committed = False

    def __enter__(self) -> StorageUnitOfWork:
        return self.begin()

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> bool:
        try:
            if self._session is not None and self._session.in_transaction():
                self.rollback()
        finally:
            self.close()
        return False

    def _require_session(self) -> Session:
        if self._session is None:
            raise JiejianError(ErrorCode.STORAGE_STATE, "事务尚未开始")
        return self._session
