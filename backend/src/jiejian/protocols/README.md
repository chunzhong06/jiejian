# Protocols

## 定位

`protocols` 保存跨进程或持久工件必须共同遵守的版本化 Wire Model。它是 `schema_version`、规范 JSON、大小上限和严格解析规则的代码真源。

## 负责 / 不负责

- 负责 Runner V1、Recording V1、FlowDraft V1 的模型、编码、严格解析和 secret 拒绝。
- 与 `schemas/` 中签入的公共 JSON Schema 保持一致。
- 不负责 Job 状态、业务编排、数据库事务或 Verdict。

## 子模块与 public API

- `runner_v1.py`：Verification Runner 输入、结果、cleanup 和 staging 清单。
- `recording_v1.py`：Recording Runner 请求、事件和结果。
- `flow_draft_v1.py`：FlowDraft、审阅命令和规范编码。
- `jiejian.protocols` 的 `__all__` 是正式稳定 Python 导入面；内部实现不通过其他聚合根转发。

## 调用与数据流

```text
Worker / Execution → RunnerInputV1 → Verification Runner → RunnerResultV1
Recording JobHandler → RecordingRunnerRequestV1 → Recording Runner → RecordingRunnerResultV1
Recording Event → FlowDraftV1 → Review Command → confirmed Flow
```

## 关键不变量和失败语义

- 所有公共对象带固定 `schema_version`；未知字段、重复 JSON key、非有限数值和超限 payload 必须拒绝。
- 原始 secret、授权头和未脱敏敏感值不得进入协议对象。
- 规范 JSON 字节和 SHA-256 用于跨进程完整性比较；解析失败是协议错误，不是安全 Verdict。
- 公共不兼容变化必须新增版本和迁移说明，不能原地改变 V1 语义。

## 修改与测试入口

- 协议测试：[`tests/execution/protocol`](../../../../tests/execution/protocol/)
- 公共 Schema：[`schemas/README.md`](../../../../schemas/README.md)
- Runner 协议说明：[Runner 执行协议 V1](../../../../docs/04_协议定义/Runner执行协议V1.md)

## 相关规范、协议与 ADR

- [公共数据格式](../../../../docs/04_协议定义/数据格式.md)
- [ADR-0002](../../../../docs/03_技术决策/ADR-0002-阶段2执行协议.md)、[ADR-0009](../../../../docs/03_技术决策/ADR-0009-阶段3录制持久化与回放.md)
