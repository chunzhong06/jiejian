# 验证 Actor 账号持久化、登录尝试来源复核和秘密清理的事务边界。

from __future__ import annotations

from tests.support.builders.identities import ACTOR_ID, PROJECT_ID, FakeSecretStore, application_understanding, boundary_reader, build_identity_service
import io
import json
import subprocess
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from product.backend.domain.errors import ErrorCode, JiejianError
from product.backend.domain.boundaries.entities import BusinessRevisionState
from product.backend.domain.identities.models import TestIdentityAuthMethod as IdentityAuthMethod, TestIdentityCookie as IdentityCookie
from product.backend.infrastructure.secrets.refs import credential_ref
from product.backend.infrastructure.runtime.paths import RuntimePaths
from product.backend.infrastructure.storage.unit_of_work import StorageUnitOfWork
from product.backend.application.test_identities.service import PreparedLoginState, TestIdentityService as IdentityService, TestIdentityStatus as IdentityStatus
from product.backend.application.test_identities.login_execution import IdentityLoginSupervisor
from product.backend.application.test_identities.models import IdentityPreparationStatus
import product.backend.application.test_identities.login_execution as preparation_module
from product.protocols.preparation.test_identity_preparation import IdentityPreparationResult, IdentityPreparationResultType, PreparedCookieRef, canonical_identity_preparation_json_bytes, parse_identity_preparation_request






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
            raise subprocess.TimeoutExpired("fake-preparation", timeout)
        return self.returncode






def _prepare(
    service: IdentityService,
    store: FakeSecretStore,
) -> tuple[str, str]:
    created = service.create(PROJECT_ID, actor_id=ACTOR_ID, actor_revision=1, label="所有者账号")
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
    service, store, _ = build_identity_service(tmp_path)
    identity_id, secret_ref = _prepare(service, store)

    view_payload = service.get(identity_id).model_dump_json()
    database_bytes = (tmp_path / "var" / "data" / "jiejian.db").read_bytes()
    assert "session-secret-value" not in view_payload
    assert secret_ref not in view_payload
    assert b"session-secret-value" not in database_bytes
    assert secret_ref.encode("utf-8") in database_bytes


def test_endpoint_change_preserves_actor_bound_identity(tmp_path: Path) -> None:
    service, store, factory = build_identity_service(tmp_path)
    identity_id, _ = _prepare(service, store)
    with StorageUnitOfWork(factory) as work:
        work.application_understanding.replace(
            application_understanding(endpoint="http://127.0.0.1:8877", revision=4)
        )
        work.commit()

    changed = service.get(identity_id)
    assert changed.status is IdentityStatus.PREPARED
    assert changed.review_reasons == ()
    assert (changed.actor_id, changed.actor_revision) == (ACTOR_ID, 1)

    reset = service.reset(identity_id)
    assert reset.status is IdentityStatus.NOT_PREPARED
    assert (reset.actor_id, reset.actor_revision) == (ACTOR_ID, 1)
    assert reset.review_reasons == ()


def test_candidate_role_name_change_does_not_rewrite_frozen_actor_identity(tmp_path: Path) -> None:
    service, store, factory = build_identity_service(tmp_path)
    identity_id, _ = _prepare(service, store)
    changed_understanding = application_understanding(revision=4)
    changed_role = changed_understanding.role_candidates[0].model_copy(
        update={"display_name": "项目所有者"}
    )
    with StorageUnitOfWork(factory) as work:
        work.application_understanding.replace(
            changed_understanding.model_copy(
                update={"role_candidates": (changed_role,)}
            )
        )
        work.commit()

    changed = service.get(identity_id)
    assert changed.status is IdentityStatus.PREPARED
    assert changed.review_reasons == ()
    assert (changed.actor_id, changed.actor_revision, changed.actor_display_name) == (ACTOR_ID, 1, "所有者")


def test_delete_failure_keeps_metadata_then_success_removes_exact_secret(
    tmp_path: Path,
) -> None:
    service, store, _ = build_identity_service(tmp_path)
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


def test_repository_delete_rejection_keeps_metadata_and_never_deletes_secret(tmp_path, monkeypatch):
    service, store, factory = build_identity_service(tmp_path)
    identity_id, secret_ref = _prepare(service, store)
    with StorageUnitOfWork(factory) as work:
        repository_type = type(work.test_identities)
    delete_secret = Mock(wraps=store.delete)
    monkeypatch.setattr(store, "delete", delete_secret)

    def reject(_repository, _identity_id):
        raise JiejianError(ErrorCode.STORAGE_CONSTRAINT, "注入 repository 删除拒绝")

    # 注入点是 repository 边界；真实 FK 结构由 migration 用例单独证明。
    monkeypatch.setattr(repository_type, "delete", reject)
    with pytest.raises(JiejianError) as error:
        service.delete(identity_id)
    assert error.value.code == ErrorCode.STORAGE_CONSTRAINT.value
    delete_secret.assert_not_called()
    assert service.get(identity_id).status is IdentityStatus.PREPARED
    assert store.read(secret_ref) == "session-secret-value"


