# 官方 Sample 基础设施出口；只暴露受控安装与本地运行时管理能力。

from product.backend.infra.samples.official import (
    OfficialSampleInstallation,
    OfficialSampleManager,
    OfficialSampleRuntime,
)

__all__ = [
    "OfficialSampleInstallation",
    "OfficialSampleManager",
    "OfficialSampleRuntime",
]
