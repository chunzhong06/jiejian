from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from product.backend.workflows.contracts.governance import ContractGovernance
from product.backend.core.contracts.models import CandidateRiskKind, CandidateSuggestion, ContractSourceType, SourceReference
from product.backend.core.lifecycle import ContractStatus
from product.backend.core.lifecycle import ProjectStatus
from product.backend.core.verification.permissions import ActionDefinition, CoverageDimension, PermissionContract, PermissionContext, PermissionExpectation, PermissionRule, RelationEndpoint, RelationFact, RelationType, ResourceDefinition, SecurityEffectDefinition, SecurityEffectKind, SubjectDefinition
from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.infra.storage import (
    ProjectRecord,
    StorageUnitOfWork,
    create_session_factory,
    create_sqlite_engine,
    upgrade_database,
)

NOW_US = 1_830_000_000_000_000

pytestmark = pytest.mark.database


@pytest.fixture
def governance(
    tmp_path: Path,
) -> Iterator[tuple[ContractGovernance, sessionmaker[Session], Engine]]:
    path = tmp_path / "governance.db"
    upgrade_database(path)
    engine = create_sqlite_engine(path)
    factory = create_session_factory(engine)
    with StorageUnitOfWork(factory) as work:
        for project_id in ("project-a", "project-b"):
            work.projects.add(
                ProjectRecord(
                    project_id=project_id,
                    name=project_id,
                    status=ProjectStatus.READY,
                    created_at_us=NOW_US,
                    updated_at_us=NOW_US,
                )
            )
        work.commit()
    ticks = iter(range(NOW_US + 1, NOW_US + 100))
    yield ContractGovernance(
        lambda: StorageUnitOfWork(factory),
        clock_us=lambda: next(ticks),
        available_observations=("resource_state",),
    ), factory, engine
    engine.dispose()


def _source(locator: str = "requirements.md#ownership") -> SourceReference:
    return SourceReference(
        source_type=ContractSourceType.REQUIREMENT_TEXT,
        locator=locator,
        content_sha256="a" * 64,
    )


def _contract(contract_id: str, version: int = 1, rule_id: str = "foreign-read") -> PermissionContract:
    return PermissionContract(
        contract_id=contract_id,
        version=version,
        role_ids=("member",),
        workflow_states=("DRAFT",),
        subjects=(SubjectDefinition(subject_id="member", roles=("member",), tenant_id="tenant"),),
        effects=(SecurityEffectDefinition(effect_id="document-read", kind=SecurityEffectKind.DATA_DISCLOSURE, resource_type="document", protected_fields=("content",)),),
        actions=(ActionDefinition(action_id="view", effect_ids=("document-read",)),),
        resources=(ResourceDefinition(resource_id="document", resource_type="document", owner_subject_id="member", tenant_id="tenant", workflow_state="DRAFT"),),
        relations=(RelationFact(relation_id="owns-document", relation=RelationType.OWNS, source=RelationEndpoint(endpoint_type="subject", endpoint_id="member"), target=RelationEndpoint(endpoint_type="resource", endpoint_id="document")),),
        rules=(PermissionRule(rule_id=rule_id, subject_id="member", action_id="view", resource_id="document", relation_path=("owns-document",), context=PermissionContext(resource_ids=("document",)), expectation=PermissionExpectation.DENY, required_observations=("resource_state",), coverage_dimensions=(CoverageDimension.RELATION,)),),
    )


def _suggestion() -> CandidateSuggestion:
    return CandidateSuggestion(id="foreign-read", kind=CandidateRiskKind.FOREIGN_READ, required_observations=("resource_state",))


