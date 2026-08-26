# 验证测试账号持久化、角色/端点失效和秘密清理的事务边界。

from __future__ import annotations

import io
import json
from functools import partial
from pathlib import Path

import pytest

from product.backend.core.application_understanding import (
    ApplicationUnderstanding,
    CandidateConfidence,
    CandidateDecision,
    CandidateOrigin,
    RoleCandidate,
    candidate_id,
)
from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.core.lifecycle import ProjectStatus
from product.backend.core.test_identity import (
    TestIdentityAuthMethod as IdentityAuthMethod,
    TestIdentityCookie as IdentityCookie,
)
from product.backend.infra.secrets import credential_ref
from product.backend.infra.storage import (
    ProjectRecord,
    StorageUnitOfWork,
    create_session_factory,
    create_sqlite_engine,
    upgrade_database,
)
from product.backend.workflows.test_identities import (
    IdentityPreparationManager,
    IdentityPreparationStatus,
    PreparedLoginState,
    TestIdentityService as IdentityService,
    TestIdentityStatus as IdentityStatus,
)
from product.protocols import (
    IdentityPreparationResult,
    IdentityPreparationResultType,
    PreparedCookieRef,
    canonical_identity_preparation_json_bytes,
    parse_identity_preparation_request,
)


PROJECT_ID = "sample-project"
ROLE_ID = candidate_id("role", "owner")
ENDPOINT = "http://127.0.0.1:8865"
FINGERPRINT = "a" * 64


class FakeSecretStore:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.fail_delete = False

    def write(self, secret_ref: str, secret: str) -> None:
        self.values[secret_ref] = secret

    def read(self, secret_ref: str) -> str | None:
        return self.values.get(secret_ref)

    def delete(self, secret_ref: str) -> None:
        if self.fail_delete:
            raise OSError("blocked")
        self.values.pop(secret_ref, None)

    def configured(self, secret_ref: str | None) -> bool:
        return secret_ref is not None and secret_ref in self.values


class RetainedBytesIO(io.BytesIO):
    def close(self) -> None:
        return


class FakePreparationProcess:
    def __init__(self) -> None:
        self.stdin = RetainedBytesIO()
        self.stdout = io.BytesIO()
        self.returncode: int | None = None

    def poll(self) -> int | None:
        return self.returncode

    def wait(self, timeout: float | None = None) -> int:
        if self.returncode is None:
            raise TimeoutError(timeout)
        return self.returncode


def _understanding(*, endpoint: str = ENDPOINT, revision: int = 3) -> ApplicationUnderstanding:
    return ApplicationUnderstanding(
        project_id=PROJECT_ID,
        source_root="D:/sample",
        confirmed_endpoint=endpoint,
        endpoint_source_fingerprint=FINGERPRINT,
        endpoint_confirmed_at_us=2,
        endpoint_last_checked_at_us=2,
        endpoint_reachable=True,
        role_candidates=(
            RoleCandidate(
                candidate_id=ROLE_ID,
                canonical_key="owner",
                display_name="所有者",
                confidence=CandidateConfidence.HIGH,
                decision=CandidateDecision.CONFIRMED,
                origin=CandidateOrigin.MANUAL,
            ),
        ),
        revision=revision,
        created_at_us=1,
        updated_at_us=2,
    )


def _service(tmp_path: Path) -> tuple[IdentityService, FakeSecretStore, object]:
    database = tmp_path / "var" / "data" / "jiejian.db"
    upgrade_database(database)
    factory = create_session_factory(create_sqlite_engine(database))
    with StorageUnitOfWork(factory) as work:
        work.projects.add(
            ProjectRecord(
                project_id=PROJECT_ID,
                name="样例应用",
                status=ProjectStatus.DRAFT,
                created_at_us=1,
                updated_at_us=1,
            )
        )
        work.application_understanding.add(_understanding())
        work.commit()
    store = FakeSecretStore()
    service = IdentityService(
        partial(StorageUnitOfWork, factory),
        secret_store=store,
        clock_us=lambda: 10,
    )
    return service, store, factory


def _prepare(
    service: IdentityService,
    store: FakeSecretStore,
) -> tuple[str, str]:
    created = service.create(PROJECT_ID, role_candidate_id=ROLE_ID, label="所有者账号")
    secret_ref = credential_ref(
        "test-identity", PROJECT_ID, created.identity_id, "cookie-00"
    )
    store.write(secret_ref, "session-secret-value")
    prepared = service.save_prepared_state(
        created.identity_id,
        PreparedLoginState(
            auth_method=IdentityAuthMethod.COOKIE_SESSION,
            cookies=(
                IdentityCookie(
                    name="session",
                    domain="127.0.0.1",
                    path="/",
                    secure=False,
                    http_only=True,
                    same_site="LAX",
                    value_secret_ref=secret_ref,
                ),
            ),
            prepared_at_us=11,
        ),
    )
    assert prepared.status is IdentityStatus.PREPARED
    return created.identity_id, secret_ref


