# 核对规则索引与原发布事务、有界整理回执及坏包隔离；索引不会产生第二份安全结论。
from uuid import uuid4
import pytest
from sqlalchemy import text
from product.backend.domain.errors import JiejianError
from product.backend.infrastructure.artifacts.checks.check_publication import CheckPublisher
from product.backend.infrastructure.artifacts.checks.check_packages import check_final_directory
from product.backend.infrastructure.storage.results.rule_history import RuleHistoryRepository
from product.backend.application.checks.history import CheckHistoryService, MaintainHistory
from product.backend.application.checks.reading.results import CheckResultReader
from tests.support.builders.checks.check_publication import package_parts, NOW


def services(parts):
    var,factory,job,staging,_=parts
    publisher=CheckPublisher(var,factory,clock_us=lambda:NOW+20)
    package=publisher.publish(staging);reader=CheckResultReader(var_dir=var,uow_factory=factory)
    return package,reader,CheckHistoryService(reader,factory),publisher


def test_rule_index_shares_publication_transaction_and_can_recover(package_parts,monkeypatch):
    var,factory,job,staging,_=package_parts;publisher=CheckPublisher(var,factory,clock_us=lambda:NOW+20)
    original=RuleHistoryRepository.index
    def fail(*args,**kwargs):raise RuntimeError('injected index failure')
    monkeypatch.setattr(RuleHistoryRepository,'index',fail)
    with pytest.raises(RuntimeError):publisher.publish(staging)
    with factory() as work:
        assert work.jobs.get(job.job_id).state.value=='RUNNING'
        assert work.check_publications.get(job.run_id) is None
    monkeypatch.setattr(RuleHistoryRepository,'index',original)
    assert not check_final_directory(var,job.project_id,job.run_id).exists()
    package=publisher.publish(staging)
    publisher.complete_existing(check_final_directory(var,job.project_id,job.run_id))
    reader=CheckResultReader(var_dir=var,uow_factory=factory)
    for action in package.request.actions:
        for case in action.cases:
            rule=case.permission
            page=reader.history(job.project_id,rule_reference=(rule.intent_id,rule.revision,rule.intent_hash))
            assert len(page.items)==1 and case.case_id in page.items[0].matching_cases
            assert page.items[0].status.result_integrity=='VALID'
    with factory() as work:
        assert work._session.execute(text('SELECT count(*) FROM rule_check_index')).scalar_one()==sum(len(action.cases) for action in package.request.actions)


def test_missing_index_maintenance_receipt_and_corrupt_package(package_parts,monkeypatch):
    package,reader,service,_=services(package_parts);_,factory,job,_,_=package_parts
    with factory() as work:
        work._session.execute(text('DELETE FROM rule_check_index'));work.commit()
    assert service.status(job.project_id)['status']=='NEEDS_SCAN'
    def forbidden(*args,**kwargs):raise AssertionError('history does not evaluate')
    monkeypatch.setattr('product.backend.domain.verification.checks.evaluate_check_case',forbidden)
    command=MaintainHistory(operation_id=uuid4().hex,expected_checkpoint=0,limit=1)
    answer=service.maintain(job.project_id,command)
    assert answer['complete'] and answer['processed']==1
    assert service.maintain(job.project_id,command)==answer
    assert service.receipt(job.project_id,command.operation_id)['receipt']==answer
    with pytest.raises(JiejianError):service.maintain(job.project_id,command.model_copy(update={'limit':2}))
    with pytest.raises(JiejianError):service.maintain(job.project_id,MaintainHistory(operation_id=uuid4().hex,expected_checkpoint=0))
    original=(package.directory/'result.json').read_bytes();(package.directory/'result.json').write_bytes(b'{}')
    damaged=service.maintain(job.project_id,MaintainHistory(operation_id=uuid4().hex,expected_checkpoint=1))
    assert damaged['failed']==1 and service.status(job.project_id)['status']=='INCOMPLETE'
    assert reader.history(job.project_id).items[0].status.run.verdict is None
    (package.directory/'result.json').write_bytes(original)
    repaired=service.maintain(job.project_id,MaintainHistory(operation_id=uuid4().hex,expected_checkpoint=2))
    assert repaired['failed']==0 and service.status(job.project_id)['status']=='COMPLETE'


