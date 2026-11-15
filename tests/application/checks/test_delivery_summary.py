"""交付项保留历史身份与具名处理入口，不使用当前名称冒充历史。"""
from types import SimpleNamespace as NS
from product.backend.application.checks.reading.delivery import delivery_items, historical_permission_labels
from product.protocols.checks.execution_request import PermissionReference


def test_omitted_requirement_keeps_exact_reference_and_missing_history_explicit():
    ref=PermissionReference(intent_id='pin_'+'a'*32,revision=2,intent_hash='b'*64)
    story=NS(actions=(),repair_reviews=(),selection=NS(omitted=(ref,),uncovered_requirements=(),pending_review_ids=()),
        requirement_scope=(),discovery_coverage=None,runtime_status='UNSUPPORTED')
    item=delivery_items(story)[0]
    assert item.permission==ref and item.historical_name_available is False
    assert '历史' in item.label and 'revision=2' in item.review_url and ref.intent_hash in item.review_url
    named=delivery_items(story,{(ref.intent_id,ref.revision,ref.intent_hash):'申请人不得读取他人凭单'})[0]
    assert named.historical_name_available and named.label=='申请人不得读取他人凭单'


def test_discovery_delivery_links_to_the_frozen_source_identity():
    story=NS(actions=(),repair_reviews=(),selection=None,requirement_scope=(),runtime_status='UNSUPPORTED',
        discovery_coverage=NS(items=(NS(key='ACTION:original',label='申请审批',status='PENDING',kind='ACTION',
            candidate_id='original',source_id=None,request_id=None),),omitted_count=0))
    item=delivery_items(story)[0]
    assert item.source_key=='ACTION:original' and 'candidate_id=original' in item.review_url


def test_history_resolver_uses_exact_revision_and_rejects_wrong_hash():
    ref=PermissionReference(intent_id='pin_'+'a'*32,revision=2,intent_hash='b'*64)
    rule=NS(project_id='app',intent_hash=ref.intent_hash,subject_actor_id='member',subject_actor_revision=1,
        resource_owner_actor_id='owner',resource_owner_actor_revision=1,business_action_id='read',action_revision=1,
        relation='OTHER_ROLE',expectation='DENY',conditions=NS(resource_states=('WAITING',)))
    calls=[]
    def revision(key,version):
        calls.append((key,version));return rule
    work=NS(permission_intents=NS(get_revision=revision),business_boundaries=NS(
        actor_revision=lambda key,version:NS(display_name={'member':'申请人','owner':'负责人'}[key]),
        action_revision=lambda key,version:NS(display_name='读取凭单',primary_resource_concept='凭单')))
    labels=historical_permission_labels(work,'app',(ref,))
    assert '申请人' in labels[ref.intent_id,2,ref.intent_hash] and 'WAITING' in next(iter(labels.values()))
    assert calls==[(ref.intent_id,2)]
    wrong=ref.model_copy(update={'intent_hash':'c'*64})
    assert historical_permission_labels(work,'app',(wrong,))=={}


def test_uncovered_scope_opens_frozen_candidate_and_unknown_issue_has_no_misleading_link():
    story=NS(actions=(),repair_reviews=(),runtime_status='UNSUPPORTED',discovery_coverage=None,
        selection=NS(omitted=(),uncovered_requirements=('original@3/req',),pending_review_ids=('bri_unknown',)),
        requirement_scope=(NS(candidate_id='original',revision=3,requirements=(NS(requirement_id='req',requirement='待领取凭单'),)),))
    uncovered,unresolved,_=delivery_items(story)
    assert uncovered.label=='待领取凭单' and 'candidate_id=original' in uncovered.review_url and 'revision=3' in uncovered.review_url
    assert unresolved.source_key=='bri_unknown' and unresolved.review_url is None
    assert unresolved.historical_name_available is False and '历史审阅对象未保存' in unresolved.result
