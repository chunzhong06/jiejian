# =============================================================================
# ApplicationCore 组合根
#
# 职责
#   组装 当前启动、项目接入、动作级 Workspace、Business Boundary 与 TestIdentity。
#
# 边界
#   只装配业务准备与录制 Worker；不开放旧 Permission writer、Check、SourceChange 或 Run。
# =============================================================================

from __future__ import annotations

import os
from collections.abc import Mapping
from functools import partial
from pathlib import Path
from typing import Callable

from product.backend.infra.llm.adapters.httpx_transport import HttpxLLMTransport
from product.backend.infra.llm.profiles import LLMProfileRegistry
from product.backend.infra.runtime.jobs.attempts import JobAttempts
from product.backend.infra.runtime.jobs.queue import JobQueue
from product.backend.infra.runtime.jobs.targets import recording_job_targets
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
from product.backend.workflows.workspace import WorkspaceService
from product.backend.workflows.preparation.bindings import PreparationBindingService
from product.backend.workflows.preparation.service import PreparationService
from product.backend.workflows.recording.credentials import RecordingCredentialProvider, RuntimeSecretVault
from product.backend.workflows.recording.lifecycle import RecordingLifecycle
from product.backend.workflows.recording.project_submission import ProjectRecordingService
from product.backend.workflows.recording.submission import RecordingSubmission
from product.backend.core.errors import ErrorCode, JiejianError


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

        _ = official_sample_root
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
        self.secret_store = secret_store or llm_secret_store or default_secret_store()

        self.job_targets = recording_job_targets()
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
        self.workspace = WorkspaceService(
            factory,
            self.business_boundaries,
        )
        self.permission_intents = PermissionIntentService(factory)
        self.test_identities = TestIdentityService(
            factory,
            secret_store=self.secret_store,
            clock_us=clock_us,
        )
        self.preparation_bindings = PreparationBindingService(
            factory, self.var_dir, test_identities=self.test_identities,
        )
        self.preparation = PreparationService(
            self.business_boundaries, self.test_identities, bindings=self.preparation_bindings,
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
        )
        self.worker = LocalWorkerSupervisor(
            self.var_dir, factory, self.job_queue, self.job_attempts,
            targets=self.job_targets, environment_provider=self.environment_for_secret_names,
            clock_us=clock_us,
        )
        self.project_lifecycle = ProjectLifecycleService(
            factory,
            self.test_identities,
            stop_official_sample=lambda _project_id: False,
            clock_us=clock_us,
        )
        self.maintenance = LocalMaintenanceService(
            self.var_dir,
            active_runtime_paths=lambda: (
                self.paths.runtime, self.paths.worker_logs, self.paths.recording_logs,
            ) if self.worker.is_running() else (),
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

    def close(self) -> None:
        """先证明录制进程与调度线程退出，再清空短期秘密和释放数据库。"""

        self.worker.stop()
        self.runtime_secrets.clear()
        self.engine.dispose()

    def environment_for_secret_names(self, names) -> dict[str, str]:
        values = self.runtime_secrets.resolve(names)
        if any(name not in values for name in names):
            raise JiejianError(ErrorCode.TEST_IDENTITY_NOT_READY, "录制会话已失效，请重新准备测试账号")
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
            "check": "unavailable",
            "recovered_jobs": self.worker.recovered_jobs,
        }
