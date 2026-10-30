# 验证私有参照的不可覆盖、归属与容量边界；不创建目标进程或读取真实凭据。
from functools import partial
import hashlib
from uuid import uuid4
import pytest
from product.backend.domain.errors import JiejianError
from product.backend.domain.lifecycle import ProjectStatus
from product.backend.infrastructure.artifacts.proof_artifacts import ProofArtifactStore
from product.backend.infrastructure.storage.unit_of_work import StorageUnitOfWork
from product.backend.infrastructure.storage.applications.projects import ProjectRecord
from product.backend.infrastructure.storage.db import prepare_database, create_sqlite_engine, create_session_factory
from product.protocols.preparation.proof_artifacts import ProofArtifactInput
from product.backend.application.preparation.proofs.artifact_inputs import UploadProofArtifact
from tests.support.builders.checks.check_service import ready_check_harness


def test_private_bytes_are_immutable_scoped_and_bounded(tmp_path):
    store=ProofArtifactStore(tmp_path)
    asset='pai_'+uuid4().hex
    content=store.accept(b'controlled fixture bytes')
    value=store.save('project_a',asset,content)
    assert store.save('project_a',asset,content)==value
    assert store.read('project_a',value)==b'controlled fixture bytes'
    with pytest.raises(JiejianError):store.save('project_a',asset,store.accept(b'different content'))
    with pytest.raises(JiejianError):store.read('project_b',value)
    with pytest.raises(JiejianError):store.directory('../escape',asset)
    for raw in (b'',b'x'*4194305,b'password:forbidden',b'session-test-value'):
        with pytest.raises(JiejianError):store.accept(raw,known_secrets=('session-test-value',))
    (store.directory('project_a',asset)/'artifact.bin').write_bytes(b'corrupted')
    with pytest.raises(JiejianError):store.read('project_a',value)


def test_reference_replay_accepts_full_capacity_and_read_uses_current_secret_scope(tmp_path):
    store=ProofArtifactStore(tmp_path)
    content=store.accept(b'x'*4194304)
    asset='pai_'+uuid4().hex
    manifest=store.save('project_a',asset,content)
    assert store.save('project_a',asset,content)==manifest
    assert store.read('project_a',manifest)==content.raw
    with pytest.raises(JiejianError) as error:
        store.read('project_a',manifest,known_secrets=('xxxx',))
    assert error.value.code=='STORAGE_SECRET'


def test_pending_capture_reserves_project_capacity_and_cancel_releases_it(tmp_path):
    database=tmp_path/'data.db';prepare_database(database);engine=create_sqlite_engine(database)
    factory=partial(StorageUnitOfWork,create_session_factory(engine))
    try:
        with factory() as work:
            work.projects.add(ProjectRecord(project_id='project_a',name='资源测试',status=ProjectStatus.READY,created_at_us=1,updated_at_us=1))
            values=[]
            for index in range(64):
                value=ProofArtifactInput(asset_id='pai_'+f'{index:032x}',project_id='project_a',operation_id=f'{index:032x}',
                    action_id='bac_'+'1'*32,action_revision=1,resource_binding_id='res_'+'1'*32,resource_id='alpha',
                    owner_identity_id='tid_'+'1'*32,origin='REFERENCE_CAPTURE',reference_capture_id='rpc_'+f'{index:032x}',
                    state='PENDING',created_at_us=1,basis_id='pb_'+'1'*64)
                work.proof_artifacts.add_input(value);values.append(value)
            extra=values[0].model_copy(update={'asset_id':'pai_'+'f'*32,'operation_id':'f'*32})
            with pytest.raises(JiejianError,match='容量'):work.proof_artifacts.add_input(extra)
            work.proof_artifacts.update_input(values[0].model_copy(update={'state':'CANCELLED'}),expected_state='PENDING')
            work.proof_artifacts.add_input(extra)
            assert len(work.proof_artifacts.inputs('project_a'))==64
            assert work.proof_artifacts.input('project_b',extra.asset_id) is None
            work.commit()
    finally:engine.dispose()


def test_upload_replay_checks_declared_content_and_stale_basis_without_publishing(tmp_path):
    harness=ready_check_harness(tmp_path)
    try:
        core,project=harness.core,harness.project_id
        context=core.proof_preparation.context(project)
        resource=context['resources'][0]
        raw=b'controlled upload fixture'
        command=UploadProofArtifact(operation_id=uuid4().hex,basis_id=context['basis_id'],
            action_id=harness.action.action_id,action_revision=1,resource_binding_id=resource['resource_binding_id'],
            size=len(raw),sha256=hashlib.sha256(raw).hexdigest(),confirmed=True)
        receipt=core.proof_artifacts.upload(project,command,raw)
        assert core.proof_artifacts.upload(project,command,raw)==receipt
        assert core.proof_artifacts.read(project,receipt['result']['asset_id'])==raw
        with pytest.raises(JiejianError,match='上传内容'):
            core.proof_artifacts.upload(project,command,b'different content')
        stale=command.model_copy(update=dict(operation_id=uuid4().hex,basis_id='pb_'+'0'*64))
        with pytest.raises(JiejianError):core.proof_artifacts.upload(project,stale,raw)
        with core.uow_factory() as work:
            assert work.proof_artifacts.input(project,'pai_'+stale.operation_id) is None
        assert not core.proof_artifacts.store.directory(project,'pai_'+stale.operation_id).exists()
    finally:harness.close()

pytestmark = [pytest.mark.level3]
