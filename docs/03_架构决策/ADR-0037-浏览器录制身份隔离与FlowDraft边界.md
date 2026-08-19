# ADR-0037：浏览器录制、身份隔离与 FlowDraft 边界

- 状态：已接受
- 日期：2026-08-19
- 适用范围：Recording Runner、RecordingEvent、FlowDraft、审阅、发布和回放

## 背景

浏览器录制包含 Cookie、Authorization、表单字段、响应体和动态资源标识。录制必须可审阅、可脱敏、可按身份隔离，并且回放不能绕过当前目标范围、契约和执行快照校验。

## 决策

Recording Runner 每次只执行一次录制或回放；每个 identity 使用独立的非持久 BrowserContext，不跨身份共享 Cookie、localStorage 或 sessionStorage。请求、响应、WebSocket、错误和事件在写盘前限长、脱敏并形成有界摘要；原始 trace、storage state 和秘密不发布。

普通录制入口只接受已经登记的 `profile_id` 与一个 `identity_id`，后端通过 ApplicationCore 解析当前 `ExecutionProfile`，不接受 GUI 提供磁盘路径，也不让 GUI 控制 headless。产品录制固定使用有头 Chromium；身份表示权限主体/执行身份。人工登录只发生在浏览器准备阶段，不采集登录事件，也不引入虚假的 `session_ref` 或长期 Cookie 恢复。

录制分为“准备浏览器、等待明确开始、采集中、停止并生成”四个用户阶段。现有持久状态 `STARTING` 覆盖准备与等待，用户明确开始后才进入 `RECORDING`；更细阶段由当前 attempt 的 ready/start/stop 控制事实确定性投影，不新增持久生命周期枚举。开始采集和停止生成是独立控制动作：停止保留已经采集的事件并进入 `PROCESSING`、`PENDING_REVIEW` 与 `FlowDraft`；取消走既有 Job 取消边界、丢弃本次录制并进入 `CANCELLED`。

登录准备期间仍执行 TargetScope、网络预算、安全停止和清理控制，但事件收集器关闭持久采集；收到开始控制后才为当前页面建立录制关联并追加 `RecordingEvent`。控制事实只使用当前 attempt 目录内的有界、无秘密、原子标记，由 API/ApplicationCore 写入、Worker/Runner 消费；跨 attempt 或过期控制严格拒绝。

事件以 `RecordingEvent` 保存稳定序号、关联标识和脱敏内容。事件处理生成 `FlowDraft`；删除、合并相邻步骤、重命名和变量来源确认产生新 revision。普通审阅界面不要求编辑 JSON，只有 identity、资源、变量来源和安全范围完成审阅后，FlowDraft 才能编译为 Web target/binding。

回放必须重新经过 TargetScope、Contract、plan、binding、预算和 ExecutionProjectSnapshot 校验，并复用普通 Worker/Runner、Evidence、Verification 和 publication 链。失败不能伪装成成功或绕过当前结果语义。

## 理由与取舍

把录制和 FlowDraft 放在同一审阅发布闭环，可以避免未经确认的浏览器事实直接进入执行。代价是每次草稿变化都产生 revision，并需要重新验证。

## 影响

录制资产、草稿 revision、发布 Flow 和回放 Run 分离保存；录制能力不创建第二套权限模型、调度器或报告路径。

## 迁移与兼容

只接受当前 Recording/Flow Schema 和 revision 规则；旧开发录制、原始 trace、长期浏览器凭据和旧 wire format 不兼容读取。

## 相关真源

- [执行与观察架构](../02_架构设计/执行与观察架构.md)
- [安全意图与验证架构](../02_架构设计/安全意图与验证架构.md)
- [录制与Flow协议](../04_协议与数据/录制与Flow协议.md)
- `product/protocols/recording.py`
- `product/protocols/flow_draft.py`
- `product/protocols/recording_flow.py`
