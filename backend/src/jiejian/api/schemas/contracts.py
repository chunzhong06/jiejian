# Contract 治理请求模型。

from __future__ import annotations

from pydantic import Field, model_validator

from .common import ApiModel


class RequirementCreateRequest(ApiModel):
    text: str = Field(min_length=1, max_length=16_384)
    security_tags: list[str] = Field(default_factory=list, max_length=64)
    actor: str = Field(min_length=1, max_length=128)


class CandidateDeriveRequest(ApiModel):
    requirement_ids: list[str] = Field(default_factory=list, max_length=512)
    include_flow: bool = False
    actor: str = Field(min_length=1, max_length=128)

    @model_validator(mode="after")
    def require_source(self) -> CandidateDeriveRequest:
        if not self.requirement_ids and not self.include_flow:
            raise ValueError("requirement_ids or include_flow is required")
        return self


class LLMCandidateRequest(ApiModel):
    requirement_ids: list[str] = Field(min_length=1, max_length=512)
    actor: str = Field(min_length=1, max_length=128)
    profile_name: str | None = Field(default=None, min_length=1, max_length=128)


class ContractDraftRequest(ApiModel):
    contract_id: str = Field(min_length=1, max_length=128)
    candidate_ids: list[str] = Field(min_length=1, max_length=512)
    actor: str = Field(min_length=1, max_length=128)


class ContractRevisionRequest(ApiModel):
    candidate_ids: list[str] = Field(min_length=1, max_length=512)
    actor: str = Field(min_length=1, max_length=128)


class GovernanceActorRequest(ApiModel):
    actor: str = Field(min_length=1, max_length=128)
