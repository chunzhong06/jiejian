# 验证会话引用只在内存中存活，普通凭据仍委托平台接口且清理不误删。
from unittest.mock import Mock

import pytest

from product.backend.infra.runtime.session_secrets import SessionSecretOverlay


def test_session_values_never_reach_platform_and_tombstones_prevent_delete():
    persistent = Mock()
    overlay = SessionSecretOverlay(persistent)
    reference = "cred:jiejian/test-identity/project/tid/cookie-00"
    overlay.set_session("sample-a", reference, "temporary-value")
    assert overlay.read(reference) == "temporary-value"
    assert overlay.configured(reference)
    with pytest.raises(ValueError, match="owner mismatch"):
        overlay.set_session("sample-b", reference, "other-value")
    overlay.write(reference, "refreshed")
    overlay.clear_session("sample-b")
    assert overlay.read(reference) == "refreshed"
    overlay.clear_session("sample-a")
    assert not overlay.configured(reference)
    assert overlay.read(reference) is None
    overlay.delete(reference)
    overlay.clear()
    assert persistent.mock_calls == []
    assert "refreshed" not in repr(overlay)


def test_non_session_references_use_original_store():
    persistent = Mock()
    overlay = SessionSecretOverlay(persistent)
    reference = "cred:jiejian/mcp/local/token"
    overlay.write(reference, "ordinary")
    overlay.read(reference)
    overlay.configured(reference)
    overlay.delete(reference)
    assert [call[0] for call in persistent.mock_calls] == ["write", "read", "configured", "delete"]
    with pytest.raises(ValueError):
        overlay.set_session("sample", reference, "forbidden")
