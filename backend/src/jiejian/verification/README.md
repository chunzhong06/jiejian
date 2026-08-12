# Verification

## 定位

`verification` 是关系变异、受控 HTTP 执行、多面观察、Evidence 和 Verdict 的纯能力核心。它在 Verification Runner 内运行，不拥有 Job 生命周期或工件发布事务。

## 负责 / 不负责

- 负责 Project/Flow/Contract 输入校验、关系变异计划、TargetScope、预算、HTTP 观察、owner observer 对照、Evidence 和聚合 Verdict。
- 负责把 Runner 内的验证结果写入调用方指定 staging 目录。
- 不 claim Job、不续租、不发布最终目录，也不依据 LLM 文本决定结论。

## 子模块与 public API

- `models.py`：TargetScope、Identity、Flow、SecurityContract、Mutation、Observation、Evidence、RunResult。
- `inputs.py`：受限 YAML 与 ProjectBundle 加载。
- `planning.py`：确定性关系变异计划。
- `safety.py` / `http.py`：目标授权、请求预算、重定向和响应上限。
- `evaluation.py`：单用例 Evidence 与 Run Verdict。
- `execution.py`：`VerificationSnapshot` 和 `SnapshotRunExecutor`。
- `artifacts.py`：Runner staging 内的结果工件。

## 调用与数据流

```text
runner.execution
→ VerificationSnapshot
→ build_mutation_plan
→ TargetGuard + HttpExecutor
→ evaluate_case / build_evidence
→ aggregate_verdict
→ staging artifacts
```

## 关键不变量和失败语义

- HTTP 2xx、401、403、404 都只是观察，不直接等于安全结论；拒绝响应后仍可能发生副作用。
- `COMPLETED` 是生命周期，`PASS/BLOCK/INCONCLUSIVE` 是漏洞结论，两者分开保存。
- 必需观察器缺失或证据不足才是 `INCONCLUSIVE`；协议、启动、预算和数据库错误不是 `INCONCLUSIVE`。
- 每个 mutation case 在执行前预留清理预算；清理失败会阻止继续产生目标副作用。
- secret 只从运行环境解析，不进入持久快照、协议、日志或 Evidence。

## 修改与测试入口

- 纯验证：[`tests/verification`](../../../../tests/verification/)
- 隔离 Runner：[`tests/execution/runner`](../../../../tests/execution/runner/)
- 产品门禁：[`tests/e2e/test_cli_security_gate.py`](../../../../tests/e2e/test_cli_security_gate.py)
- 黄金样例：[`samples/README.md`](../../../../samples/README.md)

## 相关规范、协议与 ADR

- [Runner 执行协议 V1](../../../../docs/04_协议定义/Runner执行协议V1.md)
- [项目设计规范](../../../../docs/02_开发规范/项目设计规范.md)
- [ADR-0002](../../../../docs/03_技术决策/ADR-0002-阶段2执行协议.md)、[ADR-0006](../../../../docs/03_技术决策/ADR-0006-阶段2隔离执行设计.md)
