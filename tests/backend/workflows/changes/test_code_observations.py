# 验证独立代码观察只附带元数据，内容漂移或 Git 不可用不拼接部分身份。
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4
import pytest
from product.backend.core.errors import JiejianError
from product.backend.infra.source_identity import GitSourceContext
from product.backend.workflows.changes.observations import CodeObservationService
from product.backend.infra.storage.code_observations import CodeObservationRepository
from tests.fixtures.action_preparation import build_preparation_harness


@pytest.mark.parametrize("status", ["AVAILABLE", "NOT_A_REPOSITORY", "UNBORN", "UNAVAILABLE"])
def test_capture_git_states_and_expected_content(monkeypatch, status):
    understanding = SimpleNamespace(get=Mock(return_value=SimpleNamespace(revision=1, source_root="source", source_analysis_authorized=True)),
        inspect_source_fingerprint=Mock(return_value="a" * 64))
    monkeypatch.setattr("product.backend.workflows.changes.observations.inspect_git_source",
        Mock(return_value=GitSourceContext(status=status, head="b" * 40 if status == "AVAILABLE" else None)))
    service = CodeObservationService(understanding)
    value = service.capture("project", "a" * 64)
    assert value["git_status"] == status
    assert value["consistency"] == ("UNAVAILABLE" if status == "UNAVAILABLE" else "CONSISTENT")
    understanding.inspect_source_fingerprint.side_effect = ["a" * 64, "c" * 64]
    changed = service.capture("project", "a" * 64)
    assert changed["source_fingerprint"] == "a" * 64 and changed["head"] is None
    assert changed["consistency"] == "UNAVAILABLE"


def test_unauthorized_capture_does_not_call_git(monkeypatch):
    understanding = SimpleNamespace(get=Mock(return_value=SimpleNamespace(source_analysis_authorized=False)))
    git = Mock(side_effect=AssertionError("must not call"))
    monkeypatch.setattr("product.backend.workflows.changes.observations.inspect_git_source", git)
    assert CodeObservationService(understanding).capture("project", "a" * 64)["git_status"] == "UNAVAILABLE"
    git.assert_not_called()


def test_head_changes_after_content_read_does_not_save_mixed_identity(monkeypatch):
    understanding = SimpleNamespace(get=Mock(return_value=SimpleNamespace(revision=1, source_root="source", source_analysis_authorized=True)),
        inspect_source_fingerprint=Mock(return_value="a" * 64))
    monkeypatch.setattr("product.backend.workflows.changes.observations.inspect_git_source", Mock(side_effect=[
        GitSourceContext(status="AVAILABLE", head="b" * 40), GitSourceContext(status="AVAILABLE", head="c" * 40)]))
    value = CodeObservationService(understanding).capture("project", "a" * 64)
    assert value["consistency"] == "UNAVAILABLE" and value["head"] is None
    assert value["source_fingerprint"] == "a" * 64


def test_change_observation_is_exact_and_transactional(tmp_path, monkeypatch):
    harness = build_preparation_harness(tmp_path)
    core, project = harness.core, harness.project_id
    monkeypatch.setattr("product.backend.workflows.changes.observations.inspect_git_source", lambda root: GitSourceContext(status="AVAILABLE", head="a" * 40))
    try:
        first = core.source_changes.submit(project, reason="只登记源码")
        with core.uow_factory() as work:
            observed = work.code_observations.for_target(project, "change", first.manifest.change_id)
        assert observed["head"] == "a" * 40
        original = CodeObservationRepository.add_link
        def failed(self, *args, **kwargs):
            original(self, *args, **kwargs)
            raise RuntimeError("injected metadata failure")
        monkeypatch.setattr(CodeObservationRepository, "add_link", failed)
        with pytest.raises(RuntimeError):
            core.source_changes.submit(project, reason="登记回滚")
        with core.uow_factory() as work:
            assert len(work.source_changes.current_changes(project)) == 1
            assert work.code_observations.for_target(project, "change", first.manifest.change_id) == observed
    finally:
        harness.close()
