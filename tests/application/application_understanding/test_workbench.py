"""保护无源码事实、来源净化和重复工作中的人工资产。"""
import json
from uuid import uuid4
import pytest

from product.backend.application.application_understanding.imports import normalize_source
from product.backend.domain.errors import JiejianError
from product.protocols.web.environment import FrozenEnvironment
from product.protocols.web.target import WebTargetScope
from product.protocols.preparation.api_source import ApiSourceDocument,parse_source_document


@pytest.mark.parametrize('kind',['source','environment'])
def test_current_catalog_accepts_only_consumed_revisions_and_history_keeps_strict_ownership(core,monkeypatch,kind):
    from product.backend.infrastructure.storage.applications.api_sources import ApiSourceRepository,ApiSourceRow
    from product.backend.infrastructure.storage.applications.environments import EnvironmentRepository,EnvironmentRow
    from product.protocols.web.environment import EnvironmentDocument
    project=core.application_environments.create_application(operation_id=uuid4().hex,name='修订查询')
    other=core.application_environments.create_application(operation_id=uuid4().hex,name='其他应用')
    identifier=('src_' if kind=='source' else 'env_')+uuid4().hex
    target=WebTargetScope(base_url='http://127.0.0.1:18081',allowed_origins=('http://127.0.0.1:18081',),allowed_hosts=('127.0.0.1',),allowed_ports=(18081,),allow_private_network=True)
    with core.uow_factory() as work:
        repository=work.api_sources if kind=='source' else work.environments
        for revision in range(1,101):
            document=(ApiSourceDocument(source_id=identifier,project_id=project.project_id,revision=revision,
                kind='OPENAPI',name='接口',requests=(),warnings=(),created_at_us=revision) if kind=='source' else
                EnvironmentDocument(project_id=project.project_id,configuration=FrozenEnvironment(
                    environment_id=identifier,revision=revision,name='环境',target=target),created_at_us=revision))
            repository.add(document)
        row=work._session.get(ApiSourceRow if kind=='source' else EnvironmentRow,(identifier,1))
        row.payload='{}'
        work.commit()
    owner=ApiSourceRepository if kind=='source' else EnvironmentRepository
    original=owner._document
    accepted=[]
    def read(row,*args):
        accepted.append(row.revision)
        return original(row,*args)
    monkeypatch.setattr(owner,'_document',staticmethod(read))
    with core.uow_factory() as work:
        repository=work.api_sources if kind=='source' else work.environments
        assert len(repository.latest(project.project_id))==1
        assert accepted==[100]
        assert repository.revision(other.project_id,identifier,1) is None
        assert repository.latest(other.project_id)==()
        with pytest.raises(JiejianError):repository.revision(project.project_id,identifier,1)
        with pytest.raises(JiejianError):repository.revisions(project.project_id)


def test_external_environment_preserves_absent_source_and_reuses_revision(core):
    operation = uuid4().hex
    project = core.application_environments.create_application(operation_id=operation, name='业务系统')
    assert core.application_environments.create_application(operation_id=operation, name='业务系统') == project
    target = WebTargetScope(base_url='http://127.0.0.1:18081', allowed_origins=('http://127.0.0.1:18081',),
        allowed_hosts=('127.0.0.1',), allowed_ports=(18081,), allow_private_network=True)
    environment = FrozenEnvironment(environment_id='env_' + uuid4().hex, revision=1, name='测试环境', target=target)
    first = core.application_environments.save(project.project_id, environment, expected_revision=0)
    assert core.application_environments.save(project.project_id, environment, expected_revision=0) == first
    current = core.application_environments.activate(project.project_id, environment.environment_id, revision=1, expected_revision=0)
    assert current.source_root is None and current.source_fingerprint is None
    assert current.environment == environment and current.confirmed_endpoint is None
    assert core.application_understanding.inspect_source_fingerprint(project.project_id) is None
    with pytest.raises(JiejianError):
        core.application_environments.create_application(operation_id=operation, name='另一应用')


def test_har_drops_values_and_keeps_no_script_or_response():
    secret = 'sensitive-credential-value'
    raw = json.dumps({'log': {'entries': [{'request': {'method':'GET',
        'url':'http://127.0.0.1:8080/orders?token=' + secret,
        'headers':[{'name':'Authorization','value':'Bearer ' + secret}]},
        'response': {'content': {'text':secret}}}]}})
    requests, warnings = normalize_source(raw, 'HAR')
    encoded = json.dumps([item.model_dump(mode='json') for item in requests])
    assert secret not in encoded and 'Bearer' not in encoded
    assert requests[0].parameters[0].sensitive
    assert requests[0].path == '/orders' and warnings


@pytest.mark.parametrize('document,kind', [
    ({'openapi':'3.1.0','paths':{},'components':{'schemas':{'bad':{'$ref':'https://invalid.example/schema'}}}}, 'OPENAPI'),
    ({'log':{'entries':[{'request':{'method':'GET','url':'http://user:password@127.0.0.1/data'}}]}}, 'HAR'),
    ({'info':{'schema':'https://schema.getpostman.com/json/collection/v2.1.0/collection.json'},
      'item':[{'request':{'method':'GET','url':'{{base}}/data'}}]}, 'POSTMAN'),
])
def test_unknown_source_inputs_are_rejected_without_external_io(document, kind):
    with pytest.raises(JiejianError):
        normalize_source(json.dumps(document), kind)


