# 只读核对材料的业务、身份、录制与来源；调用者拥有 UoW，检查与字段构造均不提交事务。
from __future__ import annotations

from pathlib import Path
from typing import Protocol
from product.backend.core.boundaries.entities import BusinessRevisionState, ImplementationBindingStatus
from product.backend.core.errors import JiejianError
from product.backend.core.preparation.bindings import ActionEvidenceBinding, ActionEvidenceKind, ActionExecutionBinding, ActionRecoveryBinding, ActionResourceBinding, RegisteredObserverReference
from product.backend.core.recording.models import RecordingPurpose, RecordingState
from product.backend.workflows.business_boundaries.inspection import inspect_action_binding, inspect_actor_binding
from product.backend.workflows.preparation.bindings.recording_candidates import supplement_candidates
from product.backend.workflows.recording.source import identity_source_fingerprint, recording_endpoint_fingerprint, require_persisted_recording_source, current_recording_instance

class RegisteredObserverReader(Protocol):
    def contains(self, project_id: str, reference: RegisteredObserverReference) -> bool: ...


class BindingSourceInspector:
    """共享同一来源有效性判断；返回原原因顺序，不保存准备状态或扩大读取范围。"""

    def __init__(self, var_dir: Path, registered_observers: RegisteredObserverReader | None = None):
        self._var_dir = var_dir.resolve()
        self._registered_observers = registered_observers

    def reasons(self, work, binding, action, understanding):
        if understanding is None or (
            binding.project_id, binding.business_action_id, binding.action_revision, binding.action_semantic_fingerprint,
        ) != (action.project_id, action.action_id, action.revision, action.semantic_fingerprint):
            return ("ACTION_BINDING_SOURCE_STALE",)
        source_reused = False
        if binding.source_fingerprint != understanding.source_fingerprint:
            from product.backend.workflows.preparation.bindings.reuse import recorded_material_reusable
            source_reused = recorded_material_reusable(work,binding,understanding,self._var_dir)
        identity = work.test_identities.get(binding.subject_test_identity_id)
        owner = work.test_identities.get(binding.resource_owner_test_identity_id)
        if (owner is None or owner.project_id != action.project_id or owner.prepared_at_us is None
                or binding.owner_identity_fingerprint != identity_source_fingerprint(owner)):
            return ("RESOURCE_OWNER_SOURCE_STALE",)
        owner_root = work.business_boundaries.actor(owner.actor_id)
        owner_actor = work.business_boundaries.actor_revision(owner.actor_id, owner.actor_revision)
        if (owner_root is None or owner_actor is None or owner_root.current_revision != owner.actor_revision
                or owner_actor.effective_state is not BusinessRevisionState.ACTIVE
                or inspect_actor_binding(owner.actor_id, owner.actor_revision,
                    work.business_boundaries.actor_binding(owner.actor_id, owner.actor_revision), understanding).status is not ImplementationBindingStatus.CURRENT):
            return ("RESOURCE_OWNER_SOURCE_STALE",)
        action_root = work.business_boundaries.action(action.action_id)
        implementation = inspect_action_binding(action.action_id, action.revision,
                                                work.business_boundaries.action_binding(action.action_id, action.revision), understanding)
        if (action_root is None or action_root.current_revision != action.revision
                or action.effective_state is not BusinessRevisionState.ACTIVE
                or identity is None or identity.project_id != action.project_id or identity.prepared_at_us is None
                or binding.subject_identity_fingerprint != identity_source_fingerprint(identity)
                or implementation.status is not ImplementationBindingStatus.CURRENT
                or binding.implementation_fingerprint != implementation.binding_fingerprint
                or (binding.source_fingerprint != understanding.source_fingerprint and not source_reused)
                or binding.endpoint_fingerprint != recording_endpoint_fingerprint(understanding, controlled_instance_id=current_recording_instance(work, action.project_id))):
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
                or recording.resource_owner_test_identity_id != binding.resource_owner_test_identity_id
                or recording.purpose is not expected_purpose or recording.project_id != action.project_id
                or (recording.business_action_id, recording.action_revision, recording.subject_test_identity_id)
                != (binding.business_action_id, binding.action_revision, binding.subject_test_identity_id)
                or draft_record.revision != binding.source_draft_revision
                or draft_record.draft_sha256 != binding.source_draft_sha256):
            return ("RECORDING_SOURCE_STALE",)
        try:
            require_persisted_recording_source(work, recording, self._var_dir,
                reused_source_fingerprint=binding.source_fingerprint if source_reused else None)
        except JiejianError:
            return ("RECORDING_SOURCE_STALE",)
        if isinstance(binding, (ActionExecutionBinding, ActionResourceBinding)):
            from product.backend.workflows.recording.lifecycle import RecordingLifecycle
            try:
                flow = RecordingLifecycle.load_final_flow(RecordingLifecycle.flow_path(self._var_dir, recording), expected_hash=binding.flow_sha256)
            except JiejianError:
                return ("ACTION_FLOW_UNAVAILABLE",)
            if (flow.id != binding.flow_id or flow.resource_owner_test_identity_id != binding.resource_owner_test_identity_id
                    or (flow.business_action_id, flow.action_revision, flow.subject_test_identity_id)
                    != (binding.business_action_id, binding.action_revision, binding.subject_test_identity_id)):
                return ("ACTION_FLOW_STALE",)
        else:
            if isinstance(binding, ActionEvidenceBinding) and recording.effect_id != binding.effect_id:
                return ("EFFECT_REFERENCE_STALE",)
            if isinstance(binding, ActionRecoveryBinding) and not action.state_changing:
                return ("RECOVERY_NOT_REQUIRED",)
            resource = work.action_preparation.resource(action.action_id, action.revision, binding.resource_owner_test_identity_id)
            if (resource is None or resource.source_recording_id != recording.parent_recording_id
                    or self.reasons(work, resource, action, understanding)):
                return ("SUPPLEMENT_RESOURCE_STALE",)
            try:
                candidates = supplement_candidates(recording, draft_record.draft, resource.actual_resource_id)
            except JiejianError:
                return ("SUPPLEMENT_REQUEST_STALE",)
            if not any(item.step_id == binding.step_id and item.request_template == binding.request_template for item in candidates):
                return ("SUPPLEMENT_REQUEST_STALE",)
        return ()


def binding_source_fields(work, action, identity, understanding, now_us, owner_id):
    implementation = work.business_boundaries.action_binding(action.action_id, action.revision)
    return {
        "project_id": action.project_id, "business_action_id": action.action_id, "action_revision": action.revision,
        "action_semantic_fingerprint": action.semantic_fingerprint,
        "implementation_fingerprint": implementation.binding_fingerprint,
        "source_fingerprint": understanding.source_fingerprint,
        "endpoint_fingerprint": recording_endpoint_fingerprint(understanding, controlled_instance_id=current_recording_instance(work, action.project_id)),
        "subject_test_identity_id": identity.identity_id, "subject_identity_fingerprint": identity_source_fingerprint(identity),
        "resource_owner_test_identity_id": owner_id,
        "owner_identity_fingerprint": identity_source_fingerprint(work.test_identities.get(owner_id)),
        "confirmed_at_us": now_us,
    }
