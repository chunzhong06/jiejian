# 重验当前请求与冻结运行配置的完整关联；Worker/Runner/发布器共用，禁止拼接不同快照。
from __future__ import annotations

import hashlib

from product.backend.core.errors import ErrorCode, JiejianError
from product.protocols.check_result import CheckRunnerInput
from product.protocols.check_runtime import CheckRuntimeBundle, check_runtime_fingerprint
from product.protocols.execution_v3 import PersistedExecutionRequestV3, canonical_execution_request_v3_bytes


def check_publication_budget_reason(actions, bundle) -> str | None:
    """提交前为固定单 Case 结果及主/辅助观察预留空间，避免执行后才发现发布上限。"""
    count = sum(len(action.cases) for action in actions)
    # 结果根上限 1 MiB；每 Case 预留 4 KiB，涵盖全部原因码与唯一 Evidence 引用。
    if count > bundle.budget.max_cases or count * 4096 + 8192 > 1_048_576:
        return "CHECK_CASE_BUDGET_EXCEEDED"
    configured = {action.action_id: action for action in bundle.actions}
    for action in actions:
        if action.action_id not in configured:
            continue
        proofs = {proof.binding_fingerprint: proof for proof in configured[action.action_id].proofs}
        for case in action.cases:
            # 主来源至多五个阶段；每个辅助来源至多 baseline/after/eventual。
            observations = sum(5 + 3 * len(proofs[item.binding_fingerprint].auxiliary_sources)
                for item in case.proof_requirements if item.binding_fingerprint in proofs)
            if observations > 240:
                return "CHECK_EVIDENCE_BUDGET_EXCEEDED"
    return None


def validate_check_inputs(request: PersistedExecutionRequestV3, bundle: CheckRuntimeBundle,
                          runner_input: CheckRunnerInput | None = None) -> None:
    """在任何目标 I/O 前检查全计划关联；不从数据库或当前配置补齐缺少的事实。"""
    try:
        config_hash = check_runtime_fingerprint(bundle)
        request_hash = hashlib.sha256(canonical_execution_request_v3_bytes(request)).hexdigest()
        if (request.project_id, request.source_fingerprint, request.config_fingerprint, request.budget_fingerprint) != (
            bundle.project_id, bundle.source_fingerprint, config_hash, bundle.budget.fingerprint()
        ):
            raise ValueError("request runtime association")
        if runner_input is not None and (runner_input.request_hash, runner_input.config_hash) != (request_hash, config_hash):
            raise ValueError("input asset association")
        actions = {item.action_id: item for item in bundle.actions}
        if set(actions) != {item.action_id for item in request.actions}:
            raise ValueError("runtime action coverage")
        identities = {item.identity_id: item for item in bundle.identities}
        if check_publication_budget_reason(request.actions, bundle) is not None:
            raise ValueError("case budget exceeded")
        for action in request.actions:
            configured = actions[action.action_id]
            if (configured.action_revision, configured.action_semantic_fingerprint) != (
                action.action_revision, action.action_semantic_fingerprint
            ):
                raise ValueError("runtime action revision")
            proofs = {item.binding_fingerprint: item for item in configured.proofs}
            if set(proofs) != {item.binding_fingerprint for case in action.cases for item in case.proof_requirements}:
                raise ValueError("runtime proof coverage")
            for case in action.cases:
                if (case.execution.flow_id, case.execution.flow_sha256, case.execution.execution_binding_fingerprint) != (
                    configured.flow_id, configured.flow_sha256, configured.execution_binding_fingerprint
                ):
                    raise ValueError("runtime execution asset")
                for identity_id, actor, revision, fingerprint in (
                    (case.subject_test_identity_id, case.subject_actor_id, case.subject_actor_revision, case.subject_identity_fingerprint),
                    (case.resource_owner_test_identity_id, case.resource_owner_actor_id, case.resource_owner_actor_revision, case.owner_identity_fingerprint),
                ):
                    identity = identities.get(identity_id)
                    if identity is None or (identity.actor_id, identity.actor_revision, identity.identity_fingerprint) != (actor, revision, fingerprint):
                        raise ValueError("runtime identity association")
                if (case.recovery is None) != (configured.recovery is None) or (
                    case.recovery is not None and case.recovery.binding_fingerprint != configured.recovery.binding_fingerprint
                ):
                    raise ValueError("runtime recovery association")
                for proof in case.proof_requirements:
                    runtime_proof = proofs[proof.binding_fingerprint]
                    if (runtime_proof.effect_id, runtime_proof.rule) != (proof.effect_id, proof.rule):
                        raise ValueError("runtime proof association")
                    if proof.rule == "REGISTERED_EFFECT" and (
                        runtime_proof.observer_id, runtime_proof.descriptor_fingerprint
                    ) != (proof.reference.observer_id, proof.reference.descriptor_fingerprint):
                        raise ValueError("runtime descriptor association")
    except (ValueError, TypeError, AttributeError, KeyError):
        raise JiejianError(ErrorCode.RUNNER_PROTOCOL_INVALID, "执行快照格式无效") from None


def validate_check_decisions(package) -> None:
    """仅 Worker 发布时重验唯一纯规则；GET reader 不调用此入口。"""
    from product.backend.core.verification.checks import (
        CheckDecisionInput, aggregate_check_verdict, evaluate_check_case, project_check_effect_facts,
    )
    results = {item.case_id: item for item in package.result.case_results}
    by_evidence = {item.evidence_id: item for item in package.evidence}
    verdicts = []
    for action in package.request.actions:
        controls = {item.deny_case_id: item.allow_case_id for item in action.twins}
        for case in action.cases:
            result = results[case.case_id]
            outcome = result.outcome
            observations = tuple(observation for reference in result.evidence_ids
                for observation in by_evidence[reference].observations)
            control = controls.get(case.case_id)
            decision = evaluate_check_case(CheckDecisionInput(case=case, execution=outcome.execution_outcome,
                actual_identity=outcome.actual_identity_status, run_correlated=outcome.run_correlated,
                resource_correlated=outcome.resource_correlated, baseline_trusted=outcome.baseline_trusted,
                recovery_verified=outcome.recovery_verified,
                allow_control_verdict=None if control is None else results[control].verdict,
                effects=project_check_effect_facts(case, observations)))
            if decision.verdict is not result.verdict:
                raise JiejianError(ErrorCode.ARTIFACT_MANIFEST, "工件内容校验失败")
            verdicts.append(decision.verdict)
    if package.result.verdict is not aggregate_check_verdict(tuple(verdicts), planned_case_count=len(results)):
        raise JiejianError(ErrorCode.ARTIFACT_MANIFEST, "工件内容校验失败")
