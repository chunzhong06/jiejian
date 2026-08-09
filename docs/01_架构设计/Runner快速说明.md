# Runner 快速说明

## 负责什么

- 严格解析 RunnerInputV1；
- 在授权范围和预算内执行一个完整 Run；
- 复用 Verification 的计划、HTTP、观察、判定和 Evidence 逻辑；
- 在安全点响应取消并执行必要清理；
- 原子生成 RunnerResultV1 和当前 attempt 的 staging 工件。

## 不负责什么

- 不读取 `project.yaml`、`flow.yaml` 或 `contract.yaml`；
- 不 claim Job、不决定租约或重试；
- 不写 SQLite；
- 不直接写最终 Run 目录；
- 不把进程退出码当作 `PASS`、`BLOCK` 或 `INCONCLUSIVE`。

## 输入

RunnerInputV1 包含 `run_id`、`job_id`、attempt、lease owner、Fencing Token、创建时间、预算和完整项目执行快照。快照只含 `env:NAME` 秘密引用，真实值通过本次最小子进程环境传入。

## 输出

RunnerResultV1 记录结果类型、Run lifecycle、Job state、可选 verdict、reason codes、清理结果、有限错误结构和 staging 工件清单。Runner 退出码 0 只表示结果文件已形成，Worker 仍必须复验 Schema、关联字段与全部哈希。

## 何时启动

Worker 成功 claim PENDING 或 RETRY_WAIT Job、获得当前租约和新 Fencing Token，并从持久请求构造 RunnerInputV1 后启动 Runner。一次 Runner 对应一次完整 Run attempt，不按 TestCase 拆进程。

## 失败如何处理

- 输入/协议错误：退出 64，没有可信结果；
- Runner 内部致命故障：退出 70；
- staging 或结果写入失败：退出 74；
- 超时或启动失败：由 Worker 映射到有限重试或最终失败；
- 取消：Runner 观察取消标记、清理后返回 CANCELLED；
- 旧 Fencing Token 或过期租约结果：Worker 拒绝接收和发布。

完整协议见[Runner 执行协议 V1](../04_协议定义/Runner执行协议V1.md)，进程决策见[ADR-0006](../03_技术决策/ADR-0006-阶段2隔离执行设计.md)。

