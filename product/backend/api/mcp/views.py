# 将业务事实投影为 Agent 可读的有限视图；不导出源码、秘密或重新计算结论。
from __future__ import annotations
from typing import Any
from pydantic import BaseModel

def _json(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, tuple | list):
        return [_json(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _json(item) for key, item in value.items()}
    return value

def _understanding_view(value: BaseModel) -> dict[str, Any]:
    payload = value.model_dump(mode="json")
    for field in ("source_root", "source_fingerprint", "endpoint_source_fingerprint"):
        payload.pop(field, None)
    for field in ("role_candidates", "action_candidates"):
        for candidate in payload.get(field, []):
            candidate.pop("evidence", None)
    return payload

def _current_change_view(value):
    """Agent 仅看到相对路径与业务影响，不得到源码、快照或配置指纹。"""
    return dict(project_id=value.manifest.project_id,change_id=value.manifest.change_id,reason=value.manifest.reason,
        submitted_by=value.manifest.submitted_by,claimed_paths=list(value.manifest.claimed_paths),
        registration_status="RECORDED", repair_reference=_json(value.manifest.repair_reference),
        comparison_status=value.change_set.status,
        receipt_boundary="登记回执只确认本批修改已记录，不确认修复成功；无需让用户重复登记。",
        added_paths=list(value.change_set.added_paths),modified_paths=list(value.change_set.modified_paths),
        removed_paths=list(value.change_set.removed_paths),revalidation=_json(value.revalidation),
        action_impacts=[dict(action_id=item.action_id,action_revision=item.action_revision,classification=item.classification,
            permission_ids=[ref.intent_id for ref in item.permission_refs],relevant_paths=list(item.relevant_paths))
            for item in value.assessment.payload.action_impacts])

def _current_run_view(value):
    return dict(run_id=value.run.run_id,project_id=value.run.project_id,lifecycle=value.run.lifecycle,
        verdict=value.run.verdict,result_integrity=value.result_integrity,job=_json(value.job),progress=_json(value.progress))

def _current_repair_view(contract):
    from product.backend.workflows.checks.repairs.repair_text import REPAIR_REQUIREMENTS
    return dict(reference=_json(contract.reference()),requirements=dict(REPAIR_REQUIREMENTS),
        permission=_json(contract.deny.identity.permission),resource_id=contract.deny.identity.resource_id,
        resource_owner_test_identity_id=contract.deny.identity.resource_owner_test_identity_id,
        must_disappear=list(contract.deny.identity.protected_effect_ids),evidence_refs=list(contract.deny.evidence_refs),
        selected_allow_permission=_json(contract.selected_control.identity.permission),
        must_preserve=[dict(role=role,source_case_id=item.source_case_id,
            action_id=item.identity.action_id,protected_effect_ids=list(item.identity.protected_effect_ids))
            for role,item in (("SELECTED_ALLOW",contract.selected_control),
                             *(("REGRESSION",row) for row in contract.regressions))],
        regression_count=len(contract.regressions))

def _current_story_view(story):
    return dict(run_id=story.run_id,project_id=story.project_id,verdict=story.verdict,judgement=story.judgement,
        runtime_status=story.runtime_status,runtime_instance_id=story.runtime_instance_id,
        actions=[dict(case_id=item.case_id,display_name=item.display_name,judgement=item.judgement,
            permission_expectation=item.permission.expectation,fact_comparison=_json(item.fact_comparison),
            breakpoint=None if item.breakpoint is None else dict(breakpoint_type=item.breakpoint.breakpoint_type,precision=item.breakpoint.precision),
            repair_requirement=None if item.repair_requirement is None else _current_repair_view(item.repair_requirement),
            claim_boundary=list(item.claim_boundary)) for item in story.actions],repair_verification=_json(story.repair_verification))
