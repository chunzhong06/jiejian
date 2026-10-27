# 用 stub 验证 manager 清理异常优先级；不启动 Sample、进程或 HTTP 请求。
from threading import RLock
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from product.backend.domain.errors import ErrorCode, JiejianError
from product.backend.infrastructure.samples.official.manager import OfficialSampleManager
from tests.support.builders.runtime.runtime_environment import runtime_identity_environment, write_python_installation_contract


def test_stop_keeps_first_termination_error_and_attempts_existing_cleanup(tmp_path, monkeypatch):
    manager = OfficialSampleManager.__new__(OfficialSampleManager)
    manager._lock = RLock()
    manager._active = SimpleNamespace(experience_id="exp_" + "a" * 32, process=object(), secrets={"fixture": "value"},
        log_path=tmp_path / "sample.log", experience_root=tmp_path / "sample")
    first = JiejianError(ErrorCode.STATE_PRECONDITION, "终止首错")
    monkeypatch.setattr("product.backend.infrastructure.samples.official.manager.terminate_process_tree", Mock(side_effect=first))
    monkeypatch.setattr("product.backend.infrastructure.samples.official.manager._append_event", Mock(side_effect=OSError("log failed")))
    remove = Mock(side_effect=OSError("directory failed"))
    monkeypatch.setattr("product.backend.infrastructure.samples.official.manager.shutil.rmtree", remove)
    with pytest.raises(JiejianError) as error:
        manager.stop()
    assert error.value is first
    remove.assert_called_once_with(tmp_path / "sample")
    assert manager._active is None


def test_start_log_failure_does_not_mask_launch_error(tmp_path, monkeypatch):
    first = JiejianError(ErrorCode.RUNTIME_ENVIRONMENT_INVALID, "启动首错")
    manager = OfficialSampleManager(tmp_path / "var", write_python_installation_contract(tmp_path / "installation-contract"),
        runtime_identity_environment(tmp_path / "var"), process_launcher=Mock(side_effect=first))
    monkeypatch.setattr("product.backend.infrastructure.samples.official.manager._append_event", Mock(side_effect=OSError("log failed")))
    with pytest.raises(JiejianError) as error:
        manager.start()
    assert error.value is first

pytestmark = [pytest.mark.level3]
