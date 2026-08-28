# 验证后端 API中的结果闸门接口。

from __future__ import annotations

from contextlib import contextmanager
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from product.backend.api.routers.gating import build_gating_router
from product.backend.cli.app import app as cli_app


BASELINE_ID = "baseline_" + "a" * 32
RUN_ID = "run_" + "b" * 32
GATE_ID = "gate_" + "c" * 32


class _FakeGating:
    def accept_baseline(self, run_id: str, **kwargs):
        return {"schema_version": "1", "baseline_id": BASELINE_ID, "project_id": "project-api", "accepted_run_id": run_id, "actor": kwargs["actor"], "reason": kwargs["reason"]}

    def get_baseline(self, baseline_id: str):
        return {"schema_version": "1", "baseline_id": baseline_id}

    def evaluate(self, baseline_id: str, run_id: str, *, policy):
        return {"schema_version": "1", "gate_result_id": GATE_ID, "baseline_id": baseline_id, "run_id": run_id, "policy_version": policy.policy_version, "decision": "PASS", "reasons": [], "input_hash": "d" * 64, "evaluated_at_us": 1}

    def latest_gate_result(self, baseline_id: str, run_id: str):
        return {"schema_version": "1", "gate_result_id": GATE_ID, "baseline_id": baseline_id, "run_id": run_id, "decision": "PASS"}

    def get_gate_result(self, gate_result_id: str):
        return {"schema_version": "1", "gate_result_id": gate_result_id, "decision": "PASS"}


def test_api_uses_explicit_baseline_and_gate_paths() -> None:
    app = FastAPI()
    app.include_router(build_gating_router(SimpleNamespace(gating=_FakeGating())))
    with TestClient(app) as client:
        accepted = client.post(
            "/api/projects/project-api/baselines",
            json={"schema_version": "1", "accepted_run_id": RUN_ID, "actor": "operator", "reason": "fixed run"},
        )
        evaluated = client.post(
            f"/api/baselines/{BASELINE_ID}/runs/{RUN_ID}/gate",
            json={"schema_version": "1", "minimum_severity": "low"},
        )
        read = client.get(f"/api/gates/{GATE_ID}")
    assert accepted.status_code == evaluated.status_code == read.status_code == 200
    assert evaluated.json()["data"]["decision"] == read.json()["data"]["decision"] == "PASS"


def test_new_cli_gate_mode_returns_gate_decision_exit_code(monkeypatch) -> None:
    fake_context = SimpleNamespace(gating=_FakeGating(), close=lambda: None)
    @contextmanager
    def fake_scope(_context):
        yield fake_context

    monkeypatch.setattr("product.backend.cli.commands.gating.application_scope", fake_scope)
    result = CliRunner().invoke(
        cli_app,
        ["system", "advanced", "gate", "evaluate", BASELINE_ID, RUN_ID],
    )
    assert result.exit_code == 0
    assert '"decision":"PASS"' in result.stdout


def test_baseline_cli_requires_explicit_actor() -> None:
    result = CliRunner().invoke(
        cli_app,
        [
            "system",
            "advanced",
            "baseline",
            "accept",
            RUN_ID,
            "--reason",
            "fixed run",
        ],
    )
    assert result.exit_code != 0
    assert "--actor" in result.output
