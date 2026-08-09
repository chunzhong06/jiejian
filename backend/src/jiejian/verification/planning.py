"""根据 Flow 与安全契约生成确定性的关系变异计划。"""

from __future__ import annotations

import hashlib
import json
import random
from importlib.metadata import version
from typing import Any

from ..domain.verification import (
    Flow,
    Identity,
    MutationCase,
    MutationKind,
    MutationPlan,
    ResourceDefinition,
    RuleKind,
    SecurityContract,
)
from ..errors import ErrorCode, JiejianError
from ..redaction import redact


def engine_version() -> str:
    """从安装发行包元数据读取引擎版本，避免源码内重复常量。"""

    return version("jiejian")


def build_mutation_plan(
    identities_snapshot: tuple[Identity, ...],
    resources_snapshot: tuple[ResourceDefinition, ...],
    flow: Flow,
    contract: SecurityContract,
    *,
    seed: int,
) -> MutationPlan:
    """把验证输入转换为固定 seed 下可复现的变异用例。"""

    identities = {identity.id: identity for identity in identities_snapshot}
    resources = {resource.id: resource for resource in resources_snapshot}
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
            fingerprint = _fingerprint(fingerprint_payload)
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

    random.Random(seed).shuffle(cases)
    return MutationPlan(
        seed=seed,
        engine_version=engine_version(),
        cases=tuple(cases),
    )


def _fingerprint(payload: Any) -> str:
    encoded = json.dumps(
        redact(payload),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
