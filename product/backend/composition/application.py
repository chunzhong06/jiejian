# =============================================================================
# ApplicationCore 组合根
#
# 职责
#   组装 1.1.0 当前启动、项目接入、Business Boundary、TestIdentity 与只读结果基础能力。
#
# 边界
#   旧 Permission writer、Preparation、Check、SourceChange、Recording 和 Run 不注册为 CURRENT。
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
from product.backend.infra.runtime.jobs.targets import default_run_job_targets
from product.backend.infra.runtime.maintenance import LocalMaintenanceService
from product.backend.infra.runtime.paths import RuntimePaths
from product.backend.infra.secrets import SecretStore as LLMSecretStore
from product.backend.infra.secrets import SecretStore, default_secret_store
from product.backend.infra.storage import StorageUnitOfWork
from product.backend.workflows.application_understanding.service import ApplicationUnderstandingService
from product.backend.workflows.business_boundaries import BusinessBoundaryService
from product.backend.workflows.business_boundaries.status import BoundaryWorkspaceStatusService
from product.backend.workflows.onboarding.workflow import FolderSelector, OnboardingWorkflow, SystemFolderSelector
from product.backend.workflows.permission_intents import PermissionIntentService
from product.backend.workflows.projects.catalog import ProjectCatalog
from product.backend.workflows.projects.lifecycle import ProjectLifecycleService
from product.backend.workflows.test_identities import TestIdentityService


class ApplicationCore:
    """创建 fresh 1.1.0 基础设施并只注册已经切换到稳定业务边界的能力。"""

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

        # Worker 生命周期仍需要现有 Job/Result 基础表；控制面不重新开放旧 Run writer。
        self.job_targets = default_run_job_targets()
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
        self.product_status = BoundaryWorkspaceStatusService(
            factory,
            self.business_boundaries,
        )
        self.permission_intents = PermissionIntentService(factory)
        self.test_identities = TestIdentityService(
            factory,
            secret_store=self.secret_store,
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
            active_runtime_paths=lambda: (),
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
        """释放组合根独占的 Engine；没有启动的旧能力无需补偿关闭。"""

        self.engine.dispose()

    def environment_for_secret_names(self, names) -> dict[str, str]:
        _ = names
        return dict(self._base_environment)
