# 录制与 Flow 协议

> 状态：CURRENT。本文解释 Recording 与 FlowDraft 的共同审阅发布闭环。

## 目的与消费者

Recording Runner、GUI/CLI 录制入口、FlowDraft 审阅、动作 Flow 编译和后续回放工作流共享本协议族。录制资产不是 PermissionContract，也不是可直接执行的 Profile。

## 先理解：录制的是业务动作，不是登录过程

用户先选择正式 BusinessAction revision 和已准备 TestIdentity，独立 Recording Process 恢复会话并打开 headed Chromium。页面准备与登录检查阶段不采集；只有 `capture.ready → start → started` 完整成立后，用户执行的真实业务按钮才进入 `RecordingEvent`。停止后正式结果被 ApplicationCore 消费，才形成可审阅 FlowDraft。

FlowDraft 仍只是候选业务流程。唯一且可执行的 TARGET 与资源可以确定性采用，存在歧义时由用户审阅；最终 Flow 保留必要 SETUP、变量和资源位置。OBSERVATION 开始前必须绑定已有 BusinessEffect，RECOVERY 只为改变状态的动作形成恢复模板；录制不创建 Effect 或 ALLOW/DENY。

## 协议边界

- 普通 Recording create 请求只提交正式 `business_action_id + action_revision`、单一已准备 `test_identity_id`、时长、purpose、必要 parent/effect 与幂等键；服务端从 ApplicationUnderstanding 和 TestIdentity 解析 endpoint、动作与非秘密身份元数据。GUI 不传 Profile/path、目标范围、SecretStore 引用或 headless 开关。
- `RecordingRunnerRequest` 绑定正式业务动作版本、身份、准备来源指纹、目标范围、预算和单一短期 session 描述。目标授权必须与已确认 endpoint 一致，超时、请求数和响应字节预算只能收紧。session 只包含 Cookie/Bearer 的 `env:` 引用与非秘密元数据；秘密正文只进入本次 Worker/Recording Runner 最小环境和内存中的独立 BrowserContext。
- Recording result 表达一次录制的状态、错误、清理结果与已脱敏事件；不回传登录状态或秘密引用。
- `RecordingEvent` 保存稳定序号、关联标识、事件类型、身份和有界脱敏摘要。
- `FlowDraft` 绑定正式业务动作版本与身份，保存步骤、变量、TARGET/资源推荐与明确确认、revision 和审阅状态；每条 review command 产生新的 revision。
- 审阅通过后，FlowDraft 编译为当前 Flow：只保留唯一 TARGET 与其必要 SETUP，通过 `CASE_SUBJECT` 与 `CASE_RESOURCE_ID` 延迟注入运行时主体和资源。Flow 不保存 alternate identity/resource、ALLOW/DENY、Observer 或 reset 默认；后续确定性编译仍进入普通 ExecutionWorkflow，不建立并行执行链。

## 生命周期与数据流

```text
已确认 action + 已准备 TestIdentity
  → 服务端生成短期 session/env refs
  → 独立 identity 有头 BrowserContext 恢复认证
  → 登录准备与页面检查（不采集）
  → 明确开始 → RecordingEvent（限长、脱敏）
  → 明确停止
  → FlowDraft revision
  → 明确确认唯一 TARGET、有限资源位置和必要变量
  → action-centered Flow（SETUP + TARGET）
  → 后续受控配置编译、执行快照和回放
```

## 失败与安全语义

TargetScope、身份、协议、主机、端口、私网、重定向、响应大小、下载、SSE、长连接和清理均受限制。写盘前必须脱敏；原始 Cookie、Authorization、storage state、trace 和秘密不发布。审阅缺失、revision 冲突、编译失败或回放重验证失败时停止。

## 控制与状态投影

- 持久 Recording 状态不增加新枚举：`STARTING` 表示准备浏览器或等待开始，`RECORDING` 表示正在采集，停止成功后进入 `PROCESSING` 和 `PENDING_REVIEW`。
- 状态读取可以附加由当前 attempt 控制事实推导的 `capture_phase`，稳定区分准备、等待开始、开始中、采集、停止中与结束；它是控制面投影，不是 Verification Verdict，也不写入 Recording 状态约束。
- 开始与停止端点只控制当前 attempt。开始前不产生 `RecordingEvent`；停止保留事件并生成草稿；取消仍使用 Job cancel，并形成 `CANCELLED`，不得把停止实现为取消。
- ready/start/stop 控制标记不携带秘密或用户输入，必须限定在当前 attempt、原子写入并严格校验录制、Job 与 attempt 关联。

## 版本规则与 Schema 真源

当前 `RecordingRunnerRequest`、`FlowDraft` 与最终 `Flow` 的根 `schema_version` 为字符串 2；`RecordingEvent`、`RecordingRunnerResult` 与审阅命令仍为字符串 1。只升级发生不兼容变化的独立根，不按产品版本机械同步。模型、required 和 strict parsing 以：

- `product/protocols/recording.py`
- `product/protocols/flow_draft.py`
- `product/protocols/recording_flow.py`
- `product/protocols/schemas/recording/`

为准。版本号只表示机器格式。

## 查询入口

| 要查什么 | 当前真源 |
| --- | --- |
| Recording/FlowDraft/Flow 根模型 | `product/protocols/recording.py`、`product/protocols/flow_draft.py`、`product/protocols/recording_flow.py` |
| 提交、生命周期与结果消费 | `product/backend/workflows/recording/` |
| capture 标记、浏览器和事件收集 | `product/backend/infra/recording/` |
| API 与 GUI | `product/backend/api/routers/recordings.py`、`product/frontend/src/features/recording/` |
| 直接测试 | `tests/backend/workflows/recording/`、`tests/backend/infra/recording/`、`tests/protocols/test_recording.py` |

## 相关真源

- [浏览器录制、身份隔离与 FlowDraft 边界](../../05_设计依据/ADR-0037-浏览器录制身份隔离与FlowDraft边界.md)
- [执行与观察架构](../../01_系统地图/执行与观察.md)
