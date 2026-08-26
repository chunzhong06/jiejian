# 验证共享秘密引用只接受登记命名空间与固定分段深度。

from __future__ import annotations

import pytest

from product.backend.infra.secrets import (
    credential_ref,
    validate_credential_secret_ref,
)


def test_shared_secret_refs_keep_llm_and_test_identity_namespaces_isolated() -> None:
    assert credential_ref("llm", "primary") == "cred:jiejian/llm/primary"
    identity_ref = credential_ref(
        "test-identity",
        "sample-project",
        "tid_0123456789abcdef0123456789abcdef",
        "cookie-00",
    )
    assert validate_credential_secret_ref(identity_ref) == identity_ref

    for invalid in (
        "cred:jiejian/unknown/value",
        "cred:jiejian/llm/primary/extra",
        "cred:jiejian/test-identity/sample-project/tid_x",
        "cred:jiejian/test-identity/sample-project/../secret",
    ):
        with pytest.raises(ValueError):
            validate_credential_secret_ref(invalid)
