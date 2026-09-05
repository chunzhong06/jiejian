# =============================================================================
# 测试身份准备进程管理
#
# 定位
#   TestIdentityService 与独立 headed browser 进程之间的本地生命周期编排。
#
# 职责
#   启动受控进程｜转发保存/取消意图｜提交非秘密结果｜重启时清理孤立凭据。
#
# 边界
#   不读取密码或登录秘密正文；仅凭精确 secret_ref 进行补偿与恢复清理。
#
# 调用链
#   API → IdentityPreparationManager → child process → TestIdentityService
# =============================================================================

from __future__ import annotations

import json
import re
import shutil
import subprocess
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.core.business_boundary import BusinessRevisionState, boundary_sha256
from product.backend.core.test_identity import TestIdentityCookie
from product.backend.infra.identity.control import (
    IdentityPreparationControlPaths,
    identity_preparation_control_paths,
    valid_identity_preparation_marker,
    write_identity_preparation_marker,
)
from product.backend.infra.runtime.paths import RuntimePaths
from product.backend.infra.runtime.process.environment import (
    ProcessEnvironmentRole,
    spawn_python_module,
)
from product.backend.infra.runtime.process.tree import (
    release_process_tree,
    terminate_process_tree,
)
from product.backend.infra.secrets import SecretStore, validate_credential_secret_ref
from product.backend.workflows.test_identities.service import (
    PreparedLoginState,
    TestIdentityService,
    TestIdentityStatus,
)
from product.protocols import (
    IDENTITY_PREPARATION_RESULT_MAX_BYTES,
    IdentityPreparationRequest,
    IdentityPreparationResult,
    IdentityPreparationResultType,
    canonical_identity_preparation_json_bytes,
    parse_identity_preparation_result,
)
from product.protocols.web.target import WebTargetScope


class IdentityPreparationStatus(StrEnum):
    STARTING = "STARTING"
    WAITING_FOR_LOGIN = "WAITING_FOR_LOGIN"
    SAVING = "SAVING"
    CANCELLING = "CANCELLING"
    PREPARED = "PREPARED"
    UNSUPPORTED = "UNSUPPORTED"
    CANCELLED = "CANCELLED"
    FAILED = "FAILED"


class IdentityPreparationView(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        strict=True,
        hide_input_in_errors=True,
    )

    preparation_id: str = Field(pattern=r"^prep_[0-9a-f]{32}$")
    identity_id: str = Field(pattern=r"^tid_[0-9a-f]{32}$")
    status: IdentityPreparationStatus
    message: str = Field(min_length=1, max_length=256)
    error_code: str | None = Field(default=None, max_length=64)
    log_path: str = Field(min_length=1, max_length=2048)


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


