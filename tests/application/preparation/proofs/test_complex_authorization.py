"""普通应用的关系前提和字段后果从正式权限、来源采用走到独立发布阅读。"""
import json
import time
from uuid import uuid4

import httpx
import pytest
from product.backend.application.preparation.proofs.commands import SaveProofSource,GrantProofScope,StartProofPreflight,AdoptProofSource
from product.protocols.preparation.proof_sources import AtomicProofSourceConfig
from tests.support.builders.runtime.managed_records import ordinary_application,source_configuration,wait_for,reload_ordinary_policy


def adopt_and_check(harness,config,expected,*,change_id=None):
    core,project=harness.core,harness.project_id
    service=core.proof_preparation
    basis=service.context(project)['basis_id']
    saved=service.save(project,SaveProofSource(operation_id=uuid4().hex,basis_id=basis,config=config))
    common=dict(basis_id=basis,source_id=saved['result']['source_id'],revision=1)
    service.grant_scope(project,GrantProofScope(operation_id=uuid4().hex,confirmed=True,**common))
    queued=service.start(project,StartProofPreflight(operation_id=uuid4().hex,**common));core.worker.start()
    result=wait_for(lambda:service.status(project,queued['result']['preflight_id']))
    assert result['report']['assessment']=='USABLE',result
    service.adopt(project,AdoptProofSource(operation_id=uuid4().hex,preflight_id=queued['result']['preflight_id'],confirmed=True,**common))
    # 样本在正式检查前更新；不把应用启动时的旧共享表冒充本次时效事实。
    port=core.node_runtime.reference(project).port
    with httpx.Client(base_url=f'http://127.0.0.1:{port}',trust_env=False) as client:
        assert client.post('/api/login',json={'account':'alice'}).status_code==200
        response=client.post('/__test_relationship_sample')
        assert response.status_code in (200,404)
    scope=dict(change_id=change_id) if change_id else {}
    preview=core.checks.preview(project,**scope)
    assert preview.can_execute,preview
    submitted=core.checks.submit(project,expected_plan_fingerprint=preview.plan_fingerprint,idempotency_key=uuid4().hex,**scope)
    deadline=time.monotonic()+45
    while time.monotonic()<deadline:
        status=core.check_results.status(submitted.run.run_id,project_id=project)
        if status.run.lifecycle.value in {'COMPLETED','FAILED','CANCELLED','SAFETY_STOPPED'}:break
        time.sleep(.1)
    package=core.check_results.package(submitted.run.run_id,project_id=project)
    assert status.run.verdict is not None and status.run.verdict.value==expected,(
        package.result.primary_error,[(item.verdict,item.reason_codes) for item in package.result.case_results])
    assert package.evidence
    for evidence in package.evidence:
        assert core.check_results.evidence_records(submitted.run.run_id,evidence.evidence_id,evidence.case.case_id,project_id=project).records
    return package


def verify_source_repairs(harness,configuration,baseline):
    """同一事实来源完成真实改码和原题复验，旧结果仍可独立阅读。"""
    core,project=harness.core,harness.project_id
    history=[(baseline.result.run_id,baseline.result.verdict)]
    reference=None;original=None
    for index,policy in enumerate(('true','true /* ineffective correction */',"actor.role === 'owner' && actor.id === ownerId")):
        change=reload_ordinary_policy(harness,policy,repair_reference=reference if index else None)
        package=adopt_and_check(harness,configuration(),'PASS' if index==2 else 'BLOCK',change_id=change if index else None)
        if index==0:
            original=package.result.run_id
            reference=core.check_repairs.contracts(original)[0].reference()
        else:
            repair=core.check_story.build(package.result.run_id).repair_verification
            assert repair.source_run_id==original
            assert repair.status==('VERIFIED' if index==2 else 'NOT_VERIFIED')
        history.append((package.result.run_id,package.result.verdict))
        for run_id,verdict in history:
            assert core.check_results.package(run_id,project_id=project).result.verdict==verdict


