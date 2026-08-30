# 验证应用工作流中的应用容器组装。

from __future__ import annotations

import inspect

from product.backend.workflows.context import ApplicationCore
from product.backend.infra.runtime.jobs.targets import JobTargetType
from product.backend.worker_container import WorkerContainer


def test_application_and_worker_containers_are_independent_and_complete(tmp_path) -> None:
    application = ApplicationCore(tmp_path / "application-var", environ={})
    worker = WorkerContainer(tmp_path / "worker-var", environ={})
    try:
        assert not isinstance(worker, ApplicationCore)
        assert "_minimal" not in inspect.signature(ApplicationCore).parameters
        assert not hasattr(application, "_minimal")
        assert not hasattr(application, "build_job_handler_registry")
        assert not hasattr(application, "run_recording")
        assert not hasattr(application, "run_demo")
        assert not hasattr(application, "guide_snapshot")
        assert application.result_services.finalizer._reports is application.result_services.reports
        assert application.results is application.result_services.reader
        assert application.findings is application.result_services.queries
        assert application.product_results._presentation is application.result_presentation
        assert application.product_results._history is application.result_history
        assert application.product_status._result_presentation is application.result_presentation
        assert worker.result_services.finalizer._reports is worker.result_services.reports
        assert worker.handler_factory._publication is worker.run_publisher
        assert worker.handler_factory._reconciliation is worker.run_reconciler
        assert not hasattr(worker, "cache")
        assert not hasattr(worker, "onboarding")
        assert not hasattr(worker, "demo")
        assert not hasattr(worker, "llm_profiles")
        assert worker.handler_factory.build_artifact_check_handler() is not None
        assert worker.job_queue is not None
        assert worker.job_attempts is not None
    finally:
        worker.close()
        application.close()


def test_worker_handler_factory_registers_run_recording_and_artifact_handlers(tmp_path) -> None:
    worker = WorkerContainer(tmp_path / "worker-var", environ={})
    try:
        registry = worker.handler_factory.build_registry("container-test-worker", {})
        assert registry.resolve_auxiliary("ARTIFACT_CHECK") is not None
        assert set(registry._factories) == {
            JobTargetType.RUN,
            JobTargetType.RECORDING,
        }
    finally:
        worker.close()
