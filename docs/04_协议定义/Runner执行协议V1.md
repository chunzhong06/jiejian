# 阶段 2 Runner 协议 V1

本文是 [ADR-0002](../03_技术决策/ADR-0002-阶段2执行协议.md) 的字段级协议。实现真源是 `backend/src/jiejian/protocols/runner_v1.py`，稳定公共导入面是 `jiejian.protocols`，签入 Schema 是 `schemas/runner/runner-input-v1.schema.json` 和 `runner-result-v1.schema.json`。

## 1. 编码与边界函数

- 编码：UTF-8，无 BOM。
- JSON：对象键按 Unicode 排序，分隔符为 `,` 和 `:`，不输出额外空白或换行。
- 数值：禁止 NaN、Infinity 和 -Infinity。
- 对象：任意层级重复键、未知字段和未知 `schema_version` 均拒绝。
- 输入大小：最多 1,048,576 字节，在 UTF-8 解码和 JSON 解析前检查。
- 结果大小：最多 4,194,304 字节，在 UTF-8 解码和 JSON 解析前检查。
- 哈希：对规范 JSON 字节计算小写十六进制 SHA-256。

公开安全边界函数：

- `canonical_json_bytes(document, *, known_secrets=())`：规范序列化 RunnerInputV1 或 RunnerResultV1，并执行秘密扫描和对应大小限制。
- `canonical_json_sha256(document, *, known_secrets=())`：将 `known_secrets` 原样传递给规范序列化边界，再对规范字节计算 SHA-256。
- `parse_runner_input(raw, *, known_secrets=())`：按 1 MiB、重复键、非有限数、秘密、版本、字段和模型约束解析输入。
- `parse_runner_result(raw, *, known_secrets=())`：按 4 MiB 及同等严格规则解析结果。

`known_secrets` 是阶段 2.3 调用方提供的当前尝试真实秘密值集合。规范序列化在编码前扫描模型数据；解析先形成经过重复键和非有限数检查的 JSON 对象，再在 Pydantic 校验前扫描。扫描覆盖对象键及所有字符串值，任一非空秘密作为子串出现即以固定错误码 `PROTOCOL_SECRET_EXPOSED` 和固定文本拒绝；空秘密忽略。异常不得包含秘密、所在字段名或原始值。

其他解析失败使用稳定错误码 `PROTOCOL_INVALID` 或 `PROTOCOL_TOO_LARGE`，错误文本和 details 只包含有上限的稳定错误类型与错误数量，不回显原始输入值或不受信任的字段名。

## 2. 公共标识与时间

| 名称 | 格式或语义 |
| --- | --- |
| project_id | 阶段 1 slug，`^[a-z][a-z0-9_-]{0,63}$` |
| run_id | `run_` + 32 位小写 UUID hex |
| job_id | `job_` + 32 位小写 UUID hex |
| evidence_id | 阶段 1 内容寻址 ID |
| `*_at_us` | 自 Unix epoch 起的 UTC 微秒非负整数 |
| `*_after_us` | 以微秒表示的延迟或可用时间语义 |

时间值由调用方提供。协议模块不读取系统时钟。

## 3. RunnerInputV1

顶层字段全部必填：

| 字段 | 类型 | 约束 |
| --- | --- | --- |
| schema_version | string | 只能为 `"1"` |
| run_id | string | `^run_[0-9a-f]{32}$` |
| job_id | string | `^job_[0-9a-f]{32}$` |
| attempt | integer | 1 基，至少 1 |
| lease_owner | string | 当前 claim 的 Worker 实例标识，1..128 个受限字符 |
| fencing_token | integer | Job 内单调递增正整数 |
| created_at_us | integer | UTC Unix 微秒，至少 0 |
| budget | ExecutionBudgetV1 | 本次执行不可变预算 |
| project_snapshot | ExecutionProjectSnapshotV1 | 完整执行内容快照 |

模型配置为 `extra=forbid`、`frozen=True`、严格类型。一个输入对应一个完整 Run 尝试，不按 TestCase 拆 Runner。

### 3.1 ExecutionBudgetV1

| 字段 | 类型 | 约束 |
| --- | --- | --- |
| schema_version | string | `"1"` |
| max_requests | integer | 1..500，必须等于 TargetScope.max_requests |
| request_timeout_us | integer | 1..30,000,000，必须等于 TargetScope.timeout_seconds 的微秒值 |
| max_duration_us | integer | 1..3,600,000,000 |
| max_response_bytes | integer | 1..4,194,304，必须等于 TargetScope.max_response_bytes |
| max_parallel_cases | integer | V1 固定为 1 |

