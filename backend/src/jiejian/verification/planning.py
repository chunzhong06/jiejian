# =============================================================================
# Verification 关系变异规划
#
# 定位
#   在不产生目标副作用时把 Flow 和 Contract 派生为确定性 MutationPlan
#
# 职责
#   校验 Flow 引用｜交换身份、资源或高权限字段｜生成稳定测试用例与内容指纹
#
# 调用链
#   SnapshotRunExecutor.run → build_mutation_plan → MutationPlan / MutationCase
# =============================================================================

from __future__ import annotations

import hashlib
import json
import random
from importlib.metadata import version
from typing import Any

from .models import (
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
    """读取当前安装包版本，作为本次变异计划的引擎版本。"""

    return version("jiejian")


def build_mutation_plan(
    identities_snapshot: tuple[Identity, ...],
    resources_snapshot: tuple[ResourceDefinition, ...],
    flow: Flow,
    contract: SecurityContract,
    *,
    seed: int,
) -> MutationPlan:
    """从正常 Flow 派生固定 seed 下可复现的攻击测试计划。

    核心数据
        原始 FlowStep 保留正常身份、资源和请求，作为执行时的正常对照。
        每个 MutationCase 保存一种身份交换、资源交换或高权限字段变体。

    数据流
        函数先校验 Flow 引用的身份和资源，再为每个正常步骤生成适用的攻击变体，
        随后匹配 ContractRule、生成稳定指纹并汇总为 MutationPlan。

    关键说明
        本函数只在内存中规划测试，不发送目标请求。每种变体都必须在 Contract
        中具有显式规则，规划器不会自行补充判定标准。

    返回
        包含全部 MutationCase、固定 seed 和当前引擎版本的 MutationPlan。
    """

    # ID 与规则类型索引只服务本次规划；既不解析身份秘密，也不持久化。
    identities = {identity.id: identity for identity in identities_snapshot}
    resources = {resource.id: resource for resource in resources_snapshot}
    rules = {rule.kind: rule for rule in contract.rules}
    cases: list[MutationCase] = []

    # --- 阶段：从正常步骤派生攻击变体 ---
    for step in flow.steps:
        if step.identity_id not in identities or step.alternate_identity_id not in identities:
            raise JiejianError(ErrorCode.INPUT_INVALID, "Flow 引用了不存在的身份")
        if step.resource_id not in resources or step.alternate_resource_id not in resources:
            raise JiejianError(ErrorCode.INPUT_INVALID, "Flow 引用了不存在的资源")
        # 读取步骤只交换身份或资源；写入步骤再增加高权限字段测试。
        mutations = [MutationKind.IDENTITY_SWAP, MutationKind.RESOURCE_SWAP]
        if step.method != "GET":
            mutations.append(MutationKind.PRIVILEGED_FIELD)

        for mutation in mutations:
            # 身份与资源关系每次只替换一个维度；请求值会另写入可识别标记。
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
            # 执行器需要真正的资源所有者，以其身份比较攻击前后的后端状态。
            owner_identity_id = resources[resource_id].owner_identity_id
            body = dict(step.json_body)
            if step.method != "GET":
                # 可识别的测试值用于区分本次变体与正常 baseline 写入。
                body["value"] = f"mutated-{mutation.value}"
            if mutation is MutationKind.PRIVILEGED_FIELD:
                body.update(
                    {
                        "owner_id": step.alternate_identity_id,
                        "role": "admin",
                    }
                )
            # 读取越权、写入副作用和高权限字段分别使用显式 Contract 规则判定。
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
            # 指纹只包含决定测试语义的字段，供 case、Evidence 和结果视图稳定关联。
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

    # 固定 seed 只改变执行顺序；相同输入与 seed 必须产生相同计划。
    random.Random(seed).shuffle(cases)
    return MutationPlan(
        seed=seed,
        engine_version=engine_version(),
        cases=tuple(cases),
    )


def _fingerprint(payload: Any) -> str:
    """先脱敏，再为测试语义生成稳定 SHA-256 内容指纹。

    字段排序和紧凑 JSON 消除字典顺序及空白差异。生成的指纹用于构造 case_id，
    并随 Evidence 贯穿后续执行和结果读取。
    """

    encoded = json.dumps(
        redact(payload),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
