from copy import deepcopy
from uuid import uuid4

import pytest

from product.backend.domain.errors import ErrorCode, JiejianError
from tests.support.builders.preparation.action_preparation import build_preparation_harness


@pytest.mark.parametrize('internal', [False, True])
def test_step_failure_preserves_receipt_context_and_distinguishes_internal_fault(tmp_path, monkeypatch, caplog, internal):
    harness = build_preparation_harness(tmp_path)
    service = harness.core.preparation_batches
    operation = uuid4().hex
    pending = dict(kind='START_PREFLIGHT', command=dict(operation_id=uuid4().hex))
    value = dict(operation_id=operation, project_id=harness.project_id, plan_hash='a'*64,
        control_session_id=harness.core.proof_preparation.control_session_id, state='RUNNING',
        cancel_requested=False, created_at_us=1, updated_at_us=1,
        payload=dict(schema_version='2', plan=dict(sources=[dict(source_id='fixture')]), stage='NEXT',
            items=[dict(label='业务结果', state='WAITING', pending=deepcopy(pending))],
            recipe={}, message='正在准备', index=0))
    try:
        with harness.core.uow_factory() as work:
            work.preparation_batches.save(value)
            work.commit()

        def fail(_value):
            if internal:
                raise RuntimeError('opaque-sensitive-fixture')
            raise JiejianError(ErrorCode.STATE_PRECONDITION, '读取授权已撤回')

        monkeypatch.setattr(service, '_step', fail)
        service.advance()
        public = service.show(harness.project_id, operation)
        with harness.core.uow_factory() as work:
            saved = work.preparation_batches.get(harness.project_id, operation)
        assert public['state'] == 'BLOCKED'
        assert saved['payload']['items'][0]['pending'] == pending
        if internal:
            assert public['error_code'] == 'PREPARATION_INTERNAL_ERROR'
            assert '内部错误' in public['message']
            error = saved['payload']['error']
            assert error['exception_type'] == 'RuntimeError'
            assert error['frames'][-1]['function'] == 'fail'
            assert 'opaque-sensitive-fixture' not in str(saved) + caplog.text
            assert 'PREPARATION_INTERNAL_ERROR' in caplog.text
        else:
            assert public['error_code'] == 'STATE_PRECONDITION'
            assert public['message'] == '读取授权已撤回'
            assert 'exception_type' not in saved['payload']['error']

        # 失败后的轮询不能重放未知写入；原回执与待处理步骤仍供显式恢复核对。
        monkeypatch.setattr(service, '_step', lambda _value: pytest.fail('replayed a failed step'))
        service.advance()
        assert service.show(harness.project_id, operation) == public
    finally:
        harness.close()


pytestmark = [pytest.mark.level3]


def test_restart_honors_persisted_cancellation_without_authorizing_more_preparation(tmp_path):
    harness = build_preparation_harness(tmp_path)
    service = harness.core.preparation_batches
    operation = uuid4().hex
    value = dict(operation_id=operation, project_id=harness.project_id, plan_hash='a'*64,
        control_session_id='previous-control-session', state='CANCELLING', cancel_requested=True,
        created_at_us=1, updated_at_us=1,
        payload=dict(schema_version='2', plan=dict(sources=[]), stage='NEXT', items=[], recipe={}, message='正在取消'))
    try:
        with harness.core.uow_factory() as work:
            work.preparation_batches.save(value)
            jobs_before = work.jobs.list_for_project(harness.project_id)
            work.commit()
        service.advance()
        assert service.show(harness.project_id, operation)['state'] == 'CANCELLED'
        with harness.core.uow_factory() as work:
            assert work.jobs.list_for_project(harness.project_id) == jobs_before
    finally:
        harness.close()
