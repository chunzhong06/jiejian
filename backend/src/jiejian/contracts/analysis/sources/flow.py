# =============================================================================
# Flow Contract 来源适配
#
# 定位
#   已确认 Recording Flow 到不可信 Contract Candidate 的确定性转换器
#
# 职责
#   提取步骤观察点｜生成稳定规则 ID｜保留 Flow 来源摘要
#
# 调用链
#   ContractAnalysisService → build_flow_candidates → CandidateBatch
# =============================================================================

from __future__ import annotations

from ....verification.models import ContractRule, Flow, RuleKind
from ...models import ContractCandidate, ContractSourceType
from ..models import CandidateBatch
from ..canonical import _candidate, _rule_id, canonical_sha256


def build_flow_candidates(project_id: str, flow: Flow) -> CandidateBatch:
    """从已编译 Flow 生成可重复候选；确认编译属于 Application 边界。"""

    if not isinstance(flow, Flow):
        raise TypeError("domain flow candidate builder requires a compiled Flow")
    flow_hash = canonical_sha256(flow)
    candidates: list[ContractCandidate] = []
    for step in flow.steps:
        if step.method == "GET":
            candidates.append(
                _candidate(
                    project_id,
                    ContractSourceType.RECORDING_FLOW,
                    f"flow:{flow.id}/step:{step.id}",
                    flow_hash,
                    ContractRule(
                        schema_version="1",
                        id=_rule_id("flow", step.id, "foreign-read"),
                        kind=RuleKind.FOREIGN_READ,
                        required_observers=("http",),
                        severity="high",
                    ),
                )
            )
        else:
            candidates.append(
                _candidate(
                    project_id,
                    ContractSourceType.RECORDING_FLOW,
                    f"flow:{flow.id}/step:{step.id}",
                    flow_hash,
                    ContractRule(
                        schema_version="1",
                        id=_rule_id("flow", step.id, "unauthorized-side-effect"),
                        kind=RuleKind.UNAUTHORIZED_SIDE_EFFECT,
                        required_observers=("http", "owner_api"),
                        severity="critical",
                    ),
                )
            )
        if step.sensitive_fields:
            candidates.append(
                _candidate(
                    project_id,
                    ContractSourceType.RECORDING_FLOW,
                    f"flow:{flow.id}/step:{step.id}/fields:{','.join(sorted(step.sensitive_fields))}",
                    flow_hash,
                    ContractRule(
                        schema_version="1",
                        id=_rule_id("flow", step.id, "privileged-field"),
                        kind=RuleKind.PRIVILEGED_FIELD,
                        required_observers=("http", "owner_api"),
                        severity="critical",
                    ),
                )
            )
    return CandidateBatch(
        adapter="recording_flow_v1",
        candidates=tuple(sorted(candidates, key=lambda item: item.candidate_id)),
        input_sha256=flow_hash,
    )
