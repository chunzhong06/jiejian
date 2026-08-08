"""阶段 1 的确定性变异、HTTP 执行、显式判定和证据构建。"""

from __future__ import annotations

import hashlib
import json
import random
from dataclasses import dataclass
from importlib.metadata import version
from typing import Any

import httpx

from .domain.models import CaseVerdict, RunVerdict
from .domain.stage1 import (
    ContractRule,
    Evidence,
    Flow,
    MutationCase,
    MutationKind,
    MutationPlan,
    Observation,
    ProjectDefinition,
    ReasonCode,
    RuleKind,
    SecurityContract,
)
from .errors import ErrorCode, JiejianError
from .redaction import redact, redact_known_secrets
from .safety import TargetGuard


def engine_version() -> str:
    """从安装发行包元数据读取引擎版本，避免源码内重复常量。"""

    return version("jiejian")


def build_mutation_plan(
    project: ProjectDefinition,
    flow: Flow,
    contract: SecurityContract,
    *,
    seed: int | None = None,
) -> MutationPlan:
    identities = {identity.id: identity for identity in project.identities}
    resources = {resource.id: resource for resource in project.resources}
    rules = {rule.kind: rule for rule in contract.rules}
    cases: list[MutationCase] = []

    for step in flow.steps:
        if step.identity_id not in identities or step.alternate_identity_id not in identities:
            raise JiejianError(ErrorCode.INPUT_INVALID, "Flow 引用了不存在的身份")
        if step.resource_id not in resources or step.alternate_resource_id not in resources:
            raise JiejianError(ErrorCode.INPUT_INVALID, "Flow 引用了不存在的资源")
        mutations = [MutationKind.IDENTITY_SWAP, MutationKind.RESOURCE_SWAP]
        if step.method != "GET":
            mutations.append(MutationKind.PRIVILEGED_FIELD)

        for mutation in mutations:
            identity_id = (
                step.alternate_identity_id
                if mutation is MutationKind.IDENTITY_SWAP
                else step.identity_id
            )
            resource_id = (
                step.alternate_resource_id
                if mutation is MutationKind.RESOURCE_SWAP
                else step.resource_id
            )
            owner_identity_id = resources[resource_id].owner_identity_id
            body = dict(step.json_body)
            if step.method != "GET":
                body["value"] = f"mutated-{mutation.value}"
            if mutation is MutationKind.PRIVILEGED_FIELD:
                body.update(
                    {
                        "owner_id": step.alternate_identity_id,
                        "role": "admin",
                    }
                )
            rule_kind = (
                RuleKind.FOREIGN_READ
                if step.method == "GET"
                else RuleKind.PRIVILEGED_FIELD
                if mutation is MutationKind.PRIVILEGED_FIELD
                else RuleKind.UNAUTHORIZED_SIDE_EFFECT
            )
            rule = rules.get(rule_kind)
            if rule is None:
                raise JiejianError(
                    ErrorCode.INPUT_INVALID,
                    "契约缺少变异所需的显式规则",
                    details={"kind": rule_kind.value},
                )
            try:
                path = step.path.format(resource_id=resource_id)
            except (KeyError, ValueError) as exc:
                raise JiejianError(ErrorCode.INPUT_INVALID, "Flow 路径模板无效") from exc
            fingerprint_payload = {
                "step_id": step.id,
                "rule_id": rule.id,
                "mutation": mutation.value,
                "method": step.method,
                "path": path,
                "identity_id": identity_id,
                "resource_id": resource_id,
                "body": body,
            }
            fingerprint = _hash_payload(fingerprint_payload)
            cases.append(
                MutationCase(
                    case_id=f"case_{fingerprint[:16]}",
                    fingerprint=fingerprint,
                    step_id=step.id,
                    rule_id=rule.id,
                    mutation=mutation,
                    method=step.method,
                    path=path,
                    identity_id=identity_id,
                    resource_id=resource_id,
                    owner_identity_id=owner_identity_id,
                    json_body=body,
                )
            )

    selected_seed = project.mutation_seed if seed is None else seed
    random.Random(selected_seed).shuffle(cases)
    return MutationPlan(
        seed=selected_seed,
        engine_version=engine_version(),
        cases=tuple(cases),
    )


