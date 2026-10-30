# 验证准备依赖装配不启动进程，关闭失败时保留监督事实、数据库与运行版本引用。

import subprocess
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from product.backend.bootstrap.application import ApplicationCore
from product.backend.domain.errors import ErrorCode, JiejianError
from tests.support.builders.preparation.action_preparation import build_preparation_harness
from tests.support.secrets import MemorySecrets


def test_core_constructs_preparation_readers_without_starting_processes(tmp_path, monkeypatch):
    launch = Mock(side_effect=AssertionError("构造不应启动进程"))
    class ForbiddenProcess(subprocess.Popen):
        def __init__(self, *args, **kwargs):
            launch(*args, **kwargs)

    monkeypatch.setattr(subprocess, "Popen", ForbiddenProcess)
    core = ApplicationCore(tmp_path / "var", secret_store=MemorySecrets(), environ={})
    try:
        assert core.identity_preparations.list("prj_" + "0" * 32) == ()
        assert core.identity_preparations.active_runtime_paths() == ()
        assert not core.worker.is_running()
        launch.assert_not_called()
    finally:
        core.close()


@pytest.mark.parametrize("failure", ["worker", "runtime", "sample", "manager", "vault", "secrets", "engine", "assets", None])
def test_core_close_releases_independent_owners_and_protects_shared_resources(failure):
    events = []
    core = ApplicationCore.__new__(ApplicationCore)
    def step(name):
        def invoke():
            events.append(name)
            if name == failure:
                raise JiejianError(ErrorCode.PROCESS_TREE_FAILED, "注入关闭失败")
        return invoke
    core.worker = SimpleNamespace(stop=step("worker"))
    core.runtime_worker = SimpleNamespace(stop=step("runtime"))
    core.official_experience = SimpleNamespace(close=step("sample"))
    core.secret_store = SimpleNamespace(clear=step("secrets"))
    core.identity_preparations = SimpleNamespace(close=step("manager"))
    core.runtime_secrets = SimpleNamespace(clear=step("vault"))
    core.engine = SimpleNamespace(dispose=step("engine"))
    core.maintenance = SimpleNamespace(assets=SimpleNamespace(close=step("assets")))
    if failure:
        with pytest.raises(JiejianError):
            core.close()
        stops = ["worker", "sample", "runtime", "manager"]
        assert set(events) == set(stops if failure in stops else stops + ["vault", "secrets", "engine", "assets"])
    else:
        core.close()
        assert set(events) == {"worker", "sample", "runtime", "manager", "vault", "secrets", "engine", "assets"}
    assert len(events)==len(set(events))
    if {"vault","secrets","engine","assets"}&set(events):
        assert max(events.index(name) for name in ("worker","sample","runtime","manager")) < min(events.index(name) for name in ("vault","secrets","engine","assets"))


def test_worker_cleanup_failure_keeps_login_recoverable_and_protects_shared_resources(tmp_path, monkeypatch):
    h = build_preparation_harness(tmp_path)
    core = h.core
    identity = core.test_identities.reset(h.identities[0].identity_id)
    manager = core.identity_preparations
    wake = Mock()
    manager.bind_worker(wake)
    started = manager.start(identity.identity_id)
    wake.assert_called_once_with()
    directory = core.paths.identity_preparations / started.preparation_id
    directory.mkdir()
    disposed = Mock(wraps=core.engine.dispose)
    monkeypatch.setattr(core.engine, "dispose", disposed)
    stop = core.worker.stop
    monkeypatch.setattr(core.worker, "stop", Mock(side_effect=JiejianError(
        ErrorCode.PROCESS_TREE_FAILED, "注入 Worker 关闭失败")))
    try:
        with pytest.raises(JiejianError):
            core.close()
        disposed.assert_not_called()
        assert manager.status(started.preparation_id) == started
        assert manager.active_runtime_paths() == (directory,)
        relative = directory.relative_to(core.var_dir).as_posix()
        item = next(item for item in core.maintenance.status()["inventory"] if item["relative_path"] == relative)
        assert item["state"] == "PROTECTED"

        # 尚未交给 Worker 的任务可直接取消；确认无执行者后才允许发布闲置标记。
        assert manager.cancel(started.preparation_id).status.value == "CANCELLED"
        with core.uow_factory() as work:
            job = work.jobs.get(started.job_id)
        assert job.attempt == 0
        manager.reconcile_exited(job)
        assert manager.active_runtime_paths() == ()
        item = next(item for item in core.maintenance.status()["inventory"] if item["relative_path"] == relative)
        assert item["state"] == "CLEANABLE"
    finally:
        monkeypatch.setattr(core.worker, "stop", stop)
        core.close()
    disposed.assert_called_once()

pytestmark = [pytest.mark.level3]
