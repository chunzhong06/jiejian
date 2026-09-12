# 从已检查的当前绑定冻结运行配置；原 Flow/Draft/模板先验 hash，秘密仅保留 env 引用。
from __future__ import annotations

import hashlib
import json
from urllib.parse import parse_qsl, urlsplit

from product.backend.core.action_preparation import ActionEvidenceKind
from product.backend.core.check_plan import derive_effect_proof
from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.infra.artifacts.check_packages import read_check_bytes, reject_check_links
from product.backend.infra.recording.request_store import RecordingRequestStore
from product.backend.workflows.recording.lifecycle import RecordingLifecycle
from product.backend.workflows.recording.source import identity_source_fingerprint
from product.protocols.check_runtime import CheckActionConfig, CheckBudget, CheckRuntimeBundle, async_completion_candidates
from product.protocols.observer import ObserverSpec
from product.protocols.web.response import HttpOutcomeClassifier, HttpPredicate, HttpPredicateKind
from product.protocols.flow_draft import canonical_flow_draft_json_bytes
from product.protocols.recording_flow import Flow
from product.protocols.web.request import HttpRequestTemplate


def _incomplete(reason):
    return JiejianError(ErrorCode.STATE_PRECONDITION, "准备尚未完成", details={"reason": reason})


def recorded_request_template(template) -> HttpRequestTemplate:
    """将已绑定的资源占位转换为同一正式 Web 叶模型；不引入任意表达式或动态 URL。"""
    parsed = urlsplit(template.relative_path)
    slots = []
    marker = "{case_resource_id}"
    def slot(consumer):
        name = f"resource_{len(slots)}"
        slots.append(dict(slot_id=name, source="CASE_RESOURCE_ID", consumer=consumer, max_length=256))
        return name
    path = parsed.path
    if marker in path:
        if path.count(marker) != 1:
            raise _incomplete("RECOVERY_REQUEST_UNSUPPORTED")
        path = path.replace(marker, "{" + slot("PATH") + "}")
    query = []
    for name, value in parse_qsl(parsed.query, keep_blank_values=True):
        if marker in value and value != marker:
            raise _incomplete("OBSERVATION_REQUEST_UNSUPPORTED")
        query.append(dict(name=name, **({"slot_id": slot("QUERY")} if value == marker else {"literal": value})))
    def body_value(value):
        if value == marker:
            return {"$slot": slot("JSON_BODY")}
        if isinstance(value, dict):
            return {key: body_value(child) for key, child in value.items()}
        if isinstance(value, list):
            return [body_value(child) for child in value]
        return value
    payload = dict(method=template.method, path=path, query=query)
    if template.json_body:
        payload["body"] = dict(kind="JSON", value=body_value(template.json_body))
    payload["input_slots"] = slots
    return HttpRequestTemplate.model_validate_json(json.dumps(payload), strict=True)


