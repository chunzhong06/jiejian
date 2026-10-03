# 生产连接校验必须在无目标操作下完成；重复声明同一依赖可用，不得替换或调用另一套能力。
from unittest.mock import Mock
import pytest
from product.backend.composition import ApplicationCore
from tests.fixtures.preparation.action_preparation import MemorySecretStore


def test_connected_services_share_readers_and_reject_replacement(tmp_path):
    core = ApplicationCore(tmp_path / "var", secret_store=MemorySecretStore(), environ={})
    try:
        assert core.preparation_bindings.source_inspector is core.binding_sources
        assert core.preparation_materials._source_inspector is core.binding_sources
        assert core.check_runtime_builder._source_inspector is core.binding_sources
        core.checks.bind_delivery_recorder(core.development.attach_check_run)
        core.check_runtime_builder.bind_runtime_readers(reference_reader=core.runtime_ports.reference,
            sources_reader=core.proof_preparation.frozen_sources)
        core._validate_connections()
        replacement = Mock(side_effect=AssertionError("装配核对不得调用能力"))
        with pytest.raises(ValueError):
            core.checks.bind_delivery_recorder(replacement)
        with pytest.raises(ValueError):
            core.check_runtime_builder.bind_runtime_readers(reference_reader=replacement,
                sources_reader=core.proof_preparation.frozen_sources)
        replacement.assert_not_called()
    finally:
        core.close()


def test_missing_production_connection_is_rejected_before_a_use_case(tmp_path, monkeypatch):
    core = ApplicationCore(tmp_path / "var", secret_store=MemorySecretStore(), environ={})
    try:
        monkeypatch.setattr(core.checks, "_delivery_run_attacher", None)
        with pytest.raises(ValueError, match="尚未连接"):
            core._validate_connections()
        with core.uow_factory() as work:
            assert work.projects.list_all() == ()
    finally:
        core.close()
