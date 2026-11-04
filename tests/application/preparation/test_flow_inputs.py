import json
import pytest
from product.backend.application.preparation.flow_inputs import validate_public_flow_inputs
from product.backend.domain.errors import ErrorCode,JiejianError
from product.protocols.web.workflow import HttpWorkflowStep


def target(request):
    return HttpWorkflowStep.model_validate_json(json.dumps(dict(id='target',purpose='TARGET',identity_id='CASE_SUBJECT',request_template={'method':'POST','path':'/orders',**request})))


@pytest.mark.parametrize('request_input', [
    {'query':[{'name':'api_key','literal':'private-value'}]},
    {'body':{'kind':'JSON','value':{'nested':{'credentials':{'password':'private-value'}}}}},
    {'body':{'kind':'JSON','value':{'note':'Bearer private-value'}}},
    {'headers':[{'name':'X-CSRF-Token','slot_id':'token'}],'input_slots':[{'slot_id':'token','source':'PRIOR_STEP_JSON_PATH','consumer':'HEADER','producer_step_id':'setup','source_path':'$.csrf','secret':False}]},
])
def test_sensitive_flow_fields_cannot_enter_public_saved_inputs(request_input):
    with pytest.raises(JiejianError) as error:validate_public_flow_inputs((target(request_input),))
    assert error.value.code==ErrorCode.INPUT_INVALID
    assert 'private-value' not in str(error.value)


def test_explicit_secret_reference_and_public_literal_are_accepted():
    step=target({'query':[{'name':'page','literal':'2'}],
        'body':{'kind':'JSON','value':{'token':{'$slot':'dynamic'}}},
        'input_slots':[{'slot_id':'dynamic','source':'PRIOR_STEP_JSON_PATH','consumer':'JSON_BODY','producer_step_id':'setup','source_path':'$.token','secret':True}]})
    validate_public_flow_inputs((step,))


