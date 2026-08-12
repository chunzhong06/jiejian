# =============================================================================
# Application 组合根
#
# 定位
#   API、CLI 与 Worker 共用的能力实例装配边界
#
# 职责
#   连接 Storage 与应用服务｜注册 JobHandler｜集中运行时依赖注入
#
# 调用链
#   API / CLI / Worker bootstrap → ApplicationContext → capability services
# =============================================================================

from __future__ import annotations

from functools import partial
from pathlib import Path
from collections.abc import Mapping
from typing import Callable

from ..execution.attempts import JobAttemptService
from ..execution.handlers import JobHandlerRegistry
from ..execution.published_artifacts import attempt_paths_for
from ..execution.publication import RunPublicationService
from ..execution.requests import ExecutionRequestService
from ..execution.reconciliation import RunReconciliationService
from ..execution.request_store import ExecutionRequestStore
from ..execution.run_handler import VerificationRunJobHandler
from ..execution.queue import JobQueueService
from ..execution.submission import ExecutionSubmissionService
from ..execution.targets import JobTargetType, default_run_job_targets
from ..projects.service import ProjectControlService
from ..recording.application import RecordingApplicationService
from ..recording.job_handler import RecordingJobHandler
from ..recording.job_target import RecordingJobTargetHandler
from ..recording.request_store import RecordingRequestStore
from ..results.published import PublishedResultReader
from ..storage import StorageUnitOfWork
from ..contracts.llm.adapters.httpx_transport import HttpxLLMTransport
from ..contracts.llm.profiles import LLMProfileApplicationService
from ..contracts.llm.secrets import LLMSecretStore


class ApplicationContext:
    """创建基础设施并注册各能力区的应用服务。"""

    def __init__(
        self,
        var_dir: Path,
        *,
        llm_transport=None,
        llm_secret_store: LLMSecretStore | None = None,
        environ: Mapping[str, str] | None = None,
        clock_us: Callable[[], int] | None = None,
    ) -> None:
        from ..storage import (
            create_session_factory,
            create_sqlite_engine,
            default_database_path,
            upgrade_database,
        )

        self.var_dir = var_dir.resolve()
        database_path = default_database_path(self.var_dir)
        upgrade_database(database_path)
        self.engine = create_sqlite_engine(database_path)
        factory = partial(StorageUnitOfWork, create_session_factory(self.engine))
        self.uow_factory = factory
        self.job_targets = default_run_job_targets()
        self.job_targets.register(
            JobTargetType.RECORDING,
            RecordingJobTargetHandler(),
        )
        self.job_queue = JobQueueService(factory, targets=self.job_targets)
        self.execution_request_store = ExecutionRequestStore(self.var_dir)
        self.execution_submission = ExecutionSubmissionService(
            factory,
            self.execution_request_store,
            queue=self.job_queue,
        )
        self.results = PublishedResultReader(self.var_dir, self.uow_factory)
        self.projects = ProjectControlService(factory)
        self.execution_requests = ExecutionRequestService(factory, self.projects)
        from ..contracts.governance_service import ContractGovernanceService

        self.contracts = ContractGovernanceService(
            factory,
            observer_resolver=self.projects.current_observers,
        )
        from ..contracts.analysis.service import ContractAnalysisService

        self.contract_analysis = ContractAnalysisService(
            factory,
            var_dir=self.var_dir,
            observer_resolver=self.projects.current_observers,
        )
        from ..contracts.llm.service import LLMCandidateGenerationService

        self.llm_profiles = LLMProfileApplicationService(
            factory,
            transport=llm_transport or HttpxLLMTransport(),
            secret_store=llm_secret_store,
            environ=environ,
            clock_us=clock_us,
        )
        self.llm_candidates = LLMCandidateGenerationService(
            factory,
            profile_resolver=self.llm_profiles,
        )
        from ..contracts.workbench import ContractWorkbenchService

        self.contract_workbench = ContractWorkbenchService(
            factory,
            self.projects,
            self.contracts,
            self.contract_analysis,
            self.llm_candidates,
        )

    def build_job_handler_registry(self, lease_owner: str, environ) -> JobHandlerRegistry:
        attempts = JobAttemptService(
            self.uow_factory,
            targets=self.job_targets,
        )
        registry = JobHandlerRegistry()

        def build_run_handler() -> VerificationRunJobHandler:
            publication = RunPublicationService(self.var_dir, self.uow_factory)
            return VerificationRunJobHandler(
                var_dir=self.var_dir,
                lease_owner=lease_owner,
                uow_factory=self.uow_factory,
                attempt_service=attempts,
                request_store=self.execution_request_store,
                publication_service=publication,
                reconciliation_service=RunReconciliationService(
                    self.var_dir,
                    self.uow_factory,
                    publication,
                ),
                environ=environ,
            )

        def build_recording_handler() -> RecordingJobHandler:
            recording_store = RecordingRequestStore(self.var_dir)
            return RecordingJobHandler(
                var_dir=self.var_dir,
                lease_owner=lease_owner,
                uow_factory=self.uow_factory,
                attempts=attempts,
                application=RecordingApplicationService(
                    self.uow_factory,
                    recording_store,
                    attempts=attempts,
                ),
                request_store=recording_store,
                cancel_path_for=lambda root, job: attempt_paths_for(
                    root, job
                ).cancel_path,
                environ=environ,
            )

        registry.register(JobTargetType.RUN, build_run_handler)
        registry.register(JobTargetType.RECORDING, build_recording_handler)
        return registry

    def close(self) -> None:
        self.engine.dispose()
