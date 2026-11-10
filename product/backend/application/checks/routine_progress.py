"""分项准备只读进展；不构造可绑定资产，也不产生完整材料指纹。"""
from typing import Literal
from product.protocols.checks.execution_request import WireModel


class RoutineRequirementProgress(WireModel):
    kind: Literal['ACCOUNT','RESOURCE','FLOW','PROOF']
    slot: str
    status: Literal['PRESENT','PARTIAL','NEEDS_REVIEW','MISSING','UNKNOWN']
    count: int | None
    minimum_count: int
    reason_codes: tuple[str,...] = ()


def requirement_progress(document, assets, preparation):
    """完整资产优先；局部资源只说明已有配置，不从所有者分组推算资源总数。"""
    values=[]
    for requirement in document.requirements:
        complete=[item for item in assets if item.kind==requirement.kind and item.requirement_slot==requirement.slot]
        if len(complete)>=requirement.minimum_count:
            values.append(RoutineRequirementProgress(kind=requirement.kind,slot=requirement.slot,status='PRESENT',
                count=len(complete),minimum_count=requirement.minimum_count));continue
        if preparation is None:
            values.append(RoutineRequirementProgress(kind=requirement.kind,slot=requirement.slot,status='UNKNOWN',count=None,
                minimum_count=requirement.minimum_count,reason_codes=('PREPARATION_UNAVAILABLE',)));continue
        actions=[item for item in preparation.actions if requirement.action is None or
                 (item.action_id,item.action_revision)==(requirement.action.action_id,requirement.action.revision)]
        slots=[item for action in actions for item in action.identity_requirements.slots if requirement.actor is not None and
               (item.requirement.actor_id,item.requirement.actor_revision)==(requirement.actor.actor_id,requirement.actor.revision)]
        if requirement.kind=='ACCOUNT':
            nodes=slots
            count=len({item.test_identity_id for item in nodes if item.status=='SATISFIED' and item.test_identity_id})
        elif requirement.kind=='FLOW':
            nodes=[item.execution for item in actions]
            count=sum(item.status=='SATISFIED' for item in nodes)
        elif requirement.kind=='PROOF':
            nodes=[item for action in actions for item in action.effect_evidence if item.effect_id==requirement.effect_id]
            count=sum(item.status=='SATISFIED' for item in nodes)
        else:
            owners={item.requirement.slot_id for item in slots}
            nodes=[item for action in actions for item in action.resources if item.owner_slot_id in owners]
            count=None
        ready=any(item.status=='SATISFIED' for item in nodes) if count is None else count>0
        status=('PRESENT' if count is None or count>=requirement.minimum_count else 'PARTIAL') if ready else (
            'NEEDS_REVIEW' if any(item.status in {'STALE','BLOCKED'} for item in nodes) else 'MISSING')
        if ready and count is None and requirement.minimum_count>1:
            status='NEEDS_REVIEW'
        values.append(RoutineRequirementProgress(kind=requirement.kind,slot=requirement.slot,status=status,count=count,
            minimum_count=requirement.minimum_count,reason_codes=tuple(dict.fromkeys(reason for item in nodes for reason in item.reason_codes))))
    return tuple(values)
