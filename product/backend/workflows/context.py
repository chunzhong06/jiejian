# =============================================================================
# Application 组合根
#
# 定位
#   API、CLI 与 GUI 共用的完整应用能力装配边界
#
# 职责
#   连接 Storage 与应用服务｜集中运行时依赖注入
#
# 边界
#   只负责控制面装配；Worker 使用独立 WorkerContainer，高风险动作仍由 Worker/Runner 执行。
#
# 调用链
#   API / CLI / GUI → ApplicationCore → capability services
# =============================================================================

from __future__ import annotations

import os
from functools import partial
from pathlib import Path
from collections.abc import Mapping
from typing import Callable

from product.backend.infra.runtime.job_requests import ExecutionRequestStore
from product.backend.infra.runtime.jobs.attempts import JobAttempts
from product.backend.infra.runtime.jobs.queue import JobQueue
from product.backend.workflows.runs.submission import RunSubmission
from product.backend.workflows.runs.execution import ExecutionWorkflow
from product.backend.infra.runtime.jobs.targets import JobTargetType, default_run_job_targets
from product.backend.infra.runtime.jobs.recording import RecordingJobTargetHandler
from product.backend.workflows.projects.catalog import ProjectCatalog
from product.backend.workflows.recording.submission import RecordingSubmission
from product.backend.workflows.recording.lifecycle import RecordingLifecycle
from product.backend.infra.runtime.paths import RuntimePaths
from product.backend.infra.runtime.cache import CacheMaintenanceService
from product.backend.infra.recording.request_store import RecordingRequestStore
from product.backend.infra.storage import StorageUnitOfWork
from product.backend.infra.llm.adapters.httpx_transport import HttpxLLMTransport
from product.backend.infra.llm.profiles import LLMProfileRegistry
from product.backend.infra.llm.secrets import LLMSecretStore
from product.backend.workflows.onboarding.workflow import FolderSelector, OnboardingWorkflow, SystemFolderSelector
from product.backend.workflows.onboarding.secrets import RuntimeSecretVault
from product.backend.workflows.onboarding.guide import GuideQueryService
from product.backend.workflows.recording.run_service import RecordingRunService
from product.backend.workflows.results.services import build_result_services


class ApplicationCore:
    """创建基础设施并注册各能力区的应用服务。"""

    def __init__(
        self,
        var_dir: Path,
        *,
        llm_transport=None,
        llm_secret_store: LLMSecretStore | None = None,
        environ: Mapping[str, str] | None = None,
        clock_us: Callable[[], int] | None = None,
        folder_selector: FolderSelector | None = None,
    ) -> None:
        from product.backend.infra.storage import create_session_factory, create_sqlite_engine, default_database_path, upgrade_database

        self.var_dir = var_dir.resolve()
        self.paths = RuntimePaths(self.var_dir).ensure_layout()
        self._base_environment = dict(environ if environ is not None else os.environ)
        self.cache = CacheMaintenanceService(
            self.var_dir,
            environment=self._base_environment,
        )
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
        self.job_attempts = JobAttempts(factory, targets=self.job_targets)
        self.job_queue = JobQueue(factory, targets=self.job_targets)
        self.execution_request_store = ExecutionRequestStore(self.var_dir)
        self.result_services = build_result_services(
            self.var_dir,
            self.uow_factory,
            clock_us=clock_us,
        )
        self.results = self.result_services.reader
        self.finding_materializer = self.result_services.materializer
        self.findings = self.result_services.queries
        self.gating = self.result_services.gate
        self.reports = self.result_services.reports
        self.result_finalizer = self.result_services.finalizer
        self.secret_vault = RuntimeSecretVault()
        self.execution_submission = RunSubmission(
            factory,
            self.execution_request_store,
            queue=self.job_queue,
        )
        self.execution = ExecutionWorkflow(
            factory,
            self.execution_request_store,
            self.execution_submission,
            environment_provider=self.environment_for_secret_names,
            var_dir=self.var_dir,
            clock_us=clock_us,
        )
        self.projects = ProjectCatalog(factory)
        from product.backend.workflows.contracts.governance import ContractGovernance

        self.contracts = ContractGovernance(
            factory,
            observer_resolver=self.projects.current_observations,
        )
        self.recording_submission = RecordingSubmission(
            factory,
            RecordingRequestStore(self.var_dir),
        )
        self.recording_lifecycle = RecordingLifecycle(factory, var_dir=self.var_dir)
        self.onboarding = OnboardingWorkflow(
            folder_selector
            or SystemFolderSelector(
                environment=self._base_environment,
                var_dir=self.var_dir,
            ),
            var_dir=self.var_dir,
            vault=self.secret_vault,
            projects=self.projects,
            contracts=self.contracts,
            execution=self.execution,
            environment_provider=self.environment_for_secret_names,
        )
        self.recording_runs = RecordingRunService(
            self.var_dir,
            self.uow_factory,
            self.recording_submission,
            self.environment_for_secret_names,
        )
        self.guide = GuideQueryService(
            self.projects,
            self.execution,
            self.uow_factory,
        )
        from product.backend.workflows.contracts.analysis import ContractAnalysis

        self.contract_analysis = ContractAnalysis(
            factory,
            var_dir=self.var_dir,
            observer_resolver=self.projects.current_observations,
        )
        from product.backend.workflows.contracts.candidate_generation import ContractCandidateGenerator

        self.llm_profiles = LLMProfileRegistry(
            factory,
            transport=llm_transport or HttpxLLMTransport(),
            secret_store=llm_secret_store,
            environ=environ,
            clock_us=clock_us,
        )
        self.llm_candidates = ContractCandidateGenerator(
            factory,
            profile_resolver=self.llm_profiles,
        )
        from product.backend.workflows.contracts.workbench import ContractWorkbench

        self.contract_workbench = ContractWorkbench(
            factory,
            self.projects,
            self.contracts,
            self.contract_analysis,
            self.llm_candidates,
        )

    def close(self) -> None:
        self.secret_vault.clear()
        self.engine.dispose()

    def environment_for_secret_names(self, names) -> dict[str, str]:
        environment = dict(self._base_environment)
        environment.update(self.secret_vault.resolve(names))
        return environment
