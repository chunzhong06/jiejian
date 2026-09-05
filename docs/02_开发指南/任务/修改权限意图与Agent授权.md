# 修改业务边界、权限意图与 Agent 授权

> 状态：CURRENT。用于修改 1.1.0 Business Boundary、Permission v2、Human Approval、实现绑定和 Agent/自动化只读边界。

## 这是什么

1.1.0 把权限真源拆成稳定业务语义与当前代码定位：

```text
ApplicationUnderstanding Candidate
  → 仅用于发现和 implementation binding

BusinessActor + BusinessAction + Effect catalog
  → 人确认的稳定业务边界

PermissionIntentRevision
  → 谁对谁的资源执行什么动作，应 ALLOW 或 DENY，保护哪些 Effect
```

Candidate、测试账号、Flow、HTTP 绑定或某次 Run 都不能成为业务权限真源。只有本机 GUI 发起、服务端固定为 `LOCAL_GUI` 的 Proposal 决定事务可以改变正式语义；CLI、MCP、Machine、AI、Compiler、Worker 和 Runner 都不是审批人。

## 快速找到修改位置

| 要改什么 | 先看哪里 | 直接测试 |
| --- | --- | --- |
| Actor、Action、Effect 与 implementation binding | `product/backend/core/business_boundary.py` | `tests/backend/core/test_business_boundary.py` |
| 不可变 Proposal、指纹与 Decision | `product/backend/core/boundary_proposal.py` | `tests/backend/workflows/business_boundaries/` |
| Permission v2 revision 与 policy state | `product/backend/core/permission_intent.py` | `tests/backend/workflows/business_boundaries/` |
| Proposal/Approval 原子事务 | `product/backend/workflows/business_boundaries/service.py` | `tests/backend/api/test_business_boundaries.py` |
| Storage 与数据库结构 | `product/backend/infra/storage/business_boundaries.py`、`product/backend/infra/storage/setup/permission_intents.py` | `tests/backend/infra/storage/test_migration_baseline.py` |
| Human-only loopback API | `product/backend/api/routers/business_boundaries.py` | `tests/backend/api/test_business_boundaries.py` |
| 当前权限页面 | `product/frontend/src/features/boundaries/`、`product/frontend/src/api/businessBoundaries.ts` | `product/frontend/src/features/boundaries/BusinessBoundaryPage.test.tsx` |
| Agent/MCP 不变量 | `product/backend/api/mcp.py` | `tests/backend/api/test_permission_oracle_invariant.py`、`tests/architecture/test_business_boundary_v2.py` |

## Candidate 的责任

`preview_from_discovery()` 读取 ApplicationUnderstanding 的角色与动作 Candidate，只输出未 stale 且没有被用户明确 `REJECTED` 的候选。HIGH/MEDIUM 只可作为前端默认建议，LOW 只列出而不自动采用。多个 Candidate 合并为一个业务主体或动作必须由用户明确操作；名称相似不构成合并依据。

正式 Actor、Action、Effect 和 Permission 不保存 Candidate ID。Candidate ID 只进入 `ActorImplementationBinding` 或 `ActionImplementationBinding`；手工业务语义使用 `MISSING` binding，仍可 ACTIVE，页面必须同时说明“业务边界已确认”和“当前代码中还没有可靠定位”。

## Business Boundary revision

`BusinessActorRevision` 和 `BusinessActionRevision` 按稳定 ID 追加不可变 revision。Action revision 拥有完整 Effect catalog；Effect 表达真正业务结果，例如对象形成、状态变化或受保护数据披露，不能用 request、task、queue 或 worker 节点代替。

Permission v2 引用稳定 Actor/Action revision，语义包含资源关系、`ALLOW/DENY` 和受保护 effect IDs。`PermissionIntentRevision` 不包含 Candidate、TestIdentity、Flow、Observer、Profile 或运行信息。

