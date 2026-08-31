# 确定性汇总权限考题的现有准备事实，并只执行冻结白名单中的机械动作。

from __future__ import annotations

from collections.abc import Callable
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from product.backend.core.application_understanding import CandidateDecision
from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.core.permission_intent import PermissionIntentRelation
from product.backend.infra.storage import StorageUnitOfWork
from product.backend.workflows.permission_intents import PermissionIntentCellStatus
from product.backend.workflows.recording.safety_setup import (
    ActionSafetyAssetKind,
    ActionSafetyAssetStatus,
)
from product.backend.workflows.source_changes import SourceRevalidationInspectionStatus
from product.backend.workflows.test_identities import TestIdentityStatus


class PreparationItemKind(StrEnum):
    IDENTITY = "IDENTITY"
    FLOW = "FLOW"
    RESOURCE = "RESOURCE"
    OBSERVATION = "OBSERVATION"
    RECOVERY = "RECOVERY"
    EFFECT = "EFFECT"
    PROFILE = "PROFILE"


class PreparationItemStatus(StrEnum):
    READY = "READY"
    AUTO = "AUTO"
    USER = "USER"
    BLOCKED = "BLOCKED"


class PreparationAutoAction(StrEnum):
    ENSURE_IDENTITY_RECORD = "ENSURE_IDENTITY_RECORD"
    BUILD_CURRENT_PROFILE = "BUILD_CURRENT_PROFILE"


PreparationPath = Literal[
    "/application",
    "/changes",
    "/permissions",
    "/preparation",
    "/identities",
    "/flows",
    "/validation",
]


class _PreparationModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        strict=True,
        hide_input_in_errors=True,
    )


class PreparationItemView(_PreparationModel):
    key: str = Field(min_length=1, max_length=256)
    kind: PreparationItemKind
    label: str = Field(min_length=1, max_length=160)
    status: PreparationItemStatus
    description: str = Field(min_length=1, max_length=320)
    next_path: PreparationPath | None = None
    next_label: str | None = Field(default=None, min_length=1, max_length=80)
    reason_codes: tuple[str, ...] = Field(default=(), max_length=32)
    auto_action: PreparationAutoAction | None = None
    role_candidate_id: str | None = None
    action_candidate_id: str | None = None
    recording_id: str | None = None
    identity_id: str | None = None
    owner_test_identity_id: str | None = None


class PreparationExternalBlockerView(_PreparationModel):
    key: str = Field(min_length=1, max_length=128)
    category: Literal["APPLICATION", "PERMISSION", "SOURCE_CHANGE"]
    label: str = Field(min_length=1, max_length=120)
    description: str = Field(min_length=1, max_length=320)
    next_path: PreparationPath
    next_label: str = Field(min_length=1, max_length=80)
    reason_codes: tuple[str, ...] = Field(default=(), max_length=32)


class ProjectPreparationView(_PreparationModel):
    project_id: str = Field(min_length=1, max_length=64)
    ready: bool
    items: tuple[PreparationItemView, ...]
    next_item_key: str | None = Field(default=None, max_length=256)
    auto_action_count: int = Field(ge=0)
    user_action_count: int = Field(ge=0)
    blocked_count: int = Field(ge=0)
    external_blockers: tuple[PreparationExternalBlockerView, ...]


_KIND_ORDER = {
    kind: index
    for index, kind in enumerate(
        (
            PreparationItemKind.IDENTITY,
            PreparationItemKind.FLOW,
            PreparationItemKind.RESOURCE,
            PreparationItemKind.OBSERVATION,
            PreparationItemKind.RECOVERY,
            PreparationItemKind.EFFECT,
            PreparationItemKind.PROFILE,
        )
    )
}

_PREPARATION_GAPS = frozenset(
    {
        "TEST_IDENTITY_MISSING",
        "TEST_IDENTITY_NOT_PREPARED",
        "MISSING_SUBJECT",
        "ACTION_FLOW_OR_RESOURCE_MISSING",
        "ACTION_SAFETY_SETUP_STALE",
        "ACTION_SAFETY_SETUP_MISSING",
        "TEST_RESOURCE_UNCONFIRMED",
        "MISSING_RESOURCE",
        "RELATION_UNPROVABLE",
        "OBSERVATION_UNCONFIRMED",
        "MISSING_OBSERVER",
        "RECOVERY_UNCONFIRMED",
        "SECURITY_EFFECT_UNCONFIRMED",
        "GENERATED_PROFILE_MISSING",
        "GENERATED_PROFILE_STALE",
    }
)

