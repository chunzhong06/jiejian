# HTTP 执行候选是待确认配置线索，不属于 PermissionContract 或可执行 Profile。

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from product.backend.core.verification.permissions import canonical_sha256


class HttpBindingCandidateModel(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)
    schema_version: Literal["1"] = "1"


class HttpBindingCandidateSource(StrEnum):
    RECORDING = "RECORDING"
    OPENAPI_LINK = "OPENAPI_LINK"
    SCHEMA_DEPENDENCY = "SCHEMA_DEPENDENCY"
    NAME_HEURISTIC = "NAME_HEURISTIC"


class HttpProducerConsumerKind(StrEnum):
    OPENAPI_LINK = "OPENAPI_LINK"
    LOCATION_HEADER = "LOCATION_HEADER"
    SCHEMA_DEPENDENCY = "SCHEMA_DEPENDENCY"
    NAME_HEURISTIC = "NAME_HEURISTIC"


class HttpResponseSchemaCandidate(HttpBindingCandidateModel):
    status_code: str = Field(min_length=3, max_length=16)
    media_type: str = Field(min_length=1, max_length=128)
    schema_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    property_paths: tuple[str, ...] = Field(default=(), max_length=1024)


class HttpProducerConsumerLink(HttpBindingCandidateModel):
    kind: HttpProducerConsumerKind
    producer_operation_id: str = Field(min_length=1, max_length=256)
    consumer_operation_id: str | None = Field(default=None, min_length=1, max_length=256)
    consumer_field: str | None = Field(default=None, min_length=1, max_length=256)
    source_expression: str = Field(min_length=1, max_length=512)


class HttpBindingCandidate(HttpBindingCandidateModel):
    candidate_id: str = Field(pattern=r"^httpbind-[0-9a-f]{32}$")
    source: HttpBindingCandidateSource
    source_priority: int = Field(ge=0, le=3)
    source_locator: str = Field(min_length=1, max_length=512)
    operation_id: str = Field(min_length=1, max_length=256)
    method: Literal["GET", "PATCH", "POST", "PUT", "DELETE", "HEAD"]
    path: str = Field(min_length=1, max_length=2048)
    path_fields: tuple[str, ...] = Field(default=(), max_length=256)
    query_fields: tuple[str, ...] = Field(default=(), max_length=256)
    header_fields: tuple[str, ...] = Field(default=(), max_length=256)
    request_schema_fingerprint: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    response_schemas: tuple[HttpResponseSchemaCandidate, ...] = Field(default=(), max_length=256)
    security_scheme_ids: tuple[str, ...] = Field(default=(), max_length=64)
    producer_consumer_links: tuple[HttpProducerConsumerLink, ...] = Field(default=(), max_length=256)
    requires_confirmation: Literal[True] = True
    candidate_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_candidate(self) -> HttpBindingCandidate:
        priority = {
            HttpBindingCandidateSource.RECORDING: 0,
            HttpBindingCandidateSource.OPENAPI_LINK: 1,
            HttpBindingCandidateSource.SCHEMA_DEPENDENCY: 2,
            HttpBindingCandidateSource.NAME_HEURISTIC: 3,
        }[self.source]
        if self.source_priority != priority:
            raise ValueError("HTTP binding candidate source priority is invalid")
        for values in (
            self.path_fields,
            self.query_fields,
            self.header_fields,
            self.security_scheme_ids,
        ):
            if len(set(values)) != len(values) or values != tuple(sorted(values)):
                raise ValueError("HTTP binding candidate fields must be unique and sorted")
        payload = self.model_dump(mode="json", exclude={"candidate_id", "candidate_fingerprint"})
        expected = canonical_sha256(payload)
        if self.candidate_id != f"httpbind-{expected[:32]}" or self.candidate_fingerprint != expected:
            raise ValueError("HTTP binding candidate fingerprint does not match its payload")
        return self


class HttpBindingCandidateBatch(HttpBindingCandidateModel):
    candidates: tuple[HttpBindingCandidate, ...] = Field(default=(), max_length=4096)
    input_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_batch(self) -> HttpBindingCandidateBatch:
        expected = tuple(sorted(self.candidates, key=lambda item: (item.source_priority, item.candidate_id)))
        if self.candidates != expected:
            raise ValueError("HTTP binding candidates must follow source priority and stable ID")
        if len({item.candidate_id for item in self.candidates}) != len(self.candidates):
            raise ValueError("HTTP binding candidate IDs must be unique")
        return self
