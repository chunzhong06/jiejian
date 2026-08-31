# 修改 Agent 变更影响

> 状态：CURRENT。用于修改源码版本快照、Agent 变化声明、权限实现影响、修复要求引用、重验计划、变化感知的检查提交，以及结果和历史中的变化摘要。

## 先确认边界

Agent 只能说明“这次修改是为了什么”，并可附上有界的相对路径线索。路径不是事实，也不能决定检查范围。界鉴会在既有源码只读授权内重新分析项目，按服务端形成的前后快照计算真实增删改，再把变化关联到当前 `PermissionIntentRevision` 的实现映射。

人的 ALLOW/DENY、规则退休和正式实现映射仍只由 Human GUI 批准。MCP、CLI、Machine、模型、Compiler 和 Run 都不能借变化分析推进 `policy_epoch`，也不能把 Agent 提供的权限 ID、Case ID 或 Effect ID 当作重验范围。

## 当前闭环

```text
jiejian_change_submit（PREPARE，可选携带权威 RepairContract 引用）
  → 服务端按 source Run/Finding 重建 RepairContract 并核对 fingerprint
  → 保存 ChangeManifest
  → 受控源码重分析
  → SourceRevisionSnapshot 前后比较
  → SourceChangeSet 记录真实增删改
  → ChangeImpactAssessment 关联当前权限实现证据
  → SourceRevalidationInspection 核对当前源码/权限/binding
  → ProjectRevalidation 组合准备度与可信结果
  → ProjectRepair 组合修复要求、关联变化与独立复验
  → READY inspection 形成 RevalidationPlan
  → jiejian_check_prepare / jiejian_check_run(change_id)
  → submit 前只读核对 live 源码与登记基线
  → PersistedExecutionRequest.source_fingerprint
  → PersistedExecutionRequest.change_context
  → 可选 PersistedExecutionRequest.repair_context
  → ResultPresentation / HistoryView / report.json
```

`jiejian_change_show` 是 READ 工具，返回变化数量、影响计数、待复核权限、安全文案，以及 Agent 声明和界鉴实际确认的新增/修改/删除相对路径。路径只允许位于已授权源码根下；工具不返回绝对路径、源码正文、diff、hash、Git 信息或命令输出。GUI 默认只显示数量，用户展开“查看变化明细”后才显示这些相对路径。修复型变化只保存 `RepairContractReference`，不复制合同，也不接受文件、函数、行号或补丁建议；提交与后续检查都会从已发布事实重新校验引用。

普通产品的修复续接只读取 `ProjectRepair`。当状态为 READY_TO_VERIFY 时，验证入口优先使用该修复任务关联的 change ID；没有正式修复任务时，才使用普通 `ProjectRevalidation=READY` 的 change ID。Official Sample 编排中的 repair ID 不进入这项选择。工作台的 Delivery Check 只能由用户显式点击触发，每次重新读取 live 服务端事实，前端不保存上次结论。

## 代码与测试入口

| 修改内容 | 生产真源 | 直接测试 |
| --- | --- | --- |
| 快照、Manifest、diff、影响与重验模型 | `product/backend/core/source_changes.py` | `tests/backend/workflows/source_changes/test_source_changes.py` |
| SQLite 聚合与 migration | `product/backend/infra/storage/source_changes.py`、`product/backend/migrations/versions/0005_source_change_impacts.py`、`0006_repair_contract_reference.py` | Storage 与 migration 测试 |
| 重分析、影响评估与唯一重验 inspection | `product/backend/workflows/source_changes.py` | source changes workflow 测试 |
| 项目重验状态 | `product/backend/workflows/projects/revalidation.py` | `tests/backend/workflows/projects/test_revalidation.py` |
| 项目修复闭环 | `product/backend/workflows/projects/repair.py` | `tests/backend/workflows/projects/test_repair.py` |
| MCP 与只读 API | `product/backend/api/mcp.py`、`product/backend/api/routers/source_changes.py` | `test_mcp.py`、`test_source_changes.py`、Oracle invariant |
| 检查准备、提交和 Run 冻结 | `product/backend/workflows/security_setup/checks.py`、`product/backend/workflows/runs/execution.py`、`product/protocols/execution_request.py` | checks、request store、source changes 测试 |
| 显式交付证明 | `product/backend/workflows/projects/delivery.py`、`product/backend/api/routers/projects.py` | `tests/backend/workflows/projects/test_delivery.py`、API/MCP 测试 |
| 修复合同重建与复验 | `product/backend/workflows/results/repair.py`、`product/backend/core/repair.py` | `test_repair_contracts.py`、官方 Sample 修复编排测试 |
| 工作台、结果与历史 | `WorkbenchPage`、`CheckResultsPage`、`CheckHistoryPage` | 各页面同目录测试 |

## 影响分类

- `DIRECTLY_AFFECTED`：真实变化路径与当前 action 或 role 的实现证据直接相交。这些权限至少进入本次必需重验集合。
- `MAPPING_REVIEW_REQUIRED`：实现证据缺失、候选失效、binding 非 CURRENT，或没有可靠基线。检查必须关闭执行，先回到权限页由人复核正式映射。
- `NO_DIRECT_EVIDENCE`：当前没有找到与已知权限实现直接相交的变化。这不是安全结论，产品文案必须保留“这不代表其他未建模影响一定不存在”。