### 3.2 ExecutionProjectSnapshotV1

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| schema_version | string | `"1"` |
| project_id | string | 项目公共 slug |
| project_name | string | 1..128 字符 |
| target | TargetScope | 阶段 1 严格安全范围快照 |
| identities | Identity[] | 至少两个，ID 唯一，只含 `env:NAME` 秘密引用 |
| resources | ResourceDefinition[] | 至少两个，ID 唯一且 owner 引用有效身份 |
| flow | Flow | 阶段 1 完整 Flow 内容，不含文件路径 |
| contract | SecurityContract | 阶段 1 完整契约内容，不含文件路径 |
| owner_observer_enabled | boolean | owner_api 观察器开关快照 |
| mutation_seed | integer | 确定性变异 seed |

快照拒绝敏感字段名、Bearer 文本和凭据赋值文本。`secret_ref` 是唯一秘密相关字段，只接受 `env:[A-Z][A-Z0-9_]{0,127}`。身份 ID、资源 ID、Flow step ID、Contract rule ID 和 RuleKind 均不得重复，契约必须为 ACTIVE；每个 Flow 至少需要 foreign_read，存在非 GET step 时还必须包含 unauthorized_side_effect 和 privileged_field。Runner 不读取 ProjectDefinition.flow_path、contract_path 或任何 YAML。

## 4. RunnerResultV1

顶层字段：

| 字段 | 类型 | 约束 |
| --- | --- | --- |
| schema_version | string | 只能为 `"1"` |
| run_id | string | 必须匹配输入 run_id |
| job_id | string | 必须匹配输入 job_id |
| attempt | integer | 必须匹配输入 attempt |
| lease_owner | string | 必须匹配输入与当前 lease owner |
| fencing_token | integer | 必须匹配当前 lease token |
| finished_at_us | integer | UTC Unix 微秒，至少 0 |
| result_type | enum | SUCCESS、SAFETY_STOPPED、CANCELLED、RETRYABLE_ERROR、FATAL_ERROR |
| run_lifecycle | RunLifecycle | 受第 5 节矩阵约束 |
| job_state | JobState | 受第 5 节矩阵约束 |
| verdict | RunVerdict 或 null | 只有 SUCCESS 非空 |
| reason_codes | string[] | 最多 128 个、不重复、`^[A-Z][A-Z0-9_]{0,127}$` |
| cleanup | CleanupResultV1 | 清理结果 |
| error | RunnerErrorV1 或 null | 只有错误结果非空 |
| artifacts | StagedArtifactV1[] | 最多 4096 项，路径按 casefold 唯一，总 byte_count 不超过 1 GiB |

### 4.1 CleanupResultV1

- `schema_version`：`"1"`。
- `status`：NOT_REQUIRED、SUCCEEDED 或 FAILED。
- `reason_codes`：最多 64 个稳定代码。FAILED 必须至少一个；其他状态必须为空。

### 4.2 RunnerErrorV1

- `schema_version`：`"1"`。
- `code`：稳定大写错误码，最多 128 字符。
- `retryable`：RETRYABLE_ERROR 必须为 true，FATAL_ERROR 必须为 false。

V1 不允许自由文本错误消息进入 Runner 结果。诊断文本只进入统一脱敏日志。

### 4.3 StagedArtifactV1

- `schema_version`：`"1"`。
- `path`：1..512 字符的规范相对 POSIX 路径。
- `byte_count`：0..1,073,741,824。
- `sha256`：64 位小写十六进制。

路径不得以 `/` 开头，不得含 Windows 盘符、冒号或 ADS、反斜杠、Windows 禁止字符、控制字符、空段、`.` 或 `..`。每段不得超过 255 字符或以点、空格结尾，并拒绝忽略大小写且可带扩展名的 CON、PRN、AUX、NUL、COM1..9、LPT1..9。相同结果内路径按 `casefold()` 不得重复。

每个工件保留 1 GiB 单项上限，同一 RunnerResultV1 的 `byte_count` 总和也不得超过 1 GiB。等于上限允许，超过上限在 Worker 使用结果或校验暂存文件前由协议模型拒绝。

## 5. 结果矩阵

