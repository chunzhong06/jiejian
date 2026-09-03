# 公共数据与 Schema 版本

> 状态：CURRENT。本文是公共数据族索引和版本规则，不复制完整 JSON Schema。

## 目的与消费者

跨进程 Python 模型、JSON Schema、canonical/hash、strict parsing 和数据库持久化共同构成数据边界。Worker、Runner、Observer、API、CLI、GUI、报告和测试按需读取对应协议文档与 Schema。`schema_version` 只标识能够独立交换或持久化并拥有独立 reader 的根文档；只嵌入其他根的 DTO 不重复携带版本。

## 协议边界与公共数据族

| 独立根文档 | Python 真源 | checked-in Schema | 当前格式 |
| --- | --- | --- | --- |
| `PermissionContract`、规范化/覆盖/差分计划 | `product/backend/core/verification/permissions/`、`differential.py` | `schemas/contracts/` | 1 |
| `WebExecutionProfile`、`HttpRequestTemplate` | `web/profile.py`、`web/request.py` | `schemas/execution/` | 1 |
| `PersistedExecutionRequest` | `execution_request.py` | `schemas/runner/persisted-execution-request.schema.json` | 2 |
| `RunnerInput`、`Evidence`、`RunnerResult` | `runner/` | `schemas/runner/` | 1 |
| Observer Invocation、`ObservationEnvelope` | `observer/` | `schemas/observer/`；同时签入 `ObserverSpec`/`ObserverOutcome` 组件 Schema | 1 |
| `RecordingRunnerRequest`、`RecordingEvent`、`RecordingRunnerResult` | `recording.py` | `schemas/recording/` | 1 |
| `FlowDraft`、FlowDraft 审阅命令 | `flow_draft.py` | `schemas/recording/` | 1 |
| `Flow` | `recording_flow.py` | `schemas/recording/flow.schema.json` | 1 |
| `IdentityPreparationRequest`、`IdentityPreparationResult` | `test_identity_preparation.py` | `schemas/identity/` | 1 |
| `ArtifactCheckRequest`、`ArtifactScanResult`、`ArtifactResultManifest`、`PublicationManifest` | `artifacts.py`、`run_packages.py` | `schemas/artifacts/` | 1 |
| `BaseRunReport`、`GateRunReport` | `report.py` | `schemas/reports/report.schema.json` | 5 |
| `ReportPackageManifest` | `report.py` | `schemas/reports/report-package-manifest.schema.json` | 1 |
| `TrustedResultReceipt` | `product/backend/infra/artifacts/run_packages.py` | `schemas/runner/trusted-result-receipt.schema.json` | 1 |
| `RunnerProgressEvent` | `product/backend/infra/runtime/runner/progress.py` | 无；内部有界 JSONL reader | 1 |

API `ApiResponse` 根格式为字符串 1，前端必须先严格验证该最外层版本再读取 `data` 或脱敏错误；未知或缺失版本直接失败。`HealthResponse`、`ReadyResponse`、各独立请求体、运行配置 `Settings` 和 CLI `DoctorReport` 也为 1。ApplicationUnderstanding、ApplicationConnectionView、EndpointDiscoveryResult、ProjectReadiness、AIAssistanceSettings、GuidanceSnapshot、AssistantGuidanceView、ErrorDiagnosis、LLMModelCatalog、LLMProfileView 和其他 `ApiResponse.data` 或 error 内部视图不重复声明版本。它们的 Python 真源位于相应 API 或运行时入口，目前没有 checked-in JSON Schema。Sample 的 `scenario.json`、`truth.json`、`contract.json`、`profile.json` 是当前 Web V1 演示根文档，格式版本统一为 1；样例不扩展 Verdict 覆盖范围。

AI 模板输入、模型输出、assistant refresh 请求体与 assistant cache entry 是各自拥有严格 reader 的版本 1 根文档。模型输出只接受固定模板身份、最多三条不重复 recommendation 和本次系统提供的 option ID；缓存成功记录只保存 provider/profile/model、推理设置、模板身份、事实指纹、已验证推荐和生成时间，失败记录只保存稳定错误码与退避时间。它们没有 checked-in Schema，严格 Python reader 与本地白名单 validator 是当前机器边界真源。

`RunnerProgressEvent` 每行独立持久化并由专用 reader 读取，因此携带自己的格式 1；`GET /api/jobs/{job_id}/progress` 的 `data` 只是 `ApiResponse` 内部视图，不再重复版本。该事件是 staging 外的非权威运行中旁路，不进入 RunnerResult、Evidence、publication、Finding、Report、Gate 或恢复语义。

`ChangeVerificationContext` 与 `RepairVerificationContext` 只嵌入 `PersistedExecutionRequest`，不是独立交换根，因此不重复 `schema_version`。当前请求在顶层冻结项目源码指纹；`ChangeVerificationContext` 只保留变化身份、影响指纹和必需权限集合。`RepairVerificationContext` 冻结权威修复引用、原 `policy_epoch`、原权限身份、必须消失的效果、必须保留的 ALLOW 控制和原关键证据标准。文件清单、diff、源码内容与补丁建议都不进入执行请求。

