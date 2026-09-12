# 串行执行冻结 CHECK：完整 ALLOW 先行、每 Case 单次 TARGET、独立观察与精确资源恢复。
from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path

from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.core.lifecycle import CaseVerdict, RunLifecycle
from product.backend.core.verification.checks import (CheckDecisionInput, aggregate_check_verdict,
    evaluate_check_case, project_check_effect_facts)
from product.backend.infra.artifacts.check_validation import validate_check_inputs
from product.backend.infra.execution.web.check_runtime import CheckWebRuntime
from product.backend.infra.observers.check_runtime import CheckObserverRuntime
from product.protocols.check_result import (CheckCaseOutcome, CheckCaseResult, CheckEvidence,
    CheckPrimaryError, CheckRunnerInput, CheckRunnerResult, seal_check_evidence)


@dataclass(frozen=True)
class CheckExecutionOutput:
    result: CheckRunnerResult
    evidence: tuple[CheckEvidence, ...]


class CheckExecutor:
    """唯一真实检查编排入口；冻结预算限制会话，判定仍全部委托 core 纯规则。"""

    def __init__(self, request, bundle, runner_input: CheckRunnerInput, *, environ,
                 attempt_dir: Path, cancellation_requested, clock_us=None, reserved_origins=(), progress=None):
        validate_check_inputs(request, bundle, runner_input)
        self.request, self.bundle, self.input = request, bundle, runner_input
        self.clock = clock_us or (lambda: time.time_ns() // 1000)
        self.cancelled = cancellation_requested
        self.progress = progress or (lambda _phase, _completed, _planned: None)
        self.web = CheckWebRuntime(bundle, environ=environ, cancellation_requested=cancellation_requested,
            reserved_origins=reserved_origins, request_scope=(runner_input.run_id, runner_input.job_id, runner_input.attempt))
        self.observers = CheckObserverRuntime(bundle, self.web, environ=environ, attempt_dir=attempt_dir,
            cancellation_requested=cancellation_requested, clock_us=self.clock)
        self._baselines = {}
        self._cleanup_issues = []
        self._first_error = None
        self._stopped = None

    def execute(self) -> CheckExecutionOutput:
        started = self.clock()
        results, evidence = {}, []
        configured = {item.action_id: item for item in self.bundle.actions}
        cases = [(action, case) for action in self.request.actions for case in action.cases]
        # A1 去重后的 Case 是唯一执行单位；双角色合一执行一次，superset 控制和完整回归仍各自运行。
        cases.sort(key=lambda pair: (pair[1].permission.expectation == "DENY", pair[0].action_id, pair[1].case_id))
        self.progress("PREPARING", 0, len(cases))
        try:
            for action, case in cases:
                self.progress("EXECUTING", len(results), len(cases))
                if self.cancelled() and self._stopped is None:
                    self._stop("EXEC_CANCELLED", "EXECUTION")
                if self.clock() - started >= self.bundle.budget.max_duration_us and self._stopped is None:
                    self._stop("EXEC_TIMEOUT", "EXECUTION")
                control = next((twin.allow_case_id for twin in action.twins if twin.deny_case_id == case.case_id), None)
                allow_verdict = results[control].verdict if control in results else None
                result, document = self._case(action, configured[action.action_id], case, allow_verdict)
                results[case.case_id] = result
                evidence.append(document)
        finally:
            self.web.close()
        ordered = tuple(results[case.case_id] for action in self.request.actions for case in action.cases)
        self.progress("FINALIZING", len(results), len(cases))
        verdict = aggregate_check_verdict(tuple(item.verdict for item in ordered), planned_case_count=len(cases))
        blocked = any(item.verdict is CaseVerdict.VULNERABLE for item in ordered)
        cancelled = self._stopped == "EXEC_CANCELLED" and not blocked
        result_type = "CANCELLED" if cancelled else "SAFETY_STOPPED" if self._stopped else "SUCCESS"
        lifecycle = RunLifecycle.CANCELLED if cancelled else RunLifecycle.SAFETY_STOPPED if self._stopped else RunLifecycle.COMPLETED
        return CheckExecutionOutput(CheckRunnerResult(run_id=self.input.run_id, job_id=self.input.job_id,
            attempt=self.input.attempt, lease_owner=self.input.lease_owner, fencing_token=self.input.fencing_token,
            request_hash=self.input.request_hash, config_hash=self.input.config_hash,
            result_type=result_type, lifecycle=lifecycle, case_results=ordered, verdict=None if cancelled else verdict,
            primary_error=self._first_error, cleanup_issues=tuple(dict.fromkeys(self._cleanup_issues)),
            started_at_us=started, completed_at_us=self.clock()), tuple(evidence))

    def _case(self, action, configured, case, allow_verdict):
        execution, status, identity = "UNKNOWN", None, "UNKNOWN"
        baseline, recovered, correlated = False, not configured.state_changing, False
        observations = []
        if self._stopped is None:
            try:
                before = self._observe(configured, case, "BASELINE", baseline=False)
                observations.extend(item.observation for item in before)
                observations.extend(item.observation for item in self._observe_auxiliary(configured, case, "BASELINE"))
                projections = tuple(item.baseline_projection for item in before)
                baseline = all(item is not None for item in projections)
                key = (action.action_id, case.resource_id, tuple(proof.binding_fingerprint for proof in case.proof_requirements))
                original = self._baselines.get(key)
                reset_first = configured.state_changing and (not baseline or (original is not None and original != projections)
                    or self._creation_exists(configured, before))
                if reset_first:
                    self._recover_request(configured, case)
                    self.observers.restart_case_baseline(case.case_id)
                    restored = self._observe(configured, case, "BEFORE", baseline=False, cleanup=True)
                    observations.extend(item.observation for item in restored)
                    projections = tuple(item.baseline_projection for item in restored)
                    baseline = all(item is not None for item in projections) and not self._creation_exists(configured, restored)
                    baseline = baseline and (original is None or projections == original)
                    # 恢复复核完成后重新采集正式 BEFORE，使投影历史只含恢复后的窗口。
                    if baseline:
                        self.observers.restart_case_baseline(case.case_id)
                        before = self._observe(configured, case, "BEFORE", baseline=True)
                        observations = [item for item in observations if item.phase != "BEFORE"]
                        observations.extend(item.observation for item in before)
                        baseline = tuple(item.baseline_projection for item in before) == projections
                if baseline and original is None:
                    self._baselines[key] = projections
                    original = projections
                if original is not None and projections != original:
                    baseline = False
                if not baseline:
                    self._stop("BASELINE_INTEGRITY_INVALID", "BASELINE")
                else:
                    execution_fact, response, identity = self.web.execute_flow(configured, case, verify_identity=True)
                    execution, status = execution_fact.outcome.value, response.status_code
                    after = (*self._observe(configured, case, "AFTER", baseline=True),
                        *self._observe_auxiliary(configured, case, "AFTER"))
                    observations.extend(item.observation for item in after)
                    eventual = (*self._observe(configured, case, "EVENTUAL", baseline=True),
                        *self._observe_auxiliary(configured, case, "EVENTUAL"))
                    observations.extend(item.observation for item in eventual)
                    if status == 202:
                        completed = self._trusted_terminal_completion(configured, case, identity, eventual)
                        execution = configured.steps[-1].classifier.classify(response, terminal_completed=completed).value
                    correlated = any(item.observation.correlated for item in (*after, *eventual))
            except JiejianError as exc:
                identity = self.web.actual_identity_status(case.case_id)
                execution = "UNKNOWN"
                self._stop(exc.code, "EXECUTION")
                # 传输失败也可能已经产生业务效果；仍用本 Case 的合法观察来源采证。
                if self.web.target_attempted(case.case_id):
                    after = (*self._observe(configured, case, "AFTER", baseline=baseline, cleanup=True),
                        *self._observe_auxiliary(configured, case, "AFTER", cleanup=True))
                    observations.extend(item.observation for item in after)
                    correlated = any(item.observation.correlated for item in after)
            finally:
                if configured.state_changing and self.web.target_attempted(case.case_id):
                    try:
                        self._recover_request(configured, case)
                        restored = self._observe(configured, case, "RECOVERY", baseline=baseline, cleanup=True)
                        observations.extend(item.observation for item in restored)
                        recovered = baseline and tuple(item.baseline_projection for item in restored) == self._baselines.get(key)
                    except JiejianError:
                        recovered = False
                    if not recovered:
                        self._cleanup_issues.append("RECOVERY_UNVERIFIED")
                        self._stop("RECOVERY_UNVERIFIED", "RECOVERY")
        unique_observations = {}
        for item in observations:
            observation_key = (item.proof_fingerprint, item.observer_id, item.phase)
            prior = unique_observations.get(observation_key)
            if prior is None or prior.state != "CONFIRMED":
                unique_observations[observation_key] = item
        observations = tuple(unique_observations.values())
        outcome = CheckCaseOutcome(execution_outcome=execution, http_status=status,
            actual_identity_status=identity, baseline_trusted=baseline, recovery_verified=recovered,
            run_correlated=correlated, resource_correlated=correlated)
        decision = evaluate_check_case(CheckDecisionInput(case=case, execution=execution, actual_identity=identity,
            run_correlated=correlated, resource_correlated=correlated, baseline_trusted=baseline,
            recovery_verified=recovered, allow_control_verdict=allow_verdict,
            effects=project_check_effect_facts(case, observations)))
        document = seal_check_evidence(run_id=self.input.run_id, job_id=self.input.job_id,
            attempt=self.input.attempt, action_id=action.action_id, action_revision=action.action_revision,
            request_hash=self.input.request_hash, config_hash=self.input.config_hash, case=case,
            outcome=outcome, observations=tuple(observations), trace=self.observers.trace(configured, case))
        result = CheckCaseResult(case_id=case.case_id, action_id=action.action_id, verdict=decision.verdict,
            reason_codes=decision.reason_codes, evidence_ids=(document.evidence_id,), outcome=outcome)
        return result, document

    def _trusted_terminal_completion(self, action, case, identity, eventual):
        """只接受冻结绑定对应的本 Case 终态；失配或冲突不能被任意一个 True 覆盖。"""
        binding = action.steps[-1].classifier.completion_binding
        if identity != "MATCH" or binding is None:
            return False
        participating = {proof.binding_fingerprint for proof in action.proofs
            if proof.rule == "REGISTERED_EFFECT" and any(source.observer_id == binding for source in proof.auxiliary_sources)}
        requirements = {proof.proof_fingerprint: proof for proof in case.proof_requirements
                        if proof.binding_fingerprint in participating}
        matches = tuple(item for item in eventual if item.observation.observer_id == binding)
        if not matches:
            return False
        marker = self.web.request_marker(case.case_id)
        for item in matches:
            observation = item.observation
            requirement = requirements.get(observation.proof_fingerprint)
            if (requirement is None or not item.execution_completed or observation.phase != "EVENTUAL"
                    or observation.effect_id != requirement.effect_id
                    or item.completion_case_id != case.case_id or item.completion_resource_id != case.resource_id
                    or item.completion_binding_fingerprint != requirement.binding_fingerprint
                    or not {case.case_id, marker} <= set(observation.correlation_refs)):
                return False
        return True

    def _observe(self, action, case, phase, *, baseline, cleanup=False):
        sources = {item.binding_fingerprint: item for item in action.proofs}
        observed = []
        for requirement in case.proof_requirements:
            proof = sources[requirement.binding_fingerprint]
            if phase == "EVENTUAL" and (proof.observer_id is None or not any(
                item.value == "EVENTUAL" for item in self.observers.specs[proof.observer_id].phases)):
                continue
            observed.append(self.observers.observe(case=case, action_id=action.action_id,
                requirement=requirement, proof=proof, phase=phase, baseline_trusted=baseline, cleanup=cleanup))
        return tuple(observed)

    def _observe_auxiliary(self, action, case, phase, *, cleanup=False):
        requirements = {item.binding_fingerprint: item for item in case.proof_requirements}
        observed = []
        for proof in action.proofs:
            requirement = requirements.get(proof.binding_fingerprint)
            if requirement is None:
                continue
            for source in proof.auxiliary_sources:
                spec = self.observers.specs[source.observer_id]
                if phase == "EVENTUAL" and not any(item.value == "EVENTUAL" for item in spec.phases):
                    continue
                # 沿同一冻结 proof 引用采集低权限材料；辅助来源不能升级为决定性证明。
                auxiliary = proof.model_copy(update=dict(rule="REGISTERED_EFFECT", observer_id=source.observer_id,
                    descriptor_fingerprint=source.descriptor_fingerprint, observation_identity_id=source.observation_identity_id,
                    request=None, source_label=source.source_label, source_location=source.source_location, auxiliary_sources=()))
                observed.append(self.observers.observe(case=case, action_id=action.action_id,
                    requirement=requirement.model_copy(update={"level": source.level, "rule": "REGISTERED_EFFECT"}),
                    proof=auxiliary, phase=phase, baseline_trusted=True, cleanup=cleanup))
        return tuple(observed)

    def _recover_request(self, action, case):
        recovery = action.recovery
        if recovery is None or self.web.verify_identity(recovery.source_subject_identity_id, case, cleanup=True) != "MATCH":
            raise JiejianError(ErrorCode.STATE_PRECONDITION, "准备尚未完成")
        self.web.request(recovery.request, case=case, action_id=action.action_id,
            identity_id=recovery.source_subject_identity_id, cleanup=True)

    @staticmethod
    def _creation_exists(action, observations):
        kinds = {item.effect_id: item.effect_kind for item in action.proofs}
        return any(kinds[item.observation.effect_id] == "OBJECT_CREATION" and item.baseline_projection is not None
            and (item.observation.state == "CONFIRMED" or item.baseline_projection[0] is True)
            for item in observations)

    def _stop(self, code, phase):
        if self._stopped is None:
            self._stopped = code
            self._first_error = CheckPrimaryError(code=code, phase=phase)
