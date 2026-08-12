# Results

## 定位

`results` 是已发布 Run、工件和 Evidence 的只读完整性边界。它提供当前阶段已有的结果视图，不提前引入阶段 6 Reporting 或 GatePolicy。

## 负责 / 不负责

- 负责把数据库 Run/Evidence 索引与已发布 manifest、receipt 和工件重新匹配。
- 为 API、CLI 和 GUI 提供 overview、report、findings 和 evidence 视图。
- 不重新执行 Planner/Verification，不改变 Verdict，也不生成新的多格式报告。

## 子模块与 public API

- `published.py`：`PublishedResultReader` 和不可变 `PublishedRunView` 是仓库内跨能力入口。
- `__init__.py` 仅为包标记，不提供旧聚合导出。

## 调用与数据流

```text
CLI report/ci、API results/runs、GUI
→ PublishedResultReader
→ Storage Run/Evidence records + publication manifest
→ 完整性校验后的只读视图
```

## 关键不变量和失败语义

- 只读取数据库已完成且已发布的当前 Run；staging 或孤立目录不是结果真源。
- manifest、receipt、文件清单、哈希和 Evidence 索引必须相互一致。
- 完整性错误是工件或基础设施失败，不能重写为 `INCONCLUSIVE`。
- Result 读取不修改历史 Run 快照或已发布工件。

## 修改与测试入口

- API/结果读取：[`tests/api/test_control_plane.py`](../../../../tests/api/test_control_plane.py)
- 发布与篡改拒绝：[`tests/execution/worker/test_publication_recovery.py`](../../../../tests/execution/worker/test_publication_recovery.py)
- CLI：[`tests/e2e/test_cli_security_gate.py`](../../../../tests/e2e/test_cli_security_gate.py)

## 相关规范、协议与 ADR

- [数据流](../../../../docs/01_架构设计/数据流.md)
- [ADR-0007](../../../../docs/03_技术决策/ADR-0007-阶段2工件发布与恢复.md)、[ADR-0010](../../../../docs/03_技术决策/ADR-0010-阶段4控制面与WebGUI.md)