当前 Job 与 Worker 只接受格式 2。已发布历史结果有一个明确的只读例外：历史 reader 可以解析严格 canonical 的格式 1 请求，用于 Result、History 与 RepairContract 重建；它不会补猜格式 1 缺少的项目级源码身份，也不能把历史请求送回当前执行入口。只有格式 2 请求能作为新的 Run 输入。

## 生命周期与数据流

根文档先由严格 Python 模型或明确 reader 解析和校验，再通过 canonical 序列化生成稳定 hash；跨进程边界消费 Schema 约束，持久化边界另由 migration 和 Storage 管理。协议版本不等于数据库 revision，也不等于产品代际。关系型拆列记录、API `data` 内部视图、预算、binding、locator、Plan、Fact、Finding 和 Gate 组成对象均不是独立 JSON 根。

## 失败与安全语义

未知版本、缺失 required、额外字段、类型错误、canonical/hash 不一致、身份关联错误、大小/预算越界和秘密出现于公共数据中均严格失败。每个根文档在根类上显式声明自己的当前唯一版本，parser 不从公共基类默认版本或旧 reader 猜测格式；解析错误必须脱敏，不能回退到旧开发格式或猜测迁移。

## 兼容规则

当前不兼容旧开发数据库、Profile、Evidence、Artifact、Report 或任意旧 wire format。除已发布 `PersistedExecutionRequest` 格式 1 的严格只读历史入口外，每个根只接受上表当前格式，不提供 fallback 或 alias；嵌套 DTO 的变化由所属根版本和 canonical 回归保护。数据库只接受签入的 `0001_business_boundary_v2` fresh 基线与精确结构；旧 1.x revision 只读拒绝。数据库 revision 与根文档版本不能互相替代。

## 版本规则与 Schema 真源

唯一机器真源是 `product/protocols/` 与 `product/protocols/schemas/`。协议 Markdown 只描述消费者、生命周期、安全边界和失败语义；字段、required、枚举和类型以 JSON Schema 与 Python 模型为准。

## 相关真源

- [工程设计规范](../../04_工程约束/工程设计.md)
- [数据与持久化架构](../../01_系统地图/数据与持久化.md)
- `product/backend/migrations/`
- `product/protocols/`

<!-- GENERATED:START -->

<!-- Schema 文件由 product/protocols/schema.py 注册表治理；本区只列当前文件。 -->

- `product/protocols/schemas/artifacts/artifact-check-request.schema.json`
- `product/protocols/schemas/artifacts/artifact-result-manifest.schema.json`
- `product/protocols/schemas/artifacts/artifact-scan-result.schema.json`
- `product/protocols/schemas/artifacts/publication-manifest.schema.json`
- `product/protocols/schemas/contracts/differential-experiment-plan.schema.json`
- `product/protocols/schemas/contracts/normalized-permission-plan.schema.json`
- `product/protocols/schemas/contracts/permission-contract.schema.json`
- `product/protocols/schemas/contracts/permission-mutation-plan.schema.json`
- `product/protocols/schemas/execution/http.schema.json`
- `product/protocols/schemas/execution/web-execution-profile.schema.json`
- `product/protocols/schemas/identity/identity-preparation-request.schema.json`
- `product/protocols/schemas/identity/identity-preparation-result.schema.json`
- `product/protocols/schemas/observer/async-task-observer-invocation.schema.json`
- `product/protocols/schemas/observer/audit-log-observer-invocation.schema.json`
- `product/protocols/schemas/observer/observation-envelope.schema.json`
- `product/protocols/schemas/observer/observer-invocation.schema.json`
- `product/protocols/schemas/observer/observer-outcome.schema.json`
- `product/protocols/schemas/observer/observer-spec.schema.json`
- `product/protocols/schemas/recording/flow-draft-review-command.schema.json`
- `product/protocols/schemas/recording/flow-draft.schema.json`
- `product/protocols/schemas/recording/flow.schema.json`
- `product/protocols/schemas/recording/recording-event.schema.json`
- `product/protocols/schemas/recording/recording-runner-request.schema.json`
- `product/protocols/schemas/recording/recording-runner-result.schema.json`
- `product/protocols/schemas/reports/report-package-manifest.schema.json`
- `product/protocols/schemas/reports/report.schema.json`
- `product/protocols/schemas/runner/evidence.schema.json`
- `product/protocols/schemas/runner/persisted-execution-request.schema.json`
- `product/protocols/schemas/runner/runner-input.schema.json`
- `product/protocols/schemas/runner/runner-result.schema.json`
- `product/protocols/schemas/runner/trusted-result-receipt.schema.json`

<!-- GENERATED:END -->
