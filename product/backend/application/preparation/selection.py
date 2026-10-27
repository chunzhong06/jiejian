# 按当前材料缺口给出准备页入口建议，不推导安全结论或替代提交前预览。
from collections.abc import Sequence
from typing import Literal
from product.backend.application.preparation.models import ActionPreparationView, PreparationStatus

def preparation_recommendation(actions: Sequence[ActionPreparationView]) -> tuple[str | None, Literal['identity','execution','resource','evidence','recovery'] | None]:
    if not actions:
        return None,None
    for action in actions:
        if action.preparation_complete:
            continue
        groups=(
            ('identity',action.identity_requirements.slots),
            ('execution',(action.execution,)),
            ('resource',action.resources),
            ('evidence',action.effect_evidence),
            ('recovery',(action.recovery,)),
        )
        for kind,items in groups:
            if any(item.status not in {PreparationStatus.SATISFIED,PreparationStatus.NOT_REQUIRED} for item in items):
                return action.action_id,kind
        return action.action_id,None
    return actions[0].action_id,None
