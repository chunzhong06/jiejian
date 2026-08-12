# =============================================================================
# Verification 快照执行
#
# 定位
#   隔离 Runner 内的安全验证核心，不拥有 Job 生命周期或最终发布事务
#
# 职责
#   构造关系变异计划｜执行受控请求与清理｜聚合 Evidence 和 Verdict
#
# 调用链
#   runner.execution → SnapshotRunExecutor → planning / http / evaluation / artifacts
# =============================================================================

from __future__ import annotations

import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from ..domain.lifecycle import CaseVerdict
from .models import (
    Evidence,
    Flow,
    Identity,
    MutationCase,
    Observation,
    ReasonCode,
    ResourceDefinition,
    RunResult,
    SecurityContract,
    TargetScope,
)
from ..errors import ErrorCode, JiejianError
from ..redaction import redact
from .artifacts import persist_run
from .evaluation import aggregate_verdict, build_evidence, evaluate_case
from .http import HttpExecutor
from .planning import build_mutation_plan
from .safety import TargetGuard

_SAFETY_ERROR_CODES = {
    ErrorCode.SCOPE_URL.value,
    ErrorCode.SCOPE_HOST.value,
    ErrorCode.SCOPE_PORT.value,
    ErrorCode.SCOPE_PRIVATE_NETWORK.value,
    ErrorCode.SCOPE_REDIRECT.value,
    ErrorCode.EXEC_BUDGET.value,
    ErrorCode.EXEC_RESPONSE_TOO_LARGE.value,
}
_INFRASTRUCTURE_ERROR_CODES = {
    ErrorCode.EXEC_REQUEST.value,
    ErrorCode.EXEC_TIMEOUT.value,
    ErrorCode.EXEC_CANCELLED.value,
    ErrorCode.SECRET_MISSING.value,
}


@dataclass(frozen=True, slots=True)
class VerificationSnapshot:
    """路径无关的完整验证输入；Runner 和 YAML 适配器共同构造。"""

    project_id: str
    project_name: str
    target: TargetScope
    identities: tuple[Identity, ...]
    resources: tuple[ResourceDefinition, ...]
    flow: Flow
    contract: SecurityContract
    owner_observer_enabled: bool
    mutation_seed: int

    def to_json_snapshot(self) -> dict[str, object]:
        return {
            "schema_version": "1",
            "project_id": self.project_id,
            "project_name": self.project_name,
            "target": self.target.model_dump(mode="json"),
            "identities": [item.model_dump(mode="json") for item in self.identities],
            "resources": [item.model_dump(mode="json") for item in self.resources],
            "flow": self.flow.model_dump(mode="json"),
            "contract": self.contract.model_dump(mode="json"),
            "owner_observer_enabled": self.owner_observer_enabled,
            "mutation_seed": self.mutation_seed,
        }


