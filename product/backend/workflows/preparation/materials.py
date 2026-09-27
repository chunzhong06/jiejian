# 在原准备真源上解释材料、预览局部替换并持久回读；不执行目标请求或形成安全结论。
import time
import json

from product.backend.core.boundaries.entities import boundary_sha256
from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.core.preparation.bindings import ActionExecutionBinding, ActionResourceBinding, ActionEvidenceBinding
from product.backend.core.recording.models import RecordingState, RecordingPurpose
from product.backend.workflows.preparation.material_models import MaterialChange, MaterialReference, PreparationDraft
from product.backend.workflows.recording.lifecycle import RecordingLifecycle


class PreparationMaterialService:
    def __init__(self, uow_factory, bindings, var_dir, *, preparation, clock_us=None):
        self._uow_factory, self._bindings, self._var_dir = uow_factory, bindings, var_dir
        self._preparation = preparation
        self._clock = clock_us or (lambda: time.time_ns() // 1000)

    def details(self, project_id, reference):
        with self._uow_factory() as work:
            action, understanding, current, fingerprint = self._context(work, project_id, reference)
            view = self._bindings._item(work, current, action, understanding, "MATERIAL_REQUIRED")
            candidates = []
            for recording in work.recordings.list_for_project(project_id):
                if recording.state is not RecordingState.COMPLETED or (
                    recording.business_action_id, recording.action_revision) != (action.action_id, action.revision):
                    continue
                try:
                    bindings = self._candidate(work, reference, recording.recording_id)
                except JiejianError:
                    continue
                candidates.append(dict(recording_id=recording.recording_id,
                    captured_at_us=recording.capture_finished_at_us,
                    current=any(item.binding_fingerprint == getattr(current, "binding_fingerprint", None) for item in bindings),
                    updates=[self._reference(item).model_dump(mode="json") for item in bindings]))
            return dict(material=reference.model_dump(mode="json"), status=view.status.value,
                reason_codes=view.reason_codes, retained=current is not None,
                source_recording_id=getattr(current, "source_recording_id", None),
                confirmed_at_us=getattr(current, "confirmed_at_us", None),
                expected_fingerprint=fingerprint, observed_at_us=self._clock(), candidates=candidates,
                recording_context=self._recording_context(work, project_id, reference, action, understanding, current, fingerprint))

    def _recording_context(self, work, project_id, ref, action, understanding, current, fingerprint):
        from product.backend.workflows.preparation.demonstrations import legal_demonstrations
        from product.backend.workflows.business_boundaries.inspection import inspect_action_binding
        if inspect_action_binding(action.action_id, action.revision,
                work.business_boundaries.action_binding(action.action_id, action.revision), understanding).status.value != "CURRENT":
            return None
        prepared = next((item for item in self._preparation.get(project_id).actions
                         if (item.action_id, item.action_revision) == (action.action_id, action.revision)), None)
        if prepared is None or (ref.kind == "recovery" and not action.state_changing):
            return None
        choices = legal_demonstrations(prepared.assurance_contract, prepared.permissions, prepared.identity_requirements)
        choices = { (item.subject_test_identity_id, item.resource_owner_test_identity_id, item.subject_slot_id, item.resource_owner_slot_id): item
            for item in choices if item.can_execute
            and (ref.kind != "resource" or item.resource_owner_test_identity_id == ref.member_id)
            and (current is None or (item.subject_test_identity_id, item.resource_owner_test_identity_id) ==
                 (current.subject_test_identity_id, current.resource_owner_test_identity_id)) }
        if len(choices) != 1:
            return None
        choice = next(iter(choices.values()))
        parent = None
        purpose = "TARGET" if ref.kind in {"execution", "resource"} else "OBSERVATION" if ref.kind == "evidence" else "RECOVERY"
        if purpose != "TARGET":
            resource = work.action_preparation.resource(action.action_id, action.revision, choice.resource_owner_test_identity_id)
            if resource is None or self._bindings._source_reasons(work, resource, action, understanding):
                return None
            parent = resource.source_recording_id
        pending = [item for item in work.recordings.list_for_project(project_id)
            if (item.business_action_id, item.action_revision, item.purpose.value, item.parent_recording_id, item.effect_id,
                item.subject_test_identity_id, item.resource_owner_test_identity_id) ==
               (action.action_id, action.revision, purpose, parent, ref.member_id if ref.kind == "evidence" else None,
                choice.subject_test_identity_id, choice.resource_owner_test_identity_id)
            and item.state.value not in {"COMPLETED", "FAILED", "CANCELLED", "SAFETY_STOPPED"}
            and work.preparation_recovery.candidate_recording(item.recording_id)]
        if len(pending) > 1:
            return None
        return dict(context_id=boundary_sha256(dict(material=ref.model_dump(mode="json"), basis=fingerprint)),
            material=ref.model_dump(mode="json"), expected_fingerprint=fingerprint,
            can_execute=True, business_action_id=action.action_id, action_revision=action.revision,
            subject_test_identity_id=choice.subject_test_identity_id, resource_owner_test_identity_id=choice.resource_owner_test_identity_id,
            subject_slot_id=choice.subject_slot_id, resource_owner_slot_id=choice.resource_owner_slot_id,
            recording_purpose=purpose, parent_recording_id=parent, effect_id=ref.member_id if ref.kind == "evidence" else None,
            recording_id=None if not pending else pending[0].recording_id,
            title="录制新的替换材料", why_now="为当前材料准备一个新的候选来源。",
            user_responsibility="在浏览器中完成这项操作，并审阅采集到的步骤。",
            system_will_do="审阅后保存为候选，回到材料详情预览影响并确认替换。")

    def preview(self, project_id, command):
        with self._uow_factory() as work:
            return self._preview(work, project_id, command)[0]

    def apply(self, project_id, command):
        """同一次材料写入只接受一次；竞争者完成后仅回读回执，不重放写动作。"""
        try:
            return self._apply_once(project_id, command)
        except JiejianError as error:
            if error.code not in {ErrorCode.STORAGE_CONSTRAINT.value, ErrorCode.STORAGE_FAILURE.value}:
                raise
            with self._uow_factory() as work:
                receipt = work.preparation_recovery.receipt(command.operation_id)
            if receipt is not None and receipt["project_id"] == project_id and receipt["request_fingerprint"] == boundary_sha256(command.model_dump(mode="json")):
                return receipt
            raise

    def _apply_once(self, project_id, command):
        request_fingerprint = boundary_sha256(command.model_dump(mode="json"))
        with self._uow_factory() as work:
            work.acquire_write_lock()
            existing = work.preparation_recovery.receipt(command.operation_id)
            if existing is not None:
                if existing["project_id"] != project_id or existing["request_fingerprint"] != request_fingerprint:
                    raise JiejianError(ErrorCode.STATE_PRECONDITION, "操作标识已用于另一项材料操作")
                return existing
            preview, bindings = self._preview(work, project_id, command)
            for binding in bindings:
                work.action_preparation.replace(binding)
            receipt = dict(schema_version="1", operation_id=command.operation_id, project_id=project_id,
                request_fingerprint=request_fingerprint, created_at_us=self._clock(),
                result="SAVED" if bindings else "RECHECKED", **preview)
            work.preparation_recovery.add_receipt(receipt)
            work.commit()
            return receipt

    def receipt(self, project_id, operation_id):
        with self._uow_factory() as work:
            value = work.preparation_recovery.receipt(operation_id)
            if value is None or value["project_id"] != project_id:
                raise JiejianError(ErrorCode.RECORD_NOT_FOUND, "尚未找到这次材料保存回执，请核对后再操作")
            return value

    def draft(self, project_id):
        with self._uow_factory() as work:
            if work.projects.get(project_id) is None:
                raise JiejianError(ErrorCode.PROJECT_NOT_FOUND, "应用不存在")
            value = work.preparation_recovery.draft(project_id)
            return (PreparationDraft(revision=0) if value is None else PreparationDraft.model_validate_json(json.dumps(value))).model_dump(mode="json")

    def save_draft(self, project_id, draft):
        with self._uow_factory() as work:
            project = work.projects.get(project_id)
            if project is None:
                raise JiejianError(ErrorCode.PROJECT_NOT_FOUND, "应用不存在")
            if project.status.value == "ARCHIVED":
                raise JiejianError(ErrorCode.STATE_PRECONDITION, "应用已归档，准备草稿仅供回看")
            if draft.material is not None:
                self._context(work, project_id, draft.material)
                if (draft.action_id, draft.action_revision) != (draft.material.action_id, draft.material.action_revision):
                    raise JiejianError(ErrorCode.INPUT_INVALID, "准备位置与业务动作不一致")
            elif draft.action_id is not None:
                self._context(work, project_id, MaterialReference(action_id=draft.action_id,
                    action_revision=draft.action_revision or 1, kind="execution"))
            if draft.candidate_recording_id is not None:
                if draft.material is None:
                    raise JiejianError(ErrorCode.INPUT_INVALID, "材料选择缺少业务上下文")
                recording = work.recordings.get(draft.candidate_recording_id)
                if recording is None or (recording.project_id, recording.business_action_id, recording.action_revision) != (project_id, draft.material.action_id, draft.material.action_revision):
                    raise JiejianError(ErrorCode.INPUT_INVALID, "候选材料不属于当前准备上下文")
            value = work.preparation_recovery.save_draft(project_id, draft.model_dump(mode="json"))
            work.commit()
            return value

    def _context(self, work, project_id, ref):
        project = work.projects.get(project_id)
        if project is None or project.status.value == "ARCHIVED":
            raise JiejianError(ErrorCode.STATE_PRECONDITION, "应用不存在或已归档，不能更新准备材料")
        root = work.business_boundaries.action(ref.action_id)
        action = work.business_boundaries.action_revision(ref.action_id, ref.action_revision)
        if root is None or action is None or action.project_id != project_id or root.current_revision != ref.action_revision:
            raise JiejianError(ErrorCode.STATE_PRECONDITION, "业务动作已变化，请返回检查材料重新核对")
        repository = work.action_preparation
        if ref.kind == "evidence":
            if ref.member_id not in {effect.effect_id for effect in action.effect_catalog}:
                raise JiejianError(ErrorCode.INPUT_INVALID, "结果证明不属于当前动作")
            binding = repository.evidence(ref.action_id, ref.action_revision, ref.member_id)
        elif ref.kind == "resource":
            owner = work.test_identities.get(ref.member_id or "")
            if owner is None or owner.project_id != project_id:
                raise JiejianError(ErrorCode.INPUT_INVALID, "资源所有者不属于当前应用")
            binding = repository.resource(ref.action_id, ref.action_revision, ref.member_id)
        else:
            if ref.member_id is not None:
                raise JiejianError(ErrorCode.INPUT_INVALID, "此材料不接受子项标识")
            binding = getattr(repository, ref.kind)(ref.action_id, ref.action_revision)
        understanding = work.application_understanding.get(project_id)
        # 所有依赖属于同一事务快照；任一身份、源码或关联材料变化都要求重新预览。
        from product.backend.workflows.recording.source import current_recording_instance
        basis = dict(action=action.model_dump(mode="json"), controlled_instance_id=current_recording_instance(work, project_id),
            understanding=None if understanding is None else understanding.model_dump(mode="json"),
            identities=[identity.model_dump(mode="json") for identity in work.test_identities.list_for_project(project_id)],
            bindings=[item.binding_fingerprint for item in self._all_bindings(work, action)])
        return action, understanding, binding, boundary_sha256(basis)

    def _all_bindings(self, work, action):
        repo = work.action_preparation
        return tuple(item for item in (repo.execution(action.action_id, action.revision),
            *repo.resources(action.action_id, action.revision),
            *(repo.evidence(action.action_id, action.revision, effect.effect_id) for effect in action.effect_catalog),
            repo.recovery(action.action_id, action.revision)) if item is not None)

    def _candidate(self, work, ref, recording_id):
        recording = work.recordings.get(recording_id)
        draft = work.flow_drafts.latest(recording_id)
        if recording is None or draft is None or recording.state is not RecordingState.COMPLETED or (
            recording.business_action_id, recording.action_revision) != (ref.action_id, ref.action_revision):
            raise JiejianError(ErrorCode.STATE_PRECONDITION, "候选录制不属于当前业务动作或尚未完成审阅")
        flow = None
        if recording.purpose is RecordingPurpose.TARGET:
            flow = RecordingLifecycle.load_final_flow(RecordingLifecycle.flow_path(self._var_dir, recording))
        bindings = self._bindings.build_recording_bindings(work, recording, draft,
            flow=flow, now_us=recording.finished_at_us)
        matching = tuple(binding for binding in bindings if self._reference(binding) == ref)
        if not matching:
            raise JiejianError(ErrorCode.STATE_PRECONDITION, "候选录制的材料用途或资源所有者不匹配")
        repository = work.action_preparation
        previous = (repository.evidence(ref.action_id, ref.action_revision, ref.member_id) if ref.kind == "evidence" else
                    repository.resource(ref.action_id, ref.action_revision, ref.member_id) if ref.kind == "resource" else
                    getattr(repository, ref.kind)(ref.action_id, ref.action_revision))
        if previous is not None and (matching[0].subject_test_identity_id, matching[0].resource_owner_test_identity_id) != (
                previous.subject_test_identity_id, previous.resource_owner_test_identity_id):
            raise JiejianError(ErrorCode.STATE_PRECONDITION, "局部替换不能改变操作账号或资源所有者，请按当前准备任务核对新的身份组合")
        # 动作与录制中的资源不可拆散，替换二者时在预览中明确列出。
        return bindings

    def _preview(self, work, project_id, command):
        action, understanding, current, fingerprint = self._context(work, project_id, command.material)
        if fingerprint != command.expected_fingerprint:
            raise JiejianError(ErrorCode.STATE_PRECONDITION, "材料或依赖已变化，请重新预览后确认")
        bindings = () if command.candidate_recording_id is None else self._candidate(work, command.material, command.candidate_recording_id)
        if not bindings:
            view = self._bindings._item(work, current, action, understanding, "MATERIAL_REQUIRED")
            if view.status.value != "SATISFIED":
                raise JiejianError(ErrorCode.STATE_PRECONDITION, "现有材料尚不能复用，请先处理其依赖或重新录制")
        changed = {self._reference(item) for item in bindings}
        retained = [self._reference(item).model_dump(mode="json") for item in self._all_bindings(work, action)
                    if self._reference(item) not in changed]
        recheck = [item for item in retained if any(binding.__class__ in (ActionExecutionBinding, ActionResourceBinding)
                   for binding in bindings) and item["kind"] in ("resource", "evidence", "recovery")]
        return dict(material=command.material.model_dump(mode="json"), expected_fingerprint=fingerprint,
            before_fingerprint=getattr(current, "binding_fingerprint", None),
            updates=[self._reference(item).model_dump(mode="json") for item in bindings],
            retained=retained, recheck=recheck,
            after_fingerprints=[item.binding_fingerprint for item in bindings]), bindings

    @staticmethod
    def _reference(binding):
        kind = "execution" if isinstance(binding, ActionExecutionBinding) else "resource" if isinstance(binding, ActionResourceBinding) else "evidence" if isinstance(binding, ActionEvidenceBinding) else "recovery"
        return MaterialReference(action_id=binding.business_action_id, action_revision=binding.action_revision,
            kind=kind, member_id=binding.resource_owner_test_identity_id if kind == "resource" else binding.effect_id if kind == "evidence" else None)
