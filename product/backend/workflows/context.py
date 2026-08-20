# =============================================================================
# Application 组合根
#
# 定位
#   API、CLI 与 Worker 共用的能力实例装配边界
#
# 职责
#   连接 Storage 与应用服务｜注册 JobHandler｜集中运行时依赖注入
#
# 边界
#   只负责装配；高风险动作仍由 Worker/Runner 和专用 Handler 执行，入口不得绕过边界。
#
# 调用链
#   API / CLI / Worker bootstrap → ApplicationCore → capability services
# =============================================================================

from __future__ import annotations

import os
from functools import partial
from pathlib import Path
from collections.abc import Mapping
from typing import Callable

from product.backend.infra.runtime.jobs.attempts import JobAttempts
from product.backend.infra.runtime.jobs.handlers import JobHandlerRegistry
from product.backend.infra.artifacts.run_packages import attempt_paths_for
from product.backend.infra.artifacts.run_publication import RunPublisher
from product.backend.infra.runtime.jobs.reconciliation import RunReconciler
from product.backend.infra.runtime.job_requests import ExecutionRequestStore, required_secret_names
from product.backend.infra.runtime.jobs.verification import VerificationRunJobHandler
from product.backend.infra.runtime.jobs.queue import JobQueue
from product.backend.workflows.runs.submission import RunSubmission
from product.backend.workflows.runs.execution import ExecutionWorkflow
from product.backend.infra.runtime.jobs.targets import JobTargetType, default_run_job_targets
from product.backend.infra.artifacts.scan_job import ArtifactCheckJobHandler
from product.backend.workflows.projects.catalog import ProjectCatalog
from product.backend.workflows.recording.submission import RecordingSubmission
from product.backend.workflows.recording.lifecycle import RecordingLifecycle
from product.backend.infra.runtime.jobs.recording import RecordingJobHandler
from product.backend.infra.runtime.jobs.recording import RecordingJobTargetHandler
from product.backend.infra.runtime.jobs.dispatch import WorkerDispatcher
from product.backend.infra.recording.request_store import RecordingRequestStore
from product.backend.workflows.results.published import PublishedResultReader
from product.backend.workflows.results.reporting import ReportBuilder
from product.backend.infra.storage import StorageUnitOfWork
from product.backend.infra.llm.adapters.httpx_transport import HttpxLLMTransport
from product.backend.infra.llm.profiles import LLMProfileRegistry
from product.backend.infra.llm.secrets import LLMSecretStore
from product.backend.workflows.onboarding.workflow import FolderSelector, OnboardingWorkflow, SystemFolderSelector
from product.backend.workflows.onboarding.secrets import RuntimeSecretVault
from product.backend.workflows.onboarding.demo import DemoExecutionStatusReader, DemoRuntimeSupervisor
from product.backend.workflows.onboarding.models import DemoVariant, OnboardingDemoStatus
from product.backend.core.errors import ErrorCode, JiejianError
from product.protocols import RunnerResult


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
        _minimal: bool = False,
    ) -> None:
        from product.backend.infra.storage import create_session_factory, create_sqlite_engine, default_database_path, upgrade_database

        self.var_dir = var_dir.resolve()
        self._base_environment = dict(environ if environ is not None else os.environ)
        database_path = default_database_path(self.var_dir)
        if not _minimal:
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
        if _minimal:
            return
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
        self.results = PublishedResultReader(self.var_dir, self.uow_factory)
        from product.backend.workflows.results.findings import FindingProjection

        self.findings = FindingProjection(self.uow_factory, self.results)
        from product.backend.workflows.results.gating import RegressionGate

        self.gating = RegressionGate(
            self.uow_factory,
            self.results,
            self.findings,
            clock_us=clock_us,
        )
        self.reports = ReportBuilder(
            self.var_dir,
            self.results,
            self.findings,
            self.gating,
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
            folder_selector or SystemFolderSelector(environment=self._base_environment),
            var_dir=self.var_dir,
            vault=self.secret_vault,
            projects=self.projects,
            contracts=self.contracts,
            execution=self.execution,
            environment_provider=self.environment_for_secret_names,
        )
        self.demo = DemoRuntimeSupervisor(
            self.onboarding,
            var_dir=self.var_dir,
            base_environment=self._base_environment,
            secret_vault=self.secret_vault,
            status_reader=DemoExecutionStatusReader(factory, self.results),
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

    def build_job_handler_registry(self, lease_owner: str, environ) -> JobHandlerRegistry:
        attempts = self.job_attempts
        registry = JobHandlerRegistry()

        def build_run_handler() -> VerificationRunJobHandler:
            publication = RunPublisher(self.var_dir, self.uow_factory)
            return VerificationRunJobHandler(
                var_dir=self.var_dir,
                lease_owner=lease_owner,
                uow_factory=self.uow_factory,
                attempt_service=attempts,
                request_store=self.execution_request_store,
                publication_service=publication,
                reconciliation_service=RunReconciler(
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
                application=RecordingSubmission(
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
        registry.register_auxiliary("ARTIFACT_CHECK", self.build_artifact_check_handler)
        return registry

    def build_artifact_check_handler(self) -> ArtifactCheckJobHandler:
        """构造只由 Worker 使用的隔离产物检查 Handler。"""

        return ArtifactCheckJobHandler(self.var_dir)

    def run_recording(self, command, *, timeout_seconds: int, secret_names: tuple[str, ...] = ()):
        """提交 Recording 并等待其 Worker 完成；入口层不直接装配调度基础设施。"""
        submission = self.recording_submission.submit(command)
        dispatcher = WorkerDispatcher(
            var_dir=self.var_dir,
            uow_factory=self.uow_factory,
            environ=self._base_environment,
        )
        process = dispatcher.start(
            job_id=submission.job.job_id,
            lease_owner=f"recording-worker-{os.getpid()}-{id(submission)}",
            secret_names=secret_names,
        )
        dispatcher.wait_recording(
            submission.job.job_id,
            process,
            timeout_seconds=timeout_seconds,
        )
        return submission

    def guide_snapshot(self) -> dict[str, object]:
        """从现有项目、权限规则和运行记录生成无独立持久状态的引导视图。"""

        projects = self.projects.list()
        items: list[dict[str, object]] = []
        recent_runs = []
        for project in projects:
            profiles = self.execution.list(project.project_id)
            with self.uow_factory() as work:
                runs = work.runs.list_for_project(project.project_id)
            recent_runs.extend((project, run) for run in runs)
            items.append(
                {
                    "project": project,
                    "profiles": profiles,
                    "permission_rules_ready": (
                        project.governed_contract_id is not None
                        and project.governed_contract_version is not None
                    ),
                }
            )
        recent_runs.sort(key=lambda item: item[1].created_at_us, reverse=True)
        return {
            "schema_version": "1",
            "projects": tuple(items),
            "recent_runs": tuple(recent_runs),
        }

    def run_demo(
        self, variant: DemoVariant
    ) -> tuple[OnboardingDemoStatus, RunnerResult]:
        """运行内置演示并等待可信发布结果；目标请求仍只由独立 Worker/Runner 发出。"""

        status = self.demo.start(variant)
        if status.job_id is None:
            raise JiejianError(
                ErrorCode.ONBOARDING_DEMO_FAILED, "内置演示没有形成可执行任务"
            )
        try:
            with self.uow_factory() as work:
                job = work.jobs.get(status.job_id)
            if job is None:
                raise JiejianError(
                    ErrorCode.ONBOARDING_DEMO_FAILED,
                    "内置演示任务无法读取",
                )
            request = self.execution_request_store.load(
                status.job_id, expected_hash=job.request_hash
            )
            secret_names = required_secret_names(request)
            environment = self.environment_for_secret_names(secret_names)
            known_secrets = tuple(
                value for name in secret_names if (value := environment.get(name))
            )
            dispatcher = WorkerDispatcher(
                var_dir=self.var_dir,
                uow_factory=self.uow_factory,
                environ=environment,
            )
            process = dispatcher.start(
                job_id=status.job_id,
                lease_owner=f"guide-worker-{os.getpid()}-{id(status)}",
                secret_names=secret_names,
            )
            staged = dispatcher.wait(
                status.job_id,
                process,
                known_secrets=known_secrets,
                timeout_seconds=(request.budget.max_duration_us * 3) / 1_000_000
                + 60,
            )
            return status, staged.result
        finally:
            self.demo.stop()

    def close(self) -> None:
        if hasattr(self, "demo"):
            self.demo.close()
        if hasattr(self, "secret_vault"):
            self.secret_vault.clear()
        self.engine.dispose()

    def environment_for_secret_names(self, names) -> dict[str, str]:
        environment = dict(self._base_environment)
        environment.update(self.secret_vault.resolve(names))
        return environment


class WorkerContext(ApplicationCore):
    """只打开既有数据库并装配 Job 所需的最小 Worker 组合根。"""

    def __init__(self, var_dir: Path, *, environ: Mapping[str, str] | None = None) -> None:
        super().__init__(var_dir, environ=environ, _minimal=True)
