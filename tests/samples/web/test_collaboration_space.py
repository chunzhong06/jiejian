# 验证协作空间 Sample 的真实业务链与六面本地数据源，不调用界鉴 Verification。

from __future__ import annotations

import base64
import json
import re
import socket
import sqlite3
import time
import zipfile
from pathlib import Path

import httpx
import pytest

from samples.web.collaboration_space.source.server import (
    CollaborationSpaceServer,
    create_collaboration_space_server,
)


PROJECT_ID = "campus-digital-museum"
RESOURCE_ID = "campus-digital-museum-package"
TRACE_SEMANTIC_KEYS = (
    "request_received",
    "server_identity_resolved",
    "export_request_created",
    "authorization_decided",
    "export_message_sent",
    "export_job_started",
    "archive_generated",
    "export_job_completed",
)
TRACE_KINDS = (
    "ENTRY",
    "IDENTITY",
    "PERSISTENT_EFFECT",
    "AUTHORIZATION",
    "MESSAGE",
    "DELEGATION",
    "FINAL_EFFECT",
    "FINAL_EFFECT",
)


def _login(client: httpx.Client, account: str, password: str) -> None:
    response = client.post("/api/session", json={"username": account, "password": password})
    assert response.status_code == 200
    assert response.json()["account"] == account


def _wait_task(client: httpx.Client, base_url: str, marker: str, bearer: str) -> dict:
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        response = client.get(f"{base_url}/api/tasks/{marker}", headers={"Authorization": f"Bearer {bearer}"})
        assert response.status_code == 200
        payload = response.json()
        if payload["state"] in {"SUCCESS", "FAILED", "REVOKED", "NOT_CREATED"}:
            return payload
        time.sleep(0.01)
    raise AssertionError("sample export task did not reach a terminal state")


def _audit_records(runtime_root: Path, marker: str) -> list[dict]:
    path = runtime_root / "audit" / "events.jsonl"
    return [
        record
        for line in path.read_text(encoding="utf-8").splitlines()
        if (record := json.loads(line))["case_tag"] == marker
    ]


def test_product_page_supports_two_real_demo_sessions(
    collaboration_space_factory,
) -> None:
    sample = collaboration_space_factory("AUTHORIZE_BEFORE_ENQUEUE")
    with httpx.Client(base_url=sample.base_url, follow_redirects=False, trust_env=False) as client:
        page = client.get("/")
        assert page.status_code == 200
        assert "协作空间 · 校园数字展馆" in page.text
        assert "选择演示身份" in page.text
        assert "导出完整项目交付包" in page.text
        assert "撤销当前资料包？" in page.text
        assert "确认撤销" in page.text
        assert "重新生成交付包" in page.text
        assert 'data-account="eve"' not in page.text
        assert "外部访客" not in page.text
        assert "Observer" not in page.text
        assert "Verdict" not in page.text
        create_export_script = page.text.split("async function createExport()", 1)[1].split(
            "function openRevokeDialog()",
            1,
        )[0]
        assert "headers: { 'Content-Type': 'application/json' }" in create_export_script
        assert "body: JSON.stringify({ resource_id: 'campus-digital-museum-package' })" in create_export_script

        session = client.post("/api/demo-session", json={"account": "bob"})
        assert session.status_code == 200
        assert session.json()["role"] == "普通成员"
        catalog = client.get("/api/projects")
        assert catalog.status_code == 200
        assert set(catalog.json()["projects"][0]) == {"project_id", "name", "summary"}
        assert client.get(f"/api/projects/{PROJECT_ID}").status_code == 200
        collaboration = client.get(f"/api/projects/{PROJECT_ID}/collaboration")
        assert collaboration.status_code == 200
        assert set(collaboration.json()) == {"project_id", "name", "members", "materials"}
        assert {item["kind"] for item in collaboration.json()["materials"]} == {
            "APPLICATION_NOTE",
            "BUDGET_SUMMARY",
            "DESIGN_SOURCE",
            "REVIEW_NOTE",
        }


