# Runner 执行协议

> 状态：CURRENT。本文解释跨进程 Runner 边界；字段约束以 `product/protocols` 和 JSON Schema 为准。

## 目的与消费者

协议连接 ApplicationCore/Worker、隔离 Runner、Observer 和 publication。Worker 写入冻结请求，Runner 读取 `RunnerInput`/`PersistedExecutionRequest`，Runner 返回 `Evidence` 与 `RunnerResult`，Worker 校验后发布。

## 协议边界

- `PersistedExecutionRequest` 是执行真源，保存项目、Contract/plan/孪生快照、workflow/effect bindings、身份、目标范围、预算、Observer 引用和指纹。
- `RunnerInput` 绑定 run、job、attempt、lease owner、fencing token、创建时间、预算和项目快照。
- `Evidence` 绑定不可变 case/twin snapshot、ExecutionFact、ObservationFact、SecurityEffectFact、基线/闭合状态、verdict 和 evidence hash。
- `RunnerResult` 返回结果类型、生命周期状态、Job 状态、Verdict、清理结果、错误和覆盖计数。
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

目标流量只在受控 Runner 内产生。通用 Orchestrator 的输入输出不含 HTTP 类型；当前 Web Runtime 负责全部 HTTP 细节。Runner 退出、取消、超时或清理失败必须返回可区分的结果，不得将基础设施失败伪装成安全 PASS。`finished_at_us` 只能在全部观察、Evidence 准备和 Cleanup 完成后取得。

## 失败与安全语义

未知 TargetType、请求结构、ID 关联、fencing token、预算、路径、大小、秘密、hash 或退出状态均严格失败。Worker 只接受当前 attempt 的结果；过期租约、重复完成和孤儿 staging 不得覆盖已发布事实。

秘密只通过最小环境和受控引用注入，秘密值不进入协议、Evidence、日志、异常或报告。主进程及其 Worker、Runner、Recording、Observer、Artifact Scan 使用同一已确认 Python，并进入可证明回收的内核进程树。HTTP scope、重定向、私网、请求/响应预算和清理由 Web Runtime 与 Runner 边界执行。

## 版本规则与 Schema 真源

状态化工作流与效果事实使 RunnerInput、Evidence 和 RunnerResult 升级为单一当前格式；`schema_version` 是机器格式版本，不表示产品代际。协议正文不复制完整字段表，严格模型、required、枚举和 canonical 规则以：

- `product/protocols/runner.py`
- `product/protocols/execution_request.py`
- `product/protocols/schemas/runner/`

为准。旧开发请求、结果和 wire format 不兼容读取。

## 相关真源

- [执行与观察架构](../02_架构设计/执行与观察架构.md)
- [工件发布、完整性与恢复边界](../03_架构决策/ADR-0033-工件发布完整性与恢复边界.md)
- `product/protocols/runner.py`
- `product/protocols/execution_request.py`
