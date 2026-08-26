# 验证录制凭据链的短驻留秘密边界与清理语义。

from __future__ import annotations

from pathlib import Path

from product.backend.workflows.context import ApplicationCore
from product.backend.workflows.recording.credentials import RuntimeSecretVault


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
    context = ApplicationCore(
        tmp_path / "var",
        environ={
            "BASE_ONLY": "base",
            "JIEJIAN_CONTROL_ORIGIN": "http://127.0.0.1:9000",
        },
    )
    context.secret_vault.put("onb_1", {"ONBOARDING_ONLY": "opaque"})

    assert context.environment_for_secret_names(("BASE_ONLY", "ONBOARDING_ONLY")) == {
        "BASE_ONLY": "base",
        "ONBOARDING_ONLY": "opaque",
    }
    assert "JIEJIAN_CONTROL_ORIGIN" not in context.environment_for_secret_names(
        ("JIEJIAN_CONTROL_ORIGIN",)
    )
    context.close()
    assert context.environment_for_secret_names(("BASE_ONLY", "ONBOARDING_ONLY")) == {
        "BASE_ONLY": "base",
    }
