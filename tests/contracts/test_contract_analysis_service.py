from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from jiejian.contracts.analysis.service import ContractAnalysisService
from jiejian.contracts.governance_service import ContractGovernanceService
from jiejian.contracts.governance import transition_contract_version
from jiejian.contracts.models import (
    ContractAuditAction,
    ContractAuditEntry,
    ContractProvenance,
    ContractSourceType,
    ContractVersion,
    SourceReference,
)
from jiejian.domain.lifecycle import ContractStatus
from jiejian.verification.models import (
    ContractRule,
    Flow,
    FlowStep,
    Identity,
    ResourceDefinition,
    RuleKind,
    SecurityContract,
    TargetScope,
)
from jiejian.errors import ErrorCode, JiejianError
from jiejian.protocols import ExecutionBudgetV1, ExecutionProjectSnapshotV1
from jiejian.protocols import FlowDraftStepV1, FlowDraftV1
from jiejian.storage import (
    ProjectRecord,
    StorageUnitOfWork,
    create_session_factory,
    create_sqlite_engine,
    upgrade_database,
)
from jiejian.execution.request_store import PersistedExecutionRequestV1
from jiejian.domain.lifecycle import JobState, ProjectStatus, RunLifecycle
from jiejian.storage.repositories import JobRecord, RunRecord
from jiejian.execution.request_store import ExecutionRequestStore

pytestmark = pytest.mark.database


@pytest.fixture
def analysis_services(tmp_path: Path) -> Iterator[tuple[ContractAnalysisService, ContractGovernanceService, object, Path]]:
    database = tmp_path / "analysis.db"
    upgrade_database(database)
    engine = create_sqlite_engine(database)
    factory = create_session_factory(engine)
    with StorageUnitOfWork(factory) as work:
        work.projects.add(
            ProjectRecord(
                project_id="analysis-project",
                name="analysis",
                status=ProjectStatus.READY,
                created_at_us=1,
                updated_at_us=1,
            )
        )
        work.commit()
    yield (
        ContractAnalysisService(lambda: StorageUnitOfWork(factory), var_dir=tmp_path),
        ContractGovernanceService(lambda: StorageUnitOfWork(factory), clock_us=iter([2, 3, 4, 5, 6, 7]).__next__, available_observers=("http",)),
        factory,
        tmp_path,
    )
    engine.dispose()


def _source(locator: str = "analysis.md") -> SourceReference:
    return SourceReference(
        source_type=ContractSourceType.REQUIREMENT_TEXT,
        locator=locator,
        content_sha256="a" * 64,
    )


def _rule() -> ContractRule:
    return ContractRule(
        id="side-effect",
        kind=RuleKind.UNAUTHORIZED_SIDE_EFFECT,
        required_observers=("http", "owner_api"),
        severity="critical",
    )


def test_governance_activation_uses_assessment_gate(
    analysis_services: tuple[ContractAnalysisService, ContractGovernanceService, object, Path],
) -> None:
    _, governance, _, _ = analysis_services
    draft = governance.create_draft(
        "analysis-project",
        "assessment-contract",
        rules=(_rule(),),
        sources=(_source(),),
        actor="analyst",
    )
    with pytest.raises(JiejianError) as captured:
        governance.submit_review(
            "analysis-project", "assessment-contract", draft.version, actor="reviewer"
        )
    assert captured.value.code == ErrorCode.CONTRACT_ASSESSMENT_BLOCKED.value


def test_application_compiles_flow_draft_and_bounds_source_paths(
    analysis_services: tuple[ContractAnalysisService, ContractGovernanceService, object, Path],
    tmp_path: Path,
) -> None:
    analysis, _, _, _ = analysis_services
    draft = FlowDraftV1(
        schema_version="1",
        recording_id="rec_" + "1" * 32,
        flow_id="confirmed-flow",
        revision=1,
        steps=(
            FlowDraftStepV1(
                schema_version="1",
                id="step-000001",
                name="read",
                identity_id="owner",
                alternate_identity_id="attacker",
                resource_id="resource",
                alternate_resource_id="foreign-resource",
                bindings_confirmed=True,
                method="GET",
                path="/resources/{resource_id}",
                expected_statuses=(200,),
                source_event_sequences=(1,),
                request_id="request_000001",
            ),
        ),
        variables=(),
    )
    assert not analysis.from_flow("analysis-project", draft).issues
    unconfirmed = draft.model_copy(update={"steps": (draft.steps[0].model_copy(update={"bindings_confirmed": False}),)})
    assert analysis.from_flow("analysis-project", unconfirmed).issues[0].code.value == "AMBIGUOUS_SOURCE"

    root = tmp_path / "project"
    root.mkdir()
    source = root / "routes.py"
    source.write_text("@router.get('/x')\ndef read(): ...\n", encoding="utf-8")
    assert analysis.from_fastapi_source("analysis-project", source, project_root=root).candidates

    outside = tmp_path / "outside.py"
    outside.write_text("@router.get('/x')\ndef read(): ...\n", encoding="utf-8")
    assert analysis.from_fastapi_source("analysis-project", outside, project_root=root).issues[0].code.value == "SOURCE_PATH_OUTSIDE_PROJECT"

    secret_dir = root / "secret-data"
    secret_dir.mkdir()
    secret_source = secret_dir / "routes.py"
    secret_source.write_text("@router.get('/x')\ndef read(): ...\n", encoding="utf-8")
    assert analysis.from_fastapi_source("analysis-project", secret_source, project_root=root).issues[0].code.value == "SOURCE_SUFFIX_DENIED"

    invalid_utf8 = root / "invalid.py"
    invalid_utf8.write_bytes(b"\xff\xfe")
    assert analysis.from_fastapi_source("analysis-project", invalid_utf8, project_root=root).issues[0].detail == "source_file_not_utf8"


