# 官方示例安装和活跃运行的内部事实，秘密不参与公开表示。
from __future__ import annotations

import subprocess
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal
from product.protocols.runtime.runtime_identity import RuntimeLaunchManifest


AuthorizationOrder = Literal[
    "ENQUEUE_BEFORE_AUTHORIZE",
    "AUTHORIZE_BEFORE_ENQUEUE",
]


BlobObservation = Literal["AVAILABLE", "UNAVAILABLE"]


OwnerObservation = Literal["AVAILABLE", "UNAVAILABLE"]


@dataclass(frozen=True, slots=True)
class OfficialSampleInstallation:
    """显式 Sample 根的非秘密可用性事实。"""

    available: bool
    sample_id: str = "collaboration-space"
    display_name: str = "协作空间"
    reason: str | None = None
    root: Path | None = field(default=None, repr=False)
    source: Path | None = field(default=None, repr=False)
    runtime_kind: str = "PYTHON"
    entry: str | None = None
    files: tuple[str, ...] = ()
    entry_module: str | None = None
    health_path: str | None = None


@dataclass(frozen=True, slots=True)
class OfficialSampleRuntime:
    """一个活跃 Sample 的内部运行事实；秘密和进程不得进入公共 DTO。"""

    experience_id: str
    sample_id: str
    display_name: str
    origin: str
    experience_root: Path
    source_root: Path
    runtime_root: Path
    descriptor_path: Path
    control_path: Path
    log_path: Path
    process: subprocess.Popen[Any] = field(repr=False, compare=False)
    secrets: dict[str, str] = field(repr=False, compare=False)
    launch_manifest: RuntimeLaunchManifest | None = None

    @property
    def check_descriptor_path(self) -> Path:
        return self.runtime_root / "check-environment.json"


ProcessLauncher = Callable[..., subprocess.Popen[Any]]
