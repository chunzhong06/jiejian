# 修改权限意图与 Agent 授权

> 状态：CURRENT。用于修改长期权限意图、Human Approval、实现映射、Agent proposal、MCP Oracle 边界和 Run 权限策略快照。

## 这是什么

权限意图回答“哪类人对哪类业务资源执行什么动作应该允许或拒绝”。它是人类长期安全需求，不是当前源码候选、测试账号、HTTP 绑定或某次 Run 的临时配置。只有本机 GUI 的服务端批准事务可以改变这份真源；CLI、MCP、Machine、AI、Compiler、Check Prepare、Run 和 Recording 都只能读取、准备或提出不生效建议。

## 快速找到修改位置

| 要改什么 | 先看哪里 | 直接测试 |
| --- | --- | --- |
| Revision、Approval、Binding、Proposal 领域模型 | `product/backend/core/permission_intent.py` | `tests/backend/workflows/security_setup/test_permission_intent_ledger.py` |
| 矩阵、批准事务、proposal 与运行快照 | `product/backend/workflows/permission_intents.py` | `tests/backend/api/test_permission_intent_human_approval.py`、`tests/backend/api/test_permission_oracle_invariant.py` |
| Human-only HTTP API | `product/backend/api/routers/permission_intents.py` | `tests/backend/api/test_permission_intent_approval_boundary.py` |
| MCP 权限意图工具 | `product/backend/api/mcp.py` | `tests/backend/api/test_mcp.py`、`tests/backend/api/test_permission_oracle_invariant.py` |
| Compiler 与冻结执行请求 | `product/backend/workflows/security_setup/compiler.py`、`product/protocols/execution_request.py` | `tests/backend/workflows/security_setup/test_compiler.py` |
| 结果、历史与报告快照摘要 | `product/backend/workflows/results/presentation.py`、`product/protocols/report.py` | `tests/backend/workflows/results/test_result_presentation.py`、`tests/backend/workflows/results/test_history.py`、`tests/backend/workflows/results/test_reports.py` |
| 修复要求与同考题复验 | `product/backend/core/repair.py`、`product/backend/workflows/results/repair.py` | `tests/backend/workflows/results/test_repair_contracts.py` |
| 权限确认与 proposal 页面 | `product/frontend/src/features/checks/PermissionCheckPage.tsx`、`product/frontend/src/api/permissionIntents.ts` | `product/frontend/src/features/checks/PermissionCheckPage.test.tsx` |

## 长期账本怎样工作

`PermissionIntentRevision` 按稳定 `intent_id` 追加不可变 revision。语义包含 ACTIVE/RETIRED、主体/动作/资源所有者业务显示名、资源关系、ALLOW/DENY 和受保护效果；`intent_hash` 只覆盖这些语义，不包含审批人、candidate、测试账号、运行或时间。`ProjectPolicyState.policy_epoch` 从 0 开始，只有 Human GUI 批准真实语义变化时递增。对已有要求选择“未确认”表示追加 RETIRED revision，不是删除历史。

`HumanApproval` 由服务端写入固定 `LOCAL_GUI` 身份、审批时间和原因。HTTP body 只接受 cell target、目标 expectation 和可选 reason，不接受自由 actor。批准事务在同一 UnitOfWork 中校验预期 epoch，追加 revision 与 binding，并更新项目 epoch；并发变化必须要求用户刷新后重试。

## 实现映射与重新分析

`IntentImplementationBinding` 把人类 revision 映射到当前 action/role candidate、ApplicationUnderstanding revision 和安全准备 fingerprint。源码重新分析、候选变化或安全准备变化只能把 binding 降为 NEEDS_REVIEW/UNRESOLVED，不能删除、退休或修改人类规则。重新确认同一语义只更新 binding，不推进 `policy_epoch`。

`SecuritySetupCompiler` 只消费 ACTIVE latest + CURRENT binding。任何 ACTIVE revision 缺少 CURRENT binding 都必须 fail closed；测试账号或代表变化形成 coverage gap 或新的生成配置，不能静默缩小权限范围。

## Agent proposal 与 Oracle 边界

