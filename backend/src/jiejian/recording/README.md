# Recording

## 定位

`recording` 在独立 Recording Runner 中采集浏览器交互，把受控、脱敏的 Recording Event 编译为待审阅 FlowDraft，并在确认后发布可执行 Flow。

## 负责 / 不负责

- 负责 Recording 提交和结果消费、BrowserContext 身份隔离、TargetScope、预算、事件脱敏、FlowDraft 编译、审阅、确认和回放。
- 通过 Execution 的 `JobHandler` / `JobTargetHandler` 端口接入统一 Job 生命周期。
- 不执行 Verification 判定；Recording Event 和 FlowDraft 都不自动成为可执行 Flow。

## 子模块与 public API

- `application.py`：`RecordingApplicationService`，持久提交和可信结果消费。
- `browser.py` / `events.py` / `transport.py`：浏览器会话、事件关联和受控网络传输。
- `sanitization.py` / `ui_capture.py`：落盘前脱敏与 UI 动作采集。
- `processing.py` / `review.py` / `workflow.py`：Event → FlowDraft → 已确认 Flow。
- `request_store.py`：Recording Runner 请求快照。
- `job_handler.py` / `job_target.py`：Execution 端口实现。
- `recording_runner/` 是正式独立进程入口，不由本 package 根重导出。

## 调用与数据流

```text
CLI / API / GUI
→ RecordingApplicationService
→ Job + RecordingRunnerRequestV1
→ Recording Runner + Playwright
→ 脱敏 RecordingEventV1
→ FlowDraftProcessor / Reviewer
→ 人工确认的 Flow
```

## 关键不变量和失败语义

- 每个身份使用独立 BrowserContext；在创建 Page 前安装目标、预算和事件边界。
- secret 和敏感值必须在事件写入、日志和错误输出前脱敏。
- TargetScope、请求/响应/页面/事件预算任何一项越界都停止继续采集。
- collector 在关闭浏览器资源前冻结，避免清理回调改变已经判定的结果。
- Recording 成功只表示采集完成，不表示 Flow 已确认，更不表示安全验证 PASS。

## 修改与测试入口

- Recording/浏览器边界：[`tests/execution/recording`](../../../../tests/execution/recording/)
- 公共协议：[`tests/execution/protocol/test_recording_v1.py`](../../../../tests/execution/protocol/test_recording_v1.py)
- API：[`tests/api/test_control_plane.py`](../../../../tests/api/test_control_plane.py)
- 公共 Schema：[`schemas/recording`](../../../../schemas/recording/)

## 相关规范、协议与 ADR

- [数据流](../../../../docs/01_架构设计/数据流.md)
- [公共数据格式](../../../../docs/04_协议定义/数据格式.md)
- [ADR-0009](../../../../docs/03_技术决策/ADR-0009-阶段3录制持久化与回放.md)、[ADR-0017](../../../../docs/03_技术决策/ADR-0017-阶段5-O3能力优先架构迁移约束.md)
