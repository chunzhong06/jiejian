# 录制与 Flow 协议

> 状态：CURRENT。本文解释 Recording 与 FlowDraft 的共同审阅发布闭环。

## 目的与消费者

Recording Runner、GUI/CLI 录制入口、FlowDraft 审阅、ExecutionProfile 编译和回放工作流共享本协议族。录制资产不是 PermissionContract，也不是可直接执行的 Profile。

## 协议边界

- Recording request/result 表达一次录制或回放的身份、目标范围、预算、状态、错误和清理结果。
- `RecordingEvent` 保存稳定序号、关联标识、事件类型、身份和有界脱敏摘要。
- `FlowDraft` 保存步骤、变量、revision 和审阅状态；review command 产生新的 revision。
- 审阅通过后，FlowDraft 编译为 Web target 与 ActionExecutionBinding，再进入普通 Contract/Profile/ExecutionWorkflow。

## 生命周期与数据流

```text
Recording request → 独立 identity BrowserContext
  → RecordingEvent（限长、脱敏）
  → FlowDraft revision
  → 审阅/确认变量来源
  → Web target/binding 编译
  → 普通执行快照和回放
```

## 失败与安全语义

TargetScope、身份、协议、主机、端口、私网、重定向、响应大小、下载、SSE、长连接和清理均受限制。写盘前必须脱敏；原始 Cookie、Authorization、storage state、trace 和秘密不发布。审阅缺失、revision 冲突、编译失败或回放重验证失败时停止。

## 版本规则与 Schema 真源

Recording、FlowDraft、RecordingEvent 和 Recording Runner 相关 Schema 当前主要为 1；review command 当前 Schema 若没有 `schema_version`，不补写不存在的字段。模型、required 和 strict parsing 以：

- `product/protocols/recording.py`
- `product/protocols/flow_draft.py`
- `product/protocols/recording_flow.py`
- `product/protocols/schemas/recording/`

为准。版本号只表示机器格式。

## 相关真源

- [浏览器录制、身份隔离与 FlowDraft 边界](../03_架构决策/ADR-0037-浏览器录制身份隔离与FlowDraft边界.md)
- [执行与观察架构](../02_架构设计/执行与观察架构.md)
