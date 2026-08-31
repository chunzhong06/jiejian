# =============================================================================
# ApplicationCore 组合根
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

from product.backend.infra.runtime.jobs.requests import ExecutionRequestStore
from product.backend.infra.runtime.jobs.attempts import JobAttempts
from product.backend.infra.runtime.jobs.queue import JobQueue
from product.backend.workflows.runs.submission import RunSubmission
from product.backend.workflows.runs.execution import ExecutionWorkflow
from product.backend.infra.runtime.jobs.targets import JobTargetType, default_run_job_targets
from product.backend.infra.runtime.jobs.recording import RecordingJobTargetHandler
from product.backend.workflows.projects.catalog import ProjectCatalog
from product.backend.workflows.projects.lifecycle import ProjectLifecycleService
from product.backend.workflows.projects.preparation import ProjectPreparationService
from product.backend.workflows.projects.readiness import ProjectReadinessService
from product.backend.workflows.application_understanding.service import ApplicationUnderstandingService
from product.backend.workflows.recording.submission import RecordingSubmission
from product.backend.workflows.recording.lifecycle import RecordingLifecycle
from product.backend.infra.runtime.paths import RuntimePaths
from product.backend.infra.runtime.maintenance import LocalMaintenanceService
from product.backend.infra.samples import OfficialSampleManager
from product.backend.infra.runtime.runner.progress import RunnerProgressReader
from product.backend.infra.recording.request_store import RecordingRequestStore
from product.backend.infra.storage import StorageUnitOfWork
from product.backend.infra.llm.adapters.httpx_transport import HttpxLLMTransport
from product.backend.infra.llm.profiles import LLMProfileRegistry
from product.backend.infra.secrets import SecretStore as LLMSecretStore
from product.backend.infra.secrets import SecretStore, default_secret_store
from product.backend.workflows.test_identities import (
    IdentityPreparationManager,
    TestIdentityExecutionCredentials,
    TestIdentityService,
)
from product.backend.workflows.permission_intents import PermissionIntentService
from product.backend.workflows.source_changes import SourceChangeService
from product.backend.workflows.security_setup import CheckWorkflow, SecuritySetupCompiler
from product.backend.workflows.security_setup.local_observer_registry import (
    LocalObserverEnvironmentRegistry,
)
from product.backend.workflows.onboarding.workflow import FolderSelector, OnboardingWorkflow, SystemFolderSelector
from product.backend.workflows.recording.credentials import RuntimeSecretVault
from product.backend.workflows.recording.run_service import RecordingRunService
from product.backend.workflows.recording.project_submission import ProjectRecordingService
from product.backend.workflows.recording.credentials import RecordingCredentialProvider
from product.backend.workflows.recording.safety_setup import ActionSafetySetupService
from product.backend.workflows.results.services import build_result_services
from product.backend.workflows.control import (
    ProductFlowQuery,
    ProductResultQuery,
    ProductStatusService,
)
from product.backend.workflows.official_sample import OfficialSampleExperience
from product.backend.workflows.competition_validation import (
    CompetitionValidationSummaryQuery,
)