def test_maintenance_stops_at_time_budget_and_keeps_resumable_checkpoint(package_parts,monkeypatch):
    _,reader,service,_=services(package_parts);_,_,job,_,_=package_parts
    original=RuleHistoryRepository.scan
    def scan(self,project_id,**values):
        rows=original(self,project_id,**values)
        if values['limit']>1:return (*rows,dict(run_id='not-read',manifest_hash='0'*64,published_at_us=NOW+30,created_at_us=NOW))
        return (dict(run_id='not-read'),)
    monkeypatch.setattr(RuleHistoryRepository,'scan',scan)
    moments=iter((0,6));service.clock=lambda:next(moments)
    count=0;read=reader.package
    def counted(*args,**kwargs):
        nonlocal count
        count+=1;return read(*args,**kwargs)
    monkeypatch.setattr(reader,'package',counted)
    result=service.maintain(job.project_id,MaintainHistory(operation_id=uuid4().hex,expected_checkpoint=0,limit=25))
    assert count==1 and result['processed']==1 and not result['complete'] and result['checkpoint']==1


def test_concurrent_maintenance_cannot_overwrite_advanced_checkpoint(package_parts,monkeypatch):
    _,reader,service,_=services(package_parts);project=package_parts[2].project_id
    original=reader.package;entered=False
    def concurrent(*args,**kwargs):
        nonlocal entered
        if not entered:
            entered=True
            service.maintain(project,MaintainHistory(operation_id=uuid4().hex,expected_checkpoint=0))
        return original(*args,**kwargs)
    monkeypatch.setattr(reader,'package',concurrent)
    command=MaintainHistory(operation_id=uuid4().hex,expected_checkpoint=0)
    with pytest.raises(JiejianError,match='另一批整理'):service.maintain(project,command)
    assert service.status(project)['checkpoint']==1
    assert service.receipt(project,command.operation_id)['status']=='NOT_FOUND'


def test_rule_catalog_pages_exact_revisions_and_never_borrows_old_result(tmp_path):
    from tests.support.builders.checks.check_service import ready_check_harness
    from product.backend.domain.boundaries.permissions import PermissionIntentRevision, PermissionIntentSemantic, permission_intent_sha256
    harness=ready_check_harness(tmp_path);core,project=harness.core,harness.project_id
    try:
        existing=core.business_boundaries.view(project).permission_intents;original=existing[0]
        with core.uow_factory() as work:
            for index in range(256,287):work.permission_intents.add_revision(original.model_copy(update={'intent_id':f'pin_{index:032x}'}))
            values=original.model_dump(mode='json');values.update(intent_id='pin_'+f'{256:032x}',revision=2,effective_state='RETIRED')
            values['intent_hash']=permission_intent_sha256({key:values[key] for key in PermissionIntentSemantic.model_fields})
            work.permission_intents.add_revision(PermissionIntentRevision.model_validate_json(__import__('json').dumps(values)));work.commit()
        first=core.check_history.rules(project,limit=25)
        assert len(first['items'])==25 and first['next_cursor'] is not None
        second=core.check_history.rules(project,limit=25,after=first['next_cursor'])
        ids={(item['intent_id'],item['revision']) for item in first['items']+second['items']}
        assert len(ids)==len(existing)+30 and not any(item[0]=='pin_'+f'{256:032x}' for item in ids)
        archived=core.check_history.rules(project,limit=50,include_archived=True)
        assert {(item['revision'],item['effective_state']) for item in archived['items'] if item['intent_id']=='pin_'+f'{256:032x}'}=={(1,'ACTIVE'),(2,'RETIRED')}
        assert all(item['latest_run_id'] is None and item['case_results']==[] for item in archived['items'])
    finally:harness.close()


def test_history_maintenance_api_requires_local_session_and_exact_filter(package_parts,worker_services):
    import sqlite3
    from tests.support.builders.control_plane import create_app, TestClient
    from tests.support.builders.preparation.action_preparation import MemorySecretStore
    from fastapi.testclient import TestClient as RawClient
    package,_,_,_=services(package_parts);var=package_parts[0];project=package.request.project_id
    (var/'data').mkdir(exist_ok=True)
    with sqlite3.connect(worker_services.database_path) as source,sqlite3.connect(var/'data/jiejian.db') as target:source.backup(target)
    app=create_app(var,start_worker=False,secret_store=MemorySecretStore(),environ={});base=f'/api/projects/{project}/check-history'
    with TestClient(app) as client:
        assert client.get(base,params=dict(intent_id='incomplete')).status_code==400
        payload=dict(operation_id=uuid4().hex,expected_checkpoint=0,limit=1)
        response=client.post(base+'/index-maintenance',json=payload);assert response.status_code==200,response.text
        assert client.post(base+'/index-maintenance',json=payload).json()==response.json()
        assert client.get(base+'/index-maintenance/'+payload['operation_id']).json()['data']['status']=='FOUND'
        raw=RawClient(app)
        try:assert raw.post(base+'/index-maintenance',json=dict(payload,operation_id=uuid4().hex)).status_code in {403,421}
        finally:raw.close()

pytestmark = [pytest.mark.level3]
