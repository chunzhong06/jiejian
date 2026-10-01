# 用真实 SQLite 和受控源码扫描验证连续交付、幂等重放及整笔事务回滚。
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest

from product.backend.core.errors import JiejianError
from product.backend.infra.storage.development import DevelopmentRepository
from product.backend.workflows.development import DevelopmentService
from tests.fixtures.action_preparation import build_preparation_harness


@pytest.fixture
def development(tmp_path):
    harness = build_preparation_harness(tmp_path)
    core = harness.core
    current = core.application_understanding.get(harness.project_id)
    core.application_understanding.analyze_source_for_change(harness.project_id, revision=current.revision)
    service = DevelopmentService(uow_factory=core.uow_factory, understanding=core.application_understanding,
        boundaries=core.business_boundaries, changes=core.source_changes)
    try:
        yield harness, service
    finally:
        harness.close()


def _start(harness, service):
    created = service.create(harness.project_id, operation_id=uuid4().hex, title="导出体验优化", goal="保留权限并改进导出")
    accepted = service.accept(harness.project_id, created.task_id, operation_id=uuid4().hex,
        expected_version=created.task_version, context_id=created.context_id, client_name="Codex test")
    return accepted


def test_create_replay_conflict_and_one_active_task(development):
    harness, service = development
    key = uuid4().hex
    values = dict(operation_id=key, title="导出优化", goal="保持原权限")
    first = service.create(harness.project_id, **values)
    assert service.create(harness.project_id, **values) == first
    with pytest.raises(JiejianError, match="不同内容"):
        service.create(harness.project_id, **{**values, "goal": "新的目标"})
    with pytest.raises(JiejianError, match="未结束任务"):
        service.create(harness.project_id, **{**values, "operation_id": uuid4().hex})
    assert len(service.list(harness.project_id)) == 1
    assert service.receipt("other", "CREATE", key) is None


def test_concurrent_same_key_returns_one_persistent_task(development):
    harness, service = development
    key = uuid4().hex
    with ThreadPoolExecutor(max_workers=2) as executor:
        calls = [executor.submit(service.create, harness.project_id, operation_id=key, title="并发请求", goal="同一任务") for _ in range(2)]
        receipts = [call.result(timeout=20) for call in calls]
    assert receipts[0] == receipts[1]
    assert len(service.list(harness.project_id)) == 1


def test_two_deliveries_keep_relative_and_cumulative_start_and_replay_after_source_changes(development):
    harness, service = development
    accepted = _start(harness, service)
    source = harness.source_root / "delivery.py"
    source.write_text("# 第一批修改。\nvalue = 1\n", encoding="utf-8")
    args = dict(operation_id=uuid4().hex, expected_version=accepted.task_version, context_id=accepted.context_id,
        reason="第一批真实交付", submitted_by="Codex test", claimed_paths=("delivery.py",))
    first = service.deliver(harness.project_id, accepted.task_id, **args)
    source.write_text("# 第二批修改。\nvalue = 2\n", encoding="utf-8")
    assert service.deliver(harness.project_id, accepted.task_id, **args) == first
    second = service.deliver(harness.project_id, accepted.task_id, **{**args,
        "operation_id": uuid4().hex, "expected_version": first.task_version, "reason": "第二批真实交付"})
    with harness.core.uow_factory() as work:
        deliveries = work.development.deliveries(harness.project_id, accepted.task_id)
        assert len(deliveries) == 2
        assert deliveries[0].ordinal == 2 and deliveries[1].ordinal == 1
        assert deliveries[0].previous_delivery_id == deliveries[1].delivery_id
        assert deliveries[0].start_snapshot_id == deliveries[1].start_snapshot_id
        first_change = work.source_changes.current_change(harness.project_id, first.change_id)[1]
        second_change = work.source_changes.current_change(harness.project_id, second.change_id)[1]
        assert first_change.added_paths == ("delivery.py",)
        assert second_change.modified_paths == ("delivery.py",)
        assert second_change.previous_snapshot_id == first_change.current_snapshot_id


