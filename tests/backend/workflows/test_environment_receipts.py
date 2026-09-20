# 使用 stub 进程所有者验证环境回执、重启投影和首错保留；不运行 Sample 或目标请求。
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.workflows.official_sample import OfficialSampleExperience
from product.backend.api.routers.experience import build_experience_router
from tests.fixtures.action_preparation import build_preparation_harness


@pytest.fixture
def environment(tmp_path):
    harness = build_preparation_harness(tmp_path)
    manager = SimpleNamespace(active=None, installation=SimpleNamespace(available=True, display_name="协作空间", reason=None))
    def start(**kwargs):
        manager.active = SimpleNamespace(experience_id="exp_" + uuid4().hex, display_name="协作空间", source_root=harness.source_root, origin="http://127.0.0.1:8765")
        return manager.active
    def stop(*args):
        manager.active = None
    manager.start, manager.stop = Mock(side_effect=start), Mock(side_effect=stop)
    understanding = SimpleNamespace(connect=Mock(return_value=SimpleNamespace(project=SimpleNamespace(project_id=harness.project_id), understanding=SimpleNamespace(revision=1))),
        confirm_endpoint=Mock(return_value=SimpleNamespace(revision=2)), authorize_source_analysis=Mock(return_value=SimpleNamespace(revision=3)), analyze_source_for_change=Mock())
    arguments = dict(understanding=understanding, boundaries=Mock(), identities=Mock(), secret_store=Mock(), registry=Mock(),
        installer=Mock(), bindings=Mock(), preparation=Mock(), changes=Mock(), repairs=Mock(),
        uow_factory=harness.core.uow_factory, var_dir=harness.var_dir, archive_project=Mock(), clock_us=lambda: 100)
    experience = OfficialSampleExperience(manager, **arguments)
    yield SimpleNamespace(harness=harness, manager=manager, understanding=understanding, arguments=arguments, experience=experience)
    harness.close()


def test_start_stop_replay_and_persistent_history(environment):
    env = environment
    assert env.experience.status().lifecycle == "NOT_STARTED"
    key = str(uuid4())
    first = env.experience.start(consent=True, operation_id=key)
    assert first.lifecycle == "RUNNING" and first.operation_state == "SUCCEEDED"
    assert env.experience.start(consent=True, operation_id=key) == first
    assert env.manager.start.call_count == 1
    stop_key = str(uuid4())
    stopped = env.experience.stop(operation_id=stop_key)
    assert stopped.lifecycle == "STOPPED"
    assert env.experience.stop(operation_id=stop_key) == stopped
    assert env.manager.stop.call_count == 1
    assert env.arguments["archive_project"].call_count == 1
    # 重建服务不复活进程，但保留停止后的精确项目入口。
    rebuilt = OfficialSampleExperience(env.manager, **env.arguments)
    assert rebuilt.status().lifecycle == "STOPPED"
    assert rebuilt.status().history_project_id == env.harness.project_id
    assert len(rebuilt.history()["items"]) == 2
    with pytest.raises(JiejianError):
        rebuilt.stop(operation_id=key)


def test_restart_pending_is_unknown_and_never_reexecutes(environment):
    env = environment
    key = str(uuid4())
    with env.harness.core.uow_factory() as work:
        work.environment_operations.save(dict(operation_id=key, operation="start", state="PENDING", started_at_us=1,
            finished_at_us=None, experience_id=None, project_id=None, error_code=None, cleanup_confirmed=False))
        work.commit()
    rebuilt = OfficialSampleExperience(env.manager, **env.arguments)
    assert rebuilt.status().lifecycle == "UNKNOWN"
    assert rebuilt.history()["items"][0]["state"] == "UNKNOWN"
    assert rebuilt.start(consent=True, operation_id=key).operation_state == "UNKNOWN"
    env.manager.start.assert_not_called()
    with env.harness.core.uow_factory() as work:
        assert work.environment_operations.get(key)["state"] == "PENDING"
    with pytest.raises(JiejianError):
        rebuilt.stop()
    assert rebuilt.status().lifecycle == "UNKNOWN"
    env.manager.stop.assert_not_called()


