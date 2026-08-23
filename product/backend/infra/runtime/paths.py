# =============================================================================
# 运行目录唯一物理路径
#
# 定位
#   为开发、发布、Worker、Storage 和控制面提供同一套 VarDir 分区。
#
# 职责
#   规范 data/runtime/cache/logs/temp/test 路径｜拒绝旧布局回退｜集中创建安全目录
#
# 边界
#   只定位和创建目录，不决定缓存回收、数据库迁移或业务状态。
#
# 调用链
#   Settings / ApplicationCore / Worker / CLI → RuntimePaths → 各基础设施
# =============================================================================

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class RuntimePaths:
    """当前运行实例的唯一目录布局；所有路径均在同一 VarDir 下。"""

    root: Path

    def __post_init__(self) -> None:
        object.__setattr__(self, "root", self.root.expanduser().resolve())

    @property
    def data(self) -> Path:
        return self.root / "data"

    @property
    def database(self) -> Path:
        return self.data / "jiejian.db"

    @property
    def jobs(self) -> Path:
        return self.data / "jobs"

    @property
    def projects(self) -> Path:
        return self.data / "projects"

    @property
    def reports(self) -> Path:
        return self.data / "reports"

    @property
    def artifact_checks(self) -> Path:
        return self.data / "artifact-checks"

    @property
    def runtime(self) -> Path:
        return self.root / "runtime"

    @property
    def build_runtime(self) -> Path:
        return self.runtime / "build"

    @property
    def frontend_workspace(self) -> Path:
        return self.build_runtime / "frontend-workspace"

    @property
    def frontend_dist(self) -> Path:
        return self.runtime / "frontend"

    @property
    def worker_runtime(self) -> Path:
        return self.runtime / "workers"

    @property
    def python_runtime(self) -> Path:
        return self.runtime / "python"

    @property
    def uv_runtime(self) -> Path:
        return self.runtime / "uv"

    @property
    def playwright_runtime(self) -> Path:
        return self.runtime / "playwright"

    @property
    def release_artifacts(self) -> Path:
        return self.runtime / "release-artifacts"

    @property
    def locks(self) -> Path:
        return self.runtime / "locks"

    @property
    def cache(self) -> Path:
        return self.root / "cache"

    @property
    def uv_cache(self) -> Path:
        return self.cache / "uv"

    @property
    def pnpm_store(self) -> Path:
        return self.cache / "pnpm-store"

    @property
    def npm_cache(self) -> Path:
        return self.cache / "npm"

    @property
    def vite_cache(self) -> Path:
        return self.cache / "vite"

    @property
    def downloads(self) -> Path:
        return self.cache / "downloads"

    @property
    def startup_cache(self) -> Path:
        return self.cache / "startup"

    @property
    def logs(self) -> Path:
        return self.root / "logs"

    @property
    def startup_logs(self) -> Path:
        return self.logs / "startup"

    @property
    def worker_logs(self) -> Path:
        return self.logs / "workers"

    @property
    def runner_logs(self) -> Path:
        return self.logs / "runner"

    @property
    def recording_logs(self) -> Path:
        return self.logs / "recording"

    @property
    def app_logs(self) -> Path:
        return self.logs / "app"

    @property
    def temp(self) -> Path:
        return self.root / "temp"

    @property
    def test(self) -> Path:
        return self.root / "test"

    def ensure_layout(self) -> RuntimePaths:
        """建立目录分区；不创建数据库、运行时或缓存内容。"""

        for path in (
            self.data,
            self.jobs,
            self.projects,
            self.reports,
            self.artifact_checks,
            self.runtime,
            self.build_runtime,
            self.python_runtime,
            self.uv_runtime,
            self.playwright_runtime,
            self.release_artifacts,
            self.worker_runtime,
            self.locks,
            self.cache,
            self.uv_cache,
            self.pnpm_store,
            self.npm_cache,
            self.vite_cache,
            self.downloads,
            self.startup_cache,
            self.logs,
            self.startup_logs,
            self.worker_logs,
            self.runner_logs,
            self.recording_logs,
            self.app_logs,
            self.temp,
            self.test,
        ):
            path.mkdir(parents=True, exist_ok=True)
        return self