def test_receipt_failure_rolls_back_understanding_change_delivery_and_task(development, monkeypatch):
    harness, service = development
    accepted = _start(harness, service)
    before = harness.core.application_understanding.get(harness.project_id)
    (harness.source_root / "delivery.py").write_text("# 必须与回执一起回滚。\nvalue = 1\n", encoding="utf-8")
    original = DevelopmentRepository.add_receipt
    def fail_after_insert(self, receipt):
        original(self, receipt)
        if receipt.kind == "DELIVER":
            raise RuntimeError("receipt failure")
    monkeypatch.setattr(DevelopmentRepository, "add_receipt", fail_after_insert)
    key = uuid4().hex
    with pytest.raises(RuntimeError, match="receipt failure"):
        service.deliver(harness.project_id, accepted.task_id, operation_id=key, expected_version=accepted.task_version,
            context_id=accepted.context_id, reason="回滚验证", submitted_by="Codex test")
    assert service.receipt(harness.project_id, "DELIVER", key) is None
    assert service.task(harness.project_id, accepted.task_id).version == accepted.task_version
    assert harness.core.application_understanding.get(harness.project_id) == before
    with harness.core.uow_factory() as work:
        assert work.development.deliveries(harness.project_id, accepted.task_id) == ()
        assert work.source_changes.current_changes(harness.project_id) == ()


def test_revision_invalidates_old_context_and_close_has_no_verdict(development):
    harness, service = development
    accepted = _start(harness, service)
    revised = service.revise(harness.project_id, accepted.task_id, operation_id=uuid4().hex,
        expected_version=accepted.task_version, title="新目标", goal="仍沿用批准权限")
    with pytest.raises(JiejianError, match="上下文"):
        service.deliver(harness.project_id, accepted.task_id, operation_id=uuid4().hex,
            expected_version=revised.task_version, context_id=accepted.context_id, reason="旧上下文", submitted_by="Codex test")
    closed = service.finish(harness.project_id, accepted.task_id, operation_id=uuid4().hex, expected_version=revised.task_version)
    task = service.task(harness.project_id, accepted.task_id)
    assert task.status == "CLOSED" and "verdict" not in task.model_dump()
    assert closed.kind == "CLOSE"
    new = service.create(harness.project_id, operation_id=uuid4().hex, title="下一项任务", goal="继续修改")
    assert new.task_id != task.task_id


def test_delivery_cumulative_diff_paging_and_cancelled_history(development):
    harness, service = development
    accepted = _start(harness, service)
    path = harness.source_root / "delivery.py"
    path.write_text("# 第一批\nvalue = 1\n", encoding="utf-8")
    first = service.deliver(harness.project_id, accepted.task_id, operation_id=uuid4().hex,
        expected_version=accepted.task_version, context_id=accepted.context_id, reason="第一批", submitted_by="Codex test")
    path.write_text("# 第二批\nvalue = 2\n", encoding="utf-8")
    second = service.deliver(harness.project_id, accepted.task_id, operation_id=uuid4().hex,
        expected_version=first.task_version, context_id=accepted.context_id, reason="第二批", submitted_by="Codex test")
    details = service.delivery_details(harness.project_id, second.change_id)
    assert details["relative_change"]["modified_paths"] == ["delivery.py"]
    assert details["cumulative_change"]["added_paths"] == ["delivery.py"]
    assert details["verification"]["run_id"] is None
    page = service.delivery_page(harness.project_id, accepted.task_id, limit=1)
    assert page["items"][0]["delivery"]["delivery_id"] == second.delivery_id and page["next_ordinal"] == 2
    earlier = service.delivery_page(harness.project_id, accepted.task_id, before_ordinal=page["next_ordinal"], limit=1)
    assert earlier["items"][0]["delivery"]["delivery_id"] == first.delivery_id and earlier["next_ordinal"] is None
    service.finish(harness.project_id, accepted.task_id, operation_id=uuid4().hex, expected_version=second.task_version, cancel=True)
    newer = service.create(harness.project_id, operation_id=uuid4().hex, title="下一项任务", goal="继续开发")
    history = service.history(harness.project_id, limit=1)
    assert history["items"][0]["task_id"] == newer.task_id
    history = service.history(harness.project_id, before_task_id=history["next_task_id"], limit=1)
    assert history["items"][0]["status"] == "CANCELLED" and history["items"][0]["title"] == "导出体验优化"
    assert service.delivery_details("other", second.change_id) is None
    with pytest.raises(JiejianError):
        service.history("other", before_task_id=accepted.task_id)


