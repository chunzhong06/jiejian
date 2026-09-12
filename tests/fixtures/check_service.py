# 经正式录制接受、业务权限与受控注册端口形成可预览/提交的真实应用 fixture。
from product.backend.core.action_preparation import RegisteredObserverReference
from product.backend.workflows.checks.registry import CheckRuntimeRegistration, RegisteredCheckProof
from product.protocols.observer import ObserverSpec
from tests.fixtures.action_preparation import add_recording, build_preparation_harness
import json


def ready_check_harness(tmp_path, *, core=None):
    harness = build_preparation_harness(tmp_path, state_changing=False, core=core)
    core = harness.core
    recording = add_recording(harness)
    core.recording_lifecycle.finalize(recording.recording_id, var_dir=harness.var_dir, now_us=100)
    reference = RegisteredObserverReference(descriptor_id="exp_" + "1" * 32,
        descriptor_fingerprint="a" * 64, observer_id="controlled-proof")
    spec = ObserverSpec.model_validate_json(json.dumps(dict(observer_id=reference.observer_id, observer_type="OWNER_API",
        target=dict(target_id="object", locator=dict(locator_type="OWNER_API", relative_path_template="/objects/{resource_id}"),
            normalization_id="business-state", normalization_version="1"), phases=["BEFORE", "AFTER"], required=True,
        budget=dict(timeout_us=1_000_000, max_rows=1, max_bytes=262_144))))
    with core.uow_factory() as work:
        source = work.application_understanding.get(harness.project_id).source_fingerprint
    registration = CheckRuntimeRegistration(project_id=harness.project_id, source_fingerprint=source,
        proofs=(RegisteredCheckProof(reference=reference, effect=harness.action.effect_catalog[0], spec=spec,
            observation_identity_id=harness.identities[0].identity_id, source_label="业务状态观察",
            source_location="routes.py", closure_supported=True, resource_correlation_supported=True,
            exclusive_resource_window=True),))
    core.check_registry.register(registration)
    core.preparation_bindings.register_observer(recording.recording_id, effect_id=harness.effect_id,
        reference=reference, now_us=101)
    return harness
