# LLM profile 的非秘密 SQLAlchemy 映射；秘密正文只存在于凭据存储。

from __future__ import annotations

from sqlalchemy import BigInteger, Boolean, CheckConstraint, ForeignKey, Integer, String, select
from sqlalchemy.orm import Mapped, mapped_column

from product.backend.infra.storage.base import Base


class LLMProfileRow(Base):
    __tablename__ = "llm_profiles"
    __table_args__ = (
        CheckConstraint(
            "provider IN ('openai', 'deepseek', 'gemini', 'openai_compatible')",
            name="provider_value",
        ),
        CheckConstraint(
            "length(profile_name) BETWEEN 1 AND 128 AND "
            "substr(profile_name, 1, 1) GLOB '[a-z]' AND "
            "profile_name NOT GLOB '*[^a-z0-9_-]*'",
            name="profile_name_format",
        ),
        CheckConstraint("length(model) BETWEEN 1 AND 256", name="model_length"),
        CheckConstraint("base_url IS NULL OR length(base_url) BETWEEN 1 AND 2048", name="base_url_length"),
        CheckConstraint("timeout_ms BETWEEN 100 AND 300000", name="timeout_range"),
        CheckConstraint("max_input_bytes BETWEEN 1 AND 1048576", name="input_bytes_range"),
        CheckConstraint("max_output_bytes BETWEEN 1 AND 1048576", name="output_bytes_range"),
        CheckConstraint("max_budget_microusd BETWEEN 0 AND 1000000000", name="budget_range"),
        CheckConstraint("secret_ref IS NULL OR length(secret_ref) BETWEEN 1 AND 256", name="secret_ref_length"),
        CheckConstraint("created_at_us >= 0 AND updated_at_us >= created_at_us", name="time_order"),
    )

    profile_name: Mapped[str] = mapped_column(String(128), primary_key=True)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    model: Mapped[str] = mapped_column(String(256), nullable=False)
    reasoning_effort: Mapped[str | None] = mapped_column(String(16), nullable=True)
    base_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    timeout_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    max_input_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    max_output_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    max_budget_microusd: Mapped[int] = mapped_column(BigInteger, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False)
    secret_ref: Mapped[str | None] = mapped_column(String(256), nullable=True)
    allow_local_http: Mapped[bool] = mapped_column(Boolean, nullable=False)
    created_at_us: Mapped[int] = mapped_column(BigInteger, nullable=False)
    updated_at_us: Mapped[int] = mapped_column(BigInteger, nullable=False)


class AIAssistanceSettingsRow(Base):
    __tablename__ = "ai_assistance_settings"
    __table_args__ = (
        CheckConstraint("settings_key = 'default'", name="settings_key_value"),
    )

    settings_key: Mapped[str] = mapped_column(String(16), primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False)
    default_profile_name: Mapped[str | None] = mapped_column(
        String(128), ForeignKey("llm_profiles.profile_name", ondelete="SET NULL"), nullable=True
    )
    updated_at_us: Mapped[int] = mapped_column(BigInteger, nullable=False)

# 本聚合的 Repository 与持久化记录边界。

"""LLM profile 与全局 AI 辅助设置的非秘密配置仓储。"""

from collections.abc import Sequence

from sqlalchemy.orm import Session

from product.backend.infra.llm.config import AIAssistanceSettings, LLMProfileConfig, LLMProviderType
from product.backend.core.errors import ErrorCode, JiejianError

from product.backend.infra.storage.base import _flush, _scalar, _scalars, ensure_storage_payload_safe


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
            "provider": profile.provider.value,
            "model": profile.model,
            "reasoning_effort": profile.reasoning_effort,
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
                "profile_name": row.profile_name,
                "provider": LLMProviderType(row.provider),
                "model": row.model,
                "reasoning_effort": row.reasoning_effort,
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


class AIAssistanceSettingsRepository:
    def __init__(self, session: Session, known_secrets: Sequence[str]) -> None:
        self._session = session
        self._known_secrets = known_secrets

    def get(self) -> AIAssistanceSettings:
        row = _scalar(
            self._session,
            select(AIAssistanceSettingsRow).where(AIAssistanceSettingsRow.settings_key == "default"),
        )
        if row is None:
            return AIAssistanceSettings(enabled=False, default_profile_name=None, updated_at_us=0)
        return AIAssistanceSettings(
            enabled=row.enabled,
            default_profile_name=row.default_profile_name,
            updated_at_us=row.updated_at_us,
        )

    def replace(self, settings: AIAssistanceSettings) -> None:
        values = {
            "settings_key": "default",
            "enabled": settings.enabled,
            "default_profile_name": settings.default_profile_name,
            "updated_at_us": settings.updated_at_us,
        }
        ensure_storage_payload_safe(values, self._known_secrets)
        row = _scalar(
            self._session,
            select(AIAssistanceSettingsRow).where(AIAssistanceSettingsRow.settings_key == "default"),
        )
        if row is None:
            self._session.add(AIAssistanceSettingsRow(**values))
        else:
            for key, value in values.items():
                setattr(row, key, value)
        _flush(self._session)