class CheckRuntimeBuilder:
    def __init__(self, *, uow_factory, var_dir, preparation, business_boundaries, credentials, registry):
        self._uow_factory, self._var_dir = uow_factory, var_dir.resolve()
        self._preparation, self._boundaries = preparation, business_boundaries
        self._credentials, self._registry = credentials, registry

    def build(self, project_id, *, work=None):
        if work is None:
            with self._uow_factory() as current:
                return self.build(project_id, work=current)
        boundary = self._boundaries.view(project_id, work=work)
        understanding = work.application_understanding.get(project_id)
        if understanding is None or not understanding.source_fingerprint or not understanding.confirmed_endpoint:
            raise _incomplete("CHECK_SOURCE_UNAVAILABLE")
        registered = self._registry.snapshot(project_id)
        if registered is not None and registered.source_fingerprint != understanding.source_fingerprint:
            raise _incomplete("CHECK_RUNTIME_SOURCE_STALE")
        identity_ids, configs, specs, target = set(), [], {}, None
        preparation = {item.action_id: item for item in self._preparation.get(project_id).actions}
        resource_windows = {} if registered is None else {item.binding_fingerprint: item.exclusive_resource_window
            for item in registered.resource_windows}
        for action in boundary.actions:
            execution = work.action_preparation.execution(action.action_id, action.revision)
            if execution is None:
                raise _incomplete("ACTION_EXECUTION_MISSING")
            self._check_binding(work, execution, action, understanding)
            recording = work.recordings.get(execution.source_recording_id)
            source_job = work.jobs.get_by_recording(recording.recording_id)
            source = RecordingRequestStore(self._var_dir).load_history(source_job.job_id, expected_hash=source_job.request_hash)
            if target is not None and target != source.target_scope:
                raise _incomplete("CHECK_TARGET_SCOPE_CONFLICT")
            target = source.target_scope
            flow_path = RecordingLifecycle.flow_path(self._var_dir, recording)
            reject_check_links(self._var_dir, flow_path)
            raw = read_check_bytes(flow_path)
            if len(raw) > 1_048_576 or hashlib.sha256(raw).hexdigest() != execution.flow_sha256:
                raise _incomplete("ACTION_FLOW_STALE")
            flow = Flow.model_validate_json(raw, strict=True)
            if flow.id != execution.flow_id or (flow.business_action_id, flow.action_revision, flow.subject_test_identity_id,
                flow.resource_owner_test_identity_id) != (action.action_id, action.revision,
                execution.subject_test_identity_id, execution.resource_owner_test_identity_id):
                raise _incomplete("ACTION_FLOW_STALE")
            steps = self._ordered_steps(flow)
            config = dict(action_id=action.action_id, action_revision=action.revision,
                action_semantic_fingerprint=action.semantic_fingerprint, display_name=action.display_name,
                primary_resource_concept=action.primary_resource_concept,
                state_changing=action.state_changing, flow_id=flow.id, flow_sha256=execution.flow_sha256,
                execution_binding_fingerprint=execution.binding_fingerprint, steps=steps, proofs=[])
            effects = {effect.effect_id: effect for effect in action.effect_catalog}
            permissions = tuple(item for item in boundary.permission_intents if item.business_action_id == action.action_id)
            protected = {effect for permission in permissions for effect in permission.protected_effect_ids}
            for effect_id in sorted(protected):
                binding = work.action_preparation.evidence(action.action_id, action.revision, effect_id)
                if binding is None:
                    raise _incomplete("EFFECT_EVIDENCE_MISSING")
                self._check_binding(work, binding, action, understanding)
                effect = effects[effect_id]
                # 证明来源 owner 是采集来源，不替换当前 Case 的 owner，也不复用其他 Case 的观察结果。
                proof = dict(effect_id=effect_id, effect_kind=effect.effect_kind.value,
                    business_label=effect.business_label, resource_concept=effect.resource_concept,
                    expected_state=effect.expected_state, protected_projection=effect.protected_projection,
                    binding_fingerprint=binding.binding_fingerprint, observation_identity_id=binding.subject_test_identity_id,
                    source_label=effect.business_label, source_location=f"recordings/{binding.source_recording_id}/{binding.step_id}")
                if binding.kind is ActionEvidenceKind.REGISTERED_OBSERVER:
                    runtime = self._registry.proof(project_id, binding.observer_reference, effect_id)
                    if runtime is None or runtime.effect != effect or not (runtime.closure_supported and runtime.resource_correlation_supported):
                        raise _incomplete("REGISTERED_EFFECT_PROOF_UNAVAILABLE")
                    specs[runtime.spec.observer_id] = runtime.spec.model_dump(mode="json")
                    for auxiliary in runtime.auxiliary_sources:
                        specs[auxiliary.spec.observer_id] = auxiliary.spec.model_dump(mode="json")
                        identity_ids.add(auxiliary.source.observation_identity_id)
                    proof["auxiliary_sources"] = [item.source.model_dump(mode="json") for item in runtime.auxiliary_sources]
                    proof.update(rule="REGISTERED_EFFECT", observer_id=runtime.spec.observer_id,
                        descriptor_fingerprint=runtime.reference.descriptor_fingerprint,
                        observation_identity_id=runtime.observation_identity_id, source_label=runtime.source_label,
                        source_location=runtime.source_location, exclusive_resource_window=runtime.exclusive_resource_window)
                else:
                    derived = derive_effect_proof(effect, binding, "resource-placeholder")
                    proof.update(rule=derived.rule, request=recorded_request_template(binding.request_template).model_dump(mode="json"))
                    # 录制本身没有证明独占窗口；需要受控注册明确提供，不能靠模板名猜测。
                    proof["exclusive_resource_window"] = resource_windows.get(binding.binding_fingerprint, False)
                config["proofs"].append(proof)
                identity_ids.add(proof["observation_identity_id"])
            if action.state_changing:
                recovery = work.action_preparation.recovery(action.action_id, action.revision)
                if recovery is None:
                    raise _incomplete("RECOVERY_MISSING")
                self._check_binding(work, recovery, action, understanding)
                config["recovery"] = dict(binding_fingerprint=recovery.binding_fingerprint,
                    source_subject_identity_id=recovery.subject_test_identity_id,
                    request=recorded_request_template(recovery.request_template).model_dump(mode="json"))
                identity_ids.add(recovery.subject_test_identity_id)
            # 只冻结 A1 当前槽位实际选择的身份，不能把同项目所有账号凭据一并注入。
            prepared = preparation.get(action.action_id)
            if prepared is None:
                raise _incomplete("CHECK_PLAN_INCOMPLETE")
            identity_ids.update(slot.test_identity_id for slot in prepared.identity_requirements.slots
                if slot.test_identity_id is not None and slot.status.value == "SATISFIED")
            configs.append(config)
        if target is None:
            raise _incomplete("CHECK_PLAN_INCOMPLETE")
        if registered is not None and registered.target is not None:
            if registered.target != target:
                raise _incomplete("CHECK_TARGET_SCOPE_CONFLICT")
        budget = registered.budget if registered is not None else None
        if budget is None:
            budget = CheckBudget(max_requests=target.max_requests, request_timeout_us=int(target.timeout_seconds * 1_000_000),
                max_duration_us=300_000_000, max_response_bytes=target.max_response_bytes,
                max_cases=8192, recovery_reserve_requests=min(8, target.max_requests - 1))
        verification = {} if registered is None else {item.identity_id: item.verification for item in registered.identities}
        identities = []
        actor_labels = {(actor.actor_id, actor.revision): actor.display_name for actor in boundary.actors}
        for identity_id in sorted(identity_ids):
            record = work.test_identities.get(identity_id)
            if record is None or record.project_id != project_id:
                raise _incomplete("TEST_IDENTITY_UNAVAILABLE")
            binding = self._credentials.profile_identity(record)
            actor_label = actor_labels.get((record.actor_id, record.actor_revision))
            if actor_label is None:
                raise _incomplete("TEST_IDENTITY_UNAVAILABLE")
            identities.append(dict(identity_id=identity_id, actor_id=record.actor_id, actor_revision=record.actor_revision,
                identity_fingerprint=identity_source_fingerprint(record), label=record.label,
                actor_label=actor_label,
                binding=binding.binding.model_dump(mode="json"), verification=verification[identity_id].model_dump(mode="json") if identity_id in verification else None))
        for config in configs:
            config["steps"] = derive_target_classifiers(config, specs, identities)
        return CheckRuntimeBundle.model_validate_json(json.dumps(dict(project_id=project_id,
            source_fingerprint=understanding.source_fingerprint, target=target.model_dump(mode="json"),
            budget=budget.model_dump(mode="json"), identities=identities, actions=configs, observers=list(specs.values()))), strict=True)

    def _check_binding(self, work, binding, action, understanding):
        reasons = self._preparation._bindings._source_reasons(work, binding, action, understanding)
        if reasons:
            raise _incomplete(reasons[0])
        if getattr(binding, "source_recording_id", None) is not None:
            draft = work.flow_drafts.latest(binding.source_recording_id)
            if draft is None or hashlib.sha256(canonical_flow_draft_json_bytes(draft.draft)).hexdigest() != binding.source_draft_sha256:
                raise _incomplete("RECORDING_SOURCE_STALE")

    @staticmethod
    def _ordered_steps(flow):
        pending = {step.id: step for step in flow.steps}
        visited, result = set(), []
        while pending:
            ready = [step for step in pending.values() if set(step.depends_on_step_ids) <= visited]
            ready.sort(key=lambda step: (step.id == flow.target_step_id, step.id))
            if not ready:
                raise _incomplete("ACTION_FLOW_STALE")
            step = ready[0]
            result.append(dict(step_id=step.id, purpose=step.purpose.value,
                request=step.request_template.model_dump(mode="json"), classifier=step.classifier.model_dump(mode="json"),
                depends_on_step_ids=step.depends_on_step_ids))
            visited.add(step.id)
            del pending[step.id]
        return result