def test_unaccepted_context_and_stale_task_version_do_not_scan(development, monkeypatch):
    harness, service = development
    created = service.create(harness.project_id, operation_id=uuid4().hex, title="待接收", goal="需要明确接收")
    def forbidden(*args, **kwargs):
        raise AssertionError("must not scan")
    monkeypatch.setattr(harness.core.source_changes, "prepare_change", forbidden)
    for version in (0, created.task_version):
        with pytest.raises(JiejianError):
            service.deliver(harness.project_id, created.task_id, operation_id=uuid4().hex,
                expected_version=version, context_id=created.context_id, reason="不应登记", submitted_by="Codex test")


def test_new_service_recovers_receipt_without_scanning_again(development, monkeypatch):
    harness, service = development
    accepted = _start(harness, service)
    args = dict(operation_id=uuid4().hex, expected_version=accepted.task_version,
        context_id=accepted.context_id, reason="响应丢失", submitted_by="Codex test")
    saved = service.deliver(harness.project_id, accepted.task_id, **args)
    restored = DevelopmentService(uow_factory=harness.core.uow_factory, understanding=harness.core.application_understanding,
        boundaries=harness.core.business_boundaries, changes=harness.core.source_changes)
    def forbidden(*args, **kwargs):
        raise AssertionError("replay must not scan")
    monkeypatch.setattr(harness.core.source_changes, "prepare_change", forbidden)
    assert restored.receipt(harness.project_id, "DELIVER", args["operation_id"]) == saved
    assert restored.deliver(harness.project_id, accepted.task_id, **args) == saved


def test_competing_deliveries_require_new_task_version(development):
    harness, service = development
    accepted = _start(harness, service)
    def deliver():
        try:
            return service.deliver(harness.project_id, accepted.task_id, operation_id=uuid4().hex,
                expected_version=accepted.task_version, context_id=accepted.context_id, reason="竞争交付", submitted_by="Codex test")
        except JiejianError:
            return None
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(deliver) for _ in range(2)]
        values = [future.result(timeout=20) for future in futures]
    assert len([value for value in values if value is not None]) == 1
    with harness.core.uow_factory() as work:
        assert len(work.development.deliveries(harness.project_id, accepted.task_id)) == 1
        assert len(work.source_changes.current_changes(harness.project_id)) == 1


def test_runtime_activation_recovers_saved_process_without_loading_twice(development, monkeypatch):
    from product.backend.workflows.runtime_activation import RuntimeActivationService
    from product.protocols.runtime_identity import ControlledRuntimeReference
    harness, service = development
    accepted = _start(harness, service)
    delivery = service.deliver(harness.project_id, accepted.task_id, operation_id=uuid4().hex,
        expected_version=accepted.task_version, context_id=accepted.context_id, reason="加载修订", submitted_by="Codex test")
    calls, references = [], []
    def load(project, source):
        calls.append(project)
        value = ControlledRuntimeReference(instance_id="rti_" + "1" * 32, manifest_fingerprint="a" * 64,
            source_fingerprint=source, process_id=123, process_created_at=456, owner_id="exp_" + "2" * 32)
        references.append(value)
        return value
    activation = RuntimeActivationService(uow_factory=harness.core.uow_factory, loader=load,
        reader=lambda project: references[-1] if references else None, clock=lambda: 123)
    original = DevelopmentRepository.finish_runtime_receipt
    def fail_receipt(*args):
        raise OSError("lost database response")
    monkeypatch.setattr(DevelopmentRepository, "finish_runtime_receipt", fail_receipt)
    key = uuid4().hex
    with pytest.raises(JiejianError, match="可能已经加载"):
        activation.activate(harness.project_id, delivery.delivery_id, operation_id=key, expected_version=delivery.task_version)
    assert activation.receipt(harness.project_id, key).status == "UNKNOWN"
    monkeypatch.setattr(DevelopmentRepository, "finish_runtime_receipt", original)
    recovered = activation.activate(harness.project_id, delivery.delivery_id, operation_id=key, expected_version=delivery.task_version)
    assert recovered.status == "SUCCEEDED" and len(calls) == 1
    assert activation.activate(harness.project_id, delivery.delivery_id, operation_id=key, expected_version=delivery.task_version) == recovered
    assert len(calls) == 1

