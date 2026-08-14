from __future__ import annotations

from pathlib import Path

from jiejian.application.context import ApplicationContext
from jiejian.onboarding.secrets import RuntimeSecretVault


def test_runtime_secret_vault_is_opaque_and_clears_by_session() -> None:
    vault = RuntimeSecretVault()
    vault.put("onb_1", {"PRIMARY": "secret-value"})

    assert vault.resolve(("PRIMARY", "MISSING")) == {"PRIMARY": "secret-value"}
    assert "secret-value" not in repr(vault)
    assert "secret-value" not in str(vault.model_dump())
    vault.clear_session("onb_1")
    assert vault.resolve(("PRIMARY",)) == {}


def test_application_context_combines_base_environment_and_vault_then_clears(
    tmp_path: Path,
) -> None:
    context = ApplicationContext(tmp_path / "var", environ={"BASE_ONLY": "base"})
    context.secret_vault.put("onb_1", {"ONBOARDING_ONLY": "opaque"})

    assert context.environment_for_secret_names(("BASE_ONLY", "ONBOARDING_ONLY")) == {
        "BASE_ONLY": "base",
        "ONBOARDING_ONLY": "opaque",
    }
    context.close()
    assert context.environment_for_secret_names(("BASE_ONLY", "ONBOARDING_ONLY")) == {
        "BASE_ONLY": "base",
    }
