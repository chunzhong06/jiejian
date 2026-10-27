# 验证来源与授权仓储使用正式 reader 能够原样读取的编码。
from functools import partial
import pytest

from product.backend.domain.lifecycle import ProjectStatus
from product.backend.infrastructure.storage.applications.projects import ProjectRecord
from product.backend.infrastructure.storage.db import prepare_database, create_sqlite_engine, create_session_factory
from product.backend.infrastructure.storage.unit_of_work import StorageUnitOfWork
from product.protocols.preparation.proof_sources import (
    AtomicProofSourceConfig, ManagedIdentityClaim, ProofSourceRevision, SourceReadScope, proof_fingerprint,
)

pytestmark = [pytest.mark.level3, pytest.mark.database]


def test_saved_source_and_scope_roundtrip_through_their_strict_readers(tmp_path):
    path = tmp_path / "workspace.db"
    prepare_database(path)
    engine = create_sqlite_engine(path)
    factory = partial(StorageUnitOfWork, create_session_factory(engine))
    identity = "tid_" + "1" * 32
    resource = "res_" + "1" * 32
    config = AtomicProofSourceConfig(action_id="bac_" + "1" * 32, action_revision=1,
        effect_id="bef_" + "1" * 32, observation_identity_id=identity, resource_binding_id=resource,
        collection="items", relative_path_template="/collections/items/{resource_id}",
        mappings={"resource_id":("resource_id",), "owner_id":("owner_id",)},
        source_contract_id="RESOURCE_FIELDS_V1", protected_projection=("title",),
        identity_claims=(ManagedIdentityClaim(identity_id=identity, application_subject_id="viewer",
            request_path="/session", subject_path=("id",), role_path=("role",), application_role="viewer"),))
    source = ProofSourceRevision(project_id="test", source_id="psr_" + "1" * 32,
        revision=1, config=config, basis_id="pb_" + "1" * 64, fingerprint=proof_fingerprint(config),
        submitted_via="LOCAL_GUI", client_name="本机用户", created_at_us=1)
    scope = SourceReadScope(scope_id="prs_" + "1" * 32, project_id="test", origin="http://127.0.0.1:8765",
        path_templates=("/session", config.relative_path_template), identity_ids=(identity,),
        resource_binding_ids=(resource,), max_response_bytes=4096, timeout_us=1_000_000, created_at_us=1)
    try:
        with factory() as work:
            work.projects.add(ProjectRecord(project_id="test", name="测试项目", status=ProjectStatus.READY,
                created_at_us=1, updated_at_us=1))
            work.proof_sources.save(source)
            work.proof_sources.add_scope(scope)
            work.commit()
        with factory() as work:
            assert work.proof_sources.source("test", source.source_id) == source
            assert work.proof_sources.scope("test", scope.scope_id) == scope
            assert work.proof_sources.source("other", source.source_id) is None
            assert work.proof_sources.scope("other", scope.scope_id) is None
    finally:
        engine.dispose()
