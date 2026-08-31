# Storage ORM 映射的唯一显式登记边界，不承担查询、连接或事务职责。

from __future__ import annotations

from importlib import import_module


_STORAGE_ORM_MODULES = (
    "product.backend.infra.storage.application_understanding",
    "product.backend.infra.storage.contracts",
    "product.backend.infra.storage.execution.jobs",
    "product.backend.infra.storage.execution.runs",
    "product.backend.infra.storage.execution_profiles",
    "product.backend.infra.storage.llm",
    "product.backend.infra.storage.projects",
    "product.backend.infra.storage.recordings",
    "product.backend.infra.storage.results.evidence",
    "product.backend.infra.storage.results.finalizations",
    "product.backend.infra.storage.results.findings",
    "product.backend.infra.storage.results.gating",
    "product.backend.infra.storage.setup.permission_intents",
    "product.backend.infra.storage.setup.test_identities",
    "product.backend.infra.storage.setup.test_setup",
    "product.backend.infra.storage.source_changes",
)


def load_storage_orm_mappings() -> None:
    """幂等加载全部签入的 Row-bearing 模块，使 Base.metadata 完整可用。"""

    for module in _STORAGE_ORM_MODULES:
        import_module(module)


__all__ = ["load_storage_orm_mappings"]