def test_source_update_preserves_annotations_and_checks_revision(core):
    project = core.application_environments.create_application(operation_id=uuid4().hex, name='业务系统')
    sources = core.application_sources
    source_id = 'src_' + uuid4().hex
    raw = json.dumps({'openapi':'3.1.0', 'paths':{'/orders/{id}':{'get':{'summary':'订单详情'}}}}, ensure_ascii=False)
    preview = sources.preview(project.project_id, raw=raw, kind='OPENAPI')
    document = sources.accept(project.project_id, candidate_id=preview['candidate_id'], name='接口文档', source_id=source_id,
        expected_revision=0, expected_fingerprint=preview['fingerprint'])
    request = document.requests[0]
    annotation = sources.annotate(project.project_id, source_id, request.item_id,
        label='人工订单说明', action_id=None, expected_revision=0)
    updated = raw.replace('订单详情', '新名称')
    preview = sources.preview(project.project_id, raw=updated, kind='OPENAPI', source_id=source_id)
    assert preview['changed'] == (request.item_id,)
    sources.accept(project.project_id, candidate_id=preview['candidate_id'], name='接口文档', source_id=source_id,
        expected_revision=1, expected_fingerprint=preview['fingerprint'])
    assert sources.context(project.project_id)['annotations'] == (annotation,)
    with pytest.raises(JiejianError):
        sources.annotate(project.project_id, source_id, request.item_id, label='过期编辑', action_id=None, expected_revision=0)


def test_persistent_source_roots_require_explicit_format_identity():
    source=dict(document_type='jiejian.api-source',schema_version='1',source_id='src_'+'a'*32,
        project_id='app',revision=1,kind='OPENAPI',name='接口',requests=[],warnings=[],created_at_us=1)
    assert parse_source_document(json.dumps(source),ApiSourceDocument).revision==1
    for field in ('document_type','schema_version'):
        broken={key:value for key,value in source.items() if key!=field}
        with pytest.raises(ValueError):
            parse_source_document(json.dumps(broken),ApiSourceDocument)


def test_local_references_and_body_names_are_imported_without_example_values():
    document={'openapi':'3.1.0','components':{'parameters':{'Id':{'name':'id','in':'path','required':True}},
        'schemas':{'Body':{'type':'object','properties':{'amount':{'type':'number','example':12345},'token':{'type':'string','example':'credential-value'}}}}},
        'paths':{'/orders/{id}':{'parameters':[{'$ref':'#/components/parameters/Id'}],'patch':{'requestBody':{'content':{'application/json':{'schema':{'$ref':'#/components/schemas/Body'}}}}}}}}
    requests,_warnings=normalize_source(json.dumps(document),'OPENAPI')
    assert {(item.name,item.location) for item in requests[0].parameters}=={('id','PATH'),('amount','BODY'),('token','BODY')}
    assert 'credential-value' not in requests[0].model_dump_json() and '12345' not in requests[0].model_dump_json()


@pytest.mark.parametrize('document,kind',[
    ({'info':[]},'POSTMAN'),({'openapi':'3.1.0','paths':{'/orders':{'get':{'parameters':1}}}},'OPENAPI'),
    ({'log':{'entries':[{'request':{'method':'GET','url':'/orders','headers':'not-a-list'}}]}},'HAR'),
])
def test_malformed_shapes_produce_safe_input_errors(document,kind):
    with pytest.raises(JiejianError):
        normalize_source(json.dumps(document),kind)


def test_connection_impact_is_read_only_and_stale_material_basis_is_rejected(core, monkeypatch):
    project = core.application_environments.create_application(operation_id=uuid4().hex, name='连接切换')
    target = WebTargetScope(base_url='http://127.0.0.1:18081', allowed_origins=('http://127.0.0.1:18081',),
        allowed_hosts=('127.0.0.1',), allowed_ports=(18081,), allow_private_network=True)
    environment = FrozenEnvironment(environment_id='env_' + uuid4().hex, revision=1, name='修复部署', target=target)
    core.application_environments.save(project.project_id, environment, expected_revision=0)
    current = dict(state='RECHECK_REQUIRED', basis='old', items=[])
    monkeypatch.setattr(core.application_environments, '_impact_reader', lambda project, work: current.copy())
    preview = core.application_environments.activation_preview(project.project_id, environment.environment_id, revision=1)
    assert preview['materials']['basis'] == 'old'
    assert core.application_environments.context(project.project_id)['active_environment'] is None
    current['basis'] = 'changed'
    with pytest.raises(JiejianError, match='重新查看切换影响'):
        core.application_environments.activate(project.project_id, environment.environment_id,
            revision=1, expected_revision=0, impact_fingerprint=preview['impact_fingerprint'])
    assert core.application_environments.context(project.project_id)['active_environment'] is None
    fresh = core.application_environments.activation_preview(project.project_id, environment.environment_id, revision=1)
    selected = core.application_environments.activate(project.project_id, environment.environment_id,
        revision=1, expected_revision=0, impact_fingerprint=fresh['impact_fingerprint'])
    assert selected.environment == environment