def test_start_partial_project_and_first_error_survive_cleanup_failure(environment):
    env = environment
    env.understanding.confirm_endpoint.side_effect = JiejianError(ErrorCode.APPLICATION_ENDPOINT_INVALID, "首错")
    env.manager.stop.side_effect = RuntimeError("secret raw cleanup failure")
    key = str(uuid4())
    with pytest.raises(JiejianError) as error:
        env.experience.start(consent=True, operation_id=key)
    assert error.value.code == "APPLICATION_ENDPOINT_INVALID"
    receipt = env.experience.history()["items"][0]
    assert receipt["state"] == "UNKNOWN" and receipt["project_id"] == env.harness.project_id
    assert receipt["error_code"] == "APPLICATION_ENDPOINT_INVALID"
    assert "secret raw" not in str(receipt)
    assert env.experience.start(consent=True, operation_id=key).operation_state == "UNKNOWN"
    assert env.manager.start.call_count == 1


def test_archive_failure_not_stopped_and_new_explicit_stop_finishes(environment):
    env = environment
    env.experience.start(consent=True)
    archive = env.arguments["archive_project"]
    archive.side_effect = JiejianError(ErrorCode.STORAGE_FAILURE, "归档失败")
    key = str(uuid4())
    with pytest.raises(JiejianError):
        env.experience.stop(operation_id=key)
    assert env.experience.status().lifecycle == "UNKNOWN"
    assert not env.experience.status().active
    env.experience.stop(operation_id=key)
    assert archive.call_count == 1
    archive.side_effect = None
    assert env.experience.stop(operation_id=str(uuid4())).lifecycle == "STOPPED"
    assert archive.call_count == 2


def test_restart_completed_start_is_not_running(environment):
    env = environment
    env.experience.start(consent=True)
    env.manager.active = None
    rebuilt = OfficialSampleExperience(env.manager, **env.arguments)
    assert rebuilt.status().lifecycle == "UNKNOWN"
    assert rebuilt.status().project_id is None
    assert rebuilt.status().history_project_id == env.harness.project_id
    with pytest.raises(JiejianError):
        rebuilt.stop()
    assert rebuilt.status().lifecycle == "UNKNOWN"
    assert rebuilt.status().history_project_id == env.harness.project_id
    env.manager.stop.assert_not_called()


def test_environment_api_optional_id_and_history(environment):
    app = FastAPI()
    app.include_router(build_experience_router(SimpleNamespace(official_experience=environment.experience)))
    with TestClient(app) as client:
        key = str(uuid4())
        body = dict(schema_version="1", consent=True, operation_id=key)
        path = "/api/experience/official-sample"
        assert client.post(path + "/start", json=body).json()["data"]["operation_id"] == key
        assert client.post(path + "/start", json=body).status_code == 200
        assert environment.manager.start.call_count == 1
        assert client.post(path + "/stop", json={"operation_id": str(uuid4())}).json()["data"]["lifecycle"] == "STOPPED"
        assert len(client.get(path + "/history").json()["data"]["items"]) == 2
        assert client.get(path + "/history?limit=101").status_code == 422


def test_failed_manager_stop_cannot_be_retried_as_empty_success(environment):
    env = environment
    env.experience.start(consent=True)
    def failed(*args):
        env.manager.active = None
        raise OSError("injected incomplete cleanup")
    env.manager.stop.side_effect = failed
    with pytest.raises(JiejianError):
        env.experience.stop()
    with pytest.raises(JiejianError):
        env.experience.stop()
    assert env.manager.stop.call_count == 1
    assert env.experience.status().lifecycle == "UNKNOWN"


def test_busy_rejection_keeps_running_environment_and_terminal_receipt(environment, monkeypatch):
    env = environment
    env.experience.start(consent=True)
    monkeypatch.setattr(env.experience, "_require_idle", Mock(side_effect=JiejianError(ErrorCode.STATE_PRECONDITION, "仍有活动任务")))
    key = str(uuid4())
    with pytest.raises(JiejianError):
        env.experience.stop(operation_id=key)
    value = env.experience.status()
    assert value.lifecycle == "RUNNING" and value.active
    assert value.operation_id == key and value.operation_state == "FAILED"
    env.manager.stop.assert_not_called()
    env.arguments["archive_project"].assert_not_called()
    assert env.experience.stop(operation_id=key).operation_state == "FAILED"
