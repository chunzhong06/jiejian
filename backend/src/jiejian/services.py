"""阶段 1 同步运行编排：基线、变异、观察、判定与清理。"""

from __future__ import annotations

import os
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from .artifacts import persist_run
from .domain.models import CaseVerdict
from .domain.stage1 import (
    Evidence,
    Identity,
    MutationCase,
    Observation,
    ReasonCode,
    RunResult,
)
from .engine import (
    HttpExecutor,
    aggregate_verdict,
    build_evidence,
    build_mutation_plan,
    evaluate_case,
)
from .errors import ErrorCode, JiejianError
from .inputs import ProjectBundle, load_project_bundle
from .redaction import redact
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
    ErrorCode.SECRET_MISSING.value,
}


class RunService:
    """单进程同步纵切；不依赖业务数据库、队列或后台进程。"""

    def __init__(
        self,
        var_dir: Path,
        *,
        environ: Mapping[str, str] | None = None,
    ) -> None:
        self.var_dir = var_dir.resolve()
        self.environ = os.environ if environ is None else environ

    def run(
        self,
        project_path: Path,
        *,
        contract_path: Path | None = None,
    ) -> RunResult:
        bundle = load_project_bundle(project_path, contract_path=contract_path)
        plan = build_mutation_plan(bundle.project, bundle.flow, bundle.contract)
        cleanup_reserve = 2 * len(plan.cases)
        if bundle.project.target.max_requests < cleanup_reserve:
            raise JiejianError(
                ErrorCode.EXEC_BUDGET,
                "HTTP 请求预算不足以预留全部清理请求",
                details={"required_cleanup_requests": cleanup_reserve},
            )
        run_id = f"run_{uuid4().hex}"
        started_at = datetime.now(UTC)
        guard = TargetGuard(bundle.project.target)
        guard.authorize_url(bundle.project.target.base_url)
        known_secrets = tuple(
            self._secret(identity) for identity in bundle.project.identities
        )
        executor = HttpExecutor(
            guard,
            cleanup_reserve=cleanup_reserve,
            known_secrets=known_secrets,
        )
        evidence: list[Evidence] = []
        try:
            for case in plan.cases:
                item = self._run_case(executor, bundle, case, run_id=run_id)
                evidence.append(item)
                if ReasonCode.CLEANUP_FAILED.value in item.reason_codes:
                    break
        finally:
            executor.close()

        evidence_tuple = tuple(evidence)
        verdict = aggregate_verdict(evidence_tuple)
        reason_codes = tuple(
            dict.fromkeys(code for item in evidence_tuple for code in item.reason_codes)
        )
        artifact_dir = self.var_dir / "projects" / bundle.project.id / "runs" / run_id
        result = RunResult(
            run_id=run_id,
            project_id=bundle.project.id,
            engine_version=plan.engine_version,
            verdict=verdict,
            reason_codes=reason_codes,
            evidence=evidence_tuple,
            artifact_dir=str(artifact_dir),
        )
        persist_run(
            result,
            bundle,
            plan.model_dump(mode="json"),
            started_at=started_at,
            finished_at=datetime.now(UTC),
        )
        return result

    def _run_case(
        self,
        executor: HttpExecutor,
        bundle: ProjectBundle,
        case: MutationCase,
        *,
        run_id: str,
    ) -> Evidence:
        identities = {identity.id: identity for identity in bundle.project.identities}
        resource_owners = {
            resource.id: resource.owner_identity_id
            for resource in bundle.project.resources
        }
        steps = {step.id: step for step in bundle.flow.steps}
        rules = {rule.id: rule for rule in bundle.contract.rules}
        step = steps[case.step_id]
        rule = rules[case.rule_id]
        observations: list[Observation] = []
        verdict = CaseVerdict.INCONCLUSIVE
        reason_codes: tuple[str, ...] = ()
        phase = "cleanup"

        try:
            self._cleanup(executor, bundle, case.case_id)
            phase = "baseline"
            if "owner_api" in rule.required_observers and not bundle.project.owner_observer_enabled:
                reason_codes = (ReasonCode.REQUIRED_OBSERVER_MISSING.value,)
            else:
                initial_state = None
                if "owner_api" in rule.required_observers:
                    initial_state = self._observe_owner(
                        executor,
                        bundle,
                        resource_id=step.resource_id,
                        owner_identity_id=resource_owners[step.resource_id],
                        identities=identities,
                        case_id=case.case_id,
                        phase="initial",
                    )
                    observations.append(initial_state)
                baseline_path = step.path.format(resource_id=step.resource_id)
                baseline = executor.request(
                    step.method,
                    baseline_path,
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
                            bundle,
                            resource_id=step.resource_id,
                            owner_identity_id=resource_owners[step.resource_id],
                            identities=identities,
                            case_id=case.case_id,
                            phase="baseline",
                        )
                        observations.append(baseline_state)
                        if step.method != "GET" and initial_state.data == baseline_state.data:
                            reason_codes = (
                                ReasonCode.BASELINE_PRECONDITION_FAILED.value,
                            )
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
                                    bundle,
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
                                    bundle,
                                    resource_id=case.resource_id,
                                    owner_identity_id=case.owner_identity_id,
                                    identities=identities,
                                    case_id=case.case_id,
                                    phase="after",
                                )
                            )
                        verdict, reason_codes = evaluate_case(
                            case,
                            rule,
                            tuple(observations),
                        )
        except JiejianError as exc:
            if exc.code in _SAFETY_ERROR_CODES | _INFRASTRUCTURE_ERROR_CODES:
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
                self._cleanup(executor, bundle, case.case_id)
            except JiejianError as exc:
                if exc.code in _SAFETY_ERROR_CODES:
                    raise
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
        bundle: ProjectBundle,
        *,
        resource_id: str,
        owner_identity_id: str,
        identities: Mapping[str, Identity],
        case_id: str,
        phase: str,
    ) -> Observation:
        path = bundle.flow.owner_observer_path.format(resource_id=resource_id)
        try:
            response = executor.request(
                "GET",
                path,
                case_id=case_id,
                bearer_token=self._secret(identities[owner_identity_id]),
            )
        except JiejianError as exc:
            if exc.code in _SAFETY_ERROR_CODES:
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
        bundle: ProjectBundle,
        case_id: str,
    ) -> None:
        response = executor.request(
            "POST",
            bundle.flow.reset_path,
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
