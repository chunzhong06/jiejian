"""已发现但未登记的业务持续可见；排除、关联及来源变化不伪造权限结论。"""
import json
from types import SimpleNamespace as N
from uuid import uuid4
import pytest
from product.backend.domain.errors import JiejianError
from product.backend.domain.applications.models import ActionCandidate,RoleCandidate,CandidateEvidence,CandidateDecision,CandidateConfidence
from product.backend.application.application_understanding.service import ApplicationUnderstandingService
from product.backend.application.business_boundaries.models import BoundaryMaintenanceCommand
from product.backend.application.business_boundaries.discovery import discovery_coverage
from tests.support.builders.preparation.action_preparation import build_preparation_harness
from tests.support.builders.checks.check_service import ready_check_harness
from product.backend.infrastructure.runtime.jobs.check_requests import CheckRequestStore
from product.protocols.checks.execution_request import canonical_execution_request_bytes


def import_requests(core, project, source, *, revision=0, extra=False):
    parameters = [{'name':'view','in':'query','schema':{'type':'string'}}] if extra else []
    raw = json.dumps({'openapi':'3.0.3','paths':{'/orders/{id}':{'get':{
        'summary':'读取订单','parameters':parameters,'responses':{'200':{'description':'ok'}}}}}})
    preview = core.application_sources.preview(project,raw=raw,kind='OPENAPI',source_id=source if revision else None)
    return core.application_sources.accept(project,candidate_id=preview['candidate_id'],name='接口资料',source_id=source,
        expected_revision=revision,expected_fingerprint=preview['fingerprint'])


def test_unregistered_requests_survive_checks_and_explicit_exclusion_is_content_bound(core):
    project = core.application_environments.create_application(operation_id=uuid4().hex,name='新增业务')
    source = import_requests(core,project.project_id,'src_'+uuid4().hex)
    request = source.requests[0]
    initial = core.business_boundaries.discovery(project.project_id)
    assert initial.pending_count == 1 and initial.excluded_count == 0
    epoch = core.business_boundaries.view(project.project_id).policy_epoch
    current = core.application_understanding.get(project.project_id)
    decided = core.application_sources.propose_action(project.project_id,source.source_id,request.item_id,
        expected_revision=current.revision,expected_source_revision=source.revision,decision='REJECTED')
    assert core.application_sources.propose_action(project.project_id,source.source_id,request.item_id,
        expected_revision=current.revision,expected_source_revision=source.revision,decision='REJECTED') == decided
    excluded = core.business_boundaries.discovery(project.project_id)
    frozen = excluded.model_dump_json()
    assert excluded.excluded_count == 1 and excluded.pending_count == 0
    import_requests(core,project.project_id,source.source_id,revision=1,extra=True)
    changed = core.business_boundaries.discovery(project.project_id)
    assert changed.pending_count == 1 and changed.excluded_count == 0
    assert changed.fingerprint != excluded.fingerprint and excluded.model_dump_json() == frozen
    assert core.business_boundaries.view(project.project_id).policy_epoch == epoch
    with pytest.raises(JiejianError,match='接口来源已变化'):
        core.application_sources.propose_action(project.project_id,source.source_id,request.item_id,
            expected_revision=decided.revision,expected_source_revision=1,decision='REJECTED')


def test_linking_an_entry_does_not_claim_it_was_executed(tmp_path):
    harness = build_preparation_harness(tmp_path)
    try:
        core,project = harness.core,harness.project_id
        source = import_requests(core,project,'src_'+uuid4().hex)
        request = source.requests[0]
        core.application_sources.annotate(project,source.source_id,request.item_id,label='读取订单',
            action_id=harness.action.action_id,expected_revision=0,expected_source_revision=1)
        # 此夹具从旧版全局绑定起步；新增候选后按普通提案重核，保持业务规则不变。
        draft = core.business_boundaries.maintenance_draft(project)
        proposal = core.business_boundaries.create_maintenance_proposal(project,BoundaryMaintenanceCommand(
            expected_boundary_state_fingerprint=draft.boundary_state_fingerprint,actors=draft.actors,
            actions=draft.actions,permissions=draft.permissions,provenance='核对现有实现定位'))
        core.business_boundaries.approve(project,proposal.proposal.proposal_id,
            expected_fingerprint=proposal.proposal.proposal_fingerprint,reason='确认实现定位，沿用权限要求')
        plan = N(actions=(N(action_id=harness.action.action_id,cases=(N(),),gaps=()),))
        step = N(purpose='TARGET',request=N(method='GET',path='/other'))
        bundle = N(actions=(N(action_id=harness.action.action_id,steps=(step,)),))
        with core.uow_factory() as work:
            coverage = discovery_coverage(work,project,core.business_boundaries.view(project,work=work),plan=plan,bundle=bundle)
        item = next(item for item in coverage.items if item.request_id == request.item_id)
        assert item.status == 'RELATED' and item.in_execution is False
        assert coverage.unexecuted_request_count == 1
        before = core.application_understanding.get(project)
        with pytest.raises(JiejianError,match='仍关联正式业务操作'):
            core.application_sources.propose_action(project,source.source_id,request.item_id,
                expected_revision=before.revision,expected_source_revision=1,decision='REJECTED')
        assert core.application_understanding.get(project) == before
    finally:
        harness.close()


