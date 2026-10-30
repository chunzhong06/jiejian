# 在 Worker 租约内监督登录进程，并在同一事务采用账号凭据引用和任务回执。
from __future__ import annotations

import json
import hashlib
import re
import shutil
import subprocess
import threading
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4
from product.backend.domain.errors import ErrorCode, JiejianError
from product.backend.domain.identities.models import TestIdentityCookie
from product.backend.infrastructure.identity.control import (
    IdentityPreparationControlPaths,
    identity_preparation_control_paths,
    valid_identity_preparation_marker,
    write_identity_preparation_marker,
)
from product.backend.infrastructure.runtime.paths import RuntimePaths
from product.backend.infrastructure.runtime.process.environment import (
    ProcessEnvironmentRole,
    spawn_python_module,
)
from product.backend.infrastructure.runtime.process.tree import (
    release_process_tree,
    terminate_process_tree,
)
from product.backend.infrastructure.secrets import SecretStore, validate_credential_secret_ref
from product.backend.application.test_identities.service import (
    PreparedLoginState,
    TestIdentityService,
    TestIdentityStatus,
)
from product.protocols.preparation.test_identity_preparation import (
    IDENTITY_PREPARATION_RESULT_MAX_BYTES,
    IdentityPreparationRequest,
    IdentityPreparationResult,
    IdentityPreparationResultType,
    canonical_identity_preparation_json_bytes,
    parse_identity_preparation_result,
)
from product.protocols.web.target import WebTargetScope
from product.backend.application.test_identities.models import (
    IdentityPreparationStatus,
    IdentityPreparationView,
)
import time
from types import SimpleNamespace
from product.backend.application.application_understanding.service import (
    ApplicationUnderstandingService,
)
from product.backend.application.business_boundaries.service import BusinessBoundaryService
from product.backend.application.test_identities.models import IdentityPreparationStatus
from product.backend.application.test_identities.service import (
    TestIdentityService,
    PreparedLoginState,
)
from product.backend.domain.lifecycle import JobState
from product.backend.infrastructure.runtime.jobs.events import append_job_event
from product.backend.infrastructure.runtime.jobs.models import (
    ClaimJob,
    CompleteCancellation,
    FatalFailure,
    FatalFailureCode,
    JobEventType,
)
from product.backend.infrastructure.runtime.process.control import (
    AttemptProcessControl,
    DEFAULT_LEASE_DURATION_US,
)
from product.backend.infrastructure.secrets import default_secret_store
from product.backend.infrastructure.identity.control import (
    valid_identity_preparation_marker,
    write_identity_preparation_marker,
)
from product.backend.application.test_identities.source import preparation_source


@dataclass(slots=True)
class _ActivePreparation:
    request: IdentityPreparationRequest
    process: subprocess.Popen[bytes]
    controls: IdentityPreparationControlPaths
    log_path: Path
    source_fingerprint: str
    startup_failed: bool = False
    result_read: bool = False
    result: IdentityPreparationResult | None = None
    official_account: str | None = None