def test_preparation_manager_commits_only_non_secret_child_result(tmp_path: Path) -> None:
    service, store, factory = build_identity_service(tmp_path)
    created = service.create(PROJECT_ID, actor_id=ACTOR_ID, actor_revision=1, label="所有者账号")
    fake_process = FakePreparationProcess()

    def launch(*_args, **_kwargs):
        return fake_process

    manager = IdentityLoginSupervisor(
        tmp_path / "var",
        service,
        store,
        {"JIEJIAN_PROJECT_ROOT": str(tmp_path)},
        process_launcher=launch,
        application_understanding=SimpleNamespace(get=lambda _project_id: application_understanding()),
        business_boundaries=boundary_reader(factory),
    )
    started = manager.start(created.identity_id, operation_id='a' * 32)
    assert manager.start(created.identity_id, operation_id='a' * 32).preparation_id == started.preparation_id
    assert manager.latest(created.identity_id).preparation_id == started.preparation_id
    active_paths = manager.active_runtime_paths()
    assert active_paths == (
        RuntimePaths(tmp_path / "var").identity_preparations / started.preparation_id,
    )
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
    assert manager.active_runtime_paths() == ()


def test_preparation_manager_retries_orphaned_secret_cleanup_on_next_start(
    tmp_path: Path,
) -> None:
    service, store, factory = build_identity_service(tmp_path)
    created = service.create(PROJECT_ID, actor_id=ACTOR_ID, actor_revision=1, label="所有者账号")
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

    IdentityLoginSupervisor(
        tmp_path / "var",
        service,
        store,
        {"JIEJIAN_PROJECT_ROOT": str(tmp_path)},
        application_understanding=SimpleNamespace(get=lambda _project_id: application_understanding()),
        business_boundaries=boundary_reader(factory),
    )
    assert attempt_dir.is_dir()
    assert store.read(secret_ref) == "orphaned-session-secret"

    store.fail_delete = False
    IdentityLoginSupervisor(
        tmp_path / "var",
        service,
        store,
        {"JIEJIAN_PROJECT_ROOT": str(tmp_path)},
        application_understanding=SimpleNamespace(get=lambda _project_id: application_understanding()),
        business_boundaries=boundary_reader(factory),
    )
    assert not attempt_dir.exists()
    assert store.read(secret_ref) is None


@pytest.mark.parametrize("change", ["endpoint", "reset", "delete", "actor_revision"])
def test_preparation_result_rejects_changed_login_source(tmp_path: Path, change: str) -> None:
    service, store, factory = build_identity_service(tmp_path)
    created = service.create(PROJECT_ID, actor_id=ACTOR_ID, actor_revision=1, label="所有者账号")
    process = FakePreparationProcess()

    def understanding(_project_id):
        with StorageUnitOfWork(factory) as work:
            return work.application_understanding.get(PROJECT_ID)

    manager = IdentityLoginSupervisor(
        tmp_path / "var", service, store, {"JIEJIAN_PROJECT_ROOT": str(tmp_path)},
        process_launcher=lambda *_args, **_kwargs: process,
        application_understanding=SimpleNamespace(get=understanding),
        business_boundaries=boundary_reader(factory),
    )
    started = manager.start(created.identity_id)
    if change == "endpoint":
        with StorageUnitOfWork(factory) as work:
            work.application_understanding.replace(application_understanding(endpoint="http://127.0.0.1:8877", revision=4))
            work.commit()
    elif change == "reset":
        service._clock_us = lambda: 20
        service.reset(created.identity_id)
    elif change == "delete":
        service.delete(created.identity_id)
    else:
        # 业务主体推进当前 revision，账号仍合法引用历史 revision；不能伪造账号字段变化。
        with StorageUnitOfWork(factory) as work:
            previous = work.business_boundaries.actor_revision(ACTOR_ID, 1)
            root = work.business_boundaries.actor(ACTOR_ID)
            work.business_boundaries.add_actor_revision(previous.model_copy(update={"revision": 2}))
            work.business_boundaries.replace_actor(root.model_copy(update={"current_revision": 2}))
            work.commit()
        assert service.get(created.identity_id).actor_revision == 1

    secret_ref = credential_ref("test-identity", PROJECT_ID, created.identity_id, "bearer")
    store.write(secret_ref, "temporary-test-secret")
    unrelated_ref = credential_ref("test-identity", PROJECT_ID, "tid_" + "f" * 32, "bearer")
    store.write(unrelated_ref, "unrelated-test-secret")
    result = IdentityPreparationResult(
        schema_version="1", preparation_id=started.preparation_id, project_id=PROJECT_ID,
        identity_id=created.identity_id, result_type=IdentityPreparationResultType.PREPARED,
        auth_method=IdentityAuthMethod.BEARER, bearer_secret_ref=secret_ref, prepared_at_us=30,
    )
    process.stdout = io.BytesIO(canonical_identity_preparation_json_bytes(result))
    process.returncode = 0
    finished = manager.status(started.preparation_id)
    assert finished.status is IdentityPreparationStatus.FAILED
    assert store.read(secret_ref) is None
    assert store.read(unrelated_ref) == "unrelated-test-secret"
    if change != "delete":
        assert service.get(created.identity_id).status is IdentityStatus.NOT_PREPARED


