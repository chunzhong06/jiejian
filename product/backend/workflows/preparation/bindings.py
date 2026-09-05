# 在录制接受事务中保存技术绑定，并从当前业务、身份、来源与文件事实实时检查有效性。
# 检查路径只读；注册 Observer 只能通过注入的受控引用检查器，不接收地址或查询正文。

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Protocol

from product.backend.core.action_preparation import (
    ActionEvidenceBinding, ActionEvidenceKind, ActionExecutionBinding, ActionRecoveryBinding,
    ActionResourceBinding, RegisteredObserverReference, seal_binding,
)
from product.backend.core.business_boundary import BusinessRevisionState, ImplementationBindingStatus
from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.core.recording import RecordingPurpose, RecordingState
from product.backend.workflows.business_boundaries.inspection import inspect_action_binding, inspect_actor_binding
from product.backend.workflows.preparation.models import (
    ActionTechnicalPreparationView, EffectEvidencePreparationView, PreparationItemView,
    PreparationStatus, ResourcePreparationView,
)
from product.backend.workflows.preparation.recording_candidates import (
    choose_supplement_candidate, flow_resource_injection, request_event, resource_value,
    supplement_candidates,
)
from product.backend.workflows.recording.source import (
    identity_source_fingerprint, recording_endpoint_fingerprint, require_recording_source,
)
from product.backend.workflows.test_identities.service import TestIdentityStatus


class RegisteredObserverReader(Protocol):
    def contains(self, project_id: str, reference: RegisteredObserverReference) -> bool: ...


