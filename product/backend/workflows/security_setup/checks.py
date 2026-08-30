# =============================================================================
# 普通用户检查预览与提交
#
# 定位
#   PermissionIntent 准备事实与唯一 ExecutionWorkflow 之间的普通控制面应用服务。
#
# 职责
#   投影人话 CheckPreview｜定位最早缺口｜冻结可选变化/修复上下文｜无 Profile 参数提交当前 Generated Profile
#
# 边界
#   不生成 Case、不决定 Verdict、不执行目标；Coverage 与差分事实只读取冻结请求。
#
# 调用链
#   StartCheck API → CheckWorkflow → SecuritySetupCompiler / ExecutionWorkflow
# =============================================================================

from __future__ import annotations

from collections.abc import Mapping
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.core.verification.permissions import PermissionExpectation
from product.backend.workflows.permission_intents import (
    PermissionIntentCellStatus,
    PermissionIntentService,
)
from product.backend.workflows.runs.execution import ExecutionWorkflow
from product.backend.workflows.results.repair import RepairContractService
from product.backend.workflows.security_setup.compiler import SecuritySetupCompiler
from product.backend.workflows.source_changes import SourceChangeService
from product.backend.core.source_changes import RevalidationPlan
from product.protocols.execution_request import (
    ChangeVerificationContext,
    RepairVerificationContext,
)


class _CheckModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        strict=True,
        hide_input_in_errors=True,
    )


class CheckPreviewGap(_CheckModel):
    code: str = Field(min_length=1, max_length=96)
    message: str = Field(min_length=1, max_length=160)
    next_path: Literal["/application", "/identities", "/flows", "/check"]
    next_label: str = Field(min_length=1, max_length=32)


class CheckPreviewItem(_CheckModel):
    subject_label: str
    subject_role_display_name: str
    relation: str
    expectation: PermissionExpectation | None = None
    ready: bool
    gaps: tuple[CheckPreviewGap, ...] = ()


class CheckPreviewAction(_CheckModel):
    action_candidate_id: str
    action_display_name: str
    resource_logical_name: str | None = None
    ready: bool
    checks: tuple[CheckPreviewItem, ...] = ()
    gaps: tuple[CheckPreviewGap, ...] = ()


class CheckPreview(_CheckModel):
    project_id: str
    ready: bool
    actions: tuple[CheckPreviewAction, ...]
    gaps: tuple[CheckPreviewGap, ...]
    next_path: str | None = None
    next_label: str | None = None
    case_count: int = Field(ge=0)
    differential_pair_count: int = Field(ge=0)
    change_id: str | None = Field(default=None, pattern=r"^chg_[0-9a-f]{32}$")
    required_intent_count: int = Field(default=0, ge=0)