@pytest.mark.parametrize("reason", ["new_revision", "retired", "unconfirmed_endpoint"])
def test_preparation_start_rejects_unusable_source_before_launch(tmp_path, reason):
    service, store, factory = build_identity_service(tmp_path)
    created = service.create(PROJECT_ID, actor_id=ACTOR_ID, actor_revision=1, label="所有者账号")
    current = boundary_reader(factory).view(PROJECT_ID).actors[0]
    if reason == "new_revision":
        current = current.model_copy(update={"revision": 2})
    elif reason == "retired":
        current = current.model_copy(update={"effective_state": BusinessRevisionState.RETIRED})
    understanding = application_understanding()
    if reason == "unconfirmed_endpoint":
        understanding = understanding.model_copy(update={"endpoint_reachable": False})
    launch = Mock()
    manager = IdentityLoginSupervisor(
        tmp_path / "var", service, store, {"JIEJIAN_PROJECT_ROOT": str(tmp_path)},
        process_launcher=launch, application_understanding=SimpleNamespace(get=lambda _: understanding),
        business_boundaries=SimpleNamespace(view=lambda _: SimpleNamespace(actors=(current,))),
    )
    with pytest.raises(JiejianError):
        manager.start(created.identity_id)
    launch.assert_not_called()
    assert tuple(manager._paths.identity_preparations.iterdir()) == ()


def _manager_attempt(tmp_path):
    service, store, factory = build_identity_service(tmp_path)
    created = service.create(PROJECT_ID, actor_id=ACTOR_ID, actor_revision=1, label="所有者账号")
    process = FakePreparationProcess()
    manager = IdentityLoginSupervisor(
        tmp_path / "var", service, store, {"JIEJIAN_PROJECT_ROOT": str(tmp_path)},
        process_launcher=lambda *_args, **_kwargs: process,
        application_understanding=SimpleNamespace(get=lambda _: application_understanding()),
        business_boundaries=boundary_reader(factory),
    )
    return manager, process, service, store, created


def _child_result(manager, process, store, started):
    ref = credential_ref("test-identity", PROJECT_ID, started.identity_id, "bearer")
    store.write(ref, "temporary-test-secret")
    result = IdentityPreparationResult(
        schema_version="1", preparation_id=started.preparation_id, project_id=PROJECT_ID,
        identity_id=started.identity_id, result_type=IdentityPreparationResultType.PREPARED,
        auth_method=IdentityAuthMethod.BEARER, bearer_secret_ref=ref, prepared_at_us=30,
    )
    process.stdout = io.BytesIO(canonical_identity_preparation_json_bytes(result))
    process.returncode = 0
    root = manager._active[started.preparation_id].controls.root
    (root / "secret-refs.json").write_text(json.dumps({
        "schema_version": "1", "identity_id": started.identity_id, "secret_refs": [ref],
    }), encoding="utf-8")
    return result, ref, root


def test_manager_release_precedes_pipe_read_and_preserves_retry(tmp_path, monkeypatch):
    manager, process, service, store, created = _manager_attempt(tmp_path)
    started = manager.start(created.identity_id)
    _, ref, root = _child_result(manager, process, store, started)
    release = Mock(side_effect=[JiejianError(ErrorCode.PROCESS_TREE_FAILED, "注入释放失败"), None])
    monkeypatch.setattr(preparation_module, "release_process_tree", release)
    with pytest.raises(JiejianError):
        manager.status(started.preparation_id)
    assert manager.active_runtime_paths() == (root,)
    assert service.get(created.identity_id).status is IdentityStatus.NOT_PREPARED
    assert manager._active[started.preparation_id].result_read is False
    assert process.stdout.tell() == 0
    assert manager.status(started.preparation_id).status is IdentityPreparationStatus.PREPARED
    assert service.get(created.identity_id).status is IdentityStatus.PREPARED
    assert store.read(ref) == "temporary-test-secret"
    assert manager.active_runtime_paths() == ()
    assert not root.exists()
    assert release.call_count == 2


