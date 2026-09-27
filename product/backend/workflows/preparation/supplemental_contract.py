# 补充材料的唯一导入根和安全规范化；格式接受不表示材料真实或独立验证。
from __future__ import annotations

import hashlib
import re
from typing import Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, model_validator
from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.infra.storage.base import _canonical_json, ensure_storage_payload_safe


class MaterialModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, hide_input_in_errors=True)


class SupplementalRecord(MaterialModel):
    recorded_at_us: int = Field(ge=0)
    resource_label: str = Field(min_length=1, max_length=128)
    event_label: str = Field(min_length=1, max_length=256)


class SupplementalDocument(MaterialModel):
    schema_version: Literal["1"]
    project_id: str = Field(min_length=1, max_length=64)
    action_id: str = Field(min_length=1, max_length=36)
    action_revision: int = Field(ge=1)
    title: str = Field(min_length=1, max_length=128)
    source_label: str = Field(min_length=1, max_length=128)
    claimed_resource_label: str | None = Field(default=None, max_length=128)
    records: list[SupplementalRecord] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def safe_document(self):
        validate_material_payload(self.model_dump(mode="json"))
        return self


def validate_material_payload(value, known_secrets=()):
    """只接受有界文本；拒绝已知秘密及典型凭据，不声称识别任意伪装秘密。"""
    ensure_storage_payload_safe(value, known_secrets)
    raw = _canonical_json(value)
    if re.search(r"-----BEGIN [A-Z ]*PRIVATE KEY-----|\bcredentials\s*[:=]\s*\S+|<\s*script\b|javascript\s*:", raw, re.I):
        raise JiejianError(ErrorCode.STORAGE_SECRET, "材料包含不允许的敏感或可执行内容")
    if len(raw.encode("utf-8")) > 65536:
        raise JiejianError(ErrorCode.INPUT_INVALID, "材料超过 64KiB 上限")
    return raw


def material_fingerprint(value):
    return hashlib.sha256(validate_material_payload(value).encode("utf-8")).hexdigest()


def request_uuid(value):
    try:
        return str(UUID(value))
    except (ValueError, TypeError, AttributeError):
        raise JiejianError(ErrorCode.INPUT_INVALID, "请求标识必须为 UUID") from None
