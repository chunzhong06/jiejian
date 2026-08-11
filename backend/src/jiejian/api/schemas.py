"""控制面输入输出 Schema。"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ApiModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, hide_input_in_errors=True)
    schema_version: Literal["1"] = "1"


class ProjectRegisterRequest(ApiModel):
    path: str = Field(min_length=1, max_length=2048)
    revalidate: bool = False


class ContractActivateRequest(ApiModel):
    path: str = Field(min_length=1, max_length=2048)


class RecordingCreateRequest(ApiModel):
    # JSON arrays decode to list; tuple conversion belongs at the application boundary.
    identities: list[str] | None = None
    duration_seconds: int = Field(default=60, ge=1, le=3_600)
    headless: bool = True
    idempotency_key: str = Field(min_length=1, max_length=128)


class RunCreateRequest(ApiModel):
    idempotency_key: str = Field(min_length=1, max_length=128)


class ReviewRequest(ApiModel):
    command: dict[str, Any]
    bindings: dict[str, dict[str, str]] | None = None


class ApiResponse(ApiModel):
    data: Any


class HealthResponse(ApiModel):
    status: Literal["ok"]


class ReadyResponse(ApiModel):
    status: Literal["ready"]
    worker: Literal["running", "stopped"]
