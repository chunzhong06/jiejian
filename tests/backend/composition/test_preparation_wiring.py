# 验证准备依赖装配不启动进程，并在关闭失败时保留监督事实与数据库。

import io
import subprocess
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from product.backend.composition import ApplicationCore
from product.backend.core.errors import ErrorCode, JiejianError
import product.backend.workflows.test_identities.preparation as preparation_module
from tests.fixtures.action_preparation import MemorySecretStore, build_preparation_harness


def test_core_constructs_preparation_readers_without_starting_processes(tmp_path, monkeypatch):
    launch = Mock(side_effect=AssertionError("构造不应启动进程"))
    monkeypatch.setattr(subprocess, "Popen", launch)
    core = ApplicationCore(tmp_path / "var", secret_store=MemorySecretStore(), environ={})
    try:
        assert core.workspace._preparation is core.preparation
        assert core.identity_preparations._application_understanding is core.application_understanding
        assert core.identity_preparations._business_boundaries is core.business_boundaries
        assert core.identity_preparations._identities is core.test_identities
        assert core.identity_preparations.active_runtime_paths() == ()
        assert not core.worker.is_running()
        launch.assert_not_called()
    finally:
        core.close()


@pytest.mark.parametrize("failure", ["worker", "manager", None])
def test_core_close_orders_resources_and_does_not_dispose_after_failure(failure):
    events = []
    core = ApplicationCore.__new__(ApplicationCore)
    def step(name):
        def invoke():
            events.append(name)
            if name == failure:
                raise JiejianError(ErrorCode.PROCESS_TREE_FAILED, "注入关闭失败")
        return invoke
    core.worker = SimpleNamespace(stop=step("worker"))
    core.identity_preparations = SimpleNamespace(close=step("manager"))
    core.runtime_secrets = SimpleNamespace(clear=step("vault"))
    core.engine = SimpleNamespace(dispose=step("engine"))
    if failure:
        with pytest.raises(JiejianError):
            core.close()
        assert events == (["worker"] if failure == "worker" else ["worker", "manager"])
    else:
        core.close()
        assert events == ["worker", "manager", "vault", "engine"]


def test_manager_cleanup_failure_protects_active_paths_and_engine(tmp_path, monkeypatch):
    h = build_preparation_harness(tmp_path)
    core = h.core
    identity = core.test_identities.reset(h.identities[0].identity_id)
    class Input(io.BytesIO):
        def close(self):
            pass
    class Process:
        stdin = Input()
        stdout = io.BytesIO()
        returncode = None
        def poll(self):
            return self.returncode
        def wait(self, timeout):
            if self.returncode is None:
                raise subprocess.TimeoutExpired("controlled-fake", timeout)
            return self.returncode
    process = Process()
    manager = core.identity_preparations
    manager._environment["JIEJIAN_PROJECT_ROOT"] = str(tmp_path)
    manager._process_launcher = lambda *_args, **_kwargs: process
    started = manager.start(identity.identity_id)
    active = manager._active[started.preparation_id]
    disposed = Mock(wraps=core.engine.dispose)
    monkeypatch.setattr(core.engine, "dispose", disposed)
    failure = [True]
    def terminate(*_):
        if failure[0]:
            raise JiejianError(ErrorCode.PROCESS_TREE_FAILED, "注入清理失败")
        process.returncode = 1
    monkeypatch.setattr(preparation_module, "terminate_process_tree", terminate)
    with pytest.raises(JiejianError):
        core.close()
    disposed.assert_not_called()
    assert manager._active[started.preparation_id] is active
    assert core.maintenance._active_runtime_paths() == (active.controls.root,)
    # 根已退出但尚未清理的树与 journal 仍由 maintenance 保护。
    process.returncode = 1
    assert manager.active_runtime_paths() == (active.controls.root,)
    monkeypatch.setattr(core.worker, "is_running", lambda: True)
    paths = core.maintenance._active_runtime_paths()
    assert paths == (core.paths.runtime, core.paths.worker_logs, core.paths.recording_logs, active.controls.root)
    monkeypatch.setattr(core.worker, "is_running", lambda: False)
    failure[0] = False
    core.close()
    disposed.assert_called_once()
    assert manager.active_runtime_paths() == ()
