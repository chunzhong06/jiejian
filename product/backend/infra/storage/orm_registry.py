# Storage ORM 映射的唯一显式登记边界，不承担查询、连接或事务职责。

from __future__ import annotations

from importlib import import_module


_STORAGE_ORM_MODULES = (
    "product.backend.infra.storage.preparation.proof_sources",
    "product.backend.infra.storage.runtime.runtime_loads",
    "product.backend.infra.storage.boundaries.rule_candidates",
    "product.backend.infra.storage.changes.development",
    "product.backend.infra.storage.preparation.preparation_recovery",
    "product.backend.infra.storage.runtime.sample_workspaces",
    "product.backend.infra.storage.preparation.supplemental_materials",
    "product.backend.infra.storage.changes.code_observations",
    "product.backend.infra.storage.runtime.environment_operations",
    "product.backend.infra.storage.applications.application_understanding",
    "product.backend.infra.storage.boundaries.business_boundaries",
    "product.backend.infra.storage.preparation.action_preparation",
    "product.backend.infra.storage.boundaries.contracts",
    "product.backend.infra.storage.execution.jobs",
    "product.backend.infra.storage.execution.runs",
    "product.backend.infra.storage.execution.profiles",
    "product.backend.infra.storage.settings.llm",
    "product.backend.infra.storage.applications.projects",
    "product.backend.infra.storage.preparation.recordings",
    "product.backend.infra.storage.results.evidence",
    "product.backend.infra.storage.results.check_publications",
    "product.backend.infra.storage.results.finalizations",
    "product.backend.infra.storage.results.findings",
    "product.backend.infra.storage.results.gating",
    "product.backend.infra.storage.boundaries.permission_intents",
    "product.backend.infra.storage.preparation.test_identities",
    "product.backend.infra.storage.changes.source_changes",
)


def load_storage_orm_mappings() -> None:
    """幂等加载全部签入的 Row-bearing 模块，使 Base.metadata 完整可用。"""

    for module in _STORAGE_ORM_MODULES:
        import_module(module)


__all__ = ["load_storage_orm_mappings"]
