# =============================================================================
# Storage Unit of Work
#
# 定位
#   应用服务与具体 Repository 之间的显式事务及资源所有权边界
#
# 职责
#   组合聚合仓储｜统一 commit/rollback｜关闭 Session 并映射持久化错误
#
# 边界
#   每个实例独占一个 Session；未显式 commit 的工作在退出时回滚，Repository 不自行提交。
#
# 调用链
#   Application / Execution services → StorageUnitOfWork → Repositories / Session
# =============================================================================

from __future__ import annotations

from collections.abc import Sequence
from types import TracebackType

from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.infra.storage.execution.job_control import JobControlRepository
from product.backend.infra.storage.application_understanding import ApplicationUnderstandingRepository
from product.backend.infra.storage.business_boundaries import BusinessBoundaryRepository
from product.backend.infra.storage.action_preparation import ActionPreparationRepository
from product.backend.infra.storage.contracts import ContractVersionRepository
from product.backend.infra.storage.llm import AIAssistanceSettingsRepository, LLMProfileRepository
from product.backend.infra.storage.execution_profiles import ExecutionProfileRepository
from product.backend.infra.storage.results.evidence import EvidenceIndexRepository
from product.backend.infra.storage.results.findings import FindingRepository
from product.backend.infra.storage.results.finalizations import RunFinalizationRepository
from product.backend.infra.storage.results.gating import GatingRepository
from product.backend.infra.storage.execution.jobs import JobEventRepository, JobRepository
from product.backend.infra.storage.projects import ProjectRepository
from product.backend.infra.storage.recordings import FlowDraftRevisionRepository, RecordingRepository
from product.backend.infra.storage.source_changes import SourceChangeRepository
from product.backend.infra.storage.execution.runs import RunRepository
from product.backend.infra.storage.setup import (
    PermissionIntentRepository,
    TestIdentityRepository,
)


class StorageUnitOfWork:
    """一个实例只承载一个显式事务；退出时不会隐式提交。"""

    projects: ProjectRepository
    application_understanding: ApplicationUnderstandingRepository
    business_boundaries: BusinessBoundaryRepository
    action_preparation: ActionPreparationRepository
    contract_versions: ContractVersionRepository
    runs: RunRepository
    recordings: RecordingRepository
    flow_drafts: FlowDraftRevisionRepository
    jobs: JobRepository
    job_events: JobEventRepository
    job_control: JobControlRepository
    evidence: EvidenceIndexRepository
    llm_profiles: LLMProfileRepository
    ai_assistance_settings: AIAssistanceSettingsRepository
    execution_profiles: ExecutionProfileRepository
    findings: FindingRepository
    finalizations: RunFinalizationRepository
    gating: GatingRepository
    test_identities: TestIdentityRepository
    permission_intents: PermissionIntentRepository
    source_changes: SourceChangeRepository

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
        """打开唯一事务并把全部 Repository 绑定到同一个 Session。"""

        if self._session is not None:
            raise JiejianError(ErrorCode.STORAGE_STATE, "事务已经开始")
        session = self._session_factory()
        session.begin()
        self._session = session
        self._committed = False
        self.projects = ProjectRepository(session, self._known_secrets)
        self.application_understanding = ApplicationUnderstandingRepository(
            session,
            self._known_secrets,
        )
        self.business_boundaries = BusinessBoundaryRepository(
            session,
            self._known_secrets,
        )
        self.action_preparation = ActionPreparationRepository(session, self._known_secrets)
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
        self.ai_assistance_settings = AIAssistanceSettingsRepository(session, self._known_secrets)
        self.execution_profiles = ExecutionProfileRepository(
            session, self._known_secrets
        )
        self.findings = FindingRepository(session, self._known_secrets)
        self.finalizations = RunFinalizationRepository(session, self._known_secrets)
        self.gating = GatingRepository(session, self._known_secrets)
        self.test_identities = TestIdentityRepository(session, self._known_secrets)
        self.permission_intents = PermissionIntentRepository(
            session,
            self._known_secrets,
        )
        self.source_changes = SourceChangeRepository(session, self._known_secrets)
        return self

    def commit(self) -> None:
        """显式提交事务；约束与数据库错误统一回滚并映射为脱敏错误。"""

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
        """回滚仍活跃的未提交事务并关闭 Session；重复关闭安全。"""

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