class IdentityPreparationManager:
    """为每个测试账号最多监督一个当前准备进程。"""

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
    ) -> None:
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
        self._reconcile_orphaned_attempts()

    def active_runtime_paths(self) -> tuple[Path, ...]:
        """返回当前受监督准备会话目录，供本地维护保护真实活跃路径。"""

        with self._lock:
            return tuple(
                active.controls.root
                for active in self._active.values()
            )

    def start(self, identity_id: str) -> IdentityPreparationView:
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
            preparation_id = f"prep_{uuid4().hex}"
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
                    process = self._process_launcher(
                        self._environment,
                        "product.backend.infra.identity.process",
                        role=ProcessEnvironmentRole.IDENTITY_PREPARATION,
                        extra_environment={
                            "JIEJIAN_IDENTITY_PREPARATION_DIR": str(attempt_dir)
                        },
                        cwd=self._project_root(),
                        stdin=subprocess.PIPE,
                        stdout=subprocess.PIPE,
                        stderr=stderr,
                        tree_name=f"identity-preparation-{preparation_id}",
                    )
                    # 取得进程立即纳入监督；日志句柄或 stdin 关闭失败也不能遗失所有权。
                    active = _ActivePreparation(request, process, controls, log_path, source_fingerprint)
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
                    write_identity_preparation_marker(active.controls.cancel, root=active.controls.root)
                    try:
                        active.process.wait(timeout=2.0)
                    except subprocess.TimeoutExpired:
                        terminate_process_tree(active.process, 2.0)
                if active.process.poll() is None:
                    raise JiejianError(ErrorCode.IDENTITY_PREPARATION_FAILED, "登录状态准备失败，请查看日志后重试")
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
                raw = b"" if process.stdout is None else process.stdout.read(IDENTITY_PREPARATION_RESULT_MAX_BYTES + 1)
                active.result = parse_identity_preparation_result(raw) if process.returncode == 0 else None
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
        cleanup_complete = self._cleanup_journal(active.controls.root, active.request)
        self._active.pop(preparation_id, None)
        self._terminal[preparation_id] = view
        if view.status is not IdentityPreparationStatus.FAILED and cleanup_complete:
            shutil.rmtree(active.controls.root, ignore_errors=True)
        return view

    def _commit_result(
        self,
        active: _ActivePreparation,
        result: IdentityPreparationResult,
    ) -> IdentityPreparationView:
        request = active.request
        try:
            current = self._identities.get(request.identity_id)
            if (current.status is not TestIdentityStatus.NOT_PREPARED
                    or self._source(current)[1] != active.source_fingerprint):
                raise JiejianError(ErrorCode.TEST_IDENTITY_NOT_READY, "测试账号当前不能开始登录准备，请先处理复核或重置状态")
            assert result.auth_method is not None
            assert result.prepared_at_us is not None
            self._identities.save_prepared_state(
                request.identity_id,
                PreparedLoginState(
                    auth_method=result.auth_method,
                    cookies=tuple(
                        TestIdentityCookie(**cookie.model_dump())
                        for cookie in result.cookies
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

    def _cleanup_result_secrets(self, result: IdentityPreparationResult, request: IdentityPreparationRequest) -> bool:
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
            if not secret_ref.startswith(f"cred:jiejian/test-identity/{request.project_id}/{request.identity_id}/"):
                complete = False
                continue
            if secret_ref in committed:
                continue
            try:
                self._secret_store.delete(secret_ref)
            except (JiejianError, OSError, RuntimeError, ValueError):
                complete = False
        return complete

    def _cleanup_journal(self, root: Path, request: IdentityPreparationRequest | None = None) -> bool:
        """只回收本次 journal 的合法引用；已提交及无关账号引用绝不删除。"""
        journal = root / "secret-refs.json"
        if not journal.is_file():
            return True
        try:
            with journal.open("rb") as stream:
                raw = stream.read(65_537)
            if len(raw) > 65_536:
                return False
            payload = json.loads(raw)
            if (not isinstance(payload, dict) or set(payload) != {"schema_version", "identity_id", "secret_refs"}
                    or payload["schema_version"] != "1" or not isinstance(payload["identity_id"], str)
                    or not re.fullmatch(r"tid_[0-9a-f]{32}", payload["identity_id"])
                    or not isinstance(payload["secret_refs"], list)):
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
            project_id = request.project_id if request is not None else None if record is None else record.project_id
            complete = True
            for value in payload["secret_refs"]:
                try:
                    ref = validate_credential_secret_ref(value)
                    parts = ref.split("/")
                    if (len(parts) < 5 or parts[:2] != ["cred:jiejian", "test-identity"]
                            or parts[3] != identity_id or project_id is not None and parts[2] != project_id):
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
        """登录尝试只冻结非秘密来源；updated_at 仅识别本次尝试期间的重置。"""
        boundary = self._business_boundaries.view(identity.project_id)
        actor = next((item for item in boundary.actors
            if item.actor_id == identity.actor_id and item.project_id == identity.project_id
            and item.revision == identity.actor_revision
            and item.effective_state is BusinessRevisionState.ACTIVE), None)
        if actor is None:
            raise JiejianError(ErrorCode.TEST_IDENTITY_NOT_READY,
                "测试账号当前不能开始登录准备，请先处理复核或重置状态")
        understanding = self._application_understanding.get(identity.project_id)
        if (understanding.confirmed_endpoint is None or not understanding.endpoint_reachable
                or understanding.endpoint_confirmed_at_us is None
                or understanding.endpoint_source_fingerprint is None):
            raise JiejianError(ErrorCode.APPLICATION_ENDPOINT_INVALID, "应用运行地址无效")
        facts = {name: getattr(identity, name) for name in (
            "project_id", "identity_id", "actor_id", "actor_revision", "created_at_us", "updated_at_us")}
        facts.update({name: getattr(understanding, name) for name in (
            "confirmed_endpoint", "endpoint_source_fingerprint", "source_fingerprint")})
        return understanding.confirmed_endpoint, boundary_sha256(facts)

    def _reconcile_orphaned_attempts(self) -> None:
        for attempt_dir in self._paths.identity_preparations.iterdir():
            if not attempt_dir.is_dir():
                continue
            if self._cleanup_journal(attempt_dir):
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
            log_path=str(
                self._paths.identity_preparation_logs
                / f"{request.preparation_id}.log"
            ),
        )
