"""以原请求条件保护原题，不能让更弱的请求和普通SAFE结果替代漏洞路径。"""
import pytest
from product.backend.domain.checks.repair import verify_current_repair
from product.protocols.web.request import HttpParameter,JsonBody
from tests.support.builders.checks.repair import contract_and_new


def test_changed_trigger_cannot_be_verified_as_original_repair():
    contract,current,change=contract_and_new()
    action=current.bundle.actions[0]
    step=action.steps[-1]
    changed=step.model_copy(update={'request':step.request.model_copy(update={'query':(HttpParameter(name='force',literal='false'),)})})
    current.bundle=current.bundle.model_copy(update={'actions':(action.model_copy(update={'steps':(*action.steps[:-1],changed)}),*current.bundle.actions[1:])})
    result=verify_current_repair(contract,request=current.request,bundle=current.bundle,result=current.result,
        evidence=current.evidence,expected_change_context=change,original_request=current.original.request,original_bundle=current.original.bundle)
    assert result.status=='INCONCLUSIVE'
    assert result.reason_codes==('REPAIR_CHALLENGE_CHANGED',)


def verify(current,contract,change,**extra):
    return verify_current_repair(contract,request=current.request,bundle=current.bundle,result=current.result,
        evidence=current.evidence,expected_change_context=change,original_request=current.original.request,
        original_bundle=current.original.bundle,**extra)


@pytest.mark.parametrize('field',['path','method','body','query','setup','dependency'])
def test_original_request_obligations_survive_a_safe_current_result(field):
    contract,current,change=contract_and_new()
    action=current.bundle.actions[0];target=action.steps[-1]
    if field in {'setup','dependency'}:
        setup=target.model_copy(update={'step_id':'setup-original','purpose':'SETUP','request':target.request.model_copy(update={'path':'/prepare/{resource}'})})
        baseline=action.model_copy(update={'steps':(setup,target.model_copy(update={'depends_on_step_ids':(setup.step_id,)}))})
        current.original.bundle=current.original.bundle.model_copy(update={'actions':(baseline,)})
        steps=(setup,target) if field=='dependency' else action.steps
        current.bundle=current.bundle.model_copy(update={'actions':(action.model_copy(update={'steps':steps}),)})
    else:
        updates={'path':{'path':'/weaker/{resource}'},'method':{'method':'GET'},'body':{'body':JsonBody(value={'force':False})},'query':{'query':(HttpParameter(name='force',literal='false'),)}}[field]
        if field in {'body','query'}:
            original=target.request.model_copy(update={'body':JsonBody(value={'force':True})} if field=='body' else {'query':(HttpParameter(name='force',literal='true'),)})
            current.original.bundle=current.original.bundle.model_copy(update={'actions':(action.model_copy(update={'steps':(target.model_copy(update={'request':original}),)}),)})
        changed=target.model_copy(update={'request':target.request.model_copy(update=updates)})
        current.bundle=current.bundle.model_copy(update={'actions':(action.model_copy(update={'steps':(*action.steps[:-1],changed)}),)})
    answer=verify(current,contract,change)
    assert current.result.verdict.value=='PASS'
    assert answer.status=='INCONCLUSIVE' and answer.reason_codes==('REPAIR_CHALLENGE_CHANGED',)


def test_technical_rerecording_and_new_session_do_not_replace_original_request():
    contract,current,change=contract_and_new()
    action=current.bundle.actions[0];target=action.steps[-1];slot=target.request.input_slots[0]
    request=target.request.model_copy(update={'path':target.request.path.replace('{'+slot.slot_id+'}','{new-resource-slot}'),
        'input_slots':(slot.model_copy(update={'slot_id':'new-resource-slot'}),)})
    rerecorded=action.model_copy(update={'flow_id':'new-flow','flow_sha256':'f'*64,'steps':(target.model_copy(update={'step_id':'new-target','request':request}),)})
    current.bundle=current.bundle.model_copy(update={'actions':(rerecorded,),
        'identities':tuple(identity.model_copy(update={'binding':identity.binding.model_copy(update={'secret_ref':'env:REFRESHED_SESSION'})}) for identity in current.bundle.identities)})
    action=current.request.actions[0]
    current.request=current.request.model_copy(update={'actions':(action.model_copy(update={'cases':tuple(case.model_copy(update={'execution':case.execution.model_copy(update={'flow_id':'new-flow','flow_sha256':'f'*64})}) for case in action.cases)}),)})
    assert verify(current,contract,change).status=='VERIFIED'


def test_missing_original_request_cannot_be_replaced_by_the_current_request():
    contract,current,change=contract_and_new()
    answer=verify_current_repair(contract,request=current.request,bundle=current.bundle,result=current.result,
        evidence=current.evidence,expected_change_context=change)
    assert answer.status=='INCONCLUSIVE' and answer.reason_codes==('REPAIR_CHALLENGE_UNAVAILABLE',)


def test_condition_comparison_does_not_change_the_original_reference():
    from product.backend.application.checks.repairs.repair import build_current_repair_contract
    contract,current,change=contract_and_new()
    before=contract.reference();verify(current,contract,change)
    rebuilt=build_current_repair_contract(current.original,contract.source_case_id)
    assert rebuilt.reference()==before


@pytest.mark.parametrize('kind',['public_header','fixed_to_dynamic','array_order'])
def test_request_values_cannot_be_weakened_through_another_representation(kind):
    from product.protocols.web.request import ValueSlot,ValueSlotSource,ValueSlotConsumer,ValueType
    contract,current,change=contract_and_new()
    action=current.bundle.actions[0];target=action.steps[-1]
    if kind=='public_header':
        before=target.request.model_copy(update={'headers':(HttpParameter(name='X-Mode',literal='force'),)})
        after=before.model_copy(update={'headers':(HttpParameter(name='x-mode',literal='normal'),)})
    elif kind=='array_order':
        before=target.request.model_copy(update={'body':JsonBody(value={'steps':['publish','authorize']})})
        after=before.model_copy(update={'body':JsonBody(value={'steps':['authorize','publish']})})
    else:
        before=target.request.model_copy(update={'query':(HttpParameter(name='force',literal='true'),)})
        slot=ValueSlot(slot_id='trigger',source=ValueSlotSource.CASE_RESOURCE_ID,consumer=ValueSlotConsumer.QUERY,value_type=ValueType.STRING)
        after=before.model_copy(update={'query':(HttpParameter(name='force',slot_id='trigger'),),'input_slots':(*before.input_slots,slot)})
    current.original.bundle=current.original.bundle.model_copy(update={'actions':(action.model_copy(update={'steps':(target.model_copy(update={'request':before}),)}),)})
    current.bundle=current.bundle.model_copy(update={'actions':(action.model_copy(update={'steps':(target.model_copy(update={'request':after}),)}),)})
    assert verify(current,contract,change).reason_codes==('REPAIR_CHALLENGE_CHANGED',)