def test_login_secret_never_enters_sqlite_or_public_view(tmp_path: Path) -> None:
    service, store, _ = _service(tmp_path)
    identity_id, secret_ref = _prepare(service, store)

    view_payload = service.get(identity_id).model_dump_json()
    database_bytes = (tmp_path / "var" / "data" / "jiejian.db").read_bytes()
    assert "session-secret-value" not in view_payload
    assert secret_ref not in view_payload
    assert b"session-secret-value" not in database_bytes
    assert secret_ref.encode("utf-8") in database_bytes


def test_endpoint_change_marks_prepared_identity_for_review(tmp_path: Path) -> None:
    service, store, factory = _service(tmp_path)
    identity_id, _ = _prepare(service, store)
    with StorageUnitOfWork(factory) as work:
        work.application_understanding.replace(
            _understanding(endpoint="http://127.0.0.1:8877", revision=4)
        )
        work.commit()

    changed = service.get(identity_id)
    assert changed.status is IdentityStatus.NEEDS_REVIEW
    assert changed.review_reasons == ("ENDPOINT_CHANGED",)

    reset = service.reset(identity_id)
    assert reset.status is IdentityStatus.NOT_PREPARED
    assert reset.confirmed_endpoint == "http://127.0.0.1:8877"
    assert reset.review_reasons == ()


def test_delete_failure_keeps_metadata_then_success_removes_exact_secret(
    tmp_path: Path,
) -> None:
    service, store, _ = _service(tmp_path)
    identity_id, secret_ref = _prepare(service, store)
    store.fail_delete = True

    with pytest.raises(JiejianError) as failed:
        service.delete(identity_id)
    assert failed.value.code == ErrorCode.TEST_IDENTITY_SECRET_CLEANUP.value
    assert service.get(identity_id).identity_id == identity_id
    assert store.read(secret_ref) == "session-secret-value"

    store.fail_delete = False
    service.delete(identity_id)
    assert store.read(secret_ref) is None
    with pytest.raises(JiejianError) as missing:
        service.get(identity_id)
    assert missing.value.code == ErrorCode.TEST_IDENTITY_NOT_FOUND.value


def test_preparation_manager_commits_only_non_secret_child_result(tmp_path: Path) -> None:
    service, store, _ = _service(tmp_path)
    created = service.create(PROJECT_ID, role_candidate_id=ROLE_ID, label="所有者账号")
    fake_process = FakePreparationProcess()

    def launch(*_args, **_kwargs):
        return fake_process

    manager = IdentityPreparationManager(
        tmp_path / "var",
        service,
        store,
        {"JIEJIAN_PROJECT_ROOT": str(tmp_path)},
        process_launcher=launch,
    )
    started = manager.start(created.identity_id)
    request = parse_identity_preparation_request(fake_process.stdin.getvalue())
    secret_ref = credential_ref(
        "test-identity", PROJECT_ID, created.identity_id, "cookie-00"
    )
    store.write(secret_ref, "session-secret-value")
    result = IdentityPreparationResult(
        schema_version="1",
        preparation_id=request.preparation_id,
        project_id=PROJECT_ID,
        identity_id=created.identity_id,
        result_type=IdentityPreparationResultType.PREPARED,
        auth_method=IdentityAuthMethod.COOKIE_SESSION,
        cookies=(
            PreparedCookieRef(
                name="session",
                domain="127.0.0.1",
                path="/",
                secure=False,
                http_only=True,
                same_site="LAX",
                value_secret_ref=secret_ref,
            ),
        ),
        prepared_at_us=12,
    )
    fake_process.stdout = io.BytesIO(
        canonical_identity_preparation_json_bytes(result)
    )
    fake_process.returncode = 0

    finished = manager.status(started.preparation_id)
    assert finished.status is IdentityPreparationStatus.PREPARED
    assert service.get(created.identity_id).status is IdentityStatus.PREPARED
    assert "session-secret-value" not in finished.model_dump_json()
    assert finished.log_path.endswith(f"{started.preparation_id}.log")


def test_preparation_manager_retries_orphaned_secret_cleanup_on_next_start(
    tmp_path: Path,
) -> None:
    service, store, _ = _service(tmp_path)
    created = service.create(PROJECT_ID, role_candidate_id=ROLE_ID, label="所有者账号")
    secret_ref = credential_ref(
        "test-identity",
        PROJECT_ID,
        created.identity_id,
        "cookie-00",
    )
    store.write(secret_ref, "orphaned-session-secret")
    attempt_dir = (
        tmp_path
        / "var"
        / "runtime"
        / "identity-preparations"
        / "prep_00000000000000000000000000000000"
    )
    attempt_dir.mkdir(parents=True)
    (attempt_dir / "secret-refs.json").write_text(
        json.dumps(
            {
                "schema_version": "1",
                "identity_id": created.identity_id,
                "secret_refs": [secret_ref],
            }
        ),
        encoding="utf-8",
    )
    store.fail_delete = True

    IdentityPreparationManager(
        tmp_path / "var",
        service,
        store,
        {"JIEJIAN_PROJECT_ROOT": str(tmp_path)},
    )
    assert attempt_dir.is_dir()
    assert store.read(secret_ref) == "orphaned-session-secret"

    store.fail_delete = False
    IdentityPreparationManager(
        tmp_path / "var",
        service,
        store,
        {"JIEJIAN_PROJECT_ROOT": str(tmp_path)},
    )
    assert not attempt_dir.exists()
    assert store.read(secret_ref) is None