@dataclass(frozen=True, slots=True)
class HttpResponse:
    status_code: int
    data: dict[str, Any]


class HttpExecutor:
    """唯一主动 HTTP 边界；统一执行范围、预算、超时和响应体限制。"""

    def __init__(
        self,
        guard: TargetGuard,
        *,
        cleanup_reserve: int = 0,
        known_secrets: tuple[str, ...] = (),
    ) -> None:
        self.guard = guard
        self.requests_used = 0
        self.cleanup_reserve = cleanup_reserve
        self.known_secrets = known_secrets
        self.client = httpx.Client(
            follow_redirects=False,
            timeout=guard.scope.timeout_seconds,
            trust_env=False,
        )

    def close(self) -> None:
        self.client.close()

    def request(
        self,
        method: str,
        path: str,
        *,
        case_id: str,
        bearer_token: str | None = None,
        json_body: dict[str, Any] | None = None,
        cleanup_request: bool = False,
        test_mode: bool = False,
    ) -> HttpResponse:
        target = self.guard.authorize_path(path)
        remaining_for_normal = self.guard.scope.max_requests - self.cleanup_reserve
        if self.requests_used >= self.guard.scope.max_requests or (
            not cleanup_request and self.requests_used >= remaining_for_normal
        ):
            raise JiejianError(ErrorCode.EXEC_BUDGET, "HTTP 请求预算已耗尽")
        self.requests_used += 1
        if cleanup_request and self.cleanup_reserve:
            self.cleanup_reserve -= 1
        headers = {"X-Jiejian-Case-ID": case_id}
        if bearer_token is not None:
            headers["Authorization"] = f"Bearer {bearer_token}"
        if test_mode:
            headers["X-Jiejian-Test-Mode"] = "1"
        try:
            with self.client.stream(
                method,
                target.url,
                headers=headers,
                json=json_body if json_body else None,
            ) as response:
                content = bytearray()
                for chunk in response.iter_bytes():
                    content.extend(chunk)
                    if len(content) > self.guard.scope.max_response_bytes:
                        raise JiejianError(
                            ErrorCode.EXEC_RESPONSE_TOO_LARGE,
                            "响应体超过安全预算",
                        )
                location = response.headers.get("location")
                if 300 <= response.status_code < 400 and location:
                    self.guard.authorize_redirect(target.url, location)
                data = redact_known_secrets(
                    _decode_response(bytes(content)),
                    self.known_secrets,
                )
                return HttpResponse(status_code=response.status_code, data=data)
        except httpx.TimeoutException as exc:
            raise JiejianError(ErrorCode.EXEC_TIMEOUT, "目标请求超时") from exc
        except httpx.RequestError as exc:
            raise JiejianError(
                ErrorCode.EXEC_REQUEST,
                "目标请求失败",
                details={"reason": type(exc).__name__},
            ) from exc


