# Windows L5：真实 headed browser、Sample 登录与 Credential Manager 恢复/清理闭环。

from __future__ import annotations

import os
from pathlib import Path
from uuid import uuid4

import pytest

from product.backend.core.application_understanding import (
    ApplicationUnderstanding,
    CandidateConfidence,
    CandidateDecision,
    CandidateOrigin,
    RoleCandidate,
    candidate_id,
)
from product.backend.core.lifecycle import ProjectStatus
from product.backend.infra.identity.browser import IdentityPreparationBrowserAdapter
from product.backend.infra.secrets import WindowsCredentialManagerSecretStore
from product.backend.infra.storage import ProjectRecord
from product.backend.composition import ApplicationCore
from product.backend.workflows.test_identities import PreparedLoginState, TestIdentityStatus as IdentityStatus
from product.backend.core.test_identity import TestIdentityCookie as IdentityCookie
from product.protocols import IdentityPreparationRequest, IdentityPreparationResultType
from product.protocols.web.target import WebTargetScope


pytestmark = [
    pytest.mark.browser,
    pytest.mark.process,
    pytest.mark.slow,
    pytest.mark.skipif(
        os.name != "nt" or os.environ.get("JIEJIAN_RUN_WINDOWS_L5") != "1",
        reason="requires explicit Windows L5 authorization",
    ),
]


def test_web_test_login_persists_only_credential_refs_and_deletes_exact_entry(
    tmp_path: Path,
    web_test_target_factory,
    request: pytest.FixtureRequest,
) -> None:
    sample = web_test_target_factory()
    endpoint = f"http://127.0.0.1:{sample.port}"
    project_id = "web-test-project"
    role_id = candidate_id("role", "member")
    var_dir = tmp_path / "var"
    store = WindowsCredentialManagerSecretStore()
    cleanup_refs: set[str] = set()

    def cleanup_credentials() -> None:
        for secret_ref in tuple(cleanup_refs):
            try:
                store.delete(secret_ref)
            except OSError:
                pass

    request.addfinalizer(cleanup_credentials)
    application = ApplicationCore(var_dir, secret_store=store, environ={})
    identity_id = ""
    captured_refs: tuple[str, ...] = ()
    try:
        with application.uow_factory() as work:
            work.projects.add(
                ProjectRecord(
                    project_id=project_id,
                    name="Web 测试项目",
                    status=ProjectStatus.DRAFT,
                    created_at_us=1,
                    updated_at_us=1,
                )
            )
            work.application_understanding.add(
                ApplicationUnderstanding(
                    project_id=project_id,
                    source_root="D:/web-test",
                    confirmed_endpoint=endpoint,
                    endpoint_source_fingerprint="a" * 64,
                    endpoint_confirmed_at_us=2,
                    endpoint_last_checked_at_us=2,
                    endpoint_reachable=True,
                    role_candidates=(
                        RoleCandidate(
                            candidate_id=role_id,
                            canonical_key="member",
                            display_name="成员",
                            confidence=CandidateConfidence.HIGH,
                            decision=CandidateDecision.CONFIRMED,
                            origin=CandidateOrigin.MANUAL,
                        ),
                    ),
                    revision=3,
                    created_at_us=1,
                    updated_at_us=2,
                )
            )
            work.commit()
        created = application.test_identities.create(
            project_id,
            role_candidate_id=role_id,
            label="成员测试账号",
        )
        identity_id = created.identity_id
        request = IdentityPreparationRequest(
            schema_version="1",
            preparation_id=f"prep_{uuid4().hex}",
            project_id=project_id,
            identity_id=identity_id,
            target_scope=WebTargetScope(
                base_url=endpoint,
                allowed_origins=(endpoint,),
                allowed_hosts=("127.0.0.1",),
                allowed_ports=(sample.port,),
                allow_private_network=True,
                timeout_seconds=10.0,
                max_requests=64,
                max_response_bytes=262_144,
            ),
        )

        def login(page) -> None:
            page.select_option('select[name="role"]', "member")
            page.fill('input[name="password"]', sample.passwords["member"])
            page.click('button[type="submit"]')
            page.wait_for_load_state("domcontentloaded")
            page.goto(f"{endpoint}/resources/document")
            page.wait_for_load_state("domcontentloaded")

        plans: list[tuple[str, ...]] = []
        errors: list[BaseException] = []

        def remember_plan(refs: tuple[str, ...]) -> None:
            plans.append(refs)
            cleanup_refs.update(refs)

        result = IdentityPreparationBrowserAdapter().run(
            request,
            secret_store=store,
            ready_callback=lambda: None,
            save_requested=lambda: True,
            cancellation_requested=lambda: False,
            before_secret_write=remember_plan,
            interaction=login,
            error_observer=errors.append,
        )
        assert result.result_type is IdentityPreparationResultType.PREPARED, [
            f"{type(error).__name__}: {error}" for error in errors
        ]
        captured_refs = tuple(cookie.value_secret_ref for cookie in result.cookies)
        assert captured_refs == plans[0]
        assert tuple(store.read(ref) for ref in captured_refs) == (
            sample.tokens["member"],
        )
        application.test_identities.save_prepared_state(
            identity_id,
            PreparedLoginState(
                auth_method=result.auth_method,
                cookies=tuple(
                    IdentityCookie(**cookie.model_dump())
                    for cookie in result.cookies
                ),
                prepared_at_us=result.prepared_at_us,
            ),
        )
        assert application.test_identities.get(identity_id).status is IdentityStatus.PREPARED
    finally:
        application.close()

    secret_bytes = sample.tokens["member"].encode("utf-8")
    for path in var_dir.rglob("*"):
        if path.is_file():
            try:
                assert secret_bytes not in path.read_bytes()
            except OSError:
                continue
    fixture_source = Path(__file__).resolve().parents[4] / "tests" / "fixtures" / "web_test_target.py"
    assert secret_bytes not in fixture_source.read_bytes()

    restarted = ApplicationCore(var_dir, secret_store=store, environ={})
    try:
        restored = restarted.test_identities.get(identity_id)
        assert restored.status is IdentityStatus.PREPARED
        assert "secret_ref" not in restored.model_dump_json()
        restarted.test_identities.delete(identity_id)
        assert all(store.read(ref) is None for ref in captured_refs)
    finally:
        restarted.close()
