# 快速发现当前合同与夹具过期，避免等到 Worker 或数据库整链结束才发现。
import pytest


from product.backend.infrastructure.storage.execution.jobs import JobRecord
from tests.support.contracts import JOB_TARGET_FIELDS, WORKER_CAPABILITIES
from tests.support.builders.migration_history import migration_head, migration_history

def test_runtime_uses_the_actual_upgrade_graph():
    from product.backend.migrations.runtime import MigrationHistory, migration_resources
    scripts = migration_history()
    with migration_resources() as root:
        history = MigrationHistory.load(root)
    assert history.head == migration_head()
    assert history.revisions == {item.revision for item in scripts.walk_revisions()}


@pytest.mark.parametrize('branched', [False, True])
def test_history_discovers_new_revisions_and_rejects_ambiguous_endpoints(tmp_path, branched):
    from product.backend.migrations.runtime import MigrationHistory
    versions = tmp_path / 'migrations' / 'versions'
    versions.mkdir(parents=True)
    (tmp_path / 'alembic.ini').write_text('[alembic]\nscript_location = %(here)s/migrations\n', encoding='utf-8')
    revisions = [('initial', None), ('feature', 'initial')]
    if branched:
        revisions.append(('other_feature', 'initial'))
    for revision, parent in revisions:
        (versions / f'{revision}.py').write_text(f'revision = {revision!r}\ndown_revision = {parent!r}\n', encoding='utf-8')
    if branched:
        with pytest.raises(ValueError):
            MigrationHistory.load(tmp_path)
    else:
        history = MigrationHistory.load(tmp_path)
        assert history.head == 'feature'
        assert history.revisions == {'initial', 'feature'}


def test_job_fixture_contract_contains_every_target():
    assert JOB_TARGET_FIELDS <= set(JobRecord.model_fields)


def test_current_worker_registry_is_explicit():
    from product.backend.infrastructure.runtime.jobs.registration import current_check_and_recording_targets
    targets = current_check_and_recording_targets().target_types
    assert tuple(sorted('CHECK' if item.value == 'RUN' else item.value for item in targets)) == WORKER_CAPABILITIES

pytestmark=[pytest.mark.level1]