def test_full_review_activation_revision_and_supersession_flow(
    governance: tuple[ContractGovernance, sessionmaker[Session], Engine],
) -> None:
    service, factory, _ = governance
    requirement = service.create_requirement(
        "project-a",
        source=_source(),
        text="用户只能读取自己的资源",
        security_tags=("ownership",),
        actor="analyst",
    )
    candidate = service.create_candidate(
        "project-a",
        source=_source("analysis/routes.py#resource"),
        suggestion=_suggestion(),
        requirement_ids=(requirement.requirement_id,),
        actor="analyzer",
    )
    draft = service.create_draft(
        "project-a",
        "ownership-contract",
        snapshot=_contract("ownership-contract"),
        requirement_ids=(requirement.requirement_id,),
        candidate_ids=(candidate.candidate_id,),
        actor="analyst",
    )
    expected_sources = tuple(
        sorted(
            {requirement.source, candidate.source},
            key=lambda item: (item.source_type.value, item.locator, item.content_sha256),
        )
    )
    assert draft.provenance.sources == expected_sources
    review = service.submit_review(
        "project-a", "ownership-contract", draft.version, actor="reviewer"
    )
    active_v1 = service.activate_review(
        "project-a", "ownership-contract", review.version, actor="approver"
    )
    draft_v2 = service.revise_active(
        "project-a",
        "ownership-contract",
        snapshot=_contract("ownership-contract", version=2, rule_id="foreign-read-v2"),
        sources=(_source("manual/revision-v2"),),
        requirement_ids=(requirement.requirement_id,),
        actor="analyst",
    )
    review_v2 = service.submit_review(
        "project-a", "ownership-contract", draft_v2.version, actor="reviewer"
    )
    active_v2 = service.activate_review(
        "project-a", "ownership-contract", review_v2.version, actor="approver"
    )

    assert active_v1.status is ContractStatus.ACTIVE
    assert active_v2.version == 2
    assert active_v2.supersedes_version == 1
    with StorageUnitOfWork(factory) as work:
        stored_v1 = work.contract_versions.get("project-a", "ownership-contract", 1)
        stored_v2 = work.contract_versions.get_active("project-a", "ownership-contract")
        stored_project = work.projects.get("project-a")
    assert stored_v1 is not None and stored_v1.status is ContractStatus.SUPERSEDED
    assert stored_v2 == active_v2
    assert stored_project is not None
    assert stored_project.governed_contract_id == "ownership-contract"
    assert stored_project.governed_contract_version == 2


def test_activation_of_another_contract_switches_project_binding(
    governance: tuple[ContractGovernance, sessionmaker[Session], Engine],
) -> None:
    service, factory, _ = governance
    first = service.create_draft(
        "project-a", "first-contract", snapshot=_contract("first-contract"), sources=(_source("manual/first"),), actor="analyst"
    )
    first_review = service.submit_review("project-a", "first-contract", first.version, actor="reviewer")
    service.activate_review("project-a", "first-contract", first_review.version, actor="approver")
    second = service.create_draft(
        "project-a", "second-contract", snapshot=_contract("second-contract", rule_id="second-rule"), sources=(_source("manual/second"),), actor="analyst"
    )
    second_review = service.submit_review("project-a", "second-contract", second.version, actor="reviewer")
    service.activate_review("project-a", "second-contract", second_review.version, actor="approver")
    with StorageUnitOfWork(factory) as work:
        project = work.projects.get("project-a")
    assert project is not None
    assert (project.governed_contract_id, project.governed_contract_version) == ("second-contract", 1)


def test_rejection_illegal_activation_and_cross_project_references(
    governance: tuple[ContractGovernance, sessionmaker[Session], Engine],
) -> None:
    service, _, _ = governance
    requirement = service.create_requirement(
        "project-a", source=_source(), text="安全需求", actor="analyst"
    )
    with pytest.raises(JiejianError) as cross_project:
        service.create_candidate(
            "project-b",
            source=_source(),
            suggestion=_suggestion(),
            requirement_ids=(requirement.requirement_id,),
            actor="analyst",
        )
    assert cross_project.value.code == ErrorCode.CONTRACT_REFERENCE_INVALID.value

    draft = service.create_draft(
        "project-a",
        "rejected-contract",
        snapshot=_contract("rejected-contract"),
        sources=(_source("manual/rejected-contract"),),
        actor="analyst",
    )
    with pytest.raises(JiejianError) as skipped_review:
        service.activate_review(
            "project-a", "rejected-contract", draft.version, actor="approver"
        )
    assert skipped_review.value.code == ErrorCode.STATE_INVALID_TRANSITION.value
    review = service.submit_review(
        "project-a", "rejected-contract", draft.version, actor="reviewer"
    )
    rejected = service.reject_review(
        "project-a", "rejected-contract", review.version, actor="reviewer"
    )
    assert rejected.status is ContractStatus.REJECTED
    with pytest.raises(JiejianError):
        service.submit_review(
            "project-a", "rejected-contract", rejected.version, actor="reviewer"
        )


def test_draft_requires_first_contract_version(
    governance: tuple[ContractGovernance, sessionmaker[Session], Engine],
) -> None:
    service, _, _ = governance
    with pytest.raises(JiejianError) as captured:
        service.create_draft(
            "project-a",
            "versioned-contract",
            snapshot=_contract("versioned-contract", version=2),
            sources=(_source("manual/versioned"),),
            actor="analyst",
        )
    assert captured.value.code == ErrorCode.CONTRACT_REFERENCE_INVALID.value


def test_manual_contract_without_provenance_sources_does_not_fabricate_source(
    governance: tuple[ContractGovernance, sessionmaker[Session], Engine],
) -> None:
    service, _, _ = governance
    draft = service.create_draft(
        "project-a",
        "source-free-contract",
        snapshot=_contract("source-free-contract"),
        actor="analyst",
    )
    assert draft.provenance.sources == ()
