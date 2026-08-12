from __future__ import annotations

import pytest
from pydantic import ValidationError

from jiejian.contracts.governance import transition_contract_version
from jiejian.contracts.models import (
    ContractAuditAction,
    ContractAuditEntry,
    ContractCandidate,
    ContractProvenance,
    ContractSourceType,
    ContractVersion,
    LLMGenerationMetadata,
    Requirement,
    SourceReference,
)
from jiejian.domain.lifecycle import ContractStatus
from jiejian.verification.models import ContractRule, RuleKind, SecurityContract
from jiejian.errors import ErrorCode, JiejianError

SHA256 = "a" * 64


def _source() -> SourceReference:
    return SourceReference(
        source_type=ContractSourceType.REQUIREMENT_TEXT,
        locator="requirements/security.md#ownership",
        content_sha256=SHA256,
    )


def _rule(rule_id: str = "foreign-read") -> ContractRule:
    return ContractRule(
        id=rule_id,
        kind=RuleKind.FOREIGN_READ,
        required_observers=("http",),
        severity="high",
    )


def _draft(*rules: ContractRule) -> ContractVersion:
    return ContractVersion(
        project_id="contract-project",
        contract_id="ownership-contract",
        version=1,
        status=ContractStatus.DRAFT,
        snapshot=SecurityContract(
            id="ownership-contract",
            version=1,
            status=ContractStatus.DRAFT,
            rules=rules or (_rule(),),
        ),
        provenance=ContractProvenance(sources=(_source(),)),
        audit=(
            ContractAuditEntry(
                action=ContractAuditAction.CREATED,
                actor="reviewer",
                occurred_at_us=10,
            ),
        ),
        created_at_us=10,
        updated_at_us=10,
    )


def test_requirement_and_candidate_are_strict_frozen_and_traceable() -> None:
    requirement = Requirement(
        requirement_id="req_" + "1" * 32,
        project_id="contract-project",
        source=_source(),
        text="用户只能读取自己的资源",
        security_tags=("ownership",),
        created_by="analyst",
        created_at_us=10,
    )
    candidate = ContractCandidate(
        candidate_id="cand_" + "2" * 32,
        project_id=requirement.project_id,
        source=_source(),
        rule=_rule(),
        requirement_ids=(requirement.requirement_id,),
        created_by="analyst",
        created_at_us=11,
    )

    assert requirement.schema_version == candidate.schema_version == "1"
    assert candidate.requirement_ids == (requirement.requirement_id,)
    with pytest.raises(ValidationError):
        Requirement.model_validate(
            {**requirement.model_dump(), "created_at_us": "10"}
        )
    with pytest.raises(ValidationError):
        candidate.rule = _rule("changed")


def test_contract_version_rejects_empty_or_duplicate_rules() -> None:
    with pytest.raises(ValidationError):
        SecurityContract(
            id="ownership-contract",
            version=1,
            status=ContractStatus.DRAFT,
            rules=(),
        )
    with pytest.raises(ValidationError, match="unique"):
        _draft(_rule(), _rule())


def test_llm_candidate_requires_exclusive_generation_metadata() -> None:
    metadata = LLMGenerationMetadata(
        provider_id="memory",
        model_id="model",
        adapter_version="1",
        prompt_template_id="template",
        prompt_template_version="1",
        prompt_template_sha256="b" * 64,
        input_sha256="c" * 64,
        output_sha256="d" * 64,
    )
    llm_source = _source().model_copy(update={"source_type": ContractSourceType.LLM})
    with pytest.raises(ValidationError):
        ContractCandidate(
            candidate_id="cand_" + "3" * 32,
            project_id="contract-project",
            source=llm_source,
            rule=_rule(),
            created_by="analyst",
            created_at_us=11,
        )
    with pytest.raises(ValidationError):
        ContractCandidate(
            candidate_id="cand_" + "4" * 32,
            project_id="contract-project",
            source=_source(),
            rule=_rule(),
            created_by="analyst",
            created_at_us=11,
            llm_metadata=metadata,
        )


def test_candidate_cannot_skip_review_and_active_is_frozen() -> None:
    draft = _draft()
    with pytest.raises(ValidationError, match="audit trail"):
        ContractVersion(
            **{
                **draft.model_dump(),
                "status": ContractStatus.ACTIVE,
                "snapshot": draft.snapshot.model_copy(
                    update={"status": ContractStatus.ACTIVE}
                ),
                "audit": (
                    draft.audit[0],
                    ContractAuditEntry(
                        action=ContractAuditAction.ACTIVATED,
                        actor="approver",
                        occurred_at_us=11,
                    ),
                ),
                "updated_at_us": 11,
            }
        )
    with pytest.raises(JiejianError) as captured:
        transition_contract_version(
            draft,
            ContractStatus.ACTIVE,
            actor="reviewer",
            occurred_at_us=11,
        )
    assert captured.value.code == ErrorCode.STATE_INVALID_TRANSITION.value

    review = transition_contract_version(
        draft,
        ContractStatus.REVIEW,
        actor="reviewer",
        occurred_at_us=11,
    )
    active = transition_contract_version(
        review,
        ContractStatus.ACTIVE,
        actor="approver",
        occurred_at_us=12,
    )
    assert active.snapshot.status is ContractStatus.ACTIVE
    with pytest.raises(ValidationError):
        active.snapshot = active.snapshot.model_copy(update={"rules": (_rule("changed"),)})
