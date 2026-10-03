# 预设开发演练只读投影：推进依赖同源码、同权限的真实发布结果，不按版本名称推断结论。
from typing import Literal
from .preset_delivery import preset_change_id

from product.backend.core.errors import JiejianError
from product.protocols.checks.execution_request import WireModel


class OfficialDevelopmentJourney(WireModel):
    project_id: str
    implementation: str
    delivery_source: Literal["PRESET_DEMONSTRATION", "EXTERNAL_CODE"] = "PRESET_DEMONSTRATION"
    run_id: str | None = None
    verdict: Literal["PASS", "BLOCK", "INCONCLUSIVE"] | None = None
    repair_verified: bool = False
    can_optimize: bool = False
    evidence_limited: bool = False
    reason: str


def build_development_journey(current, *, reader, understanding, boundaries, repairs, development=None):
    values = dict(project_id=current.project_id, implementation=current.scenario_version.value,
                  evidence_limited=current.evidence_limited)
    if reader is None:
        return OfficialDevelopmentJourney(**values, reason="先完成当前实现的独立检查。")
    try:
        fingerprint = understanding.inspect_source_fingerprint(current.project_id)
        external = current.preset_source_fingerprint is not None and fingerprint != current.preset_source_fingerprint
        if external:
            values["implementation"] = "CUSTOM"
            values["delivery_source"] = "EXTERNAL_CODE"
        epoch = boundaries.view(current.project_id).policy_epoch
        records = reader.list_for_project(current.project_id)
        repair_change = current.repair_change_id
        if not external and current.scenario_version.value != "BASELINE" and development is not None:
            change_id = preset_change_id(development, current, current.scenario_version.value)
            details = None if change_id is None else development.delivery_details(current.project_id, change_id)
            verification = None if details is None else details["verification"]
            if verification is None or verification["run_id"] is None:
                return OfficialDevelopmentJourney(**values, reason="这批交付尚无关联检查；请从本批交付继续准备与验证。")
            # 相同源码的其它检查不替代本批验收；精确关联也不能越过观察条件变更。
            records = [reader.status(verification["run_id"], project_id=current.project_id)]
            if current.scenario_version.value == "FIXED":
                repair_change = change_id
        # 只消费有界结果窗口，遇到损坏记录不借旧 PASS 掩盖；找不到时保持尚未核对。
        for status in records:
            if status.run.created_at_us < current.scenario_changed_at_us:
                continue
            if status.result_integrity != "VALID":
                return OfficialDevelopmentJourney(**values, reason="当前检查尚未发布可用结论，请先查看检查进展。")
            package = reader.package(status.run.run_id, project_id=current.project_id)
            if package.request.source_fingerprint != fingerprint or package.request.policy_epoch != epoch:
                continue
            verdict = status.run.verdict.value
            verified = False
            if repairs is not None and repair_change:
                state = repairs.evaluate(current.project_id)
                linked = [task for task in state.tasks if task.change_id == repair_change]
                verified = bool(linked) and all(task.status == "VERIFIED" and task.run_id == status.run.run_id for task in linked)
            return OfficialDevelopmentJourney(**values, run_id=status.run.run_id, verdict=verdict,
                can_optimize=not external and current.scenario_version.value == "BASELINE" and verdict == "PASS" and not current.evidence_limited,
                repair_verified=verified, reason="结论仅覆盖本次已核对的源码和权限；后续修改需重新检查。")
    except (JiejianError, OSError):
        return OfficialDevelopmentJourney(**values, reason="当前源码或发布事实暂时无法核对，不能推进预设开发。")
    return OfficialDevelopmentJourney(**values, reason="当前实现尚无对应检查；先确认权限、准备材料并执行检查。")
