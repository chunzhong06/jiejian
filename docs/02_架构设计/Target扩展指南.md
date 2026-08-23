# Target 扩展指南

> 状态：CURRENT。本文冻结 Web V1 的 Target Runtime 接入边界，并说明未来增加下一种 Target 时允许变化与禁止变化的范围。

## 职责

说明 Target Runtime Port、唯一生产组合点、容器装配与未来 Target 的最小接入步骤，并列出不得复制的共享安全层。

## 非职责

- 不宣称 CLI、MCP 或本地进程 Target 已实现。
- 不定义未来 CLI 的 OS 沙箱、命令协议或产品入口细节。
- 不修改 Permission、Verification、Evidence、Finding、Report 或 Gate 语义。
- 不复制 Runner、Observer 或 Web wire 的完整字段表。

## 真源

当前代码真源是 `product/backend/infra/execution/port.py`、`registry.py`、`web/`、`infra/runtime/runner/`、`workflows/context.py`、`workflows/worker_container.py` 与 `product/protocols/web/`。

## 目的

保证下一种 Target 只增加自己的 wire、Runtime、观察桥、安全执行舱和注册，不复制通用 Case 阶段或结果链。

## 当前生产能力

生产 `TargetType` 只有 `WEB`。`TEST_FAKE` 只允许作为测试内 Registry kind；`CLI_APPLICATION`、`MCP_AGENT`、`TEST_FAKE` 均不得进入生产枚举、Schema、Sample、数据库或产品目录。

当前 Web wire 类型迁移固定为：

| 旧名称 | 当前名称 |
| --- | --- |
| `ExecutionProfile` | `WebExecutionProfile` |
| `ExecutionIdentity` | `WebExecutionIdentity` |
| `ExecutionProjectSnapshot` | `WebExecutionSnapshot` |

迁移只明确职责名称和模块归属，不改变合法 Web JSON 字段、canonical 字节、安全语义或现有稳定身份。

## Target Runtime Port

`TargetRuntimeFactory` 以 bounded `kind` 注册，并只提供：

```text
create(snapshot: ExecutionSnapshotView, context: TargetRuntimeContext) -> TargetRuntime
```

一个 attempt 只创建一个 `TargetRuntime`：

```text
open_case(case, action) -> TargetCaseSession
close() -> None
```

每个 Case 使用独立 `TargetCaseSession`：

```text
prepare() -> None
observe_target(spec, binding, correlation, phase) -> TargetObservationResult | None
evaluate_baseline(baseline_envelopes) -> TargetBaselineResult
execute_target() -> ExecutionFact
resolve_execution(observations) -> ExecutionFact
build_disclosure_proof(effect, resource_id, observations) -> DisclosureProof | None
cleanup() -> None
```

`execute_target()` 每个 Session 恰好执行一次；`resolve_execution()` 只能解释已有目标响应和观察事实，不能再次操作目标。任何阶段失败都由通用 Case Orchestrator 在 `finally` 中调用 `cleanup()`。

`ExecutionSnapshotView` 只暴露 `project_id`、`target_type`、`contract`、`plan`、`differential_plan`、`observers`、`effect_bindings` 和 `observer_bindings`。`TargetRuntimeContext` 只包含 attempt 环境映射、staging、微秒时钟与取消检查。两者均不携带 HTTP Client、身份秘密、数据库、Finding 或 Report 服务。

## 关键数据流

```text
Runner composition
  → TargetRuntimeRegistry.create(kind, snapshot, context)
  → TargetRuntime.open_case
  → CaseOrchestrator 固定阶段
  → TargetCaseSession 产生 ExecutionFact / 目标观察
  → 共享 SecurityEffect 聚合与 Verification
  → Evidence / RunnerResult / publication / ResultFinalizer
```

## 唯一组合点与容器

`product/backend/infra/runtime/runner/composition.py` 是生产 Web Runtime 与共享 Observer 的唯一注册点。Registry 和通用 Runner 不导入 Web Runtime；API、CLI 和 Verification 也不导入 Target Runtime 或具体 Observer。

