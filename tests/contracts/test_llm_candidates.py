from __future__ import annotations

import json
import hashlib
import pytest

from product.backend.workflows.contracts.governance import ContractGovernance
from product.backend.workflows.contracts.candidate_generation import ContractCandidateGenerator
from product.backend.infra.llm.profiles import LLMProfileRegistry
from product.backend.infra.llm.adapters.base import LLMHttpResponse
from product.backend.infra.llm.config import LLMProviderType
from product.backend.core.contracts.models import (
    CandidateRiskKind,
    CandidateSuggestion,
    ContractSourceType,
    LLMGenerationMetadata,
    Requirement,
    SourceReference,
)
from product.backend.core.lifecycle import ProjectStatus
from product.backend.core.verification.permissions import PermissionContract
from product.backend.core.verification.permissions import (
    ActionDefinition,
    CoverageDimension,
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

pytestmark = pytest.mark.database


def _source(locator: str) -> SourceReference:
    return SourceReference(
        source_type=ContractSourceType.REQUIREMENT_TEXT,
        locator=locator,
        content_sha256="a" * 64,
    )


def _requirement(requirement_id: str, project_id: str, text: str) -> Requirement:
    return Requirement(
        requirement_id=requirement_id,
        project_id=project_id,
        source=_source("private/routes.py"),
        text=text,
        created_by="analyst",
        created_at_us=1,
    )


def _output(requirement_id: str) -> str:
    return json.dumps(
        {
            "schema_version": "1",
            "candidates": [
                {
                    "requirement_ids": [requirement_id],
                    "suggestion": {
                        "schema_version": "1",
                        "id": "foreign-read",
                        "kind": "FOREIGN_READ",
                        "required_observations": ["resource_state"],
                        "severity": "high",
                    },
                }
            ],
        }
    )


def _authorization_contract() -> PermissionContract:
    return PermissionContract(
        contract_id="authorization-contract",
        version=1,
        role_ids=("user",),
        workflow_states=("DRAFT",),
        subjects=(
            SubjectDefinition(subject_id="attacker", roles=("user",), tenant_id="tenant", department_id="department"),
            SubjectDefinition(subject_id="owner", roles=("user",), tenant_id="tenant", department_id="department"),
        ),
        actions=(ActionDefinition(action_id="modify", side_effect=True),),
        resources=(
            ResourceDefinition(resource_id="owner-resource", resource_type="document", tenant_id="tenant", department_id="department", owner_subject_id="owner", workflow_state="DRAFT"),
        ),
        relations=(
            RelationFact(
                relation_id="same-tenant-owner",
                relation=RelationType.SAME_TENANT,
                source=RelationEndpoint(endpoint_type="subject", endpoint_id="attacker"),
                target=RelationEndpoint(endpoint_type="subject", endpoint_id="owner"),
            ),
            RelationFact(
                relation_id="owns-owner-resource",
                relation=RelationType.OWNS,
                source=RelationEndpoint(endpoint_type="subject", endpoint_id="owner"),
                target=RelationEndpoint(endpoint_type="resource", endpoint_id="owner-resource"),
            ),
        ),
        rules=(
            PermissionRule(
                rule_id="unauthorized-modify",
                subject_id="attacker",
                action_id="modify",
                resource_id="owner-resource",
                relation_path=("same-tenant-owner", "owns-owner-resource"),
                expectation=PermissionExpectation.DENY,
                required_observations=("resource_state",),
                context=PermissionContext(resource_ids=("owner-resource",)),
                coverage_dimensions=(CoverageDimension.RELATION,),
            ),
        ),
        batch_rules=(),
    )


@pytest.fixture
def llm_context(tmp_path: Path):
    database = tmp_path / "llm.db"
    upgrade_database(database)
    engine = create_sqlite_engine(database)
    factory = create_session_factory(engine)
    with StorageUnitOfWork(factory) as work:
        work.projects.add(
            ProjectRecord(
                project_id="llm-project",
                name="llm",
                status=ProjectStatus.READY,
                created_at_us=1,
                updated_at_us=1,
            )
        )
        work.projects.add(
            ProjectRecord(
                project_id="other-project",
                name="other",
                status=ProjectStatus.READY,
                created_at_us=1,
                updated_at_us=1,
            )
        )
        work.requirements.add(
            _requirement(
                "req_" + "1" * 32,
                "llm-project",
                "suggestion id=foreign-read kind=FOREIGN_READ observations=resource_state severity=high note=supersecret",
            )
        )
        work.requirements.add(
            _requirement(
                "req_" + "2" * 32,
                "other-project",
                "suggestion id=foreign-read kind=FOREIGN_READ observations=resource_state severity=high",
            )
        )
        work.commit()
    yield factory, tmp_path
    engine.dispose()


def test_llm_generation_is_bounded_redacted_idempotent_and_persisted(llm_context) -> None:
    factory, _ = llm_context
    prompts: list[str] = []

    def provider(prompt: str) -> str:
        prompts.append(prompt)
        return _output("req_" + "1" * 32)

    service = ContractCandidateGenerator(
        lambda: StorageUnitOfWork(factory),
        provider=provider,
        provider_id="memory",
        model_id="test-model",
        known_secrets=("supersecret",),
        clock_us=iter((2, 3)).__next__,
    )
    first = service.generate("llm-project", ("req_" + "1" * 32,), actor="analyst")
    second = service.generate("llm-project", ("req_" + "1" * 32,), actor="other-analyst")
    assert first.candidates == second.candidates
    assert first.candidates[0].source.source_type is ContractSourceType.LLM
    metadata = first.candidates[0].llm_metadata
    assert isinstance(metadata, LLMGenerationMetadata)
    assert metadata.input_sha256 == first.input_sha256
    assert metadata.output_sha256 == first.output_sha256
    assert metadata.input_sha256 == hashlib.sha256(
        prompts[0].split("INPUT_JSON:\n", 1)[1].encode()
    ).hexdigest()
    assert first.candidates[0].source.locator == "llm:memory:1"
    assert "supersecret" not in prompts[0]
    assert "private/routes.py" not in prompts[0]
    assert "[REDACTED]" in prompts[0]
    with StorageUnitOfWork(factory) as work:
        stored = work.contract_candidates.get(first.candidates[0].candidate_id)
    assert stored == first.candidates[0]
    assert stored is not None
    assert stored.llm_metadata == metadata


def test_llm_requires_provider_and_rejects_unauthorized_requirement_before_call(llm_context) -> None:
    factory, _ = llm_context
    with pytest.raises(JiejianError) as unavailable:
        ContractCandidateGenerator(lambda: StorageUnitOfWork(factory)).generate(
            "llm-project", ("req_" + "1" * 32,), actor="analyst"
        )
    assert unavailable.value.code == ErrorCode.LLM_PROVIDER_UNAVAILABLE.value

    calls = 0

    def provider(_: str) -> str:
        nonlocal calls
        calls += 1
        return _output("req_" + "1" * 32)

    service = ContractCandidateGenerator(lambda: StorageUnitOfWork(factory), provider=provider)
    with pytest.raises(JiejianError) as unauthorized:
        service.generate("llm-project", ("req_" + "2" * 32,), actor="analyst")
    assert unauthorized.value.code == ErrorCode.LLM_REQUIREMENT_INVALID.value
    assert calls == 0


@pytest.mark.parametrize("payload", [
    "```json\n{}\n```",
    '{"schema_version":"1","candidates":[{"requirement_ids":["req_' + "1" * 32 + '"],"suggestion":{},"extra":"denied"}]}',
])
def test_llm_rejects_non_schema_output_without_leaking_response(llm_context, payload: str) -> None:
    factory, _ = llm_context
    service = ContractCandidateGenerator(lambda: StorageUnitOfWork(factory), provider=lambda _: payload)
    with pytest.raises(JiejianError) as captured:
        service.generate("llm-project", ("req_" + "1" * 32,), actor="analyst")
    assert captured.value.code == ErrorCode.LLM_OUTPUT_INVALID.value
    assert payload not in str(captured.value)


def test_generated_llm_candidate_conflict_is_blocked_by_governance(llm_context) -> None:
    factory, _ = llm_context
    requirement_id = "req_" + "1" * 32
    governance = ContractGovernance(
        lambda: StorageUnitOfWork(factory),
        clock_us=iter((10, 11, 12, 13)).__next__,
        available_observations=("resource_state",),
    )
    explicit = governance.create_candidate(
        "llm-project",
        source=SourceReference(
            source_type=ContractSourceType.STATIC_ANALYSIS,
            locator="analysis/routes.py#ownership",
            content_sha256="b" * 64,
        ),
        suggestion=CandidateSuggestion(
            id="ownership-side-effect",
            kind=CandidateRiskKind.UNAUTHORIZED_SIDE_EFFECT,
            required_observations=("resource_state",),
            severity="high",
        ),
        requirement_ids=(requirement_id,),
        actor="analyzer",
    )
    llm = ContractCandidateGenerator(
        lambda: StorageUnitOfWork(factory),
        provider=lambda _: _output(requirement_id),
        provider_id="memory",
        model_id="test-model",
        clock_us=iter((20,)).__next__,
    )
    generated = llm.generate("llm-project", (requirement_id,), actor="llm-adapter")
    llm_candidate = generated.candidates[0]
    assert llm_candidate.llm_metadata is not None

    contract = _authorization_contract()
    draft = governance.create_draft(
        "llm-project",
        contract.contract_id,
        snapshot=contract,
        candidate_ids=(explicit.candidate_id, llm_candidate.candidate_id),
        actor="analyst",
    )
    with pytest.raises(JiejianError) as captured:
        governance.submit_review(
            "llm-project", contract.contract_id, draft.version, actor="reviewer"
        )
    assert captured.value.code == ErrorCode.CONTRACT_ASSESSMENT_BLOCKED.value


def test_profile_resolver_generation_persists_compatible_provenance_without_secret(llm_context) -> None:
    factory, _ = llm_context

    class SecretStore:
        def __init__(self) -> None:
            self.value = "value-d"

        def write(self, secret_ref: str, secret: str) -> None:
            self.value = secret

        def read(self, secret_ref: str) -> str | None:
            return self.value

        def delete(self, secret_ref: str) -> None:
            self.value = ""

        def configured(self, secret_ref: str | None) -> bool:
            return bool(self.value)

    class Transport:
        def __init__(self) -> None:
            self.calls = 0
            self.prompts: list[bytes] = []

        def send(self, request):
            self.calls += 1
            self.prompts.append(request.body)
            return LLMHttpResponse(
                200,
                json.dumps(
                    {"choices": [{"message": {"content": _output("req_" + "1" * 32)}}]}
                ).encode(),
            )

    store = SecretStore()
    transport = Transport()
    profiles = LLMProfileRegistry(
        lambda **kwargs: StorageUnitOfWork(factory, **kwargs),
        transport=transport,
        secret_store=store,
        clock_us=iter((10, 20, 30, 40)).__next__,
    )
    profiles.create(
        {
            "profile_name": "profile-one",
            "provider": LLMProviderType.OPENAI,
            "model": "gpt-test",
        },
        secret=store.value,
    )
    service = ContractCandidateGenerator(
        lambda: StorageUnitOfWork(factory),
        profile_resolver=profiles,
        clock_us=iter((50, 60, 70, 80, 100, 120)).__next__,
    )
    result = service.generate(
        "llm-project",
        ("req_" + "1" * 32,),
        actor="analyst",
        profile_name="profile-one",
    )
    assert transport.calls == 1
    assert "value-d" not in transport.prompts[0].decode()
    metadata = result.candidates[0].llm_metadata
    assert metadata is not None
    assert metadata.provenance_schema_version == "2"
    assert metadata.profile_name == "profile-one"
    assert metadata.provider == "openai"
    assert metadata.model == "gpt-test"
    assert result.candidates[0].source.locator == "llm:openai:1"
    assert metadata.input_sha256 == hashlib.sha256(
        json.loads(transport.prompts[0])["messages"][0]["content"].split("INPUT_JSON:\n", 1)[1].encode()
    ).hexdigest()
    assert metadata.estimated_cost_microusd is None
    with StorageUnitOfWork(factory) as work:
        stored = work.contract_candidates.get(result.candidates[0].candidate_id)
    assert stored is not None
    assert "value-d" not in stored.model_dump_json()

    repeated = service.generate(
        "llm-project",
        ("req_" + "1" * 32,),
        actor="second-analyst",
        profile_name="profile-one",
    )
    assert transport.calls == 2
    assert repeated.candidates == result.candidates
    assert repeated.candidates[0].llm_metadata == metadata


def test_profile_resolver_rejects_disabled_unconfigured_and_unauthorized_before_request(llm_context) -> None:
    factory, _ = llm_context
    calls = 0

    class Store:
        def read(self, secret_ref: str) -> str | None:
            return None

        def write(self, secret_ref: str, secret: str) -> None:
            pass

        def delete(self, secret_ref: str) -> None:
            pass

        def configured(self, secret_ref: str | None) -> bool:
            return False

    class Transport:
        def send(self, request):
            nonlocal calls
            calls += 1
            raise AssertionError("transport must not be called")

    profiles = LLMProfileRegistry(
        lambda **kwargs: StorageUnitOfWork(factory, **kwargs),
        transport=Transport(),
        secret_store=Store(),
        clock_us=lambda: 1,
    )
    profiles.create(
        {
            "profile_name": "disabled",
            "provider": LLMProviderType.OPENAI,
            "model": "gpt",
            "enabled": False,
        },
    )
    service = ContractCandidateGenerator(
        lambda: StorageUnitOfWork(factory), profile_resolver=profiles
    )
    requirement_id = "req_" + "1" * 32
    with pytest.raises(JiejianError) as disabled:
        service.generate("llm-project", (requirement_id,), actor="a", profile_name="disabled")
    assert disabled.value.code == ErrorCode.LLM_PROVIDER_UNAVAILABLE.value
    with pytest.raises(JiejianError) as unconfigured:
        service.generate("llm-project", (requirement_id,), actor="a", profile_name="missing")
    assert unconfigured.value.code == ErrorCode.LLM_PROFILE_NOT_FOUND.value
    with pytest.raises(JiejianError) as unauthorized:
        service.generate("llm-project", ("req_" + "2" * 32,), actor="a", profile_name="disabled")
    assert unauthorized.value.code == ErrorCode.LLM_REQUIREMENT_INVALID.value
    assert calls == 0
