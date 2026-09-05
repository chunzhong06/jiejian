# 验证准备只读接口与未接入写入口的明确边界。

import socket
import subprocess
from unittest.mock import Mock

from sqlalchemy import event

from tests.fixtures.action_preparation import MemorySecretStore, build_preparation_harness
from tests.fixtures.control_plane import TestClient, create_app


def test_preparation_get_matches_source_without_writes_or_external_calls(tmp_path, monkeypatch):
    app = create_app(tmp_path / "var", start_worker=False, secret_store=MemorySecretStore(), environ={})
    core = app.state.context
    h = build_preparation_harness(tmp_path, core=core)
    expected = core.preparation.get(h.project_id).model_dump(mode="json")
    statements = []
    listener = lambda connection, cursor, statement, parameters, context, many: statements.append(statement)
    event.listen(core.engine, "before_cursor_execute", listener)
    forbidden = Mock(side_effect=AssertionError("GET 不应触发外部操作"))
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    monkeypatch.setattr(core.identity_preparations, "start", forbidden)
    monkeypatch.setattr(core.recording_lifecycle, "finalize", forbidden)
    transport = Mock()
    monkeypatch.setattr(core.llm_profiles, "_transport", transport)
    with TestClient(app) as client:
        # Windows 事件循环先建立自己的 socketpair，再对请求期间的目标网络调用设断言。
        monkeypatch.setattr(socket.socket, "connect", forbidden)
        response = client.get(f"/api/projects/{h.project_id}/preparation")
        assert response.status_code == 200
        assert response.json()["data"] == expected
        assert client.get(f"/api/projects/{h.project_id}/preparation").json() ["data"] == expected
        assert statements and all(sql.lstrip().upper().startswith(("SELECT", "PRAGMA")) for sql in statements)
        forbidden.assert_not_called()
        assert transport.mock_calls == []
        assert client.post(f"/api/projects/{h.project_id}/prepare-safe", json={"schema_version": "1"}).status_code == 404
        assert client.post(f"/api/projects/{h.project_id}/preparation", json={"schema_version": "1"}).status_code == 405
        assert client.get("/api/projects/missing-project/preparation").status_code == 404
        registered = set(app.openapi()["paths"])
        assert not any(path.startswith(("/api/runs", "/api/changes")) or "prepare-safe" in path for path in registered)
    event.remove(core.engine, "before_cursor_execute", listener)
