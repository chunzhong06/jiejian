# Projects

## 定位

`projects` 是项目输入进入应用能力的边界。它把磁盘中的 ProjectBundle 校验为可追踪的 Project 记录，并向 Contract 和 Execution 提供当前项目快照与可用观察器。

## 负责 / 不负责

- 负责项目登记、来源文件哈希、重新校验、当前 ProjectBundle 读取和观察器解析。
- 保留显式 YAML Contract 的兼容激活入口。
- 不创建治理 Contract，不决定 Contract 状态，也不构造或执行 Job。

## 子模块与 public API

- `service.py`：`ProjectControlService` 是仓库内跨能力入口；`file_sha256` 和 `project_source_hash` 固化来源完整性算法。
- 本 package 不承诺仓库外 Python import 兼容；调用方应导入上述叶模块。

## 调用与数据流

```text
API / CLI
→ ProjectControlService
→ verification.inputs.load_project_bundle
→ StorageUnitOfWork.projects
→ Contracts / ExecutionRequestService
```

## 关键不变量和失败语义

- 项目 ID、来源路径和来源哈希必须在重新读取时继续一致；来源漂移不能被静默接受。
- Project 只提供项目事实和观察器，不反向读取 ContractVersion。
- 项目校验失败属于输入或来源错误，不产生 Run、Job 或安全 Verdict。

## 修改与测试入口

- 输入解析与路径安全：[`verification/README.md`](../verification/README.md)、[`tests/verification`](../../../../tests/verification/)
- 持久化与 API 行为：[`tests/storage`](../../../../tests/storage/)、[`tests/api`](../../../../tests/api/)
- 端到端入口：[`tests/e2e`](../../../../tests/e2e/)

## 相关规范、协议与 ADR

- [系统数据流](../../../../docs/01_架构设计/数据流.md)
- [项目设计规范](../../../../docs/02_开发规范/项目设计规范.md)
- [ADR-0010](../../../../docs/03_技术决策/ADR-0010-阶段4控制面与WebGUI.md)、[ADR-0014](../../../../docs/03_技术决策/ADR-0014-阶段5.4A治理Contract与执行请求绑定.md)、[ADR-0017](../../../../docs/03_技术决策/ADR-0017-阶段5-O3能力优先架构迁移约束.md)
