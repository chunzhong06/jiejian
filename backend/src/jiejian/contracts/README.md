# Contracts

## 定位

`contracts` 把安全 Requirement 转换为可审阅、可版本化、可绑定到新 Run 的 SecurityContract。Requirement、Candidate、ContractVersion 和执行快照处于不同信任层级，不能因字段相似而合并。

## 负责 / 不负责

- 负责 Requirement、来源引用、Candidate、provenance、版本状态机、Workbench、确定性分析、六类 Drift 和受限 LLM Candidate。
- 负责把项目绑定的 ACTIVE 版本冻结到新 ExecutionRequest。
- 不发送目标流量，不直接产生 Evidence/Verdict，也不允许 LLM 激活 Contract。

## 子模块与 public API

- `models.py`：治理模型和版本状态。
- `governance.py` / `governance_service.py`：纯状态转换与事务编排。
- `analysis/`：来源适配、合并、assessment、Diff、历史解析和六类 Drift。
- `llm/`：profile CRUD/resolver、秘密引用、显式连接测试、有界输入、严格 JSON 输出和不可信 Candidate 适配；适配器不把明文秘密交给持久层。
- `workbench.py`：API、CLI、GUI 共享的仓库内应用入口 `ContractWorkbenchService`。
- `execution_binding.py`：`resolve_execution_contract`，只接受项目绑定的 ACTIVE 治理版本或显式兼容输入。

本能力没有 package-root 聚合导出；跨能力调用应使用具体叶模块。

## 调用与数据流

```text
Requirement / Flow / OpenAPI / 授权源码 / 受限 LLM
→ ContractCandidate
→ merge + assessment
→ DRAFT → REVIEW → ACTIVE / REJECTED / SUPERSEDED
→ Project 绑定
→ ExecutionRequest 中的冻结 Contract 快照
```

## 关键不变量和失败语义

- Candidate 始终是不可信候选；只有治理状态机可以形成 ACTIVE Contract。
- ACTIVE 和 SUPERSEDED 版本正文不可原地修改；修订创建新 DRAFT。
- 激活新版本时，旧 ACTIVE、当前版本和 Project 绑定在同一事务中更新。
- 六类 Drift 是确定性派生结果，不修改历史 Run，也不替代 Verdict。
- LLM 只接收显式选择、脱敏且有界的 Requirement，默认离线；解析或评估失败不得产生部分持久化。
- profile 的 `secret_ref` 只指向环境变量或 Windows Credential Manager；密钥不进入响应、日志、Candidate 或 provenance。

## 修改与测试入口

- 能力测试：[`tests/contracts`](../../../../tests/contracts/)
- REST 工作台：[`tests/api/test_contract_workbench.py`](../../../../tests/api/test_contract_workbench.py)
- CLI 工作台：[`tests/e2e/test_cli_contract_workbench.py`](../../../../tests/e2e/test_cli_contract_workbench.py)
- 持久化：[`tests/storage/test_contract_storage.py`](../../../../tests/storage/test_contract_storage.py)

## 相关规范、协议与 ADR

- [数据格式](../../../../docs/04_协议定义/数据格式.md)
- [ADR-0011～ADR-0016、ADR-0020 索引](../../../../docs/03_技术决策/README.md)
- [项目设计规范](../../../../docs/02_开发规范/项目设计规范.md)
