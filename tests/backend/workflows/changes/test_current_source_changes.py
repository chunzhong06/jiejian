# 使用真实受控扫描与 SQLite 聚合验证声明不充当 diff、权限守恒和失败事务回滚。
import pytest

from product.backend.core.errors import JiejianError
from product.backend.infra.storage.source_changes import SourceChangeRepository
from product.backend.workflows.changes.service import CurrentSourceChangeService
from tests.fixtures.action_preparation import build_preparation_harness


@pytest.fixture
def harness(tmp_path):
    harness = build_preparation_harness(tmp_path)
    core = harness.core
    current = core.application_understanding.get(harness.project_id)
    core.application_understanding.analyze_source_for_change(harness.project_id,revision=current.revision)
    service = CurrentSourceChangeService(uow_factory=core.uow_factory,understanding=core.application_understanding,
        boundaries=core.business_boundaries)
    try:
        yield harness,service
    finally:
        harness.close()


def test_claimed_path_is_only_hint_and_stale_mapping_never_auto_rebinds(harness):
    current,service = harness
    core,project = current.core,current.project_id
    before = core.business_boundaries.view(project)
    (current.source_root/"actual.py").write_text("def changed(): return 2\n",encoding="utf-8")
    value = service.submit(project,reason="登记实际修改",claimed_paths=("claimed.py",))
    assert value.manifest.claimed_paths == ("claimed.py",)
    assert value.change_set.added_paths == ("actual.py",)
    assert "claimed.py" not in value.change_set.changed_paths
    after = core.business_boundaries.view(project)
    assert (before.policy_epoch,before.permission_intents)==(after.policy_epoch,after.permission_intents)
    assert value.revalidation.status == "MAPPING_REVIEW_REQUIRED"
    assert service.get(project,value.manifest.change_id) == (value.manifest,value.change_set,value.assessment)
    assert service.latest(project).manifest == value.manifest
    (current.source_root/"actual.py").write_text("def changed(): return 3\n",encoding="utf-8")
    assert service.inspect_revalidation(project,value.manifest.change_id).status == "SOURCE_STALE"


def test_failed_aggregate_transaction_keeps_no_half_change(harness,monkeypatch):
    current,service = harness
    original = SourceChangeRepository.add_current_change
    def failed(self,*args):
        original(self,*args)
        raise RuntimeError("injected aggregate failure")
    monkeypatch.setattr(SourceChangeRepository,"add_current_change",failed)
    (current.source_root/"actual.py").write_text("def changed(): return 2\n",encoding="utf-8")
    with pytest.raises(RuntimeError,match="injected"):
        service.submit(current.project_id,reason="事务失败对照")
    with current.core.uow_factory() as work:
        assert work.source_changes.current_changes(current.project_id)==()
        understanding = work.application_understanding.get(current.project_id)
        assert work.source_changes.snapshot_for_fingerprint(current.project_id,understanding.source_fingerprint) is not None


@pytest.mark.parametrize("path",["../escape.py","C:/escape.py","/escape.py","a//b.py"])
def test_invalid_claimed_paths_rejected_before_scanning(harness,path,monkeypatch):
    current,service = harness
    def forbidden(*args,**kwargs):
        raise AssertionError("invalid input must not scan")
    monkeypatch.setattr(current.core.application_understanding,"analyze_source_for_change",forbidden)
    with pytest.raises((ValueError,JiejianError)):
        service.submit(current.project_id,reason="错误路径",claimed_paths=(path,))


