# LLM 候选的严格、无 provider 依赖的数据边界。

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from ..models import ContractCandidate
from ...verification.models import ContractRule


class LLMModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        strict=True,
        hide_input_in_errors=True,
    )

    schema_version: Literal["1"] = "1"


class LLMRuleCandidate(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        strict=True,
        hide_input_in_errors=True,
    )

    requirement_ids: tuple[str, ...] = Field(min_length=1, max_length=256)
    rule: ContractRule


class LLMOutput(LLMModel):
    candidates: tuple[LLMRuleCandidate, ...] = Field(min_length=1, max_length=32)


class LLMGenerationResult(LLMModel):
    candidates: tuple[ContractCandidate, ...] = Field(min_length=1, max_length=32)
    input_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    output_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
