import json
import pytest
from pydantic import ValidationError
from product.protocols.preparation.operation_flow import OperationFlow,operation_resource_injection
from product.protocols.web.workflow import HttpWorkflowBinding
from product.protocols.checks.execution_request import RecoveryReference


def flow_document(*,created=False):
    target=dict(id='update',purpose='TARGET',identity_id='CASE_SUBJECT',request_template=dict(method='POST' if created else 'PATCH',
        path='/tickets' if created else '/tickets/{case_resource_id}',
        body=dict(kind='JSON',value={'title':{'$slot':'title'}}),
        input_slots=[dict(slot_id='title',source='PRIOR_STEP_JSON_PATH',consumer='JSON_BODY',producer_step_id='lookup',consumer_step_id='update',source_path='$.title')]
            +([] if created else [dict(slot_id='case_resource_id',source='CASE_RESOURCE_ID',consumer='PATH')]),
        response_extractors=[dict(extractor_id='created_resource_id',kind='JSON_PATH',json_path='$.id')] if created else []),
        classifier=dict(accepted=[dict(kind='STATUS_IN',statuses=[200,201])],denied=[]),depends_on_step_ids=['lookup'])
    setup=dict(id='lookup',purpose='SETUP',identity_id='CASE_SUBJECT',request_template=dict(method='GET',path='/defaults',response_extractors=[dict(extractor_id='title',kind='JSON_PATH',json_path='$.title')]),classifier=dict(accepted=[dict(kind='STATUS_IN',statuses=[200])],denied=[]))
    workflow=HttpWorkflowBinding.model_validate_json(json.dumps(dict(workflow_id='ofl_'+'a'*32,source_flow_id='ofl_'+'a'*32,action_id='bac_'+'b'*32,steps=[setup,target],target_step_id='update')))
    return dict(id='ofl_'+'a'*32,revision=1,project_id='app_'+'b'*32,business_action_id='bac_'+'b'*32,action_revision=1,
        subject_test_identity_id='tid_'+'c'*32,resource_owner_test_identity_id='tid_'+'c'*32,provenance='MANUAL',source_fingerprint='d'*64,
        target_scope=dict(base_url='http://127.0.0.1:8000',allowed_origins=['http://127.0.0.1:8000'],allowed_hosts=['127.0.0.1'],allowed_ports=[8000],allow_private_network=True),
        workflow=workflow.model_dump(mode='json'),actual_resource_id='sample',resource_injection=operation_resource_injection(workflow).model_dump(mode='json'),
        recovery=dict(method='POST',relative_path='/restore/{case_resource_id}',json_body={}))


@pytest.mark.parametrize('created',[False,True])
def test_dynamic_operation_flow_has_one_exact_resource_origin(created):
    document=flow_document(created=created)
    value=OperationFlow.model_validate_json(json.dumps(document))
    assert value.resource_injection.consumer.value==('RESPONSE_JSON' if created else 'PATH')
    assert value.steps[1].depends_on_step_ids==('lookup',)
    document['resource_injection']['location']='$.other' if created else 'path[0]'
    with pytest.raises(ValidationError):OperationFlow.model_validate_json(json.dumps(document))


def test_flow_cannot_read_undeclared_producer_field_or_forge_recording_origin():
    document=flow_document()
    document['workflow']['steps'][1]['request_template']['input_slots'][0]['source_path']='$.other'
    document['workflow']['workflow_fingerprint']=None
    with pytest.raises(ValidationError):OperationFlow.model_validate_json(json.dumps(document))
    document=flow_document();document['provenance']='RECORDING'
    with pytest.raises(ValidationError):OperationFlow.model_validate_json(json.dumps(document))


def test_recovery_preserves_legacy_hash_fields_and_rejects_mixed_origins():
    fields=dict(step_id='restore',binding_fingerprint='a'*64,request_template_fingerprint='b'*64)
    legacy=RecoveryReference(**fields,recording_id='rec_'+'c'*32,draft_revision=1,draft_sha256='d'*64)
    assert 'operation_flow_id' not in legacy.model_dump(mode='json')
    edited=RecoveryReference(**fields,operation_flow_id='ofl_'+'c'*32,operation_flow_revision=2)
    assert 'recording_id' not in edited.model_dump(mode='json')
    with pytest.raises(ValidationError):RecoveryReference(**legacy.model_dump(),operation_flow_id='ofl_'+'c'*32,operation_flow_revision=2)
