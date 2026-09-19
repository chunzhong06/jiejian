# 验证当前两个组合根的空库装配与惰性 CHECK/Recording 注册，不启动任务进程。
from __future__ import annotations

from contextlib import ExitStack, closing
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from product.backend.composition import ApplicationCore
from product.backend.composition.worker import WorkerContainer
from product.backend.core.errors import JiejianError
from product.backend.infra.runtime.jobs.targets import JobTargetType
from product.backend.infra.runtime.worker.supervisor import LocalWorkerSupervisor
from product.backend.infra.storage import default_database_path, upgrade_database


def test_application_and_worker_containers_are_independent_and_complete(tmp_path, monkeypatch) -> None:
    def forbidden_start(*args, **kwargs):
        pytest.fail("组合测试不允许启动 Worker 或目标进程")

    monkeypatch.setattr(LocalWorkerSupervisor, "start", forbidden_start)
    store = Mock()
    store.read.side_effect = AssertionError("组合测试不允许读取秘密")
    store.write.side_effect = AssertionError("组合测试不允许写入秘密")
    worker_var = tmp_path / "worker-var"
    upgrade_database(default_database_path(worker_var))
    # Worker 只校验现有库；先用正式 migration 创建隔离空库，并保证部分构造失败也关闭已有容器。
    with ExitStack() as stack:
        application = stack.enter_context(closing(ApplicationCore(
            tmp_path / "application-var", environ={}, secret_store=store, llm_secret_store=store,
        )))
        worker = stack.enter_context(closing(WorkerContainer(worker_var, environ={})))
        assert not isinstance(worker, ApplicationCore)
        assert type(application.worker) is LocalWorkerSupervisor
        assert not application.worker.is_running()
        assert application.worker.capabilities == ("CHECK", "RECORDING")
        assert application.check_story._reader is application.check_results
        assert application.check_repairs._reader is application.check_results
        assert application.check_story.repairs is application.check_repairs
        assert application.project_repair._reader is application.check_results
        assert application.project_repair._repairs is application.check_repairs
        assert application.project_repair._changes is application.source_changes
        for retired in ("result_services", "product_results", "product_status", "project_readiness", "project_preparation"):
            assert not hasattr(application, retired)
        for product_only in ("workspace", "project_repair", "product_status", "result_services",
                             "onboarding", "llm_profiles", "project_preparation"):
            assert not hasattr(worker, product_only)
        assert set(worker.job_targets.target_types) == {JobTargetType.RUN, JobTargetType.RECORDING}
        assert worker.handler_factory is not None
        assert worker.job_queue is not None
        assert worker.job_attempts is not None
    assert not application.worker.is_running()
    assert worker._closed
    store.read.assert_not_called()
    store.write.assert_not_called()


def test_worker_registry_only_allows_check_and_recording_without_constructing_handlers(tmp_path) -> None:
    var_dir = tmp_path / "worker-var"
    upgrade_database(default_database_path(var_dir))
    with closing(WorkerContainer(var_dir, environ={})) as worker:
        registry = worker.handler_factory.build_registry("container-test-worker", {})
        assert set(registry._factories) == {JobTargetType.RUN, JobTargetType.RECORDING}
        assert registry._operation_types == {JobTargetType.RUN: frozenset({"CHECK"})}
        assert registry._auxiliary_factories == {}
        # 只验证旧 operation 在工厂调用前被拒绝，不解析合法任务或启动 Handler。
        with pytest.raises(JiejianError):
            registry.resolve(SimpleNamespace(run_id="run-old", recording_id=None, operation_type="RUN"))