class CheckWorkflow:
    """实时读取当前计划，并把普通提交收敛到唯一 Generated Profile。"""

    def __init__(
        self,
        *,
        permission_intents: PermissionIntentService,
        security_setup: SecuritySetupCompiler,
        execution: ExecutionWorkflow,
        source_changes: SourceChangeService,
        repair_contracts: RepairContractService,
    ) -> None:
        self._permission_intents = permission_intents
        self._security_setup = security_setup
        self._execution = execution
        self._source_changes = source_changes
        self._repair_contracts = repair_contracts

    def prepare(self, project_id: str, *, change_id: str | None = None) -> CheckPreview:
        """先关闭变化重验前置缺口，再编译同一份完整当前检查计划。"""

        revalidation = self._revalidation(project_id, change_id)
        self._security_setup.compile(project_id)
        return self._preview(project_id, revalidation)

    def preview(self, project_id: str, *, change_id: str | None = None) -> CheckPreview:
        """投影当前矩阵、Coverage 和 DifferentialPlan；不持久化派生状态。"""

        return self._preview(project_id, self._revalidation(project_id, change_id))

    def _preview(
        self,
        project_id: str,
        revalidation: RevalidationPlan | None,
    ) -> CheckPreview:
        matrix = self._permission_intents.matrix(project_id)
        repair_context = self._repair_context(project_id, revalidation)
        profile_id = self._security_setup.current_generated_profile_id(project_id)
        snapshot = None
        profile_gap: CheckPreviewGap | None = None
        if profile_id is None:
            profile_gap = _gap("GENERATED_PROFILE_MISSING")
        else:
            try:
                snapshot = self._execution.build_request(
                    profile_id,
                    project_id=project_id,
                    change_context=self._change_context(revalidation),
                    repair_context=repair_context,
                ).project_snapshot
            except JiejianError:
                profile_gap = _gap("GENERATED_PROFILE_STALE")

        cases = () if snapshot is None else snapshot.plan.cases
        plan_gaps_by_action: dict[str, list[CheckPreviewGap]] = {}
        differential_gap_by_case: dict[str, object] = {}
        paired_deny_case_ids: set[str] = set()
        if snapshot is not None:
            action_by_rule = {
                rule.rule_id: rule.action_id for rule in snapshot.contract.rules
            }
            for gap in snapshot.plan.gaps:
                action_id = action_by_rule.get(gap.rule_id)
                if action_id is not None:
                    plan_gaps_by_action.setdefault(action_id, []).append(
                        _gap(gap.code.value)
                    )
            differential_gap_by_case = {
                item.deny_case_id: item for item in snapshot.differential_plan.gaps
            }
            paired_deny_case_ids = {
                twin.deny_case.case_id for twin in snapshot.differential_plan.twins
            }

        actions: list[CheckPreviewAction] = []
        for action in matrix.actions:
            action_gaps = [
                *(_gap(code) for code in action.gaps),
                *plan_gaps_by_action.get(action.action_candidate_id, ()),
            ]
            checks: list[CheckPreviewItem] = []
            runnable_gaps: list[CheckPreviewGap] = []
            for cell in action.cells:
                cell_gaps: list[CheckPreviewGap] = []
                if cell.status is not PermissionIntentCellStatus.CURRENT:
                    cell_gaps.extend(
                        _gap(code)
                        for code in (
                            cell.review_reasons
                            or ("PERMISSION_INTENT_UNCONFIRMED",)
                        )
                    )
                if (
                    cell.status is PermissionIntentCellStatus.CURRENT
                    and cell.execution_gap is not None
                ):
                    cell_gaps.append(_gap(cell.execution_gap))
                matching_cases = tuple(
                    case
                    for case in cases
                    if case.action_id == action.action_candidate_id
                    and case.subject_id == cell.representative_test_identity_id
                    and all(value is cell.expectation for value in case.expectations)
                )
                if (
                    snapshot is not None
                    and cell.status is PermissionIntentCellStatus.CURRENT
                    and cell.execution_gap is None
                ):
                    if not matching_cases:
                        cell_gaps.append(_gap("COVERAGE_RECORD_MISSING"))
                    if cell.expectation is PermissionExpectation.DENY:
                        deny_case_ids = {
                            case.case_id for case in matching_cases
                        }
                        for case_id in sorted(deny_case_ids):
                            differential_gap = differential_gap_by_case.get(case_id)
                            if differential_gap is not None:
                                cell_gaps.append(
                                    _gap(
                                        f"DIFFERENTIAL_{differential_gap.code.value}",
                                        message=differential_gap.detail,
                                    )
                                )
                        if deny_case_ids and not (
                            deny_case_ids & paired_deny_case_ids
                        ) and not any(
                            case_id in differential_gap_by_case
                            for case_id in deny_case_ids
                        ):
                            cell_gaps.append(_gap("DIFFERENTIAL_PAIR_MISSING"))
                elif (
                    profile_gap is not None
                    and cell.status is PermissionIntentCellStatus.CURRENT
                    and cell.execution_gap is None
                ):
                    cell_gaps.append(profile_gap)
                if (
                    cell.status is PermissionIntentCellStatus.CURRENT
                    and cell.execution_gap is None
                ):
                    runnable_gaps.extend(cell_gaps)
                checks.append(
                    CheckPreviewItem(
                        subject_label=f"{cell.subject_role_display_name}权限组",
                        subject_role_display_name=cell.subject_role_display_name,
                        relation=cell.relation.value,
                        expectation=cell.expectation,
                        ready=not cell_gaps,
                        gaps=_unique_gaps(cell_gaps),
                    )
                )
            combined = _unique_gaps(
                [*action_gaps, *(gap for item in checks for gap in item.gaps)]
            )
            actions.append(
                CheckPreviewAction(
                    action_candidate_id=action.action_candidate_id,
                    action_display_name=action.action_display_name,
                    resource_logical_name=action.resource_logical_name,
                    ready=(
                        bool(checks)
                        and action.compilable
                        and profile_gap is None
                        and not plan_gaps_by_action.get(action.action_candidate_id)
                        and not runnable_gaps
                    ),
                    checks=tuple(checks),
                    gaps=combined,
                )
            )

        global_gaps = _unique_gaps(
            [
                *(gap for action in actions for gap in action.gaps),
                *(() if actions else (_gap("ACTION_MISSING"),)),
                *(() if profile_gap is None else (profile_gap,)),
            ]
        )
        # Generated Profile 可以只覆盖当前完整子集；其他已确认动作保留缺口展示，
        # 不能反向阻止已经具备真实 Coverage 与差分计划的动作执行。
        ready = profile_gap is None and any(action.ready for action in actions)
        first_gap = min(global_gaps, key=_gap_order) if global_gaps else None
        return CheckPreview(
            project_id=project_id,
            ready=ready,
            actions=tuple(actions),
            gaps=global_gaps,
            next_path=first_gap.next_path if first_gap else None,
            next_label=first_gap.next_label if first_gap else None,
            case_count=0 if snapshot is None else len(snapshot.plan.cases),
            differential_pair_count=(
                0 if snapshot is None else len(snapshot.differential_plan.twins)
            ),
            change_id=None if revalidation is None else revalidation.change_id,
            required_intent_count=(
                0 if revalidation is None else len(revalidation.required_intent_ids)
            ),
        )

    def submit(
        self,
        project_id: str,
        *,
        idempotency_key: str,
        change_id: str | None = None,
    ):
        """至少一个动作完整时解析当前 Generated Profile，并复用现有执行提交链。"""

        revalidation = self._revalidation(project_id, change_id)
        preview = self._preview(project_id, revalidation)
        if not preview.ready:
            raise JiejianError(
                ErrorCode.STATE_PRECONDITION,
                "检查准备尚未完成，请先处理页面显示的覆盖缺口",
                details={
                    "next_path": preview.next_path,
                    "gap_codes": tuple(item.code for item in preview.gaps),
                },
            )
        profile_id = self._security_setup.current_generated_profile_id(project_id)
        if profile_id is None:
            raise JiejianError(
                ErrorCode.EXECUTION_PROFILE_SOURCE_DRIFT,
                "当前检查配置已经失效，请重新生成",
            )
        return self._execution.submit(
            profile_id,
            project_id=project_id,
            change_context=self._change_context(revalidation),
            repair_context=self._repair_context(project_id, revalidation),
            idempotency_key=idempotency_key,
        )

    def _revalidation(
        self,
        project_id: str,
        change_id: str | None,
    ) -> RevalidationPlan | None:
        return (
            None
            if change_id is None
            else self._source_changes.revalidation_plan(project_id, change_id)
        )

    @staticmethod
    def _change_context(
        revalidation: RevalidationPlan | None,
    ) -> ChangeVerificationContext | None:
        if revalidation is None:
            return None
        return ChangeVerificationContext(
            change_id=revalidation.change_id,
            impact_fingerprint=revalidation.impact_fingerprint,
            required_intent_ids=revalidation.required_intent_ids,
            source_fingerprint=revalidation.source_fingerprint,
        )

    def _repair_context(
        self,
        project_id: str,
        revalidation: RevalidationPlan | None,
    ) -> RepairVerificationContext | None:
        if revalidation is None or revalidation.repair_reference is None:
            return None
        return self._repair_contracts.context(
            project_id,
            revalidation.repair_reference,
            self._permission_intents.policy_snapshot(project_id),
        )