_APPLICATION_GAPS = frozenset(
    {
        "ACTION_MISSING",
        "RESOURCE_OWNER_ROLE_UNCONFIRMED",
        "ACTION_CANDIDATE_STALE",
        "SUBJECT_ROLE_CANDIDATE_STALE",
        "OWNER_ROLE_CANDIDATE_STALE",
    }
)


class ProjectPreparationService:
    """每次从现有事实重算准备状态；写入口只执行两个显式白名单动作。"""

    def __init__(
        self,
        uow_factory: Callable[..., StorageUnitOfWork],
        *,
        test_identities,
        permission_intents,
        action_safety_setup,
        checks,
        source_changes=None,
    ) -> None:
        self._uow_factory = uow_factory
        self._test_identities = test_identities
        self._permission_intents = permission_intents
        self._action_safety_setup = action_safety_setup
        self._checks = checks
        self._source_changes = source_changes

    def status(self, project_id: str) -> ProjectPreparationView:
        """只读投影当前准备事实，不保存计划、进度或页面状态。"""

        with self._uow_factory() as work:
            project = work.projects.get(project_id)
            if project is None:
                raise JiejianError(ErrorCode.PROJECT_NOT_FOUND, "项目不存在")
            understanding = work.application_understanding.get(project_id)

        external = self._application_blockers(understanding)
        if understanding is None:
            return self._view(project_id, (), external)

        matrix = self._permission_intents.matrix(project_id)
        identities = tuple(
            sorted(
                self._test_identities.list(project_id),
                key=lambda item: item.identity_id,
            )
        )
        external.extend(self._permission_blockers(matrix))
        external.extend(self._source_change_blockers(project_id))

        active_by_action = {
            action.action_candidate_id: tuple(
                cell
                for cell in action.cells
                if cell.intent_id is not None and cell.expectation is not None
            )
            for action in matrix.actions
        }
        active_by_action = {
            action_id: cells for action_id, cells in active_by_action.items() if cells
        }

        items: list[PreparationItemView] = []
        for action in sorted(matrix.actions, key=lambda item: item.action_candidate_id):
            cells = active_by_action.get(action.action_candidate_id, ())
            if not cells:
                continue
            items.extend(
                self._identity_items(
                    action,
                    cells,
                    identities,
                    automation_allowed=not external,
                )
            )
            items.extend(
                self._action_items(
                    action,
                    self._action_safety_setup.inspect_action(
                        project_id,
                        action.action_candidate_id,
                    ),
                )
            )

        try:
            preview = self._checks.preview(project_id)
        except JiejianError as exc:
            preview = None
            preview_error = exc.code
        else:
            preview_error = None
            external.extend(self._preview_external_blockers(preview))

        external = self._unique_blockers(external)
        # 外部 blocker 出现时，先前推导出的 AUTO 不能继续执行写操作。
        if external:
            items = [
                item.model_copy(
                    update={
                        "status": PreparationItemStatus.BLOCKED,
                        "description": "请先处理页面列出的外部阻塞项，再继续自动准备。",
                        "auto_action": None,
                        "reason_codes": tuple(
                            dict.fromkeys((*item.reason_codes, "EXTERNAL_BLOCKER"))
                        ),
                    }
                )
                if item.status is PreparationItemStatus.AUTO
                else item
                for item in items
            ]

        items.append(
            self._profile_item(
                items,
                external,
                preview,
                preview_error=preview_error,
            )
        )
        return self._view(project_id, tuple(items), external)

    def prepare_safe(self, project_id: str) -> ProjectPreparationView:
        """有限执行安全机械动作；候选确认、登录、录制和 Run 提交均不在此入口。"""

        initial = self.status(project_id)
        if initial.external_blockers:
            return initial

        ensured_roles: set[str] = set()
        for item in initial.items:
            if (
                item.auto_action is not PreparationAutoAction.ENSURE_IDENTITY_RECORD
                or item.role_candidate_id is None
                or item.role_candidate_id in ensured_roles
            ):
                continue
            ensured_roles.add(item.role_candidate_id)
            current_identities = tuple(self._test_identities.list(project_id))
            if self._matching_identities(item, current_identities):
                continue
            self._test_identities.create(
                project_id,
                role_candidate_id=item.role_candidate_id,
                label=item.label,
            )

        current = self.status(project_id)
        if current.external_blockers:
            return current
        non_profile_pending = tuple(
            item
            for item in current.items
            if item.kind is not PreparationItemKind.PROFILE
            and item.status is not PreparationItemStatus.READY
        )
        profile_auto = tuple(
            item
            for item in current.items
            if item.kind is PreparationItemKind.PROFILE
            and item.auto_action is PreparationAutoAction.BUILD_CURRENT_PROFILE
        )
        if not non_profile_pending and len(profile_auto) == 1:
            self._checks.prepare(project_id)
            current = self.status(project_id)
        return current

    @staticmethod
    def _application_blockers(understanding) -> list[PreparationExternalBlockerView]:
        if understanding is None:
            return [
                _blocker(
                    "application-missing",
                    "APPLICATION",
                    "尚未完成应用接入",
                    "请先连接应用并确认运行地址。",
                    "/application",
                    "去应用接入",
                    ("APPLICATION_MISSING",),
                )
            ]
        reasons: list[str] = []
        if (
            not understanding.confirmed_endpoint
            or not understanding.endpoint_source_fingerprint
            or understanding.endpoint_reachable is not True
        ):
            reasons.append("APPLICATION_ENDPOINT_UNCONFIRMED")
        if not understanding.source_analysis_authorized or not understanding.source_fingerprint:
            reasons.append("SOURCE_ANALYSIS_INCOMPLETE")
        if not any(
            item.decision is CandidateDecision.CONFIRMED and not item.stale
            for item in understanding.role_candidates
        ):
            reasons.append("ROLE_CANDIDATE_UNCONFIRMED")
        if not any(
            item.decision is CandidateDecision.CONFIRMED and not item.stale
            for item in understanding.action_candidates
        ):
            reasons.append("ACTION_CANDIDATE_UNCONFIRMED")
        if not reasons:
            return []
        return [
            _blocker(
                "application-incomplete",
                "APPLICATION",
                "应用事实尚未确认完整",
                "运行地址、源码分析、权限组和业务动作必须先由用户确认。",
                "/application",
                "去完成应用接入",
                tuple(reasons),
            )
        ]

    @staticmethod
    def _permission_blockers(matrix) -> list[PreparationExternalBlockerView]:
        application_reasons: set[str] = set()
        permission_reasons: set[str] = set()
        if matrix.confirmed_count == 0:
            permission_reasons.add("PERMISSION_INTENT_UNCONFIRMED")
        if matrix.review_required_count:
            permission_reasons.add("PERMISSION_INTENT_NEEDS_REVIEW")
        for action in matrix.actions:
            active = tuple(
                cell
                for cell in action.cells
                if cell.intent_id is not None and cell.expectation is not None
            )
            expectations = {
                cell.expectation.value for cell in active if cell.expectation is not None
            }
            for code in action.gaps:
                if code in _PREPARATION_GAPS:
                    continue
                if code == "ALLOW_INTENT_MISSING" and "ALLOW" in expectations:
                    continue
                if code == "DENY_INTENT_MISSING" and "DENY" in expectations:
                    continue
                if code in _APPLICATION_GAPS:
                    application_reasons.add(code)
                else:
                    permission_reasons.add(code)
            for cell in active:
                if cell.status is not PermissionIntentCellStatus.CURRENT:
                    permission_reasons.update(
                        cell.review_reasons or ("PERMISSION_INTENT_NEEDS_REVIEW",)
                    )
        blockers: list[PreparationExternalBlockerView] = []
        if application_reasons:
            blockers.append(
                _blocker(
                    "application-candidate-stale",
                    "APPLICATION",
                    "应用候选已经变化",
                    "请先重新确认当前权限组和业务动作。",
                    "/application",
                    "去确认应用范围",
                    tuple(sorted(application_reasons)),
                )
            )
        if permission_reasons:
            blockers.append(
                _blocker(
                    "permission-incomplete",
                    "PERMISSION",
                    "权限规则尚未形成当前可执行映射",
                    "请先确认权限要求或重新确认实现映射。",
                    "/permissions",
                    "去确认权限规则",
                    tuple(sorted(permission_reasons)),
                )
            )
        return blockers

    def _source_change_blockers(
        self,
        project_id: str,
    ) -> list[PreparationExternalBlockerView]:
        if self._source_changes is None:
            return []
        latest = self._source_changes.latest(project_id)
        if latest is None:
            return []
        inspection = self._source_changes.inspect_revalidation(
            project_id,
            latest[0].change_id,
        )
        if inspection.status is SourceRevalidationInspectionStatus.READY:
            return []
        mapping_review = (
            inspection.status
            is SourceRevalidationInspectionStatus.MAPPING_REVIEW_REQUIRED
        )
        return [
            _blocker(
                "source-change-review",
                "SOURCE_CHANGE",
                "最近代码变化仍需审阅",
                "代码变化的实现映射尚未形成当前可重验事实。",
                "/permissions" if mapping_review else "/changes",
                "去确认权限实现" if mapping_review else "去审阅代码变化",
                inspection.reason_codes,
            )
        ]

    @staticmethod
    def _identity_items(
        action,
        cells,
        identities,
        *,
        automation_allowed: bool,
    ) -> tuple[PreparationItemView, ...]:
        items: list[PreparationItemView] = []
        for cell in sorted(
            cells,
            key=lambda item: (
                item.subject_role_candidate_id,
                item.relation.value,
                item.intent_id or "",
            ),
        ):
            key = (
                f"identity:{action.action_candidate_id}:"
                f"{cell.subject_role_candidate_id}:{cell.relation.value}"
            )
            probe = PreparationItemView(
                key=key,
                kind=PreparationItemKind.IDENTITY,
                label=_identity_label(cell),
                status=PreparationItemStatus.BLOCKED,
                description="正在核对当前测试账号。",
                next_path="/identities",
                next_label="管理测试账号",
                role_candidate_id=cell.subject_role_candidate_id,
                action_candidate_id=action.action_candidate_id,
                identity_id=cell.representative_test_identity_id,
            )
            matching = ProjectPreparationService._matching_identities(probe, identities)
            prepared = tuple(
                item for item in matching if item.status is TestIdentityStatus.PREPARED
            )
            if prepared:
                selected = prepared[0]
                item = probe.model_copy(
                    update={
                        "status": PreparationItemStatus.READY,
                        "description": f"{selected.label} 的登录状态当前可用。",
                        "next_path": None,
                        "next_label": None,
                        "reason_codes": (),
                        "identity_id": selected.identity_id,
                    }
                )
            elif matching:
                selected = matching[0]
                item = probe.model_copy(
                    update={
                        "status": PreparationItemStatus.USER,
                        "description": f"{selected.label} 需要登录或重新登录。",
                        "reason_codes": ("TEST_IDENTITY_NOT_PREPARED",),
                        "identity_id": selected.identity_id,
                    }
                )
            elif cell.relation is PermissionIntentRelation.OWNS:
                item = probe.model_copy(
                    update={
                        "status": PreparationItemStatus.BLOCKED,
                        "description": "资源所有者账号必须先通过真实业务流程建立。",
                        "next_path": "/flows",
                        "next_label": "去录制业务流程",
                        "reason_codes": ("OWNER_IDENTITY_MISSING",),
                    }
                )
            elif automation_allowed:
                item = probe.model_copy(
                    update={
                        "status": PreparationItemStatus.AUTO,
                        "description": "可以安全创建非秘密测试账号记录；真实登录仍由用户完成。",
                        "reason_codes": ("TEST_IDENTITY_MISSING",),
                        "auto_action": PreparationAutoAction.ENSURE_IDENTITY_RECORD,
                    }
                )
            else:
                item = probe.model_copy(
                    update={
                        "status": PreparationItemStatus.BLOCKED,
                        "description": "请先处理外部阻塞项，再创建测试账号记录。",
                        "reason_codes": ("TEST_IDENTITY_MISSING", "EXTERNAL_BLOCKER"),
                    }
                )
            items.append(item)
        return tuple(items)

    @staticmethod
    def _matching_identities(item: PreparationItemView, identities) -> tuple:
        if item.identity_id is not None:
            return tuple(
                identity
                for identity in identities
                if identity.identity_id == item.identity_id
            )
        candidates = tuple(
            identity
            for identity in identities
            if identity.role_candidate_id == item.role_candidate_id
        )
        # Matrix 已经确认是否存在可执行 representative；没有时只投影
        # 仍需用户处理的同角色身份，避免把资源所有者误当作 other-account。
        return tuple(
            identity
            for identity in candidates
            if identity.status is not TestIdentityStatus.PREPARED
        )

    @staticmethod
    def _action_items(action, inspection) -> tuple[PreparationItemView, ...]:
        suffixes = {
            ActionSafetyAssetKind.FLOW: "业务流程",
            ActionSafetyAssetKind.RESOURCE: "测试资源",
            ActionSafetyAssetKind.OBSERVATION: "结果观察",
            ActionSafetyAssetKind.RECOVERY: "现场恢复",
            ActionSafetyAssetKind.EFFECT: "受保护后果",
        }
        items: list[PreparationItemView] = []
        for asset in inspection.assets:
            kind = PreparationItemKind(asset.kind.value)
            if asset.status is ActionSafetyAssetStatus.CURRENT:
                status = PreparationItemStatus.READY
                description = "当前静态测试资产仍与正式事实一致。"
            elif asset.kind is ActionSafetyAssetKind.FLOW:
                status = PreparationItemStatus.USER
                description = "需要录制或重新确认当前真实业务流程。"
            elif asset.candidate_count > 0 or (
                asset.kind is ActionSafetyAssetKind.RECOVERY
                and not inspection.state_changing
            ):
                status = PreparationItemStatus.USER
                description = "已有有限候选，需要用户重新确认。"
            else:
                status = PreparationItemStatus.BLOCKED
                description = "当前没有可靠候选，需要补录对应业务事实。"
            items.append(
                _item(
                    action,
                    kind,
                    status,
                    f"{action.action_display_name}{suffixes[asset.kind]}",
                    description,
                    asset.reason_codes,
                    recording_id=asset.recording_id,
                )
            )
        return tuple(items)

    @staticmethod
    def _preview_external_blockers(preview) -> list[PreparationExternalBlockerView]:
        application: set[str] = set()
        permission: set[str] = set()
        for gap in preview.gaps:
            if gap.code in _PREPARATION_GAPS:
                continue
            # Matrix 已区分“权限语义缺失”和“账号缺失导致暂不可执行”，
            # Preview 的聚合 ALLOW/DENY gap 不能反向覆盖这个判断。
            # CheckPreview 会把未被用户选入当前考题的矩阵单元也汇总为未确认；
            # 正式 PermissionIntent 是否阻塞已经由 Matrix 判定，不能在这里扩大范围。
            if gap.code in {
                "ALLOW_INTENT_MISSING",
                "DENY_INTENT_MISSING",
                "PERMISSION_INTENT_UNCONFIRMED",
            }:
                continue
            if gap.next_path == "/application":
                application.add(gap.code)
            elif gap.next_path == "/permissions":
                permission.add(gap.code)
        blockers: list[PreparationExternalBlockerView] = []
        if application:
            blockers.append(
                _blocker(
                    "check-application-blocker",
                    "APPLICATION",
                    "检查范围依赖的应用事实未确认",
                    "请先完成应用候选确认。",
                    "/application",
                    "去确认应用范围",
                    tuple(sorted(application)),
                )
            )
        if permission:
            blockers.append(
                _blocker(
                    "check-permission-blocker",
                    "PERMISSION",
                    "当前权限覆盖仍有阻塞",
                    "请先补齐权限规则或差分覆盖。",
                    "/permissions",
                    "去确认权限规则",
                    tuple(sorted(permission)),
                )
            )
        return blockers

    @staticmethod
    def _profile_item(items, external, preview, *, preview_error: str | None):
        prerequisites_ready = all(
            item.status is PreparationItemStatus.READY for item in items
        )
        if preview_error is not None:
            return PreparationItemView(
                key="profile:current",
                kind=PreparationItemKind.PROFILE,
                label="当前检查配置",
                status=PreparationItemStatus.BLOCKED,
                description="当前检查预览不可用，请先处理前面的阻塞项。",
                next_path="/validation",
                next_label="查看验证准备",
                reason_codes=(preview_error,),
            )
        profile_gaps = {
            gap.code
            for gap in (() if preview is None else preview.gaps)
            if gap.code in {"GENERATED_PROFILE_MISSING", "GENERATED_PROFILE_STALE"}
        }
        if prerequisites_ready and not external and not profile_gaps:
            return PreparationItemView(
                key="profile:current",
                kind=PreparationItemKind.PROFILE,
                label="当前检查配置",
                status=PreparationItemStatus.READY,
                description="当前检查配置与正式准备事实一致。",
                reason_codes=(),
            )
        if prerequisites_ready and not external and profile_gaps:
            return PreparationItemView(
                key="profile:current",
                kind=PreparationItemKind.PROFILE,
                label="当前检查配置",
                status=PreparationItemStatus.AUTO,
                description="可以复用当前编译链生成最新检查配置。",
                next_path="/validation",
                next_label="生成当前检查配置",
                reason_codes=tuple(sorted(profile_gaps)),
                auto_action=PreparationAutoAction.BUILD_CURRENT_PROFILE,
            )
        return PreparationItemView(
            key="profile:current",
            kind=PreparationItemKind.PROFILE,
            label="当前检查配置",
            status=PreparationItemStatus.BLOCKED,
            description="等待前面的测试准备或外部阻塞项完成。",
            next_path="/validation",
            next_label="查看验证准备",
            reason_codes=("PREPARATION_PREREQUISITE",),
        )

    @staticmethod
    def _unique_blockers(blockers) -> tuple[PreparationExternalBlockerView, ...]:
        merged: dict[str, PreparationExternalBlockerView] = {}
        for blocker in blockers:
            current = merged.get(blocker.key)
            if current is None:
                merged[blocker.key] = blocker
                continue
            merged[blocker.key] = current.model_copy(
                update={
                    "reason_codes": tuple(
                        dict.fromkeys((*current.reason_codes, *blocker.reason_codes))
                    )
                }
            )
        order = {"APPLICATION": 0, "PERMISSION": 1, "SOURCE_CHANGE": 2}
        return tuple(
            sorted(merged.values(), key=lambda item: (order[item.category], item.key))
        )

    @staticmethod
    def _view(project_id: str, items, external) -> ProjectPreparationView:
        external = tuple(external)
        ordered = tuple(
            sorted(
                items,
                key=lambda item: (
                    _KIND_ORDER[item.kind],
                    item.action_candidate_id or "",
                    item.role_candidate_id or "",
                    item.key,
                ),
            )
        )
        next_item = next(
            (item for item in ordered if item.status is not PreparationItemStatus.READY),
            None,
        )
        if external:
            next_key = external[0].key
        else:
            next_key = None if next_item is None else next_item.key
        return ProjectPreparationView(
            project_id=project_id,
            ready=bool(ordered)
            and not external
            and all(item.status is PreparationItemStatus.READY for item in ordered),
            items=ordered,
            next_item_key=next_key,
            auto_action_count=sum(
                item.status is PreparationItemStatus.AUTO for item in ordered
            ),
            user_action_count=sum(
                item.status is PreparationItemStatus.USER for item in ordered
            ),
            blocked_count=sum(
                item.status is PreparationItemStatus.BLOCKED for item in ordered
            ),
            external_blockers=external,
        )