当前执行仍使用完整 ACTIVE/CURRENT Coverage，不根据影响结果裁剪 Runner 用例。`required_intent_ids` 只说明本次至少需要重验哪些权限，不能替代现有 Coverage、ALLOW 控制或 DifferentialPlan。

`SourceRevalidationInspection` 固定只有 READY、NO_BASELINE、SOURCE_STALE、POLICY_STALE 和 MAPPING_REVIEW_REQUIRED。`revalidation_plan()` 必须先调用 inspection，只有 READY 才能形成计划，不能在计划入口复制第二套算法。`ProjectRevalidation` 再严格按“无变化、映射待审、stale、同变化可信结果、准备未完成、可重验”顺序形成 NO_CHANGE、REVIEW_REQUIRED、STALE、VERIFIED、PREPARATION_REQUIRED 或 READY；旧结果不能掩盖后续源码或权限漂移。

## 冻结与历史

所有新检查提交都会在创建 Job/Run 前重新扫描当前源码。扫描失败或 live 指纹偏离登记基线时直接阻断；通过后，项目级源码指纹写入格式 2 的 `PersistedExecutionRequest` 顶层。变化感知的提交再由 `ChangeVerificationContext` 冻结 `change_id`、影响指纹和排序去重后的必需权限 ID。修复型变化还冻结独立 `RepairVerificationContext`，其中只保留权威引用、原权限身份、必须消失的效果、必须保留的 ALLOW 控制和原关键证据标准。Runner 与 Evidence 不接收文件清单、源码内容或补丁建议，也不在执行时重新读取 live 变化记录。

结果和历史从该 Run 的冻结请求投影权限版本、代码变化重验标记和必需权限数量。普通页面不显示内部权限 ID 或任何指纹；后续源码、权限或 binding 变化不能改写已经提交的 Run。

## 修改时逐项核对

1. `claimed_paths` 仍是受限相对路径线索，绝对路径、父目录跳转和空路径段继续拒绝。
2. 真实 diff 只由两份服务端快照计算；mtime、Agent 声明和 Git 状态不参与。
3. 没有基线、源码再次漂移、权限规则版本漂移或实现绑定非 CURRENT 时 fail closed。
4. Agent rebind 只形成 `IntentProposal`；只有 GUI 批准事务可以把 binding 恢复为 CURRENT，且纯重绑不推进 `policy_epoch`。
5. `check_prepare` 与 `check_run` 只接受可选 `change_id`，不新增选择权限、Case、Effect、Profile 或文件范围的参数。
6. `ChangeVerificationContext` 保持嵌套对象，不单独增加 `schema_version`；公共执行请求变化后同步 checked-in Schema。
7. `RepairContractReference` 必须由服务端重建校验后才能持久化；后续 check prepare/run 继续复用同一 `change_id`，不增加修复专用运行入口。
8. 工作台默认只显示有界业务摘要；展开变化明细时才显示 Agent 声明和界鉴实际确认的相对路径。结果和历史不显示 change ID、权限内部 ID 或指纹，并覆盖无基线、直接影响、映射待审和无直接证据四种情况。
9. ProjectPreparation、ProjectReadiness、Guidance、ProductStatus、变化页和验证入口只消费 inspection/ProjectRevalidation，不按 `complete`、mapping count 或 change ID 比较另算状态。
10. `ProjectRepair` 只投影已发布修复要求、关联变化、ProjectRevalidation 与复验事实；`DeliveryCheck` 按 live 源码、当前权限身份、修复/重验状态和最近可信结果形成一次只读、fail-closed 的交付证明。

## 最小验证

按实际修改选择最小集合：

```powershell
.\scripts\dev.ps1 test tests/backend/workflows/source_changes/test_source_changes.py
.\scripts\dev.ps1 test tests/backend/workflows/projects/test_revalidation.py tests/backend/workflows/projects/test_preparation.py tests/backend/workflows/control/test_status.py
.\scripts\dev.ps1 test tests/backend/workflows/results/test_repair_contracts.py tests/backend/workflows/test_official_sample_repair.py
.\scripts\dev.ps1 test tests/backend/api/test_mcp.py tests/backend/api/test_permission_oracle_invariant.py
.\scripts\dev.ps1 test tests/backend/workflows/security_setup/test_checks.py tests/backend/workflows/results/test_result_presentation.py tests/backend/workflows/results/test_history.py
.\scripts\dev.ps1 frontend-test src/features/workspace/WorkbenchPage.test.tsx src/features/checks/CheckResultsPage.test.tsx src/features/checks/CheckHistoryPage.test.tsx
.\scripts\dev.ps1 schema
.\scripts\dev.ps1 docs
```

协议模型、源码注释和产品文案变化还要分别执行项目的 Schema、注释与文档治理检查。不要为了变化闭环启动真实外部 Agent 或扩大到完整 L4/L5。
