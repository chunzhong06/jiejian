"""将登记时的影响与当前材料并列；历史影响记录不随当前就绪状态改写。"""
from typing import Literal
from product.backend.application.preparation.models import MaterialImpactView
from product.protocols.checks.execution_request import WireModel, PermissionReference, content_hash


class ChangedRequirement(WireModel):
    permission: PermissionReference
    current: PermissionReference | None
    status: Literal['CURRENT', 'CHANGED', 'REMOVED']
    action_id: str
    action_label: str
    classification: Literal['DIRECTLY_AFFECTED', 'MAPPING_REVIEW_REQUIRED', 'NO_DIRECT_EVIDENCE']
    relevant_paths: tuple[str, ...]


class ChangeContinuation(WireModel):
    fingerprint: str
    plan_fingerprint: str | None
    requirements: tuple[ChangedRequirement, ...]
    added_requirements: tuple[PermissionReference, ...]
    materials: tuple[MaterialImpactView, ...]
    next_step: str
    scope: str = '登记时的源码影响与当前准备分别列示；没有直接映射的要求继续保留在检查范围。'


def change_continuation(assessment, current_refs, preview, action_labels):
    current = {item.intent_id: item for item in current_refs}
    requirements = tuple(ChangedRequirement(permission=rule, current=current.get(rule.intent_id),
        status='REMOVED' if rule.intent_id not in current else 'CURRENT' if rule == current[rule.intent_id] else 'CHANGED',
        action_id=action.action_id, action_label=action_labels.get(action.action_id, '登记时的业务操作'),
        classification=action.classification, relevant_paths=action.relevant_paths)
        for action in assessment.payload.action_impacts for rule in action.permission_refs)
    old = {item.intent_id for item in assessment.payload.permission_refs}
    added = tuple(item for item in current_refs if item.intent_id not in old)
    preparation = None if preview is None else preview.preparation_work
    materials = () if preparation is None else preparation.impacts
    changed = any(item.status != 'CURRENT' for item in requirements)
    next_step = ('关联业务标准已变化，先审阅新要求和验证方式，再安排继任检查；原题结果保留。' if changed else
        '原要求仍一致。核对受影响材料和运行交付后，继续原题与正常功能检查。')
    values = dict(plan_fingerprint=None if preview is None else preview.plan_fingerprint,
        requirements=requirements, added_requirements=added, materials=materials, next_step=next_step)
    hashed = dict(values, requirements=[item.model_dump(mode='json') for item in requirements],
        added_requirements=[item.model_dump(mode='json') for item in added],
        materials=[item.model_dump(mode='json') for item in materials])
    return ChangeContinuation(**values, fingerprint=content_hash('ChangeContinuation', hashed))
