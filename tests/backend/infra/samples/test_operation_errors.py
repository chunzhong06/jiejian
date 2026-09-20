# 用 stub 验证 manager 清理异常优先级；不启动 Sample、进程或 HTTP 请求。
from threading import RLock
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.infra.samples.official import OfficialSampleManager
from tests.fixtures.runtime_environment import runtime_identity_environment


def test_stop_keeps_first_termination_error_and_attempts_existing_cleanup(tmp_path, monkeypatch):
    manager = OfficialSampleManager.__new__(OfficialSampleManager)
    manager._lock = RLock()
    manager._active = SimpleNamespace(experience_id="exp_" + "a" * 32, process=object(), secrets={"fixture": "value"},
        log_path=tmp_path / "sample.log", experience_root=tmp_path / "sample")
    first = JiejianError(ErrorCode.STATE_PRECONDITION, "终止首错")
    monkeypatch.setattr("product.backend.infra.samples.official.terminate_process_tree", Mock(side_effect=first))
    monkeypatch.setattr("product.backend.infra.samples.official._append_event", Mock(side_effect=OSError("log failed")))
    remove = Mock(side_effect=OSError("directory failed"))
    monkeypatch.setattr("product.backend.infra.samples.official.shutil.rmtree", remove)
    with pytest.raises(JiejianError) as error:
        manager.stop()
    assert error.value is first
    remove.assert_called_once_with(tmp_path / "sample")
    assert manager._active is None


def test_start_log_failure_does_not_mask_launch_error(tmp_path, monkeypatch):
    first = JiejianError(ErrorCode.RUNTIME_ENVIRONMENT_INVALID, "启动首错")
    manager = OfficialSampleManager(tmp_path / "var", Path(__file__).resolve().parents[4] / "samples/web/collaboration_space",
        runtime_identity_environment(tmp_path / "var"), process_launcher=Mock(side_effect=first))
    monkeypatch.setattr("product.backend.infra.samples.official._append_event", Mock(side_effect=OSError("log failed")))
    with pytest.raises(JiejianError) as error:
        manager.start()
    assert error.value is first
