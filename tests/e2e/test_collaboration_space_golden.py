# 验证协作空间经正式编译、Worker、Runner、六 Observer 和结果发布形成三态 Golden。

from __future__ import annotations

import json
import time
from pathlib import Path
from threading import Thread

import pytest

from samples.web.collaboration_space.source.server import (
    create_collaboration_space_server,
)
from tests.fixtures.collaboration_golden import (
    InMemorySecretStore,
    prepare_formal_project,
    reachable_discovery,
    sample_credentials,
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


def test_three_state_golden_uses_real_sample_observers_and_published_results(
    tmp_path: Path,
) -> None:
    var_dir = tmp_path / "var"
    runtime_root = var_dir / "runtime" / "samples" / "collaboration-space"
    credentials = sample_credentials()
    sample = create_collaboration_space_server(
        port=0,
        runtime_root=runtime_root,
        authorization_order="AUTHORIZE_BEFORE_ENQUEUE",
        blob_observation="AVAILABLE",
        **credentials,
    )
    sample_thread = Thread(target=sample.serve_forever, daemon=True)
    sample_thread.start()
    endpoint = f"http://127.0.0.1:{sample.server_port}"
    store = InMemorySecretStore()
    environment = runtime_identity_environment(
        var_dir,
        extra={
            "JIEJIAN_SAMPLE_SQLITE_DATABASE": str(
                runtime_root / "database" / "collaboration-space.sqlite3"
            ),
            "JIEJIAN_SAMPLE_AUDIT_ROOT": str(runtime_root / "audit"),
            "JIEJIAN_SAMPLE_QUEUE_SAS": credentials["queue_sas"],
            "JIEJIAN_SAMPLE_BLOB_SAS": credentials["blob_sas"],
            "JIEJIAN_SAMPLE_TASK_BEARER": credentials["task_bearer"],
            "JIEJIAN_SAMPLE_OWNER_OBSERVER": credentials["owner_observer"],
            "PYTHONNOUSERSITE": "1",
        },
    )
    app = create_app(
        var_dir,
        start_worker=True,
        secret_store=store,
        environ=environment,
    )
    app.state.context.application_understanding.endpoint_discovery = (
        reachable_discovery(endpoint)
    )
    try:
        with TestClient(app) as client:
            setup = prepare_formal_project(
                client,
                app.state.context,
                store,
                endpoint=endpoint,
                observer_descriptor_path=runtime_root / "environment.json",
                sessions=credentials["session_material"],
            )
            runs: list[dict[str, object]] = []
            cases = (
                (
                    "vulnerable",
                    "ENQUEUE_BEFORE_AUTHORIZE",
                    "AVAILABLE",
                    "BLOCK",
                    "VULNERABLE",
                ),
                (
                    "fixed",
                    "AUTHORIZE_BEFORE_ENQUEUE",
                    "AVAILABLE",
                    "PASS",
                    "SAFE",
                ),
                (
                    "inconclusive",
                    "AUTHORIZE_BEFORE_ENQUEUE",
                    "UNAVAILABLE",
                    "INCONCLUSIVE",
                    "INCONCLUSIVE",
                ),
            )
            for (
                variant,
                authorization_order,
                blob_observation,
                expected_run_verdict,
                expected_bob_verdict,
            ) in cases:
                # 与正式 Official Sample 管理链一致：先清理上一轮测试基线，
                # 再原子切换只读行为控制文件，不给业务属性增加测试 setter。
                sample.reset()
                sample._write_control(authorization_order, blob_observation)
                compiled = client.post(
                    f"/api/projects/{setup['project_id']}/security-setup/compile",
                    json={"schema_version": "1", "actor": "协作空间 Golden 验收"},
                )
                assert compiled.status_code == 200, compiled.text
                preview = client.get(
                    f"/api/projects/{setup['project_id']}/check-preview"
                )
                assert preview.status_code == 200, preview.text
                assert preview.json()["data"]["ready"] is True
                submitted = client.post(
                    f"/api/projects/{setup['project_id']}/checks",
                    json={
                        "schema_version": "1",
                        "idempotency_key": f"collaboration-golden-{variant}",
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
                assert len(evidence) == 2, evidence
                alice = _evidence_for_label(evidence, setup["alice_id"])
                bob = _evidence_for_label(evidence, setup["bob_id"])
                assert alice["case_snapshot"]["expectations"] == ["ALLOW"]
                assert alice["execution_fact"]["outcome"] == "ACCEPTED"
                assert alice["verdict"] == "SAFE"
                assert bob["case_snapshot"]["expectations"] == ["DENY"]
                assert bob["execution_fact"]["outcome"] == "DENIED"
                assert bob["verdict"] == expected_bob_verdict
                for item in evidence:
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
                    assert _source_status(bob_issue, "OWNER_API") == "NOT_FOUND"
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
                _assert_sample_recovered(sample, case_ids)
                runs.append({"run_id": run_id, "verdict": expected_run_verdict})

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
    finally:
        sample.shutdown()
        sample.server_close()
        sample_thread.join(timeout=5)
    assert not sample_thread.is_alive()


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


def _evidence_for_label(
    evidence: list[dict[str, object]],
    identity_id: str,
) -> dict[str, object]:
    return next(
        item
        for item in evidence
        if item["case_snapshot"]["subject_id"] == identity_id
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


def _assert_sample_recovered(sample, case_ids: set[str]) -> None:
    """验收 Recovery 撤销当前交付物，同时保留已发生的业务历史。"""

    audit_path = sample.runtime_root / "audit" / "events.jsonl"
    audit = (
        [json.loads(line) for line in audit_path.read_text(encoding="utf-8").splitlines()]
        if audit_path.is_file()
        else []
    )
    queued = sample.storage.queue_records()
    visible_blobs = {item["name"] for item in sample.storage.blob_objects()}
    for case_id in case_ids:
        job = sample.storage.find_job(case_id)
        if job is None:
            assert sample.storage.task_for_marker(case_id) is None
            continue
        assert job["state"] == "REVOKED"
        assert sample.storage.task_for_marker(case_id)["state"] == "REVOKED"
        assert [
            item["event_type"] for item in audit if item.get("case_tag") == case_id
        ] == ["EXPORT_ENQUEUED", "TASK_RUNNING", "EXPORT_READY", "EXPORT_REVOKED"]
        assert [
            item["event_type"] for item in queued if item.get("case_tag") == case_id
        ] == ["EXPORT_ENQUEUED", "TASK_RUNNING", "EXPORT_READY", "EXPORT_REVOKED"]
        assert all(not name.startswith(f"{case_id}/") for name in visible_blobs)
        assert (
            sample.runtime_root
            / "blob"
            / case_id
            / "campus-digital-museum-package.zip"
        ).is_file()
    assert sample.storage.resource_state()["workflow_state"] == "ABSENT"
