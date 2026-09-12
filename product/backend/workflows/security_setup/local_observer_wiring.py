# 旧准备入口复用当前六来源描述读取器，不维护另一份解析规则。
from product.backend.workflows.checks.local_observer_wiring import LocalObserverWiring, load_local_observer_wiring

__all__ = ["LocalObserverWiring", "load_local_observer_wiring"]
