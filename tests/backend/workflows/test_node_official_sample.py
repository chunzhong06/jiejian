# 验证官方Node体验复用通用运行所有者、人的规则选择和真实业务文件；不预制检查结论。
from pathlib import Path
from uuid import uuid4
import io
import zipfile
import httpx
import pytest
from product.backend.composition import ApplicationCore
from product.backend.core.errors import JiejianError
from product.backend.infra.samples.official import _load_installation
from tests.fixtures.preparation.action_preparation import MemorySecretStore
from tests.fixtures.runtime.runtime_environment import runtime_identity_environment, write_python_installation_contract
from tests.backend.workflows._support_current_official_sample import prepare_actual_sessions,prepare_proof_sources,use_memory_sample_login

ROOT=Path(__file__).resolve().parents[3]
SAMPLE=ROOT/'samples/web/digital_gallery'


def test_manifest_two_is_strict_and_old_python_remains_readable(tmp_path):
    assert _load_installation(SAMPLE).runtime_kind=='NODE_ESM'
    assert _load_installation(write_python_installation_contract(tmp_path/'legacy-contract')).runtime_kind=='PYTHON'
    import json,shutil
    copy=tmp_path/'sample';shutil.copytree(SAMPLE,copy)
    manifest=copy/'sample.json';value=json.loads(manifest.read_text(encoding='utf-8'));value['extra']=True
    manifest.write_text(json.dumps(value),encoding='utf-8');assert not _load_installation(copy).available




@pytest.mark.process
@pytest.mark.slow
def test_gallery_materials_and_five_real_implementations(tmp_path):
    import time
    var=tmp_path/'var'
    core=ApplicationCore(var,official_sample_root=SAMPLE,secret_store=MemorySecretStore(),environ=runtime_identity_environment(var))
    use_memory_sample_login(core)
    try:
        started=core.official_experience.start(consent=True);project=started.project_id
        proposed=core.official_experience.boundary_proposal(exhibition_download=True)
        core.business_boundaries.approve(project,proposed.proposal.proposal_id,expected_fingerprint=proposed.proposal.proposal_fingerprint,reason='确认示例五项业务要求')
        core.official_experience.prepare()
        assert len(core.test_identities.list(project))==2
        assert not core.preparation.get(project).preparation_complete
        context=core.proof_preparation.context(project)
        assert len(context['sources'])==4 and not any(item['adopted'] for item in context['sources'])
        assert not context['read_scopes']
        prepare_proof_sources(core,project)
        history=[];reference=None
        from product.backend.workflows.examples.environment import OfficialScenarioVersion
        for stage,expected in [('BASELINE','PASS'),('VULNERABLE','BLOCK'),('EXPOSE_REVOKE','BLOCK'),('FIXED','PASS'),('PREVIEW_CHANGED','PASS')]:
            print('真实场景：'+stage,flush=True)
            change_id=None
            if stage!='BASELINE':
                state=core.official_experience.switch_version(version=OfficialScenarioVersion(stage),repair_reference=reference if stage=='FIXED' else None)
                change_id=state.current_change_id;assert change_id
                prepare_actual_sessions(core,project,state.origin)
                core.official_experience.prepare()
                prepare_proof_sources(core,project)
            preview=core.checks.preview(project,change_id=change_id);assert preview.can_execute,preview
            submitted=core.checks.submit(project,expected_plan_fingerprint=preview.plan_fingerprint,idempotency_key=uuid4().hex,change_id=change_id)
            deadline=time.monotonic()+60
            while time.monotonic()<deadline:
                status=core.check_results.status(submitted.run.run_id,project_id=project)
                if status.run.lifecycle.value in {'COMPLETED','FAILED','CANCELLED','SAFETY_STOPPED'}:break
                time.sleep(.1)
            package=core.check_results.package(submitted.run.run_id)
            diagnostic={'stage':stage,'cases':[(item.case_id,item.verdict.value,item.reason_codes) for item in package.result.case_results],
                'observations':[(doc.case.permission.expectation,[(ob.phase,ob.state,ob.reason_codes) for ob in doc.observations]) for doc in package.evidence]}
            from product.backend.infra.runtime.process.records.record_server import record_store_path
            diagnostic['record_journal_bytes']=record_store_path(var,project).stat().st_size
            if status.run.verdict is None or status.run.verdict.value!=expected:
                import json
                audit=ROOT/'var/audit/testing'/('gallery-'+submitted.run.run_id+'.json')
                audit.write_text(json.dumps(diagnostic,ensure_ascii=False,indent=2),encoding='utf-8')
                print('有界诊断：'+str(audit))
            assert status.run.verdict is not None and status.run.verdict.value==expected,diagnostic['cases']
            assert len(package.result.case_results)==5
            # 事件来自真实受控请求；五种业务版本仍沿用原有判据，Trace 不参与 Verdict。
            assert all(doc.trace and doc.trace.complete for doc in package.evidence),[(doc.case.case_id,doc.trace) for doc in package.evidence]
            assert all(any(event.kind=='AUTHORIZATION' for event in doc.trace.events) for doc in package.evidence)
            story=core.check_story.build(submitted.run.run_id)
            assert all(item.execution_path and item.execution_path.events for item in story.actions)
            from product.backend.api.mcp.views import _current_story_view
            agent_view=_current_story_view(story)
            assert all(item['evidence_refs'] and item['execution_path_complete'] for item in agent_view['actions'])
            if stage=='VULNERABLE':reference=core.check_repairs.contracts(submitted.run.run_id)[0].reference()
            if stage=='EXPOSE_REVOKE':
                document=next(item for item in package.evidence if item.case.permission.expectation=='DENY')
                assert document.outcome.http_status==403
                states=[fact.data for fact in document.business_facts if fact.data.kind=='COMMITTED_STATE']
                assert len({fact.operation_id for fact in states})==2
            if stage=='FIXED':assert core.check_story.build(submitted.run.run_id).repair_verification.status=='VERIFIED'
            history.append((submitted.run.run_id,expected))
            for run_id,verdict in history:assert core.check_results.status(run_id,project_id=project).run.verdict.value==verdict
        assert len(core.check_results.history(project).items)==5
        state=core.official_experience.stop();assert not state.active and state.recovery_state=='EXITED'
    finally:core.close()


