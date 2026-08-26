# 协议代码导航

> `product/protocols` 定义跨进程公共模型、严格解析和稳定编码；字段约束以 `schemas/` 下的 JSON Schema 为准。协议语义先从[公共数据与 Schema 版本](../../docs/04_协议与数据/公共数据与Schema版本.md)阅读。

## 主要协议文件

| 文件 | 负责什么 |
| --- | --- |
| `runner/` | `input.py`、`evidence.py`、`result.py` 与 `codec.py` 分别负责 Runner 根文档和 canonical 编码。 |
| `execution.py` | 与 Target 无关的执行预算、效果绑定和 Observer requirement binding。 |
| `execution_request.py` | Worker 交给 Runner 的冻结执行请求。 |
| `observer/` | `config.py`、`invocation.py`、`result.py` 与 `codec.py` 分别负责观察配置、调用、结果和 canonical/严格解析。 |
| `web/` | WebExecutionProfile/Snapshot、身份/秘密引用、Target scope、HTTP workflow 和 canonical profile。 |
| `recording.py` | Recording Runner 请求、事件、预算、结果和清理状态。 |
| `flow_draft.py` | FlowDraft、步骤编辑和变量确认命令。 |
| `recording_flow.py` | 审阅确认后的稳定 Flow。 |
| `test_identity_preparation.py` | 独立登录浏览器的非秘密请求、结果、预算和严格解析。 |
| `artifacts.py` | 工件检查请求、扫描结果和发布清单。 |
| `report.py` | 报告语义、报告 ID、canonical hash 和 package manifest。 |
| `__init__.py` | 对外稳定导出；新增导出前先确认存在真实跨模块消费者。 |

`schemas/` 按 `runner`、`observer`、`execution`、`identity`、`contracts`、`recording`、`artifacts` 和 `reports` 分族保存机器字段真源。

## 版本与 canonical 约束

- 当前 Web V1 的独立根文档统一使用字符串 `schema_version: "1"`；只有能够独立交换或持久化且有独立 reader 的根文档携带版本，嵌套 DTO 不重复版本。
- 每个根文档只接受一个当前 wire/schema 格式；该版本不是产品版本，也不是数据库 revision。
- 未知版本、额外字段、重复键、非有限数、超预算内容和秘密材料必须严格失败，不能猜测兼容。
- canonical 编码必须对同一语义产生稳定字节；ID、fingerprint 和 hash 只能基于对应协议定义的 canonical payload。
- Python 模型、JSON Schema、解析器和 canonical/hash 测试必须保持一致。数据库结构另由 `product/backend/migrations/` 管理，当前只有 `0001_web_v1` 基线。

`AssistantGuidanceCache` 与 `RunnerProgressEvent` 是运行时有界缓存/旁路事件，拥有严格 parser/codec 和直接测试，但不进入 `schemas/`：它们不是对外公共 Schema 根，也不参与 Report、Evidence 或数据库协议。

修改协议时，至少同步检查：对应 Python 模型、`schemas/`、`__init__.py` 导出、协议测试以及直接相关的 Protocol/Architecture。公共格式不兼容时还要给出迁移说明；不能只改消费者来绕过 Schema。

测试位于 [`tests/protocols/`](../../tests/protocols/)，执行与观察的当前边界见[执行与观察架构](../../docs/02_架构设计/执行与观察架构.md)。