`IntentProposal` 只有 SEMANTIC_CHANGE 和 IMPLEMENTATION_REBIND 两类，创建后保持 PENDING，直到 Human GUI 批准或拒绝。前端只显示当前值、Agent 建议和原因，不能自行构造 revision；批准语义建议进入正式 Human Approval transaction，批准 rebind 只更新 binding。

MCP 权限工具固定为：

```text
jiejian_intent_list              READ
jiejian_intent_show              READ
jiejian_intent_propose           PREPARE
jiejian_intent_rebind_propose    PREPARE
```

MCP 没有 approve/reject，也没有 permission_set 或 candidate_decide。无论 READ、PREPARE 还是 EXECUTE，MCP 允许的重分析、身份准备、Recording、检查准备、运行和取消都不能改变 active revision、`intent_hash` 或 `policy_epoch`；proposal 在人类批准前也不能生效。

修复入口只新增 READ 的 `jiejian_repair_contract_get`。它从已发布 BLOCK 与 Finding 重建权威要求；Agent 在 `jiejian_change_submit` 中只能回传服务端给出的引用，不能修改要求、批准权限或直接宣称修复通过。CLI 不提供修复合同、批准或修复专用运行命令。

## Run 权限策略快照

提交 Run 前把 `project_id`、`policy_epoch`、`policy_fingerprint` 以及每条 ACTIVE revision 的语义身份和实现映射冻结进 `PermissionPolicySnapshot` 和持久执行请求。代码变化重验还冻结独立 `ChangeVerificationContext`，但不能用它裁剪完整 Coverage。修复重验再冻结 `RepairVerificationContext`：原要求的 revision/hash 必须精确不变；纯实现重绑只要未改变 `policy_epoch` 和 `intent_hash` 可以继续。删除受保护效果、降低原关键证据要求或破坏 ALLOW 控制都不能得到 `VERIFIED`。ResultPresentation、History 和 report.json 只从该冻结请求复制摘要，不读取 live Ledger 改写旧结果。普通页面显示“本次检查依据权限版本 X”和可选重验数量，不显示内部指纹或 intent 标识。

如果提交修复重验前发现任一原要求身份变化，服务端固定失败为“原权限要求已经改变，请按新权限重新形成检查。”，不得把改变考题当作修复。修复复验的 `VERIFIED / NOT_VERIFIED / INCONCLUSIVE` 独立于 Verification Verdict，只说明同一考题下的修复要求是否被证明满足。

## 怎么验证

先按修改面运行最小直接测试，不为局部权限意图变化重复完整 L4/L5：

```powershell
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File .\scripts\dev.ps1 test tests/backend/api/test_permission_intent_human_approval.py tests/backend/api/test_permission_oracle_invariant.py tests/backend/workflows/security_setup/test_permission_intent_ledger.py tests/backend/workflows/results/test_repair_contracts.py tests/backend/workflows/results/test_result_presentation.py tests/backend/workflows/results/test_history.py tests/backend/workflows/results/test_reports.py
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File .\scripts\dev.ps1 frontend-test src/features/checks/PermissionCheckPage.test.tsx src/features/checks/CheckResultsPage.test.tsx src/features/checks/CheckHistoryPage.test.tsx
```

公共执行请求或报告字段变化时再运行 `dev.ps1 schema -Update` 和 `dev.ps1 schema`；文档变化运行 `dev.ps1 docs -Update` 后再运行 `dev.ps1 docs`。最终仍要检查 MCP tool inventory 中不存在 mutator/approve/reject，并证明结果与历史来自 Run 的冻结 policy snapshot。

## 相关真源

- [安全意图与验证架构](../../01_系统地图/权限验证与结果.md)
- [应用接入与检查主流程](../../01_系统地图/应用接入与检查主流程.md)
- [修改 Agent 变更影响](修改Agent变更影响.md)
- [权限契约与执行计划](../../03_参考手册/协议/权限契约与执行计划.md)
- [控制面与 Machine 输出协议](../../03_参考手册/协议/控制面与Machine输出协议.md)
- [验证与测试](../../04_工程约束/验证与测试.md)