def evaluate_case(
    case: MutationCase,
    rule: ContractRule,
    observations: tuple[Observation, ...],
) -> tuple[CaseVerdict, tuple[str, ...]]:
    by_phase = {(item.observer, item.phase): item for item in observations}
    mutation_http = by_phase.get(("http", "mutation"))
    if mutation_http is None:
        return CaseVerdict.INCONCLUSIVE, (ReasonCode.REQUIRED_OBSERVER_MISSING.value,)

    if rule.kind is RuleKind.FOREIGN_READ:
        if 200 <= (mutation_http.status_code or 0) < 300 and mutation_http.data:
            return CaseVerdict.VULNERABLE, (
                ReasonCode.FOREIGN_RESOURCE_OBSERVED.value,
            )
        if mutation_http.status_code in {401, 403, 404}:
            return CaseVerdict.SAFE, ()
        return CaseVerdict.INCONCLUSIVE, (
            ReasonCode.UNEXPECTED_HTTP_RESPONSE.value,
        )

    before = by_phase.get(("owner_api", "before"))
    after = by_phase.get(("owner_api", "after"))
    if before is None or after is None:
        return CaseVerdict.INCONCLUSIVE, (ReasonCode.REQUIRED_OBSERVER_MISSING.value,)
    if rule.kind is RuleKind.UNAUTHORIZED_SIDE_EFFECT and before.data != after.data:
        return CaseVerdict.VULNERABLE, (
            ReasonCode.UNAUTHORIZED_SIDE_EFFECT.value,
        )
    if rule.kind is RuleKind.PRIVILEGED_FIELD:
        protected_before = {key: before.data.get(key) for key in ("owner_id", "role")}
        protected_after = {key: after.data.get(key) for key in ("owner_id", "role")}
        if protected_before != protected_after:
            return CaseVerdict.VULNERABLE, (
                ReasonCode.PRIVILEGED_FIELD_ACCEPTED.value,
            )
    if mutation_http.status_code in {401, 403, 404}:
        return CaseVerdict.SAFE, ()
    return CaseVerdict.INCONCLUSIVE, (
        ReasonCode.UNEXPECTED_HTTP_RESPONSE.value,
    )


def build_evidence(
    case: MutationCase,
    *,
    run_id: str,
    verdict: CaseVerdict,
    reason_codes: tuple[str, ...],
    observations: tuple[Observation, ...],
) -> Evidence:
    safe_observations = tuple(
        Observation.model_validate(redact(item.model_dump(mode="json")))
        for item in observations
    )
    request = redact(
        {
            "method": case.method,
            "path": case.path,
            "identity_id": case.identity_id,
            "resource_id": case.resource_id,
            "json_body": case.json_body,
        }
    )
    payload = redact(
        {
            "schema_version": "1",
            "run_id": run_id,
            "case_id": case.case_id,
            "fingerprint": case.fingerprint,
            "rule_id": case.rule_id,
            "mutation": case.mutation.value,
            "verdict": verdict.value,
            "reason_codes": reason_codes,
            "request": request,
            "observations": [
                item.model_dump(mode="json") for item in safe_observations
            ],
        }
    )
    evidence_hash = _hash_payload(payload)
    return Evidence(
        evidence_id=f"ev_{evidence_hash[:20]}",
        run_id=run_id,
        case_id=case.case_id,
        fingerprint=case.fingerprint,
        rule_id=case.rule_id,
        mutation=case.mutation,
        verdict=verdict,
        reason_codes=reason_codes,
        request=request,
        observations=safe_observations,
        evidence_hash=evidence_hash,
    )


def aggregate_verdict(evidence: tuple[Evidence, ...]) -> RunVerdict:
    if any(ReasonCode.CLEANUP_FAILED.value in item.reason_codes for item in evidence):
        return RunVerdict.INCONCLUSIVE
    if any(item.verdict is CaseVerdict.VULNERABLE for item in evidence):
        return RunVerdict.BLOCK
    if any(
        item.verdict in {CaseVerdict.INCONCLUSIVE, CaseVerdict.ERROR}
        for item in evidence
    ):
        return RunVerdict.INCONCLUSIVE
    return RunVerdict.PASS


def _decode_response(content: bytes) -> dict[str, Any]:
    if not content:
        return {}
    try:
        decoded = json.loads(content)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return {"text": content.decode("utf-8", errors="replace")}
    return decoded if isinstance(decoded, dict) else {"value": decoded}


def _hash_payload(payload: Any) -> str:
    encoded = json.dumps(
        redact(payload),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