@pytest.mark.parametrize("cleanup_fails", [False, True])
def test_manager_stdin_failure_keeps_supervision_until_cleanup(tmp_path, monkeypatch, cleanup_fails):
    manager, process, service, store, created = _manager_attempt(tmp_path)
    process.stdin.write = Mock(side_effect=OSError("injected stdin failure"))

    def terminate(*_):
        if cleanup_fails:
            raise JiejianError(ErrorCode.PROCESS_TREE_FAILED, "注入终止失败")
        process.returncode = 0

    monkeypatch.setattr(preparation_module, "terminate_process_tree", terminate)
    with pytest.raises(JiejianError) as error:
        manager.start(created.identity_id)
    assert error.value.code == ErrorCode.IDENTITY_PREPARATION_FAILED.value
    assert "injected" not in str(error.value)
    if cleanup_fails:
        active = next(iter(manager._active.values()))
        assert active.process is process and active.startup_failed
        started = SimpleNamespace(preparation_id=active.request.preparation_id, identity_id=created.identity_id)
        _, ref, root = _child_result(manager, process, store, started)
        assert manager.active_runtime_paths() == (root,)
        # 即使子进程后来输出合法结果，启动握手失败的尝试也不能提交身份。
        manager.close()
        assert store.read(ref) is None
    assert manager.active_runtime_paths() == ()
    assert service.get(created.identity_id).status is IdentityStatus.NOT_PREPARED


@pytest.mark.parametrize("invalid", ["malformed", "missing_stdout", "wrong_preparation", "wrong_identity"])
def test_manager_invalid_result_uses_exact_journal_compensation(tmp_path, invalid):
    manager, process, service, store, created = _manager_attempt(tmp_path)
    started = manager.start(created.identity_id)
    result, ref, root = _child_result(manager, process, store, started)
    unrelated = credential_ref("test-identity", PROJECT_ID, "tid_" + "f" * 32, "bearer")
    store.write(unrelated, "unrelated-test-secret")
    if invalid == "malformed":
        process.stdout = io.BytesIO(b"not-json")
    elif invalid == "missing_stdout":
        process.stdout = None
    else:
        update = {"preparation_id": "prep_" + "f" * 32} if invalid == "wrong_preparation" else {
            "identity_id": "tid_" + "f" * 32, "bearer_secret_ref": unrelated}
        process.stdout = io.BytesIO(canonical_identity_preparation_json_bytes(result.model_copy(update=update)))
    assert manager.status(started.preparation_id).status is IdentityPreparationStatus.FAILED
    assert service.get(created.identity_id).status is IdentityStatus.NOT_PREPARED
    assert store.read(ref) is None
    assert store.read(unrelated) == "unrelated-test-secret"


@pytest.mark.parametrize("journal_case", ["committed", "unrelated", "delete_failure", "wrong_identity", "bad_fields"])
def test_manager_journal_protects_committed_and_unrelated_refs(tmp_path, journal_case):
    manager, process, service, store, created = _manager_attempt(tmp_path)
    started = manager.start(created.identity_id)
    _, ref, root = _child_result(manager, process, store, started)
    unrelated = credential_ref("test-identity", PROJECT_ID, "tid_" + "f" * 32, "bearer")
    store.write(unrelated, "unrelated-test-secret")
    payload = {"schema_version": "1", "identity_id": created.identity_id, "secret_refs": [ref]}
    if journal_case == "committed":
        service.save_prepared_state(created.identity_id, PreparedLoginState(
            auth_method=IdentityAuthMethod.BEARER, bearer_secret_ref=ref, prepared_at_us=30))
    elif journal_case == "unrelated":
        payload["secret_refs"].append(unrelated)
    elif journal_case == "delete_failure":
        store.fail_delete = True
    elif journal_case == "wrong_identity":
        payload["identity_id"] = "tid_" + "f" * 32
    else:
        payload["unexpected"] = "rejected"
    (root / "secret-refs.json").write_text(json.dumps(payload), encoding="utf-8")
    process.stdout = io.BytesIO(b"malformed")
    assert manager.status(started.preparation_id).status is IdentityPreparationStatus.FAILED
    assert store.read(unrelated) == "unrelated-test-secret"
    if journal_case == "unrelated":
        assert store.read(ref) is None
    else:
        assert store.read(ref) == "temporary-test-secret"
    assert root.exists()
    if journal_case == "delete_failure":
        store.fail_delete = False
        manager._reconcile_orphaned_attempts()
        assert store.read(ref) is None and not root.exists()

pytestmark = [pytest.mark.level3]
