# 从 current 业务边界、非秘密身份视图和技术检查端口实时投影准备缺口。
# 缺少技术事实时只返回 NEEDS_USER；不调用模型、目标、浏览器或旧准备编译链。

from __future__ import annotations

from typing import Protocol

from product.backend.core.assurance import (
    ActionAssuranceContract,
    AssuranceStatus,
    compile_action_assurance,
    ActionAllowControlBinding, PermissionIdentity,
)
from product.backend.core.business_boundary import BusinessActionRevision
from product.backend.workflows.business_boundaries.models import BusinessBoundaryView
from product.backend.workflows.preparation.models import (
    ActionPreparationView,
    ActionTechnicalPreparationView,
    EffectEvidencePreparationView,
    IdentityPreparationView,
    IdentitySlotPreparationView,
    PreparationItemView,
    PreparationStatus,
    PreparationView,
    ResourcePreparationView,
)
from product.backend.workflows.test_identities.service import TestIdentityStatus, TestIdentityView
from product.backend.core.errors import ErrorCode, JiejianError
import time


class BoundaryReader(Protocol):
    def view(self, project_id: str, *, work=None) -> BusinessBoundaryView: ...


class IdentityReader(Protocol):
    def list(self, project_id: str) -> tuple[TestIdentityView, ...]: ...


class PreparationBindingReader(Protocol):
    def inspect(
        self, action: BusinessActionRevision, contract: ActionAssuranceContract,
        identities: IdentityPreparationView, *, work=None,
    ) -> ActionTechnicalPreparationView: ...


