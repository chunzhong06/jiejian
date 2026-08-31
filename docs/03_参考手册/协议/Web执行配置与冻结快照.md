# Web 执行配置与冻结快照

> 状态：CURRENT。本文区分 Web 用户配置、冻结执行输入和持久请求；字段约束以代码和 Schema 为准。

## 目的与消费者

`WebExecutionProfile` 是内部 Web 执行配置根文档，由 SecuritySetupCompiler 从当前权威事实内容寻址生成，并只经 ApplicationCore/ExecutionWorkflow 登记与提交；产品控制面不接受用户上传、选择或改写 Profile。`WebExecutionSnapshot` 和 `PersistedExecutionRequest` 是提交后不可变的执行输入，供 Worker/Runner 消费。

## 先理解：Profile 是当前配置，Snapshot 是历史执行事实

普通用户完成 Flow、安全准备与权限要求后，确定性编译器生成当前唯一 Profile。点击开始检查时，ApplicationCore 重新验证当前 Contract、身份代表、target scope、workflow/effect/Observer bindings 与所有指纹，然后冻结 Snapshot 和持久执行请求。之后即使账号或权限规则变化，已经提交的 Run 仍读取自己的不可变快照。

Profile 可以含受控 secret ref，但不含秘密值；Snapshot 固定“当时准备执行什么”，不在 Runner 中重新查询当前 GUI 状态。这个区分保证历史 Evidence 可以解释，也避免运行中配置漂移。

## 协议边界

Profile 包含 project、Business/Auth/Observer scope、`WebExecutionIdentity`、`HttpIdentityBinding`、Contract 引用、subject/workflow/effect/Observer bindings、seed、case budget、关系深度和持续时间限制，以及受控 secret refs。它不内嵌可变 Contract 或秘密值。

`HttpWorkflowBinding` 只允许一个 TARGET，并以 SETUP/TARGET/CLEANUP、受控请求模板、ValueSlot、确定性结果分类、基线投影和清理策略表达状态化流程。身份 bootstrap 与业务流程分离；Cookie jar 只在 Web Runtime 内存中按 identity 隔离。已确认 `RecoveryBindingKind.NOT_REQUIRED` 的纯 GET/HEAD 数据披露动作使用 `ResetStrategyKind.NOT_REQUIRED`：仍执行基线、Observer 与完整性校验，但不发送清理请求；该策略不得包含状态变化或 CLEANUP 步骤，不能作为缺失恢复能力的兜底。

`HttpOutcomeClassifier.completion_binding` 只声明既有 Observer requirement，不自行读取任务或形成 Verdict。普通生成配置若把 202 列为 TARGET accepted status，会绑定本地 AsyncTask requirement；执行时仍必须由同一 Case 的异步终态事实明确证明完成，202 才能成为 ACCEPTED。没有绑定或终态证明时保持 UNKNOWN。

普通生成配置可使用 `PREPARED_COOKIE_SESSION`：Profile 只保存有限 Cookie 元数据与 `env:` 引用，正文由主进程从共享 SecretStore 按冻结请求需要最小注入。Owner API Observer 可以通过 `identity_id` 复用同一已准备身份；`credential_ref` 与 `identity_id` 互斥。

登记时必须确认 ACTIVE Contract、项目绑定、target scope、bindings、Observer 和 fingerprint。普通生成配置还必须匹配当前 ApplicationUnderstanding、编译时选定的 TestIdentity 代表、Flow、测试安全事实与组级 PermissionIntent 的 authority fingerprint；代表补充或替换不会改变 PermissionIntent，但会产生新的生成配置身份。任一配置输入变化后，即使旧文件仍存在也拒绝构造或提交请求。Profile 变化、Contract 漂移、plan/binding hash 不一致或未知结构默认拒绝。

提交时冻结完整 Contract、Coverage/PermissionMutationPlan、DifferentialExperimentPlan、workflow/effect bindings、目标范围、预算和身份，形成 `WebExecutionSnapshot`；同时把当前项目 `policy_epoch`、策略 fingerprint 以及每条 ACTIVE revision 的 `intent_id/revision/intent_hash/binding_fingerprint` 固定为 `PermissionPolicySnapshot`，共同写入 `PersistedExecutionRequest`。代码变化重验再加入可选 `ChangeVerificationContext`，只保存 `change_id`、影响指纹、排序后的必需权限 ID 与源码指纹，不保存文件清单或 diff。执行期间不重新读取当前 Profile、Ledger、变化聚合或治理表。

## 生命周期与数据流

```text
WebExecutionProfile 校验/登记
  → Contract/plan/binding fingerprint
  → WebExecutionSnapshot + PermissionPolicySnapshot
  → 可选 ChangeVerificationContext
  → PersistedExecutionRequest
  → Worker/Runner → Web Target Runtime
```

Profile 是配置事实，快照是执行事实；更新 Profile、代码变化记录或 live 权限映射不改变历史 Run 或已发布 Evidence。变化评估给出的必需权限集合不能裁剪 Snapshot 中已经编译的完整 Coverage。

GUI 读取执行配置时只使用专用摘要投影：返回动作对应的目标步骤、SETUP/CLEANUP 数量、基线完整性模式，以及效果绑定的必需/佐证通道与闭合策略。该投影不返回身份凭据、Cookie、Authorization、secret ref 或完整请求模板，也不替代 Profile 和冻结快照本身。

## 失败与安全语义

未绑定 Contract、非 ACTIVE 版本、目标范围不明确、secret ref 非法、预算越界、指纹漂移或解析失败均 fail closed。秘密值不进入 Profile 公共 JSON、PersistedExecutionRequest、Evidence、日志或报告。

## 版本规则与 Schema 真源

当前 `WebExecutionProfile` 与 `PersistedExecutionRequest` 独立根以字符串 `schema_version="1"` 起步，`WebExecutionSnapshot` 作为冻结请求内的嵌套对象不重复版本；各 reader 只接受单一当前格式。Schema/protocol 版本表示机器格式，不表示产品代际。严格模型和 canonical/hash 以：

- `product/protocols/web/profile.py`
- `product/protocols/web/identity.py`
- `product/protocols/web/target.py`
- `product/protocols/web/workflow.py`
- `product/protocols/execution.py`
- `product/protocols/execution_request.py`
- `product/protocols/schemas/execution/web-execution-profile.schema.json`

为准。旧开发 Profile、Run 和请求格式不兼容读取。

## 查询入口

| 要查什么 | 当前真源 |
| --- | --- |
| Profile、identity、target、workflow 模型 | `product/protocols/web/` |
| Snapshot 与 Persisted Request | `product/protocols/execution.py`、`product/protocols/execution_request.py` |
| Profile 登记与提交 | `product/backend/workflows/runs/`、`product/backend/workflows/security_setup/` |
| Web Target Runtime | `product/backend/infra/execution/web/` |
| 直接测试 | `tests/protocols/web/`、`tests/backend/infra/execution/`、`tests/backend/workflows/security_setup/` |

## 相关真源

- [Target 扩展指南](../../02_开发指南/任务/扩展Target.md)
- [安全意图与验证架构](../../01_系统地图/权限验证与结果.md)
- [执行与观察架构](../../01_系统地图/执行与观察.md)
- [契约与执行快照绑定](../../05_设计依据/ADR-0030-契约与执行快照绑定.md)