# 轻量登记不要求手工建任务；原子性、权限漂移与重放仍按真实持久层验证。
def test_lightweight_registration_creates_context_without_acceptance_and_replays(development, monkeypatch):
    harness, service = development
    preview = service.registration_preview(harness.project_id)
    assert service.active(harness.project_id) is None
    (harness.source_root / "simple.py").write_text("# 修改后才登记。\nvalue = 1\n", encoding="utf-8")
    args = dict(operation_id=uuid4().hex, expected_registration_fingerprint=preview["fingerprint"], submitted_by="MCP · Codex")
    first = service.register_change(harness.project_id, **args)
    assert first.change_id and first.delivery_id
    assert service.view(harness.project_id, first.task_id)["acceptance"] is None
    def forbidden(*args, **kwargs):
        raise AssertionError("replay must not scan")
    monkeypatch.setattr(harness.core.source_changes, "prepare_change", forbidden)
    assert service.register_change(harness.project_id, **args) == first
    with pytest.raises(JiejianError, match="不同内容"):
        service.register_change(harness.project_id, **{**args, "reason": "changed payload"})


def test_lightweight_registration_rolls_back_new_context_with_failed_receipt(development, monkeypatch):
    harness, service = development
    before = harness.core.application_understanding.get(harness.project_id)
    preview = service.registration_preview(harness.project_id)
    original = DevelopmentRepository.add_receipt
    def fail(self, receipt):
        original(self, receipt)
        raise RuntimeError("atomic receipt failure")
    monkeypatch.setattr(DevelopmentRepository, "add_receipt", fail)
    key = uuid4().hex
    with pytest.raises(RuntimeError, match="atomic receipt failure"):
        service.register_change(harness.project_id, operation_id=key, expected_registration_fingerprint=preview["fingerprint"])
    assert service.active(harness.project_id) is None
    assert service.receipt(harness.project_id, "DELIVER", key) is None
    assert harness.core.application_understanding.get(harness.project_id) == before
    with harness.core.uow_factory() as work:
        assert work.source_changes.current_changes(harness.project_id) == ()


def test_lightweight_registration_concurrent_replay_and_stale_preview(development):
    harness, service = development
    preview = service.registration_preview(harness.project_id)
    args = dict(operation_id=uuid4().hex, expected_registration_fingerprint=preview["fingerprint"])
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = [pool.submit(service.register_change, harness.project_id, **args) for _ in range(2)]
        receipts = [result.result(timeout=25) for result in results]
    assert receipts[0] == receipts[1]
    assert len(service.list(harness.project_id)) == 1
    with pytest.raises(JiejianError, match="登记范围已变化"):
        service.register_change(harness.project_id, **{**args, "operation_id": uuid4().hex})
    next_preview = service.registration_preview(harness.project_id)
    next_receipt = service.register_change(harness.project_id, operation_id=uuid4().hex,
        expected_registration_fingerprint=next_preview["fingerprint"])
    details = service.delivery_details(harness.project_id, next_receipt.change_id)
    assert details["delivery"]["ordinal"] == 2
    assert details["delivery"]["task_id"] == receipts[0].task_id


def test_lightweight_registration_does_not_overwrite_concurrent_context(development, monkeypatch):
    harness, service = development
    preview = service.registration_preview(harness.project_id)
    prepare = harness.core.source_changes.prepare_change
    def intervening(*args, **kwargs):
        value = prepare(*args, **kwargs)
        service.create(harness.project_id, operation_id=uuid4().hex, title="existing client", goal="explicit context")
        return value
    monkeypatch.setattr(harness.core.source_changes, "prepare_change", intervening)
    with pytest.raises(JiejianError, match="登记期间"):
        service.register_change(harness.project_id, operation_id=uuid4().hex, expected_registration_fingerprint=preview["fingerprint"])
    with harness.core.uow_factory() as work:
        assert work.source_changes.current_changes(harness.project_id) == ()
    assert service.view(harness.project_id, service.active(harness.project_id).task_id)["context"]["title"] == "existing client"
