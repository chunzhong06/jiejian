# 验证唯一Node示例的审批、材料恢复、源码保护和冻结录制；完整五轮结论另由整链用例覆盖。
from pathlib import Path
import pytest
from product.backend.composition import ApplicationCore
from product.backend.core.errors import JiejianError
from product.backend.workflows.examples.environment import OfficialScenarioVersion
from product.backend.workflows.examples.materials import OfficialScenarioInstaller
from tests.fixtures.secrets import InMemorySecretStore
from tests.fixtures.runtime.runtime_environment import runtime_identity_environment
from tests.backend.workflows._support_current_official_sample import prepare_sample,use_memory_sample_login

pytestmark=[pytest.mark.process,pytest.mark.slow]

@pytest.fixture
def current_sample(tmp_path):
    var=tmp_path/'var'
    core=ApplicationCore(var,official_sample_root=Path(__file__).resolve().parents[3]/'samples/web/digital_gallery',
        secret_store=InMemorySecretStore(),environ=runtime_identity_environment(var))
    use_memory_sample_login(core)
    try:yield core
    finally:core.close()


def test_sample_requires_human_approval_then_real_login_and_source_adoption(current_sample):
    core=current_sample;view=core.official_experience.start(consent=True);project=view.project_id
    assert view.active and core.runtime_ports.reference(project)==core.node_runtime.reference(project)
    with pytest.raises(JiejianError):core.official_experience.prepare()
    assert core.test_identities.list(project)==()
    proposal=core.official_experience.boundary_proposal(exhibition_download=True).proposal
    core.business_boundaries.approve(project,proposal.proposal_id,expected_fingerprint=proposal.proposal_fingerprint,reason='核对业务要求')
    prepared=core.official_experience.prepare()
    assert not prepared.scenario_prepared and len(core.test_identities.list(project))==2
    assert all(item.status.value=='PREPARED' for item in core.test_identities.list(project))
    sources=core.proof_preparation.context(project)
    assert len(sources['sources'])==4 and not sources['read_scopes'] and not any(item['adopted'] for item in sources['sources'])
    assert not core.checks.preview(project).can_execute
    with core.uow_factory() as work:assert work.runs.list_for_project(project)==()


def test_rebuilt_installer_resumes_persistent_review_without_consuming_again(current_sample,monkeypatch):
    import time
    core=current_sample;view=core.official_experience.start(consent=True);project=view.project_id
    proposal=core.official_experience.boundary_proposal(exhibition_download=True).proposal
    core.business_boundaries.approve(project,proposal.proposal_id,expected_fingerprint=proposal.proposal_fingerprint,reason='核对业务要求')
    finalize=core.recording_lifecycle.finalize
    def interrupted(*args,**kwargs):raise RuntimeError('interrupted before finalize')
    monkeypatch.setattr(core.recording_lifecycle,'finalize',interrupted)
    with pytest.raises(RuntimeError,match='interrupted'):core.official_experience.prepare()
    with core.uow_factory() as work:
        first=next(item for item in work.jobs.list_for_project(project) if item.operation_type=='BROWSER_RECORDING')
        before=work.recordings.get(first.recording_id);draft=work.flow_drafts.latest(first.recording_id)
        assert before.state.value=='PENDING_REVIEW'
    monkeypatch.setattr(core.recording_lifecycle,'finalize',finalize)
    core.official_experience.installer=OfficialScenarioInstaller(core.project_recordings,core.recording_submission,core.job_attempts,
        var_dir=core.var_dir,recording_credentials=core.recording_credentials,lifecycle=core.recording_lifecycle,
        clock_us=lambda:time.time_ns()//1000,preparation=core.preparation)
    assert not core.official_experience.prepare().scenario_prepared
    with core.uow_factory() as work:
        assert len(work.recordings.list_for_project(project))==4
        assert work.recordings.get(first.recording_id).browser_events==before.browser_events
        assert work.flow_drafts.latest(first.recording_id)==draft
        assert work.runs.list_for_project(project)==()


def test_external_source_change_cannot_be_overwritten_by_preset(current_sample):
    core=current_sample;view=core.official_experience.start(consent=True)
    source=Path(core.application_understanding.get(view.project_id).source_root)/'delivery.mjs'
    changed=source.read_text(encoding='utf-8')+'\n// 用户的当前修改\n';source.write_text(changed,encoding='utf-8')
    journey=core.official_experience.development_journey()
    assert journey.implementation=='CUSTOM' and not journey.can_optimize
    with pytest.raises(JiejianError,match='外部修改'):core.official_experience.switch_version(version=OfficialScenarioVersion.VULNERABLE)
    assert source.read_text(encoding='utf-8')==changed


def test_corrupted_flow_is_rejected_without_overwriting_frozen_material(current_sample):
    from product.backend.workflows.recording.lifecycle import RecordingLifecycle
    core=current_sample;project=prepare_sample(core)
    action=core.business_boundaries.view(project).actions[0]
    with core.uow_factory() as work:
        binding=work.action_preparation.execution(action.action_id,action.revision)
        recording=work.recordings.get(binding.source_recording_id)
    path=RecordingLifecycle.flow_path(core.var_dir,recording);original=path.read_bytes()
    try:
        path.write_bytes(original+b' ')
        assert not core.checks.preview(project).can_execute
        assert path.read_bytes()==original+b' '
    finally:path.write_bytes(original)
    assert core.checks.preview(project).can_execute