def test_source_changes_reject_stale_preview_and_later_reviews_preserve_accepted_request(tmp_path):
    harness=ready_check_harness(tmp_path)
    core,project=harness.core,harness.project_id
    try:
        source=import_requests(core,project,'src_'+uuid4().hex)
        preview=core.checks.preview(project)
        assert preview.can_execute and preview.discovery_coverage.pending_count
        updated=import_requests(core,project,source.source_id,revision=1,extra=True)
        current=core.checks.preview(project)
        assert current.can_execute and current.plan_fingerprint!=preview.plan_fingerprint
        with pytest.raises(JiejianError):
            core.checks.submit(project,expected_plan_fingerprint=preview.plan_fingerprint,idempotency_key='stale-source')
        accepted=core.checks.submit(project,expected_plan_fingerprint=current.plan_fingerprint,idempotency_key='frozen-source')
        store=CheckRequestStore(harness.var_dir)
        frozen=store.load(accepted.job.job_id,expected_hash=accepted.job.request_hash)
        original=canonical_execution_request_bytes(frozen)
        understanding=core.application_understanding.get(project)
        core.application_sources.propose_action(project,source.source_id,updated.requests[0].item_id,
            expected_revision=understanding.revision,expected_source_revision=2,decision='REJECTED')
        assert core.business_boundaries.discovery(project).excluded_count==1
        repeated=core.checks.submit(project,expected_plan_fingerprint=current.plan_fingerprint,idempotency_key='frozen-source')
        assert not repeated.created and repeated.job.job_id==accepted.job.job_id
        assert canonical_execution_request_bytes(store.load(accepted.job.job_id,expected_hash=accepted.job.request_hash))==original
        assert frozen.discovery_coverage.pending_count and frozen.discovery_coverage.excluded_count==0
    finally:
        harness.close()


def test_request_detail_keeps_review_visible_beyond_summary_budget(core):
    project=core.application_environments.create_application(operation_id=uuid4().hex,name='大量接口')
    raw=json.dumps({'openapi':'3.0.3','paths':{f'/api/items/{i}':{'get':{'responses':{'200':{'description':'ok'}}}}
        for i in range(140)}})
    preview=core.application_sources.preview(project.project_id,raw=raw,kind='OPENAPI')
    source=core.application_sources.accept(project.project_id,candidate_id=preview['candidate_id'],name='接口清单',
        source_id='src_'+uuid4().hex,expected_revision=0,expected_fingerprint=preview['fingerprint'])
    coverage=core.business_boundaries.discovery(project.project_id)
    shown={item.request_id for item in coverage.items}
    request=next(item for item in source.requests if item.item_id not in shown)
    current=core.application_understanding.get(project.project_id)
    core.application_sources.propose_action(project.project_id,source.source_id,request.item_id,
        expected_revision=current.revision,expected_source_revision=1,decision='REJECTED')
    summary=core.business_boundaries.discovery(project.project_id)
    focused=core.business_boundaries.discovery(project.project_id,focus_request=(source.source_id,request.item_id))
    assert summary.excluded_count==1 and summary.pending_count==139 and summary.omitted_count==12
    assert len(focused.items)==128 and focused.fingerprint==summary.fingerprint
    assert focused.items[0].request_id==request.item_id and focused.items[0].status=='EXCLUDED'


def test_source_analysis_does_not_erase_unchanged_api_source_review(core,tmp_path):
    directory=tmp_path/'application'
    directory.mkdir()
    (directory/'app.mjs').write_text("const roles=['reviewer'];",encoding='utf-8')
    connected=core.application_understanding.connect(directory,project_name='资料与源码分别维护')
    project=connected.project.project_id
    current=core.application_understanding.authorize_source_analysis(project,revision=connected.understanding.revision)
    source=import_requests(core,project,'src_'+uuid4().hex)
    current=core.application_understanding.get(project)
    current=core.application_sources.propose_action(project,source.source_id,source.requests[0].item_id,
        expected_revision=current.revision,expected_source_revision=1,decision='REJECTED')
    analyzed=core.application_understanding.analyze_source(project,revision=current.revision)
    coverage=core.business_boundaries.discovery(project)
    item=next(item for item in coverage.items if item.request_id==source.requests[0].item_id)
    assert item.status=='EXCLUDED'
    assert any(not item.stale and any(e.detector=='API_SOURCE' for e in item.evidence) for item in analyzed.action_candidates)


@pytest.mark.parametrize('kind',['role','action'])
def test_excluded_source_candidate_requires_new_review_when_evidence_changes(kind):
    evidence=CandidateEvidence(relative_path='app.mjs',line_start=1,line_end=1,detector='SOURCE',content_sha256='a'*64)
    model=RoleCandidate if kind=='role' else ActionCandidate
    candidate=model(candidate_id=kind+'_'+'1'*32,canonical_key='reviewer',display_name='已核对名称',confidence=CandidateConfidence.MEDIUM,
        decision=CandidateDecision.REJECTED,evidence=(evidence,))
    merge=ApplicationUnderstandingService._merge_roles if kind=='role' else ApplicationUnderstandingService._merge_actions
    assert merge((candidate,),(candidate,))[0].decision is CandidateDecision.REJECTED
    changed=candidate.model_copy(update={'evidence':(evidence.model_copy(update={'content_sha256':'b'*64}),)})
    reviewed=merge((candidate,),(changed,))[0]
    assert reviewed.decision is CandidateDecision.REVIEW_REQUIRED and reviewed.display_name==candidate.display_name
