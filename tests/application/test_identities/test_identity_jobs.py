# 验证跨控制面回读、同键恢复以及取消与登录提交的事务先后。
# 使用真实数据库和内存凭据，直接驱动结果采用；本组不证明实际浏览器采集或系统凭据写入。
from functools import partial
from types import SimpleNamespace
import time

import pytest

from tests.support.builders.identities import build_identity_service, boundary_reader, PROJECT_ID, ACTOR_ID
from product.backend.application.test_identities.preparation import IdentityPreparationManager
from product.backend.application.test_identities.service import PreparedLoginState
from product.backend.domain.errors import JiejianError
from product.backend.domain.identities.models import TestIdentityAuthMethod as AuthMethod, TestIdentityCookie as Cookie
from product.backend.domain.lifecycle import JobState
from product.backend.application.test_identities.login_execution import IdentityPreparationHandler
from product.backend.infrastructure.runtime.jobs.attempts import JobAttempts
from product.backend.infrastructure.runtime.jobs.queue import JobQueue
from product.backend.infrastructure.runtime.jobs.models import ClaimJob, WaitingFatalFailure
from product.backend.application.workspace.progress import ApplicationProgress
from product.backend.infrastructure.runtime.jobs.registration import current_check_and_recording_targets
from product.backend.infrastructure.storage import StorageUnitOfWork
from product.backend.infrastructure.secrets.refs import credential_ref


@pytest.fixture
def login(tmp_path):
    identities, secrets, sessions = build_identity_service(tmp_path)
    work = partial(StorageUnitOfWork, sessions)
    targets = current_check_and_recording_targets()
    queue, attempts = JobQueue(work, targets=targets), JobAttempts(work, targets=targets)
    def understanding(project):
        with work() as unit:
            return unit.application_understanding.get(project)
    def manager():
        return IdentityPreparationManager(tmp_path / 'var', identities, secrets, {},
            application_understanding=SimpleNamespace(get=understanding), business_boundaries=boundary_reader(sessions),
            uow_factory=work, job_queue=queue)
    identity = identities.create(PROJECT_ID, actor_id=ACTOR_ID, actor_revision=1, label='所有者账号')
    return SimpleNamespace(manager=manager, identities=identities, secrets=secrets, work=work,
        attempts=attempts, identity=identity, var=tmp_path / 'var')


def test_two_control_faces_and_two_request_keys_share_one_login(login):
    first = login.manager().start(login.identity.identity_id, operation_id='a' * 32)
    second = login.manager()
    assert second.latest(login.identity.identity_id) == first
    assert second.start(login.identity.identity_id, operation_id='a' * 32) == first
    assert second.start(login.identity.identity_id, operation_id='b' * 32) == first
    with login.work() as unit:
        assert len(unit.jobs.list_for_project(PROJECT_ID)) == 1
    with pytest.raises(JiejianError, match='取消当前登录'):
        login.identities.reset(login.identity.identity_id)


@pytest.mark.parametrize('cancel_first', [True, False])
def test_save_and_cancel_use_one_transaction_order(login, cancel_first):
    # 人工排列两个竞争写操作，保护“取消先到则不能保存，保存先到则不能回滚成功”的契约。
    manager = login.manager()
    started = manager.start(login.identity.identity_id)
    import time
    now = time.time_ns() // 1000
    claimed = login.attempts.claim(ClaimJob(job_id=started.job_id, lease_owner='login-test', now_us=now,
        lease_duration_us=30_000_000))
    with login.work() as unit:
        row = unit.identity_preparations.get(started.preparation_id)
    ref = credential_ref('test-identity', PROJECT_ID, login.identity.identity_id, 'cookie-00')
    login.secrets.write(ref, 'ephemeral-test-value')
    prepared = PreparedLoginState(auth_method=AuthMethod.COOKIE_SESSION,
        cookies=(Cookie(name='session', domain='127.0.0.1', path='/', secure=False,
            http_only=True, same_site='LAX', value_secret_ref=ref),), prepared_at_us=now)
    handler = IdentityPreparationHandler(login.var, lease_owner='login-test', uow_factory=login.work,
        attempts=login.attempts, environ={}, secret_store=login.secrets)
    if cancel_first:
        manager.cancel(started.preparation_id)
        with pytest.raises(JiejianError):
            handler._finish(claimed.job, row, phase='PREPARED', prepared=prepared)
        assert login.identities.get_record(login.identity.identity_id).auth_method is None
    else:
        handler._finish(claimed.job, row, phase='PREPARED', prepared=prepared)
        assert manager.cancel(started.preparation_id).status.value == 'PREPARED'
        with login.work() as unit:
            assert unit.jobs.get(started.job_id).state is JobState.SUCCEEDED
            assert unit.identity_preparations.get(started.preparation_id)['phase'] == 'PREPARED'
        assert login.identities.get_record(login.identity.identity_id).auth_method is not None
        login.identities.reset(login.identity.identity_id)
        assert login.secrets.read(ref) is None


def test_cancel_before_worker_claim_is_terminal_and_next_round_is_explicit(login):
    manager = login.manager()
    first = manager.start(login.identity.identity_id, operation_id='c' * 32)
    assert manager.cancel(first.preparation_id).status.value == 'CANCELLED'
    assert manager.start(login.identity.identity_id, operation_id='c' * 32).preparation_id == first.preparation_id
    assert manager.start(login.identity.identity_id, operation_id='d' * 32).preparation_id != first.preparation_id


def test_failed_login_remains_discoverable_until_an_explicit_new_round(login):
    manager = login.manager()
    first = manager.start(login.identity.identity_id)
    login.attempts.record_waiting_fatal_failure(WaitingFatalFailure(job_id=first.job_id, now_us=time.time_ns() // 1000))
    progress = ApplicationProgress(login.work, manager)
    item, = progress.activity(PROJECT_ID)['items']
    assert item['phase'] == 'FAILED'
    assert item['destination'].endswith('preparation_id=' + first.preparation_id)
    assert manager.status(first.preparation_id).status.value == 'FAILED'

    second = manager.start(login.identity.identity_id)
    item, = progress.activity(PROJECT_ID)['items']
    assert item['id'] == second.job_id
    assert first.preparation_id not in item['destination']
    manager.cancel(second.preparation_id)
    assert progress.activity(PROJECT_ID)['items'] == []
