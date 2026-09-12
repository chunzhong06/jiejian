# 从完整性已验证的发布包生成只读结果说明；固定文案与安全结论均不由解释器创造。
from __future__ import annotations

from typing import Literal

from pydantic import Field

from product.backend.core.lifecycle import CaseVerdict, RunVerdict
from product.backend.core.check_repair import CurrentRepairContract, CurrentRepairVerification
from product.backend.core.verification.breakpoints import BreakpointLocator, BreakpointResult
from product.backend.core.verification.checks import CheckDecisionInput, project_check_effect_facts
from product.backend.workflows.checks.story_text import CLAIM_BOUNDARIES, EFFECT_LABELS, EXECUTION_LABELS, JUDGEMENTS
from product.protocols.check_result import CheckObservation, CheckCaseOutcome
from product.protocols.execution_v3 import ChangeContext, FrozenPermission, WireModel


class StoryIdentity(WireModel):
    identity_id: str | None
    label: str | None
    actor_id: str | None
    actor_label: str | None
    verification_status: Literal["PLANNED", "MATCH", "MISMATCH", "UNKNOWN"]
    namespace: str | None = None
    application_subject_id: str | None = None


class StoryEffect(WireModel):
    effect_id: str
    business_label: str
    resource_concept: str
    observed_state: Literal["CONFIRMED", "ABSENT", "UNKNOWN"]
    judgement: str
    evidence_refs: tuple[str, ...]


class StoryControl(WireModel):
    case_id: str
    verdict: CaseVerdict
    evidence_refs: tuple[str, ...]


class FactComparison(WireModel):
    permission_requirement: FrozenPermission
    planned_identity: StoryIdentity
    verified_actual_identity: StoryIdentity
    http_surface: CheckCaseOutcome
    http_explanation: str
    effects: tuple[StoryEffect, ...]
    allow_control: StoryControl | None


class EvidenceExplanation(WireModel):
    source_label: str
    source_location: str
    observed_fact: CheckObservation
    supports_claim: str
    does_not_prove: str
    evidence_refs: tuple[str, ...]


class ActionResultStory(WireModel):
    action_id: str
    action_revision: int = Field(ge=1)
    display_name: str
    case_id: str
    permission: FrozenPermission
    judgement: str
    fact_comparison: FactComparison
    breakpoint: BreakpointResult | None
    decisive_proof_chain: tuple[EvidenceExplanation, ...] = Field(max_length=4)
    evidence_explanations: tuple[EvidenceExplanation, ...]
    claim_boundary: tuple[str, ...]
    repair_requirement: CurrentRepairContract | None = None
    technical_references: tuple[str, ...]


class ResultStory(WireModel):
    run_id: str
    project_id: str
    verdict: RunVerdict
    judgement: str
    policy_epoch: int = Field(ge=0)
    actions: tuple[ActionResultStory, ...]
    claim_boundary: tuple[str, ...]
    technical_references: tuple[str, ...]
    change_context: ChangeContext | None = None
    repair_verification: CurrentRepairVerification | None = None


