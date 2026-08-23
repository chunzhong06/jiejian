# =============================================================================
# Runner 结果构造
#
# 定位
#   把通用 CaseResult 聚合为 Evidence 与 attempt 结果所需的纯数据。
#
# 职责
#   构造证据｜归并运行判定｜保持稳定身份计算只依赖通用事实
#
# 边界
#   不访问 Target、Observer Adapter、数据库或 Report；Verdict 只来自既有
#   Verification 调用方。
# =============================================================================

from __future__ import annotations

from collections.abc import Iterable

from product.backend.core.lifecycle import CaseVerdict, RunVerdict
from product.protocols import Evidence, RunnerResultType, build_evidence


def evidence_from_case(document, case_result) -> Evidence:
    """按 CaseResult 的已冻结事实构造内容寻址 Evidence。"""

    return build_evidence(
        schema_version="4",
        run_id=document.run_id,
        case_snapshot=case_result.case,
        twin_snapshot=case_result.twin_snapshot,
        twin_role=case_result.twin_role,
        allow_control_valid=case_result.allow_control_valid,
        baseline_integrity=case_result.baseline_integrity,
        finding_pre_identity=case_result.finding_pre_identity,
        execution_fact=case_result.execution_fact,
        requirement_bindings=case_result.requirement_bindings,
        observation_facts=case_result.observation_facts,
        security_effect_facts=case_result.security_effect_facts,
        observations=case_result.observations,
        outcomes=case_result.outcomes,
        verdict=case_result.verdict,
        reason_codes=case_result.reason_codes,
    )


def run_verdict(evidence: Iterable[Evidence], *, has_gaps: bool) -> RunVerdict:
    """保持既有 Evidence→RunVerdict 归约，不引入第二套判定。"""

    items = tuple(evidence)
    if not items and has_gaps:
        return RunVerdict.INCONCLUSIVE
    if any(item.verdict is CaseVerdict.VULNERABLE for item in items):
        return RunVerdict.BLOCK
    if has_gaps or any(item.verdict is CaseVerdict.INCONCLUSIVE for item in items):
        return RunVerdict.INCONCLUSIVE
    return RunVerdict.PASS
