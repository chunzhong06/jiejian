# 验证真实 CURRENT AI 接线的冷读取、显式生成、单飞、缓存重验和控制面边界。

import json
import threading
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient as RawTestClient

from product.backend.infra.llm.adapters.base import LLMTransportError
from product.backend.infra.llm.config import LLMProviderType
from product.backend.workflows.assistant.current_surfaces import PreparationAssistantSurfaceResolver
from product.backend.workflows.assistant.templates import AssistantTemplateId
from tests.fixtures.action_preparation import MemorySecretStore, build_preparation_harness
from tests.fixtures.control_plane import TEST_CONTROL_ORIGIN, TestClient, create_app


class Provider:
    provider = LLMProviderType.OPENAI
    profile_name = "offline-test"

    def __init__(self):
        self.calls = 0
        self.error = False
        self.entered = None
        self.release = None

    def invoke(self, prompt, *, json_schema):
        self.calls += 1
        if self.entered:
            self.entered.set()
            assert self.release.wait(10)
        if self.error:
            raise LLMTransportError("timeout")
        data = json.loads(prompt.split("PROJECT_DATA_BEGIN\n", 1)[1].split("\nPROJECT_DATA_END", 1)[0])
        return SimpleNamespace(model="offline", reasoning_effort=None, final_payload=json.dumps({
            "schema_version": "1", "template_id": data["template_id"], "template_version": "1",
            "suggestions": [{"kind": "EXPLANATION", "entity_ids": [data["entities"][0]["entity_id"]], "explanation": "现有材料仍需人工补齐。"}]}))


@pytest.fixture
def context(tmp_path, monkeypatch):
    app = create_app(tmp_path / "var", start_worker=False, secret_store=MemorySecretStore(), environ={})
    h = build_preparation_harness(tmp_path, core=app.state.context)
    provider = Provider()
    profiles = h.core.llm_profiles
    monkeypatch.setattr(profiles, "get_settings", lambda: SimpleNamespace(enabled=True, default_profile_name="offline-test"))
    monkeypatch.setattr(profiles, "get", lambda _: SimpleNamespace(enabled=True, secret_configured=True))
    monkeypatch.setattr(profiles, "resolve_provider", lambda _: provider)
    yield app, h, provider
    h.close()


def _path(h):
    return f"/api/projects/{h.project_id}/assistant/preparation-explanation"


def test_current_get_is_cold_post_generates_and_cache_rechecks_entity_types(context):
    app, h, provider = context
    assert isinstance(h.core.assistant_surfaces, PreparationAssistantSurfaceResolver)
    with TestClient(app) as client:
        params = {"business_action_id": h.action.action_id}
        initial = client.get(_path(h), params=params)
        assert initial.status_code == 200 and initial.json()["data"]["status"] == "REFRESH_NEEDED"
        assert provider.calls == 0
        generated = client.post(_path(h), params=params, json={"schema_version": "1"})
        assert generated.status_code == 200 and generated.json()["data"]["status"] == "READY"
        assert provider.calls == 1
        assert client.get(_path(h), params=params).json()["data"] == generated.json()["data"]
        assert client.post(_path(h), params=params, json={"schema_version": "1"}).json()["data"]["status"] == "READY"
        assert provider.calls == 1
        view = h.core.assistant_service.get_project(h.project_id, AssistantTemplateId.PREPARATION_EXPLANATION,
            business_action_id=h.action.action_id)
        cache_path = h.core.assistant_service._cache._path(view.subject_id, view.template_id, view.state_fingerprint)
        payload = json.loads(cache_path.read_text(encoding="utf-8"))
        payload["suggestions"][0]["kind"] = "OBSERVATION_GAP"
        # ID 仍存在但 ACTION 不属于 effect category，缓存必须重新做 typed 校验。
        cache_path.write_text(json.dumps(payload), encoding="utf-8")
        assert client.get(_path(h), params=params).json()["data"]["status"] == "REFRESH_NEEDED"
        assert provider.calls == 1


