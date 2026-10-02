# 运行归属必须唯一；普通项目与停止的示例不能通过隐式回退启动其他应用。
from unittest.mock import Mock

import pytest

from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.workflows.runtime_ports import ProjectRuntimePorts, RuntimeProvider
from product.protocols.runtime_identity import ControlledRuntimeReference


def test_unowned_project_does_not_call_sample_or_guess_launch():
    read, load = Mock(), Mock()
    ports = ProjectRuntimePorts((RuntimeProvider("sample", lambda project: project == "sample", read, load),))
    assert ports.reference("ordinary") is None
    with pytest.raises(JiejianError) as failure:
        ports.load_delivery("ordinary", "a" * 64)
    assert failure.value.to_dict()["details"]["reason"] == "RUNTIME_PROVIDER_UNAVAILABLE"
    read.assert_not_called()
    load.assert_not_called()


def test_persisted_owner_routes_exact_project_and_revision():
    reference = ControlledRuntimeReference(instance_id="rti_" + "1" * 32, manifest_fingerprint="a" * 64,
        source_fingerprint="b" * 64, process_id=123, process_created_at=456, owner_id="exp_" + "2" * 32)
    read, load = Mock(return_value=None), Mock(return_value=reference)
    other_read, other_load = Mock(), Mock()
    ports = ProjectRuntimePorts((RuntimeProvider("first", lambda project: project == "first", read, load),
        RuntimeProvider("second", lambda project: project == "second", other_read, other_load)))
    assert ports.reference("first") is None
    assert ports.load_delivery("first", "b" * 64) is reference
    load.assert_called_once_with("first", "b" * 64)
    other_read.assert_not_called()
    other_load.assert_not_called()


def test_ambiguous_owner_never_loads_either_target():
    first, second = Mock(), Mock()
    ports = ProjectRuntimePorts((RuntimeProvider("a", lambda _: True, first, first),
        RuntimeProvider("b", lambda _: True, second, second)))
    with pytest.raises(JiejianError) as failure:
        ports.reference("same-project")
    assert failure.value.to_dict()["details"]["reason"] == "RUNTIME_PROVIDER_CONFLICT"
    first.assert_not_called()
    second.assert_not_called()


def test_owned_source_failure_is_not_reinterpreted_as_unowned():
    error = JiejianError(ErrorCode.STATE_PRECONDITION, "旧实例退出尚未确认")
    load = Mock(side_effect=error)
    ports = ProjectRuntimePorts((RuntimeProvider("owned", lambda _: True, Mock(side_effect=error), load),))
    with pytest.raises(JiejianError) as failure:
        ports.reference("project")
    assert failure.value is error
    with pytest.raises(JiejianError) as failure:
        ports.load_delivery("project", "c" * 64)
    assert failure.value is error
    load.assert_called_once()