_GAP_PRESENTATION: Mapping[str, tuple[str, str, str]] = {
    "ACTION_MISSING": ("还没有已确认的业务动作", "/application", "去应用接入"),
    "TEST_IDENTITY_MISSING": ("缺少完成差分所需的测试账号", "/identities", "去准备测试账号"),
    "TEST_IDENTITY_NOT_PREPARED": ("测试账号的登录状态尚未准备", "/identities", "去准备测试账号"),
    "MISSING_SUBJECT": ("差分检查所需测试账号不可用", "/identities", "去准备测试账号"),
    "ACTION_FLOW_OR_RESOURCE_MISSING": ("尚未录制并确认这个业务动作", "/flows", "去准备业务流程"),
    "ACTION_SAFETY_SETUP_STALE": ("业务动作准备信息已经变化", "/flows", "去重新确认业务流程"),
    "RESOURCE_OWNER_ROLE_UNCONFIRMED": ("资源所有者权限组尚未确认", "/application", "去确认权限组"),
    "TEST_RESOURCE_UNCONFIRMED": ("测试资源尚未确认", "/flows", "去确认测试资源"),
    "OBSERVATION_UNCONFIRMED": ("可信观察方式尚未确认", "/flows", "去确认观察方式"),
    "RECOVERY_UNCONFIRMED": ("安全恢复方式尚未确认", "/flows", "去确认恢复方式"),
    "SECURITY_EFFECT_UNCONFIRMED": ("真实安全影响尚未确认", "/flows", "去确认真实影响"),
    "MISSING_RESOURCE": ("差分检查所需测试资源不可用", "/flows", "去确认测试资源"),
    "MISSING_OBSERVER": ("差分检查缺少可信观察方式", "/flows", "去确认观察方式"),
    "ALLOW_INTENT_MISSING": ("缺少一个可执行的允许权限组", "/check", "去确认权限规则"),
    "DENY_INTENT_MISSING": ("缺少一个可执行的拒绝权限组", "/check", "去确认权限规则"),
    "PERMISSION_INTENT_UNCONFIRMED": ("权限期望尚未确认", "/check", "去确认权限规则"),
    "PERMISSION_INTENT_STALE": ("权限期望依赖的事实已经变化", "/check", "去重新确认权限规则"),
    "PERMISSION_INTENT_NEEDS_REVIEW": ("已有权限期望需要重新确认", "/check", "去重新确认权限规则"),
    "GENERATED_PROFILE_MISSING": ("尚未生成当前检查配置", "/check", "去生成检查配置"),
    "GENERATED_PROFILE_STALE": ("当前检查配置已经失效", "/check", "去重新生成检查配置"),
    "COVERAGE_RECORD_MISSING": ("当前权限要求没有形成可执行用例", "/check", "去检查权限规则"),
    "COVERAGE_GAP": ("当前权限要求仍有覆盖缺口", "/check", "去检查权限规则"),
    "RELATION_UNPROVABLE": ("当前账号与资源关系无法证明", "/check", "去检查权限规则"),
    "BUDGET_EXCEEDED": ("检查用例超过当前安全预算", "/check", "去检查权限规则"),
    "RELATION_DEPTH_EXCEEDED": ("权限关系路径超过当前安全深度", "/check", "去检查权限规则"),
    "DIFFERENTIAL_PAIR_MISSING": ("拒绝用例缺少可比较的允许控制", "/check", "去检查权限规则"),
}


def _gap(code: str, *, message: str | None = None) -> CheckPreviewGap:
    clean_code = code.removeprefix("CoverageGapCode.")
    presentation = _GAP_PRESENTATION.get(
        clean_code,
        (message or "当前检查仍有未解决的覆盖缺口", "/check", "去检查权限规则"),
    )
    return CheckPreviewGap(
        code=clean_code,
        message=message or presentation[0],
        next_path=presentation[1],
        next_label=presentation[2],
    )


def _unique_gaps(gaps: list[CheckPreviewGap]) -> tuple[CheckPreviewGap, ...]:
    return tuple({item.code: item for item in gaps}.values())


def _gap_order(gap: CheckPreviewGap) -> tuple[int, str]:
    rank = {
        "/application": 0,
        "/identities": 1,
        "/flows": 2,
        "/check": 3,
    }
    return rank[gap.next_path], gap.code


__all__ = [
    "CheckPreview",
    "CheckPreviewAction",
    "CheckPreviewGap",
    "CheckPreviewItem",
    "CheckWorkflow",
]
