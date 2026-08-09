"""多面观察的显式判定、证据构建与门禁聚合。"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from ..domain.lifecycle import CaseVerdict, RunVerdict
from ..domain.verification import (
    ContractRule,
    Evidence,
    MutationCase,
    Observation,
    ReasonCode,
    RuleKind,
)
from ..redaction import redact


def evaluate_case(
    case: MutationCase,
    rule: ContractRule,
    observations: tuple[Observation, ...],
) -> tuple[CaseVerdict, tuple[str, ...]]:
    """按契约规则解释观察结果，不把 HTTP 状态码直接当作结论。"""

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
    """生成已脱敏、内容寻址的单用例证据。"""

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
    evidence_hash = _evidence_hash(payload)
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
    """按 BLOCK、INCONCLUSIVE、PASS 的门禁优先级聚合证据。"""

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


def _evidence_hash(payload: Any) -> str:
    encoded = json.dumps(
        redact(payload),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
