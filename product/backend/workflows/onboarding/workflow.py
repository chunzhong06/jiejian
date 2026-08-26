# =============================================================================
# 应用接入辅助工作流
#
# 定位
#   系统目录选择与受限只读识别之间的应用边界。
#
# 职责
#   隔离系统目录选择器｜执行预算内目录识别｜返回无秘密候选事实
#
# 边界
#   选择动作不扫描；识别不执行命令、不联网、不读取源码正文。
#
# 调用链
#   Onboarding API → OnboardingWorkflow → FolderSelector / Discovery
# =============================================================================

from __future__ import annotations

import json
import os
import subprocess
import threading
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Protocol

from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.infra.runtime.paths import RuntimePaths
from product.backend.infra.runtime.process.environment import (
    ProcessEnvironmentRole,
    confirmed_python_executable,
    minimal_process_environment,
    run_python_module,
)
from product.backend.workflows.onboarding.discovery import discover_folder
from product.backend.workflows.onboarding.models import (
    DiscoveryLimits,
    DiscoveryResult,
    FolderSelectionResult,
)


class FolderSelector(Protocol):
    def select_folder(self) -> FolderSelectionResult:
        """打开系统目录选择器，返回 selected/cancelled/unavailable。"""


class SystemFolderSelector:
    """用短生命周期主线程 UI 进程隔离 Tk，并保证超时和并发请求可收敛。"""

    _DESKTOP_ENVIRONMENT_KEYS = (
        "ALLUSERSPROFILE",
        "APPDATA",
        "HOMEDRIVE",
        "HOMEPATH",
        "PROGRAMDATA",
        "PUBLIC",
        "SYSTEMDRIVE",
    )

    def __init__(
        self,
        *,
        environment: Mapping[str, str] | None = None,
        timeout_seconds: float = 120.0,
        python_executable: str | None = None,
        var_dir: Path | None = None,
        platform_name: str | None = None,
        runner: Callable[..., subprocess.CompletedProcess[str]] | None = None,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("folder selector timeout must be positive")
        self._environment = dict(environment if environment is not None else os.environ)
        self._timeout_seconds = timeout_seconds
        self._python_executable = python_executable
        selected_var = var_dir or Path(self._environment.get("JIEJIAN_VAR_DIR", "var"))
        self._runtime_paths = RuntimePaths(selected_var.resolve()).ensure_layout()
        self._platform_name = platform_name or os.name
        self._runner = runner
        self._selection_lock = threading.Lock()

    def select_folder(self) -> FolderSelectionResult:
        if self._platform_name != "nt":
            return FolderSelectionResult(
                status="unavailable",
                message="当前平台没有可用的系统目录选择器，请改用手工绝对路径",
            )
        if not self._selection_lock.acquire(blocking=False):
            return FolderSelectionResult(
                status="unavailable",
                message="目录选择器已经打开，请先完成或取消当前选择",
            )
        try:
            try:
                child_environment = minimal_process_environment(
                    self._environment,
                    role=ProcessEnvironmentRole.ONBOARDING_SELECTOR,
                )
                source_by_casefold = {
                    key.casefold(): value for key, value in self._environment.items()
                }
                for name in self._DESKTOP_ENVIRONMENT_KEYS:
                    value = source_by_casefold.get(name.casefold())
                    if value:
                        child_environment[name] = value
                confirmed_executable = confirmed_python_executable(child_environment)
                if self._python_executable is not None:
                    # 测试替身也必须声明同一解释器，避免目录选择器形成例外旁路。
                    requested_executable = Path(self._python_executable).resolve()
                    if requested_executable != Path(confirmed_executable):
                        raise JiejianError(
                            ErrorCode.ONBOARDING_SELECTOR_UNAVAILABLE,
                            "系统目录选择器不能替换界鉴已确认的 Python 解释器",
                        )
                if self._runner is not None:
                    completed = self._runner(
                        [
                            confirmed_executable,
                            "-B",
                            "-m",
                            "product.backend.workflows.onboarding.folder_picker_process",
                        ],
                        cwd=str(Path(__file__).resolve().parents[4]),
                        env=child_environment,
                        stdin=subprocess.DEVNULL,
                        capture_output=True,
                        text=True,
                        encoding="utf-8",
                        errors="replace",
                        timeout=self._timeout_seconds,
                        check=False,
                        shell=False,
                    )
                else:
                    source_environment = dict(self._environment)
                    source_environment.setdefault(
                        "JIEJIAN_VAR_DIR", str(self._runtime_paths.root)
                    )
                    desktop_environment = {
                        name: child_environment[name]
                        for name in self._DESKTOP_ENVIRONMENT_KEYS
                        if name in child_environment
                    }
                    completed = run_python_module(
                        source_environment,
                        "product.backend.workflows.onboarding.folder_picker_process",
                        role=ProcessEnvironmentRole.ONBOARDING_SELECTOR,
                        cwd=self._runtime_paths.temp,
                        timeout_seconds=self._timeout_seconds,
                        extra_environment=desktop_environment,
                        python_executable=confirmed_executable,
                    )
            except subprocess.TimeoutExpired:
                return FolderSelectionResult(
                    status="unavailable",
                    message="目录选择器等待超时，请重试或改用手工绝对路径",
                )
            except (OSError, ValueError) as exc:
                raise JiejianError(
                    ErrorCode.ONBOARDING_SELECTOR_UNAVAILABLE,
                    "系统目录选择器当前不可用，请改用手工绝对路径",
                ) from exc
            if completed.returncode != 0:
                raise JiejianError(
                    ErrorCode.ONBOARDING_SELECTOR_UNAVAILABLE,
                    "系统目录选择器当前不可用，请改用手工绝对路径",
                )
            try:
                payload = json.loads(completed.stdout.strip())
                if not isinstance(payload, dict) or payload.pop("schema_version", None) != "1":
                    raise ValueError("unsupported folder selector result version")
                result = FolderSelectionResult.model_validate(payload)
            except Exception as exc:
                raise JiejianError(
                    ErrorCode.ONBOARDING_SELECTOR_UNAVAILABLE,
                    "系统目录选择器返回无效，请改用手工绝对路径",
                ) from exc
            if (result.status == "selected") != (result.path is not None):
                raise JiejianError(
                    ErrorCode.ONBOARDING_SELECTOR_UNAVAILABLE,
                    "系统目录选择器返回无效，请改用手工绝对路径",
                )
            return result
        finally:
            self._selection_lock.release()


class OnboardingWorkflow:
    """只编排目录选择与受限识别；普通检查由应用理解和权限准备链负责。"""

    def __init__(
        self,
        folder_selector: FolderSelector | None = None,
        *,
        limits: DiscoveryLimits | None = None,
    ) -> None:
        self.folder_selector = folder_selector or SystemFolderSelector()
        self.limits = limits or DiscoveryLimits()

    def select_folder(self) -> FolderSelectionResult:
        return self.folder_selector.select_folder()

    def inspect(self, path: str) -> DiscoveryResult:
        """按冻结预算只读识别目录；不执行候选命令、不联网、不读取源码正文。"""

        return discover_folder(path, limits=self.limits)
