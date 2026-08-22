# 公共数据与 Schema 版本

> 状态：CURRENT。本文是公共数据族索引和版本规则，不复制完整 JSON Schema。

## 目的与消费者

跨进程 Python 模型、JSON Schema、canonical/hash、strict parsing 和数据库持久化共同构成数据边界。Worker、Runner、Observer、API、CLI、GUI、报告和测试按需读取对应协议文档与 Schema。

## 协议边界与公共数据族

| 数据族 | Python 真源 | Schema 目录 | 当前主要版本 |
| --- | --- | --- | --- |
| Runner/Input/Request/Evidence/Result | `runner.py`、`execution_request.py` | `schemas/runner/` | 3 |
| Observer | `observer.py` | `schemas/observer/` | 2 |
| ExecutionProfile | `execution_profile.py` | `schemas/execution/` | 2 |
| Contract/Plan | core 权限模型与协议模型 | `schemas/contracts/` | 2 |
| Recording/FlowDraft/Event | `recording.py`、`flow_draft.py`、`recording_flow.py` | `schemas/recording/` | 1 |
| Artifact | `artifacts.py` | `schemas/artifacts/` | 1 |
| Report/Package Manifest | `report.py` | `schemas/reports/` | 3 |

`flow-draft-review-command.schema.json` 当前没有 `schema_version` 字段；不得为了表格完整而补写字段。

## 生命周期与数据流

公共模型先由严格 Python 模型解析和校验，再通过 canonical 序列化生成稳定 hash；跨进程边界消费 Schema 约束，持久化边界另由 migration 和 Storage 管理。协议版本不等于数据库 revision，也不等于产品代际。

## 失败与安全语义

未知版本、缺失 required、额外字段、类型错误、canonical/hash 不一致、身份关联错误、大小/预算越界和秘密出现于公共数据中均严格失败。每个公共根文档显式声明自己的当前唯一版本，parser 不从公共基类默认版本或旧 reader 猜测格式；解析错误必须脱敏，不能回退到旧开发格式或猜测迁移。

## 兼容规则

当前不兼容旧开发数据库、Profile、Run、Evidence、Artifact、Report 或旧 wire format。公共 Schema 只接受代码明确支持的版本；数据库 revision 由 Alembic 管理，二者不能互相替代。

## 版本规则与 Schema 真源

唯一机器真源是 `product/protocols/` 与 `product/protocols/schemas/`。协议 Markdown 只描述消费者、生命周期、安全边界和失败语义；字段、required、枚举和类型以 JSON Schema 与 Python 模型为准。

## 相关真源

- [工程设计规范](../01_技术规范/工程设计规范.md)
- [数据与持久化架构](../02_架构设计/数据与持久化架构.md)
- `product/backend/migrations/`
- `product/protocols/`