def test_alice_exports_and_all_data_sources_are_real(collaboration_space_factory) -> None:
    sample = collaboration_space_factory("AUTHORIZE_BEFORE_ENQUEUE")
    with httpx.Client(base_url=sample.base_url, follow_redirects=False, trust_env=False) as client:
        _login(client, "alice", sample.passwords["alice"])
        marker = "case-alice-real"
        response = client.post(
            f"/api/projects/{PROJECT_ID}/exports",
            headers={"X-Jiejian-Case-ID": marker},
            json={"resource_id": RESOURCE_ID},
        )
        assert response.status_code == 202
        task = _wait_task(client, sample.base_url, marker, sample.task_bearer)
        assert set(task) == {"schema_version", "case_tag", "resource_id", "task_id", "state", "final_result"}
        assert task["schema_version"] == "1"
        assert task["resource_id"] == RESOURCE_ID
        assert task["state"] == "SUCCESS"

        status = client.get(f"/api/projects/{PROJECT_ID}/exports/{marker}")
        assert status.status_code == 200
        assert status.json()["export"]["state"] == "SUCCESS"

        owner_api = client.get(
            f"/api/observer/resources/{RESOURCE_ID}",
            headers={"Authorization": f"Bearer {sample.owner_observer}"},
        )
        assert owner_api.status_code == 200
        assert owner_api.json() == {
            "resource_id": RESOURCE_ID,
            "workflow_state": "READY",
            "value": task["final_result"]["artifact_id"],
        }

        queue = client.get(
            "/collaboration/export-events/messages?"
            + sample.queue_sas
            + "&peekonly=true&numofmessages=8"
        )
        assert queue.status_code == 200
        assert "QueueMessage" in queue.text
        message_text = re.search(r"<MessageText>([^<]+)</MessageText>", queue.text)
        assert message_text is not None
        assert json.loads(base64.b64decode(message_text.group(1)).decode("utf-8"))["case_tag"] == marker

        listed = client.get(
            "/collaboration/exports?"
            + sample.blob_sas
            + "&restype=container&comp=list&prefix="
            + marker
            + "/&include=metadata&maxresults=5"
        )
        assert listed.status_code == 200
        object_name = f"{marker}/campus-digital-museum-package.zip"
        assert object_name in listed.text

        head = client.head(f"/collaboration/exports/{object_name}?{sample.blob_sas}")
        assert head.status_code == 200
        assert head.headers["x-ms-meta-case_tag"] == marker
        assert head.headers["x-ms-meta-resource_id"] == RESOURCE_ID
        archive_response = client.get(f"/collaboration/exports/{object_name}?{sample.blob_sas}")
        assert archive_response.status_code == 200
        archive_path = sample.server.runtime_root / "blob" / marker / "campus-digital-museum-package.zip"
        assert archive_path.is_file()
        ranged = client.get(
            f"/collaboration/exports/{object_name}?{sample.blob_sas}",
            headers={"Range": f"bytes=0-{int(head.headers['content-length']) - 1}"},
        )
        assert ranged.status_code == 206
        assert ranged.content == archive_path.read_bytes()
        with zipfile.ZipFile(archive_path) as archive:
            assert {
                "01-项目申报书.json",
                "02-完整预算.csv",
                "03-成员信息.json",
                "04-设计源文件/展馆首页线框.svg",
                "05-评审记录.json",
            } == set(archive.namelist())
            assert "校园数字展馆" in archive.read("01-项目申报书.json").decode("utf-8")
            assert "70000" in archive.read("02-完整预算.csv").decode("utf-8")
            assert "虚构" in archive.read("03-成员信息.json").decode("utf-8")
            assert "虚构设计源文件" in archive.read("04-设计源文件/展馆首页线框.svg").decode("utf-8")
            assert "演示用途的虚构数据" in archive.read("05-评审记录.json").decode("utf-8")

        database_path = sample.server.runtime_root / "database" / "collaboration-space.sqlite3"
        with sqlite3.connect(database_path) as database:
            tables = {row[0] for row in database.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            assert {"projects", "members", "export_jobs"}.issubset(tables)
            row = database.execute(
                "SELECT resource_id, workflow_state, value FROM resource_state WHERE resource_id = ?",
                (RESOURCE_ID,),
            ).fetchone()
            assert row == (RESOURCE_ID, "READY", task["final_result"]["artifact_id"])

        audit = (sample.server.runtime_root / "audit" / "events.jsonl").read_text(encoding="utf-8")
        assert marker in audit
        assert '"effect":"READY"' in audit
        assert "password" not in audit.casefold()
        records = _audit_records(sample.server.runtime_root, marker)
        assert tuple(record["semantic_key"] for record in records) == TRACE_SEMANTIC_KEYS
        assert tuple(record["kind"] for record in records) == TRACE_KINDS
        assert [record["sequence"] for record in records] == list(range(1, 9))
        assert records[0]["subject_id"] == records[0]["actor_id"] == "alice"
        assert all(record["task_id"] == "" for record in records[:2])
        real_task_id = records[2]["task_id"]
        assert real_task_id.startswith("task-")
        assert all(record["task_id"] == real_task_id for record in records[2:])
        assert all(record["actor_id"] == "alice" for record in records[:5])
        assert records[3]["authorization_decision"] == "ALLOW"
        assert records[5]["subject_id"] == "alice"
        assert records[5]["actor_id"] == "export-worker"
        assert all(
            record.get("parent_event_id") == records[index - 1]["event_id"]
            for index, record in enumerate(records)
            if index > 0
        )
        assert all(
            record.get("origin_authorization_event_id") == records[3]["event_id"]
            for record in records[4:]
        )
        assert records[5]["delegated_from_event_id"] == records[4]["event_id"]
        assert records[6]["delegated_from_event_id"] == records[5]["event_id"]
        assert records[7]["delegated_from_event_id"] == records[6]["event_id"]
        assert all(secret not in audit for secret in sample.passwords.values())

        descriptor = json.loads(
            (sample.server.runtime_root / "environment.json").read_text(encoding="utf-8")
        )
        assert set(descriptor) == {
            "application",
            "owner_api",
            "sqlite",
            "audit",
            "task",
            "queue",
            "blob",
        }
        assert "mode" not in descriptor
        assert descriptor["owner_api"] == {
            "credential_ref": "env:JIEJIAN_SAMPLE_OWNER_OBSERVER",
            "origin": sample.base_url,
            "relative_path_template": "/api/observer/resources/{resource_id}",
        }
        assert descriptor["sqlite"]["table_or_view"] == "resource_state"
        assert descriptor["audit"]["relative_file_pattern"] == "events.jsonl"
        assert descriptor["task"]["relative_path_template"] == "/api/tasks/{request_marker}"
        assert descriptor["queue"]["queue_name"] == "export-events"
        assert descriptor["blob"]["prefix_template"] == "{request_marker}/"


def test_export_request_rejects_unknown_resource(collaboration_space_factory) -> None:
    sample = collaboration_space_factory("AUTHORIZE_BEFORE_ENQUEUE")
    with httpx.Client(base_url=sample.base_url, follow_redirects=False, trust_env=False) as client:
        _login(client, "alice", sample.passwords["alice"])
        response = client.post(
            f"/api/projects/{PROJECT_ID}/exports",
            json={"resource_id": "another-package"},
        )

        assert response.status_code == 400
        assert response.json() == {"code": "EXPORT_RESOURCE_INVALID"}


def test_export_status_request_exposes_resource_for_recording(
    collaboration_space_factory,
) -> None:
    sample = collaboration_space_factory("AUTHORIZE_BEFORE_ENQUEUE")
    with httpx.Client(
        base_url=sample.base_url,
        follow_redirects=False,
        trust_env=False,
    ) as client:
        page = client.get("/")
        assert page.status_code == 200
        assert (
            "'?resource_id=' + encodeURIComponent('campus-digital-museum-package')"
            in page.text
        )
        _login(client, "alice", sample.passwords["alice"])
        valid = client.get(
            f"/api/projects/{PROJECT_ID}/exports/not-created?resource_id={RESOURCE_ID}"
        )
        invalid = client.get(
            f"/api/projects/{PROJECT_ID}/exports/not-created?resource_id=another-package"
        )

        assert valid.status_code == 200
        assert valid.json()["export"] is None
        assert invalid.status_code == 400
        assert invalid.json() == {"code": "EXPORT_RESOURCE_INVALID"}


def test_owner_api_requires_its_independent_read_only_credential(
    collaboration_space_factory,
) -> None:
    sample = collaboration_space_factory()
    path = f"/api/observer/resources/{RESOURCE_ID}"
    with httpx.Client(base_url=sample.base_url, trust_env=False) as client:
        assert client.get(path).status_code == 401
        assert client.get(path, headers={"Authorization": "Bearer wrong"}).status_code == 401
        assert client.get(
            path,
            headers={"Authorization": f"Bearer {sample.owner_observer}"},
        ).status_code == 200


@pytest.mark.parametrize("order", ["ENQUEUE_BEFORE_AUTHORIZE", "AUTHORIZE_BEFORE_ENQUEUE"])
def test_bob_order_boundary_preserves_surface_denial_and_real_effect(collaboration_space_factory, order: str) -> None:
    sample = collaboration_space_factory(order)
    with httpx.Client(base_url=sample.base_url, follow_redirects=False, trust_env=False) as bob:
        _login(bob, "bob", sample.passwords["bob"])
        bob_marker = f"case-bob-{order.lower()}"
        denied = bob.post(
            f"/api/projects/{PROJECT_ID}/exports",
            headers={"X-Jiejian-Case-ID": bob_marker},
        )
        assert denied.status_code == 403
        task = _wait_task(bob, sample.base_url, bob_marker, sample.task_bearer)
        if order == "ENQUEUE_BEFORE_AUTHORIZE":
            assert task["state"] == "SUCCESS"
            assert task["final_result"] is not None
            assert bob.get(f"/api/projects/{PROJECT_ID}/exports/{bob_marker}").json()["export"]["state"] == "SUCCESS"
        else:
            assert task["state"] == "NOT_CREATED"
            assert not (sample.server.runtime_root / "blob" / bob_marker).exists()
        records = _audit_records(sample.server.runtime_root, bob_marker)
        expected_keys = (
            TRACE_SEMANTIC_KEYS
            if order == "ENQUEUE_BEFORE_AUTHORIZE"
            else TRACE_SEMANTIC_KEYS[:2] + ("authorization_decided",)
        )
        assert tuple(record["semantic_key"] for record in records) == expected_keys
        expected_kinds = (
            TRACE_KINDS
            if order == "ENQUEUE_BEFORE_AUTHORIZE"
            else TRACE_KINDS[:2] + ("AUTHORIZATION",)
        )
        assert tuple(record["kind"] for record in records) == expected_kinds
        assert records[0]["subject_id"] == records[0]["actor_id"] == "bob"
        if order == "ENQUEUE_BEFORE_AUTHORIZE":
            assert all(record["task_id"] == "" for record in records[:2])
            real_task_id = records[2]["task_id"]
            assert real_task_id.startswith("task-")
            assert all(record["task_id"] == real_task_id for record in records[2:])
            assert all(record["actor_id"] == "bob" for record in records[:5])
        else:
            assert all(record["task_id"] == "" for record in records)
            assert all(record["actor_id"] == "bob" for record in records)
        assert next(
            record for record in records if record["semantic_key"] == "authorization_decided"
        )["authorization_decision"] == "DENY"
        if order == "ENQUEUE_BEFORE_AUTHORIZE":
            assert records[-1]["subject_id"] == "bob"
            assert records[-1]["actor_id"] == "export-worker"
        else:
            assert all(record["sequence"] <= 3 for record in records)

def test_unavailable_blob_does_not_change_fixed_bob_business_result(
    collaboration_space_factory,
) -> None:
    sample = collaboration_space_factory("AUTHORIZE_BEFORE_ENQUEUE", "UNAVAILABLE")
    with httpx.Client(base_url=sample.base_url, follow_redirects=False, trust_env=False) as client:
        _login(client, "bob", sample.passwords["bob"])
        marker = "case-blob-unavailable"
        before = client.get(
            f"/collaboration/exports?{sample.blob_sas}&restype=container&comp=list&prefix={marker}/"
        )
        assert before.status_code == 200
        assert client.post(
            f"/api/projects/{PROJECT_ID}/exports",
            headers={"X-Jiejian-Case-ID": marker},
        ).status_code == 403
        task = _wait_task(client, sample.base_url, marker, sample.task_bearer)
        assert task["state"] == "NOT_CREATED"
        listed = client.get(f"/collaboration/exports?{sample.blob_sas}&restype=container&comp=list&prefix={marker}/")
        assert listed.status_code == 503
        project = client.get(f"/api/projects/{PROJECT_ID}")
        assert project.status_code == 200
        assert project.json()["export_state"] == "NOT_CREATED"
        assert not (sample.server.runtime_root / "blob" / marker).exists()


def test_owner_revoke_preserves_history_hides_current_resource_and_allows_regeneration(
    collaboration_space_factory,
) -> None:
    sample = collaboration_space_factory("AUTHORIZE_BEFORE_ENQUEUE")
    marker = "case-revoke-history"
    object_name = f"{marker}/campus-digital-museum-package.zip"
    with httpx.Client(base_url=sample.base_url, follow_redirects=False, trust_env=False) as alice:
        _login(alice, "alice", sample.passwords["alice"])
        created = alice.post(
            f"/api/projects/{PROJECT_ID}/exports",
            headers={"X-Jiejian-Case-ID": marker},
        )
        assert created.status_code == 202
        ready_task = _wait_task(alice, sample.base_url, marker, sample.task_bearer)
        assert ready_task["state"] == "SUCCESS"
        assert ready_task["final_result"]["state"] == "READY"
        assert sample.server.storage.find_job(marker)["state"] == "SUCCESS"
        refreshed_project = alice.get(f"/api/projects/{PROJECT_ID}").json()
        assert refreshed_project["active_export"] == {
            "request_marker": marker,
            "task_id": ready_task["task_id"],
        }
        assert object_name in alice.get(
            f"/collaboration/exports?{sample.blob_sas}&restype=container&comp=list&prefix={marker}/"
        ).text

        for account in ("bob",):
            with httpx.Client(base_url=sample.base_url, follow_redirects=False, trust_env=False) as denied:
                _login(denied, account, sample.passwords[account])
                response = denied.request(
                    "DELETE",
                    f"/api/projects/{PROJECT_ID}/exports",
                    headers={"X-Jiejian-Case-ID": marker},
                )
                assert response.status_code == 403
                assert response.json()["code"] == "PROJECT_OWNER_REQUIRED"

        revoked = alice.request(
            "DELETE",
            f"/api/projects/{PROJECT_ID}/exports",
            headers={"X-Jiejian-Case-ID": marker},
        )
        assert revoked.status_code == 200
        assert revoked.json() == {
            "code": "EXPORT_REVOKED",
            "request_marker": marker,
            "revoked": True,
        }
        revoked_task = _wait_task(alice, sample.base_url, marker, sample.task_bearer)
        assert revoked_task["state"] == "REVOKED"
        assert revoked_task["final_result"] == {
            "artifact_id": ready_task["final_result"]["artifact_id"],
            "state": "REVOKED",
        }
        assert sample.server.storage.find_job(marker)["state"] == "REVOKED"

        project = alice.get(f"/api/projects/{PROJECT_ID}").json()
        assert project["export_state"] == "REVOKED"
        assert project["latest_task_id"] is None
        assert project["latest_artifact_id"] is None
        assert project["active_export"] is None
        owner = alice.get(
            f"/api/observer/resources/{RESOURCE_ID}",
            headers={"Authorization": f"Bearer {sample.owner_observer}"},
        )
        assert owner.json() == {"resource_id": RESOURCE_ID, "workflow_state": "ABSENT", "value": ""}
        listing = alice.get(
            f"/collaboration/exports?{sample.blob_sas}&restype=container&comp=list&prefix={marker}/"
        )
        assert object_name not in listing.text
        assert alice.get(f"/collaboration/exports/{object_name}?{sample.blob_sas}").status_code == 404
        # 历史工件保留在 runtime，但不再属于当前 Azure Blob 兼容命名空间。
        assert (sample.server.runtime_root / "blob" / marker / "campus-digital-museum-package.zip").is_file()

        database_path = sample.server.runtime_root / "database" / "collaboration-space.sqlite3"
        with sqlite3.connect(database_path) as database:
            job = database.execute(
                "SELECT state, task_id, project_id, actor_id, artifact_id, case_id, created_at_us, finished_at_us "
                "FROM export_jobs WHERE case_id = ?",
                (marker,),
            ).fetchone()
            assert job is not None and job[0] == "REVOKED"
            assert job[1] == ready_task["task_id"]
            assert job[2:6] == (PROJECT_ID, "alice", ready_task["final_result"]["artifact_id"], marker)
            assert all(type(value) is int and value > 0 for value in job[6:8])
            project_row = database.execute(
                "SELECT export_state, latest_task_id, latest_artifact_id, case_id FROM projects WHERE project_id = ?",
                (PROJECT_ID,),
            ).fetchone()
            assert project_row == ("REVOKED", None, None, None)
            assert database.execute(
                "SELECT workflow_state, value FROM resource_state WHERE resource_id = ?",
                (RESOURCE_ID,),
            ).fetchone() == ("ABSENT", "")

        audit_path = sample.server.runtime_root / "audit" / "events.jsonl"
        queue_path = sample.server.runtime_root / "queue" / "messages.jsonl"
        audit = [json.loads(line) for line in audit_path.read_text(encoding="utf-8").splitlines()]
        queued = [json.loads(line) for line in queue_path.read_text(encoding="utf-8").splitlines()]
        assert [item["event_type"] for item in audit if item["case_tag"] == marker] == [
            *TRACE_SEMANTIC_KEYS,
            "EXPORT_REVOKED",
        ]
        assert [item["event_type"] for item in queued if item["case_tag"] == marker] == [
            "EXPORT_ENQUEUED",
            "TASK_RUNNING",
            "EXPORT_READY",
            "EXPORT_REVOKED",
        ]
        assert [item["sequence"] for item in audit if item["case_tag"] == marker] == list(range(1, 10))
        assert [item["sequence"] for item in queued if item["case_tag"] == marker] == [1, 2, 3, 4]
        assert next(item for item in audit if item["event_type"] == "EXPORT_REVOKED")["effect"] == "REVOKED"
        assert next(item for item in queued if item["event_type"] == "EXPORT_REVOKED")["result"] == "revoked"

        repeated = alice.request(
            "DELETE",
            f"/api/projects/{PROJECT_ID}/exports",
            headers={"X-Jiejian-Case-ID": marker},
        )
        assert repeated.status_code == 200
        assert repeated.json()["code"] == "EXPORT_ALREADY_REVOKED"
        assert audit_path.read_text(encoding="utf-8").count('"event_type":"EXPORT_REVOKED"') == 1
        assert queue_path.read_text(encoding="utf-8").count('"event_type":"EXPORT_REVOKED"') == 1
        reused = alice.post(
            f"/api/projects/{PROJECT_ID}/exports",
            headers={"X-Jiejian-Case-ID": marker},
        )
        assert reused.status_code == 409
        assert reused.json()["code"] == "EXPORT_MARKER_REVOKED"
        assert sample.server.storage.find_job(marker)["state"] == "REVOKED"

        regenerated_marker = "case-revoke-regenerated"
        regenerated = alice.post(
            f"/api/projects/{PROJECT_ID}/exports",
            headers={"X-Jiejian-Case-ID": regenerated_marker},
        )
        assert regenerated.status_code == 202
        assert regenerated.json()["request_marker"] != marker
        assert _wait_task(alice, sample.base_url, regenerated_marker, sample.task_bearer)["state"] == "SUCCESS"
        assert sample.server.storage.find_job(marker)["state"] == "REVOKED"
        assert sample.server.storage.find_job(regenerated_marker)["state"] == "SUCCESS"
        assert alice.get(f"/api/projects/{PROJECT_ID}").json()["active_export"]["request_marker"] == regenerated_marker


def test_revoke_is_safe_without_an_active_export_and_conflicts_while_processing(
    collaboration_space_factory,
) -> None:
    sample = collaboration_space_factory("AUTHORIZE_BEFORE_ENQUEUE")
    with httpx.Client(base_url=sample.base_url, follow_redirects=False, trust_env=False) as alice:
        _login(alice, "alice", sample.passwords["alice"])
        missing = alice.request(
            "DELETE",
            f"/api/projects/{PROJECT_ID}/exports",
            headers={"X-Jiejian-Case-ID": "case-never-created"},
        )
        assert missing.status_code == 200
        assert missing.json()["code"] == "EXPORT_NOT_ACTIVE"

        marker = "case-revoke-processing"
        sample.server.storage.create_job(marker, "alice")
        processing = alice.request(
            "DELETE",
            f"/api/projects/{PROJECT_ID}/exports",
            headers={"X-Jiejian-Case-ID": marker},
        )
        assert processing.status_code == 409
        assert processing.json()["code"] == "EXPORT_NOT_READY_FOR_REVOKE"
        assert sample.server.storage.find_job(marker)["state"] == "QUEUED"


def test_reset_loopback_cleanup_and_runtime_files_contain_no_injected_secret(collaboration_space_factory) -> None:
    sample = collaboration_space_factory("ENQUEUE_BEFORE_AUTHORIZE")
    marker = "case-reset-cleanup"
    with httpx.Client(base_url=sample.base_url, follow_redirects=False, trust_env=False) as client:
        _login(client, "bob", sample.passwords["bob"])
        assert client.post(f"/api/projects/{PROJECT_ID}/exports", headers={"X-Jiejian-Case-ID": marker}).status_code == 403
        assert _wait_task(client, sample.base_url, marker, sample.task_bearer)["state"] == "SUCCESS"
        reset = client.post("/reset", headers={"X-Jiejian-Test-Mode": "1"})
        assert reset.status_code == 200
        assert _wait_task(client, sample.base_url, marker, sample.task_bearer)["state"] == "NOT_CREATED"
        project = client.get(f"/api/projects/{PROJECT_ID}").json()
        assert project["export_state"] == "NOT_CREATED"
        assert sample.server.storage.find_job(marker) is None
        for name in ("audit", "queue", "tasks", "blob"):
            assert list((sample.server.runtime_root / name).iterdir()) == []
    secret_values = tuple(sample.passwords.values()) + tuple(sample.session_material.values()) + (
        sample.task_bearer,
        sample.queue_sas,
        sample.blob_sas,
        sample.owner_observer,
    )
    for path in sample.server.runtime_root.rglob("*"):
        if path.is_file():
            assert not any(secret.encode("utf-8") in path.read_bytes() for secret in secret_values)
    descriptor = json.loads((sample.server.runtime_root / "environment.json").read_text(encoding="utf-8"))
    assert all("password" not in json.dumps(value).casefold() for value in descriptor.values())
    control = json.loads((sample.server.runtime_root / "control.json").read_text(encoding="utf-8"))
    assert control == {
        "schema_version": "1",
        "authorization_order": "ENQUEUE_BEFORE_AUTHORIZE",
        "owner_observation": "AVAILABLE",
        "blob_observation": "AVAILABLE",
    }


def test_server_requires_loopback_and_runtime_root_is_not_source_tree(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        CollaborationSpaceServer(
            ("0.0.0.0", 0),
            passwords={"alice": "a", "bob": "b"},
            runtime_root=tmp_path,
        )
    sample = create_collaboration_space_server(
        port=0,
        passwords={"alice": "a", "bob": "b"},
        runtime_root=tmp_path / "runtime",
    )
    try:
        assert sample.server_address[0] == "127.0.0.1"
        assert not str(sample.runtime_root).startswith(str(Path(__file__).resolve().parents[3] / "samples" / "web"))
    finally:
        sample.server_close()


def test_port_binding_failure_preserves_original_socket_error(tmp_path: Path) -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as occupied:
        occupied.bind(("127.0.0.1", 0))
        occupied.listen(1)
        port = int(occupied.getsockname()[1])
        with pytest.raises(OSError):
            CollaborationSpaceServer(
                ("127.0.0.1", port),
                passwords={"alice": "a", "bob": "b"},
                runtime_root=tmp_path / "uninitialized-server",
            )
