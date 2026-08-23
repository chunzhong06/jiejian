# 已确认 Recording Flow 到 Contract Candidate 的应用边界适配。

from __future__ import annotations

from product.backend.core.contracts.analysis.canonical import contract_analysis_sha256, _candidate, _rule_id
from product.backend.core.contracts.analysis.models import CandidateBatch
from product.backend.core.contracts.models import CandidateRiskKind, CandidateSuggestion, ContractCandidate, ContractSourceType
from product.protocols.recording_flow import Flow


def build_flow_candidates(project_id: str, flow: Flow) -> CandidateBatch:
    """从已确认 Flow 生成可重复候选；Flow 不进入 Verification Core。"""

    if not isinstance(flow, Flow):
        raise TypeError("flow candidate builder requires a compiled Flow")
    flow_hash = contract_analysis_sha256(flow)
    candidates: list[ContractCandidate] = []
    for step in flow.steps:
        if step.request_template.method == "GET":
            candidates.append(
                _candidate(
                    project_id,
                    ContractSourceType.RECORDED_WEB,
                    f"flow:{flow.id}/step:{step.id}",
                    flow_hash,
                    CandidateSuggestion(
                        id=_rule_id("flow", step.id, "foreign-read"),
                        kind=CandidateRiskKind.FOREIGN_READ,
                        required_observations=("resource_state",),
                        severity="high",
                    ),
                )
            )
        else:
            candidates.append(
                _candidate(
                    project_id,
                    ContractSourceType.RECORDED_WEB,
                    f"flow:{flow.id}/step:{step.id}",
                    flow_hash,
                    CandidateSuggestion(
                        id=_rule_id("flow", step.id, "unauthorized-side-effect"),
                        kind=CandidateRiskKind.UNAUTHORIZED_SIDE_EFFECT,
                        required_observations=("resource_state",),
                        severity="critical",
                    ),
                )
            )
        if step.sensitive_fields:
            candidates.append(
                _candidate(
                    project_id,
                    ContractSourceType.RECORDED_WEB,
                    f"flow:{flow.id}/step:{step.id}/fields:{','.join(sorted(step.sensitive_fields))}",
                    flow_hash,
                    CandidateSuggestion(
                        id=_rule_id("flow", step.id, "privileged-field"),
                        kind=CandidateRiskKind.PRIVILEGED_FIELD,
                        required_observations=("resource_state",),
                        severity="critical",
                    ),
                )
            )
    return CandidateBatch(
        adapter="recording_flow",
        candidates=tuple(sorted(candidates, key=lambda item: item.candidate_id)),
        input_sha256=flow_hash,
    )


__all__ = ["build_flow_candidates"]
