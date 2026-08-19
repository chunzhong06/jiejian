from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

pytestmark = pytest.mark.database

from product.backend.core.contracts.models import (
    ContractAuditAction,
    ContractAuditEntry,
    CandidateRiskKind,
    CandidateSuggestion,
    ContractCandidate,
    ContractProvenance,
    ContractSourceType,
    ContractVersion,
    Requirement,
    SourceReference,
)
from product.backend.core.lifecycle import ContractStatus, ProjectStatus
from product.backend.core.contracts.lifecycle import transition_contract_version
from product.backend.core.verification.permissions import (
    ActionDefinition,
    CoverageDimension,
    PermissionContract,
    PermissionContext,
    PermissionExpectation,
    PermissionRule,
    RelationEndpoint,
    RelationFact,
    RelationType,
    ResourceDefinition,
    SubjectDefinition,
)
from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.infra.storage import (
    ProjectRecord,
    StorageUnitOfWork,
    create_session_factory,
    create_sqlite_engine,
    upgrade_database,
)

NOW_US = 1_820_000_000_000_000
PROJECT_ID = "contract-project"


@pytest.fixture
def contract_storage(
    tmp_path: Path,
) -> Iterator[tuple[Engine, sessionmaker[Session]]]:
    path = tmp_path / "contracts.db"
    upgrade_database(path)
    engine = create_sqlite_engine(path)
    yield engine, create_session_factory(engine)
    engine.dispose()


def _source() -> SourceReference:
    return SourceReference(
        source_type=ContractSourceType.REQUIREMENT_TEXT,
        locator="requirements/security.md#ownership",
        content_sha256="a" * 64,
    )


def _rule() -> PermissionRule:
    return PermissionRule(
        rule_id="foreign-read",
        subject_id="member",
        action_id="view",
        resource_id="document",
        relation_path=("owns-document",),
        context=PermissionContext(resource_ids=("document",)),
        expectation=PermissionExpectation.DENY,
        required_observations=("resource_state",),
        coverage_dimensions=(CoverageDimension.RELATION,),
    )


def _contract(version: int = 1) -> PermissionContract:
    return PermissionContract(
        contract_id="ownership-contract",
        version=version,
        role_ids=("member",),
        workflow_states=("DRAFT",),
        subjects=(SubjectDefinition(subject_id="member", roles=("member",), tenant_id="tenant"),),
        actions=(ActionDefinition(action_id="view"),),
        resources=(ResourceDefinition(resource_id="document", resource_type="document", owner_subject_id="member", tenant_id="tenant", workflow_state="DRAFT"),),
        relations=(RelationFact(relation_id="owns-document", relation=RelationType.OWNS, source=RelationEndpoint(endpoint_type="subject", endpoint_id="member"), target=RelationEndpoint(endpoint_type="resource", endpoint_id="document")),),
        rules=(_rule(),),
    )


def _project(project_id: str = PROJECT_ID) -> ProjectRecord:
    return ProjectRecord(
        project_id=project_id,
        name="契约项目",
        status=ProjectStatus.READY,
        created_at_us=NOW_US,
        updated_at_us=NOW_US,
    )


