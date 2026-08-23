from __future__ import annotations

from contextlib import contextmanager
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from product.backend.api.app import create_app
from product.backend.api.routers.results import build_results_router
from product.backend.api.routers.runs import build_runs_router
from product.backend.core.lifecycle import RunLifecycle
from product.backend.infra.storage import BaseReportFinalizationState, FindingFinalizationState


RUN_ID = "run_" + "a" * 32


class _State:
    def __init__(self, *, findings_state: FindingFinalizationState) -> None:
        self.findings_state = findings_state
        self.base_report_state = BaseReportFinalizationState.BLOCKED

    def model_dump(self, *, mode: str):
        assert mode == "json"
        return {
            "schema_version": "1",
            "run_id": RUN_ID,
            "findings_state": self.findings_state.value,
            "base_report_state": self.base_report_state.value,
        }


class _Finalizer:
    def __init__(self) -> None:
        self.repairs: list[str] = []

    def status(self, run_id: str):
        assert run_id == RUN_ID
        return _State(findings_state=FindingFinalizationState.PENDING)

    def repair(self, run_id: str):
        self.repairs.append(run_id)
        return _State(findings_state=FindingFinalizationState.COMPLETE)


def test_result_status_is_read_only_and_repair_is_explicit_write() -> None:
    finalizer = _Finalizer()
    context = SimpleNamespace(
        result_finalizer=finalizer,
        findings=SimpleNamespace(findings_for_run=lambda _run_id: []),
        reports=SimpleNamespace(),
    )
    app = FastAPI()
    app.include_router(build_results_router(context, SimpleNamespace()))
    with TestClient(app) as client:
        status = client.get(f"/api/runs/{RUN_ID}/result-status")
        assert finalizer.repairs == []
        repaired = client.post(f"/api/runs/{RUN_ID}/result-repair")
    assert status.status_code == repaired.status_code == 200
    assert status.json()["data"]["findings_state"] == "PENDING"
    assert repaired.json()["data"]["findings_state"] == "COMPLETE"
    assert finalizer.repairs == [RUN_ID]


def test_gate_report_is_explicit_write_and_requires_gate_result_id() -> None:
    class Reports:
        def __init__(self) -> None:
            self.calls: list[tuple[str, str]] = []

        def generate_gate(self, run_id: str, gate_result_id: str):
            self.calls.append((run_id, gate_result_id))
            return SimpleNamespace(model_dump=lambda **_: {"schema_version": "4", "report_type": "GATE", "report_id": "report_" + "b" * 32})

    reports = Reports()
    context = SimpleNamespace(
        result_finalizer=SimpleNamespace(),
        reports=reports,
    )
    app = FastAPI()
    app.include_router(build_results_router(context, SimpleNamespace()))
    with TestClient(app) as client:
        response = client.post(f"/api/runs/{RUN_ID}/reports/gate", json={"schema_version": "1", "gate_result_id": "gate_" + "c" * 32})
        extra = client.post(f"/api/runs/{RUN_ID}/reports/gate", json={"schema_version": "1", "gate_result_id": "gate_" + "c" * 32, "run_id": RUN_ID})
    assert response.status_code == 200
    assert extra.status_code == 422
    assert reports.calls == [(RUN_ID, "gate_" + "c" * 32)]


def test_run_detail_includes_read_only_finalization_summary() -> None:
    run = SimpleNamespace(
        run_id=RUN_ID,
        lifecycle=RunLifecycle.COMPLETED,
        model_dump=lambda **_kwargs: {
            "schema_version": "1",
            "run_id": RUN_ID,
            "lifecycle": "COMPLETED",
        },
    )
    job = SimpleNamespace(model_dump=lambda **_kwargs: {"schema_version": "1", "job_id": "job_" + "a" * 32})

    @contextmanager
    def uow_factory():
        yield SimpleNamespace(
            runs=SimpleNamespace(get=lambda _run_id: run),
            jobs=SimpleNamespace(get_by_run=lambda _run_id: job),
        )

    finalization = SimpleNamespace(
        findings_state=FindingFinalizationState.COMPLETE,
        base_report_state=BaseReportFinalizationState.FAILED,
        base_report_id=None,
        findings_error_code=None,
        base_report_error_code="REPORT_PUBLISH_FAILED",
    )
    context = SimpleNamespace(
        uow_factory=uow_factory,
        result_finalizer=SimpleNamespace(status=lambda _run_id: finalization),
        findings=SimpleNamespace(findings_for_run=lambda _run_id: [{"finding": "one"}]),
    )
    results = SimpleNamespace(
        read=lambda _run_id: object(),
        overview=lambda _run_id, *, published: {"schema_version": "1"},
    )
    app = FastAPI()
    app.include_router(build_runs_router(context, results))
    with TestClient(app) as client:
        response = client.get(f"/api/runs/{RUN_ID}")
    assert response.status_code == 200
    assert response.json()["data"]["finding_count"] == 1
    assert response.json()["data"]["finalization"] == {
        "findings_state": "COMPLETE",
        "base_report_state": "FAILED",
        "base_report_id": None,
        "last_error_code": "REPORT_PUBLISH_FAILED",
    }


def test_startup_reconciliation_order_places_finalizer_before_worker(tmp_path, monkeypatch) -> None:
    order: list[str] = []
    app = create_app(tmp_path / "var", start_worker=True)
    monkeypatch.setattr(
        app.state.context.cache,
        "startup_maintenance",
        lambda: order.append("cache") or {},
    )

    class _RunReconciler:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        def reconcile(self):
            order.append("publication")
            return {}

    monkeypatch.setattr(
        "product.backend.infra.runtime.jobs.reconciliation.RunReconciler",
        _RunReconciler,
    )
    monkeypatch.setattr(
        app.state.context.result_finalizer,
        "reconcile",
        lambda: order.append("finalization") or {},
    )
    monkeypatch.setattr(
        app.state.worker_supervisor,
        "start",
        lambda: order.append("worker"),
    )
    with TestClient(app):
        pass
    assert order == ["cache", "publication", "finalization", "worker"]
