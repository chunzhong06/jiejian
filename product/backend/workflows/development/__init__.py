# 开发任务的稳定应用入口；内部读取与操作辅助由各自模块拥有。
from product.backend.workflows.development.service import DevelopmentService

__all__ = ["DevelopmentService"]