def test_concurrent_human_policy_change_is_kept_but_change_registration_rolls_back(harness, monkeypatch):
    from product.backend.workflows.business_boundaries.models import BoundaryMaintenanceCommand
    from product.backend.core.permission_semantics import PermissionExpectation
    current, service = harness
    core, project = current.core, current.project_id
    before = core.business_boundaries.view(project).policy_epoch
    analyze = core.application_understanding.analyze_source_for_change
    def changed(*args, **kwargs):
        result = analyze(*args, **kwargs)
        draft = core.business_boundaries.maintenance_draft(project)
        available = {item.candidate_id for item in draft.candidate_options if item.evidence_available}
        actors = tuple(item.model_copy(update={"source_candidate_ids": tuple(key for key in item.source_candidate_ids if key in available)}) for item in draft.actors)
        actions = tuple(item.model_copy(update={"source_candidate_ids": tuple(key for key in item.source_candidate_ids if key in available)}) for item in draft.actions)
        permissions = (draft.permissions[0].model_copy(update={"expectation": PermissionExpectation.DENY}), *draft.permissions[1:])
        proposal = core.business_boundaries.create_maintenance_proposal(project, BoundaryMaintenanceCommand(
            expected_boundary_state_fingerprint=draft.boundary_state_fingerprint, actors=actors,
            actions=actions, permissions=permissions, provenance="并发人工变更权限"))
        core.business_boundaries.approve(project, proposal.proposal.proposal_id,
            expected_fingerprint=proposal.proposal.proposal_fingerprint, reason="确认并发权限变更")
        return result
    monkeypatch.setattr(core.application_understanding, "analyze_source_for_change", changed)
    (current.source_root / "new.py").write_text("# 受控源码变更。\nvalue = 2\n", encoding="utf-8")
    with pytest.raises(JiejianError) as error:
        service.submit(project, reason="扫描期间权限发生变化")
    assert "源码分析期间" in error.value.to_dict()["message"], error.value.to_dict()
    assert core.business_boundaries.view(project).policy_epoch > before
    with core.uow_factory() as work:
        assert work.source_changes.current_changes(project) == ()


@pytest.mark.parametrize("during_commit", [False, True])
def test_ordinary_check_revalidates_real_source_without_change_id(tmp_path, monkeypatch, during_commit):
    from tests.fixtures.check_service import ready_check_harness
    current = ready_check_harness(tmp_path)
    core, project = current.core, current.project_id
    try:
        preview = core.checks.preview(project)
        inspect = core.checks._source_inspector
        calls = 0
        def change_source(project_id):
            nonlocal calls
            calls += 1
            if calls == (2 if during_commit else 1):
                (current.source_root / "new.py").write_text("# 检查提交前的真实变化。\nvalue = 2\n", encoding="utf-8")
            return inspect(project_id)
        monkeypatch.setattr(core.checks, "_source_inspector", change_source)
        with pytest.raises(JiejianError):
            core.checks.submit(project, expected_plan_fingerprint=preview.plan_fingerprint, idempotency_key="source-drift")
        with core.uow_factory() as work:
            assert not [job for job in work.jobs.list_for_project(project) if job.operation_type == "CHECK"]
    finally:
        current.close()


def test_missing_complete_snapshot_cannot_register_change(harness, monkeypatch):
    from contextlib import contextmanager
    current, service = harness
    @contextmanager
    def factory(**kwargs):
        with current.core.uow_factory(**kwargs) as work:
            work.source_changes.snapshot_for_fingerprint = lambda *args: None
            yield work
    monkeypatch.setattr(service, "_uow_factory", factory)
    with pytest.raises(JiejianError, match="完整快照"):
        service.submit(current.project_id, reason="缺完整扫描快照")
    with current.core.uow_factory() as work:
        assert work.source_changes.current_changes(current.project_id) == ()


def test_known_secret_in_change_reason_is_rejected_without_public_leak(harness):
    import json
    current, service = harness
    secret = "test-only-sensitive-value-123456789"
    service._uow_factory = lambda **kwargs: current.core.uow_factory(known_secrets=(secret,))
    with pytest.raises(JiejianError) as failure:
        service.submit(current.project_id, reason=secret)
    assert secret not in json.dumps(failure.value.to_dict())
    with current.core.uow_factory() as work:
        assert work.source_changes.current_changes(current.project_id) == ()


def test_change_lookup_is_project_scoped(harness):
    current, service = harness
    value = service.submit(current.project_id, reason="登记本项目变化")
    with pytest.raises(JiejianError):
        service.get("foreign-project", value.manifest.change_id)
