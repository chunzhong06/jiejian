# 唯一官方Node示例的测试准备；调用真实业务登录/创建和通用准备服务，不保留第二个示例实现。
import httpx
from uuid import uuid4


def prepare_sample(core):
    use_memory_sample_login(core)
    current=core.official_experience.start(consent=True)
    project=current.project_id
    if not core.business_boundaries.view(project).permission_intents:
        proposal=core.official_experience.boundary_proposal(exhibition_download=True).proposal
        core.business_boundaries.approve(project,proposal.proposal_id,expected_fingerprint=proposal.proposal_fingerprint,reason='组件验收核对展馆业务规则')
    core.official_experience.prepare()
    prepare_proof_sources(core,project)
    core.worker.stop()
    return project


def prepare_changed_sample(core,project):
    current=core.official_experience.status()
    prepare_actual_sessions(core,project,current.origin)
    core.official_experience.prepare()
    prepare_proof_sources(core,project)
    core.worker.stop()


def use_memory_sample_login(core):
    """工作流测试用内存秘密库与真实 HTTP 登录；Windows 子进程闭环由独立验收证明。"""
    from types import SimpleNamespace
    def prepare(identity_id,*,account,origin):
        identity=core.test_identities.get(identity_id)
        if identity.status.value!='PREPARED':
            prepare_actual_sessions(core,identity.project_id,origin,create=account=='curator',identity_id=identity_id)
    core.official_experience.identity_preparations=SimpleNamespace(prepare_official=prepare)


def prepare_actual_sessions(core,project,origin,*,create=False,identity_id=None):
    import time
    from product.backend.domain.identities.models import TestIdentityAuthMethod, TestIdentityCookie
    from product.backend.application.test_identities.service import PreparedLoginState
    for identity in core.test_identities.list(project):
        if identity_id is not None and identity.identity_id!=identity_id:continue
        account=identity.label.split(' · ')[0]
        if identity.auth_method is not None:core.test_identities.reset(identity.identity_id)
        with httpx.Client(base_url=origin,trust_env=False) as client:
            assert client.post('/api/login',json={'account':account}).status_code==200
            if create and account=='curator' and client.get('/api/galleries/campus').status_code==404:
                assert client.post('/api/galleries').status_code==201
            cookie=next(iter(client.cookies.jar));reference=f'cred:jiejian/test-identity/{project}/{identity.identity_id}/session'
            core.secret_store.write(reference,cookie.value)
            core.test_identities.save_prepared_state(identity.identity_id,PreparedLoginState(auth_method=TestIdentityAuthMethod.COOKIE_SESSION,
                cookies=(TestIdentityCookie(name=cookie.name,domain='127.0.0.1',path='/',secure=False,http_only=True,same_site='STRICT',value_secret_ref=reference),),prepared_at_us=time.time_ns()//1000))


def prepare_proof_sources(core,project):
    import json
    from pydantic import TypeAdapter
    from product.protocols.preparation.proof_sources import CurrentProofSourceConfig, FileProofSourceConfig
    from product.backend.application.preparation.proofs.commands import SaveProofSource, GrantProofScope, StartProofPreflight, AdoptProofSource
    from product.backend.application.preparation.proofs.capture_plan import CaptureSelection
    from product.backend.application.preparation.proofs.capture_service import StartReferenceCapture
    from tests.support.builders.runtime.managed_records import wait_for
    proofs=core.proof_preparation;core.worker.start()
    for item in proofs.context(project)['sources']:
        config=TypeAdapter(CurrentProofSourceConfig).validate_json(json.dumps(item['config']))
        source,revision=item['source_id'],item['revision'];basis=proofs.context(project)['basis_id']
        if isinstance(config,FileProofSourceConfig) and config.reference_artifact is None:
            boundary=core.business_boundaries.view(project)
            permission=next(row for row in boundary.permission_intents if row.business_action_id==config.action_id and row.expectation.value=='ALLOW' and row.relation.value=='OWNS')
            selection=CaptureSelection(basis_id=basis,action_id=config.action_id,action_revision=config.action_revision,
                allow_intent_id=permission.intent_id,resource_binding_id=config.resource_binding_id,collection=config.collection,
                identity_claims=tuple(claim for claim in config.identity_claims if claim.identity_id==config.reference_owner_identity_id))
            plan=core.reference_captures.preview(project,selection)
            capture=core.reference_captures.start(project,StartReferenceCapture(operation_id=uuid4().hex,basis_id=basis,selection=selection,
                plan_hash=plan.plan_hash,plan_created_at_us=plan.created_at_us,confirmed=True))['result']
            result=wait_for(lambda:core.reference_captures.status(project,capture['capture_id']))
            assert result['report']['state']=='CANDIDATE',result
            with core.uow_factory() as work:asset=work.proof_artifacts.input(project,capture['asset_id'])
            config=config.model_copy(update={'reference_artifact':asset.manifest,'reference_origin':asset.origin})
            proofs.save(project,SaveProofSource(operation_id=uuid4().hex,basis_id=basis,source_id=source,expected_revision=revision,config=config));revision+=1
        basis=proofs.context(project)['basis_id'];common=dict(basis_id=basis,source_id=source,revision=revision)
        proofs.grant_scope(project,GrantProofScope(operation_id=uuid4().hex,confirmed=True,**common))
        queued=proofs.start(project,StartProofPreflight(operation_id=uuid4().hex,**common))['result']
        result=wait_for(lambda:proofs.status(project,queued['preflight_id']))
        assert result['report']['assessment']=='USABLE',result
        proofs.adopt(project,AdoptProofSource(operation_id=uuid4().hex,preflight_id=queued['preflight_id'],confirmed=True,**common))