class IdentityLoginSupervisor:
    """为每个测试账号最多监督一个当前准备进程。"""

    # 这里只保存本进程的句柄与解析结果；跨进程的任务唯一性和完成事实由持久 Job 负责。
    # commit_prepared 由 Worker 注入，使结果采用与租约核验共享事务，而非直接保存账号。

    def __init__(
        self,
        var_dir: Path,
        identities: TestIdentityService,
        secret_store: SecretStore,
        environment: dict[str, str],
        process_launcher: Callable[..., subprocess.Popen[bytes]] = spawn_python_module,
        *,
        application_understanding,
        business_boundaries,
        commit_prepared=None,
        reconcile=True,
    ) -> None:
        self._commit_prepared = commit_prepared
        self._paths = RuntimePaths(var_dir).ensure_layout()
        self._identities = identities
        self._application_understanding = application_understanding
        self._business_boundaries = business_boundaries
        self._secret_store = secret_store
        self._environment = dict(environment)
        self._process_launcher = process_launcher
        self._active: dict[str, _ActivePreparation] = {}
        self._terminal: dict[str, IdentityPreparationView] = {}
        self._lock = threading.RLock()
        if reconcile:
            # 仅在调用方已排除其他活跃准备进程时做启动回收；共享 Worker 路径显式关闭它。
            self._reconcile_orphaned_attempts()

    def active_runtime_paths(self) -> tuple[Path, ...]:
        """返回当前受监督准备会话目录，供本地维护保护真实活跃路径。"""

        with self._lock:
            return tuple(active.controls.root for active in self._active.values())

    def start(
        self, identity_id: str, *, operation_id: str | None = None
    ) -> IdentityPreparationView:
        if operation_id is not None and re.fullmatch(r"[0-9a-f]{32}", operation_id) is None:
            raise JiejianError(ErrorCode.INPUT_INVALID, "登录操作标识格式无效")
        preparation_id = (
            None
            if operation_id is None
            else "prep_" + hashlib.sha256(f"{identity_id}:{operation_id}".encode()).hexdigest()[:32]
        )
        with self._lock:
            if preparation_id in self._active or preparation_id in self._terminal:
                return self.status(preparation_id)
            return self._start(identity_id, preparation_id=preparation_id)

    def latest(self, identity_id: str) -> IdentityPreparationView | None:
        self._identities.get(identity_id)
        with self._lock:
            active = next(
                (item for item in self._active.values() if item.request.identity_id == identity_id),
                None,
            )
            if active is not None:
                return self.status(active.request.preparation_id)
            return next(
                (
                    item
                    for item in reversed(tuple(self._terminal.values()))
                    if item.identity_id == identity_id
                ),
                None,
            )

    def start_official(
        self, identity_id: str, *, account: str, origin: str
    ) -> IdentityPreparationView | None:
        """仅提交或回读受监督登录进程；调用方保存返回标识后再观察，不在批次协调器等待。"""
        with self._lock:
            identity = self._identities.get(identity_id)
            endpoint, _ = self._source(identity)
            if (
                account not in {"curator", "judge"}
                or endpoint.rstrip("/") != origin.rstrip("/")
                or urlsplit(origin).hostname != "127.0.0.1"
            ):
                raise JiejianError(ErrorCode.STATE_PRECONDITION, "示例登录地址尚未与当前应用核对")
            active = next(
                (item for item in self._active.values() if item.request.identity_id == identity_id),
                None,
            )
            if active and active.official_account != account:
                raise JiejianError(
                    ErrorCode.TEST_IDENTITY_CONFLICT, "请先完成或关闭这个账号已打开的登录窗口"
                )
            if active is None:
                if identity.status is TestIdentityStatus.PREPARED:
                    return None
                if identity.status is TestIdentityStatus.NEEDS_REVIEW:
                    raise JiejianError(
                        ErrorCode.TEST_IDENTITY_NOT_READY,
                        "账号与当前角色对应需要复核，请先在账号页处理",
                    )
                if identity.auth_method is not None:
                    self._identities.reset(identity_id)
                view = self._start(identity_id, official_account=account)
                active = self._active[view.preparation_id]
            return self.status(active.request.preparation_id)

    def prepare_official(
        self, identity_id: str, *, account: str, origin: str
    ) -> IdentityPreparationView | None:
        """复用受监督登录进程自动准备官方虚构账号；普通登录 API 不能选择此配方。"""
        view = self.start_official(identity_id, account=account, origin=origin)
        if view is None:
            return None
        with self._lock:
            active = self._active.get(view.preparation_id)
        if active is None:
            return view
        # 已启动的同一进程由原状态回读收口；未知结果不再启动第二次登录。
        try:
            active.process.wait(timeout=40)
        except subprocess.TimeoutExpired:
            with self._lock:
                if active.request.preparation_id in self._active:
                    write_identity_preparation_marker(
                        active.controls.cancel, root=active.controls.root
                    )
                    terminate_process_tree(active.process, 2.0)
            self.status(active.request.preparation_id)
            raise JiejianError(
                ErrorCode.EXEC_TIMEOUT, "示例账号准备超时，已停止本次登录，请核对环境后重试"
            ) from None
        result = self.status(active.request.preparation_id)
        if result.status is not IdentityPreparationStatus.PREPARED:
            raise JiejianError(
                ErrorCode.IDENTITY_PREPARATION_FAILED,
                "示例账号自动登录未完成，请核对环境或使用登录浏览器",
            )
        return result

    def _start(
        self,
        identity_id: str,
        *,
        official_account: str | None = None,
        preparation_id: str | None = None,
    ) -> IdentityPreparationView:
        with self._lock:
            view = self._identities.get(identity_id)
            if view.status is not TestIdentityStatus.NOT_PREPARED:
                raise JiejianError(
                    ErrorCode.TEST_IDENTITY_NOT_READY,
                    "测试账号当前不能开始登录准备，请先处理复核或重置状态",
                )
            if any(item.request.identity_id == identity_id for item in self._active.values()):
                raise JiejianError(
                    ErrorCode.TEST_IDENTITY_CONFLICT,
                    "该测试账号已经在准备登录状态",
                )
            endpoint, source_fingerprint = self._source(view)
            scope = self._scope(endpoint)
            preparation_id = preparation_id or f"prep_{uuid4().hex}"
            attempt_dir = self._paths.identity_preparations / preparation_id
            attempt_dir.mkdir(parents=False, exist_ok=False)
            controls = identity_preparation_control_paths(attempt_dir)
            request = IdentityPreparationRequest(
                schema_version="1",
                preparation_id=preparation_id,
                project_id=view.project_id,
                identity_id=identity_id,
                target_scope=scope,
            )
            log_path = self._paths.identity_preparation_logs / f"{preparation_id}.log"
            process: subprocess.Popen[bytes] | None = None
            try:
                with log_path.open("ab") as stderr:
                    from product.backend.infrastructure.runtime.generated_files import (
                        register_generated_file,
                    )

                    register_generated_file(self._paths.root, log_path, "identity-log")
                    process = self._process_launcher(
                        self._environment,
                        "product.backend.infrastructure.samples.gallery_login"
                        if official_account
                        else "product.backend.infrastructure.identity.process",
                        *((official_account,) if official_account else ()),
                        role=ProcessEnvironmentRole.IDENTITY_PREPARATION,
                        extra_environment={"JIEJIAN_IDENTITY_PREPARATION_DIR": str(attempt_dir)},
                        cwd=self._project_root(),
                        stdin=subprocess.PIPE,
                        stdout=subprocess.PIPE,
                        stderr=stderr,
                        tree_name=f"identity-preparation-{preparation_id}",
                    )
                    # 取得进程立即纳入监督；日志句柄或 stdin 关闭失败也不能遗失所有权。
                    active = _ActivePreparation(
                        request,
                        process,
                        controls,
                        log_path,
                        source_fingerprint,
                        official_account=official_account,
                    )
                    self._active[preparation_id] = active
                assert process.stdin is not None
                process.stdin.write(canonical_identity_preparation_json_bytes(request))
                process.stdin.close()
            except Exception:
                if process is not None:
                    active.startup_failed = True
                    try:
                        if process.poll() is None:
                            terminate_process_tree(process, 2.0)
                        if process.poll() is not None:
                            self._finalize(preparation_id, active)
                    except (JiejianError, OSError, subprocess.TimeoutExpired):
                        # 对外仍返回脱敏启动失败，active 和目录保留以便 close/status 重试。
                        pass
                else:
                    shutil.rmtree(attempt_dir, ignore_errors=True)
                raise JiejianError(
                    ErrorCode.IDENTITY_PREPARATION_FAILED,
                    "测试账号登录浏览器启动失败",
                    details={"log_path": str(log_path)},
                ) from None
            return self._view(
                request,
                IdentityPreparationStatus.STARTING,
                "正在打开独立登录浏览器…",
            )

    def status(self, preparation_id: str) -> IdentityPreparationView:
        with self._lock:
            terminal = self._terminal.get(preparation_id)
            if terminal is not None:
                return terminal
            active = self._active.get(preparation_id)
            if active is None:
                raise JiejianError(
                    ErrorCode.TEST_IDENTITY_NOT_FOUND,
                    "测试账号准备会话不存在",
                )
            if active.process.poll() is not None:
                return self._finalize(preparation_id, active)
            if valid_identity_preparation_marker(active.controls.save):
                return self._view(
                    active.request,
                    IdentityPreparationStatus.SAVING,
                    "正在安全保存登录状态…",
                )
            if valid_identity_preparation_marker(active.controls.ready):
                return self._view(
                    active.request,
                    IdentityPreparationStatus.WAITING_FOR_LOGIN,
                    "请在独立浏览器中完成登录，然后回到界鉴确认保存",
                )
            return self._view(
                active.request,
                IdentityPreparationStatus.STARTING,
                "正在打开独立登录浏览器…",
            )

    def confirm(self, preparation_id: str) -> IdentityPreparationView:
        with self._lock:
            active = self._require_active(preparation_id)
            if active.process.poll() is not None:
                return self._finalize(preparation_id, active)
            if not valid_identity_preparation_marker(active.controls.ready):
                raise JiejianError(
                    ErrorCode.TEST_IDENTITY_NOT_READY,
                    "独立登录浏览器尚未准备完成",
                )
            write_identity_preparation_marker(
                active.controls.save,
                root=active.controls.root,
            )
            return self._view(
                active.request,
                IdentityPreparationStatus.SAVING,
                "正在安全保存登录状态…",
            )

    def cancel(self, preparation_id: str) -> IdentityPreparationView:
        with self._lock:
            active = self._require_active(preparation_id)
            if active.process.poll() is not None:
                return self._finalize(preparation_id, active)
            write_identity_preparation_marker(
                active.controls.cancel,
                root=active.controls.root,
            )
            return self._view(
                active.request,
                IdentityPreparationStatus.CANCELLING,
                "正在关闭独立登录浏览器…",
            )

    def close(self) -> None:
        with self._lock:
            for preparation_id, active in tuple(self._active.items()):
                if active.process.poll() is None:
                    write_identity_preparation_marker(
                        active.controls.cancel, root=active.controls.root
                    )
                    try:
                        active.process.wait(timeout=2.0)
                    except subprocess.TimeoutExpired:
                        terminate_process_tree(active.process, 2.0)
                if active.process.poll() is None:
                    raise JiejianError(
                        ErrorCode.IDENTITY_PREPARATION_FAILED, "登录状态准备失败，请查看日志后重试"
                    )
                # 回收失败保留 active 与进程句柄；调用方不可提前释放数据库。
                self._finalize(preparation_id, active)

    def _finalize(
        self,
        preparation_id: str,
        active: _ActivePreparation,
    ) -> IdentityPreparationView:
        process = active.process
        # 残留后代可能继承 stdout；先有界回收整棵树，避免读取结果等待不到 EOF。
        release_process_tree(process, 2.0)
        if not active.result_read:
            try:
                raw = (
                    b""
                    if process.stdout is None
                    else process.stdout.read(IDENTITY_PREPARATION_RESULT_MAX_BYTES + 1)
                )
                active.result = (
                    parse_identity_preparation_result(raw) if process.returncode == 0 else None
                )
            except (OSError, ValueError):
                active.result = None
            active.result_read = True
        # 结果只消费一次；后续处理重试仍使用已解析的非秘密结果。
        result = active.result

        if (
            active.startup_failed
            or result is None
            or result.preparation_id != preparation_id
            or result.project_id != active.request.project_id
            or result.identity_id != active.request.identity_id
        ):
            if result is not None:
                self._cleanup_result_secrets(result, active.request)
            view = self._view(
                active.request,
                IdentityPreparationStatus.FAILED,
                "登录状态准备失败，请查看日志后重试",
                error_code=ErrorCode.IDENTITY_PREPARATION_FAILED.value,
            )
        elif result.result_type is IdentityPreparationResultType.PREPARED:
            view = self._commit_result(active, result)
        elif result.result_type is IdentityPreparationResultType.UNSUPPORTED:
            view = self._view(
                active.request,
                IdentityPreparationStatus.UNSUPPORTED,
                "当前登录方式无法安全保存，需要高级身份配置",
            )
        elif result.result_type is IdentityPreparationResultType.CANCELLED:
            view = self._view(
                active.request,
                IdentityPreparationStatus.CANCELLED,
                "登录状态准备已取消",
            )
        else:
            view = self._view(
                active.request,
                IdentityPreparationStatus.FAILED,
                "登录状态准备失败，请查看日志后重试",
                error_code=result.error_code,
            )
        cleanup_complete = self.cleanup_attempt(active.controls.root, active.request)
        self._active.pop(preparation_id, None)
        self._terminal[preparation_id] = view
        if view.status is not IdentityPreparationStatus.FAILED and cleanup_complete:
            shutil.rmtree(active.controls.root, ignore_errors=True)
        elif cleanup_complete:
            # 进程树及临时凭据已收口；失败诊断目录可以由用户的闲置清理回收。
            from product.backend.infrastructure.maintenance.inventory import mark_runtime_idle

            mark_runtime_idle(self._paths.root, active.controls.root, "identity-preparation")
        return view

    def _commit_result(
        self,
        active: _ActivePreparation,
        result: IdentityPreparationResult,
    ) -> IdentityPreparationView:
        request = active.request
        try:
            if self._commit_prepared is not None:
                return self._commit_prepared(active, result)
            current = self._identities.get(request.identity_id)
            if (
                current.status is not TestIdentityStatus.NOT_PREPARED
                or self._source(current)[1] != active.source_fingerprint
            ):
                raise JiejianError(
                    ErrorCode.TEST_IDENTITY_NOT_READY,
                    "测试账号当前不能开始登录准备，请先处理复核或重置状态",
                )
            assert result.auth_method is not None
            assert result.prepared_at_us is not None
            self._identities.save_prepared_state(
                request.identity_id,
                PreparedLoginState(
                    auth_method=result.auth_method,
                    cookies=tuple(
                        TestIdentityCookie(**cookie.model_dump()) for cookie in result.cookies
                    ),
                    bearer_secret_ref=result.bearer_secret_ref,
                    prepared_at_us=result.prepared_at_us,
                ),
            )
            return self._view(
                request,
                IdentityPreparationStatus.PREPARED,
                "测试账号登录状态已安全保存",
            )
        except (JiejianError, ValueError):
            cleanup_complete = self._cleanup_result_secrets(result, request)
            return self._view(
                request,
                IdentityPreparationStatus.FAILED,
                (
                    "登录状态保存失败，已回收本次临时凭据"
                    if cleanup_complete
                    else "登录状态保存失败，临时凭据将在下次启动时继续清理"
                ),
                error_code=ErrorCode.IDENTITY_PREPARATION_FAILED.value,
            )

    def _cleanup_result_secrets(
        self, result: IdentityPreparationResult, request: IdentityPreparationRequest
    ) -> bool:
        refs = tuple(cookie.value_secret_ref for cookie in result.cookies)
        if result.bearer_secret_ref:
            refs += (result.bearer_secret_ref,)
        complete = True
        try:
            committed = set(self._identities.get_record(request.identity_id).secret_refs)
        except JiejianError as exc:
            if exc.code != ErrorCode.TEST_IDENTITY_NOT_FOUND.value:
                return False
            committed = set()
        for secret_ref in refs:
            if not secret_ref.startswith(
                f"cred:jiejian/test-identity/{request.project_id}/{request.identity_id}/"
            ):
                complete = False
                continue
            if secret_ref in committed:
                continue
            try:
                self._secret_store.delete(secret_ref)
            except (JiejianError, OSError, RuntimeError, ValueError):
                complete = False
        return complete

    def cleanup_attempt(
        self, root: Path, request: IdentityPreparationRequest | None = None
    ) -> bool:
        """回收已识别的临时引用并保留已提交引用；失败时保留 journal 供重试。"""
        # journal 只是待核对清单：逐项验证命名空间、账号和项目，不据文件内容删除任意凭据。
        # 数据库已有的引用属于成功采用的账号，即使 journal 仍在，也不能作为孤儿删除。
        journal = root / "secret-refs.json"
        if not journal.is_file():
            return True
        try:
            with journal.open("rb") as stream:
                raw = stream.read(65_537)
            if len(raw) > 65_536:
                return False
            payload = json.loads(raw)
            if (
                not isinstance(payload, dict)
                or set(payload) != {"schema_version", "identity_id", "secret_refs"}
                or payload["schema_version"] != "1"
                or not isinstance(payload["identity_id"], str)
                or not re.fullmatch(r"tid_[0-9a-f]{32}", payload["identity_id"])
                or not isinstance(payload["secret_refs"], list)
            ):
                return False
            identity_id = payload["identity_id"]
            if request is not None and identity_id != request.identity_id:
                return False
            try:
                record = self._identities.get_record(identity_id)
            except JiejianError as exc:
                if exc.code != ErrorCode.TEST_IDENTITY_NOT_FOUND.value:
                    return False
                record = None
            committed = set() if record is None else set(record.secret_refs)
            project_id = (
                request.project_id
                if request is not None
                else None
                if record is None
                else record.project_id
            )
            complete = True
            for value in payload["secret_refs"]:
                try:
                    ref = validate_credential_secret_ref(value)
                    parts = ref.split("/")
                    if (
                        len(parts) < 5
                        or parts[:2] != ["cred:jiejian", "test-identity"]
                        or parts[3] != identity_id
                        or project_id is not None
                        and parts[2] != project_id
                    ):
                        complete = False
                        continue
                    if ref not in committed:
                        self._secret_store.delete(ref)
                except (JiejianError, OSError, RuntimeError, TypeError, ValueError):
                    complete = False
            return complete
        except (JiejianError, OSError, RuntimeError, TypeError, ValueError):
            return False

    def _source(self, identity) -> tuple[str, str]:
        return preparation_source(
            identity,
            self._application_understanding.get(identity.project_id),
            self._business_boundaries.view(identity.project_id),
        )

    def _reconcile_orphaned_attempts(self) -> None:
        for attempt_dir in self._paths.identity_preparations.iterdir():
            if not attempt_dir.is_dir():
                continue
            if self.cleanup_attempt(attempt_dir):
                shutil.rmtree(attempt_dir, ignore_errors=True)

    def _require_active(self, preparation_id: str) -> _ActivePreparation:
        active = self._active.get(preparation_id)
        if active is None:
            raise JiejianError(
                ErrorCode.TEST_IDENTITY_NOT_FOUND,
                "测试账号准备会话不存在",
            )
        return active

    def _project_root(self) -> Path:
        # 发布版没有源码仓库；登录子进程与控制面复用同一包内产品和运行身份。
        if self._environment.get("JIEJIAN_RUNTIME_MODE") == "portable":
            release = self._environment.get("JIEJIAN_RELEASE_ROOT")
            if not release or not (Path(release).resolve() / "app").is_dir():
                raise JiejianError(
                    ErrorCode.RUNTIME_ENVIRONMENT_INVALID, "界鉴启动环境缺少包内产品目录"
                )
            return Path(release).resolve() / "app"
        configured = self._environment.get("JIEJIAN_PROJECT_ROOT")
        if not configured:
            raise JiejianError(
                ErrorCode.RUNTIME_ENVIRONMENT_INVALID,
                "界鉴启动环境缺少项目源码根目录",
            )
        return Path(configured).resolve()

    @staticmethod
    def _scope(endpoint: str) -> WebTargetScope:
        parsed = urlsplit(endpoint)
        host = parsed.hostname
        if host is None:
            raise JiejianError(ErrorCode.APPLICATION_ENDPOINT_INVALID, "应用运行地址无效")
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        origin = f"{parsed.scheme}://{host}:{port}"
        return WebTargetScope(
            base_url=origin,
            allowed_origins=(origin,),
            allowed_hosts=(host,),
            allowed_ports=(port,),
            allow_private_network=True,
            follow_redirects=False,
            timeout_seconds=10.0,
            max_requests=256,
            max_response_bytes=1_048_576,
        )

    def _view(
        self,
        request: IdentityPreparationRequest,
        status: IdentityPreparationStatus,
        message: str,
        *,
        error_code: str | None = None,
    ) -> IdentityPreparationView:
        return IdentityPreparationView(
            preparation_id=request.preparation_id,
            identity_id=request.identity_id,
            status=status,
            message=message,
            error_code=error_code,
            log_path=str(self._paths.identity_preparation_logs / f"{request.preparation_id}.log"),
        )


