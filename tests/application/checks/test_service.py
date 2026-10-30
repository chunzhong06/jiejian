# 验证真实准备材料到冻结 CHECK 的预览、幂等、提交 checkpoint 与秘密读取边界。
from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy import event

from product.backend.domain.applications.models import CandidateDecision
from product.backend.domain.errors import JiejianError
from product.backend.infrastructure.runtime.jobs.check_requests import CheckRequestStore
from product.backend.infrastructure.runtime.paths import RuntimePaths
from product.protocols.checks.execution_request import canonical_execution_request_bytes
from tests.support.builders.preparation.action_preparation import build_preparation_harness
from tests.support.builders.checks.check_service import ready_check_harness


def test_registration_read_scope_reuses_only_current_read_and_restores_after_failure():
    from product.backend.application.checks.registry import CheckRuntimeRegistry
    registry=CheckRuntimeRegistry();reads=[]
    registry.bind_persistent_reader(lambda project:reads.append(project))
    with registry.read_scope('first'):
        assert registry.snapshot('first') is None
        with registry.read_scope('first'):assert registry.snapshot('first') is None
        with pytest.raises(RuntimeError):
            with registry.read_scope('second'):
                assert registry.snapshot('second') is None
                raise RuntimeError('interrupted read')
        assert registry.snapshot('first') is None
    assert reads==['first','second']
    with registry.read_scope('first'):assert registry.snapshot('first') is None
    assert reads==['first','second','first']


def test_unprepared_preview_keeps_all_actions_and_never_submits(tmp_path):
    harness = build_preparation_harness(tmp_path)
    try:
        preview = harness.core.checks.preview(harness.project_id)
        assert not preview.can_execute and preview.gaps
        assert preview.action_count == len(preview.actions) == 1
        with harness.core.uow_factory() as work:
            assert work.runs.list_for_project(harness.project_id) == ()
    finally:
        harness.close()


def test_ready_preview_is_readonly_and_does_not_read_secret_values(tmp_path, monkeypatch):
    harness = ready_check_harness(tmp_path)
    try:
        statements = []
        event.listen(harness.core.engine, "before_cursor_execute", lambda _c, _cur, sql, *_args: statements.append(sql))
        monkeypatch.setattr(harness.core.secret_store, "read", lambda _ref: pytest.fail("preview read a secret"))
        preview = harness.core.checks.preview(harness.project_id)
        assert preview.can_execute, preview.model_dump()
        assert preview.case_count == 1 and preview.action_count == 1
        # BEGIN仅建立现有的一致读取事务；预览仍不允许任何业务写语句。
        assert all(sql.strip().upper() == 'BEGIN' or sql.lstrip().upper().startswith(("SELECT", "PRAGMA")) for sql in statements)
        assert harness.core.checks.preview(harness.project_id).plan_fingerprint == preview.plan_fingerprint
    finally:
        harness.close()


def test_submit_freezes_request_and_config_with_one_nonretryable_job(tmp_path, monkeypatch):
    harness = ready_check_harness(tmp_path)
    try:
        core = harness.core
        monkeypatch.setattr(core.secret_store, "read", lambda _ref: pytest.fail("submission read a secret"))
        preview = core.checks.preview(harness.project_id)
        frozen_before = canonical_execution_request_bytes(core.checks._freeze(harness.project_id)[1])
        first = core.checks.submit(harness.project_id, expected_plan_fingerprint=preview.plan_fingerprint, idempotency_key="same")
        repeated = core.checks.submit(harness.project_id, expected_plan_fingerprint=preview.plan_fingerprint, idempotency_key="same")
        assert first.created and not repeated.created and first.job.job_id == repeated.job.job_id
        assert first.job.operation_type == "CHECK" and first.job.max_attempts == 1
        with core.uow_factory() as work:
            observation = work.code_observations.for_target(harness.project_id, "run", first.run.run_id)
        assert observation is not None and observation["source_fingerprint"] == first.run.source_fingerprint
        store = CheckRequestStore(core.var_dir)
        request = store.load(first.job.job_id, expected_hash=first.job.request_hash)
        assert canonical_execution_request_bytes(request) == frozen_before
        assert request.plan_fingerprint == preview.plan_fingerprint
        assert store.load_bundle(first.job.job_id, expected_hash=request.config_fingerprint).identities[0].verification is None
        configs = list(RuntimePaths(core.var_dir).jobs.glob("*/config-*.json"))
        assert len(configs) == 1
    finally:
        harness.close()


def test_source_drift_inside_submit_checkpoint_leaves_no_check_job_or_assets(tmp_path, monkeypatch):
    harness = ready_check_harness(tmp_path)
    try:
        core = harness.core
        preview = core.checks.preview(harness.project_id)
        original = core.job_queue.submit
        def drift(request, **kwargs):
            with core.uow_factory() as work:
                understanding = work.application_understanding.get(harness.project_id)
                work.application_understanding.replace(understanding.model_copy(update={"confirmed_endpoint": "http://127.0.0.1:8766"}))
                work.commit()
            return original(request, **kwargs)
        monkeypatch.setattr(core.job_queue, "submit", drift)
        with pytest.raises(JiejianError) as caught:
            core.checks.submit(harness.project_id, expected_plan_fingerprint=preview.plan_fingerprint, idempotency_key="drift")
        assert caught.value.code == "STATE_PRECONDITION"
        with core.uow_factory() as work:
            assert work.runs.list_for_project(harness.project_id) == ()
        assert list(RuntimePaths(core.var_dir).jobs.glob("*/config-*.json")) == []
    finally:
        harness.close()


def test_candidate_rejection_blocks_prepared_check_without_rewriting_permissions(tmp_path):
    """通过真实候选操作核验读取和提交链，避免空刷新钩子掩盖来源失效。"""
    harness = ready_check_harness(tmp_path)
    try:
        core, project_id = harness.core, harness.project_id
        preview = core.checks.preview(project_id)
        assert preview.can_execute
        before = core.business_boundaries.view(project_id)
        understanding = core.application_understanding.get(project_id)
        core.application_understanding.decide_action(
            project_id, understanding.action_candidates[0].candidate_id,
            revision=understanding.revision, decision=CandidateDecision.REJECTED,
        )
        assert not core.checks.preview(project_id).can_execute
        with pytest.raises(JiejianError) as caught:
            core.checks.submit(project_id, expected_plan_fingerprint=preview.plan_fingerprint,
                               idempotency_key="rejected-candidate")
        assert caught.value.code == "STATE_PRECONDITION"
        after = core.business_boundaries.view(project_id)
        assert after.permission_intents == before.permission_intents
        assert after.policy_epoch == before.policy_epoch
        with core.uow_factory() as work:
            assert work.runs.list_for_project(project_id) == ()
        assert list(RuntimePaths(core.var_dir).jobs.glob("*/config-*.json")) == []
    finally:
        harness.close()


def test_concurrent_duplicate_submission_has_one_job(tmp_path):
    harness = ready_check_harness(tmp_path)
    try:
        core = harness.core
        expected = core.checks.preview(harness.project_id).plan_fingerprint
        def submit(_):
            return core.checks.submit(harness.project_id, expected_plan_fingerprint=expected, idempotency_key="race")
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = tuple(pool.map(submit, range(2)))
        assert sorted(item.created for item in results) == [False, True]
        assert len({item.job.job_id for item in results}) == 1
    finally:
        harness.close()

pytestmark = [pytest.mark.level3]
