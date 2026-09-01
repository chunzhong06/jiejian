# 验证协作空间经正式编译、Worker、Runner、六 Observer 和结果发布形成三态 Golden。

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path

import pytest

from tests.fixtures.collaboration_golden import (
    InMemorySecretStore,
)
from tests.fixtures.control_plane import TestClient, create_app
from tests.fixtures.runtime_environment import runtime_identity_environment


pytestmark = [pytest.mark.e2e, pytest.mark.database, pytest.mark.process, pytest.mark.slow]

SOURCE_LABELS = (
    ("OWNER_API", "目标业务状态", "KEY"),
    ("READ_ONLY_SQLITE", "只读数据库", "SUPPORTING"),
    ("STRUCTURED_AUDIT_LOG", "结构化审计记录", "SUPPORTING"),
    ("ASYNC_TASK_STATUS", "后台任务", "SUPPORTING"),
    ("AZURE_QUEUE_PEEK", "消息通道", "SUPPORTING"),
    ("AZURE_BLOB_OBJECT", "最终对象/文件", "KEY"),
)
SOURCE_TYPES = {item[0] for item in SOURCE_LABELS}
SAMPLE_ROOT = Path(__file__).resolve().parents[2] / "samples" / "web" / "collaboration_space"


def test_official_sample_workflow_forms_block_pass_and_inconclusive_results(
    tmp_path: Path,
) -> None:
    var_dir = tmp_path / "var"
    store = InMemorySecretStore()
    app = create_app(
        var_dir,
        start_worker=True,
        secret_store=store,
        environ=runtime_identity_environment(
            var_dir,
            extra={"PYTHONNOUSERSITE": "1"},
        ),
        official_sample_root=SAMPLE_ROOT,
    )
    with TestClient(app) as client:
        started_response = client.post(
            "/api/experience/official-sample/start",
            json={"schema_version": "1", "consent": True},
        )
        assert started_response.status_code == 200, started_response.text
        started = started_response.json()["data"]
        assert started["scenario_version"] == "VULNERABLE"
        assert started["scenario_prepared"] is False
        assert _project_run_ids(client, started["project_id"]) == []

        prepared_response = client.post("/api/experience/official-sample/prepare")
        assert prepared_response.status_code == 200, prepared_response.text
        prepared = prepared_response.json()["data"]
        assert prepared["scenario_prepared"] is True
        setup = _official_setup(client, started["project_id"])
        runtime = app.state.context.official_samples.active
        assert runtime is not None
        experience_root = runtime.experience_root

        runs: list[dict[str, object]] = []
        block_run_id: str | None = None
        cases = (
            ("vulnerable", None, "ENQUEUE_BEFORE_AUTHORIZE", "AVAILABLE", "AVAILABLE", "BLOCK", "VULNERABLE"),
            ("fixed", "FIXED", "AUTHORIZE_BEFORE_ENQUEUE", "AVAILABLE", "AVAILABLE", "PASS", "SAFE"),
            ("inconclusive", "EVIDENCE_LIMITED", "ENQUEUE_BEFORE_AUTHORIZE", "UNAVAILABLE", "UNAVAILABLE", "INCONCLUSIVE", "INCONCLUSIVE"),
        )
        for (
            variant,
            requested_version,
            authorization_order,
            owner_observation,
            blob_observation,
            expected_run_verdict,
            expected_bob_verdict,
        ) in cases:
            before_switch = _project_run_ids(client, setup["project_id"])
            if requested_version is None:
                version = prepared
            else:
                switched = client.post(
                    "/api/experience/official-sample/version",
                    json={
                        "schema_version": "1",
                        "version": requested_version,
                        "source_run_id": block_run_id if requested_version == "FIXED" else None,
                    },
                )
                assert switched.status_code == 200, switched.text
                version = switched.json()["data"]
                assert version["scenario_version"] == requested_version
                assert _project_run_ids(client, setup["project_id"]) == before_switch
            change_id = (
                version["repair_change_id"]
                if requested_version == "FIXED"
                else version["vulnerable_change_id"]
            )
            assert isinstance(change_id, str) and change_id.startswith("chg_")
            assert json.loads(runtime.control_path.read_text(encoding="utf-8")) == {
                "schema_version": "1",
                "authorization_order": authorization_order,
                "owner_observation": owner_observation,
                "blob_observation": blob_observation,
            }

            compiled = client.post(
                f"/api/projects/{setup['project_id']}/check-preparation",
                json={"schema_version": "1", "change_id": change_id},
            )
            assert compiled.status_code == 200, compiled.text
            preview = client.get(
                f"/api/projects/{setup['project_id']}/check-preview"
            )
            assert preview.status_code == 200, preview.text
            preview_data = preview.json()["data"]
            assert preview_data["ready"] is True
            assert preview_data["case_count"] == 3, preview_data
            assert preview_data["differential_pair_count"] == 1, preview_data
            submitted = client.post(
                f"/api/projects/{setup['project_id']}/checks",
                json={
                    "schema_version": "1",
                    "idempotency_key": f"collaboration-golden-{variant}",
                    "change_id": change_id,
                },
            )
            assert submitted.status_code == 202, submitted.text
            run_id = submitted.json()["data"]["run"]["run_id"]
            detail = _wait_for_final_result(client, run_id)
            assert detail["lifecycle"] == "COMPLETED", _failure_summary(detail)
            assert detail["result_integrity"] == "VERIFIED", detail
            evidence = _load_evidence(client, run_id)
            assert detail["verdict"] == expected_run_verdict, (
                json.dumps(
                    _verdict_failure_summary(detail, evidence),
                    ensure_ascii=False,
                    sort_keys=True,
                )
            )
            assert len(evidence) == 3, evidence
            alice = _evidence_for_case(
                evidence,
                setup["alice_id"],
                setup["export_action_id"],
            )
            bob = _evidence_for_case(
                evidence,
                setup["bob_id"],
                setup["export_action_id"],
            )
            bob_view = _evidence_for_case(
                evidence,
                setup["bob_id"],
                setup["view_action_id"],
            )
            assert alice["case_snapshot"]["expectations"] == ["ALLOW"]
            assert alice["execution_fact"]["outcome"] == "ACCEPTED"
            assert alice["verdict"] == "SAFE"
            assert bob["case_snapshot"]["expectations"] == ["DENY"]
            assert bob["execution_fact"]["outcome"] == "DENIED"
            assert bob["verdict"] == expected_bob_verdict
            assert bob_view["case_snapshot"]["expectations"] == ["ALLOW"]
            assert bob_view["execution_fact"]["outcome"] == "ACCEPTED"
            assert bob_view["verdict"] == "SAFE"
            assert bob_view["security_effect_facts"][0]["kind"] == "DATA_DISCLOSURE"
            assert bob_view["security_effect_facts"][0]["state"] == "CONFIRMED"
            for item in (alice, bob):
                _assert_six_sources_published(item)

            presentation_response = client.get(
                f"/api/runs/{run_id}/presentation"
            )
            assert presentation_response.status_code == 200, (
                presentation_response.text
            )
            presentation = presentation_response.json()["data"]
            assert presentation["verdict"] == expected_run_verdict
            bob_issue = next(
                item
                for item in presentation["issues"]
                if item["planned_identity_id"] == setup["bob_id"]
                and item["action_id"] == setup["export_action_id"]
            )
            assert [
                (item["observer_type"], item["label"], item["role"])
                for item in bob_issue["evidence_sources"]
            ] == list(SOURCE_LABELS)
            if variant == "vulnerable":
                assert bob_issue["surface_result"] == "页面或接口显示已拒绝"
                assert bob_issue["actual_result"] == "真实资源已经发生变化"
                assert _source_status(
                    bob_issue,
                    "AZURE_BLOB_OBJECT",
                ) == "FOUND"
            elif variant == "fixed":
                assert bob_issue["actual_result"] == "真实资源没有发生变化"
                assert _source_status(bob_issue, "OWNER_API") == "NOT_FOUND"
                assert _source_status(
                    bob_issue,
                    "AZURE_BLOB_OBJECT",
                ) == "NOT_FOUND"
            else:
                assert _source_status(bob_issue, "OWNER_API") == "UNAVAILABLE"
                assert _source_status(
                    bob_issue,
                    "AZURE_BLOB_OBJECT",
                ) == "UNAVAILABLE"
                assert presentation["headline"] == "证据不足"
                assert "不代表安全" in presentation["scope_statement"]

            reports = client.get(f"/api/runs/{run_id}/reports")
            assert reports.status_code == 200, reports.text
            report_id = reports.json()["data"][0]["report_id"]
            report = client.get(f"/api/runs/{run_id}/reports/{report_id}")
            assert report.status_code == 200, report.text
            report_data = report.json()["data"]
            assert report_data["run_id"] == run_id
            assert report_data["presentation"]["verdict"] == expected_run_verdict
            assert "evidence_sources" not in json.dumps(
                report_data["presentation"],
                ensure_ascii=False,
            )

            case_ids = {
                item["case_snapshot"]["case_id"] for item in evidence
            }
            _assert_sample_recovered(runtime.runtime_root, case_ids)
            runs.append({"run_id": run_id, "verdict": expected_run_verdict})
            if variant == "vulnerable":
                block_run_id = run_id

        history = client.get(
            f"/api/projects/{setup['project_id']}/results/history"
        )
        assert history.status_code == 200, history.text
        comparisons = history.json()["data"]["comparisons"]
        assert [item["run_id"] for item in comparisons] == [
            item["run_id"] for item in runs
        ]
        assert {item["run_id"] for item in comparisons} == {
            item["run_id"] for item in runs
        }

        stopped = client.post("/api/experience/official-sample/stop")
        assert stopped.status_code == 200, stopped.text
        assert stopped.json()["data"]["active"] is False
        assert not experience_root.exists()


