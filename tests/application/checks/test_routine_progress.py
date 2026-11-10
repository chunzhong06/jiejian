"""一项缺口不能抹掉其他真实准备事实；分项进展不生成绑定资产。"""
from types import SimpleNamespace as N
import pytest
from product.backend.application.checks.routine_progress import requirement_progress


def view(status='SATISFIED',**values):
    return N(status=status,reason_codes=(),**values)


def test_missing_proof_keeps_accounts_resource_and_flow_present():
    actor=N(actor_id='member',revision=1);action=N(action_id='read',revision=2)
    requirements=[N(kind=kind,slot=kind,actor=actor if kind in {'ACCOUNT','RESOURCE'} else None,
        action=None if kind=='ACCOUNT' else action,effect_id='note',minimum_count=1) for kind in ('ACCOUNT','RESOURCE','FLOW','PROOF')]
    account=view(requirement=N(actor_id='member',actor_revision=1,slot_id='slot'),test_identity_id='identity')
    prepared=N(actions=[N(action_id='read',action_revision=2,identity_requirements=N(slots=[account]),execution=view(),
        resources=[view(owner_slot_id='slot')],effect_evidence=[view('NEEDS_USER',effect_id='note')])])
    progress=requirement_progress(N(requirements=requirements),[],prepared)
    assert [item.status for item in progress]==['PRESENT','PRESENT','PRESENT','MISSING']
    assert [item.count for item in progress]==[1,None,1,0]
    requirements[1].minimum_count=2
    assert requirement_progress(N(requirements=requirements),[],prepared)[1].status=='NEEDS_REVIEW'
    # 分项模型没有可供绑定或执行复用的材料指纹。
    assert all('fingerprint' not in item.model_dump() for item in progress)
    requirements[0].minimum_count=2
    assert requirement_progress(N(requirements=requirements),[],prepared)[0].status=='PARTIAL'
    account.requirement.actor_revision=2
    assert requirement_progress(N(requirements=requirements),[],prepared)[0].status=='MISSING'


def test_unreadable_preparation_is_unknown_and_complete_assets_still_retained():
    requirement=N(kind='FLOW',slot='read',minimum_count=1)
    document=N(requirements=[requirement])
    assert requirement_progress(document,[],None)[0].status=='UNKNOWN'
    asset=N(kind='FLOW',requirement_slot='read')
    assert requirement_progress(document,[asset],None)[0].status=='PRESENT'


pytestmark=[pytest.mark.level3]
