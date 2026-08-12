# Runner

## 定位

`runner` 是 Verification 的独立进程和主动目标流量隔离边界。Worker 只能通过 Runner V1 输入、结果文件、退出码和 staging 与它协作。

## 负责 / 不负责

- 负责严格读取 `RunnerInputV1`、构造不可变 `VerificationSnapshot`、调用 Verification、写入 staging 和 `RunnerResultV1`。
- 负责把协议错误、内部错误和结果写入错误映射为稳定进程退出码。
- 不 claim Job、不访问数据库、不发布最终目录，也不决定 retry/recovery。

## 子模块与 public API

- `python -m jiejian.runner` 是正式进程入口。
- `__main__.py` 是极薄参数/退出壳。
- `execution.py` 是进程内唯一执行适配，连接 Runner V1 与 `SnapshotRunExecutor`。

## 调用与数据流

```text
WorkerSupervisor
→ python -m jiejian.runner
→ RunnerInputV1
→ SnapshotRunExecutor
→ staging artifacts + RunnerResultV1
→ Worker 重验与发布
```

## 关键不变量和失败语义

- Runner 只接受一个完整 Run 快照；输入路径、大小、JSON 和 secret 边界在产生目标流量前校验。
- 退出码 `0/64/70/74` 只表达可信结果形成、协议、内部或写入状态，不是 PASS/BLOCK/INCONCLUSIVE。
- Runner 只能写当前 attempt staging；最终 publication 和数据库完成态属于 Execution/Storage。
- 任何目标请求都必须经过 Verification 的 TargetGuard、预算和清理策略。

## 修改与测试入口

- 进程测试：[`tests/execution/runner`](../../../../tests/execution/runner/)
- Runner 协议：[`tests/execution/protocol/test_runner_v1.py`](../../../../tests/execution/protocol/test_runner_v1.py)
- 安全核心：[`verification/README.md`](../verification/README.md)

## 相关规范、协议与 ADR

- [Runner 执行协议 V1](../../../../docs/04_协议定义/Runner执行协议V1.md)
- [ADR-0002](../../../../docs/03_技术决策/ADR-0002-阶段2执行协议.md)、[ADR-0006](../../../../docs/03_技术决策/ADR-0006-阶段2隔离执行设计.md)
