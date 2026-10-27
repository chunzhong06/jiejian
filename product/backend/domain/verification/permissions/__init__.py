# 权限模型、Contract 与覆盖计划的公开入口。

from importlib import import_module

from product.backend.domain.verification.permissions.contract import (
    NormalizedPermissionCase,
    NormalizedPermissionPlan,
    PermissionContract,
    canonical_json_bytes,
    compile_permission_plan,
    parse_permission_contract,
    permission_model_sha256,
)
from product.backend.domain.verification.permissions.models import (
    ActionDefinition,
    BatchAuthorizationMode,
    BatchPermissionRule,
    BatchResourceExpectation,
    CoverageDimension,
    PermissionContext,
    PermissionExpectation,
    PermissionModel,
    PermissionRule,
    RelationEndpoint,
    RelationFact,
    RelationType,
    ResourceDefinition,
    SecurityEffectDefinition,
    SecurityEffectKind,
    SubjectDefinition,
    WorkflowTransition,
)

_LAZY_EXPORTS = {
    "CoverageGap",
    "CoverageGapCode",
    "CoverageRecord",
    "CoverageStatus",
    "EliminatedCandidate",
    "EliminatedReason",
    "PermissionMutationCase",
    "PermissionMutationPlan",
    "RetentionReason",
    "build_permission_coverage_plan",
}


def __getattr__(name: str):
    """按需加载会反向依赖 Verification differential 的覆盖计划导出。"""

    if name in {
        "CoverageGap",
        "CoverageGapCode",
        "CoverageRecord",
        "CoverageStatus",
        "EliminatedCandidate",
        "EliminatedReason",
        "PermissionMutationCase",
        "PermissionMutationPlan",
        "RetentionReason",
        "build_permission_coverage_plan",
    }:
        module = import_module(".coverage", __name__)
    else:
        raise AttributeError(name)
    value = getattr(module, name)
    globals()[name] = value
    return value


__all__ = [name for name in globals() if not name.startswith("_")] + sorted(_LAZY_EXPORTS)
