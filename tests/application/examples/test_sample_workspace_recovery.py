# 验证停止、重开控制面、再次运行与重置的项目身份和源码保留边界。
from pathlib import Path
import pytest
from product.backend.bootstrap.application import ApplicationCore
from product.backend.domain.lifecycle import ProjectStatus
from tests.support.secrets import MemorySecrets as InMemorySecretStore
from tests.support.builders.runtime.runtime_environment import runtime_identity_environment


@pytest.mark.process
@pytest.mark.slow
def test_stop_restart_creates_clean_project_and_archives_history(tmp_path):
    root = Path(__file__).resolve().parents[3]
    var_dir = tmp_path / "var"
    def create():
        return ApplicationCore(var_dir, official_sample_root=root / "samples/web/digital_gallery",
            secret_store=InMemorySecretStore(), environ=runtime_identity_environment(var_dir))
    core = create()
    try:
        first = core.official_experience.start(consent=True)
        with core.uow_factory() as work:
            receipt = work.environment_operations.get(first.operation_id)
            work.environment_operations.save({**receipt, "state": "UNKNOWN"})
            work.commit()
        status = core.official_experience.status()
        assert status.lifecycle == "RUNNING" and status.operation_state == "UNKNOWN"
        owned = core.official_experience.reconcile()
        assert owned.lifecycle == "RUNNING" and owned.recovery_state == "OWNED_RUNNING"
        assert owned.operation_state == "SUCCEEDED"
        source = Path(core.application_understanding.get(core.official_experience.status().project_id).source_root)
        marker = source / "user_note.txt"
        marker.write_text("retained source", encoding="utf-8")
        assert core.official_experience.start(consent=True).experience_id == first.experience_id
        stopped = core.official_experience.stop()
        assert stopped.lifecycle == "STOPPED" and stopped.workspace_retained
        assert stopped.recovery_state == "EXITED"
        assert source.is_dir() and marker.is_file()
        assert core.projects.get(first.project_id).status is not ProjectStatus.ARCHIVED
        history = core.official_experience.history()
        core.close(); core.engine.dispose()
        core = create()
        assert core.official_experience.status().recovery_state == "EXITED"
        assert core.official_experience.history() == history
        second = core.official_experience.start(consent=True)
        assert second.project_id != first.project_id
        assert second.experience_id != first.experience_id
        assert Path(core.application_understanding.get(core.official_experience.status().project_id).source_root) != source
        assert not (Path(core.application_understanding.get(core.official_experience.status().project_id).source_root) / "user_note.txt").exists()
        assert core.projects.get(first.project_id).status is ProjectStatus.ARCHIVED
        assert marker.read_text(encoding="utf-8") == "retained source"
        assert not second.scenario_prepared and second.scenario_version.value == "BASELINE"
        # 通用运行实例被单独停止后，官方入口只能确认退出并建立新项目。
        reference = core.node_runtime.reference(second.project_id)
        core.node_runtime.stop(second.project_id, instance_id=reference.instance_id)
        assert core.official_experience.reconcile().recovery_state == "EXITED"
        resumed = core.official_experience.start(consent=True)
        assert resumed.project_id != second.project_id and resumed.experience_id != second.experience_id
        assert core.projects.get(second.project_id).status is ProjectStatus.ARCHIVED
        third = core.official_experience.reset(consent=True)
        assert third.project_id != resumed.project_id
        assert core.projects.get(resumed.project_id).status is ProjectStatus.ARCHIVED
        assert core.projects.get(first.project_id).status is ProjectStatus.ARCHIVED
        assert source.is_dir()
    finally:
        core.close(); core.official_samples.stop(); core.engine.dispose()


def test_unknown_foreign_identity_never_becomes_exited(tmp_path, monkeypatch):
    from product.backend.application.examples.recovery import SampleRecovery
    from types import SimpleNamespace
    recovery = SampleRecovery(None, None, lambda: 1)
    monkeypatch.setattr(recovery, "read", lambda: ({}, {"instance_id": "exp_" + "a" * 32,
        "kernel_identity": {"kind": "windows-job", "name": "foreign-job"}}, None, None))
    observed = []
    class Work:
        sample_workspaces = SimpleNamespace(observe=observed.append)
        def __enter__(self): return self
        def __exit__(self, *args): return None
        def commit(self): pass
    recovery._factory = Work
    def forbidden(identity): raise AssertionError("foreign identity must not be probed")
    monkeypatch.setattr("product.backend.application.examples.recovery.kernel_tree_has_exited", forbidden)
    assert recovery.reconcile() == "OWNERSHIP_UNCONFIRMED"
    assert observed[0]["outcome"] == "OWNERSHIP_UNCONFIRMED"


@pytest.mark.process
@pytest.mark.slow
def test_restarted_sample_requires_fresh_approval_and_materials(tmp_path):
    from tests.support.builders.runtime.official_preparation import prepare_sample
    root = Path(__file__).resolve().parents[3]
    var_dir = tmp_path / "var"
    core = ApplicationCore(var_dir, official_sample_root=root / "samples/web/digital_gallery",
        secret_store=InMemorySecretStore(), environ=runtime_identity_environment(var_dir))
    try:
        project = prepare_sample(core)
        with core.uow_factory() as work:
            old_recordings = {item.recording_id for item in work.recordings.list_for_project(project)}
        core.official_experience.stop()
        restarted = core.official_experience.start(consent=True)
        new_project = restarted.project_id
        assert new_project != project
        assert core.projects.get(project).status is ProjectStatus.ARCHIVED
        assert not core.preparation.get(new_project).preparation_complete
        with core.uow_factory() as work:
            assert not work.test_identities.list_for_project(new_project)
            assert not work.recordings.list_for_project(new_project)
        from product.backend.domain.errors import JiejianError
        import pytest
        with pytest.raises(JiejianError):
            core.official_experience.prepare()
        assert prepare_sample(core) == new_project
        with core.uow_factory() as work:
            new_recordings = {item.recording_id for item in work.recordings.list_for_project(new_project)}
            assert old_recordings == {item.recording_id for item in work.recordings.list_for_project(project)}
            assert old_recordings.isdisjoint(new_recordings) and len(new_recordings) == 4
        assert core.official_experience.prepare().scenario_prepared
    finally:
        core.close(); core.official_samples.stop(); core.engine.dispose()


def test_same_endpoint_does_not_make_two_controlled_instances_equivalent():
    from types import SimpleNamespace
    from product.backend.domain.boundaries.entities import boundary_sha256
    from product.backend.application.recording.source import recording_endpoint_fingerprint
    value = SimpleNamespace(confirmed_endpoint="http://127.0.0.1:8888", endpoint_source_fingerprint="a" * 64)
    original = boundary_sha256({"confirmed_endpoint": value.confirmed_endpoint, "endpoint_source_fingerprint": value.endpoint_source_fingerprint})
    assert recording_endpoint_fingerprint(value) == original
    first = recording_endpoint_fingerprint(value, controlled_instance_id="exp_" + "a" * 32)
    second = recording_endpoint_fingerprint(value, controlled_instance_id="exp_" + "b" * 32)
    assert len({first, second, original}) == 3

pytestmark = [pytest.mark.level4]
