# 公共机器 Schema

`schemas/` 只保存跨进程、跨语言、跨版本的机器契约，不收纳 Contract 内部 Pydantic 模型、API 内部 Schema、测试 fixture、样例 YAML 或数据库映射。所有当前 Schema 的 `schema_version` 均为 `"1"`。

LLM profile 与 system status 是 API/OpenAPI 的 Pydantic DTO，不是 `schemas/` 下的签入公共文件 Schema；它们继续使用现有 API envelope 的 `schema_version="1"`。阶段 5.6 的 provenance 是 Candidate 同一 JSON 列的向后兼容可选扩展，不新增公共文件格式。

## 契约族与代码真源

| 契约族 | 签入 Schema | 代码真源 | Producer / Consumer |
| --- | --- | --- | --- |
| Runner | `runner/runner-input-v1.schema.json`、`runner/runner-result-v1.schema.json` | `backend/src/jiejian/protocols/runner_v1.py` | Worker/Runner 边界；Worker 写入输入，Runner 返回结果。 |
| Recording Runner | `recording/recording-runner-request-v1.schema.json`、`recording/recording-runner-result-v1.schema.json` | `backend/src/jiejian/protocols/recording_v1.py` | Recording Job/Runner 边界；Recording 适配器写入请求，Runner 返回结果。 |
| Recording 事件 | `recording/recording-event-v1.schema.json` | `backend/src/jiejian/protocols/recording_v1.py` | Recording Runner 产生，Recording 应用服务脱敏、持久化和消费。 |
| FlowDraft | `recording/flow-draft-v1.schema.json`、`recording/flow-draft-review-command-v1.schema.json` | `backend/src/jiejian/protocols/flow_draft_v1.py` | Recording 处理/审阅边界；处理器产生草稿，审阅命令驱动确认编译。 |

JSON Schema 是签入的机器契约；可执行 Pydantic 协议模型仍是运行时校验真源。对应漂移测试位于 `tests/execution/protocol/test_runner_v1.py`、`tests/execution/protocol/test_recording_v1.py` 和 `tests/execution/recording/test_flow_draft.py`。修改字段、严格性或版本前必须先更新协议决策和兼容说明；未知字段、未知版本、重复键、非有限数和不符合大小边界的输入继续拒绝。