class PreparationService:
    """现场检查当前材料并派生只读计划；不保存准备状态或提交检查任务。"""

    def __init__(
        self, business_boundaries: BoundaryReader, test_identities: IdentityReader,
        *, bindings: PreparationBindingReader | None = None, uow_factory=None, clock_us=None,
    ) -> None:
        self._business_boundaries = business_boundaries
        self._test_identities = test_identities
        self._bindings = bindings
        self._uow_factory = uow_factory
        self._clock_us = clock_us or (lambda: time.time_ns() // 1000)

    def current_plan(self, project_id: str, *, engine_version: str, config_fingerprint: str):
        """由已检查的技术绑定装配纯编译输入；缺少受控能力时保留具名缺口。"""
        from product.backend.workflows.preparation.planning import current_plan
        return current_plan(self, project_id, engine_version=engine_version,
                            config_fingerprint=config_fingerprint)

    def build_execution_request_v3(self, project_id: str, *, engine_version: str,
                                   config_fingerprint: str, budget_fingerprint: str,
                                   change_context=None, repair_context=None):
        """只构造完整快照；有缺口时拒绝，不生成会话、Job 或 Run。"""
        import json
        from product.protocols.execution_v3 import PersistedExecutionRequestV3
        plan = self.current_plan(project_id, engine_version=engine_version,
                                 config_fingerprint=config_fingerprint)
        if plan.gaps or not plan.actions or any(not item.cases for item in plan.actions):
            raise JiejianError(ErrorCode.STATE_PRECONDITION, "准备尚未完成",
                               details={"reason": "CHECK_PLAN_INCOMPLETE"})
        payload = plan.model_dump(mode="json", exclude={"gaps"})
        for action in payload["actions"]:
            action.pop("gaps")
        payload.update(config_fingerprint=config_fingerprint, budget_fingerprint=budget_fingerprint,
                       change_context=None if change_context is None else change_context.model_dump(mode="json"),
                       repair_context=None if repair_context is None else repair_context.model_dump(mode="json"))
        return PersistedExecutionRequestV3.model_validate_json(json.dumps(payload), strict=True)

    def select_allow_control(self, project_id: str, *, deny_permission: PermissionIdentity,
                             selected_allow_permission: PermissionIdentity, expected_selection_fingerprint: str):
        """在同一事务重读候选后保存技术选择；不改变正式权限、Approval 或 epoch。"""
        if self._uow_factory is None:
            raise JiejianError(ErrorCode.STATE_PRECONDITION, "准备服务未装配")
        with self._uow_factory() as work:
            boundary = self._business_boundaries.view(project_id, work=work)
            deny = next((item for item in boundary.permission_intents if item.intent_id == deny_permission.intent_id), None)
            if deny is None or (deny.revision, deny.intent_hash) != (deny_permission.revision, deny_permission.intent_hash):
                raise JiejianError(ErrorCode.STATE_PRECONDITION, "准备来源已变化")
            action = next(item for item in boundary.actions if item.action_id == deny.business_action_id)
            contract = compile_action_assurance(action, boundary.permission_intents)
            requirement = next((item for item in contract.allow_controls if item.deny_permission == deny_permission), None)
            if requirement is None or requirement.selection_fingerprint != expected_selection_fingerprint:
                raise JiejianError(ErrorCode.STATE_PRECONDITION, "准备来源已变化")
            if selected_allow_permission not in requirement.candidate_allow_permissions:
                current = next((item for item in boundary.permission_intents if item.intent_id == selected_allow_permission.intent_id), None)
                if current is not None and (current.revision, current.intent_hash) != (selected_allow_permission.revision, selected_allow_permission.intent_hash):
                    raise JiejianError(ErrorCode.STATE_PRECONDITION, "准备来源已变化")
                raise JiejianError(ErrorCode.INPUT_INVALID, "准备选择无效")
            existing = next((item for item in work.action_preparation.allow_controls(project_id)
                             if item.deny_intent_id == deny_permission.intent_id), None)
            binding = ActionAllowControlBinding(
                project_id=project_id, deny_intent_id=deny_permission.intent_id,
                deny_intent_revision=deny_permission.revision, deny_intent_hash=deny_permission.intent_hash,
                selected_allow_intent_id=selected_allow_permission.intent_id,
                selected_allow_intent_revision=selected_allow_permission.revision,
                selected_allow_intent_hash=selected_allow_permission.intent_hash,
                selection_fingerprint=expected_selection_fingerprint, confirmed_at_us=self._clock_us(),
            )
            if existing is not None and existing.model_dump(exclude={"confirmed_at_us"}) == binding.model_dump(exclude={"confirmed_at_us"}):
                return existing
            work.action_preparation.replace_allow_control(binding)
            work.commit()
            return binding

    def get(self, project_id: str) -> PreparationView:
        boundary = self._business_boundaries.view(project_id)
        identities = tuple(item for item in self._test_identities.list(project_id)
                           if item.project_id == project_id)
        actor_names = {(item.actor_id, item.revision): item.display_name for item in boundary.actors}
        selections = ()
        if self._uow_factory is not None:
            with self._uow_factory() as work:
                selections = work.action_preparation.allow_controls(project_id)
        actions = []
        for action in boundary.actions:
            contract = compile_action_assurance(action, boundary.permission_intents, selections)
            identity_view = self._identities(contract, identities, actor_names)
            from product.backend.workflows.preparation.demonstrations import legal_demonstrations
            demonstrations = legal_demonstrations(contract, boundary.permission_intents, identity_view)
            missing_legal_owners = {item.owner_slot_id for item in contract.resources} - {
                item.resource_owner_slot_id for item in demonstrations}
            technical = (
                self._bindings.inspect(action, contract, identity_view)
                if self._bindings is not None else self._missing_technical(contract, identity_view)
            )
            # 只读 Action 的恢复要求由业务语义决定，技术端口不能用伪造 row 改变它。
            if not contract.recovery_required:
                technical = technical.model_copy(update={
                    "recovery": PreparationItemView(status=PreparationStatus.NOT_REQUIRED)
                })
            expected_owners = {item.owner_slot_id for item in contract.resources}
            expected_effects = {item.effect_id for item in contract.effect_evidence}
            assignments = {item.requirement.slot_id: item.test_identity_id for item in identity_view.slots}
            sources_complete = (
                len(technical.resources) == len(expected_owners)
                and {item.owner_slot_id for item in technical.resources} == expected_owners
                and all(item.owner_test_identity_id == assignments.get(item.owner_slot_id)
                        for item in technical.resources)
                and len(technical.effect_evidence) == len(expected_effects)
                and {item.effect_id for item in technical.effect_evidence} == expected_effects
            )
            items = (identity_view, technical.execution, *technical.resources,
                     *technical.effect_evidence, technical.recovery)
            reasons = tuple(dict.fromkeys((
                *contract.reason_codes, *(reason for item in items for reason in item.reason_codes),
                *(("PREPARATION_REQUIREMENT_MISMATCH",) if not sources_complete else ()),
                *(("ALLOW_RESOURCE_SETUP_REQUIRED",) if missing_legal_owners else ()),
            )))
            complete = (
                contract.status is AssuranceStatus.READY and sources_complete and not missing_legal_owners
                and all(item.status is PreparationStatus.SATISFIED for item in items[:-1])
                and technical.recovery.status is (
                    PreparationStatus.SATISFIED if contract.recovery_required else PreparationStatus.NOT_REQUIRED
                )
            )
            actions.append(ActionPreparationView(
                **technical.model_dump(), action_id=action.action_id,
                action_revision=action.revision, display_name=action.display_name,
                assurance_contract_fingerprint=contract.fingerprint, assurance_contract=contract,
                identity_requirements=identity_view, preparation_complete=complete,
                reason_codes=reasons,
                permissions=tuple(item for item in boundary.permission_intents if item.business_action_id == action.action_id),
            ))
        return PreparationView(
            project_id=project_id, actions=tuple(actions),
            preparation_complete=bool(actions) and all(item.preparation_complete for item in actions),
        )

    @staticmethod
    def _identities(contract, identities, actor_names) -> IdentityPreparationView:
        slots = []
        used = set()
        for slot in contract.identity_requirements.slots:
            matching = tuple(item for item in identities
                             if (item.actor_id, item.actor_revision) == (slot.actor_id, slot.actor_revision))
            usable = sorted((item for item in matching
                             if item.status in (TestIdentityStatus.PREPARED, TestIdentityStatus.NOT_PREPARED)
                             and item.identity_id not in used), key=lambda item: (
                                 item.status is not TestIdentityStatus.PREPARED,
                                 item.created_at_us, item.identity_id,
                             ))
            selected = usable[0] if usable else None
            if selected is not None:
                used.add(selected.identity_id)
            satisfied = selected is not None and selected.status is TestIdentityStatus.PREPARED
            stale = selected is None and any(item.status is TestIdentityStatus.NEEDS_REVIEW for item in matching)
            reasons = () if satisfied else (
                "TEST_IDENTITY_REVIEW_REQUIRED" if stale else
                "TEST_IDENTITY_LOGIN_REQUIRED" if selected else "TEST_IDENTITY_REQUIRED",
            )
            slots.append(IdentitySlotPreparationView(
                requirement=slot, actor_display_name=actor_names[(slot.actor_id, slot.actor_revision)],
                test_identity_id=None if selected is None else selected.identity_id,
                status=PreparationStatus.SATISFIED if satisfied else
                       PreparationStatus.STALE if stale else PreparationStatus.NEEDS_USER,
                reason_codes=reasons,
            ))
        return IdentityPreparationView(
            allocation_mode=contract.identity_requirements.allocation_mode, slots=tuple(slots),
            status=PreparationStatus.BLOCKED if contract.status is AssuranceStatus.BLOCKED else
                   PreparationStatus.SATISFIED if all(item.status is PreparationStatus.SATISFIED for item in slots)
                   else PreparationStatus.NEEDS_USER,
            reason_codes=tuple(dict.fromkeys(reason for item in slots for reason in item.reason_codes)),
        )

    @staticmethod
    def _missing_technical(contract, identities) -> ActionTechnicalPreparationView:
        assignments = {item.requirement.slot_id: item.test_identity_id for item in identities.slots}
        return ActionTechnicalPreparationView(
            execution=PreparationItemView(status=PreparationStatus.NEEDS_USER, reason_codes=("ACTION_EXECUTION_REQUIRED",)),
            resources=tuple(ResourcePreparationView(
                owner_slot_id=item.owner_slot_id,
                owner_test_identity_id=assignments.get(item.owner_slot_id),
                status=PreparationStatus.NEEDS_USER, reason_codes=("ACTION_RESOURCE_REQUIRED",),
            ) for item in contract.resources),
            effect_evidence=tuple(EffectEvidencePreparationView(
                effect_id=item.effect_id, status=PreparationStatus.NEEDS_USER,
                reason_codes=("EFFECT_EVIDENCE_REQUIRED",),
            ) for item in contract.effect_evidence),
            recovery=PreparationItemView(
                status=PreparationStatus.NEEDS_USER if contract.recovery_required else PreparationStatus.NOT_REQUIRED,
                reason_codes=("ACTION_RECOVERY_REQUIRED",) if contract.recovery_required else (),
            ),
        )


__all__ = ["PreparationBindingReader", "PreparationService"]