def _official_setup(client: TestClient, project_id: str) -> dict[str, object]:
    understanding_response = client.get(
        f"/api/projects/{project_id}/application-understanding"
    )
    assert understanding_response.status_code == 200, understanding_response.text
    understanding = understanding_response.json()["data"]
    action_ids = {
        item["canonical_key"]: item["candidate_id"]
        for item in understanding["action_candidates"]
        if item["decision"] == "CONFIRMED"
    }
    identities_response = client.get(f"/api/projects/{project_id}/test-identities")
    assert identities_response.status_code == 200, identities_response.text
    identities = {
        item["role_canonical_key"]: item["identity_id"]
        for item in identities_response.json()["data"]
        if item["status"] == "PREPARED"
    }
    assert set(identities) == {"project_owner", "member"}
    return {
        "project_id": project_id,
        "alice_id": identities["project_owner"],
        "bob_id": identities["member"],
        "export_action_id": action_ids["POST /api/projects/{project_id}/exports"],
        "view_action_id": action_ids["GET /api/projects/{project_id}/collaboration"],
    }


def _project_run_ids(client: TestClient, project_id: str) -> list[str]:
    response = client.get(f"/api/projects/{project_id}/runs")
    assert response.status_code == 200, response.text
    return [item["run_id"] for item in response.json()["data"]]


