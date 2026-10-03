# 验证当前 SourceChange API 的普通声明登记、精确读取和禁止客户端裁剪完整检查。
from uuid import uuid4
from tests.fixtures.preparation.action_preparation import MemorySecretStore
from tests.fixtures.checks.check_service import ready_check_harness
from tests.fixtures.control_plane import TestClient, create_app


def test_current_source_change_routes_preserve_project_and_reject_client_scope(tmp_path):
    app = create_app(tmp_path / "var", start_worker=False, secret_store=MemorySecretStore(), environ={})
    harness = ready_check_harness(tmp_path, core=app.state.context)
    project = harness.project_id
    current = app.state.context.application_understanding.get(project)
    app.state.context.application_understanding.analyze_source_for_change(project, revision=current.revision)
    with TestClient(app) as client:
        path = f"/api/projects/{project}/source-changes"
        assert client.get(path + "/latest").json()["data"] is None
        assert client.get(f"/api/projects/{project}/repair").json()["data"]["status"] is None
        task = client.post(f"/api/projects/{project}/development/tasks", json={"schema_version": "1",
            "operation_id": uuid4().hex, "title": "本机修改", "goal": "保持原有权限"}).json()["data"]
        body = {"schema_version": "2", "task_id": task["task_id"], "context_id": task["context_id"],
            "operation_id": uuid4().hex, "expected_version": task["task_version"], "reason": "登记实际源码", "claimed_paths": ["hint.py"]}
        submitted = client.post(path, json=body)
        assert submitted.status_code == 201, submitted.text
        receipt = submitted.json()["data"]
        assert client.post(path, json=body).json()["data"] == receipt
        change_id = receipt["change_id"]
        value = client.get(path + "/" + change_id).json()["data"]
        assert "changed_paths" not in value["change_set"]
        assert all(isinstance(value["change_set"][key], list) for key in ("added_paths", "modified_paths", "removed_paths"))
        assert value["manifest"]["submitted_by"] == "LOCAL_GUI"
        assert value["manifest"]["claimed_paths"] == ["hint.py"]
        assert client.get(path + "/" + change_id).json()["data"] == value
        assert client.get(path + "/latest").json()["data"] == value
        assert client.get(path + "?limit=101").status_code == 422
        assert client.get(f"/api/projects/foreign/source-changes/{change_id}").status_code != 200
        assert client.post(path, json={"schema_version": "1", "reason": "旧无键写入"}).status_code == 422
        assert client.post(path, json={"schema_version": "1", "reason": "拒绝代填权限", "permission_ids": []}).status_code == 422
        rejected = client.post(f"/api/projects/{project}/runs", json={"schema_version": "2", "expected_plan_fingerprint": "a" * 64,
            "idempotency_key": "cannot-select", "case_ids": []})
        assert rejected.status_code == 422
        with app.state.context.uow_factory() as work:
            assert all(job.operation_type != "CHECK" for job in work.jobs.list_for_project(project))
