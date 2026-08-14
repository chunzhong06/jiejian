# =============================================================================
# Verification 证据判定
#
# 定位
#   把 HTTP 与 owner observer 的事实转换为 Evidence 和 Run Verdict 的纯算法
#
# 职责
#   判定单个 case｜构造可哈希 Evidence｜聚合 PASS/BLOCK/INCONCLUSIVE
#
# 调用链
#   SnapshotRunExecutor → evaluate_case / build_evidence → aggregate_verdict
# =============================================================================

from __future__ import annotations

import hashlib
import json
from typing import Any

from ..domain.lifecycle import CaseVerdict, RunVerdict
from .models import (
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
    """按 ContractRule 把多面 Observation 解释为单用例结论。

    核心数据
        observations 以 (observer, phase) 组合定位 HTTP 攻击响应，以及 owner_api
        的 before/after 状态；不同 RuleKind 只读取自身需要的观察面。

    数据流
        MutationCase + ContractRule + Observations
        → 关系规则比较 → CaseVerdict + 稳定 ReasonCode。

    关键说明
        HTTP 拒绝只是一项观察；如果 owner 侧状态已经变化，403 仍会得到
        VULNERABLE。必要观察缺失时只能返回 INCONCLUSIVE，不能假定安全。

    返回
        单用例 Verdict，以及解释该结论的稳定原因码元组。
    """

    # 同一观察器和阶段只保留一个事实，供后续关系规则按键读取。
    by_phase = {(item.observer, item.phase): item for item in observations}
    mutation_http = by_phase.get(("http", "mutation"))
    if mutation_http is None:
        return CaseVerdict.INCONCLUSIVE, (ReasonCode.REQUIRED_OBSERVER_MISSING.value,)

    # --- 规则：非所有者读取 ---
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

    # --- 规则：写入副作用与高权限字段 ---
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
    """把攻击请求、观察事实和结论固化为已脱敏、内容寻址的 Evidence。

    数据流
        MutationCase + CaseVerdict + Observations → 统一脱敏 → 规范 JSON 哈希
        → evidence_id / evidence_hash → Evidence。

    关键说明
        请求和观察在计算哈希前统一脱敏，保证真实秘密既不参与持久证据，
        也不会通过 evidence_hash 的输入继续传播。

    返回
        可由 case_id、fingerprint 和 evidence_hash 稳定追踪的单用例 Evidence。
    """

    # 重新经过模型校验，保证脱敏后的观察仍符合公共 Evidence 结构。
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
    # payload 是 evidence_hash 的唯一语义输入，不包含 evidence_id 本身。
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
    """把全部单用例 Evidence 聚合为一次运行的门禁结论。

    关键说明
        清理失败首先强制 INCONCLUSIVE，因为目标状态已不可信；没有清理失败时，
        任一 VULNERABLE 产生 BLOCK，其他不确定或错误用例产生 INCONCLUSIVE，
        只有全部用例安全时才返回 PASS。
    """

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
    """对已脱敏、键排序的紧凑 JSON 计算稳定 SHA-256。"""

    encoded = json.dumps(
        redact(payload),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