@pytest.mark.process
def test_provided_gallery_files_are_ready_without_capture_or_implicit_adoption(tmp_path):
    var=tmp_path/'var'
    core=ApplicationCore(var,official_sample_root=SAMPLE,secret_store=MemorySecretStore(),environ=runtime_identity_environment(var))
    use_memory_sample_login(core)
    try:
        project=core.official_experience.start(consent=True).project_id
        proposed=core.official_experience.boundary_proposal(exhibition_download=True)
        core.business_boundaries.approve(project,proposed.proposal.proposal_id,expected_fingerprint=proposed.proposal.proposal_fingerprint,reason='确认示例权限要求')
        core.official_experience.prepare()
        context=core.proof_preparation.context(project)
        files=[item for item in context['sources'] if item['config']['source_kind']=='REFERENCE_FILE']
        assert len(files)==2 and all(item['config']['reference_artifact'] for item in files)
        assert not context['read_scopes'] and not any(item['adopted'] for item in context['sources'])
        assert len(context['reference_inputs'])==2
        contents=[core.proof_artifacts.read(project,item['config']['reference_artifact']['asset_id']) for item in files]
        assert any(content.startswith(b'PK\x03\x04') for content in contents)
        assert any(content.startswith(b'%PDF-') for content in contents)
        # 再次准备不复制输入，不把已存在的候选自动采用。
        core.official_experience.prepare()
        again=core.proof_preparation.context(project)
        assert [item['asset_id'] for item in again['reference_inputs']]==[item['asset_id'] for item in context['reference_inputs']]
        assert not again['read_scopes'] and not any(item['adopted'] for item in again['sources'])
    finally:
        core.close()


@pytest.mark.process
def test_gallery_preset_refreshes_sources_and_preflight_can_continue(tmp_path):
    import json,time
    from product.backend.workflows.examples.environment import OfficialScenarioVersion
    var=tmp_path/'var'
    core=ApplicationCore(var,official_sample_root=SAMPLE,secret_store=MemorySecretStore(),environ=runtime_identity_environment(var))
    use_memory_sample_login(core)
    try:
        project=core.official_experience.start(consent=True).project_id
        proposal=core.official_experience.boundary_proposal(exhibition_download=True).proposal
        core.business_boundaries.approve(project,proposal.proposal_id,expected_fingerprint=proposal.proposal_fingerprint,reason='确认演示的权限要求')
        core.official_experience.prepare();prepare_proof_sources(core,project)
        assert core.preparation.get(project).preparation_complete
        preview=core.checks.preview(project)
        run=core.checks.submit(project,expected_plan_fingerprint=preview.plan_fingerprint,idempotency_key=uuid4().hex).run
        deadline=time.monotonic()+60
        while time.monotonic()<deadline:
            status=core.check_results.status(run.run_id,project_id=project)
            if status.run.lifecycle.value=='COMPLETED':break
            time.sleep(.1)
        assert status.run.verdict.value=='PASS'
        core.official_experience.switch_version(version=OfficialScenarioVersion.VULNERABLE)
        core.official_experience.prepare()
        context=core.proof_preparation.context(project)
        resources={item['resource_binding_id'] for item in context['resources']}
        assert all(item['config']['resource_binding_id'] in resources for item in context['sources'])
        prepare_proof_sources(core,project)
        assert core.preparation.get(project).preparation_complete
        timings={}
        for label,read in [('sources',core.proof_preparation.context),('full_guidance',core.preparation_guidance.context)]:
            started=time.perf_counter();value=read(project);timings[label]=round(time.perf_counter()-started,4)
            assert value['project_id']==project
        path=ROOT/'var/audit/preparation-feedback-20261010/timings.json';path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(json.dumps({'context_seconds':timings,'source_count':len(context['sources']),'preset_preparation':'PASSED'},indent=2),encoding='utf-8')
    finally:core.close()
