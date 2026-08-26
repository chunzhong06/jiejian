# 权限模型、Contract、覆盖计划与单用例评价的正式导出面。

from importlib import import_module

from .contract import (
    NormalizedPermissionCase,
    NormalizedPermissionPlan,
    PermissionContract,
    canonical_json_bytes,
    compile_permission_plan,
    parse_permission_contract,
    permission_model_sha256,
)
from .models import (
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
    "CaseDecisionInput",
    "PermissionEvaluationModel",
    "PermissionEvaluationReasonCode",
    "evaluate_permission_case",
}


def __getattr__(name: str):
    """按需加载会反向依赖 Verification differential 的覆盖/评价导出。"""

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
    elif name in {
        "CaseDecisionInput",
        "PermissionEvaluationModel",
        "PermissionEvaluationReasonCode",
        "evaluate_permission_case",
    }:
        module = import_module(".evaluation", __name__)
    else:
        raise AttributeError(name)
    value = getattr(module, name)
    globals()[name] = value
    return value


__all__ = [name for name in globals() if not name.startswith("_")] + sorted(_LAZY_EXPORTS)
