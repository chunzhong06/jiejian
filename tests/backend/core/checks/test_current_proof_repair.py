# 原题标准按新来源实际语义比较；修订与预检查不换题，文件或采集方法变化必须改变标准。
from types import SimpleNamespace as NS
import pytest
from product.backend.core.checks.repair import repair_evidence_standards
from product.protocols.preparation.proof_sources import AtomicProofSourceConfig,FileProofSourceConfig,FrozenProofSource,ProofContractAttestation,proof_fingerprint
from product.protocols.checks.business_facts import ArtifactManifestReference
from tests.fixtures.checks.check_execution import execution_pair


def current_standard(*,file=False):
    request,bundle=execution_pair(state_changing=True);action=request.actions[0];case=action.cases[0]
    config=AtomicProofSourceConfig(action_id=action.action_id,action_revision=action.action_revision,effect_id=case.proof_requirements[0].effect_id,
        observation_identity_id=bundle.actions[0].proofs[0].observation_identity_id,resource_binding_id='res_'+'1'*32,
        collection='units',relative_path_template='/collections/units/{resource_id}',source_contract_id='TRANSACTION_HISTORY_V2',
        mappings=dict(resource_id=('resource_id',),owner_id=('owner_id',),state=('data','state')),
        identity_claims=tuple(dict(identity_id=identity.identity_id,application_subject_id=identity.verification.expected_application_subject_id,
            request_path='/api/me',subject_path=('id',),role_path=('role',),application_role='owner' if index==0 else 'member') for index,identity in enumerate(bundle.identities)))
    if file:
        config=FileProofSourceConfig(**(config.model_dump(exclude={'source_kind','source_contract_id'})|dict(source_kind='REFERENCE_FILE',source_contract_id='FILE_RESPONSE_CONTENT_V1',
            reference_artifact=ArtifactManifestReference(asset_id='pai_'+'1'*32,sha256='a'*64,size=3),reference_origin='UPLOAD',
            reference_resource_id=case.resource_id,reference_owner_identity_id=case.resource_owner_test_identity_id)))
    contract=ProofContractAttestation(contract_id=config.source_contract_id,implementation_profile='CONTROLLED_FILE_RECEIPT_V1' if file else 'CONTROLLED_TRANSACTION_RECORDS_V2',
        fingerprint='b'*64,approved_effect_kind='FILE_CONTENT_DELIVERY' if file else 'STATE_MUTATION')
    source=FrozenProofSource(source_id='psr_'+'1'*32,revision=1,source_fingerprint=proof_fingerprint(config),config=config,contract=contract,
        owner_subject_id='owner',identity_roles={claim.identity_id:claim.application_role for claim in config.identity_claims},adoption_preflight_id='ppf_'+'1'*32 if file else None)
    proof=bundle.actions[0].proofs[0].model_copy(update={'descriptor_fingerprint':source.source_fingerprint,'effect_kind':contract.approved_effect_kind})
    current=NS(schema_version='6',json_sources=(source,),identities=bundle.identities,observers=(),actions=(bundle.actions[0].model_copy(update={'proofs':(proof,)}),))
    return action,case,current


def replace_config(bundle,config):
    source=bundle.json_sources[0].model_copy(update={'config':config,'source_fingerprint':proof_fingerprint(config)})
    proof=bundle.actions[0].proofs[0].model_copy(update={'descriptor_fingerprint':source.source_fingerprint})
    return NS(**(vars(bundle)|dict(json_sources=(source,),actions=(bundle.actions[0].model_copy(update={'proofs':(proof,)}),))))


@pytest.mark.parametrize('file',[False,True])
def test_same_meaning_revision_preflight_and_labels_keep_standard(file):
    action,case,bundle=current_standard(file=file);original=repair_evidence_standards(action,case,bundle)
    source=bundle.json_sources[0].model_copy(update={'revision':5,'adoption_preflight_id':'ppf_'+'2'*32})
    changed=NS(**(vars(bundle)|dict(json_sources=(source,),actions=(bundle.actions[0].model_copy(update={'display_name':'新标签'}),))))
    assert repair_evidence_standards(action,case,changed)==original
    config=source.config.model_copy(update={'read_scope_id':'prs_'+'3'*32,'source_files':('new-reference.mjs',)})
    assert repair_evidence_standards(action,case,replace_config(changed,config))==original


@pytest.mark.parametrize('field',['mapping','collection','identity','projection','expected','file_id','file_hash','file_size'])
def test_meaning_and_file_reference_changes_cannot_claim_equivalent_standard(field):
    action,case,bundle=current_standard(file=field.startswith('file'));original=repair_evidence_standards(action,case,bundle)
    config=bundle.json_sources[0].config
    if field=='mapping':config=config.model_copy(update={'mappings':dict(config.mappings,state=('data','another_state'))})
    elif field=='collection':config=config.model_copy(update={'collection':'other'})
    elif field=='identity':config=config.model_copy(update={'identity_claims':(config.identity_claims[0].model_copy(update={'subject_path':('other',)}),*config.identity_claims[1:])})
    elif field=='projection':config=config.model_copy(update={'protected_projection':('restricted',)})
    elif field=='expected':
        proof=bundle.actions[0].proofs[0].model_copy(update={'expected_state':'different'})
        bundle.actions=(bundle.actions[0].model_copy(update={'proofs':(proof,)}),)
    else:
        key={'file_id':'asset_id','file_hash':'sha256','file_size':'size'}[field]
        value={'file_id':'pai_'+'2'*32,'file_hash':'b'*64,'file_size':4}[field]
        config=config.model_copy(update={'reference_artifact':config.reference_artifact.model_copy(update={key:value})})
    assert repair_evidence_standards(action,case,replace_config(bundle,config))!=original


def test_new_pass_after_replacing_reference_does_not_verify_original_repair():
    from product.backend.core.checks.repair import repair_context,verify_current_repair
    from product.backend.workflows.checks.repairs.repair import build_current_repair_contract
    from product.protocols.checks.execution_request import ChangeContext
    from tests.backend.core._support_check_repair import package
    source=package();_,_,source.bundle=current_standard(file=True)
    denied=next(case for action in source.request.actions for case in action.cases if case.permission.expectation=='DENY')
    contract=build_current_repair_contract(source,denied.case_id)
    current=package(forbidden=False,run_id='run_'+'2'*32);current.bundle=source.bundle
    change=ChangeContext(change_id='chg_'+'3'*32,impact_fingerprint='4'*64,required_intent_ids=tuple(sorted(ref.intent_id for ref in contract.original_intents)))
    current.request=current.request.model_copy(update={'change_context':change,'repair_context':repair_context(contract)})
    def verify():return verify_current_repair(contract,request=current.request,bundle=current.bundle,result=current.result,evidence=current.evidence,expected_change_context=change)
    assert verify().status=='VERIFIED'
    config=current.bundle.json_sources[0].config
    config=config.model_copy(update={'reference_artifact':config.reference_artifact.model_copy(update={'asset_id':'pai_'+'4'*32})})
    current.bundle=replace_config(current.bundle,config)
    assert current.result.verdict.value=='PASS'
    assert verify().status=='INCONCLUSIVE' and verify().reason_codes==('REPAIR_STANDARD_CHANGED',)