def test_observer_resolver_is_rechecked_before_activation(
    analysis_services: tuple[ContractAnalysisService, ContractGovernanceService, object, Path],
) -> None:
    _, _, factory, _ = analysis_services
    observers = ["http", "owner_api"]
    governance = ContractGovernanceService(
        lambda: StorageUnitOfWork(factory),
        observer_resolver=lambda _project_id: tuple(observers),
        clock_us=iter(range(20, 30)).__next__,
    )
    draft = governance.create_draft(
        "analysis-project",
        "observer-drift-contract",
        rules=(_rule(),),
        sources=(_source("observer-drift.md"),),
        actor="analyst",
    )
    review = governance.submit_review(
        "analysis-project", "observer-drift-contract", draft.version, actor="reviewer"
    )
    observers[:] = ["http"]
    with pytest.raises(JiejianError) as captured:
        governance.activate_review(
            "analysis-project", "observer-drift-contract", review.version, actor="approver"
        )
    assert captured.value.code == ErrorCode.CONTRACT_ASSESSMENT_BLOCKED.value


def _snapshot(contract_id: str, version: int, status: ContractStatus) -> ExecutionProjectSnapshotV1:
    target = TargetScope(
        base_url="http://127.0.0.1:18080",
        allowed_origins=("http://127.0.0.1:18080",),
        allowed_hosts=("127.0.0.1",),
        allowed_ports=(18080,),
        allow_private_network=True,
    )
    flow = Flow(
        id="history-flow",
        steps=(
            FlowStep(
                id="read-resource",
                method="GET",
                path="/resources/{resource_id}",
                identity_id="owner",
                resource_id="resource",
                alternate_identity_id="attacker",
                alternate_resource_id="foreign-resource",
            ),
        ),
    )
    contract = SecurityContract(
        id=contract_id,
        version=version,
        status=status,
        rules=(ContractRule(id="foreign-read", kind=RuleKind.FOREIGN_READ, required_observers=("http",)),),
    )
    return ExecutionProjectSnapshotV1(
        schema_version="1",
        project_id="history-project",
        project_name="history",
        target=target,
        identities=(
            Identity(id="owner", role="owner", secret_ref="env:OWNER_TOKEN"),
            Identity(id="attacker", role="attacker", secret_ref="env:ATTACKER_TOKEN"),
        ),
        resources=(
            ResourceDefinition(id="resource", owner_identity_id="owner"),
            ResourceDefinition(id="foreign-resource", owner_identity_id="attacker"),
        ),
        flow=flow,
        contract=contract,
        owner_observer_enabled=True,
        mutation_seed=7,
    )


