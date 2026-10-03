# 同一来源漂移必须同时阻断准备、材料读取与正式检查，不改写已保存的绑定。
import pytest
from product.backend.core.errors import JiejianError
from product.backend.workflows.preparation.materials.models import MaterialReference
from tests.fixtures.checks.check_service import ready_check_harness


def test_source_drift_is_rejected_by_all_binding_consumers(tmp_path):
    h = ready_check_harness(tmp_path)
    try:
        core = h.core
        ref = MaterialReference(action_id=h.action.action_id, action_revision=h.action.revision, kind="execution")
        assert core.checks.preview(h.project_id).can_execute
        assert core.preparation_materials.details(h.project_id, ref)["status"] == "SATISFIED"
        with core.uow_factory() as work:
            original = work.action_preparation.execution(h.action.action_id, h.action.revision)
            jobs_before = work.jobs.list_for_project(h.project_id)
            current = work.application_understanding.get(h.project_id)
            work.application_understanding.replace(current.model_copy(update={"source_fingerprint": "f" * 64}))
            work.commit()
        prepared = core.preparation.get(h.project_id).actions[0]
        material = core.preparation_materials.details(h.project_id, ref)
        assert prepared.execution.status.value == "STALE"
        assert material["status"] == "STALE"
        # 原检查先发现资源所有者的实现依据失效；各消费者继续保留这个首要原因。
        assert "RESOURCE_OWNER_SOURCE_STALE" in prepared.execution.reason_codes
        assert "RESOURCE_OWNER_SOURCE_STALE" in material["reason_codes"]
        with pytest.raises(JiejianError):
            core.check_runtime_builder.build(h.project_id)
        assert not core.checks.preview(h.project_id).can_execute
        with core.uow_factory() as work:
            assert work.action_preparation.execution(h.action.action_id, h.action.revision) == original
            assert work.jobs.list_for_project(h.project_id) == jobs_before
    finally:
        h.close()