class IdentityPreparationHandler:
    # 一个实例使用当前 lease_owner 执行任务；浏览器监督与数据库完成不能各自宣布成功。
    def __init__(self, var_dir, *, lease_owner, uow_factory, attempts, environ, secret_store=None):
        self._var_dir, self._owner, self._uow = var_dir, lease_owner, uow_factory
        self._attempts, self._environment = attempts, environ
        self._clock = lambda: time.time_ns() // 1000
        self._secrets = secret_store or default_secret_store()
        self._identities = TestIdentityService(uow_factory, secret_store=self._secrets)
        self._control = AttemptProcessControl(
            uow_factory=uow_factory,
            attempt_service=attempts,
            lease_owner=lease_owner,
            utc_now_us=self._clock,
            lease_duration_us=DEFAULT_LEASE_DURATION_US,
            poll_interval_seconds=0.1,
            termination_grace_seconds=2.0,
        )

    def run_job(self, job_id):
        # 领取不到租约即退出；HTTP 的保存或取消意图只在持有该次执行权时向浏览器转发。
        claimed = self._attempts.claim(
            ClaimJob(
                job_id=job_id,
                lease_owner=self._owner,
                now_us=self._clock(),
                lease_duration_us=DEFAULT_LEASE_DURATION_US,
            )
        )
        if claimed is None:
            return None
        job = claimed.job
        with self._uow() as work:
            row = work.identity_preparations.get(job.identity_preparation_id)
        engine = IdentityLoginSupervisor(
            self._var_dir,
            self._identities,
            self._secrets,
            self._environment,
            application_understanding=ApplicationUnderstandingService(self._uow),
            business_boundaries=BusinessBoundaryService(self._uow),
            reconcile=False,
            commit_prepared=lambda active, result: self._commit(job, row, active, result),
        )
        try:
            identity = self._identities.get(row["identity_id"])
            if engine._source(identity)[1] != row["source_fingerprint"]:
                raise JiejianError(ErrorCode.STATE_PRECONDITION, "账号或应用条件已变化")
            engine._start(
                row["identity_id"],
                preparation_id=row["preparation_id"],
                official_account=row["official_account"],
            )
            active = engine._active[row["preparation_id"]]

            def controls(current):
                with self._uow() as work:
                    latest = work.identity_preparations.get(row["preparation_id"])
                if current.cancel_requested_at_us is not None:
                    write_identity_preparation_marker(
                        active.controls.cancel, root=active.controls.root
                    )
                elif latest["save_requested"] and valid_identity_preparation_marker(
                    active.controls.ready
                ):
                    write_identity_preparation_marker(
                        active.controls.save, root=active.controls.root
                    )

            timed_out, forced = self._control.monitor(
                active.process,
                job,
                max_duration_us=600_000_000,
                cancel_path=active.controls.root / "worker-cancel.requested",
                on_poll=controls,
            )
            value = engine.status(row["preparation_id"])
            if active.controls.root.exists() and not engine.cleanup_attempt(
                active.controls.root, active.request
            ):
                with self._uow() as work:
                    work.identity_preparations.update(
                        row["preparation_id"], phase="CLEANUP_REQUIRED", now_us=self._clock()
                    )
                    work.commit()
                value = value.model_copy(update={"cleanup_required": True})
            current = self._control.read_job(job_id)
            if current.state is JobState.SUCCEEDED:
                return value
            if current.cancel_requested_at_us is not None:
                self._attempts.complete_cancellation(
                    CompleteCancellation(
                        job_id=job_id,
                        lease_owner=self._owner,
                        fencing_token=job.fencing_token,
                        now_us=self._clock(),
                    )
                )
                return value
            if timed_out or forced or value.status is not IdentityPreparationStatus.UNSUPPORTED:
                raise JiejianError(ErrorCode.IDENTITY_PREPARATION_FAILED, "登录未形成可采用的结果")
            self._finish(job, row, phase="UNSUPPORTED")
            return value
        except Exception as primary:
            cleanup_failed = False
            try:
                engine.close()
            except Exception:
                cleanup_failed = True
            current = self._control.read_job(job_id)
            if current.state is JobState.RUNNING:
                try:
                    self._attempts.record_fatal_failure(
                        FatalFailure(
                            job_id=job_id,
                            lease_owner=self._owner,
                            fencing_token=job.fencing_token,
                            now_us=self._clock(),
                            reason_code=FatalFailureCode.RUNNER_FATAL,
                            error_code=primary.code
                            if isinstance(primary, JiejianError)
                            else "IDENTITY_PREPARATION_FAILED",
                            cause_code="PROCESS_TREE_FAILED" if cleanup_failed else None,
                        )
                    )
                finally:
                    if cleanup_failed:
                        with self._uow() as work:
                            work.identity_preparations.update(
                                row["preparation_id"],
                                phase="CLEANUP_REQUIRED",
                                now_us=self._clock(),
                            )
                            work.commit()
            raise

    def _finish(self, job, row, *, phase, prepared=None):
        # 浏览器结果只是候选。写锁内同时重验账号代次、准备所有者和来源，拒绝重置后的迟到结果。
        now = self._clock()
        with self._uow() as work:
            work.acquire_write_lock()
            current = work.test_identities.get(row["identity_id"])
            if current is None:
                raise JiejianError(ErrorCode.TEST_IDENTITY_NOT_FOUND, "账号已被删除")
            generation, owner = work.test_identities.preparation_owner(current.identity_id)
            actor = work.business_boundaries.actor_revision(
                current.actor_id, current.actor_revision
            )
            understanding = work.application_understanding.get(current.project_id)
            source = preparation_source(
                current, understanding, SimpleNamespace(actors=() if actor is None else (actor,))
            )[1]
            if (
                generation != row["authentication_generation"]
                or owner != row["preparation_id"]
                or source != row["source_fingerprint"]
            ):
                raise JiejianError(ErrorCode.STATE_PRECONDITION, "登录结果对应的账号或应用已经变化")
            # 条件完成同时核对 attempt、租约、fence 和取消意图，旧 Worker 不能抢先提交。
            completed = work.job_control.complete_identity_preparation(
                job_id=job.job_id,
                identity_preparation_id=row["preparation_id"],
                request_hash=job.request_hash,
                attempt=job.attempt,
                lease_owner=self._owner,
                fencing_token=job.fencing_token,
                now_us=now,
            )
            if completed is None:
                raise JiejianError(ErrorCode.JOB_LEASE_MISMATCH, "登录任务已取消或执行所有权失效")
            if prepared is not None:
                # 与 Job 终态、准备阶段及事件一起提交；失败时不留下“账号已保存、任务未完成”。
                # 事务只采用引用，外部秘密写入的补偿仍由监督器的 journal 清理负责。
                self._identities.save_prepared_state(current.identity_id, prepared, work=work)
            work.identity_preparations.update(row["preparation_id"], phase=phase, now_us=now)
            append_job_event(
                work,
                job=completed,
                event_type=JobEventType.JOB_SUCCEEDED,
                source_state=JobState.RUNNING,
                target_state=JobState.SUCCEEDED,
                occurred_at_us=now,
                metadata={"attempt": job.attempt, "fencing_token": job.fencing_token},
            )
            work.commit()

    def _commit(self, job, row, active, result):
        prepared = PreparedLoginState(
            auth_method=result.auth_method,
            cookies=tuple(TestIdentityCookie(**cookie.model_dump()) for cookie in result.cookies),
            bearer_secret_ref=result.bearer_secret_ref,
            prepared_at_us=result.prepared_at_us,
        )
        self._finish(job, row, phase="PREPARED", prepared=prepared)
        return IdentityPreparationView(
            preparation_id=row["preparation_id"],
            identity_id=row["identity_id"],
            status=IdentityPreparationStatus.PREPARED,
            message="登录已保存",
        )
