# ExecutionProfile 与执行配置

> 状态：CURRENT。本文区分用户配置、冻结执行输入和执行请求；字段约束以代码和 Schema 为准。

## 目的与消费者

ExecutionProfile 是用户可管理的执行配置，供应用接入、CLI、GUI、CI 和 ApplicationCore 登记与提交。`ExecutionProjectSnapshot` 和 `PersistedExecutionRequest` 是提交后不可变的执行输入，供 Worker/Runner 消费。

## 协议边界

Profile 包含 project、Business/Auth/Observer scope、`HttpIdentityBinding`、Contract 引用、subject/workflow/effect/Observer bindings、seed、case budget、关系深度和持续时间限制，以及受控 secret refs。它不内嵌可变 Contract 或秘密值。

`HttpWorkflowBinding` 只允许一个 TARGET，并以 SETUP/TARGET/CLEANUP、受控请求模板、ValueSlot、确定性结果分类、基线投影和清理策略表达状态化流程。身份 bootstrap 与业务流程分离；Cookie jar 只在 Runner 内存中按 identity 隔离。

登记时必须确认 ACTIVE Contract、项目绑定、target scope、bindings、Observer 和 fingerprint。Profile 变化、Contract 漂移、plan/binding hash 不一致或未知结构默认拒绝。

提交时冻结完整 Contract、Coverage/PermissionMutationPlan、DifferentialExperimentPlan、workflow/effect bindings、目标范围、预算、身份和 fingerprint，形成 `ExecutionProjectSnapshot`，再写入 `PersistedExecutionRequest`。执行期间不重新读取当前 Profile 或治理表。

## 生命周期与数据流

```text
用户配置 → Profile 校验/登记
  → Contract/plan/binding fingerprint
  → ExecutionProjectSnapshot
  → PersistedExecutionRequest
  → Worker/Runner
```

Profile 是配置事实，快照是执行事实；更新 Profile 不改变历史 Run 或已发布 Evidence。

GUI 读取执行配置时只使用专用摘要投影：返回动作对应的目标步骤、SETUP/CLEANUP 数量、基线完整性模式，以及效果绑定的必需/佐证通道与闭合策略。该投影不返回身份凭据、Cookie、Authorization、secret ref 或完整请求模板，也不替代 Profile 和冻结快照本身。

## 失败与安全语义

未绑定 Contract、非 ACTIVE 版本、目标范围不明确、secret ref 非法、预算越界、指纹漂移或解析失败均 fail closed。秘密值不进入 Profile 公共 JSON、ExecutionRequest、Evidence、日志或报告。

## 版本规则与 Schema 真源

状态化 HTTP 引入不兼容 binding 后，`ExecutionProfile` 与 `PersistedExecutionRequest` 只接受单一当前版本。Schema/protocol 版本表示机器格式，不表示产品代际。严格模型和 canonical/hash 以：

- `product/protocols/execution_profile.py`
- `product/protocols/execution_request.py`
- `product/protocols/schemas/execution/execution-profile.schema.json`

为准。旧开发 Profile、Run 和请求格式不兼容读取。

## 相关真源

- [安全意图与验证架构](../02_架构设计/安全意图与验证架构.md)
- [执行与观察架构](../02_架构设计/执行与观察架构.md)
- [契约与执行快照绑定](../03_架构决策/ADR-0030-契约与执行快照绑定.md)
