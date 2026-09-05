# 验证正式权限草稿 API 只返回临时建议，禁用、非法输入与 provider 失败不改变手工业务事实。

import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient as RawTestClient
from sqlalchemy import event

from product.backend.infra.llm.adapters.base import LLMTransportError
from tests.fixtures.action_preparation import MemorySecretStore, build_preparation_harness
from tests.fixtures.control_plane import TEST_CONTROL_ORIGIN, TestClient, create_app


class Provider:
    def __init__(self):
        self.calls = 0
        self.error = False
    def invoke(self, prompt, *, json_schema):
        self.calls += 1
        if self.error:
            raise LLMTransportError("timeout")
        data = json.loads(prompt.split("USER_DATA=", 1)[1])
        assert all(value not in prompt for value in ("bac_", "bar_", "bef_", "secret_ref", "http://"))
        return SimpleNamespace(final_payload=json.dumps({"suggestions": [{"option_id": data["options"][0]["option_id"],
            "expectation": "ALLOW", "source_quote": data["human_text"]}], "unresolved_quotes": []}))


@pytest.fixture
def context(tmp_path, monkeypatch):
    app = create_app(tmp_path / "var", start_worker=False, secret_store=MemorySecretStore(), environ={})
    h = build_preparation_harness(tmp_path, core=app.state.context)
    provider = Provider()
    settings = SimpleNamespace(enabled=True, default_profile_name="offline-test")
    monkeypatch.setattr(h.core.llm_profiles, "get_settings", lambda: settings)
    monkeypatch.setattr(h.core.llm_profiles, "get", lambda _: SimpleNamespace(enabled=True, secret_configured=True))
    monkeypatch.setattr(h.core.llm_profiles, "resolve_provider", lambda _: provider)
    yield app, h, provider, settings
    h.close()


def test_draft_api_returns_formal_atoms_without_database_cache_or_approval_writes(context, monkeypatch):
    app, h, provider, _ = context
    boundary = h.core.business_boundaries.view(h.project_id)
    before = boundary.model_dump(mode="json")
    forbidden = Mock(side_effect=AssertionError("草稿没有审批能力"))
    for name in ("create_proposal", "create_maintenance_proposal", "approve"):
        monkeypatch.setattr(h.core.business_boundaries, name, forbidden)
    statements = []
    def listener(connection, cursor, statement, parameters, context, many):
        statements.append(statement)
    with TestClient(app) as client:
        # 启动可预建缓存目录；只比较本次草稿请求是否产生缓存内容。
        cache_root = h.core.assistant_service._cache._root
        cache_before = {str(p.relative_to(cache_root)): p.read_bytes() for p in cache_root.rglob("*") if p.is_file()}
        event.listen(h.core.engine, "before_cursor_execute", listener)
        response = client.post(f"/api/projects/{h.project_id}/permission-drafts", json={"schema_version": "1", "text": "普通成员可以更新自己的文档。"})
        event.remove(h.core.engine, "before_cursor_execute", listener)
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["status"] == "READY_FOR_REVIEW" and len(data["boundary_fingerprint"]) == 64
        suggestion = data["suggestions"][0]
        assert suggestion["business_action_id"] == h.action.action_id and suggestion["action_revision"] == 1
        assert suggestion["subject_actor_id"] == h.actor.actor_id
        assert suggestion["resource_owner_actor_id"] == h.actor.actor_id
        assert suggestion["protected_effect_ids"] == [h.effect_id]
        assert set(suggestion) == {"option_ids", "subject_actor_id", "subject_actor_revision", "business_action_id", "action_revision",
            "resource_owner_actor_id", "resource_owner_actor_revision", "relation", "protected_effect_ids", "subject_display_name",
            "action_display_name", "resource_owner_display_name", "effect_display_names", "current_expectation", "suggested_expectation", "source_quotes"}
        assert statements and all(sql.lstrip().upper().startswith(("SELECT", "PRAGMA")) for sql in statements)
        assert h.core.business_boundaries.view(h.project_id).model_dump(mode="json") == before
        assert {str(p.relative_to(cache_root)): p.read_bytes() for p in cache_root.rglob("*") if p.is_file()} == cache_before
        forbidden.assert_not_called()
        assert provider.calls == 1
        assert client.get(f"/api/projects/{h.project_id}/permission-drafts").status_code == 405


@pytest.mark.parametrize("body", [{}, {"schema_version": 1, "text": "权限"}, {"schema_version": "1", "text": ""},
    {"schema_version": "1", "text": "字" * 2001}, {"schema_version": "1", "text": "权限", "facts": {}},
    {"schema_version": "1", "text": "权限", "prompt": "forbidden"}])
def test_permission_draft_api_strict_body(context, body):
    app, h, provider, _ = context
    with TestClient(app) as client:
        assert client.post(f"/api/projects/{h.project_id}/permission-drafts", json=body).status_code == 422
    assert provider.calls == 0


@pytest.mark.parametrize("authorization", ["missing_session", "wrong_origin"])
def test_permission_draft_api_keeps_local_control(context, authorization):
    app, h, provider, _ = context
    cls = RawTestClient if authorization == "missing_session" else TestClient
    with cls(app, base_url=TEST_CONTROL_ORIGIN) as client:
        response = client.post(f"/api/projects/{h.project_id}/permission-drafts", json={"schema_version": "1", "text": "权限"},
            headers={"Origin": TEST_CONTROL_ORIGIN if authorization == "missing_session" else "http://127.0.0.1:9999"})
        assert response.status_code == 403
    assert provider.calls == 0


@pytest.mark.parametrize("mode", ["disabled", "provider_error"])
def test_disabled_or_failed_ai_leaves_boundary_and_preparation_available(context, mode):
    app, h, provider, settings = context
    settings.enabled = mode != "disabled"
    provider.error = mode == "provider_error"
    before = h.core.business_boundaries.view(h.project_id)
    with TestClient(app) as client:
        response = client.post(f"/api/projects/{h.project_id}/permission-drafts", json={"schema_version": "1", "text": "权限"})
        assert response.status_code == 200 and response.json()["data"]["status"] == "UNAVAILABLE"
        assert client.get(f"/api/projects/{h.project_id}/business-boundaries").status_code == 200
        assert client.get(f"/api/projects/{h.project_id}/business-boundaries/maintenance-draft").status_code == 200
        assert client.get(f"/api/projects/{h.project_id}/preparation").status_code == 200
        assert h.core.business_boundaries.view(h.project_id) == before
        if mode == "disabled":
            assistant = client.post(f"/api/projects/{h.project_id}/assistant/preparation-explanation",
                params={"business_action_id": h.action.action_id}, json={"schema_version": "1"})
            assert assistant.json()["data"]["status"] == "DISABLED" and provider.calls == 0


def test_unknown_project_and_old_permission_writer_are_absent(context):
    app, h, provider, _ = context
    with TestClient(app) as client:
        assert client.post("/api/projects/missing/permission-drafts", json={"schema_version": "1", "text": "权限"}).status_code == 404
        paths = client.get("/openapi.json").json()["paths"]
        assert not any("permission-intents" in path or "permission-matrix" in path for path in paths)
    assert provider.calls == 0