| result_type | run_lifecycle | job_state | verdict | error | cleanup |
| --- | --- | --- | --- | --- | --- |
| SUCCESS | COMPLETED | SUCCEEDED | PASS、BLOCK、INCONCLUSIVE | null | NOT_REQUIRED 或 SUCCEEDED |
| SAFETY_STOPPED | SAFETY_STOPPED | SUCCEEDED | null | null | NOT_REQUIRED 或 SUCCEEDED；reason_codes 非空 |
| CANCELLED | CANCELLED | CANCELLED | null | null | 必须 SUCCEEDED |
| RETRYABLE_ERROR | PREFLIGHT、PLANNING、EXECUTING、VERIFYING、REPORTING 之一 | RETRY_WAIT | null | 必填且 retryable=true | NOT_REQUIRED 或 SUCCEEDED |
| FATAL_ERROR | FAILED | FAILED | null | 必填且 retryable=false | NOT_REQUIRED、SUCCEEDED 或 FAILED |

RunnerResultV1 的模型校验拒绝表外组合。尤其禁止把启动、协议、租约、工件、持久化或清理失败包装为 verdict=INCONCLUSIVE。

## 6. Job 字段语义

下列字段在阶段 2.1 数据库中按本节实现，不在阶段 2.0 创建数据库 DTO 或服务：

| 字段 | 冻结语义 |
| --- | --- |
| idempotency_key | 调用者提供的非秘密幂等键；作用域是 project_id、操作类型和该键 |
| request_hash | 创建请求规范字节的小写 SHA-256 |
| attempt | 已启动尝试数；初始 0，claim 新执行尝试时递增 |
| max_attempts | 包含首次执行的硬上限，至少 1 |
| available_at_us | 最早可 claim 的 UTC Unix 微秒时间 |
| lease_owner | 当前 Worker 实例标识，不是主机秘密 |
| fencing_token | 每次 claim 产生的 Job 内单调递增正整数；续租不改变 |
| lease_expires_at_us | 当前租约截止 UTC Unix 微秒 |
| cancel_requested_at_us | 首次取消请求时间；写入后不清空 |

相同幂等作用域和相同 request_hash 返回既有 Job/Run；不同 request_hash 返回 `JOB_IDEMPOTENCY_CONFLICT`。每个有副作用的写入必须同时匹配 job_id、lease_owner、fencing_token。

租约到期后先进入恢复审计。只有确认旧 Runner 已退出或清理完成，才允许产生新 token 并启动下一尝试；租约到期本身不授权重复目标请求。

## 7. staging、发布与事务

1. Runner 在 Worker 指定的 staging 根目录内写相对工件和结果临时文件。
2. Runner 原子形成结果文件后以进程退出码 0 表示“结果候选已形成”，不表达安全 verdict。
3. Worker 严格解析结果，匹配 run_id、job_id、attempt、lease_owner、fencing_token，并逐项验证路径、byte_count 和 SHA-256。
4. Worker 拒绝任何旧 fencing token，然后原子 promote 整个 staging 目录。
5. promote 成功后，Worker 在同一 Unit of Work 中提交 Run、Job、事件和 Evidence 索引完成态。

数据库不得先于 promote 标记完成。promote 成功而数据库提交失败的目录保留，由阶段 2.4 reconciliation 处理，不能由 Runner 删除或重新发布。

## 8. Runner 进程退出码

| 退出码 | 含义 |
| --- | --- |
| 0 | 已原子生成完整结果文件；Worker 仍需验证 Schema、fencing 和工件 |
| 64 | 输入、大小、JSON 或协议版本错误，没有可信结果 |
| 70 | Runner 启动或内部故障，没有可信结果 |
| 74 | 结果或 staging 写入失败，没有可信结果 |

PASS、BLOCK、INCONCLUSIVE、SAFETY_STOPPED 和 CANCELLED 只存在于结果文件，不编码在进程退出码中。

## 9. CLI 和秘密边界

阶段 2.3 后 CLI 只提交、等待、取消和展示 Job；所有目标流量由 Runner 发出。阶段 2.0 不修改 CLI 或 RunService。

RunnerInputV1 和持久快照只含 `env:NAME`。阶段 2.3 的 Worker 在启动 Runner 前解析当前尝试需要的最小秘密集合，通过子进程环境传递。真实值不得出现在 argv、输入、结果、错误、日志、工件清单或数据库字段中。
