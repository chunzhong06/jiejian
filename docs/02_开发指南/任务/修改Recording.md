# 修改 Recording

> 1.1.0 CURRENT：普通 Recording 与完整 Worker 主链尚未接回当前产品入口；以下内容约束保留实现，不表示当前 GUI 可录制或运行检查。

> 状态：CURRENT。用于修改真实业务流程录制、capture 控制、FlowDraft 审阅、Flow 编译和 Recording 失败收口。

## 这是什么

Recording 把“用户在已登录网页里完成一次真实业务动作”转换为可审阅的 `FlowDraft`。它不是浏览器宏录制器，也不会把登录、导航和偶然请求自动宣布为安全测试流程。普通入口只接受一个已确认 action 和一个已准备 TestIdentity；服务端解析 endpoint、目标范围和非秘密身份元数据，独立 Worker 再启动独立 Recording Process 与有头 Chromium。

持久 Recording 生命周期、Job 生命周期和 capture 控制阶段是三套不同事实。`STARTING/RECORDING/PROCESSING/PENDING_REVIEW` 表达业务对象状态；Job 表达调度与执行；`capture_phase` 从当前 attempt 的 ready/start/started/stop 标记投影。FlowDraft 只在正式 Recording result 经 `RecordingSubmission.consume_result → FlowDraftProcessor` 后形成。

## 快速找到修改位置

| 要改什么 | 先看哪里 | 直接测试 |
| --- | --- | --- |
| Recording 提交、状态与 result 消费 | `product/backend/workflows/recording/project_submission.py`、`product/backend/workflows/recording/processing.py` | `tests/backend/workflows/recording/` |
| capture start/stop 与当前 attempt 控制 | `product/backend/workflows/recording/lifecycle.py`、`product/backend/workflows/recording/run_service.py`、`product/backend/infra/recording/control.py` | `tests/backend/api/test_recordings.py` |
| 独立 Recording Process | `product/backend/infra/recording/process.py`、`product/backend/infra/recording/browser.py` | `tests/backend/infra/recording/test_process.py`、`tests/backend/infra/recording/test_browser_boundary.py` |
| 脱敏事件收集 | `product/backend/infra/recording/events.py` | `tests/backend/infra/recording/` |
| FlowDraft 审阅与 revision | `product/backend/workflows/recording/review.py`、`product/protocols/flow_draft.py` | `tests/backend/workflows/recording/`、`tests/protocols/test_recording.py` |
| Flow 编译 | `product/backend/workflows/recording/flow_compiler.py`、`product/protocols/recording_flow.py` | `tests/backend/workflows/recording/test_flow_compiler.py` |
| API/CLI/GUI 控制入口 | `product/backend/api/routers/recordings.py`、`product/backend/cli/commands/control.py`、`product/frontend/src/features/recording/` | 对应 API、CLI 与前端直接测试 |

## 正常修改路线

先画清变化发生在哪一层：浏览器采集边界、Recording application service、FlowDraft 审阅，还是最终 Flow 编译。浏览器层只收集有界脱敏事件和控制标记；workflow 层拥有状态机与幂等；协议层拥有严格根文档；页面只展示权威状态并发出明确开始、停止和审阅命令。

正式 capture 顺序必须保持：Recording Process 发布 `capture.ready`，控制面写入 start，进程确认 `capture.started`，状态进入采集中后才允许业务动作；用户停止后写入 stop，Runner 收口事件与浏览器，Job 成功，Recording 进入 `PENDING_REVIEW`。取消仍走 Job cancel，不得把停止实现为取消。

Recording 应根据录制顺序自动采用唯一且可执行的业务解释；只有多个同级业务解释并存时，页面才让用户在业务动作、有限资源值或来源步骤之间选择。编译后的 Flow 仍保留必要 SETUP 与唯一 TARGET，通过 `CASE_SUBJECT`、`CASE_RESOURCE_ID` 在运行时注入差分事实，但 HTTP method、path 位置、JSONPath、step ID 和 candidate ID 不进入普通审阅。业务资源、真实结果、独立观察和恢复方式在安全准备中形成；权限要求只能由 Human Approval 改变，不能塞回 Recording 或 Flow。

