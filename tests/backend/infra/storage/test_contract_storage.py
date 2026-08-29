# 验证内部 ContractVersion 仓储的不可变版本与来源边界。

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from product.backend.core.contracts.lifecycle import transition_contract_version
from product.backend.core.contracts.models import (
    ContractAuditAction,
    ContractAuditEntry,
    ContractProvenance,
    ContractSourceType,
    ContractVersion,
    SourceReference,
)
from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.core.lifecycle import ContractStatus, ProjectStatus
from product.backend.core.verification.permissions import (
    ActionDefinition,
    CoverageDimension,
    PermissionContext,
    PermissionContract,
    PermissionExpectation,
    PermissionRule,
    RelationEndpoint,
    RelationFact,
    RelationType,
    ResourceDefinition,
    SecurityEffectDefinition,
    SecurityEffectKind,
    SubjectDefinition,
)
from product.backend.infra.storage import (
    ProjectRecord,
    StorageUnitOfWork,
    create_session_factory,
    create_sqlite_engine,
    upgrade_database,
)


NOW_US = 1_820_000_000_000_000
PROJECT_ID = "contract-project"
pytestmark = pytest.mark.database


@pytest.fixture
def contract_storage(
    tmp_path: Path,
) -> Iterator[tuple[Engine, sessionmaker[Session]]]:
    path = tmp_path / "contracts.db"
    upgrade_database(path)
    engine = create_sqlite_engine(path)
    yield engine, create_session_factory(engine)
    engine.dispose()


def _source(locator: str = "permission-intent:contract-project") -> SourceReference:
    return SourceReference(
        source_type=ContractSourceType.PROJECT_CONFIG,
        locator=locator,
        content_sha256="a" * 64,
    )


def _contract() -> PermissionContract:
    return PermissionContract(
        contract_id="generated-contract-project",
        version=1,
        role_ids=("member",),
        workflow_states=("READY",),
        subjects=(SubjectDefinition(subject_id="member", roles=("member",), tenant_id="tenant"),),
        effects=(SecurityEffectDefinition(effect_id="document-read", kind=SecurityEffectKind.DATA_DISCLOSURE, resource_type="document", protected_fields=("content",)),),
        actions=(ActionDefinition(action_id="view", effect_ids=("document-read",)),),
        resources=(ResourceDefinition(resource_id="document", resource_type="document", owner_subject_id="member", tenant_id="tenant", workflow_state="READY"),),
        relations=(RelationFact(relation_id="owns-document", relation=RelationType.OWNS, source=RelationEndpoint(endpoint_type="subject", endpoint_id="member"), target=RelationEndpoint(endpoint_type="resource", endpoint_id="document")),),
        rules=(PermissionRule(rule_id="foreign-read", subject_id="member", action_id="view", resource_id="document", relation_path=("owns-document",), context=PermissionContext(resource_ids=("document",)), expectation=PermissionExpectation.DENY, required_observations=("resource_state",), coverage_dimensions=(CoverageDimension.RELATION,)),),
    )


def _project() -> ProjectRecord:
    return ProjectRecord(
        project_id=PROJECT_ID,
        name="契约项目",
        status=ProjectStatus.READY,
        created_at_us=NOW_US,
        updated_at_us=NOW_US,
    )


def _version(*, source: SourceReference | None = None) -> ContractVersion:
    return ContractVersion(
        project_id=PROJECT_ID,
        contract_id="generated-contract-project",
        version=1,
        status=ContractStatus.DRAFT,
        snapshot=_contract(),
        provenance=ContractProvenance(sources=(() if source is None else (source,))),
        audit=(ContractAuditEntry(action=ContractAuditAction.CREATED, actor="compiler", occurred_at_us=NOW_US + 1),),
        created_at_us=NOW_US + 1,
        updated_at_us=NOW_US + 1,
    )


def test_contract_version_round_trip_and_active_body_is_immutable(
    contract_storage: tuple[Engine, sessionmaker[Session]],
) -> None:
    _, factory = contract_storage
    draft = _version(source=_source())
    with StorageUnitOfWork(factory) as work:
        work.projects.add(_project())
        work.contract_versions.add(draft)
        work.commit()
    review = transition_contract_version(
        draft,
        ContractStatus.REVIEW,
        actor="compiler",
        occurred_at_us=NOW_US + 2,
    )
    active = transition_contract_version(
        review,
        ContractStatus.ACTIVE,
        actor="compiler",
        occurred_at_us=NOW_US + 3,
    )
    with StorageUnitOfWork(factory) as work:
        work.contract_versions.replace(review)
        work.contract_versions.replace(active)
        work.commit()
    with StorageUnitOfWork(factory) as work:
        assert work.contract_versions.get(PROJECT_ID, active.contract_id, 1) == active

    rewritten = active.model_copy(
        update={"provenance": ContractProvenance(sources=())}
    )
    with pytest.raises(JiejianError) as captured:
        with StorageUnitOfWork(factory) as work:
            work.contract_versions.replace(rewritten)
    assert captured.value.code == ErrorCode.CONTRACT_IMMUTABLE.value


def test_contract_version_rejects_inline_credentials(
    contract_storage: tuple[Engine, sessionmaker[Session]],
) -> None:
    _, factory = contract_storage
    with StorageUnitOfWork(factory) as work:
        work.projects.add(_project())
        work.commit()

    with pytest.raises(JiejianError) as captured:
        with StorageUnitOfWork(factory) as work:
            work.contract_versions.add(_version(source=_source("Bearer top-secret")))
    assert captured.value.code == ErrorCode.STORAGE_SECRET.value


def test_project_governed_binding_remains_pairwise(
    contract_storage: tuple[Engine, sessionmaker[Session]],
) -> None:
    _, factory = contract_storage
    with pytest.raises(ValueError):
        ProjectRecord(**(_project().model_dump() | {"governed_contract_id": "generated-contract-project"}))
    bound = ProjectRecord(
        **(
            _project().model_dump()
            | {
                "governed_contract_id": "generated-contract-project",
                "governed_contract_version": 1,
            }
        )
    )
    with StorageUnitOfWork(factory) as work:
        work.projects.add(bound)
        work.commit()
    with StorageUnitOfWork(factory) as work:
        assert work.projects.get(PROJECT_ID) == bound
