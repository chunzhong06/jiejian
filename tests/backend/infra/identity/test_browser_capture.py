# 验证身份准备只提取当前目标 Cookie，并在写入前留下精确引用计划。

from __future__ import annotations

from product.backend.infra.identity.browser import IdentityPreparationBrowserAdapter
from product.protocols import IdentityPreparationRequest, IdentityPreparationResultType
from product.protocols.web.target import WebTargetScope


class FakeContext:
    def __init__(self, cookies: list[dict[str, object]] | None = None) -> None:
        self._cookies = cookies or [
            {
                "name": "session",
                "value": "session-secret-value",
                "domain": "127.0.0.1",
                "path": "/",
                "secure": False,
                "httpOnly": True,
                "sameSite": "Lax",
                "expires": -1,
            },
            {
                "name": "other",
                "value": "must-not-be-saved",
                "domain": "example.test",
                "path": "/",
                "secure": True,
                "httpOnly": True,
                "sameSite": "Strict",
                "expires": -1,
            },
        ]

    def cookies(self) -> list[dict[str, object]]:
        return list(self._cookies)


class FakeSecretStore:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    def write(self, secret_ref: str, secret: str) -> None:
        self.values[secret_ref] = secret

    def read(self, secret_ref: str) -> str | None:
        return self.values.get(secret_ref)

    def delete(self, secret_ref: str) -> None:
        self.values.pop(secret_ref, None)

    def configured(self, secret_ref: str | None) -> bool:
        return secret_ref in self.values


class FailingSecretStore(FakeSecretStore):
    def write(self, secret_ref: str, secret: str) -> None:
        raise OSError(1312, "credential store unavailable")


class PartiallyFailingSecretStore(FakeSecretStore):
    def write(self, secret_ref: str, secret: str) -> None:
        if self.values:
            raise OSError(5, "second credential write failed")
        super().write(secret_ref, secret)


def test_capture_keeps_only_current_target_cookie_and_writes_plan_first() -> None:
    request = IdentityPreparationRequest(
        schema_version="1",
        preparation_id="prep_0123456789abcdef0123456789abcdef",
        project_id="sample-project",
        identity_id="tid_0123456789abcdef0123456789abcdef",
        target_scope=WebTargetScope(
            base_url="http://127.0.0.1:8865",
            allowed_origins=("http://127.0.0.1:8865",),
            allowed_hosts=("127.0.0.1",),
            allowed_ports=(8865,),
            allow_private_network=True,
        ),
    )
    store = FakeSecretStore()
    planned: list[tuple[str, ...]] = []

    result = IdentityPreparationBrowserAdapter()._capture_login_state(
        request,
        FakeContext(),  # type: ignore[arg-type]
        set(),
        store,
        prepared_at_us=12,
        before_secret_write=planned.append,
    )

    assert result.result_type is IdentityPreparationResultType.PREPARED
    assert len(result.cookies) == 1
    assert tuple(store.values.values()) == ("session-secret-value",)
    assert "must-not-be-saved" not in store.values.values()
    assert planned == [tuple(store.values)]


def test_capture_reports_secret_store_failure_without_leaving_secret() -> None:
    request = IdentityPreparationRequest(
        schema_version="1",
        preparation_id="prep_0123456789abcdef0123456789abcdef",
        project_id="sample-project",
        identity_id="tid_0123456789abcdef0123456789abcdef",
        target_scope=WebTargetScope(
            base_url="http://127.0.0.1:8865",
            allowed_origins=("http://127.0.0.1:8865",),
            allowed_hosts=("127.0.0.1",),
            allowed_ports=(8865,),
            allow_private_network=True,
        ),
    )
    store = FailingSecretStore()
    errors: list[BaseException] = []

    result = IdentityPreparationBrowserAdapter()._capture_login_state(
        request,
        FakeContext(),  # type: ignore[arg-type]
        set(),
        store,
        prepared_at_us=12,
        before_secret_write=lambda _refs: None,
        error_observer=errors.append,
    )

    assert result.result_type is IdentityPreparationResultType.FAILED
    assert len(errors) == 1
    assert isinstance(errors[0], OSError)
    assert store.values == {}


