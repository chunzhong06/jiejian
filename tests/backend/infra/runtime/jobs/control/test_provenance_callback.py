# 验证 Run 首次创建附带回调共享事务且不在幂等重放时执行；不启动 Worker。
from uuid import uuid4
import pytest
from product.backend.core.errors import JiejianError
from product.backend.infra.storage import StorageUnitOfWork


def test_created_metadata_is_atomic_and_replay_preserves_first(worker_services):
    calls = []
    def metadata(work, run):
        calls.append(run.run_id)
        work.code_observations.add_link(dict(observation_id="obs_" + uuid4().hex, project_id=run.project_id,
            source_fingerprint=run.source_fingerprint, observed_at_us=1, git_status="UNAVAILABLE", head=None,
            has_local_changes=None, consistency="UNAVAILABLE", scope="AUTHORIZED_SOURCE_SCAN"),
            kind="run", target_id=run.run_id, project_id=run.project_id, source_fingerprint=run.source_fingerprint)
    first = worker_services.queue.submit(worker_services.submit_request(), on_created=metadata)
    repeated = worker_services.queue.submit(worker_services.submit_request(), on_created=metadata)
    assert len(calls) == 1 and repeated.run == first.run
    with StorageUnitOfWork(worker_services.session_factory) as work:
        assert work.code_observations.for_target(first.run.project_id, "run", first.run.run_id) is not None


def test_callback_failure_rolls_back_run_job_and_metadata(worker_services):
    def failed(work, run):
        raise RuntimeError("metadata failure")
    with pytest.raises(RuntimeError):
        worker_services.queue.submit(worker_services.submit_request(), on_created=failed)
    with StorageUnitOfWork(worker_services.session_factory) as work:
        assert work.runs.list_for_project("job-runtime-project") == ()
        assert work.jobs.list_for_project("job-runtime-project") == ()


def test_observation_target_project_and_fingerprint_are_rechecked(worker_services):
    first = worker_services.queue.submit(worker_services.submit_request())
    for project, fingerprint in (("other-project", first.run.source_fingerprint), (first.run.project_id, "e" * 64)):
        with pytest.raises(JiejianError):
            with StorageUnitOfWork(worker_services.session_factory) as work:
                work.code_observations.add_link(dict(observation_id="obs_" + uuid4().hex, project_id=project,
                    source_fingerprint=fingerprint, observed_at_us=1, git_status="UNAVAILABLE", head=None,
                    has_local_changes=None, consistency="UNAVAILABLE", scope="AUTHORIZED_SOURCE_SCAN"),
                    kind="run", target_id=first.run.run_id, project_id=project, source_fingerprint=fingerprint)
                work.commit()
    with StorageUnitOfWork(worker_services.session_factory) as work:
        assert work.code_observations.for_target(first.run.project_id, "run", first.run.run_id) is None
