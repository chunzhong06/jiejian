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


@pytest.mark.parametrize('cancel', [False, True])
def test_queue_rejection_waits_without_unknown_write_or_busy_wake(tmp_path, monkeypatch, cancel):
    harness = build_preparation_harness(tmp_path)
    service = harness.core.preparation_batches
    operation = uuid4().hex
    value = dict(operation_id=operation, project_id=harness.project_id, plan_hash='a'*64,
        control_session_id=service._proofs.control_session_id, state='RUNNING', cancel_requested=False,
        created_at_us=1, updated_at_us=1, payload=dict(schema_version='2', stage='NEXT',
            plan=dict(sources=[{}]), items=[dict(label='结果',state='WAITING',pending=None)], message='开始'))
    rejected = True
    calls = []
    def submit(project, command):
        calls.append(command.operation_id)
        if rejected:raise JiejianError(ErrorCode.JOB_QUEUE_FULL,'容量已满')
        return dict(project_id=project,operation_id=command.operation_id,operation_kind='START_PREFLIGHT',
            result=dict(preflight_id='ppf_'+uuid4().hex))
    def step(current):
        if current['cancel_requested']:
            return service._finish(current,'CANCELLED','已取消')
        if current['payload']['items'][0]['state']=='CHECKING':return
        service._write(current,0,'START_PREFLIGHT',dict(source_id='psr_'+'1'*32,revision=1,basis_id='pb_'+'a'*64))
    try:
        with service._uow() as work:
            work.preparation_batches.save(value);work.commit()
        monkeypatch.setattr(service._proofs,'start',submit)
        monkeypatch.setattr(service,'_step',step)
        service.advance()
        with service._uow() as work:saved=work.preparation_batches.get(harness.project_id,operation)
        assert saved['state']=='RUNNING' and saved['payload']['items'][0]['pending'] is None
        assert not service.wake.is_set() and len(calls)==1
        if cancel:
            service.cancel(harness.project_id,operation);service.advance()
            assert service.show(harness.project_id,operation)['state']=='CANCELLED'
            assert len(calls)==1
        else:
            rejected=False;service.advance()
            with service._uow() as work:saved=work.preparation_batches.get(harness.project_id,operation)
            assert saved['payload']['items'][0]['state']=='CHECKING'
            assert saved['payload']['items'][0]['pending'] is None
            assert calls[0]==calls[1]
    finally:harness.close()


@pytest.mark.parametrize('error,accepted', [('JOB_QUEUE_FULL',False),('STATE_PRECONDITION',False),('JOB_QUEUE_FULL',True)])
def test_legacy_rejected_batch_requires_absence_of_job_and_receipt(tmp_path, monkeypatch, error, accepted):
    from product.backend.application.preparation.batches import BatchSource, PreparationBatchPlan, StartPreparationBatch
    harness=build_preparation_harness(tmp_path)
    service=harness.core.preparation_batches
    plan=PreparationBatchPlan(project_id=harness.project_id,mode='REVIEWED',basis_id='pb_'+'a'*64,
        runtime_origin='http://127.0.0.1:8765',guard='a'*64,
        sources=(BatchSource(source_id='psr_'+'1'*32,revision=1,config_hash='a'*64,label='结果'),))
    previous=dict(operation_id=uuid4().hex,project_id=harness.project_id,plan_hash='a'*64,
        control_session_id=service._proofs.control_session_id,state='BLOCKED',cancel_requested=False,
        created_at_us=1,updated_at_us=1,payload=dict(schema_version='2',plan=plan.model_dump(mode='json'),
            stage='NEXT',message='旧记录',error=dict(code=error),items=[dict(state='WAITING',label='结果',
            pending=dict(kind='START_PREFLIGHT',command=dict(operation_id=uuid4().hex)))]))
    try:
        with service._uow() as work:
            work.preparation_batches.save(previous);work.commit()
            job_repo=type(work.jobs)
        if accepted:monkeypatch.setattr(job_repo,'get_by_idempotency',lambda *_: object())
        monkeypatch.setattr(service,'preview',lambda *_:plan)
        command=StartPreparationBatch(operation_id=uuid4().hex,plan=plan,confirmed=True)
        if error=='JOB_QUEUE_FULL' and not accepted:
            assert service.start(harness.project_id,command)['state']=='RUNNING'
            with service._uow() as work:
                assert work.preparation_batches.get(harness.project_id,previous['operation_id'])['payload']['items'][0]['pending'] is None
        else:
            with pytest.raises(JiejianError,match='回执仍不明确'):service.start(harness.project_id,command)
    finally:harness.close()
