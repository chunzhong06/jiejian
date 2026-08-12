"""LLM profile 的非秘密 SQLAlchemy 映射。"""

from __future__ import annotations

from sqlalchemy import BigInteger, Boolean, CheckConstraint, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class LLMProfileRow(Base):
    __tablename__ = "llm_profiles"
    __table_args__ = (
        CheckConstraint("schema_version = '1'", name="schema_version_value"),
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
    schema_version: Mapped[str] = mapped_column(String(8), nullable=False)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    model: Mapped[str] = mapped_column(String(256), nullable=False)
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
