# Recording 模块

> 状态：CURRENT。Recording 模块连接已确认 action/测试身份、独立有头浏览器、capture 生命周期、脱敏事件、FlowDraft 审阅和后续安全准备。

## 职责

负责提交 Recording Job、启动独立 Recording Process、恢复已准备会话、按明确 start/stop 采集真实业务事件、消费结果形成 FlowDraft、处理 revision 审阅，并在用户确认后编译唯一 action-centered Flow。

## 非职责

不把登录和浏览自动变成业务动作，不从事件自动决定 PermissionIntent、SecurityEffect、Observer 或 Recovery，不保存秘密正文，也不为自动 L5暴露浏览器句柄、CDP 或测试专用 Runner。

## 稳定入口与模块边界

| 位置 | 负责什么 | 不负责什么 |
| --- | --- | --- |
| `product/backend/workflows/recording/project_submission.py`、`submission.py` | 普通 action/identity 提交、Job 关联与结果消费 | 浏览器操作与事件底层采集 |
| `product/backend/workflows/recording/lifecycle.py`、`run_service.py` | Recording 状态、capture start/stop、等待与错误保真 | 伪造 Job 终态或直接改数据库 |
| `product/backend/workflows/recording/processing.py` | 正式 result 到 FlowDraft | 页面候选自动确认 |
| `product/backend/workflows/recording/review.py`、`flow_compiler.py` | revision 审阅与 Flow 编译 | 权限意图和 Observer 编译 |
| `product/backend/workflows/recording/safety_candidates.py`、`safety_setup.py` | 后续资源/观察/恢复候选与确认 | RecordingEvent 采集 |
| `product/backend/infra/recording/` | 请求存储、原子控制标记、浏览器、事件、独立进程 | ApplicationCore 事务和权限结论 |
| `product/protocols/recording.py`、`flow_draft.py`、`recording_flow.py` | 严格机器根文档 | 浏览器实现和数据库生命周期 |
| `product/frontend/src/features/recording/` | 正式业务流程页面与用户确认 | 后端状态机和秘密存储 |

精确符号见[Workflows 代码参考](../../03_参考手册/代码/backend-workflows.md)和[录制与 Flow 协议](../../03_参考手册/协议/录制与Flow协议.md)。

## 我想修改什么

| 任务 | 主要位置 | 直接验证 |
| --- | --- | --- |
| 修改普通 Recording 提交与 Job 关联 | `workflows/recording/project_submission.py`、`submission.py`、`api/routers/recordings.py` | `test_project_submission.py`、`test_recordings.py` |
| 修改 capture ready/start/started/stop | `workflows/recording/run_service.py`、`lifecycle.py`、`infra/recording/control.py` | `test_run_service.py`、infra `test_control.py`、API recordings 测试 |
| 修改独立 Recording Process 或浏览器 | `infra/recording/process.py`、`browser.py`、`request_store.py` | infra `test_process.py`、`test_browser_boundary.py` |
| 修改事件采集、网络关联或脱敏 | `infra/recording/events.py`、`ui_capture.py`、`transport.py` | infra recording 直接测试 + `test_sanitization.py` |
| 修改 FlowDraft 候选/revision | `workflows/recording/processing.py`、`review.py`、`product/protocols/flow_draft.py` | `test_flow_draft_review.py`、`tests/protocols/test_recording.py` |
| 修改 Flow 编译 | `workflows/recording/flow_compiler.py`、`product/protocols/recording_flow.py` | `test_flow_compiler.py`、Recording protocol 测试 |
| 修改资源、观察或恢复准备 | `safety_candidates.py`、`safety_setup.py`、`workflows/security_setup/` | [修改安全准备](../任务/修改安全准备.md)及两个 workflow 直接测试 |
| 修改页面业务流程 | `product/frontend/src/features/recording/` | 对应 Vitest；必要时展示验收 |
| 修改真实浏览器自动验收 | `scripts/dev/sample_test/windows.py` | 低成本 UIA/Recording 局部探针；最终一次 sample-test |

## 正式生命周期与事实产物