def derive_target_classifiers(config, specs, identities):
    """只派生新检查快照的 TARGET 分类；历史录制 Flow 与 SETUP 原样保留。"""
    action = CheckActionConfig.model_validate_json(json.dumps(config), strict=True)
    try:
        parsed_specs = {key: ObserverSpec.model_validate_json(json.dumps(value), strict=True) for key, value in specs.items()}
    except ValueError:
        raise _incomplete("ASYNC_COMPLETION_BINDING_INVALID") from None
    try:
        candidates = async_completion_candidates(action, parsed_specs,
            {item["identity_id"] for item in identities if item.get("verification") is not None})
    except ValueError:
        raise _incomplete("ASYNC_COMPLETION_CONFLICT") from None
    steps = []
    for step in action.steps:
        if step.purpose != "TARGET":
            steps.append(step.model_dump(mode="json"))
            continue
        classifier = step.classifier
        changes = {}
        accepted = {status for predicate in classifier.accepted if predicate.kind is HttpPredicateKind.STATUS_IN
                    for status in predicate.statuses}
        if not classifier.denied and classifier.accepted and all(
                predicate.kind is HttpPredicateKind.STATUS_IN for predicate in classifier.accepted):
            denied = tuple(status for status in (401, 403) if status not in accepted)
            if denied:
                changes["denied"] = (HttpPredicate(kind=HttpPredicateKind.STATUS_IN, statuses=denied),)
        if classifier.completion_binding is not None:
            if classifier.completion_binding not in candidates:
                raise _incomplete("ASYNC_COMPLETION_BINDING_INVALID")
        elif 202 in accepted:
            if len(candidates) > 1:
                raise _incomplete("ASYNC_COMPLETION_AMBIGUOUS")
            if candidates:
                changes["completion_binding"] = next(iter(candidates))
        derived = HttpOutcomeClassifier.model_validate(classifier.model_dump() | changes)
        steps.append(step.model_copy(update={"classifier": derived}).model_dump(mode="json"))
    return steps
