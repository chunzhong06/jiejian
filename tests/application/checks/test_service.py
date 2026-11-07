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


def test_scenario_candidate_requires_exact_human_review_and_freezes_the_saved_revision(tmp_path):
    import json
    from product.protocols.checks.scenarios import BusinessScenarioRevision,ScenarioReference
    harness=ready_check_harness(tmp_path)
    core,project=harness.core,harness.project_id
    try:
        context=core.business_scenarios.context(project)
        assert context['identities'] and context['actions'][0]['label']
        allowed=next(case for case in context['actions'][0]['cases'] if case['permission']['expectation']=='ALLOW')
        item=dict(id='resource',permission={name:allowed['permission'][name] for name in ('intent_id','revision','intent_hash')},
            subject_identity_id=allowed['subject_test_identity_id'],resource_id=allowed['resource_id'])
        document=BusinessScenarioRevision.model_validate_json(json.dumps(dict(id='bsc_'+'3'*32,project_id=project,revision=1,
            label='已保存的正常业务',experiments=[dict(id='normal',label='正常业务',kind='NORMAL',
                invocations=[dict(id='read',label='读取资料',items=[item])])])) )
        reference=ScenarioReference(scenario_id=document.id,revision=1)
        core.business_scenarios.save(project,document,submitted_via='MCP')
        with pytest.raises(JiejianError,match='本机审阅'):
            core.checks.preview(project,scenario_reference=reference)
        core.business_scenarios.save(project,document)
        preview=core.checks.preview(project,scenario_reference=reference)
        assert preview.can_execute,preview.model_dump()
        assert preview.scenario.document==document and preview.case_count==1
        submitted=core.checks.submit(project,expected_plan_fingerprint=preview.plan_fingerprint,
            idempotency_key='scenario-submit',scenario_reference=reference)
        frozen=CheckRequestStore(harness.var_dir).load(submitted.job.job_id,expected_hash=submitted.job.request_hash)
        assert frozen.scenario.document==document
        newer=document.model_copy(update={'revision':2,'label':'后续编辑'})
        core.business_scenarios.save(project,newer)
        repeated=core.checks.submit(project,expected_plan_fingerprint=preview.plan_fingerprint,
            idempotency_key='scenario-submit',scenario_reference=reference)
        assert not repeated.created and repeated.job.job_id==submitted.job.job_id
        listing=core.business_scenarios.listing(project)
        assert listing['documents']==(dict(id=document.id,revision=2,label='后续编辑',description='',experiment_count=1),)
        assert 'experiments' not in listing['documents'][0]
        assert core.business_scenarios.read(project,document.id,1)==document
        with pytest.raises(JiejianError,match='修订已保存'):
            core.business_scenarios.save(project,document.model_copy(update={'label':'覆写历史'}))
    finally:
        harness.close()


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


def test_selected_scope_freezes_exact_references_and_keeps_old_full_encoding(tmp_path):
    from product.protocols.checks.execution_request import PermissionReference, parse_execution_request
    harness = ready_check_harness(tmp_path)
    try:
        core, project = harness.core, harness.project_id
        full, original, _ = core.checks._freeze(project)
        raw = canonical_execution_request_bytes(original)
        assert b'"selection"' not in raw
        assert canonical_execution_request_bytes(parse_execution_request(raw)) == raw
        permission = original.actions[0].cases[0].permission
        selected = (PermissionReference(**permission.model_dump(include={'intent_id', 'revision', 'intent_hash'})),)
        preview, request, _ = core.checks._freeze(project, selected_permissions=selected)
        assert preview.can_execute and preview.plan_fingerprint != full.plan_fingerprint
        assert request.selection.selected == selected
        assert parse_execution_request(canonical_execution_request_bytes(request)).selection == request.selection
        submitted = core.checks.submit(project, expected_plan_fingerprint=preview.plan_fingerprint,
            idempotency_key='selected', selected_permissions=selected)
        assert submitted.created
        repeated=core.checks.submit(project, expected_plan_fingerprint=preview.plan_fingerprint,
            idempotency_key='selected', selected_permissions=selected+selected)
        assert not repeated.created and repeated.job.job_id==submitted.job.job_id
        stale = (selected[0].model_copy(update={'intent_hash': 'f'*64}),)
        with pytest.raises(JiejianError, match='所选权限规则已变化'):
            core.checks.preview(project, selected_permissions=stale)
        with pytest.raises(JiejianError, match='原题复验'):
            core.checks.preview(project, change_id='chg_'+'1'*32, selected_permissions=selected)
    finally:
        harness.close()


def test_selected_action_does_not_require_unrelated_execution_material(tmp_path):
    from product.backend.domain.boundaries.entities import BusinessAction, boundary_sha256
    from product.backend.domain.checks.selection import references, permission_key
    from tests.support.builders.checks.assurance import permission
    harness = ready_check_harness(tmp_path)
    try:
        core, project = harness.core, harness.project_id
        with core.uow_factory() as work:
            original = core.business_boundaries.view(project, work=work).permission_intents[0]
            other = harness.action.model_copy(update={'action_id': 'bac_'+'f'*32, 'display_name': '另一项操作'})
            other = other.model_copy(update={'semantic_fingerprint': boundary_sha256(other.semantic_payload())})
            work.business_boundaries.add_action_revision(other)
            work.business_boundaries.add_action(BusinessAction(action_id=other.action_id, project_id=project,
                current_revision=other.revision, created_at_us=other.created_at_us, updated_at_us=other.created_at_us))
            extra = permission(99, business_action_id=other.action_id).model_copy(update={'project_id': project})
            work.permission_intents.add_revision(extra)
            work.commit()
        full = core.checks.preview(project)
        assert not full.can_execute
        selected = core.checks.preview(project, selected_permissions=references({permission_key(original)}))
        assert selected.can_execute, selected.gaps
        assert {item.action_id for item in selected.actions} == {harness.action.action_id}
        assert {item.intent_id for item in selected.selection.omitted} == {extra.intent_id}
    finally:
        harness.close()
