# Storage ORM 映射的唯一显式登记边界，不承担查询、连接或事务职责。

from __future__ import annotations

from importlib import import_module


_STORAGE_ORM_MODULES = (
    "product.backend.infrastructure.storage.workspace",
    "product.backend.infrastructure.storage.preparation.identity_preparations",
    "product.backend.infrastructure.storage.preparation.batches",
    "product.backend.infrastructure.storage.preparation.proof_artifacts",
    "product.backend.infrastructure.storage.preparation.suggestions",
    "product.backend.infrastructure.storage.preparation.proof_sources",
    "product.backend.infrastructure.storage.runtime.runtime_loads",
    "product.backend.infrastructure.storage.boundaries.rule_candidates",
    "product.backend.infrastructure.storage.changes.development",
    "product.backend.infrastructure.storage.preparation.preparation_recovery",
    "product.backend.infrastructure.storage.runtime.sample_workspaces",
    "product.backend.infrastructure.storage.preparation.supplemental_materials",
    "product.backend.infrastructure.storage.changes.code_observations",
    "product.backend.infrastructure.storage.runtime.environment_operations",
    "product.backend.infrastructure.storage.applications.application_understanding",
    "product.backend.infrastructure.storage.boundaries.business_boundaries",
    "product.backend.infrastructure.storage.preparation.action_preparation",
    "product.backend.infrastructure.storage.execution.jobs",
    "product.backend.infrastructure.storage.execution.runs",
    "product.backend.infrastructure.storage.settings.llm",
    "product.backend.infrastructure.storage.applications.projects",
    "product.backend.infrastructure.storage.preparation.recordings",
    "product.backend.infrastructure.storage.results.evidence",
    "product.backend.infrastructure.storage.results.check_publications",
    "product.backend.infrastructure.storage.results.rule_history",
    "product.backend.infrastructure.storage.boundaries.permission_intents",
    "product.backend.infrastructure.storage.preparation.test_identities",
    "product.backend.infrastructure.storage.changes.source_changes",
)


def load_storage_orm_mappings() -> None:
    """幂等加载全部签入的 Row-bearing 模块，使 Base.metadata 完整可用。"""

    for module in _STORAGE_ORM_MODULES:
        import_module(module)


__all__ = ["load_storage_orm_mappings"]
