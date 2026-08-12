# Run 请求模型。

from __future__ import annotations

from pydantic import Field

from .common import ApiModel


class RunCreateRequest(ApiModel):
    idempotency_key: str = Field(min_length=1, max_length=128)
