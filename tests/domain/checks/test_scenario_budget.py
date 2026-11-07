"""场景增加节点时，恢复份额也必须随之增长；不能沿用固定八次。"""
from types import SimpleNamespace as NS

from product.backend.domain.checks.scenarios import scenario_http_budget


def test_conditioned_multi_node_budget_includes_reverse_recovery_and_source_identities():
    proof=NS(binding_fingerprint='binding',observer_id='json_source',observation_identity_id='reader',auxiliary_sources=())
    config=NS(action_id='action',proofs=(proof,),created_resource=None,state_changing=True,steps=(NS(),))
    case=NS(subject_test_identity_id='owner',resource_owner_test_identity_id='owner',
        proof_requirements=(NS(binding_fingerprint='binding'),),permission=NS(conditions=NS()))
    plan=NS(scenario=NS(document=NS(experiments=(NS(invocations=(NS(batch=None),)),))),actions=(NS(action_id='action',cases=(case,)*5),))
    bundle=NS(actions=(config,),proof_sources=(NS(source_id='psr_source',config=NS()),))
    normal,recovery=scenario_http_budget(plan,bundle)
    assert recovery==20 and normal+recovery>64
    # 同一人兼任所有者不重复计数，独立观察账号仍有自己的核验请求。
    proof.observation_identity_id='owner'
    reduced=scenario_http_budget(plan,bundle)
    assert reduced[0]<normal and reduced[1]<recovery


def test_batch_or_unrecognized_source_does_not_claim_a_complete_cost_estimate():
    plan=NS(scenario=NS(document=NS(experiments=(NS(invocations=(NS(batch=NS()),)),))))
    assert scenario_http_budget(plan,NS()) is None