class PreparationBindingService:
    """接受有明确来源的技术事实；准备状态始终现场计算，不形成权限或 Run。"""

    def __init__(self, uow_factory, var_dir: Path, *, test_identities=None, registered_observers: RegisteredObserverReader | None = None):
        self._uow_factory = uow_factory
        self._var_dir = var_dir.resolve()
        self._test_identities = test_identities
        self._registered_observers = registered_observers

    def accept_recording(self, work, recording, draft_record, *, flow=None, now_us: int):
        """由生命周期服务在同一完成事务调用，候选不明确时整个事务不生效。"""
        action, identity, understanding = require_recording_source(work, recording)
        draft = draft_record.draft
        if (draft.business_action_id, draft.action_revision, draft.test_identity_id,
            draft.recording_id, draft.purpose, draft.parent_recording_id, draft.effect_id) != (
            recording.business_action_id, recording.action_revision, recording.test_identity_id,
            recording.recording_id, recording.purpose, recording.parent_recording_id, recording.effect_id,
        ):
            raise JiejianError(ErrorCode.RECORD_DRAFT_REFERENCE, "草稿与录制业务来源不一致")
        common = self._common(work, action, identity, understanding, now_us)
        source = {
            "source_recording_id": recording.recording_id, "source_draft_revision": draft.revision,
            "source_draft_sha256": draft_record.draft_sha256,
        }
        if recording.purpose is RecordingPurpose.TARGET:
            if flow is None or (flow.business_action_id, flow.action_revision, flow.test_identity_id) != (
                action.action_id, action.revision, identity.identity_id,
            ):
                raise JiejianError(ErrorCode.RECORD_DRAFT_REFERENCE, "最终 Flow 的业务身份不一致")
            target = next((item for item in draft.steps if item.id == draft.target_step_id), None)
            candidate = None if target is None else next((item for item in target.resource_candidates
                                                         if item.candidate_id == draft.resource_candidate_id), None)
            if candidate is None:
                raise JiejianError(ErrorCode.RECORD_DRAFT_UNCONFIRMED, "请确认业务动作和具体资源")
            injection = flow_resource_injection(flow, candidate)
            flow_facts = {"flow_id": flow.id, "flow_sha256": _flow_sha256(flow), "resource_injection": injection}
            resource = seal_binding(
                ActionResourceBinding, **common, **source, **flow_facts,
                owner_test_identity_id=identity.identity_id,
                actual_resource_id=resource_value(request_event(recording, target), candidate),
            )
            execution = seal_binding(ActionExecutionBinding, **common, **source, **flow_facts)
            work.action_preparation.replace(execution)
            work.action_preparation.replace(resource)
            return
        resource = work.action_preparation.resource(action.action_id, action.revision, identity.identity_id)
        if (resource is None or resource.source_recording_id != recording.parent_recording_id
                or self._source_reasons(work, resource, action, understanding)):
            raise JiejianError(ErrorCode.RECORD_STATE_PRECONDITION, "补录需要原业务演示中仍有效的具体资源")
        chosen = choose_supplement_candidate(recording, draft, resource.actual_resource_id)
        if recording.purpose is RecordingPurpose.OBSERVATION:
            binding = seal_binding(
                ActionEvidenceBinding, **common, **source, effect_id=recording.effect_id,
                kind=ActionEvidenceKind.RECORDED_OBSERVATION, step_id=chosen.step_id,
                request_template=chosen.request_template,
            )
        else:
            binding = seal_binding(ActionRecoveryBinding, **common, **source,
                                   step_id=chosen.step_id, request_template=chosen.request_template)
        work.action_preparation.replace(binding)

    def candidates(self, recording_id: str):
        """为补录审阅返回现有有限候选；读取不会自动接受或调用外部服务。"""
        with self._uow_factory() as work:
            recording = work.recordings.get(recording_id)
            draft = work.flow_drafts.latest(recording_id)
            if recording is None or draft is None:
                raise JiejianError(ErrorCode.RECORD_NOT_FOUND, "录制草稿不存在")
            if recording.purpose is RecordingPurpose.TARGET:
                return ()
            action, _, understanding = require_recording_source(work, recording)
            resource = work.action_preparation.resource(action.action_id, action.revision, recording.test_identity_id)
            if resource is None or self._source_reasons(work, resource, action, understanding):
                return ()
            return supplement_candidates(recording, draft.draft, resource.actual_resource_id)

    def register_observer(self, recording_id: str, *, effect_id: str, reference: RegisteredObserverReference, now_us: int):
        """仅供受控组合使用的窄引用写入；普通 API 不暴露此操作。"""
        with self._uow_factory() as work:
            recording = work.recordings.get(recording_id)
            if recording is None or recording.state is not RecordingState.COMPLETED or recording.purpose is not RecordingPurpose.TARGET:
                raise JiejianError(ErrorCode.RECORD_STATE_PRECONDITION, "Observer 引用需要已完成的业务演示")
            action, identity, understanding = require_recording_source(work, recording)
            if (effect_id not in {item.effect_id for item in action.effect_catalog}
                    or self._registered_observers is None
                    or not self._registered_observers.contains(action.project_id, reference)):
                raise JiejianError(ErrorCode.STATE_PRECONDITION, "受控 Observer 或当前业务效果不可用")
            binding = seal_binding(
                ActionEvidenceBinding, **self._common(work, action, identity, understanding, now_us),
                kind=ActionEvidenceKind.REGISTERED_OBSERVER, effect_id=effect_id, observer_reference=reference,
            )
            work.action_preparation.replace(binding)
            work.commit()
            return binding

    def inspect(self, action, contract, identities) -> ActionTechnicalPreparationView:
        with self._uow_factory() as work:
            understanding = work.application_understanding.get(action.project_id)
            repository = work.action_preparation
            execution = repository.execution(action.action_id, action.revision)
            execution_view = self._item(work, execution, action, understanding, "ACTION_EXECUTION_REQUIRED")
            assignments = {item.requirement.slot_id: item.test_identity_id for item in identities.slots}
            resources = []
            for requirement in contract.resources:
                owner = assignments.get(requirement.owner_slot_id)
                binding = None if owner is None else repository.resource(action.action_id, action.revision, owner)
                view = self._item(work, binding, action, understanding, "ACTION_RESOURCE_REQUIRED")
                if binding is not None and (
                    execution is None or execution_view.status is not PreparationStatus.SATISFIED
                    or binding.resource_injection != execution.resource_injection
                ):
                    view = _stale(binding, "RESOURCE_INJECTION_STALE")
                resources.append(ResourcePreparationView(**view.model_dump(), owner_slot_id=requirement.owner_slot_id,
                                                         owner_test_identity_id=owner))
            evidence = []
            for requirement in contract.effect_evidence:
                binding = repository.evidence(action.action_id, action.revision, requirement.effect_id)
                view = self._item(work, binding, action, understanding, "EFFECT_EVIDENCE_REQUIRED")
                evidence.append(EffectEvidencePreparationView(**view.model_dump(), effect_id=requirement.effect_id))
            recovery = (self._item(work, repository.recovery(action.action_id, action.revision), action,
                                   understanding, "ACTION_RECOVERY_REQUIRED") if contract.recovery_required else
                        PreparationItemView(status=PreparationStatus.NOT_REQUIRED))
            return ActionTechnicalPreparationView(execution=execution_view, resources=tuple(resources),
                                                  effect_evidence=tuple(evidence), recovery=recovery)

    def _item(self, work, binding, action, understanding, missing_reason):
        if binding is None:
            return PreparationItemView(status=PreparationStatus.NEEDS_USER, reason_codes=(missing_reason,))
        reasons = self._source_reasons(work, binding, action, understanding)
        if self._test_identities is None:
            reasons += ("TEST_IDENTITY_INSPECTION_UNAVAILABLE",)
        else:
            try:
                identity = self._test_identities.get(binding.test_identity_id)
                if identity.project_id != action.project_id or identity.status is not TestIdentityStatus.PREPARED:
                    reasons += ("TEST_IDENTITY_LOGIN_REQUIRED",)
            except JiejianError:
                reasons += ("TEST_IDENTITY_REQUIRED",)
        return PreparationItemView(
            status=PreparationStatus.STALE if reasons else PreparationStatus.SATISFIED,
            binding_fingerprint=binding.binding_fingerprint, reason_codes=tuple(dict.fromkeys(reasons)),
        )

    def _source_reasons(self, work, binding, action, understanding):
        if understanding is None or (
            binding.project_id, binding.business_action_id, binding.action_revision, binding.action_semantic_fingerprint,
        ) != (action.project_id, action.action_id, action.revision, action.semantic_fingerprint):
            return ("ACTION_BINDING_SOURCE_STALE",)
        identity = work.test_identities.get(binding.test_identity_id)
        action_root = work.business_boundaries.action(action.action_id)
        implementation = inspect_action_binding(action.action_id, action.revision,
                                                work.business_boundaries.action_binding(action.action_id, action.revision), understanding)
        if (action_root is None or action_root.current_revision != action.revision
                or action.effective_state is not BusinessRevisionState.ACTIVE
                or identity is None or identity.project_id != action.project_id or identity.prepared_at_us is None
                or binding.identity_fingerprint != identity_source_fingerprint(identity)
                or implementation.status is not ImplementationBindingStatus.CURRENT
                or binding.implementation_fingerprint != implementation.binding_fingerprint
                or binding.source_fingerprint != understanding.source_fingerprint
                or binding.endpoint_fingerprint != recording_endpoint_fingerprint(understanding)):
            return ("ACTION_BINDING_SOURCE_STALE",)
        actor_root = work.business_boundaries.actor(identity.actor_id)
        actor = work.business_boundaries.actor_revision(identity.actor_id, identity.actor_revision)
        if (actor_root is None or actor is None or actor.project_id != action.project_id
                or actor_root.current_revision != identity.actor_revision
                or actor.effective_state is not BusinessRevisionState.ACTIVE
                or inspect_actor_binding(actor.actor_id, actor.revision,
                    work.business_boundaries.actor_binding(actor.actor_id, actor.revision), understanding
                ).status is not ImplementationBindingStatus.CURRENT):
            return ("TEST_ACTOR_SOURCE_STALE",)
        if isinstance(binding, ActionEvidenceBinding) and binding.kind is ActionEvidenceKind.REGISTERED_OBSERVER:
            if binding.effect_id not in {item.effect_id for item in action.effect_catalog}:
                return ("EFFECT_REFERENCE_STALE",)
            if self._registered_observers is None or not self._registered_observers.contains(action.project_id, binding.observer_reference):
                return ("REGISTERED_OBSERVER_UNAVAILABLE",)
            return ()
        recording = work.recordings.get(binding.source_recording_id)
        draft_record = work.flow_drafts.latest(binding.source_recording_id)
        expected_purpose = (RecordingPurpose.OBSERVATION if isinstance(binding, ActionEvidenceBinding) else
                            RecordingPurpose.RECOVERY if isinstance(binding, ActionRecoveryBinding) else RecordingPurpose.TARGET)
        if (recording is None or draft_record is None or recording.state is not RecordingState.COMPLETED
                or recording.purpose is not expected_purpose or recording.project_id != action.project_id
                or (recording.business_action_id, recording.action_revision, recording.test_identity_id)
                != (binding.business_action_id, binding.action_revision, binding.test_identity_id)
                or draft_record.revision != binding.source_draft_revision
                or draft_record.draft_sha256 != binding.source_draft_sha256):
            return ("RECORDING_SOURCE_STALE",)
        try:
            require_recording_source(work, recording)
        except JiejianError:
            return ("RECORDING_SOURCE_STALE",)
        if isinstance(binding, (ActionExecutionBinding, ActionResourceBinding)):
            from product.backend.workflows.recording.lifecycle import RecordingLifecycle
            try:
                flow = RecordingLifecycle.load_final_flow(RecordingLifecycle.flow_path(self._var_dir, recording))
            except JiejianError:
                return ("ACTION_FLOW_UNAVAILABLE",)
            if (_flow_sha256(flow) != binding.flow_sha256 or flow.id != binding.flow_id
                    or (flow.business_action_id, flow.action_revision, flow.test_identity_id)
                    != (binding.business_action_id, binding.action_revision, binding.test_identity_id)):
                return ("ACTION_FLOW_STALE",)
        else:
            if isinstance(binding, ActionEvidenceBinding) and recording.effect_id != binding.effect_id:
                return ("EFFECT_REFERENCE_STALE",)
            if isinstance(binding, ActionRecoveryBinding) and not action.state_changing:
                return ("RECOVERY_NOT_REQUIRED",)
            resource = work.action_preparation.resource(action.action_id, action.revision, binding.test_identity_id)
            if (resource is None or resource.source_recording_id != recording.parent_recording_id
                    or self._source_reasons(work, resource, action, understanding)):
                return ("SUPPLEMENT_RESOURCE_STALE",)
            try:
                candidates = supplement_candidates(recording, draft_record.draft, resource.actual_resource_id)
            except JiejianError:
                return ("SUPPLEMENT_REQUEST_STALE",)
            if not any(item.step_id == binding.step_id and item.request_template == binding.request_template for item in candidates):
                return ("SUPPLEMENT_REQUEST_STALE",)
        return ()

    @staticmethod
    def _common(work, action, identity, understanding, now_us):
        implementation = work.business_boundaries.action_binding(action.action_id, action.revision)
        return {
            "project_id": action.project_id, "business_action_id": action.action_id, "action_revision": action.revision,
            "action_semantic_fingerprint": action.semantic_fingerprint,
            "implementation_fingerprint": implementation.binding_fingerprint,
            "source_fingerprint": understanding.source_fingerprint,
            "endpoint_fingerprint": recording_endpoint_fingerprint(understanding),
            "test_identity_id": identity.identity_id, "identity_fingerprint": identity_source_fingerprint(identity),
            "confirmed_at_us": now_us,
        }


def _flow_sha256(flow):
    return hashlib.sha256(json.dumps(flow.model_dump(mode="json"), ensure_ascii=False, sort_keys=True,
                                    separators=(",", ":"), allow_nan=False).encode("utf-8")).hexdigest()


def _stale(binding, reason):
    return PreparationItemView(status=PreparationStatus.STALE, reason_codes=(reason,),
                               binding_fingerprint=binding.binding_fingerprint)