```text
已确认 action + 已准备测试身份
  → POST recordings 创建 Job / Recording
  → Worker 启动独立 Recording Process
  → BrowserRecordingAdapter 恢复会话并发布 capture.ready
  → capture.start → capture.started → CAPTURING
  → 用户在正式页面执行业务动作
  → capture.stop → result 原子完成
  → RecordingSubmission.consume_result
  → FlowDraft → revision review → Flow
  → SafetySetup 确认资源、Observer 与 Recovery
```

Job 说明后台执行是否完成，Recording 状态说明录制业务生命周期，`capture_phase` 说明当前采集握手，FlowDraft/Flow 是后续用户确认产物。四类事实不能互相代替；某个进程退出也不能直接推断另三类已经收口。

## 必须保持的边界

- 正式 Recording 必须经过 API → Job → Worker → 独立 Recording Process → BrowserRecordingAdapter；自动 L5 不使用 `controlled_runner`。
- `STARTING/RECORDING/PROCESSING/PENDING_REVIEW`、Job 状态与 `capture_phase` 分开；start/stop 标记只控制当前 attempt。
- `capture.started` 之前不执行/采集业务动作；停止保留事件并形成草稿，取消继续走 Job cancel。
- 登录准备不采集，Cookie/Bearer 正文只从 SecretStore 最小注入独立 BrowserContext；事件落盘前限长脱敏。
- Recording 根据录制事实自动采用唯一且可执行的业务解释；只有多个同级业务解释并存时，用户才在业务动作、有限资源值或来源步骤之间选择。Flow 继续保留内部 TARGET、变量与资源绑定，但不保存 ALLOW/DENY、Observer 或 reset 默认。
- 失败先保存 primary failure，再正式 stop/cancel/shutdown；cleanup issue 不能覆盖主错误，数据库不能手工改终态。
- 普通 Recording 测试不得构造 RecordingEvent、预制 FlowDraft、直接访问 Sample HTTP 代替真实页面按钮；官方样例只能按其任务指南冻结的受控轨迹例外走完整 application service 链，不能直写 Storage。

## 直接验证

```powershell
.\scripts\dev.ps1 test tests/backend/workflows/recording
.\scripts\dev.ps1 test tests/backend/infra/recording
.\scripts\dev.ps1 test tests/backend/api/test_recordings.py tests/protocols/test_recording.py
.\scripts\dev.ps1 frontend-test src/features/recording/RecordingPage.test.tsx
```

按实际修改缩小范围。只有浏览器/进程/UIA 边界变化才运行局部真实 Recording 探针；完整 `dev.ps1 sample-test` 是最终验收的唯一自动 L5，人工只做展示验收。

## 首错定位

| 现象 | 先检查 | 不要先做 |
| --- | --- | --- |
| Job RUNNING，但没有浏览器 | Worker dispatch、Recording request、独立进程日志与 PID 所有权 | 给 API 进程直接启动浏览器 |
| 浏览器出现，但 capture 无法开始 | `capture.ready`、控制标记、attempt 目录和 `capture.started` | 提前执行页面业务动作 |
| stop 后没有 FlowDraft | Job/Recording 终态、result 文档、`consume_result` 和 processor | 直接构造 RecordingEvent 或 FlowDraft |
| FlowDraft 包含秘密或噪声请求 | event collector、sanitization、业务动作时间窗 | 在最终报告中才做文本替换 |
| 失败后遗留 STARTING/RECORDING | primary failure、正式 stop/cancel、Worker watchdog 与 reconciliation | 手工写数据库终态或删除 Job |
| UIA 找不到唯一窗口/按钮 | 新窗口、受控 Chromium 进程、Sample 可访问性树和 InvokePattern | SetForegroundWindow、SendInput、CDP |

## 相关真源

- [修改 Recording](../任务/修改Recording.md)
- [修改安全准备](../任务/修改安全准备.md)
- [录制与 Flow 协议](../../03_参考手册/协议/录制与Flow协议.md)
- [浏览器录制身份隔离与 FlowDraft 边界](../../05_设计依据/ADR-0037-浏览器录制身份隔离与FlowDraft边界.md)
- [验证与测试](../../04_工程约束/验证与测试.md)