@pytest.mark.parametrize('requirement,regression,group',[
    (dict(kind='ORGANIZATION'),False,False),
    (dict(kind='ORGANIZATION',organization_scope='SUBJECT_ANCESTOR',max_depth=2),True,False),
    (dict(kind='ROLE_INHERITANCE',inherited_role='reader',max_depth=2),False,False),
    (dict(kind='SHARING',state='ACTIVE'),False,False),
    (dict(kind='SHARING',state='REVOKED'),True,False),
    (dict(kind='DELEGATION',state='EXPIRED'),False,False),
    (dict(kind='SHARING',state='ACTIVE'),False,True),
])
def test_real_relationship_prerequisites_are_preserved_in_results(tmp_path,requirement,regression,group):
    graph=[dict(child='team',parent='department'),dict(child='department',parent='organization')]
    data=dict(scope_complete=True,organization='team',organization_parents=graph,
        role_inheritance=[dict(child='editor',parent='reader')],grants=[],source_time=1)
    if requirement['kind'] in {'SHARING','DELEGATION'}:
        grant=dict(grant_id='g1',kind=requirement['kind'],grantor_id='alice',grantee_id='bob',resource_id='alpha',
            actions=['publish'],valid_from_us=1)
        if requirement.get('state')=='EXPIRED':grant['valid_until_us']=2
        if requirement.get('state')=='REVOKED':grant['revoked_at_us']=2
        if group:grant.update(grantee_kind='GROUP',grantee_id='reviewers')
        data['grants']=[grant]
    def driver(text):
        text=text.replace("{id:'bob',role:roles[1]}","{id:'bob',role:roles[1],organizations:['team','organization'],groups:['reviewers'],roles:['editor']}")
        text=text.replace("{state:'draft',title:'unit-a',summary:'value-a'}",json.dumps(dict(state='draft',title='unit-a',summary='value-a',**data)))
        marker="    if(req.url==='/api/me')return reply(200,actor);"
        return text.replace(marker,marker+"\n    if(req.url==='/__test_relationship_sample'&&actor.id==='alice'){const item=await records.read('alpha');await records.transact({resource_id:'alpha',subject_id:actor.id,expected_version:item.version,changes:[{path:['source_time'],value:Date.now()*1000}]});return reply(200,{ok:true});}")
    def proposal(command,selected):command['proposed_permissions'][1]['conditions']=dict(relationships=[requirement])
    complete= requirement.get('organization_scope')=='SUBJECT_ANCESTOR' or requirement['kind']=='ROLE_INHERITANCE' or group
    harness=ordinary_application(tmp_path,regression=regression and not complete,edit_driver=driver,edit_proposal=proposal)
    try:
        def configuration():
            config=source_configuration(harness).model_dump(mode='json')
            config['relationship_mapping']=dict(application_action='publish',scope_complete_path=['scope_complete'],
                source_time_path=['source_time'],subject_organizations_path=['organizations'],subject_groups_path=['groups'],
                resource_organization_path=['organization'],organization_parents_path=['organization_parents'],
                subject_roles_path=['roles'],role_inheritance_path=['role_inheritance'],grants_path=['grants'],
                clock_uncertainty_us=5_000_000)
            return AtomicProofSourceConfig.model_validate_json(json.dumps(config))
        package=adopt_and_check(harness,configuration(),'BLOCK' if regression and not complete else 'PASS')
        assert any(item.case.permission.conditions is not None for item in package.evidence)
        if complete:verify_source_repairs(harness,configuration,package)
    finally:harness.close()


@pytest.mark.parametrize('operation,initial,final,expected_value',[
    ('ASSIGN',dict(flag=False),dict(flag=True),True),
    ('ASSIGN',dict(flag=0),dict(flag=True),True),
    ('ADD',{},dict(flag=None),None),
    ('REMOVE',dict(flag=True),{},None),
])
def test_typed_field_mutation_has_real_commits_and_restores_nested_input(tmp_path,operation,initial,final,expected_value):
    def driver(text):
        text=text.replace("{state:'draft',title:'unit-a',summary:'value-a'}",json.dumps(dict(state='draft',title='unit-a',summary='value-a',payload=initial)))
        return text.replace("{path:['state'],value:step==='publish'?'published':'draft'}",
            "{path:['payload'],value:step==='publish'?"+json.dumps(final)+":"+json.dumps(initial)+"}")
    def proposal(command,selected):
        effect=command['proposed_actions'][0]['effect_catalog'][0]
        effect.update(expected_state=None,field_mutation=dict(path=['payload','flag'],operation=operation,expected_value=expected_value))
    harness=ordinary_application(tmp_path,edit_driver=driver,edit_proposal=proposal)
    try:
        def configuration():
            config=source_configuration(harness).model_dump(mode='json');config['mappings']['state']=['data','payload','flag']
            config['state_field_optional']=operation in {'ADD','REMOVE'}
            return AtomicProofSourceConfig.model_validate_json(json.dumps(config))
        package=adopt_and_check(harness,configuration(),'PASS')
        assert any(fact.data.kind=='COMMITTED_STATE' for item in package.evidence for fact in item.business_facts)
        verify_source_repairs(harness,configuration,package)
    finally:harness.close()


pytestmark=pytest.mark.level4
