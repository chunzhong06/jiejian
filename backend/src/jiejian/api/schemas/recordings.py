# Recording 请求模型。

from __future__ import annotations

from typing import Any

from pydantic import Field

from .common import ApiModel


class RecordingCreateRequest(ApiModel):
    # JSON arrays decode to list; tuple conversion belongs at the application boundary.
    identities: list[str] | None = None
    duration_seconds: int = Field(default=60, ge=1, le=3_600)
    headless: bool = True
    idempotency_key: str = Field(min_length=1, max_length=128)


class ReviewRequest(ApiModel):
    command: dict[str, Any]
    bindings: dict[str, dict[str, str]] | None = None
