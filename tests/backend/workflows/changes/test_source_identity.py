# 验证只读源码身份对照、授权与历史隔离；不触达目标应用或执行检查。
from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from product.backend.core.errors import JiejianError, ErrorCode
from product.backend.infra.source_identity import GitSourceContext
from product.backend.workflows.changes.identity import SourceIdentityReader
from product.backend.api.routers.source_changes import build_source_changes_router


@pytest.fixture
def identity(monkeypatch):
    record = SimpleNamespace(snapshot_id="snp_" + "a" * 32, source_fingerprint="a" * 64, project_id="p1", files=("one", "two"))
    repository = SimpleNamespace(snapshot=Mock(return_value=record), snapshot_for_fingerprint=Mock(return_value=record))
    work = SimpleNamespace(source_changes=repository, code_observations=SimpleNamespace(for_target=Mock(return_value=None)))
    understanding = SimpleNamespace(get=Mock(return_value=SimpleNamespace(revision=1, source_root="authorized", source_analysis_authorized=True)),
                                    inspect_source_fingerprint=Mock(return_value="a" * 64))
    changes = SimpleNamespace(get=Mock(return_value=(None, SimpleNamespace(current_snapshot_id="saved"), None)))
    results = SimpleNamespace(package=Mock(return_value=SimpleNamespace(request=SimpleNamespace(source_fingerprint="a" * 64))))
    git = Mock(return_value=GitSourceContext(status="AVAILABLE", head="f" * 40, has_local_changes=True))
    monkeypatch.setattr("product.backend.workflows.changes.identity.inspect_git_source", git)
    reader = SourceIdentityReader(uow_factory=lambda: nullcontext(work), understanding=understanding, changes=changes, results=results)
    return SimpleNamespace(reader=reader, repository=repository, understanding=understanding, changes=changes, results=results, git=git)


def test_content_is_authority_even_with_dirty_git_and_missing_historical_git(identity):
    first = identity.reader.for_run("p1", "run1")
    assert first.comparison == "SAME"
    assert first.recorded.git_status == "NOT_RECORDED"
    assert first.recorded.file_count == 2
    assert first.target_version == "NOT_INDEPENDENTLY_IDENTIFIED"
    identity.understanding.inspect_source_fingerprint.return_value = "b" * 64
    second = identity.reader.for_run("p1", "run1")
    assert second.comparison == "CHANGED"
    assert second.recorded == first.recorded
    assert second.current_git.head == first.current_git.head
    identity.results.package.assert_called_with("run1", project_id="p1")


def test_recorded_git_comes_only_from_exact_run_association(identity):
    with identity.reader._uow_factory() as work:
        work.code_observations.for_target.return_value = dict(project_id="p1", source_fingerprint="a" * 64,
            git_status="AVAILABLE", head="e" * 40, has_local_changes=False, observed_at_us=1,
            observation_id="obs_" + "d" * 32, consistency="CONSISTENT")
        result = identity.reader.for_run("p1", "run1")
        work.code_observations.for_target.assert_called_once_with("p1", "run", "run1")
    assert result.recorded.head == "e" * 40
    assert result.current_git.head == "f" * 40


def test_change_uses_exact_snapshot_not_latest_understanding(identity):
    value = identity.reader.for_change("p1", "change1")
    assert value.change_id == "change1" and value.run_id is None
    identity.changes.get.assert_called_once_with("p1", "change1")
    identity.repository.snapshot.assert_called_once_with("saved")


def test_missing_baseline_does_not_invent_content_difference(identity):
    identity.repository.snapshot.return_value = None
    value = identity.reader.for_change("p1", "change1")
    assert value.comparison == "NO_BASELINE" and value.recorded is None


def test_frozen_run_fingerprint_remains_available_without_file_index(identity):
    identity.repository.snapshot_for_fingerprint.return_value = None
    value = identity.reader.for_run("p1", "run1")
    assert value.recorded.fingerprint == "a" * 64
    assert value.recorded.file_count is None
    assert value.recorded.snapshot_id is None


def test_unauthorized_source_never_reads_git(identity):
    identity.understanding.get.return_value.source_analysis_authorized = False
    value = identity.reader.for_run("p1", "run1")
    assert value.comparison == "UNAVAILABLE" and value.current_fingerprint is None
    identity.git.assert_not_called()
    identity.understanding.inspect_source_fingerprint.assert_not_called()


def test_concurrent_source_edit_clears_partial_current_context(identity):
    identity.understanding.inspect_source_fingerprint.side_effect = ["a" * 64, "b" * 64]
    value = identity.reader.for_run("p1", "run1")
    assert value.comparison == "UNAVAILABLE"
    assert value.current_fingerprint is None and value.current_git.head is None


def test_cross_project_or_unpublished_package_cannot_be_read(identity):
    identity.results.package.side_effect = JiejianError(ErrorCode.RECORD_NOT_FOUND, "记录不存在")
    with pytest.raises(JiejianError):
        identity.reader.for_run("other", "run1")
    identity.git.assert_not_called()


def test_git_failure_does_not_erase_valid_content_comparison(identity):
    identity.git.return_value = GitSourceContext(status="UNAVAILABLE")
    assert identity.reader.for_run("p1", "run1").comparison == "SAME"


def test_gui_routes_keep_project_and_record_identity(identity):
    app = FastAPI()
    app.include_router(build_source_changes_router(SimpleNamespace(source_identity=identity.reader)))
    with TestClient(app) as client:
        run = client.get("/api/projects/p1/runs/run1/source-identity")
        change = client.get("/api/projects/p1/source-changes/change1/source-identity")
    assert run.status_code == change.status_code == 200
    assert run.json()["data"]["run_id"] == "run1"
    assert change.json()["data"]["change_id"] == "change1"
    assert "authorized" not in run.text


def test_production_router_requires_local_control_session(tmp_path, identity):
    from tests.fixtures.control_plane import create_app, TEST_CONTROL_SESSION_TOKEN, TEST_CONTROL_ORIGIN
    from product.backend.api.local_control import LocalControlGuard
    app = create_app(tmp_path / "var", start_worker=False)
    app.state.context.source_identity = identity.reader
    path = "/api/projects/p1/runs/run1/source-identity"
    with TestClient(app, base_url=TEST_CONTROL_ORIGIN) as anonymous:
        assert anonymous.get(path).status_code == 403
        anonymous.cookies.set(LocalControlGuard.cookie_name, TEST_CONTROL_SESSION_TOKEN)
        assert anonymous.get(path).json()["data"]["recorded"]["git_status"] == "NOT_RECORDED"
    identity.results.package.assert_called_once_with("run1", project_id="p1")
