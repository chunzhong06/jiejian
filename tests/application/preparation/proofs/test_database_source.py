"""两种真实服务库都经过明确 DDL 授权、后台预检、采用、发布阅读和准确移除。"""
import json
import time
from uuid import uuid4
import pytest

from product.backend.application.preparation.proofs.commands import SaveProofSource,GrantProofScope,StartProofPreflight,AdoptProofSource,MaintainDatabaseSource
from product.protocols.preparation.proof_sources import DatabaseProofSourceConfig
from tests.support.builders.execution.server_database import local_database
from tests.support.builders.runtime.managed_records import ordinary_application,source_configuration,wait_for,reload_ordinary_policy


@pytest.mark.parametrize('engine',['POSTGRESQL','MYSQL'])
@pytest.mark.parametrize('regression,expected',[(False,'PASS'),(True,'BLOCK')])
def test_database_source_full_lifecycle_and_published_facts(tmp_path,engine,regression,expected):
    with local_database(engine,tmp_path/'database') as server:
        harness=ordinary_application(tmp_path,regression=regression,database_backend=server)
        core,project=harness.core,harness.project_id
        try:
            service=core.proof_preparation
            context=service.context(project);basis=context['basis_id'];capture=context['databases'][0]
            config=source_configuration(harness).model_dump(mode='json')
            config.update(source_kind='DATABASE_AUDIT',database_capture=capture,protected_column='state',
                collection='business_records',relative_path_template='/collections/business_records/{resource_id}')
            config=DatabaseProofSourceConfig.model_validate_json(json.dumps(config))
            saved=service.save(project,SaveProofSource(operation_id=uuid4().hex,basis_id=basis,config=config))
            common=dict(source_id=saved['result']['source_id'],revision=1,basis_id=basis)
            service.grant_scope(project,GrantProofScope(operation_id=uuid4().hex,confirmed=True,**common))
            core.worker.start()
            def maintain(purpose):
                plan=service.maintenance_preview(project,common['source_id'],1,purpose)
                request=MaintainDatabaseSource(operation_id=uuid4().hex,**common,purpose=purpose,
                    maintenance_plan_fingerprint=plan['fingerprint'],confirmed=True)
                queued=service.start(project,request)
                # 同一请求只回读同一后台任务，不重复执行 DDL。
                assert service.start(project,request)==queued
                result=wait_for(lambda:service.status(project,queued['result']['preflight_id']))
                assert result['report']['assessment']=='COMPLETED',result
            maintain('INSTALL_DATABASE')
            assert service.show(project,common['source_id'])['database_installation']['installed']
            queued=service.start(project,StartProofPreflight(operation_id=uuid4().hex,**common))
            result=wait_for(lambda:service.status(project,queued['result']['preflight_id']))
            assert result['report']['assessment']=='USABLE',result
            service.adopt(project,AdoptProofSource(operation_id=uuid4().hex,preflight_id=queued['result']['preflight_id'],confirmed=True,**common))
            preview=core.checks.preview(project)
            assert preview.can_execute,preview
            submitted=core.checks.submit(project,expected_plan_fingerprint=preview.plan_fingerprint,idempotency_key=uuid4().hex)
            deadline=time.monotonic()+45
            while time.monotonic()<deadline:
                status=core.check_results.status(submitted.run.run_id,project_id=project)
                if status.run.lifecycle.value in {'COMPLETED','FAILED','CANCELLED','SAFETY_STOPPED'}:break
                time.sleep(.1)
            assert status.run.verdict is not None and status.run.verdict.value==expected,str(status)
            package=core.check_results.package(submitted.run.run_id,project_id=project)
            assert any(fact.data.kind=='COMMITTED_STATE' for item in package.evidence for fact in item.business_facts)
            for item in package.evidence:
                index=core.check_results.evidence_records(submitted.run.run_id,item.evidence_id,item.case.case_id,project_id=project)
                assert index.records
            if regression:
                from product.protocols.runtime.database_capture import DatabaseCapture
                reference=core.check_repairs.contracts(submitted.run.run_id)[0].reference()
                original=package.result.model_dump_json()
                for policy,verdict,repair in [('(true)','BLOCK','NOT_VERIFIED'),("actor.role === 'owner' && actor.id === ownerId",'PASS','VERIFIED')]:
                    change=reload_ordinary_policy(harness,policy,repair_reference=reference,
                        databases=(DatabaseCapture.model_validate_json(json.dumps(capture)),))
                    assert not service.active_sources(project)
                    current=common|dict(basis_id=service.context(project)['basis_id'])
                    queued=service.start(project,StartProofPreflight(operation_id=uuid4().hex,**current))
                    assert wait_for(lambda:service.status(project,queued['result']['preflight_id']))['report']['assessment']=='USABLE'
                    service.adopt(project,AdoptProofSource(operation_id=uuid4().hex,preflight_id=queued['result']['preflight_id'],confirmed=True,**current))
                    preview=core.checks.preview(project,change_id=change)
                    assert preview.can_execute,preview
                    submitted=core.checks.submit(project,expected_plan_fingerprint=preview.plan_fingerprint,idempotency_key=uuid4().hex,change_id=change)
                    deadline=time.monotonic()+45
                    while time.monotonic()<deadline:
                        status=core.check_results.status(submitted.run.run_id,project_id=project)
                        if status.run.lifecycle.value in {'COMPLETED','FAILED','CANCELLED','SAFETY_STOPPED'}:break
                        time.sleep(.1)
                    assert status.run.verdict.value==verdict,status
                    assert core.check_story.build(submitted.run.run_id).repair_verification.status==repair
                assert core.check_results.package(reference.source_run_id,project_id=project).result.model_dump_json()==original
                common=current
            maintain('REMOVE_DATABASE')
            assert service.show(project,common['source_id'])['database_installation']['state']=='REMOVED'
            assert not service.active_sources(project)
            from product.backend.infrastructure.observers.records.database_capture import connection,query
            with connection(config.database_capture,{capture['password_env']:server.password}) as database:
                assert query(database,'SELECT state FROM business_records WHERE id=%s',('alpha',))[0]['state']=='draft'
        finally:harness.close()


pytestmark=[pytest.mark.level4,pytest.mark.process]