def test_history_resolver_prefers_governed_version_and_reads_legacy_request_only(
    tmp_path: Path,
) -> None:
    database = tmp_path / "history.db"
    upgrade_database(database)
    engine = create_sqlite_engine(database)
    factory = create_session_factory(engine)
    with StorageUnitOfWork(factory) as work:
        work.projects.add(ProjectRecord(project_id="history-project", name="history", status=ProjectStatus.READY, created_at_us=1, updated_at_us=1))
        governed_snapshot = _snapshot("history-contract", 1, ContractStatus.ACTIVE).contract
        work.contract_versions.add(
            ContractVersion(
                project_id="history-project",
                contract_id="history-contract",
                version=1,
                status=ContractStatus.ACTIVE,
                snapshot=governed_snapshot,
                provenance=ContractProvenance(sources=(_source("governed.md"),)),
                audit=(
                    ContractAuditEntry(action=ContractAuditAction.CREATED, actor="a", occurred_at_us=1),
                    ContractAuditEntry(action=ContractAuditAction.SUBMITTED, actor="a", occurred_at_us=2),
                    ContractAuditEntry(action=ContractAuditAction.ACTIVATED, actor="a", occurred_at_us=3),
                ),
                created_at_us=1,
                updated_at_us=3,
            )
        )
        work.runs.add(RunRecord(run_id="run_" + "1" * 32, project_id="history-project", contract_id="history-contract", contract_version=1, engine_version="0.1.0", lifecycle=RunLifecycle.QUEUED, created_at_us=4, updated_at_us=4))
        work.commit()
    resolver = ContractAnalysisService(lambda: StorageUnitOfWork(factory), var_dir=tmp_path)
    request = PersistedExecutionRequestV1(
        budget=ExecutionBudgetV1(
            schema_version="1",
            max_requests=64,
            request_timeout_us=5_000_000,
            max_duration_us=60_000_000,
            max_response_bytes=262_144,
            max_parallel_cases=1,
        ),
        project_snapshot=_snapshot("history-contract", 1, ContractStatus.ACTIVE),
    )
    request_hash, _ = ExecutionRequestStore(tmp_path).write("job_" + "1" * 32, request)
    with StorageUnitOfWork(factory) as work:
        work.jobs.add(JobRecord(job_id="job_" + "1" * 32, project_id="history-project", run_id="run_" + "1" * 32, operation_type="ACTIVE_RUN", state=JobState.PENDING, idempotency_key="history", request_hash=request_hash, attempt=0, max_attempts=1, available_at_us=4, fencing_token=0, created_at_us=4, updated_at_us=4))
        current = work.contract_versions.get("history-project", "history-contract", 1)
        assert current is not None
        work.contract_versions.replace(transition_contract_version(current, ContractStatus.SUPERSEDED, actor="system", occurred_at_us=5))
        work.commit()
    resolved = resolver.resolve_run_contract("run_" + "1" * 32)
    assert resolved.source.value == "EXECUTION_REQUEST"
    assert resolved.contract.status is ContractStatus.ACTIVE
    assert resolved.governed_version is not None
    assert resolved.governed_version.status is ContractStatus.SUPERSEDED

    legacy_request = PersistedExecutionRequestV1(
        budget=ExecutionBudgetV1(
            schema_version="1",
            max_requests=64,
            request_timeout_us=5_000_000,
            max_duration_us=60_000_000,
            max_response_bytes=262_144,
            max_parallel_cases=1,
        ),
        project_snapshot=_snapshot("legacy-contract", 4, ContractStatus.ACTIVE),
    )
    store = ExecutionRequestStore(tmp_path)
    legacy_hash, _ = store.write("job_" + "2" * 32, legacy_request)
    with StorageUnitOfWork(factory) as work:
        work.projects.add(ProjectRecord(project_id="legacy-project", name="legacy", status=ProjectStatus.READY, created_at_us=5, updated_at_us=5))
        # The snapshot's project identity is deliberately checked by the resolver; use a matching legacy project below.
        work.runs.add(RunRecord(run_id="run_" + "3" * 32, project_id="history-project", contract_id="legacy-contract", contract_version=4, engine_version="0.1.0", lifecycle=RunLifecycle.QUEUED, created_at_us=6, updated_at_us=6))
        work.jobs.add(JobRecord(job_id="job_" + "2" * 32, project_id="history-project", run_id="run_" + "3" * 32, operation_type="ACTIVE_RUN", state=JobState.PENDING, idempotency_key="legacy", request_hash=legacy_hash, attempt=0, max_attempts=1, available_at_us=6, fencing_token=0, created_at_us=6, updated_at_us=6))
        work.commit()
    legacy = resolver.resolve_run_contract("run_" + "3" * 32)
    assert legacy.source.value == "EXECUTION_REQUEST"
    assert legacy.contract.id == "legacy-contract"
    mismatch_hash, _ = store.write("job_" + "3" * 32, legacy_request)
    with StorageUnitOfWork(factory) as work:
        work.runs.add(RunRecord(run_id="run_" + "4" * 32, project_id="history-project", contract_id="wrong-contract", contract_version=4, engine_version="0.1.0", lifecycle=RunLifecycle.QUEUED, created_at_us=7, updated_at_us=7))
        work.jobs.add(JobRecord(job_id="job_" + "3" * 32, project_id="history-project", run_id="run_" + "4" * 32, operation_type="ACTIVE_RUN", state=JobState.PENDING, idempotency_key="legacy-mismatch", request_hash=mismatch_hash, attempt=0, max_attempts=1, available_at_us=7, fencing_token=0, created_at_us=7, updated_at_us=7))
        work.commit()
    with pytest.raises(JiejianError) as mismatch:
        resolver.resolve_run_contract("run_" + "4" * 32)
    assert mismatch.value.code == ErrorCode.CONTRACT_HISTORY_NOT_FOUND.value
    request_path = store.path_for("job_" + "2" * 32)
    request_path.write_bytes(b"tampered")
    with pytest.raises(JiejianError) as tampered:
        resolver.resolve_run_contract("run_" + "3" * 32)
    assert tampered.value.code == ErrorCode.JOB_REQUEST_CONFLICT.value
    engine.dispose()
