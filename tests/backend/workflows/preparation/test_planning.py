# 验证应用层现场计划与严格快照共享事实，能力缺失关闭且不提交检查任务。
from types import SimpleNamespace
import pytest
from sqlalchemy import event
from product.backend.core.errors import JiejianError
from product.backend.core.action_preparation import RegisteredObserverReference
from product.backend.core.check_plan import RegisteredEffectProofCapability
from product.backend.workflows.preparation.bindings import PreparationBindingService
from product.protocols.execution_v3 import canonical_execution_request_v3_bytes, parse_execution_request_v3
from tests.fixtures.action_preparation import build_preparation_harness, add_recording


def test_current_plan_keeps_gaps_and_builder_rejects_without_writing(tmp_path):
    harness = build_preparation_harness(tmp_path)
    try:
        statements = []
        event.listen(harness.core.engine, "before_cursor_execute", lambda connection, cursor, sql, *args: statements.append(sql))
        plan = harness.core.preparation.current_plan(harness.project_id, engine_version="test-1", config_fingerprint="a"*64)
        assert len(plan.actions) == 1 and plan.gaps
        with pytest.raises(JiejianError) as error:
            harness.core.preparation.build_execution_request_v3(harness.project_id, engine_version="test-1",
                config_fingerprint="a"*64, budget_fingerprint="b"*64)
        assert error.value.code == "STATE_PRECONDITION"
        assert all(sql.lstrip().upper().startswith(("SELECT", "PRAGMA")) for sql in statements)
    finally:
        harness.close()


def test_snapshot_requires_exact_registered_capability_and_preserves_source(tmp_path, monkeypatch):
    harness = build_preparation_harness(tmp_path, state_changing=False)
    try:
        core = harness.core
        recording = add_recording(harness)
        core.recording_lifecycle.finalize(recording.recording_id, var_dir=harness.var_dir, now_us=100)
        reference = RegisteredObserverReference(descriptor_id="exp_"+"1"*32,
            descriptor_fingerprint="a"*64, observer_id="controlled-observer")
        capability = RegisteredEffectProofCapability(**reference.model_dump(), effect_id=harness.effect_id,
            closure_supported=True, resource_correlation_supported=True)
        calls = []
        def read(project_id, exact_reference, effect_id):
            calls.append((project_id, exact_reference, effect_id))
            return capability
        binding_service = PreparationBindingService(core.uow_factory, harness.var_dir, test_identities=core.test_identities,
            registered_observers=SimpleNamespace(contains=lambda project, ref: project == harness.project_id and ref == reference))
        binding_service.register_observer(recording.recording_id, effect_id=harness.effect_id, reference=reference, now_us=101)
        core.preparation._bindings = binding_service
        arguments = dict(engine_version="test-1", config_fingerprint="b"*64, budget_fingerprint="c"*64)
        with pytest.raises(JiejianError):
            core.preparation.build_execution_request_v3(harness.project_id, **arguments)
        binding_service._effect_proofs = SimpleNamespace(capability=read)
        request = core.preparation.build_execution_request_v3(harness.project_id, **arguments)
        assert request == parse_execution_request_v3(canonical_execution_request_v3_bytes(request))
        assert request.actions[0].cases[0].permission.intent_id == "pin_"+f"{1:032x}"
        assert calls == [(harness.project_id, reference, harness.effect_id)]
        with core.uow_factory() as work:
            assert all(job.recording_id is not None and job.run_id is None for job in work.jobs.list_for_project(harness.project_id))
        old_view = core.preparation.get(harness.project_id)
        with core.uow_factory() as work:
            understanding = work.application_understanding.get(harness.project_id)
            work.application_understanding.replace(understanding.model_copy(update={"confirmed_endpoint": "http://127.0.0.1:8766"}))
            work.commit()
        # 模拟 GET 已返回而目标随后漂移；装配不能仅凭旧 SATISFIED 创建快照。
        monkeypatch.setattr(core.preparation, "get", lambda _: old_view)
        with pytest.raises(JiejianError) as error:
            core.preparation.build_execution_request_v3(harness.project_id, **arguments)
        assert error.value.code == "STATE_PRECONDITION"
    finally:
        harness.close()
