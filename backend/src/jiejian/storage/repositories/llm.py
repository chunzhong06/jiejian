"""LLM profile 非秘密配置仓储。"""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from ...contracts.llm.config import LLMProfileConfig, LLMProviderType
from ...errors import ErrorCode, JiejianError
from ..models import LLMProfileRow
from .base import (
    _flush,
    _scalar,
    _scalars,
    ensure_storage_payload_safe,
)


class LLMProfileRepository:
    def __init__(self, session: Session, known_secrets: Sequence[str]) -> None:
        self._session = session
        self._known_secrets = known_secrets

    def add(self, profile: LLMProfileConfig) -> None:
        values = self._row_values(profile)
        ensure_storage_payload_safe(values, self._known_secrets)
        self._session.add(LLMProfileRow(**values))
        _flush(self._session)

    def get(self, profile_name: str) -> LLMProfileConfig | None:
        row = _scalar(
            self._session,
            select(LLMProfileRow).where(LLMProfileRow.profile_name == profile_name),
        )
        return None if row is None else self._record(row)

    def list(self) -> tuple[LLMProfileConfig, ...]:
        rows = _scalars(self._session, select(LLMProfileRow).order_by(LLMProfileRow.profile_name))
        return tuple(self._record(row) for row in rows)

    def replace(self, profile: LLMProfileConfig) -> None:
        values = self._row_values(profile)
        ensure_storage_payload_safe(values, self._known_secrets)
        row = _scalar(
            self._session,
            select(LLMProfileRow).where(LLMProfileRow.profile_name == profile.profile_name),
        )
        if row is None:
            raise JiejianError(ErrorCode.STORAGE_CONSTRAINT, "LLM profile 不存在")
        for key, value in values.items():
            setattr(row, key, value)
        _flush(self._session)

    @staticmethod
    def _row_values(profile: LLMProfileConfig) -> dict[str, object]:
        return {
            "profile_name": profile.profile_name,
            "schema_version": profile.schema_version,
            "provider": profile.provider.value,
            "model": profile.model,
            "base_url": profile.base_url,
            "timeout_ms": profile.timeout_ms,
            "max_input_bytes": profile.max_input_bytes,
            "max_output_bytes": profile.max_output_bytes,
            "max_budget_microusd": profile.max_budget_microusd,
            "enabled": profile.enabled,
            "secret_ref": profile.secret_ref,
            "allow_local_http": profile.allow_local_http,
            "created_at_us": profile.created_at_us,
            "updated_at_us": profile.updated_at_us,
        }

    @staticmethod
    def _record(row: LLMProfileRow) -> LLMProfileConfig:
        return LLMProfileConfig.model_validate(
            {
                "schema_version": row.schema_version,
                "profile_name": row.profile_name,
                "provider": LLMProviderType(row.provider),
                "model": row.model,
                "base_url": row.base_url,
                "timeout_ms": row.timeout_ms,
                "max_input_bytes": row.max_input_bytes,
                "max_output_bytes": row.max_output_bytes,
                "max_budget_microusd": row.max_budget_microusd,
                "enabled": row.enabled,
                "secret_ref": row.secret_ref,
                "allow_local_http": row.allow_local_http,
                "created_at_us": row.created_at_us,
                "updated_at_us": row.updated_at_us,
            }
        )
