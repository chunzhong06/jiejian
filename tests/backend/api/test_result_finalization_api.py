# 验证后端 API中的结果定稿接口。

from __future__ import annotations

from contextlib import contextmanager
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from product.backend.api.routers.results import build_results_router
from product.backend.api.routers.runs import build_runs_router
from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.core.lifecycle import RunLifecycle
from product.backend.infra.storage import BaseReportFinalizationState, FindingFinalizationState
from tests.fixtures.control_plane import TestClient, create_app


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


def test_presentation_and_history_are_read_only_v2_views() -> None:
    calls: list[tuple[str, str]] = []

    class ViewBuilder:
        def __init__(self, name: str, payload: dict[str, object]) -> None:
            self.name = name
            self.payload = payload

        def build(self, key: str):
            calls.append((self.name, key))
            return SimpleNamespace(model_dump=lambda **_: self.payload)

    context = SimpleNamespace(
        result_presentation=ViewBuilder("presentation", {"run_id": RUN_ID, "headline": "发现权限问题"}),
        result_history=ViewBuilder("history", {"project_id": "project_demo", "comparisons": [{"changes": [{"status": "NOT_COVERED", "status_label": "本次未覆盖"}]}]}),
        projects=SimpleNamespace(get=lambda project_id: calls.append(("project", project_id)) or object()),
    )
    app = FastAPI()
    app.include_router(build_results_router(context, SimpleNamespace()))
    with TestClient(app) as client:
        presentation = client.get(f"/api/runs/{RUN_ID}/presentation")
        history = client.get("/api/projects/project_demo/results/history")

    assert presentation.status_code == history.status_code == 200
    assert presentation.json()["schema_version"] == "1"
    assert presentation.json()["data"] == {"run_id": RUN_ID, "headline": "发现权限问题"}
    assert "schema_version" not in presentation.json()["data"]
    assert history.json()["data"]["project_id"] == "project_demo"
    assert history.json()["data"]["comparisons"][0]["changes"][0]["status_label"] == "本次未覆盖"
    assert "schema_version" not in history.json()["data"]
    assert calls == [
        ("presentation", RUN_ID),
        ("project", "project_demo"),
        ("history", "project_demo"),
    ]


def test_report_view_reads_published_html_with_exact_browser_headers() -> None:
    class Reports:
        def __init__(self) -> None:
            self.calls: list[tuple[str, str, str]] = []
            self.broken = False

        def read_format(self, run_id: str, report_id: str, output_format: str) -> bytes:
            self.calls.append((run_id, report_id, output_format))
            if self.broken:
                raise JiejianError(ErrorCode.REPORT_INTEGRITY, "报告发布包完整性校验失败")
            return b"<html>published</html>"

    reports = Reports()
    app = FastAPI()

    async def handle_error(_request, error: JiejianError):
        return JSONResponse(status_code=409, content={"code": error.code})

    app.add_exception_handler(JiejianError, handle_error)
    app.include_router(
        build_results_router(
            SimpleNamespace(reports=reports, result_finalizer=SimpleNamespace()),
            SimpleNamespace(),
        )
    )
    report_id = "report_" + "b" * 32
    with TestClient(app) as client:
        view = client.get(f"/api/runs/{RUN_ID}/reports/{report_id}/view")
        download = client.get(f"/api/runs/{RUN_ID}/reports/{report_id}/formats/html")
        reports.broken = True
        tampered = client.get(f"/api/runs/{RUN_ID}/reports/{report_id}/view")

    assert view.status_code == 200
    assert view.content == b"<html>published</html>"
    assert view.headers["content-type"] == "text/html; charset=utf-8"
    assert view.headers["content-disposition"] == 'inline; filename="report.html"'
    assert view.headers["content-security-policy"] == (
        "default-src 'none'; style-src 'unsafe-inline'; script-src 'none'; "
        "img-src 'none'; font-src 'none'; connect-src 'none'; media-src 'none'; "
        "object-src 'none'; frame-src 'none'; child-src 'none'; form-action 'none'; "
        "base-uri 'none'; frame-ancestors 'self'"
    )
    assert view.headers["x-content-type-options"] == "nosniff"
    assert view.headers["referrer-policy"] == "no-referrer"
    assert download.status_code == 200
    assert download.content == view.content
    assert download.headers["content-disposition"] == 'attachment; filename="report.html"'
    assert tampered.status_code == 409
    assert tampered.json() == {"code": ErrorCode.REPORT_INTEGRITY.value}
    assert reports.calls == [
        (RUN_ID, report_id, "html"),
        (RUN_ID, report_id, "html"),
        (RUN_ID, report_id, "html"),
    ]


def test_gate_report_is_explicit_write_and_requires_gate_result_id() -> None:
    class Reports:
        def __init__(self) -> None:
            self.calls: list[tuple[str, str]] = []

        def generate_gate(self, run_id: str, gate_result_id: str):
            self.calls.append((run_id, gate_result_id))
            return SimpleNamespace(model_dump=lambda **_: {"schema_version": "1", "report_type": "GATE", "report_id": "report_" + "b" * 32})

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
    assert order == ["publication", "finalization", "worker", "cache"]
