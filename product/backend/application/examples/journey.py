# 预设开发演练只读投影：推进依赖同源码、同权限的真实发布结果，不按版本名称推断结论。
import hashlib
import json
from typing import Literal
from pydantic import computed_field
from product.backend.application.examples.preset_delivery import preset_change_id

from product.backend.domain.errors import JiejianError
from product.protocols.checks.execution_request import WireModel


class OfficialChangeOption(WireModel):
    version: Literal['VULNERABLE', 'EXPOSE_REVOKE']
    available: bool
    reason: str | None = None


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
    policy_epoch: int | None = None
    source_fingerprint: str | None = None
    current_change_id: str | None = None
    has_active_tasks: bool = False

    @computed_field
    @property
    def transition_basis(self) -> str:
        """绑定用户刚审阅的项目、源码与结果；写入口仍独立重读并核对。"""
        facts = self.model_dump(mode='json', exclude_computed_fields=True)
        return hashlib.sha256(json.dumps(facts, sort_keys=True, separators=(',', ':')).encode()).hexdigest()

    @computed_field
    @property
    def change_options(self) -> tuple[OfficialChangeOption, ...]:
        blocked = ('先等待或停止当前任务。' if self.has_active_tasks else
                   '源码已由外部修改，请在原开发任务中继续。' if self.implementation == 'CUSTOM' else
                   '当前依据尚未读取完整，请重新读取。' if self.policy_epoch is None else None)
        return tuple(OfficialChangeOption(version=version, available=reason is None, reason=reason)
                     for version, reason in (
                         ('VULNERABLE', blocked or (None if self.can_optimize else '本工作区已进入后续修改，可从修改历史查看此前交付。' if self.implementation != 'BASELINE' else '先完成正常起点的真实检查。')),
                         ('EXPOSE_REVOKE', blocked or (None if self.implementation == 'VULNERABLE' and self.verdict == 'BLOCK' else '先检查内部包限制被移除后的实际结果。')),
                     ))

    @computed_field
    @property
    def stage(self) -> Literal['STATE_UNAVAILABLE', 'REQUIREMENTS', 'BASELINE_CHECK', 'BASELINE_RESULT', 'CHANGED_CHECK', 'CHECK_RESULT', 'CUSTOM']:
        """只说明当前阅读任务；阶段不授权转换，也不决定权限或修复结论。"""
        if self.policy_epoch is None:
            return 'STATE_UNAVAILABLE'
        if self.implementation == 'CUSTOM':
            return 'CUSTOM'
        if self.policy_epoch == 0:
            return 'REQUIREMENTS'
        if self.run_id is None:
            return 'BASELINE_CHECK' if self.implementation == 'BASELINE' else 'CHANGED_CHECK'
        if self.implementation == 'BASELINE' and self.can_optimize:
            return 'BASELINE_RESULT'
        return 'CHECK_RESULT'


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
        values['policy_epoch'] = epoch
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
