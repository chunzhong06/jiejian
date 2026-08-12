from __future__ import annotations

import pytest

import jiejian.contracts.llm.secrets as secrets_module
from jiejian.contracts.llm.secrets import WindowsCredentialManagerSecretStore


@pytest.mark.parametrize(
    "secret_ref",
    [
        "cred:",
        "cred:jiejian/llm/",
        "cred:jiejian/llm/a/b",
        "cred:jiejian/other/profile",
        "cred:jiejian/llm/Bad",
        "cred:jiejian/llm/profile.name",
    ],
)
def test_credential_store_rejects_invalid_reference_before_win32(
    monkeypatch: pytest.MonkeyPatch, secret_ref: str
) -> None:
    monkeypatch.setattr(
        secrets_module,
        "_advapi32",
        lambda: (_ for _ in ()).throw(AssertionError("Win32 API must not be called")),
    )
    store = object.__new__(WindowsCredentialManagerSecretStore)
    with pytest.raises(ValueError):
        store.write(secret_ref, "secret")