class CheckStoryBuilder:
    """只消费 Reader 已验证的同 Run 事实；定位和解释不会重算或改写已发布 Verdict。"""

    def __init__(self, reader):
        self._reader = reader
        self.repairs = None

    def build(self, run_id: str, *, include_repair=True) -> ResultStory:
        package = self._reader.package(run_id)
        results = {item.case_id: item for item in package.result.case_results}
        evidence = {item.evidence_id: item for item in package.evidence}
        configs = {item.action_id: item for item in package.bundle.actions}
        identities = {item.identity_id: item for item in package.bundle.identities}
        stories = []
        for action in package.request.actions:
            config = configs[action.action_id]
            proofs = {item.binding_fingerprint: item for item in config.proofs}
            cases = {item.case_id: item for item in action.cases}
            twins = {item.deny_case_id: item for item in action.twins}
            for case in action.cases:
                result = results[case.case_id]
                documents = tuple(evidence[ref] for ref in result.evidence_ids)
                observations = tuple(item for document in documents for item in document.observations)
                facts = project_check_effect_facts(case, observations)
                identity = identities[case.subject_test_identity_id]
                planned = StoryIdentity(identity_id=identity.identity_id, label=identity.label,
                    actor_id=identity.actor_id, actor_label=identity.actor_label, verification_status="PLANNED")
                status = result.outcome.actual_identity_status
                verification = identity.verification if status == "MATCH" else None
                actual = planned.model_copy(update=dict(verification_status=status,
                    identity_id=identity.identity_id if verification is not None else None,
                    label=identity.label if verification is not None else None,
                    actor_id=identity.actor_id if verification is not None else None,
                    actor_label=identity.actor_label if verification is not None else None,
                    namespace=verification.namespace if verification is not None else None,
                    application_subject_id=verification.expected_application_subject_id if verification is not None else None))
                control, breakpoint = None, None
                twin = twins.get(case.case_id)
                if twin is not None:
                    allow_result = results[twin.allow_case_id]
                    control = StoryControl(case_id=allow_result.case_id, verdict=allow_result.verdict,
                        evidence_refs=allow_result.evidence_ids)
                    if result.verdict is CaseVerdict.VULNERABLE:
                        allow_docs = tuple(evidence[ref] for ref in allow_result.evidence_ids)
                        allow_case = cases[twin.allow_case_id]
                        allow_facts = project_check_effect_facts(allow_case,
                            tuple(item for document in allow_docs for item in document.observations))
                        namespaces = {source.trace_namespace for proof in config.proofs for source in proof.auxiliary_sources
                                      if source.trace_namespace is not None}
                        breakpoint = BreakpointLocator().locate_current(action=action, twin=twin,
                            allow_facts=_decision_input(allow_case, allow_result, allow_facts, None),
                            deny_facts=_decision_input(case, result, facts, allow_result.verdict),
                            allow_trace=_single_trace(allow_docs), deny_trace=_single_trace(documents),
                            identities=package.bundle.identities, trace_namespace=next(iter(namespaces)) if len(namespaces) == 1 else None,
                            allow_evidence_refs=allow_result.evidence_ids, deny_evidence_refs=result.evidence_ids)
                requirements = {proof.proof_fingerprint: proof for proof in case.proof_requirements}
                explanations, decisive = [], []
                for document in documents:
                    for item in document.observations:
                        proof = proofs[requirements[item.proof_fingerprint].binding_fingerprint]
                        source = next((source for source in proof.auxiliary_sources if source.observer_id == item.observer_id), proof)
                        trusted = item.complete and item.reliable and item.correlated and item.authoritative
                        support = (EFFECT_LABELS[item.state] if item.level == "VERDICT_REQUIRED" and trusted
                            and (item.state != "ABSENT" or item.closure == "CLOSED") else CLAIM_BOUNDARIES["supporting"]
                            if item.level != "VERDICT_REQUIRED" else CLAIM_BOUNDARIES["unknown"])
                        explanation = EvidenceExplanation(source_label=source.source_label, source_location=source.source_location,
                            observed_fact=item, supports_claim=support, does_not_prove=CLAIM_BOUNDARIES["scope"]
                            if trusted and item.level == "VERDICT_REQUIRED" else CLAIM_BOUNDARIES["supporting"],
                            evidence_refs=(document.evidence_id,))
                        explanations.append(explanation)
                        # 暂未发现但窗口未闭合只保留在完整来源中，不能提升为决定性证明。
                        if item.level == "VERDICT_REQUIRED" and trusted and item.phase in ("AFTER", "EVENTUAL") and (
                            item.state == "CONFIRMED" or (item.state == "ABSENT" and item.closure == "CLOSED")
                        ):
                            decisive.append(explanation)
                effects = []
                for fact in facts:
                    proof = proofs[requirements[fact.proof_fingerprint].binding_fingerprint]
                    effects.append(StoryEffect(effect_id=fact.effect_id, business_label=proof.business_label,
                        resource_concept=proof.resource_concept, observed_state=fact.state,
                        judgement=CLAIM_BOUNDARIES["unknown"] if fact.state == "ABSENT" and fact.closure != "CLOSED"
                        else EFFECT_LABELS[fact.state], evidence_refs=tuple(document.evidence_id for document in documents
                            if any(item.proof_fingerprint == fact.proof_fingerprint for item in document.observations))))
                judgement = JUDGEMENTS[{CaseVerdict.SAFE: "PASS", CaseVerdict.VULNERABLE: "BLOCK"}.get(result.verdict, "INCONCLUSIVE")]
                stories.append(ActionResultStory(action_id=action.action_id, action_revision=action.action_revision,
                    display_name=config.display_name, case_id=case.case_id, permission=case.permission, judgement=judgement,
                    fact_comparison=FactComparison(permission_requirement=case.permission, planned_identity=planned,
                        verified_actual_identity=actual, http_surface=result.outcome,
                        http_explanation=EXECUTION_LABELS[result.outcome.execution_outcome], effects=tuple(effects), allow_control=control),
                    breakpoint=breakpoint, decisive_proof_chain=tuple(decisive[:4]), evidence_explanations=tuple(explanations),
                    claim_boundary=tuple(CLAIM_BOUNDARIES[key] for key in ("execution", "identity", "scope", "immutable")),
                    technical_references=(case.case_id, *result.evidence_ids)))
        verification = None
        if include_repair and self.repairs is not None:
            contracts = {item.source_case_id:item for item in self.repairs.contracts(run_id)}
            stories = [item.model_copy(update={"repair_requirement":contracts.get(item.case_id)}) for item in stories]
            verification = self.repairs.verification(run_id)
        return ResultStory(run_id=run_id, project_id=package.request.project_id, verdict=package.result.verdict,
            judgement=JUDGEMENTS[package.result.verdict.value], policy_epoch=package.request.policy_epoch,
            actions=tuple(stories), claim_boundary=(CLAIM_BOUNDARIES["scope"], CLAIM_BOUNDARIES["immutable"]),
            technical_references=(package.result.request_hash, package.result.config_hash, package.manifest.result_hash),
            change_context=package.request.change_context,repair_verification=verification)


def _decision_input(case, result, facts, control):
    outcome = result.outcome
    return CheckDecisionInput(case=case, execution=outcome.execution_outcome, actual_identity=outcome.actual_identity_status,
        run_correlated=outcome.run_correlated, resource_correlated=outcome.resource_correlated,
        baseline_trusted=outcome.baseline_trusted, recovery_verified=outcome.recovery_verified,
        allow_control_verdict=control, effects=facts)


def _single_trace(documents):
    traces = tuple(document.trace for document in documents if document.trace is not None)
    # 多份不相等 Trace 不拼接因果；保持违规事实并降低定位精度。
    return traces[0] if traces and all(trace == traces[0] for trace in traces) else None