`ActionSafetySetupService.inspect_action()` 是 Recording、FlowDraft 与 ActionSafetySetup 当前事实的只读检查入口，统一形成 FLOW/RESOURCE/OBSERVATION/RECOVERY/EFFECT 的 CURRENT/MISSING/STALE 结果。它只读取已保存的非秘密事实，不访问目标应用、不恢复浏览器会话、不读取 secret 正文，也不写入确认。`ProjectPreparation` 只消费这份检查结果并组合独立的 TestIdentity 状态；缺 Flow、观察或恢复时，准备页只能把用户导航到现有 `/flows` 与确认流程，`prepare-safe` 不创建 Recording、不生成 FlowDraft，也不静默确认唯一候选。

页面在最终 Flow 或安全准备事实保存成功后，先刷新 Recording 本地事实，再刷新项目工作区；底部“继续准备”只按这次工作区刷新返回的准备投影续接。Recording 生命周期轮询只更新本页状态，不能在每个 tick 刷新整个工作区。工作区同步失败不回滚已经成立的保存结果，但必须显示可恢复提示。

## 不能破坏

- 登录和页面检查阶段不采集事件；秘密正文、Cookie、Bearer、storage state 和浏览器 profile 不进入协议、日志或 Git。
- 普通 Recording 必须经过正式 API、Worker、独立 Recording Process 和 `BrowserRecordingAdapter`；测试 `controlled_runner` 只服务 L1～L4，不得进入自动 L5。
- start/stop 标记必须绑定当前 recording/job/attempt，原子写入、严格解析且不携带用户输入或秘密。
- Recording 失败先保存主错误，再执行 stop/cancel/进程回收；cleanup issue 不能覆盖 primary failure。
- 普通应用和测试不得直接构造 RecordingEvent、FlowDraft 或调用 processor 伪造成功；不通过测试专用 API、环境变量或 CDP 暴露浏览器控制面。官方样例只能按[官方示例与整链验收](修改官方示例与整链验收.md)冻结的例外，把受控确定性轨迹送入正式 Recording 提交、Job attempt、结果消费与生命周期服务，仍不得直写 Storage。
- FlowDraft revision 冲突、目标范围漂移或回放校验失败必须停止，不猜测兼容。

## 怎么验证

先运行修改点的 workflow/protocol/infra 直接测试。涉及 API 控制再补 recordings Router；涉及页面只跑对应前端文件。真实 Worker、Recording Process、headed Chromium、UI Automation 和事件闭环只由唯一自动 L5 `dev.ps1 sample-test` 在阶段收口验证，不为普通修改连续反复运行。

```powershell
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File .\scripts\dev.ps1 test tests/backend/workflows/recording tests/backend/infra/recording tests/backend/api/test_recordings.py tests/protocols/test_recording.py
```

命令只是覆盖面示例；实际选择最小受影响路径。修改 Python 后仍需按项目规则检查中文职责头和 AST。

## 失败先查哪里

停在 `STARTING` 时先区分浏览器未启动、尚未 ready、start 未发布和 started 未确认，不直接改数据库。Job 已终态而 Recording 仍在活动态，检查 result consume 与正式 reconciliation。事件为空时先确认业务动作是否发生在 `capture.started` 之后，再查 collector 预算和脱敏；不要用直接 HTTP 请求补事件。FlowDraft 缺失时沿 `Runner result → submission consume → processor` 顺序查，不从页面重建草稿。

## 相关真源

- [Recording 模块](../模块/recording.md)
- [录制与 Flow 协议](../../03_参考手册/协议/录制与Flow协议.md)
- [浏览器录制身份隔离与 FlowDraft 边界](../../05_设计依据/ADR-0037-浏览器录制身份隔离与FlowDraft边界.md)
- [修改安全准备](修改安全准备.md)
