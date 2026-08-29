# 验证确定性 Compiler 使用的内部 ContractVersion 事务。

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from product.backend.core.contracts.models import ContractSourceType, SourceReference
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
from product.backend.workflows.contracts.governance import ContractGovernance


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
        work.projects.add(
            ProjectRecord(
                project_id="project-a",
                name="project-a",
                status=ProjectStatus.READY,
                created_at_us=NOW_US,
                updated_at_us=NOW_US,
            )
        )
        work.commit()
    ticks = iter(range(NOW_US + 1, NOW_US + 100))
    yield (
        ContractGovernance(
            lambda: StorageUnitOfWork(factory),
            clock_us=lambda: next(ticks),
            available_observations=("resource_state",),
        ),
        factory,
        engine,
    )
    engine.dispose()


def _source(locator: str = "permission-intent:project-a") -> SourceReference:
    return SourceReference(
        source_type=ContractSourceType.PROJECT_CONFIG,
        locator=locator,
        content_sha256="a" * 64,
    )


def _contract(
    version: int = 1,
    *,
    required_observations: tuple[str, ...] = ("resource_state",),
) -> PermissionContract:
    return PermissionContract(
        contract_id="generated-contract-project-a",
        version=version,
        role_ids=("member",),
        workflow_states=("READY",),
        subjects=(SubjectDefinition(subject_id="member", roles=("member",), tenant_id="tenant"),),
        effects=(SecurityEffectDefinition(effect_id="document-read", kind=SecurityEffectKind.DATA_DISCLOSURE, resource_type="document", protected_fields=("content",)),),
        actions=(ActionDefinition(action_id="view", effect_ids=("document-read",)),),
        resources=(ResourceDefinition(resource_id="document", resource_type="document", owner_subject_id="member", tenant_id="tenant", workflow_state="READY"),),
        relations=(RelationFact(relation_id="owns-document", relation=RelationType.OWNS, source=RelationEndpoint(endpoint_type="subject", endpoint_id="member"), target=RelationEndpoint(endpoint_type="resource", endpoint_id="document")),),
        rules=(PermissionRule(rule_id="foreign-read", subject_id="member", action_id="view", resource_id="document", relation_path=("owns-document",), context=PermissionContext(resource_ids=("document",)), expectation=PermissionExpectation.DENY, required_observations=required_observations, coverage_dimensions=(CoverageDimension.RELATION,)),),
    )


def test_internal_contract_version_chain_preserves_sources_and_supersedes(
    governance: tuple[ContractGovernance, sessionmaker[Session], Engine],
) -> None:
    service, factory, _ = governance
    draft = service.create_draft(
        "project-a",
        "generated-contract-project-a",
        snapshot=_contract(),
        sources=(_source(), _source()),
        actor="compiler",
    )
    review = service.submit_review(
        "project-a",
        draft.contract_id,
        draft.version,
        actor="compiler",
    )
    active_v1 = service.activate_review(
        "project-a",
        review.contract_id,
        review.version,
        actor="compiler",
    )
    draft_v2 = service.revise_active(
        "project-a",
        active_v1.contract_id,
        snapshot=_contract(2),
        sources=(_source("permission-intent:project-a:v2"),),
        actor="compiler",
    )
    review_v2 = service.submit_review(
        "project-a",
        draft_v2.contract_id,
        draft_v2.version,
        actor="compiler",
    )
    active_v2 = service.activate_review(
        "project-a",
        review_v2.contract_id,
        review_v2.version,
        actor="compiler",
    )

    assert draft.provenance.sources == (_source(),)
    assert active_v2.version == 2
    with StorageUnitOfWork(factory) as work:
        stored_v1 = work.contract_versions.get("project-a", active_v1.contract_id, 1)
        project = work.projects.get("project-a")
    assert stored_v1 is not None and stored_v1.status is ContractStatus.SUPERSEDED
    assert project is not None
    assert (project.governed_contract_id, project.governed_contract_version) == (
        active_v2.contract_id,
        active_v2.version,
    )


def test_internal_review_fails_closed_when_required_observation_is_missing(
    governance: tuple[ContractGovernance, sessionmaker[Session], Engine],
) -> None:
    service, _, _ = governance
    draft = service.create_draft(
        "project-a",
        "generated-contract-project-a",
        snapshot=_contract(required_observations=("sql_trace",)),
        actor="compiler",
    )

    with pytest.raises(JiejianError) as captured:
        service.submit_review(
            "project-a",
            draft.contract_id,
            draft.version,
            actor="compiler",
        )

    assert captured.value.code == ErrorCode.CONTRACT_ASSESSMENT_BLOCKED.value


def test_internal_version_transition_cannot_skip_review(
    governance: tuple[ContractGovernance, sessionmaker[Session], Engine],
) -> None:
    service, _, _ = governance
    draft = service.create_draft(
        "project-a",
        "generated-contract-project-a",
        snapshot=_contract(),
        actor="compiler",
    )

    with pytest.raises(JiejianError) as captured:
        service.activate_review(
            "project-a",
            draft.contract_id,
            draft.version,
            actor="compiler",
        )

    assert captured.value.code == ErrorCode.STATE_INVALID_TRANSITION.value
