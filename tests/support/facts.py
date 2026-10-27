# 构造可验证的冻结权限和独立业务效果事实，输入不包含真实账号或秘密。
from product.backend.domain.lifecycle import CaseVerdict
from product.backend.domain.verification.checks import CheckDecisionInput,CheckEffectFact
from product.protocols.checks.execution_request import CaseRole,EffectProofRequirement,ExecutionAssetReference,ExecutionCase,FrozenPermission,ObserverProofReference,content_hash

def identifier(prefix,number):return prefix+'_'+format(number,'032x')

def decision(expectation='DENY',state=None,**changes):
    effect=identifier('bef',1)
    owner=identifier('bar',1)
    actor=owner if expectation=='ALLOW' else identifier('bar',2)
    proof_values={'effect_id':effect,'level':'VERDICT_REQUIRED','rule':'REGISTERED_EFFECT','binding_fingerprint':'a'*64,'resource_id':'exhibition','reference':ObserverProofReference(descriptor_id=identifier('exp',1),descriptor_fingerprint='b'*64,observer_id='business-effects')}
    proof=EffectProofRequirement(**proof_values,proof_fingerprint=content_hash('EffectProofRequirement',{**proof_values,'reference':proof_values['reference'].model_dump(mode='json')}))
    permission=FrozenPermission(intent_id=identifier('pin',1),revision=1,intent_hash='c'*64,expectation=expectation,relation='OWNS' if expectation=='ALLOW' else 'OTHER_ROLE',subject_actor_id=actor,subject_actor_revision=1,resource_owner_actor_id=owner,resource_owner_actor_revision=1,protected_effect_ids=(effect,))
    case=ExecutionCase(case_id=identifier('case',1),roles=(CaseRole.ALLOW_REGRESSION,) if expectation=='ALLOW' else (CaseRole.DENY_CHALLENGE,),permission=permission,subject_test_identity_id=identifier('tid',1 if expectation=='ALLOW' else 2),subject_actor_id=actor,subject_actor_revision=1,subject_identity_fingerprint='d'*64,resource_owner_test_identity_id=identifier('tid',1),resource_owner_actor_id=owner,resource_owner_actor_revision=1,owner_identity_fingerprint='d'*64,resource_id='exhibition',resource_binding_fingerprint='e'*64,execution=ExecutionAssetReference(flow_id='download-package',flow_sha256='f'*64,execution_binding_fingerprint='1'*64),protected_effect_ids=(effect,),proof_requirements=(proof,),recovery=None,source_fingerprint='2'*64,config_fingerprint='3'*64)
    fact=CheckEffectFact(effect_id=effect,proof_fingerprint=proof.proof_fingerprint,state=state or ('CONFIRMED' if expectation=='ALLOW' else 'ABSENT'),complete=True,reliable=True,correlated=True,authoritative=True,closure='CLOSED')
    values={'case':case,'execution':'ACCEPTED' if expectation=='ALLOW' else 'DENIED','actual_identity':'MATCH','run_correlated':True,'resource_correlated':True,'baseline_trusted':True,'recovery_verified':True,'allow_control_verdict':None if expectation=='ALLOW' else CaseVerdict.SAFE,'effects':(fact,)}
    return CheckDecisionInput(**{**values,**changes})