GUI、界鉴 CLI 与 API 使用完整 `ApplicationCore`，其装配清单是 Storage、缓存、项目、Contract、Execution、Recording、Onboarding、LLM 与完整 `ResultServices`。Worker 使用独立 `WorkerContainer`，只装配 RuntimePaths/Storage、Job Target、Job Attempts/Queue、ExecutionRequestStore、RunPublisher/Reconciler、完整 `ResultServices` 和 `WorkerHandlerFactory`。两者共享完整工厂和服务对象，不使用继承、`_minimal` 或构造中途返回。

`ResultServices` 固定按以下顺序完整构造：

```text
PublishedResultReader → FindingMaterializer → FindingQueries
→ RegressionGate → ReportBuilder → ResultFinalizer
```

`ResultFinalizer` 在构造时直接取得 `ReportBuilder`，不存在后置依赖回填。

测试中的 `TEST_FAKE` 只在 `tests/backend/infra/runtime/runner/test_target_runtime_fake_orchestration.py` 注册。它使用测试专用 snapshot、runtime 和 session，经同一个 `CaseOrchestrator` 形成 `ExecutionFact`、`SecurityEffectFact`、`CaseResult` 并调用现有 `evaluate_permission_case`；它不进入生产 `TargetType`、Schema、Web Runtime 或 Verification。

## 增加下一种 Target

未来 CLI Target 至少需要独立新增：

- CLI wire snapshot/profile/identity/binding，并以明确的不兼容 Schema 扩展当前 Runner 输入；
- `CliTargetRuntimeFactory`、`CliTargetRuntime` 与每 Case 独立 Session；
- CLI 拥有的目标相关观察桥，或确有跨 Target 价值的新共享 Observer Adapter；
- Runner 组合入口中的显式生产注册；
- CLI 自身的授权范围、预算、OS 执行舱、清理和秘密边界；
- 对应协议、直接测试和真实 L5。

这只证明扩展方式，不代表 CLI 已经具备安全沙箱。未来 Target 不得修改或复制：

```text
PermissionContract / PermissionMutationPlan / DifferentialExperimentPlan
CaseOrchestrator 的固定安全阶段
ExecutionFact / ObservationFact / SecurityEffectFact
Verification / Evidence / RunPublisher
Finding / Report / Gate
```

## 冻结结果链

Runner 仍只产生 RunnerResult/Evidence；RunPublisher 原子发布并创建 `run_finalizations`；ResultFinalizer 物化 Finding 和 BASE Report；Gate 产生独立 GATE Report；API/CLI 的 GET 保持只读。Target Runtime 不得生成 Verdict、Finding、Report 或 Gate，也不得建立第二套结果链。

## 关键不变量

- Registry 未显式注册、kind 非 bounded stable string 或重复注册时立即失败。
- 生产组合只注册 `WEB`；只有 `runner/composition.py` 导入并注册 `WebTargetRuntimeFactory`。
- 通用 `executor`、`case_orchestrator`、`result_builder` 和 `staging` 不导入 Web wire 或 Web Runtime。
- 每个 Case 的 TARGET 只执行一次，`resolve_execution` 不发送第二次目标请求，异常路径仍执行 cleanup。
- Web Runtime 只产生目标事实，不决定 Verdict；Verification 不依赖任何 Runtime 或 Adapter。

## 失败语义

未知 kind、重复 Factory、错误 Runtime 形状、快照不匹配、目标范围、预算、观察完整性、基线或 cleanup 失败均 fail closed。新增 Target 缺少自己的范围、预算、清理、秘密或隔离设计时不得注册为生产能力。

## 安全约束

Target Runtime 只获得当前 attempt 的冻结快照、受限环境、staging、时钟和取消检查。API、CLI、GUI 不直接导入或调用 Runtime；高风险目标操作仍只发生在 Worker/Runner 进程边界内。测试 Fake 不能被描述为 CLI 沙箱或生产安全能力。

## 兼容与版本

当前生产机器协议只表达 Web Target。未来 Target 通过不兼容 Schema 和显式 Registry 注册加入，不向旧 Schema 增加可空万能字段、空枚举或 alias；旧 Router、旧 Web 类型名和旧模块不兼容保留。

## 相关真源

- [系统总体架构](系统总体架构.md)
- [执行与观察架构](执行与观察架构.md)
- [安全意图与验证架构](安全意图与验证架构.md)
- [Runner 执行协议](../04_协议与数据/Runner执行协议.md)
- `tests/backend/infra/execution/`
- `tests/backend/infra/runtime/runner/`
- `tests/architecture/test_dependencies.py`