普通 `BusinessBoundaryView` 只投影每个 intent_id 的 latest revision 中仍为 ACTIVE、且精确匹配当前 ACTIVE subject actor、resource owner actor、Action revision 与当前 Effect catalog 的权限。RETIRED、旧 Actor/Action revision 和失效 Effect 引用继续留在 history，但不进入当前权限计数或 Workbench 完成判断；当前 Action 没有有效权限时，页面区分“从未确认”与“历史权限需要按新 revision 重新确认”。本版不自动迁移旧权限。

## Proposal 与 Human Approval

编辑页只保存浏览器内草稿。用户点击“生成待审业务边界”后，服务端冻结 `BoundaryProposalBundle`、来源快照和 `proposal_fingerprint`；待审正文没有 PATCH 入口。返回修改以旧 Proposal 初始化新的本地草稿，最终创建新的 Proposal；放弃形成 `REJECTED` Decision。

批准请求只包含路径中的 `proposal_id`、预期 `proposal_fingerprint` 和原因。服务端重新校验 Proposal 未决定、指纹一致、来源没有漂移且没有 unresolved question，然后在同一 Unit of Work 中提交：

```text
BusinessActor / BusinessAction revisions
+ Actor / Action implementation bindings
+ PermissionIntent revisions
+ ProjectPolicyState
+ APPROVED Decision
```

任何一步失败都不允许留下部分正式事实。前端不能提交 `approved_by` 或审批渠道冒充其他主体。

## policy_epoch

`ProjectPolicyState.policy_epoch` 从 0 开始。批准事务只有实际写入一条或多条新的 `PermissionIntentRevision` 时才推进一次；同一 Proposal 中 carry-forward 三条权限也只推进一次。只有 Actor/Action/Effect revision 而没有权限 revision、纯 Candidate 重新绑定、相同语义重试或读取操作都不推进 epoch。批准事务必须从当前正式状态计算下一 epoch，并通过 revision、`boundary_state_fingerprint`、Proposal fingerprint 与唯一 Decision 约束拒绝并发旧写。

## Agent 与自动化边界

Agent 可以读取正式业务边界、提交源码变化或提出待审建议，但不能 approve/reject、直接写 Actor/Action/Permission、修改 `policy_epoch`、选择验证考题或形成 Verdict。MCP、CLI 与 Machine 输出不提供旧 Permission writer；API 路由也不能保留旧 matrix approve、candidate decide 或 compatibility wrapper。

当前完整新检查主链尚未重新接入。不要为了让旧 CheckPreview、Compiler 或 L5 继续工作而把 Permission v2 转写回旧表；1.1.0 的 `/tests` 与 `/changes` 可以明确不可用，但不能 dual write。

## 官方 recipe 内部资产

`OfficialBoundaryRecipe` 是有限、公开的样例材料，只生成普通 Proposal command，不是业务 Core model，也不自动批准。1.1.0 保留该纯函数和 unit test，但普通 Router、service 便捷入口、前端 API 与页面 CTA 均不暴露它。未来只有正式 Sample context 可以把 recipe 送入普通 create-proposal + approve 路径；不得根据 project name 猜 Sample。

## 怎么验证

优先运行当前直接测试：

```powershell
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File .\scripts\dev.ps1 test tests/backend/core/test_business_boundary.py tests/backend/workflows/business_boundaries tests/backend/api/test_business_boundaries.py tests/architecture/test_business_boundary_v2.py
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File .\scripts\dev.ps1 frontend-test src/features/boundaries/BusinessBoundaryPage.test.tsx src/app/ControlShell.test.tsx
```

同时检查 Proposal 不可变、Approval 原子、正式 Permission 不含 Candidate、TestIdentity 只引用 Actor revision、旧数据库只读拒绝、旧 writer 路由未注册。公共 Schema 或生成参考发生真实漂移时才使用 `dev.ps1 schema -Update` 或 `docs -Update`；否则只运行只读检查。

## 相关真源

- [应用接入与检查主流程](../../01_系统地图/应用接入与检查主流程.md)
- [数据与持久化](../../01_系统地图/数据与持久化.md)
- [权限验证与结果](../../01_系统地图/权限验证与结果.md)
- [控制面与 Machine 输出协议](../../03_参考手册/协议/控制面与Machine输出协议.md)
- [验证与测试](../../04_工程约束/验证与测试.md)
