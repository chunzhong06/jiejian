# =============================================================================
# ApplicationCore 组合根
#
# 职责
#   组装 当前启动、项目接入、动作级 Workspace、Business Boundary 与 TestIdentity。
#
# 边界
#   显式装配业务准备、当前 CHECK 与 Recording；不恢复旧 Contract/Profile 或 SourceChange writer。
# =============================================================================

from __future__ import annotations

import os
import time
from collections.abc import Mapping
from functools import partial
from pathlib import Path
from typing import Callable

from product.backend.infra.llm.adapters.httpx_transport import HttpxLLMTransport
from product.backend.infra.llm.profiles import LLMProfileRegistry
from product.backend.infra.runtime.jobs.attempts import JobAttempts
from product.backend.infra.runtime.jobs.queue import JobQueue
from product.backend.infra.runtime.jobs.targets import current_check_and_recording_targets
from product.backend.infra.runtime.worker.supervisor import LocalWorkerSupervisor
from product.backend.infra.recording.request_store import RecordingRequestStore
from product.backend.infra.runtime.maintenance import LocalMaintenanceService
from product.backend.infra.runtime.paths import RuntimePaths
from product.backend.infra.secrets import SecretStore as LLMSecretStore
from product.backend.infra.secrets import SecretStore, default_secret_store
from product.backend.infra.storage import StorageUnitOfWork
from product.backend.workflows.application_understanding.service import ApplicationUnderstandingService
from product.backend.workflows.business_boundaries import BusinessBoundaryService
from product.backend.workflows.onboarding.workflow import FolderSelector, OnboardingWorkflow, SystemFolderSelector
from product.backend.workflows.permission_intents import PermissionIntentService
from product.backend.workflows.projects.catalog import ProjectCatalog
from product.backend.workflows.projects.lifecycle import ProjectLifecycleService
from product.backend.workflows.test_identities import TestIdentityService
from product.backend.workflows.test_identities.preparation import IdentityPreparationManager
from product.backend.workflows.assistant.current_surfaces import PreparationAssistantSurfaceResolver
from product.backend.workflows.assistant.service import AssistantService
from product.backend.workflows.permission_drafting import PermissionDraftService
from product.backend.workflows.workspace import WorkspaceService
from product.backend.workflows.preparation.bindings import PreparationBindingService
from product.backend.workflows.preparation.service import PreparationService
from product.backend.workflows.recording.credentials import RecordingCredentialProvider, RuntimeSecretVault
from product.backend.workflows.recording.lifecycle import RecordingLifecycle
from product.backend.workflows.recording.project_submission import ProjectRecordingService
from product.backend.workflows.recording.submission import RecordingSubmission
from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.workflows.checks.registry import CheckRuntimeRegistry
from product.backend.workflows.checks.runtime_bundle import CheckRuntimeBuilder
from product.backend.workflows.checks.service import CheckService
from product.backend.workflows.checks.results import CheckResultReader
from product.backend.workflows.checks.story import CheckStoryBuilder
from product.backend.workflows.test_identities.execution import TestIdentityExecutionCredentials
from product.backend import __version__


