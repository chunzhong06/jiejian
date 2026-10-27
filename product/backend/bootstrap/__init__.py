# Backend 当前公共入口只急切加载 控制面；延期 Worker 容器从其模块显式导入。

from product.backend.bootstrap.application import ApplicationCore

__all__ = ["ApplicationCore"]