def test_capture_validates_all_cookies_before_writing_any_secret() -> None:
    request = IdentityPreparationRequest(
        schema_version="1",
        preparation_id="prep_0123456789abcdef0123456789abcdef",
        project_id="sample-project",
        identity_id="tid_0123456789abcdef0123456789abcdef",
        target_scope=WebTargetScope(
            base_url="http://127.0.0.1:8865",
            allowed_origins=("http://127.0.0.1:8865",),
            allowed_hosts=("127.0.0.1",),
            allowed_ports=(8865,),
            allow_private_network=True,
        ),
    )
    context = FakeContext(
        [
            {
                "name": "first",
                "value": "first-secret",
                "domain": "127.0.0.1",
                "path": "/",
                "sameSite": "Lax",
            },
            {
                "name": "empty",
                "value": "",
                "domain": "127.0.0.1",
                "path": "/",
                "sameSite": "Lax",
            },
        ]
    )
    store = FakeSecretStore()
    plans: list[tuple[str, ...]] = []

    result = IdentityPreparationBrowserAdapter()._capture_login_state(
        request,
        context,  # type: ignore[arg-type]
        set(),
        store,
        prepared_at_us=12,
        before_secret_write=plans.append,
    )

    assert result.result_type is IdentityPreparationResultType.UNSUPPORTED
    assert plans == []
    assert store.values == {}


def test_capture_compensates_partial_write_and_rejects_mixed_auth_state() -> None:
    request = IdentityPreparationRequest(
        schema_version="1",
        preparation_id="prep_0123456789abcdef0123456789abcdef",
        project_id="sample-project",
        identity_id="tid_0123456789abcdef0123456789abcdef",
        target_scope=WebTargetScope(
            base_url="http://127.0.0.1:8865",
            allowed_origins=("http://127.0.0.1:8865",),
            allowed_hosts=("127.0.0.1",),
            allowed_ports=(8865,),
            allow_private_network=True,
        ),
    )
    cookies = [
        {
            "name": name,
            "value": f"{name}-secret",
            "domain": "127.0.0.1",
            "path": "/",
            "sameSite": "Lax",
        }
        for name in ("first", "second")
    ]
    store = PartiallyFailingSecretStore()
    errors: list[BaseException] = []

    failed = IdentityPreparationBrowserAdapter()._capture_login_state(
        request,
        FakeContext(cookies),  # type: ignore[arg-type]
        set(),
        store,
        prepared_at_us=12,
        before_secret_write=lambda _refs: None,
        error_observer=errors.append,
    )
    mixed = IdentityPreparationBrowserAdapter()._capture_login_state(
        request,
        FakeContext(cookies[:1]),  # type: ignore[arg-type]
        {"bearer-secret"},
        FakeSecretStore(),
        prepared_at_us=12,
        before_secret_write=lambda _refs: None,
    )

    assert failed.result_type is IdentityPreparationResultType.FAILED
    assert len(errors) == 1
    assert store.values == {}
    assert mixed.result_type is IdentityPreparationResultType.UNSUPPORTED


def test_bearer_capture_accepts_case_insensitive_scheme_only_on_target_origin() -> None:
    tokens: set[str] = set()

    IdentityPreparationBrowserAdapter._capture_bearer(
        "http://127.0.0.1:8865/api/me",
        {"authorization": "bearer token-value"},
        "http://127.0.0.1:8865",
        tokens,
    )
    IdentityPreparationBrowserAdapter._capture_bearer(
        "http://127.0.0.1:8877/api/me",
        {"authorization": "Bearer other-token"},
        "http://127.0.0.1:8865",
        tokens,
    )

    assert tokens == {"token-value"}
