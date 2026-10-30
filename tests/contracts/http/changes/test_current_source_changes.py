# 验证当前 SourceChange API 的普通声明登记、精确读取和禁止客户端裁剪完整检查。

import pytest
from uuid import uuid4
from tests.support.secrets import MemorySecrets
from tests.support.builders.checks.check_service import ready_check_harness
from tests.support.builders.control_plane import TestClient, create_app


def test_current_source_change_routes_preserve_project_and_reject_client_scope(tmp_path):
    app = create_app(tmp_path / "var", start_worker=False, secret_store=MemorySecrets(), environ={})
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

pytestmark = [pytest.mark.level3]


def test_registration_previews_real_files_and_rejects_changed_source(tmp_path):
    app = create_app(tmp_path / 'var', start_worker=False, secret_store=MemorySecrets(), environ={})
    h = ready_check_harness(tmp_path, core=app.state.context)
    understanding = app.state.context.application_understanding.get(h.project_id)
    app.state.context.application_understanding.analyze_source_for_change(h.project_id, revision=understanding.revision)
    path = f'/api/projects/{h.project_id}/source-changes'
    source = h.source_root / 'routes.py'
    source.write_text('def update_document():\n    return False\n', encoding='utf-8')
    with TestClient(app) as client:
        response = client.get(path + '/registration-preview')
        assert response.status_code == 200, response.text
        preview = response.json()['data']
        assert preview['files'] == [{'path': 'routes.py', 'status': 'MODIFIED'}]
        assert client.get(path).json()['data'] == []
        body = dict(schema_version='1', operation_id=uuid4().hex, expected_registration_fingerprint=preview['fingerprint'],
            expected_source_fingerprint=preview['source_fingerprint'], reason='修复访问控制')
        source.write_text('def update_document():\n    return None\n', encoding='utf-8')
        assert client.post(path + '/register', json=body).status_code == 409
        assert client.get(path).json()['data'] == []
        current = client.get(path + '/registration-preview').json()['data']
        body['expected_source_fingerprint'] = current['source_fingerprint']
        saved = client.post(path + '/register', json=body)
        assert saved.status_code == 201, saved.text
        assert client.post(path + '/register', json=body).json()['data'] == saved.json()['data']
