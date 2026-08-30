# Runner 执行协议

> 状态：CURRENT。本文解释跨进程 Runner 边界；字段约束以 `product/protocols` 和 JSON Schema 为准。

## 目的与消费者

协议连接 ApplicationCore/Worker、隔离 Runner、Observer 和 publication。Worker 写入冻结请求，Runner 读取 `RunnerInput`/`PersistedExecutionRequest`，Runner 返回 `Evidence` 与 `RunnerResult`，Worker 校验后发布。

## 先理解：Runner 不是第二个控制面

用户在 GUI 或 CLI 点击“开始检查”后，ApplicationCore 只冻结要执行的事实并创建 Job。独立 Worker claim 当前 attempt，独立 Runner 才能产生目标流量、调用 Observer、恢复现场和形成候选结果。API 进程不能为了减少进程数直接执行 Web 请求；Runner 也不能自行把本地文件宣布为已发布结果。

同一次运行要区分三件事：Job/Run 生命周期说明是否执行完成，`RunnerResult` 说明本 attempt 如何结束，Evidence/Verification 才说明权限安全三态。进程正常退出不等于 PASS；清理失败也不能覆盖更早发生的主错误。

## 协议边界

- `PersistedExecutionRequest` 是执行真源，保存项目、Contract/plan/孪生快照、workflow/effect bindings、身份、目标范围、预算、Observer 引用和指纹。代码变化重验可以额外冻结最小 `ChangeVerificationContext`；Runner 不读取变化数据库，也不接收文件列表、diff 或源码正文。
- `RunnerInput` 绑定 run、job、attempt、lease owner、fencing token、创建时间、预算和项目快照。
- `Evidence` 绑定不可变 case/twin snapshot、ExecutionFact、ObservationFact、SecurityEffectFact、基线/闭合状态、verdict 和 evidence hash。
- `RunnerResult` 返回结果类型、生命周期状态、Job 状态、Verdict、清理结果、错误和覆盖计数。失败时 `RunnerError` 分别保存主错误 `code`、有限 `phase`、可选稳定 `cause_code` 和可重试性；`CleanupResult.issues` 另存现场恢复、身份关闭、Runtime 关闭或进程树清理问题，不覆盖主错误。
- Worker/Runner 通过稳定 ID、attempt 和 fencing token 关联；Runner 不自行声明最终发布完成。

## 生命周期与数据流

```text
ApplicationCore → PersistedExecutionRequest
  → Job/lease/fencing → Worker
  → RunnerInput → 受控 Runner → Case Orchestrator
  → TargetRuntimeRegistry → Web Target Runtime
  → bootstrap / SETUP / BASELINE / BEFORE / TARGET / AFTER / EVENTUAL / Cleanup
  → ExecutionFact + ObservationFact + SecurityEffectFact → Evidence
  → RunnerResult/staging → Worker 校验 → publication
```

目标流量只在受控 Runner 内产生。通用 Orchestrator 的输入输出不含 HTTP 类型；当前 Web Runtime 负责全部 HTTP 细节。Runner 退出、取消、超时或清理失败必须返回可区分的结果，不得将基础设施失败伪装成安全 PASS。主流程失败后又发生 cleanup 问题时保留原主错误和阶段；只有没有主错误而 cleanup 失败时，主错误才是 `CLEANUP_FAILED`。`finished_at_us` 只能在全部观察、Evidence 准备和 Cleanup 完成后取得。

Evidence 语义 hash 在构造前按稳定键归一 observations、outcomes、observation facts 与 reason codes；归一化只消除输入顺序差异，不改变事实、Verdict 或公共 Schema。Worker 关闭期间若取消请求发现 Job 已是终态，按幂等成功继续进程树回收；其他异常仍按原错误边界处理。

## 运行中展示旁路

`attempt/progress.jsonl` 是内部、可删除、非权威的运行中展示旁路，不属于 `RunnerResult`、Evidence 或 publication 协议。每行是格式 1 的严格 `RunnerProgressEvent` 根，只允许 `schema_version`、连续 `sequence`、受限 `case_id`/`action_id`、可空 `twin_role`、`phase`、`state` 和 `recorded_at_us`；差分角色只允许 ALLOW control 或 DENY variant，阶段只允许 PREPARE、BASELINE、TARGET、OBSERVE、VERIFY、RECOVERY，状态只允许 STARTED、COMPLETED。

writer 最多追加 256 条、64 KiB、单行 2 KiB，任一构造、校验、文件或预算失败都静默禁用自身，不影响 Runner 主流程。reader 只从数据库当前 Job 的 attempt/fencing 推导固定文件，要求完整换行、逐行 strict 校验和从 1 连续的序号；文件缺失、截断、超限或篡改统一返回空事件。该旁路禁止保存 URL、请求或响应、实际身份或资源值、秘密、错误正文、reason code、HTTP 状态、安全效果或 Verdict，也不得被 Worker 用来完成 Job、发布结果或恢复现场。

## 失败与安全语义

未知 TargetType、请求结构、ID 关联、fencing token、预算、路径、大小、秘密、hash 或退出状态均严格失败。Worker 只接受当前 attempt 的结果；过期租约、重复完成和孤儿 staging 不得覆盖已发布事实。

秘密只通过最小环境和受控引用注入，秘密值不进入协议、Evidence、日志、异常或报告。主进程及其 Worker、Runner、Recording、Observer、Artifact Scan 使用同一已确认 Python，并进入可证明回收的内核进程树。HTTP scope、重定向、私网、请求/响应预算和清理由 Web Runtime 与 Runner 边界执行。

## 版本规则与 Schema 真源

当前 `PersistedExecutionRequest`、`RunnerInput`、`Evidence` 与 `RunnerResult` 都以字符串 `schema_version="1"` 作为 Web V1 发布基线。每个 reader 只接受各自唯一当前格式，`schema_version` 是机器格式版本，不表示产品代际。协议正文不复制完整字段表，严格模型、required、枚举和 canonical 规则以：

- `product/protocols/runner/`
- `product/protocols/execution_request.py`
- `product/protocols/schemas/runner/`

为准。旧开发请求、结果和 wire format 不兼容读取。

`RunnerProgressEvent` 的严格模型和唯一 reader 位于 `product/backend/infra/runtime/runner/progress.py`；它没有 checked-in Runner Schema，因为它不是跨进程结果或 publication 输入。字段变化必须同步该 reader、只读 API 和前端类型，不能通过扩展 `RunnerResult` 偷渡运行中状态。

## 查询入口

| 要查什么 | 当前真源 |
| --- | --- |
| 冻结执行请求与 Runner 根模型 | `product/protocols/execution_request.py`、`product/protocols/runner/` |
| 独立 Runner 进程与 Case 编排 | `product/backend/infra/runtime/runner/` |
| Worker claim、attempt、fencing 与发布 | `product/backend/infra/runtime/worker/`、`product/backend/infra/runtime/jobs/` |
| Web Target Runtime | `product/backend/infra/execution/web/` |
| Runner/Worker 直接测试 | `tests/backend/infra/runtime/runner/`、`tests/backend/infra/runtime/worker/` |

## 相关真源

- [执行与观察架构](../../01_系统地图/执行与观察.md)
- [工件发布、完整性与恢复边界](../../05_设计依据/ADR-0033-工件发布完整性与恢复边界.md)
- `product/protocols/runner/`
- `product/protocols/execution_request.py`