def _wait_for_final_result(client: TestClient, run_id: str) -> dict[str, object]:
    deadline = time.monotonic() + 120
    detail: dict[str, object] | None = None
    while time.monotonic() < deadline:
        response = client.get(f"/api/runs/{run_id}")
        if response.status_code == 200:
            detail = response.json()["data"]
            finalization = detail.get("finalization") or {}
            if (
                detail.get("lifecycle")
                in {"FAILED", "CANCELLED", "SAFETY_STOPPED"}
                or finalization.get("base_report_state") in {"COMPLETE", "FAILED"}
            ):
                return detail
        time.sleep(0.1)
    raise AssertionError(
        "Golden run did not finalize: "
        + json.dumps(_failure_summary(detail or {}), ensure_ascii=False)
    )


def _failure_summary(detail: dict[str, object]) -> dict[str, object]:
    """只保留公开、无秘密且有界的终态摘要，不读取 Runner 内部进度工件。"""

    job = detail.get("job") or {}
    finalization = detail.get("finalization") or {}
    return {
        "lifecycle": detail.get("lifecycle"),
        "verdict": detail.get("verdict"),
        "job_state": job.get("state"),
        "finalization": {
            "base_report_state": finalization.get("base_report_state"),
            "error_code": finalization.get("error_code"),
        },
        "execution_error_codes": [
            item.get("code") for item in (detail.get("execution_errors") or [])
        ],
    }


