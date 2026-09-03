# Backend 当前公共入口只急切加载 1.1.0 控制面；延期 Worker 容器从其模块显式导入。

from .application import ApplicationCore

__all__ = ["ApplicationCore"]
