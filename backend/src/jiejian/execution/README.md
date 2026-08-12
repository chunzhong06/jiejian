# Execution

## 定位

`execution` 拥有持久 Job 从提交到完成的生命周期监督，包括 attempt、lease、fencing、取消、重试、Runner 进程、staging、原子发布和崩溃恢复。Worker 只是加载并调用这些能力的稳定进程壳。

## 负责 / 不负责

- 负责 ExecutionRequest 冻结、Job/attempt 状态、Handler 注册、进程监督、可信 staging 校验、publication 和 reconciliation。
- 通过通用 `JobHandler` / `JobTargetHandler` 端口承载 Verification Run 和 Recording 两个实现。
- 不实现 Verification 判定，不依赖 Recording 具体实现，也不在 Worker 内发送目标流量。

## 子模块与 public API

- `requests.py` / `request_store.py` / `submission.py` / `queue.py`：请求构造、持久快照、提交和取消。
- `handlers.py` / `targets.py`：`JobHandler`、`JobAttemptPort` 和目标类型注册端口。
- `attempts.py` / `process_control.py` / `supervisor.py`：claim、lease、fencing 和 Runner 监督。
- `published_artifacts.py` / `publication.py`：staging 校验、manifest 与原子发布。
- `recovery.py` / `reconciliation.py`：过期 attempt 和“已发布但数据库未完成”恢复。
- `dispatch.py`：CLI 等同步调用方等待持久 Job 的适配层。

这些都是仓库内叶模块接口；永久进程入口仍是 `jiejian.worker.runtime`、`jiejian.runner` 和 `jiejian.recording_runner`。

## 调用与数据流

```text
API / CLI / GUI
→ ExecutionSubmissionService / JobQueueService
→ Worker runtime
→ JobHandlerRegistry
→ VerificationRunJobHandler 或 RecordingJobHandler
→ 隔离 Runner
→ staging 校验 → atomic publication → 数据库完成态
```

## 关键不变量和失败语义

- 一个 attempt 只有匹配 `job_id + lease_owner + fencing_token` 才能续租、完成或发布。
- cancel、retry 和 recovery 不得让两个 attempt 同时拥有目标副作用权限。
- Runner 输出首先进入 attempt staging；内容、路径、大小、receipt 和哈希重验通过后才可发布。
- 最终目录原子发布先于数据库完成态；中间崩溃由 reconciliation 幂等收敛。
- `FAILED`、`CANCELLED`、`RETRY_WAIT` 是 Job 生命周期，不得转换成安全 `INCONCLUSIVE`。

## 修改与测试入口

- Job/监督/恢复：[`tests/execution/worker`](../../../../tests/execution/worker/)
- Runner 进程：[`tests/execution/runner`](../../../../tests/execution/runner/)
- 协议：[`tests/execution/protocol`](../../../../tests/execution/protocol/)
- 架构依赖：[`tests/architecture/test_dependencies.py`](../../../../tests/architecture/test_dependencies.py)

## 相关规范、协议与 ADR

- [系统架构](../../../../docs/01_架构设计/系统架构.md)
- [Runner 执行协议 V1](../../../../docs/04_协议定义/Runner执行协议V1.md)
- [ADR-0005～0007 与 ADR-0017](../../../../docs/03_技术决策/README.md)