def _verdict_failure_summary(
    detail: dict[str, object],
    evidence: list[dict[str, object]],
) -> dict[str, object]:
    """只展开三态 Golden 定位所需的无秘密事实，避免高成本重跑。"""

    cases: list[dict[str, object]] = []
    for item in evidence:
        binding_types = {
            binding["observer_id"]: binding["observer_type"]
            for binding in item["requirement_bindings"]
        }
        facts = {
            fact["requirement_id"]: {
                "effect": fact["effect"],
                "complete": fact["complete"],
                "reason_codes": fact["reason_codes"],
            }
            for fact in item["observation_facts"]
        }
        cases.append(
            {
                "subject_id": item["case_snapshot"]["subject_id"],
                "execution_outcome": item["execution_fact"]["outcome"],
                "execution_reasons": item["execution_fact"]["reason_codes"],
                "verdict": item["verdict"],
                "sources": [
                    {
                        "observer_type": binding_types[outcome["observer_id"]],
                        "status": outcome["status"],
                        "reason_codes": outcome.get("reason_codes", []),
                    }
                    for outcome in item["outcomes"]
                ],
                "facts": facts,
            }
        )
    return {
        "run": _failure_summary(detail),
        "cases": cases,
    }


def _assert_six_sources_published(
    evidence: dict[str, object],
) -> None:
    bindings = evidence["requirement_bindings"]
    outcomes = evidence["outcomes"]
    facts = evidence["observation_facts"]
    assert len(bindings) == len(outcomes) == len(facts) == 6
    binding_by_observer = {
        item["observer_id"]: item for item in bindings
    }
    assert {
        item["observer_type"] for item in binding_by_observer.values()
    } == SOURCE_TYPES
    assert {item["requirement_id"] for item in facts} == {
        item["requirement_id"] for item in bindings
    }
    assert {item["observer_id"] for item in outcomes} == set(binding_by_observer)


def _source_status(issue: dict[str, object], observer_type: str) -> str:
    return next(
        item["status"]
        for item in issue["evidence_sources"]
        if item["observer_type"] == observer_type
    )


def _evidence_for_case(
    evidence: list[dict[str, object]],
    identity_id: str,
    action_id: str,
) -> dict[str, object]:
    return next(
        item
        for item in evidence
        if item["case_snapshot"]["subject_id"] == identity_id
        and item["case_snapshot"]["action_id"] == action_id
    )


def _load_evidence(client: TestClient, run_id: str) -> list[dict[str, object]]:
    """沿公开索引和单证据端点读取已发布文档，不绕过发布边界。"""

    listed = client.get(f"/api/runs/{run_id}/evidence")
    assert listed.status_code == 200, listed.text
    documents: list[dict[str, object]] = []
    for item in listed.json()["data"]:
        detail = client.get(f"/api/runs/{run_id}/evidence/{item['evidence_id']}")
        assert detail.status_code == 200, detail.text
        documents.append(detail.json()["data"])
    return documents


def _assert_sample_recovered(runtime_root: Path, case_ids: set[str]) -> None:
    """验收 Recovery 撤销当前交付物，同时保留已发生的业务历史。"""

    audit_path = runtime_root / "audit" / "events.jsonl"
    audit = (
        [json.loads(line) for line in audit_path.read_text(encoding="utf-8").splitlines()]
        if audit_path.is_file()
        else []
    )
    queue_path = runtime_root / "queue" / "messages.jsonl"
    queued = (
        [json.loads(line) for line in queue_path.read_text(encoding="utf-8").splitlines()]
        if queue_path.is_file()
        else []
    )
    database_path = runtime_root / "database" / "collaboration-space.sqlite3"
    with sqlite3.connect(database_path) as database:
        for case_id in case_ids:
            job = database.execute(
                "SELECT state FROM export_jobs WHERE case_id = ?",
                (case_id,),
            ).fetchone()
            task_path = runtime_root / "tasks" / f"{case_id}.json"
            if job is None:
                assert not task_path.exists()
                continue
            assert job == ("REVOKED",)
            assert json.loads(task_path.read_text(encoding="utf-8"))["state"] == "REVOKED"
            audit_events = [
                item["event_type"]
                for item in audit
                if item.get("case_tag") == case_id
            ]
            assert "export_request_created" in audit_events
            assert "export_job_started" in audit_events
            assert "archive_generated" in audit_events
            assert "export_job_completed" in audit_events
            assert audit_events[-1] == "EXPORT_REVOKED"
            assert [
                item["event_type"]
                for item in queued
                if item.get("case_tag") == case_id
            ] == ["EXPORT_ENQUEUED", "TASK_RUNNING", "EXPORT_READY", "EXPORT_REVOKED"]
            assert (
                runtime_root
                / "blob"
                / case_id
                / "campus-digital-museum-package.zip"
            ).is_file()
        resource = database.execute(
            "SELECT workflow_state, value FROM resource_state"
        ).fetchone()
    assert resource == ("ABSENT", "")
