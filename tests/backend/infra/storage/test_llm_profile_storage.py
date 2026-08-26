# 验证持久化基础设施中的模型配置存储。

from __future__ import annotations

from pathlib import Path

from product.backend.infra.llm.config import AIAssistanceSettings, LLMProfileConfig, LLMProviderType
from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.infra.storage import (
    StorageUnitOfWork,
    create_session_factory,
    create_sqlite_engine,
    upgrade_database,
)


def test_llm_profile_storage_round_trip_keeps_only_non_secret_configuration(tmp_path: Path) -> None:
    database = tmp_path / "llm.db"
    upgrade_database(database)
    engine = create_sqlite_engine(database)
    factory = create_session_factory(engine)
    profile = LLMProfileConfig(
        profile_name="deepseek-local",
        provider=LLMProviderType.OPENAI_COMPATIBLE,
        model="deepseek-chat",
        base_url="https://api.deepseek.com/v1/",
        secret_ref="env:DEEPSEEK_API_KEY",
        created_at_us=1,
        updated_at_us=2,
    )
    with StorageUnitOfWork(factory) as work:
        work.llm_profiles.add(profile)
        work.commit()
    with StorageUnitOfWork(factory) as work:
        assert work.llm_profiles.get("deepseek-local") == profile
        assert work.llm_profiles.list() == (profile,)
    engine.dispose()


def test_llm_profile_storage_rejects_known_secret_in_non_secret_fields(tmp_path: Path) -> None:
    database = tmp_path / "llm-secret.db"
    upgrade_database(database)
    engine = create_sqlite_engine(database)
    factory = create_session_factory(engine)
    profile = LLMProfileConfig(
        profile_name="secret-check",
        provider=LLMProviderType.OPENAI,
        model="known-secret-value",
        created_at_us=1,
        updated_at_us=1,
    )
    with StorageUnitOfWork(factory, known_secrets=("known-secret-value",)) as work:
        try:
            work.llm_profiles.add(profile)
        except JiejianError as exc:
            assert exc.code == ErrorCode.STORAGE_SECRET.value
            assert "known-secret-value" not in str(exc)
            assert "known-secret-value" not in repr(exc.to_dict())
        else:
            raise AssertionError("known secret must be rejected")
    engine.dispose()


def test_ai_assistance_settings_is_a_single_global_non_secret_row(tmp_path: Path) -> None:
    database = tmp_path / "ai-settings.db"
    upgrade_database(database)
    engine = create_sqlite_engine(database)
    factory = create_session_factory(engine)
    with StorageUnitOfWork(factory) as work:
        assert work.ai_assistance_settings.get() == AIAssistanceSettings(
            enabled=False,
            default_profile_name=None,
            updated_at_us=0,
        )
        work.ai_assistance_settings.replace(
            AIAssistanceSettings(enabled=False, default_profile_name=None, updated_at_us=1)
        )
        work.commit()
    with StorageUnitOfWork(factory) as work:
        assert work.ai_assistance_settings.get().updated_at_us == 1
    engine.dispose()
