# ExecutionProfile 与执行配置

> 状态：CURRENT。本文区分用户配置、冻结执行输入和执行请求；字段约束以代码和 Schema 为准。

## 目的与消费者

ExecutionProfile 是用户可管理的执行配置，供应用接入、CLI、GUI、CI 和 ApplicationCore 登记与提交。`ExecutionProjectSnapshot` 和 `PersistedExecutionRequest` 是提交后不可变的执行输入，供 Worker/Runner 消费。

## 协议边界

Profile 包含 project、当前 Web target、identities、Contract 引用、subject/action bindings、Observer bindings、seed、case budget、关系深度和持续时间限制，以及受控 secret refs。它不内嵌可变 Contract、Flow 或秘密值。

登记时必须确认 ACTIVE Contract、项目绑定、target scope、bindings、Observer 和 fingerprint。Profile 变化、Contract 漂移、plan/binding hash 不一致或未知结构默认拒绝。

提交时冻结完整 Contract、Coverage/PermissionMutationPlan、bindings、目标范围、预算、身份和 fingerprint，形成 `ExecutionProjectSnapshot`，再写入 `PersistedExecutionRequest`。执行期间不重新读取当前 Profile 或治理表。

## 生命周期与数据流

```text
用户配置 → Profile 校验/登记
  → Contract/plan/binding fingerprint
  → ExecutionProjectSnapshot
  → PersistedExecutionRequest
  → Worker/Runner
```

Profile 是配置事实，快照是执行事实；更新 Profile 不改变历史 Run 或已发布 Evidence。

## 失败与安全语义

未绑定 Contract、非 ACTIVE 版本、目标范围不明确、secret ref 非法、预算越界、指纹漂移或解析失败均 fail closed。秘密值不进入 Profile 公共 JSON、ExecutionRequest、Evidence、日志或报告。

## 版本规则与 Schema 真源

当前 `ExecutionProfile` Schema 主要为 2；`PersistedExecutionRequest` 当前协议主要为 2。Schema/protocol 版本表示机器格式，不表示产品代际。严格模型和 canonical/hash 以：

- `product/protocols/execution_profile.py`
- `product/protocols/execution_request.py`
- `product/protocols/schemas/execution/execution-profile.schema.json`

为准。旧开发 Profile、Run 和请求格式不兼容读取。

## 相关真源

- [安全意图与验证架构](../02_架构设计/安全意图与验证架构.md)
- [执行与观察架构](../02_架构设计/执行与观察架构.md)
- [契约与执行快照绑定](../03_架构决策/ADR-0030-契约与执行快照绑定.md)