class ApplicationCore:
    """创建基础设施并只注册动作级工作区已经接线的能力。"""

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
        from product.backend.infra.storage import (
            create_session_factory,
            create_sqlite_engine,
            default_database_path,
            upgrade_database,
        )

        self.var_dir = var_dir.resolve()
        self.paths = RuntimePaths(self.var_dir).ensure_layout()
        self._base_environment = dict(environ if environ is not None else os.environ)
        self._base_environment.pop("JIEJIAN_CONTROL_ORIGIN", None)
        if control_origin is not None:
            self._base_environment["JIEJIAN_CONTROL_ORIGIN"] = control_origin
        database_path = default_database_path(self.var_dir)
        upgrade_database(database_path)
        self.engine = create_sqlite_engine(database_path)
        factory = partial(StorageUnitOfWork, create_session_factory(self.engine))
        self.uow_factory = factory
        from product.backend.infra.runtime.session_secrets import SessionSecretOverlay
        self.secret_store = SessionSecretOverlay(secret_store or llm_secret_store or default_secret_store())

        self.job_targets = current_check_and_recording_targets()
        self.job_attempts = JobAttempts(factory, targets=self.job_targets)
        self.job_queue = JobQueue(factory, targets=self.job_targets)
        self.projects = ProjectCatalog(factory)
        self.application_understanding = ApplicationUnderstandingService(
            factory,
            endpoint_discovery=endpoint_discovery,
            reserved_control_origin=control_origin,
            clock_us=clock_us,
        )
        self.business_boundaries = BusinessBoundaryService(factory, clock_us=clock_us)
        self.permission_intents = PermissionIntentService(factory)
        self.test_identities = TestIdentityService(
            factory,
            secret_store=self.secret_store,
            clock_us=clock_us,
        )
        self.check_registry = CheckRuntimeRegistry()
        self.check_credentials = TestIdentityExecutionCredentials(self.test_identities, self.secret_store)
        self.preparation_bindings = PreparationBindingService(
            factory, self.var_dir, test_identities=self.test_identities,
            registered_observers=self.check_registry, effect_proofs=self.check_registry,
        )
        self.preparation = PreparationService(
            self.business_boundaries, self.test_identities, bindings=self.preparation_bindings,
            uow_factory=factory, clock_us=clock_us,
        )
        self.check_runtime_builder = CheckRuntimeBuilder(uow_factory=factory, var_dir=self.var_dir,
            preparation=self.preparation, business_boundaries=self.business_boundaries,
            credentials=self.check_credentials, registry=self.check_registry)
        self.checks = CheckService(uow_factory=factory, var_dir=self.var_dir, preparation=self.preparation,
            business_boundaries=self.business_boundaries, runtime_builder=self.check_runtime_builder,
            registry=self.check_registry, queue=self.job_queue, engine_version=__version__, clock_us=clock_us,
            source_inspector=self.application_understanding.inspect_source_fingerprint)
        self.check_results = CheckResultReader(var_dir=self.var_dir, uow_factory=factory)
        self.check_story = CheckStoryBuilder(self.check_results)
        from product.backend.workflows.changes import CurrentSourceChangeService
        from product.backend.workflows.checks.repair import CurrentRepairService
        self.source_changes = CurrentSourceChangeService(uow_factory=factory,understanding=self.application_understanding,
            boundaries=self.business_boundaries,clock_us=clock_us)
        self.check_repairs = CurrentRepairService(reader=self.check_results,change_context_reader=self.source_changes.context,
            breakpoint_reader=lambda run,case:next(item.breakpoint for item in self.check_story.build(run,include_repair=False).actions if item.case_id==case))
        self.source_changes.set_dependencies(plan_reader=self.checks.preview,repair_resolver=self.check_repairs.resolve)
        self.checks.set_revalidation_services(changes=self.source_changes,repairs=self.check_repairs)
        self.check_story.repairs = self.check_repairs
        from product.backend.workflows.projects.repair import CurrentProjectRepairService
        self.project_repair = CurrentProjectRepairService(reader=self.check_results,repairs=self.check_repairs,
            changes=self.source_changes,boundaries=self.business_boundaries,pending_request_reader=self.checks.pending_request)
        self.workspace = WorkspaceService(factory, self.business_boundaries, preparation=self.preparation, var_dir=self.var_dir)
        self.workspace.set_current_checks(checks=self.checks,reader=self.check_results,changes=self.source_changes,
            repairs=self.project_repair,source_inspector=self.application_understanding.inspect_source_fingerprint)
        self.identity_preparations = IdentityPreparationManager(
            self.var_dir, self.test_identities, self.secret_store, self._base_environment,
            application_understanding=self.application_understanding,
            business_boundaries=self.business_boundaries,
        )
        self.runtime_secrets = RuntimeSecretVault()
        self.recording_credentials = RecordingCredentialProvider(
            self.test_identities, self.secret_store, self.runtime_secrets,
        )
        self.recording_request_store = RecordingRequestStore(self.var_dir)
        self.recording_lifecycle = RecordingLifecycle(
            factory, var_dir=self.var_dir, bindings=self.preparation_bindings,
        )
        self.recording_submission = RecordingSubmission(
            factory, self.recording_request_store, attempts=self.job_attempts,
            finalize_recording=self.recording_lifecycle.finalize_if_unambiguous,
        )
        self.project_recordings = ProjectRecordingService(
            self.application_understanding, self.test_identities, self.recording_credentials,
            self.recording_submission, business_boundaries=self.business_boundaries,
            uow_factory=factory, request_store=self.recording_request_store,
            projects=self.projects, clock_us=clock_us,
            preparation=self.preparation,
        )
        self.worker = LocalWorkerSupervisor(
            self.var_dir, factory, self.job_queue, self.job_attempts,
            targets=self.job_targets, environment_provider=self.environment_for_secret_names,
            clock_us=clock_us,
        )
        self.project_lifecycle = ProjectLifecycleService(
            factory,
            self.test_identities,
            stop_official_sample=lambda project_id: self.official_experience.stop_project(project_id),
            clock_us=clock_us,
        )
        self.maintenance = LocalMaintenanceService(
            self.var_dir,
            active_runtime_paths=lambda: (
                self.paths.runtime, self.paths.worker_logs, self.paths.recording_logs,
            ) + self.identity_preparations.active_runtime_paths() if self.worker.is_running()
            else self.identity_preparations.active_runtime_paths(),
        )
        self.onboarding = OnboardingWorkflow(
            folder_selector
            or SystemFolderSelector(
                environment=self._base_environment,
                var_dir=self.var_dir,
            )
        )
        self.llm_profiles = LLMProfileRegistry(
            factory,
            transport=llm_transport or HttpxLLMTransport(),
            secret_store=self.secret_store,
            environ=environ,
            clock_us=clock_us,
        )

        self.assistant_surfaces = PreparationAssistantSurfaceResolver(
            business_boundaries=self.business_boundaries,
            application_understanding=self.application_understanding,
            preparation=self.preparation, recording_lifecycle=self.recording_lifecycle, uow_factory=factory,
            check_story=self.check_story,
        )
        self.assistant_service = AssistantService(self.var_dir, surfaces=self.assistant_surfaces,
            llm_profiles=self.llm_profiles, clock_us=clock_us)
        self.permission_drafts = PermissionDraftService(business_boundaries=self.business_boundaries,
            llm_profiles=self.llm_profiles)
        from product.backend.infra.samples import OfficialSampleManager
        from product.backend.workflows.official_sample import OfficialSampleExperience
        from product.backend.workflows.official_scenario import OfficialScenarioInstaller
        self.official_samples = OfficialSampleManager(self.var_dir, official_sample_root, self._base_environment)
        self.official_scenario = OfficialScenarioInstaller(self.project_recordings, self.recording_submission,
            self.job_attempts, var_dir=self.var_dir, recording_credentials=self.recording_credentials,
            lifecycle=self.recording_lifecycle, clock_us=clock_us or (lambda: time.time_ns() // 1000), preparation=self.preparation)
        self.official_experience = OfficialSampleExperience(self.official_samples, understanding=self.application_understanding,
            boundaries=self.business_boundaries, identities=self.test_identities, secret_store=self.secret_store,
            registry=self.check_registry, installer=self.official_scenario, bindings=self.preparation_bindings,
            preparation=self.preparation, changes=self.source_changes, repairs=self.check_repairs,
            uow_factory=factory, var_dir=self.var_dir, archive_project=self.project_lifecycle.archive, clock_us=clock_us)

    def close(self) -> None:
        """先确认录制、登录进程及调度线程退出，再清空短期秘密和释放数据库。"""

        self.worker.stop()
        self.official_experience.close()
        self.identity_preparations.close()
        self.runtime_secrets.clear()
        self.secret_store.clear()
        self.engine.dispose()

    def environment_for_secret_names(self, names) -> dict[str, str]:
        values = self.runtime_secrets.resolve(names)
        values.update(self.official_samples.resolve_secret_names(tuple(name for name in names if name not in values)))
        values.update(self.check_credentials.resolve(tuple(name for name in names if name not in values)))
        for name in names:
            if name not in values and not name.startswith("JIEJIAN_RECORDING_") and self._base_environment.get(name):
                values[name] = self._base_environment[name]
        if any(name not in values for name in names):
            raise JiejianError(ErrorCode.TEST_IDENTITY_NOT_READY, "执行身份与所需凭据类型不一致，请重新生成检查配置")
        environment = {key: value for key, value in self._base_environment.items()
                       if not key.startswith("JIEJIAN_RECORDING_")}
        environment.update(values)
        return environment

    def worker_status(self) -> dict[str, object]:
        """控制面与 MCP 共享实际线程及已装配能力事实，不据线程存活推断检查可用。"""
        capabilities = self.worker.capabilities
        return {
            "worker": "running" if self.worker.is_running() and "RECORDING" in capabilities else "stopped",
            "worker_capabilities": capabilities,
            "check": "available" if "CHECK" in capabilities else "unavailable",
            "recovered_jobs": self.worker.recovered_jobs,
        }