class SnapshotRunExecutor:
    """执行一个完整快照并把产物写到调用方指定目录。"""

    def __init__(
        self,
        *,
        environ: Mapping[str, str] | None = None,
        cancellation_requested: Callable[[], bool] | None = None,
        utc_now: Callable[[], datetime] | None = None,
        executor_process_id: int | None = None,
    ) -> None:
        self.environ = os.environ if environ is None else environ
        self.cancellation_requested = cancellation_requested or (lambda: False)
        self.utc_now = utc_now or (lambda: datetime.now(UTC))
        self.executor_process_id = executor_process_id

    def run(
        self,
        snapshot: VerificationSnapshot,
        *,
        run_id: str,
        artifact_dir: Path,
        destination_dir: Path | None = None,
    ) -> RunResult:
        """执行完整快照并把已脱敏结果写入调用方指定的 staging。"""

        # --- 阶段：规划并预留全部清理请求 ---
        plan = build_mutation_plan(
            snapshot.identities,
            snapshot.resources,
            snapshot.flow,
            snapshot.contract,
            seed=snapshot.mutation_seed,
        )
        cleanup_reserve = 2 * len(plan.cases)
        if snapshot.target.max_requests < cleanup_reserve:
            raise JiejianError(
                ErrorCode.EXEC_BUDGET,
                "HTTP 请求预算不足以预留全部清理请求",
                details={"required_cleanup_requests": cleanup_reserve},
            )
        started_at = self.utc_now()
        guard = TargetGuard(snapshot.target)
        guard.authorize_url(snapshot.target.base_url)
        known_secrets = tuple(self._secret(identity) for identity in snapshot.identities)
        executor = HttpExecutor(
            guard,
            cleanup_reserve=cleanup_reserve,
            known_secrets=known_secrets,
            cancellation_requested=self.cancellation_requested,
            executor_process_id=self.executor_process_id,
        )
        evidence: list[Evidence] = []
        try:
            # --- 阶段：执行变异并形成多面观察 ---
            for case in plan.cases:
                item = self._run_case(executor, snapshot, case, run_id=run_id)
                evidence.append(item)
                if ReasonCode.CLEANUP_FAILED.value in item.reason_codes:
                    break
        finally:
            executor.close()

        # --- 阶段：聚合结论并写入 staging 工件 ---
        evidence_tuple = tuple(evidence)
        verdict = aggregate_verdict(evidence_tuple)
        reason_codes = tuple(
            dict.fromkeys(code for item in evidence_tuple for code in item.reason_codes)
        )
        result = RunResult(
            run_id=run_id,
            project_id=snapshot.project_id,
            engine_version=plan.engine_version,
            verdict=verdict,
            reason_codes=reason_codes,
            evidence=evidence_tuple,
            artifact_dir=str(artifact_dir),
        )
        persist_run(
            result,
            plan.model_dump(mode="json"),
            project_snapshot=snapshot.to_json_snapshot(),
            target_snapshot=snapshot.target,
            contract=snapshot.contract,
            mutation_seed=snapshot.mutation_seed,
            started_at=started_at,
            finished_at=self.utc_now(),
            destination_dir=destination_dir,
        )
        return result

    def _run_case(
        self,
        executor: HttpExecutor,
        snapshot: VerificationSnapshot,
        case: MutationCase,
        *,
        run_id: str,
    ) -> Evidence:
        identities = {identity.id: identity for identity in snapshot.identities}
        resource_owners = {
            resource.id: resource.owner_identity_id for resource in snapshot.resources
        }
        steps = {step.id: step for step in snapshot.flow.steps}
        rules = {rule.id: rule for rule in snapshot.contract.rules}
        step = steps[case.step_id]
        rule = rules[case.rule_id]
        observations: list[Observation] = []
        verdict = CaseVerdict.INCONCLUSIVE
        reason_codes: tuple[str, ...] = ()
        phase = "cleanup"
        infrastructure_failure = False

        try:
            self._cleanup(executor, snapshot, case.case_id)
            if self.cancellation_requested():
                raise JiejianError(ErrorCode.EXEC_CANCELLED, "运行已请求取消")
            phase = "baseline"
            if "owner_api" in rule.required_observers and not snapshot.owner_observer_enabled:
                reason_codes = (ReasonCode.REQUIRED_OBSERVER_MISSING.value,)
            else:
                initial_state = None
                if "owner_api" in rule.required_observers:
                    initial_state = self._observe_owner(
                        executor,
                        snapshot,
                        resource_id=step.resource_id,
                        owner_identity_id=resource_owners[step.resource_id],
                        identities=identities,
                        case_id=case.case_id,
                        phase="initial",
                    )
                    observations.append(initial_state)
                baseline = executor.request(
                    step.method,
                    step.path.format(resource_id=step.resource_id),
                    case_id=case.case_id,
                    bearer_token=self._secret(identities[step.identity_id]),
                    json_body=step.json_body,
                )
                observations.append(
                    Observation(
                        observer="http",
                        phase="baseline",
                        status_code=baseline.status_code,
                        data=redact(baseline.data),
                    )
                )
                if baseline.status_code not in step.expected_statuses:
                    reason_codes = (ReasonCode.BASELINE_PRECONDITION_FAILED.value,)
                else:
                    if "owner_api" in rule.required_observers:
                        baseline_state = self._observe_owner(
                            executor,
                            snapshot,
                            resource_id=step.resource_id,
                            owner_identity_id=resource_owners[step.resource_id],
                            identities=identities,
                            case_id=case.case_id,
                            phase="baseline",
                        )
                        observations.append(baseline_state)
                        if step.method != "GET" and initial_state.data == baseline_state.data:
                            reason_codes = (ReasonCode.BASELINE_PRECONDITION_FAILED.value,)
                        else:
                            before_state = (
                                Observation(
                                    observer="owner_api",
                                    phase="before",
                                    status_code=baseline_state.status_code,
                                    data=baseline_state.data,
                                )
                                if case.resource_id == step.resource_id
                                else self._observe_owner(
                                    executor,
                                    snapshot,
                                    resource_id=case.resource_id,
                                    owner_identity_id=case.owner_identity_id,
                                    identities=identities,
                                    case_id=case.case_id,
                                    phase="before",
                                )
                            )
                            observations.append(before_state)
                    if not reason_codes:
                        phase = "mutation"
                        mutation = executor.request(
                            case.method,
                            case.path,
                            case_id=case.case_id,
                            bearer_token=self._secret(identities[case.identity_id]),
                            json_body=case.json_body,
                        )
                        observations.append(
                            Observation(
                                observer="http",
                                phase="mutation",
                                status_code=mutation.status_code,
                                data=redact(mutation.data),
                            )
                        )
                        if "owner_api" in rule.required_observers:
                            observations.append(
                                self._observe_owner(
                                    executor,
                                    snapshot,
                                    resource_id=case.resource_id,
                                    owner_identity_id=case.owner_identity_id,
                                    identities=identities,
                                    case_id=case.case_id,
                                    phase="after",
                                )
                            )
                        verdict, reason_codes = evaluate_case(
                            case, rule, tuple(observations)
                        )
        except JiejianError as exc:
            if exc.code in _SAFETY_ERROR_CODES | _INFRASTRUCTURE_ERROR_CODES:
                infrastructure_failure = True
                raise
            reason_codes = (
                ReasonCode.REQUIRED_OBSERVER_MISSING.value
                if exc.code == ReasonCode.REQUIRED_OBSERVER_MISSING.value
                else ReasonCode.CLEANUP_FAILED.value
                if phase == "cleanup"
                else ReasonCode.BASELINE_PRECONDITION_FAILED.value
                if phase == "baseline"
                else exc.code,
            )
            verdict = CaseVerdict.INCONCLUSIVE
        finally:
            try:
                self._cleanup(executor, snapshot, case.case_id)
            except JiejianError as exc:
                if exc.code in _SAFETY_ERROR_CODES:
                    raise
                if infrastructure_failure:
                    raise JiejianError(
                        ReasonCode.CLEANUP_FAILED.value,
                        "基础设施错误后的清理失败",
                    ) from None
                reason_codes = tuple(
                    dict.fromkeys((*reason_codes, ReasonCode.CLEANUP_FAILED.value))
                )
                verdict = CaseVerdict.INCONCLUSIVE

        return build_evidence(
            case,
            run_id=run_id,
            verdict=verdict,
            reason_codes=reason_codes,
            observations=tuple(observations),
        )

    def _observe_owner(
        self,
        executor: HttpExecutor,
        snapshot: VerificationSnapshot,
        *,
        resource_id: str,
        owner_identity_id: str,
        identities: Mapping[str, Identity],
        case_id: str,
        phase: str,
    ) -> Observation:
        path = snapshot.flow.owner_observer_path.format(resource_id=resource_id)
        try:
            response = executor.request(
                "GET",
                path,
                case_id=case_id,
                bearer_token=self._secret(identities[owner_identity_id]),
            )
        except JiejianError as exc:
            if exc.code in _SAFETY_ERROR_CODES | {ErrorCode.EXEC_CANCELLED.value}:
                raise
            raise JiejianError(
                ReasonCode.REQUIRED_OBSERVER_MISSING.value,
                "owner_api 观察不可用",
                details={"cause": exc.code},
            ) from exc
        if not 200 <= response.status_code < 300:
            raise JiejianError(
                ReasonCode.REQUIRED_OBSERVER_MISSING.value,
                "owner_api 观察失败",
                details={"status_code": response.status_code},
            )
        return Observation(
            observer="owner_api",
            phase=phase,
            status_code=response.status_code,
            data=redact(response.data),
        )

    def _cleanup(
        self,
        executor: HttpExecutor,
        snapshot: VerificationSnapshot,
        case_id: str,
    ) -> None:
        response = executor.request(
            "POST",
            snapshot.flow.reset_path,
            case_id=case_id,
            cleanup_request=True,
            test_mode=True,
        )
        if not 200 <= response.status_code < 300:
            raise JiejianError(
                ReasonCode.CLEANUP_FAILED.value,
                "测试环境清理失败",
                details={"status_code": response.status_code},
            )

    def _secret(self, identity: Identity) -> str:
        variable = identity.secret_ref.removeprefix("env:")
        value = self.environ.get(variable)
        if not value:
            raise JiejianError(
                ErrorCode.SECRET_MISSING,
                "身份环境变量未设置",
                details={"identity_id": identity.id, "variable": variable},
            )
        return value
