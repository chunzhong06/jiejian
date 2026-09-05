# 验证录制凭据链的短驻留秘密边界与清理语义。

from __future__ import annotations

from pathlib import Path
import pytest

from product.backend.composition import ApplicationCore
from product.backend.core.errors import JiejianError
from product.backend.workflows.recording.credentials import RuntimeSecretVault
from tests.fixtures.action_preparation import MemorySecretStore


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
        secret_store=MemorySecretStore(),
    )
    context.runtime_secrets.put("onb_1", {"ONBOARDING_ONLY": "opaque"})

    assert context.environment_for_secret_names(("ONBOARDING_ONLY",)) == {
        "BASE_ONLY": "base",
        "ONBOARDING_ONLY": "opaque",
    }
    for names in (("BASE_ONLY", "ONBOARDING_ONLY"), ("JIEJIAN_CONTROL_ORIGIN",)):
        with pytest.raises(JiejianError) as error:
            context.environment_for_secret_names(names)
        assert error.value.code == "TEST_IDENTITY_NOT_READY"
    context.close()
    assert context.runtime_secrets.model_dump() == {"session_count": 0}
    with pytest.raises(JiejianError) as error:
        context.environment_for_secret_names(("ONBOARDING_ONLY",))
    assert error.value.code == "TEST_IDENTITY_NOT_READY"