def test_contract_records_round_trip_and_active_is_not_rewritten(
    contract_storage: tuple[Engine, sessionmaker[Session]],
) -> None:
    _, factory = contract_storage
    requirement = Requirement(
        requirement_id="req_" + "1" * 32,
        project_id=PROJECT_ID,
        source=_source(),
        text="用户只能读取自己的资源",
        security_tags=("ownership",),
        created_by="analyst",
        created_at_us=NOW_US + 1,
    )
    candidate = ContractCandidate(
        candidate_id="cand_" + "2" * 32,
        project_id=PROJECT_ID,
        source=_source(),
        suggestion=CandidateSuggestion(
            id="foreign-read",
            kind=CandidateRiskKind.FOREIGN_READ,
            required_observations=("resource_state",),
        ),
        requirement_ids=(requirement.requirement_id,),
        created_by="analyst",
        created_at_us=NOW_US + 2,
    )
    draft = ContractVersion(
        project_id=PROJECT_ID,
        contract_id="ownership-contract",
        version=1,
        status=ContractStatus.DRAFT,
        snapshot=_contract(),
        provenance=ContractProvenance(
            requirement_ids=(requirement.requirement_id,),
            candidate_ids=(candidate.candidate_id,),
            sources=(_source(),),
        ),
        audit=(ContractAuditEntry(action=ContractAuditAction.CREATED, actor="analyst", occurred_at_us=NOW_US + 3),),
        created_at_us=NOW_US + 3,
        updated_at_us=NOW_US + 3,
    )
    with StorageUnitOfWork(factory) as work:
        work.projects.add(_project())
        work.requirements.add(requirement)
        work.contract_candidates.add(candidate)
        work.contract_versions.add(draft)
        work.commit()

    review = transition_contract_version(draft, ContractStatus.REVIEW, actor="reviewer", occurred_at_us=NOW_US + 4)
    active = transition_contract_version(review, ContractStatus.ACTIVE, actor="approver", occurred_at_us=NOW_US + 5)
    with StorageUnitOfWork(factory) as work:
        work.contract_versions.replace(review)
        work.contract_versions.replace(active)
        work.commit()
    with StorageUnitOfWork(factory) as work:
        assert work.requirements.get(requirement.requirement_id) == requirement
        assert work.contract_candidates.get(candidate.candidate_id) == candidate
        assert work.contract_versions.get(PROJECT_ID, "ownership-contract", 1) == active

    rewritten = active.model_copy(
        update={
            "snapshot": active.snapshot.model_copy(update={"rules": (PermissionRule(
                rule_id="changed",
                subject_id="member",
                action_id="view",
                resource_id="document",
                relation_path=("owns-document",),
                context=PermissionContext(resource_ids=("document",)),
                expectation=PermissionExpectation.DENY,
                required_observations=("resource_state",),
                coverage_dimensions=(CoverageDimension.RELATION,),
            ),)}),
        }
    )
    with pytest.raises(JiejianError) as captured:
        with StorageUnitOfWork(factory) as work:
            work.contract_versions.replace(rewritten)
    assert captured.value.code == ErrorCode.CONTRACT_IMMUTABLE.value


def test_project_governed_binding_is_pairwise_and_round_trips(
    contract_storage: tuple[Engine, sessionmaker[Session]],
) -> None:
    _, factory = contract_storage
    with pytest.raises(ValueError):
        ProjectRecord(**(_project().model_dump() | {"governed_contract_id": "ownership-contract"}))
    bound = ProjectRecord(
        **(
            _project().model_dump()
            | {"governed_contract_id": "ownership-contract", "governed_contract_version": 3}
        )
    )
    with StorageUnitOfWork(factory) as work:
        work.projects.add(bound)
        work.commit()
    with StorageUnitOfWork(factory) as work:
        assert work.projects.get(PROJECT_ID) == bound


@pytest.mark.parametrize(
    "secret_text",
    ["Bearer top-secret", "password=top-secret", "credential:top-secret"],
)
def test_contract_records_reject_inline_credentials(
    contract_storage: tuple[Engine, sessionmaker[Session]], secret_text: str
) -> None:
    _, factory = contract_storage
    with StorageUnitOfWork(factory) as work:
        work.projects.add(_project())
        work.commit()
    requirement = Requirement(
        requirement_id="req_" + "3" * 32,
        project_id=PROJECT_ID,
        source=_source(),
        text=secret_text,
        created_by="analyst",
        created_at_us=NOW_US + 1,
    )
    with pytest.raises(JiejianError) as captured:
        with StorageUnitOfWork(factory) as work:
            work.requirements.add(requirement)
    assert captured.value.code == ErrorCode.STORAGE_SECRET.value