def test_explicit_post_single_flight_shares_current_focus(context):
    app, h, provider = context
    provider.entered, provider.release = threading.Event(), threading.Event()
    params = {"business_action_id": h.action.action_id}
    # 两个请求各自的受控 ASGI portal，模拟同时进入同一 ApplicationCore 的调用。
    def post():
        client = TestClient(app)
        try:
            return client.post(_path(h), params=params, json={"schema_version": "1"})
        finally:
            client.close()
    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(post)
        try:
            assert provider.entered.wait(10)
            second = executor.submit(post).result(timeout=10)
            assert second.status_code == 200 and second.json()["data"]["status"] == "GENERATING"
            assert provider.calls == 1
        finally:
            provider.release.set()
        assert first.result(timeout=10).json()["data"]["status"] == "READY"


def test_provider_failure_backoff_and_explicit_retry_preserve_manual_preparation(context):
    app, h, provider = context
    provider.error = True
    before = h.core.preparation.get(h.project_id)
    with TestClient(app) as client:
        params = {"business_action_id": h.action.action_id}
        response = client.post(_path(h), params=params, json={"schema_version": "1"})
        assert response.json()["data"]["status"] == "BACKOFF"
        assert client.get(_path(h), params=params).json()["data"]["status"] == "BACKOFF"
        assert client.post(_path(h), params=params, json={"schema_version": "1"}).json()["data"]["status"] == "BACKOFF"
        assert provider.calls == 1
        assert client.get(f"/api/projects/{h.project_id}/preparation").json()["data"] == before.model_dump(mode="json")
        provider.error = False
        assert client.post(_path(h), params=params, json={"schema_version": "1", "retry": True}).json()["data"]["status"] == "READY"
        assert provider.calls == 2


@pytest.mark.parametrize("body", [{}, {"schema_version": 1}, {"schema_version": "2"},
    {"schema_version": "1", "facts": {}}, {"schema_version": "1", "prompt": "不可信指令"}, {"schema_version": "1", "retry": "true"}])
def test_current_assistant_posts_reject_arbitrary_input(context, body):
    app, h, provider = context
    with TestClient(app) as client:
        response = client.post(_path(h), params={"business_action_id": h.action.action_id}, json=body)
        assert response.status_code == 422
    assert provider.calls == 0


@pytest.mark.parametrize("params,status", [({}, 400), ({"business_action_id": "invalid"}, 422),
    ({"business_action_id": "bac_" + "1" * 32, "facts": "{}"}, 422),
    ({"business_action_id": "bac_" + "1" * 32, "business_actor_id": "bar_" + "1" * 32}, 400)])
def test_current_query_focus_is_strict(context, params, status):
    app, h, provider = context
    with TestClient(app) as client:
        assert client.get(_path(h), params=params).status_code == status
    assert provider.calls == 0


def test_current_surface_set_and_old_result_error_routes_absent(context):
    app, h, provider = context
    with TestClient(app) as client:
        schema = client.get("/openapi.json").json()
        assert set(schema["components"]["schemas"]["ProjectAssistantSurface"]["enum"]) == {
            "implementation-mapping", "recording-review", "preparation-explanation"}
        for surface in ("next-step", "candidate-review", "identity-preparation", "observation-recovery", "check-preview-explanation"):
            assert client.get(f"/api/projects/{h.project_id}/assistant/{surface}").status_code == 422
        assert client.get("/api/runs/run-demo/assistant/result").status_code == 404
        assert client.post("/api/assistant/error", json={"schema_version": "1", "error_code": "INPUT_INVALID"}).status_code == 404
    assert provider.calls == 0


@pytest.mark.parametrize("authorization", ["missing_session", "wrong_origin"])
def test_current_assistant_local_control(context, authorization):
    app, h, provider = context
    cls = RawTestClient if authorization == "missing_session" else TestClient
    with cls(app, base_url=TEST_CONTROL_ORIGIN) as client:
        response = client.post(_path(h), params={"business_action_id": h.action.action_id}, json={"schema_version": "1"},
            headers={"Origin": TEST_CONTROL_ORIGIN if authorization == "missing_session" else "http://127.0.0.1:9999"})
        assert response.status_code == 403
    assert provider.calls == 0


def test_unique_mapping_post_is_ready_without_calling_provider(context):
    app, h, provider = context
    with TestClient(app) as client:
        path = f"/api/projects/{h.project_id}/assistant/implementation-mapping"
        response = client.post(path, params={"business_action_id": h.action.action_id}, json={"schema_version": "1"})
        assert response.status_code == 200
        assert response.json()["data"]["status"] == "READY" and not response.json()["data"]["can_generate"]
    assert provider.calls == 0