class ApplicationCore:
    """创建基础设施并注册各能力区的应用服务。"""

    def __init__(
        self,
        var_dir: Path,
        *,
        llm_transport=None,
        llm_secret_store: LLMSecretStore | None = None,
        secret_store: SecretStore | None = None,
        environ: Mapping[str, str] | None = None,
        clock_us: Callable[[], int] | None = None,
        folder_selector: FolderSelector | None = None,
        endpoint_discovery=None,
        control_origin: str | None = None,
        official_sample_root: Path | None = None,
    ) -> None:
        from product.backend.infra.storage import create_session_factory, create_sqlite_engine, default_database_path, upgrade_database

        self.var_dir = var_dir.resolve()
        self.paths = RuntimePaths(self.var_dir).ensure_layout()
        self.competition_validation = CompetitionValidationSummaryQuery(self.var_dir)
        self.runner_progress_reader = RunnerProgressReader(self.var_dir)
        self._base_environment = dict(environ if environ is not None else os.environ)
        self._base_environment.pop("JIEJIAN_CONTROL_ORIGIN", None)
        if control_origin is not None:
            # 该值只来自 Serve 已规范化的实际监听 origin，供 Worker/Runner 拒绝自检。
            self._base_environment["JIEJIAN_CONTROL_ORIGIN"] = control_origin
        self.local_observer_environments = LocalObserverEnvironmentRegistry()
        self.official_samples = OfficialSampleManager(
            self.var_dir,
            official_sample_root,
            self._base_environment,
        )
        database_path = default_database_path(self.var_dir)
        upgrade_database(database_path)
        self.engine = create_sqlite_engine(database_path)
        factory = partial(StorageUnitOfWork, create_session_factory(self.engine))
        self.uow_factory = factory
        self.secret_store = secret_store or llm_secret_store or default_secret_store()
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
        self.result_presentation = self.result_services.presentation
        self.repair_contracts = self.result_services.repair
        self.result_history = self.result_services.history
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
            clock_us=clock_us,
        )
        self.projects = ProjectCatalog(factory)
        self.application_understanding = ApplicationUnderstandingService(
            factory,
            endpoint_discovery=endpoint_discovery,
            reserved_control_origin=control_origin,
            clock_us=clock_us,
        )
        self.test_identities = TestIdentityService(
            factory,
            secret_store=self.secret_store,
            clock_us=clock_us,
        )
        self.recording_credentials = RecordingCredentialProvider(
            self.test_identities,
            self.secret_store,
            self.secret_vault,
        )
        self.identity_preparations = IdentityPreparationManager(
            self.var_dir,
            self.test_identities,
            self.secret_store,
            self._base_environment,
        )
        self.maintenance = LocalMaintenanceService(
            self.var_dir,
            active_runtime_paths=lambda: (
                *self.identity_preparations.active_runtime_paths(),
                *(
                    (active.experience_root,)
                    if (active := self.official_samples.active) is not None
                    else ()
                ),
            ),
        )
        from product.backend.workflows.contracts.governance import ContractGovernance

        self.contracts = ContractGovernance(
            factory,
            observer_resolver=self.projects.current_observations,
        )
        self.recording_request_store = RecordingRequestStore(self.var_dir)
        self.action_safety_setup = ActionSafetySetupService(
            factory,
            var_dir=self.var_dir,
            request_store=self.recording_request_store,
            test_identities=self.test_identities,
            clock_us=clock_us,
        )
        self.permission_intents = PermissionIntentService(
            factory,
            test_identities=self.test_identities,
            action_safety_setup=self.action_safety_setup,
            clock_us=clock_us,
        )
        self.application_understanding.set_permission_binding_refresher(
            self.permission_intents.refresh_bindings
        )
        self.source_changes = SourceChangeService(
            factory,
            application_understanding=self.application_understanding,
            permission_intents=self.permission_intents,
            repair_contracts=self.repair_contracts,
            clock_us=clock_us,
        )
        self.action_safety_setup.set_permission_binding_refresher(
            self.permission_intents.refresh_bindings
        )
        self.execution.set_permission_policy_snapshot_resolver(
            self.permission_intents.policy_snapshot
        )
        self.test_identity_execution = TestIdentityExecutionCredentials(
            self.test_identities,
            self.secret_store,
        )
        self.security_setup = SecuritySetupCompiler(
            factory,
            var_dir=self.var_dir,
            permission_intents=self.permission_intents,
            execution_credentials=self.test_identity_execution,
            contracts=self.contracts,
            execution=self.execution,
            local_observer_environment_resolver=(
                self.local_observer_environments.resolve
            ),
        )
        self.execution.set_generated_profile_validator(
            self.security_setup.validate_generated_profile
        )
        self.checks = CheckWorkflow(
            permission_intents=self.permission_intents,
            security_setup=self.security_setup,
            execution=self.execution,
            source_changes=self.source_changes,
            repair_contracts=self.repair_contracts,
        )
        self.project_preparation = ProjectPreparationService(
            factory,
            test_identities=self.test_identities,
            permission_intents=self.permission_intents,
            action_safety_setup=self.action_safety_setup,
            checks=self.checks,
            source_changes=self.source_changes,
        )
        self.project_readiness = ProjectReadinessService(
            factory,
            result_reader=self.results,
            endpoint_status_resolver=self.application_understanding.endpoint_status,
            permission_matrix_resolver=self.permission_intents.matrix,
            check_preview_resolver=self.checks.preview,
            preparation_resolver=self.project_preparation.status,
        )
        self.product_status = ProductStatusService(
            self.projects,
            self.project_readiness.get,
            self.result_presentation,
            self.source_changes,
        )
        self.product_results = ProductResultQuery(
            self.product_status,
            self.result_presentation,
            self.result_history,
        )
        self.product_flows = ProductFlowQuery(self.projects, factory)
        self.official_experience = OfficialSampleExperience(
            self.official_samples,
            self.application_understanding,
            self.test_identities,
            self.secret_store,
            self.local_observer_environments,
            self.product_status,
            repair_contracts=self.repair_contracts,
            source_changes=self.source_changes,
            clock_us=clock_us,
        )
        self.project_lifecycle = ProjectLifecycleService(
            factory,
            self.test_identities,
            stop_official_sample=self.official_experience.stop_project,
            clock_us=clock_us,
        )
        from product.backend.workflows.assistant import GuidanceQueryService

        self.assistant_guidance = GuidanceQueryService(
            self.project_readiness.get,
            self.checks.preview,
        )
        self.recording_submission = RecordingSubmission(
            factory,
            self.recording_request_store,
        )
        self.recording_lifecycle = RecordingLifecycle(factory, var_dir=self.var_dir)
        self.project_recordings = ProjectRecordingService(
            self.application_understanding,
            self.test_identities,
            self.recording_credentials,
            self.recording_submission,
            uow_factory=factory,
            request_store=self.recording_request_store,
            projects=self.projects,
            clock_us=clock_us,
        )
        self.onboarding = OnboardingWorkflow(
            folder_selector
            or SystemFolderSelector(
                environment=self._base_environment,
                var_dir=self.var_dir,
            ),
        )
        self.recording_runs = RecordingRunService(
            self.var_dir,
            self.uow_factory,
            self.recording_submission,
            self.environment_for_secret_names,
        )
        self.llm_profiles = LLMProfileRegistry(
            factory,
            transport=llm_transport or HttpxLLMTransport(),
            secret_store=self.secret_store,
            environ=environ,
            clock_us=clock_us,
        )
        from product.backend.workflows.assistant.service import AssistantService
        from product.backend.workflows.assistant.surfaces import AssistantSurfaceResolver

        self.assistant_service = AssistantService(
            self.var_dir,
            surfaces=AssistantSurfaceResolver(
                guidance=self.assistant_guidance,
                application_understanding=self.application_understanding,
                test_identities=self.test_identities,
                project_readiness=self.project_readiness,
                product_flows=self.product_flows,
                recording_lifecycle=self.recording_lifecycle,
                permission_intents=self.permission_intents,
                check_preview=self.checks.preview,
                result_presentation=self.result_presentation,
            ),
            llm_profiles=self.llm_profiles,
            clock_us=clock_us,
        )
    def close(self) -> None:
        self.identity_preparations.close()
        self.official_experience.close()
        self.secret_vault.clear()
        self.engine.dispose()

    def environment_for_secret_names(self, names) -> dict[str, str]:
        environment = dict(self._base_environment)
        environment.update(self.secret_vault.resolve(names))
        environment.update(self.official_samples.resolve_secret_names(names))
        if hasattr(self, "test_identity_execution"):
            environment.update(self.test_identity_execution.resolve(names))
        return environment