def _identity_label(cell) -> str:
    suffix = (
        "同权限组其他测试账号"
        if cell.relation is PermissionIntentRelation.SAME_ROLE_OTHER_ACCOUNT
        else "测试账号"
    )
    return f"{cell.subject_role_display_name[: 128 - len(suffix)]}{suffix}"


def _item(
    action,
    kind: PreparationItemKind,
    status: PreparationItemStatus,
    label: str,
    description: str,
    reason_codes: tuple[str, ...],
    *,
    recording_id: str | None = None,
) -> PreparationItemView:
    return PreparationItemView(
        key=f"{kind.value.lower()}:{action.action_candidate_id}",
        kind=kind,
        label=label,
        status=status,
        description=description,
        next_path=None if status is PreparationItemStatus.READY else "/flows",
        next_label=None if status is PreparationItemStatus.READY else "管理业务流程",
        reason_codes=reason_codes,
        action_candidate_id=action.action_candidate_id,
        recording_id=recording_id,
    )


def _blocker(
    key: str,
    category: Literal["APPLICATION", "PERMISSION", "SOURCE_CHANGE"],
    label: str,
    description: str,
    next_path: PreparationPath,
    next_label: str,
    reason_codes: tuple[str, ...],
) -> PreparationExternalBlockerView:
    return PreparationExternalBlockerView(
        key=key,
        category=category,
        label=label,
        description=description,
        next_path=next_path,
        next_label=next_label,
        reason_codes=reason_codes,
    )


__all__ = [
    "PreparationAutoAction",
    "PreparationExternalBlockerView",
    "PreparationItemKind",
    "PreparationItemStatus",
    "PreparationItemView",
    "ProjectPreparationService",
    "ProjectPreparationView",
]
