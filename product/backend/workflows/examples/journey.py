# 预设开发演练只读投影：推进依赖同源码、同权限的真实发布结果，不按版本名称推断结论。
from typing import Literal

from product.backend.core.errors import JiejianError
from product.protocols.execution_v3 import WireModel


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


def build_development_journey(current, *, reader, understanding, boundaries, repairs):
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
        # 只消费有界结果窗口，遇到损坏记录不借旧 PASS 掩盖；找不到时保持尚未核对。
        for status in reader.list_for_project(current.project_id):
            if status.run.created_at_us < current.scenario_changed_at_us:
                continue
            if status.result_integrity != "VALID":
                return OfficialDevelopmentJourney(**values, reason="当前检查尚未发布可用结论，请先查看检查进展。")
            package = reader.package(status.run.run_id, project_id=current.project_id)
            if package.request.source_fingerprint != fingerprint or package.request.policy_epoch != epoch:
                continue
            verdict = status.run.verdict.value
            verified = False
            if repairs is not None and current.repair_change_id:
                state = repairs.evaluate(current.project_id)
                linked = [task for task in state.tasks if task.change_id == current.repair_change_id]
                verified = bool(linked) and all(task.status == "VERIFIED" and task.run_id == status.run.run_id for task in linked)
            return OfficialDevelopmentJourney(**values, run_id=status.run.run_id, verdict=verdict,
                can_optimize=not external and current.scenario_version.value == "BASELINE" and verdict == "PASS" and not current.evidence_limited,
                repair_verified=verified, reason="结论仅覆盖本次已核对的源码和权限；后续修改需重新检查。")
    except (JiejianError, OSError):
        return OfficialDevelopmentJourney(**values, reason="当前源码或发布事实暂时无法核对，不能推进预设开发。")
    return OfficialDevelopmentJourney(**values, reason="当前实现尚无对应检查；先确认权限、准备材料并执行检查。")
