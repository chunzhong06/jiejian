# 定位：可信内置演示应用与新手快速检查之间的生命周期边界。
# 职责：固定启动样例进程、读取一次 ready 信号并复用 onboarding 排队链；不发送目标请求。

from __future__ import annotations

import re
import secrets
import subprocess
import sys
from collections.abc import Callable, Mapping
from pathlib import Path
from queue import Empty, Queue
from threading import Lock, Thread
from typing import Any

from ..errors import ErrorCode, JiejianError
from ..execution.process_environment import minimal_process_environment
from .models import OnboardingConfirmations, OnboardingDemoStatus, OnboardingSessionUpdate

_READY_RE = re.compile(r"^http://127\.0\.0\.1:([1-9][0-9]{0,4})$")
_DEMO_LOG_RELATIVE = "var/log/onboarding-demo.log"
_DEMO_OWNER_ENV = "JIEJIAN_SAMPLE_OWNER_TOKEN"
_DEMO_ATTACKER_ENV = "JIEJIAN_SAMPLE_ATTACKER_TOKEN"


class DemoRuntimeManager:
    """固定管理内置样例进程，并把其地址交给已有快速检查应用服务。"""

    def __init__(
        self,
        onboarding,
        *,
        var_dir: Path,
        base_environment: Mapping[str, str],
        secret_vault,
        popen: Callable[..., Any] = subprocess.Popen,
    ) -> None:
        self._onboarding = onboarding
        self._var_dir = var_dir.resolve()
        self._base_environment = dict(base_environment)
        self._secret_vault = secret_vault
        self._popen = popen
        self._lock = Lock()
        self._process: Any | None = None
        self._stderr: Any | None = None
        self._status = OnboardingDemoStatus(
            status="stopped",
            message="内置演示尚未启动。",
        )

    def status(self) -> OnboardingDemoStatus:
        with self._lock:
            process = self._process
            if process is None:
                return self._status
            if process.poll() is None:
                return self._status.model_copy(update={"status": "running"})
            self._process = None
            self._close_process_streams_locked(process)
            if self._status.status in {"starting", "running"}:
                self._status = self._status.model_copy(
                    update={
                        "status": "failed",
                        "message": "内置演示进程意外退出，请查看 var/log/onboarding-demo.log 后重试。",
                    }
                )
            return self._status

    def start(self) -> OnboardingDemoStatus:
        with self._lock:
            if self._process is not None and self._process.poll() is None:
                return self._status.model_copy(update={"status": "running"})
            if self._status.session_id and self._status.run_id:
                return self._status.model_copy(update={"status": "stopped"})
            self._status = OnboardingDemoStatus(
                status="starting",
                message="正在启动可信内置演示。",
            )
            try:
                result = self._start_locked()
            except JiejianError:
                self._stop_process_locked()
                self._status = OnboardingDemoStatus(
                    status="failed",
                    message="内置演示启动失败，请查看演示日志。",
                )
                raise
            except Exception as exc:
                self._stop_process_locked()
                self._status = OnboardingDemoStatus(
                    status="failed",
                    message="内置演示启动失败，请查看演示日志。",
                )
                raise JiejianError(
                    ErrorCode.ONBOARDING_DEMO_FAILED,
                    "内置演示启动失败，请查看演示日志。",
                    details={"log_path": _DEMO_LOG_RELATIVE},
                ) from exc
            self._status = result.model_copy(update={"status": "running"})
            return self._status

    def stop(self) -> OnboardingDemoStatus:
        with self._lock:
            self._stop_process_locked()
            if self._status.status != "failed":
                self._status = self._status.model_copy(
                    update={"status": "stopped", "message": "内置演示已停止；已排队的检查结果不会被删除。"}
                )
            return self._status

    def close(self) -> None:
        with self._lock:
            self._stop_process_locked()

    def _start_locked(self) -> OnboardingDemoStatus:
        source = self._prepare_source()
        session = self._onboarding.create_session(source, "界鉴内置演示")
        try:
            owner_token = secrets.token_urlsafe(32)
            attacker_token = secrets.token_urlsafe(32)
            self._onboarding.put_credentials(session.session_id, owner_token, attacker_token)
            session = self._onboarding.get_session(session.session_id)
            self._start_process_locked(owner_token, attacker_token)
            target = self._read_ready_url_locked()
            updated = self._onboarding.update_session(
                session.session_id,
                OnboardingSessionUpdate(
                    revision=session.revision,
                    target_address=target,
                    primary_display_name="演示所有者",
                    comparison_display_name="演示对照者",
                    primary_resource_id="owner-resource",
                    comparison_resource_id="attacker-resource",
                    read_only_path_template="/resources/{resource_id}",
                    recovery_path="/reset",
                    startup_candidate_source="trusted:jiejian.sample_app",
                    confirmations=OnboardingConfirmations(
                        app_started=True,
                        target_authorized=True,
                        recovery_confirmed=True,
                        dangerous_inference_confirmed=True,
                    ),
                ),
            )
            submitted = self._onboarding.quick_check(updated.session_id)
            return OnboardingDemoStatus(
                status="running",
                session_id=submitted.session.session_id,
                project_id=submitted.project_id,
                run_id=submitted.run_id,
                job_id=submitted.job_id,
                message="演示数据，不代表真实项目；检查已排队。",
            )
        except Exception:
            self._secret_vault.clear_session(session.session_id)
            raise

    def _prepare_source(self) -> Path:
        var_root = self._var_dir.resolve()
        demo_entry = var_root / "onboarding" / "demo"
        root = demo_entry.resolve()
        source_entry = demo_entry / "source"
        source = source_entry.resolve()
        if not root.is_relative_to(var_root) or not source.is_relative_to(root):
            raise JiejianError(ErrorCode.ONBOARDING_PATH_UNSAFE, "内置演示目录不安全")
        root.mkdir(parents=True, exist_ok=True)
        source.mkdir(parents=True, exist_ok=True)
        package = source / "package.json"
        if package.is_symlink() or not package.resolve().is_relative_to(source):
            raise JiejianError(ErrorCode.ONBOARDING_PATH_UNSAFE, "内置演示配置路径不安全")
        package.write_text(
            '{"name":"jiejian-demo","private":true}',
            encoding="utf-8",
        )
        return source

    def _start_process_locked(
        self,
        owner_token: str,
        attacker_token: str,
    ) -> None:
        log_path = self._var_dir / "log" / "onboarding-demo.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        environment = minimal_process_environment(self._base_environment)
        environment["PYTHONPATH"] = str(Path(__file__).resolve().parents[2])
        environment[_DEMO_OWNER_ENV] = owner_token
        environment[_DEMO_ATTACKER_ENV] = attacker_token
        self._stderr = log_path.open("ab")
        try:
            self._process = self._popen(
                [sys.executable, "-B", "-m", "jiejian.sample_app", "--variant", "vulnerable", "--port", "0"],
                shell=False,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=self._stderr,
                env=environment,
                cwd=str(self._var_dir),
                text=True,
                bufsize=1,
            )
        except Exception:
            self._close_stderr_locked()
            raise JiejianError(
                ErrorCode.ONBOARDING_DEMO_FAILED,
                "内置演示进程无法启动，请查看演示日志。",
                details={"log_path": _DEMO_LOG_RELATIVE},
            ) from None

    def _read_ready_url_locked(self) -> str:
        output = getattr(self._process, "stdout", None)
        if output is None:
            raise JiejianError(ErrorCode.ONBOARDING_DEMO_FAILED, "内置演示未提供可信启动信号。", details={"log_path": _DEMO_LOG_RELATIVE})
        ready: Queue[str | None] = Queue(maxsize=1)

        def read_line() -> None:
            try:
                ready.put(output.readline(), timeout=0.1)
            except Exception:
                try:
                    ready.put(None, timeout=0.1)
                except Exception:
                    pass

        Thread(target=read_line, name="jiejian-demo-ready", daemon=True).start()
        try:
            line = ready.get(timeout=10)
        except Empty:
            raise JiejianError(ErrorCode.ONBOARDING_DEMO_FAILED, "内置演示启动超时，请查看演示日志。", details={"log_path": _DEMO_LOG_RELATIVE}) from None
        candidate = (line or "").strip()
        match = _READY_RE.fullmatch(candidate)
        if match is None or not 1 <= int(match.group(1)) <= 65535:
            raise JiejianError(ErrorCode.ONBOARDING_DEMO_FAILED, "内置演示启动信号无效，请查看演示日志。", details={"log_path": _DEMO_LOG_RELATIVE})
        return candidate

    def _stop_process_locked(self) -> None:
        process, self._process = self._process, None
        if process is not None:
            try:
                if process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=2)
                    except Exception:
                        process.kill()
                        try:
                            process.wait(timeout=2)
                        except Exception:
                            pass
            except Exception:
                pass
            self._close_process_streams_locked(process)
        self._close_stderr_locked()

    def _close_process_streams_locked(self, process: Any) -> None:
        streams = (
            getattr(process, "stdout", None),
            getattr(process, "stderr", None),
        )
        for stream in streams:
            if stream is None or stream is self._stderr:
                continue
            try:
                stream.close()
            except Exception:
                pass

    def _close_stderr_locked(self) -> None:
        stream, self._stderr = self._stderr, None
        if stream is not None:
            try:
                stream.close()
            except Exception:
                pass
