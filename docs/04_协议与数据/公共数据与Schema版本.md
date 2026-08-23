# 公共数据与 Schema 版本

> 状态：CURRENT。本文是公共数据族索引和版本规则，不复制完整 JSON Schema。

## 目的与消费者

跨进程 Python 模型、JSON Schema、canonical/hash、strict parsing 和数据库持久化共同构成数据边界。Worker、Runner、Observer、API、CLI、GUI、报告和测试按需读取对应协议文档与 Schema。`schema_version` 只标识能够独立交换或持久化并拥有独立 reader 的根文档；只嵌入其他根的 DTO 不重复携带版本。

## 协议边界与公共数据族

| 独立根文档 | Python 真源 | checked-in Schema | 当前格式 |
| --- | --- | --- | --- |
| `PermissionContract` | `product/backend/core/verification/permissions.py` | `schemas/contracts/permission-contract.schema.json` | 4 |
| `WebExecutionProfile` | `web/profile.py` | `schemas/execution/web-execution-profile.schema.json` | 4 |
| `PersistedExecutionRequest`、`RunnerInput`、`Evidence`、`RunnerResult` | `execution_request.py`、`runner.py` | `schemas/runner/` | 4 |
| Observer Invocation 与 `ObservationEnvelope` | `observer.py` | `schemas/observer/` | 3 |
| `RecordingRunnerRequest`、`RecordingEvent`、`RecordingRunnerResult`、`FlowDraft` | `recording.py`、`flow_draft.py` | `schemas/recording/` | 2 |
| FlowDraft 审阅命令 | `flow_draft.py` | `flow-draft-review-command.schema.json` | 1 |
| `Flow` | `recording_flow.py` | `schemas/recording/flow.schema.json` | 4 |
| `ArtifactCheckRequest`、`ArtifactScanResult`、`ArtifactResultManifest` | `artifacts.py` | `schemas/artifacts/` | 2 |
| `BaseRunReport`、`GateRunReport`、`ReportPackageManifest` | `report.py` | `schemas/reports/` | 4 |
| `TrustedResultReceipt` | `product/backend/infra/artifacts/run_packages.py` | `schemas/runner/trusted-result-receipt.schema.json` | 1 |
| `PublicationManifest` | `product/backend/infra/artifacts/run_packages.py` | `schemas/artifacts/publication-manifest.schema.json` | 2 |

API `ApiResponse` 根格式为 2，`HealthResponse`、`ReadyResponse` 和各独立请求体为 1；运行配置 `Settings` 为 1，CLI `DoctorReport` 为 2。它们的 Python 真源位于相应 API 或运行时入口，目前没有 checked-in JSON Schema。Sample 的 `scenario.json`、`truth.json` 是版本 2 的演示根文档，只由 Sample 启动器和测试读取，产品代码不得据此决定 Verdict。

## 生命周期与数据流

根文档先由严格 Python 模型或明确 reader 解析和校验，再通过 canonical 序列化生成稳定 hash；跨进程边界消费 Schema 约束，持久化边界另由 migration 和 Storage 管理。协议版本不等于数据库 revision，也不等于产品代际。关系型拆列记录、API `data` 内部视图、预算、binding、locator、Plan、Fact、Finding 和 Gate 组成对象均不是独立 JSON 根。

## 失败与安全语义

未知版本、缺失 required、额外字段、类型错误、canonical/hash 不一致、身份关联错误、大小/预算越界和秘密出现于公共数据中均严格失败。每个根文档在根类上显式声明自己的当前唯一版本，parser 不从公共基类默认版本或旧 reader 猜测格式；解析错误必须脱敏，不能回退到旧开发格式或猜测迁移。

## 兼容规则

当前不兼容旧开发数据库、Profile、Run、Evidence、Artifact、Report 或旧 wire format。每个根只接受上表当前格式，不提供旧 reader、fallback 或 alias；嵌套 DTO 的变化由所属根版本和 canonical 回归保护。数据库只接受唯一 Alembic revision `0001_initial`，数据库 revision 与根文档版本不能互相替代。

## 版本规则与 Schema 真源

唯一机器真源是 `product/protocols/` 与 `product/protocols/schemas/`。协议 Markdown 只描述消费者、生命周期、安全边界和失败语义；字段、required、枚举和类型以 JSON Schema 与 Python 模型为准。

## 相关真源

- [工程设计规范](../01_技术规范/工程设计规范.md)
- [数据与持久化架构](../02_架构设计/数据与持久化架构.md)
- `product/backend/migrations/`
- `product/protocols/`
