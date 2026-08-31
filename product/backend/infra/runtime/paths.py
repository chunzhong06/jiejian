# =============================================================================
# 运行目录唯一物理路径
#
# 定位
#   为产品实例、Worker、Storage 和控制面提供同一套 VarDir 分区。
#
# 职责
#   规范 data/runtime/cache/logs/temp/test 路径｜拒绝旧布局回退｜集中创建安全目录
#
# 边界
#   只定位和创建当前实例目录；共享开发资产固定在仓库 var/development，不进入本对象。
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
    def frontend_dist(self) -> Path:
        return self.runtime / "frontend"

    @property
    def worker_runtime(self) -> Path:
        return self.runtime / "workers"

    @property
    def identity_preparations(self) -> Path:
        return self.runtime / "identity-preparations"

    @property
    def official_sample_runtime(self) -> Path:
        return self.runtime / "official-samples"

    @property
    def python_runtime(self) -> Path:
        return self.runtime / "python"

    @property
    def locks(self) -> Path:
        return self.runtime / "locks"

    @property
    def cache(self) -> Path:
        return self.root / "cache"

    @property
    def assistant_cache(self) -> Path:
        return self.cache / "assistant"

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
    def identity_preparation_logs(self) -> Path:
        return self.logs / "identity-preparations"

    @property
    def app_logs(self) -> Path:
        return self.logs / "app"

    @property
    def official_sample_logs(self) -> Path:
        return self.logs / "official-samples"

    @property
    def audit(self) -> Path:
        return self.root / "audit"

    @property
    def competition_audit(self) -> Path:
        return self.audit / "competition"

    @property
    def temp(self) -> Path:
        return self.root / "temp"

    @property
    def process_gates(self) -> Path:
        """子进程 source receipt 门禁；任何普通清理都不得触碰。"""

        return self.temp / "process-gates"

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
            self.worker_runtime,
            self.identity_preparations,
            self.official_sample_runtime,
            self.locks,
            self.cache,
            self.assistant_cache,
            self.logs,
            self.startup_logs,
            self.worker_logs,
            self.runner_logs,
            self.recording_logs,
            self.identity_preparation_logs,
            self.app_logs,
            self.official_sample_logs,
            self.audit,
            self.competition_audit,
            self.temp,
            self.process_gates,
            self.test,
        ):
            path.mkdir(parents=True, exist_ok=True)
        return self
