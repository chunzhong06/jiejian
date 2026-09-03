# 公共协议模块

> 状态：CURRENT。`product/protocols` 是跨进程、独立持久化或对外交换根文档、严格解析、canonical/hash 与 Schema 注册的唯一代码入口。

## 职责

公共协议定义 Worker/Runner、Observer、Web 执行、Recording/Flow、Artifact、Report 等机器边界。每个独立根只接受当前 `schema_version`，由严格模型、reader、canonical/hash、大小/秘密约束和已签入 JSON Schema 共同证明。

## 非职责

协议不编排业务事务、不访问数据库或网络、不决定 PASS/BLOCK/INCONCLUSIVE，也不因为多个模型字段相似就合并 canonical。人工 Reference 解释语义，不能代替 Python 模型和 Schema 的字段真源；自动代码参考也不能代替长期设计理由。

## 稳定入口与协议族

| 位置 | 负责什么 | 不负责什么 |
| --- | --- | --- |
| `product/protocols/runner/` | RunnerInput、Evidence、RunnerResult、严格 codec 与语义 hash | Worker claim、进程和 publication |
| `product/protocols/observer/` | Observer 调用、信封、状态 canonical 与严格 codec | 具体数据源读取和 Verdict |
| `product/protocols/web/` | Web Profile、身份、scope、workflow 与冻结配置模型 | HTTP 网络执行实现 |
| `product/protocols/recording.py`、`product/protocols/flow_draft.py`、`product/protocols/recording_flow.py` | Recording/FlowDraft/Flow 根文档 | 浏览器采集和用户审阅事务 |
| `product/protocols/report.py` | Base/Gate Report、manifest、canonical 与投影输入 | Finding 最终化和文件发布 |
| `product/protocols/schemas/` | 当前签入 JSON Schema 与 Registry 消费物 | 人工职责说明、旧格式兼容 |
| `product/protocols/schema.py` | 生成、只读漂移检查与注册表 | 自动修改业务模型 |

协议语义入口见 [公共数据与 Schema 版本](../../03_参考手册/协议/公共数据与Schema版本.md)，字段索引由生成区域维护。

## 我想修改什么

| 任务 | 主要位置 | 直接验证 |
| --- | --- | --- |
| RunnerInput/Evidence/RunnerResult 字段或 hash | `product/protocols/runner/`、`schemas/runner/` | `dev.ps1 test tests/protocols/runner`；稳定身份回归；Schema |
| Observer 调用、状态或 codec | `product/protocols/observer/`、`schemas/observer/` | `dev.ps1 test tests/protocols/observer tests/backend/infra/observers` |
| Web Profile、Workflow 或 Identity | `product/protocols/web/`、`schemas/execution/`、`schemas/identity/` | `dev.ps1 test tests/protocols/web tests/backend/infra/execution` |
| Recording、FlowDraft 或 Flow | `recording.py`、`flow_draft.py`、`recording_flow.py` 与 `schemas/recording/` | `dev.ps1 test tests/protocols/test_recording.py tests/backend/workflows/recording` |
| Report 与 package manifest | `product/protocols/report.py`、`schemas/reports/` | report protocol、results workflow、artifact store 直接测试 |
| Artifact publication 或 scan 文档 | `product/protocols/artifacts.py`、`schemas/artifacts/` | artifact protocol + `tests/backend/infra/artifacts` |
| Schema 生成器或 Registry | `product/protocols/schema.py` 中的 `SCHEMA_REGISTRY` | 先 `dev.ps1 schema -Update`，再 `dev.ps1 schema` |
| 协议语义 Reference | `docs/03_参考手册/协议/` | `dev.ps1 docs`；不手改自动代码参考 |

## 变更路线

先确认对象是否真是独立根：只有独立持久化、跨进程或对外交换且有独立 reader 的文档携带 `schema_version`；嵌套 DTO 不重复版本。字段变化先改严格模型和 reader，再同步 canonical/hash、Schema Registry、生产消费者、Sample/fixture、测试和 CURRENT Reference。

兼容不是默认选项。当前 Web V1 的旧开发格式不保留 reader；未知字段、未知版本、非 JSON、NaN、秘密、超预算和 canonical 不一致全部 fail closed。只有新的正式兼容决策证明真实外部消费者与迁移路线后，才设计多版本边界。

## 一次协议变更的完整路线

1. 识别 writer、独立 root、持久化/传输位置以及全部 reader，先证明它确实需要公共协议。
2. 冻结字段语义、必填性、枚举、预算、秘密边界和 canonical/hash 身份；版本升级按单个根文档裁决。
3. 修改严格 Pydantic 模型与 codec，并让未知字段、错误版本、非有限数、超限内容继续 fail closed。
4. 同步所有生产 writer/reader、Sample、fixture 和 CURRENT Reference；没有正式兼容决策时删除旧格式，而不是保留 alias。
5. 经 `schema -Update` 更新已签入 Schema/Registry，再用只读 `schema` 证明零漂移；最后运行协议族测试和一个直接生产消费者。

## 必须保持的边界

- Schema 版本描述机器格式，不等于产品 1.1.0，也不随产品版本机械升级。
- 不把多个领域 hash 合成万能 helper；各函数的允许类型、排除字段、排序、大小和安全语义不同。
- 协议模型不导入 workflows、infra、API 或 CLI；具体 Adapter 不成为 Schema 真源。
- 秘密正文、密码、Cookie、Token、SAS、环境全量和原始敏感响应不得进入公共协议。
- signed-in 生成区只由 `schema -Update`/`docs -Update` 维护；手工正文不写进生成标记之间。
- 修改 reader 不能只放宽消费者而跳过模型、Schema 或稳定身份测试。
- 根版本变化要逐根裁决；一个协议变化不驱动所有嵌套对象同步加版本。

## 直接验证

```powershell
.\scripts\dev.ps1 test tests/protocols/observer
.\scripts\dev.ps1 test tests/protocols/runner
.\scripts\dev.ps1 schema -Update
.\scripts\dev.ps1 schema
.\scripts\dev.ps1 docs
```

只选择实际协议族；公共 Schema 变化必须先更新再只读复核，单纯文档修改不运行 `schema -Update`。最终补生产消费者的直接测试、Python AST/职责头和 `git diff --check`。

## 首错定位

| 现象 | 先检查 | 不要先做 |
| --- | --- | --- |
| Schema 漂移 | 模型、注册表、签入 Schema 是否由同一次 `schema -Update` 生成 | 手工改 JSON Schema |
| writer 能写、reader 拒绝 | 根版本、未知字段、canonical、预算和实际 import 的 codec | 在 reader 增加宽松 fallback |
| hash 在进程间不同 | 明确所属 hash 函数、排序/排除字段和 canonical bytes | 建一个“通用 hash helper”统一所有领域 |
| fixture 通过、正式进程失败 | fixture 是否由当前正式模型序列化，生产 reader 是否读取同一根 | 给 tests composition 泄漏生产 fallback |
| 协议带入秘密或全量环境 | root 字段、异常正文、Evidence/Report 投影 | 只在 renderer 层做字符串替换 |

## 相关真源

- [公共数据与 Schema 版本](../../03_参考手册/协议/公共数据与Schema版本.md)
- [Runner 执行协议](../../03_参考手册/协议/Runner执行协议.md)
- [Observer 观察协议](../../03_参考手册/协议/Observer观察协议.md)
- [Web 执行配置与冻结快照](../../03_参考手册/协议/Web执行配置与冻结快照.md)
- [验证与测试](../../04_工程约束/验证与测试.md)
