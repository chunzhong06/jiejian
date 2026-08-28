# 修改 Observer

> 状态：CURRENT。适用于 Observer 协议、真实观察适配器、观察调度、游标与预算、Evidence 发布，以及结果页来源解释。

## Observer 解决什么问题

目标接口返回的 HTTP 状态只能说明一次请求怎样回应，不能单独证明真实资源是否发生变化。Observer 在执行前后或最终观察窗口内，从受信任的业务来源形成 `ObservationFact`，再由 Runner 把事实写入 Evidence。它负责回答“真实世界里观察到了什么”，不负责决定安全结论。

当前本地协作空间接入六类来源：

```text
Owner API
只读 SQLite
结构化审计日志
后台任务状态
Azure Queue
Azure Blob
```

这些来源都必须实际执行、投影并发布。它们在判定中的角色由冻结的 `EffectBinding` 和 `ObserverRequirementBinding` 决定，不能按 Observer 类型、页面顺序或实现便利硬编码。

## 快速找到修改位置

| 我想修改什么 | 主要位置 | 通常需要一起核对 |
| --- | --- | --- |
| Observer 类型、Locator、预算、阶段与完整性 | `product/protocols/observer/config.py` | `invocation.py`、`result.py`、Schema registry |
| canonical JSON、解析和摘要 | `product/protocols/observer/codec.py` | `product/protocols/runner/evidence.py`、协议测试 |
| 实际运行集合、阶段调度、结果校验 | `product/backend/infra/observers/coordinator.py` | `registry.py`、Runner case orchestration |
| Owner API、SQLite、审计日志 | `product/backend/infra/observers/owner_api.py`、`product/backend/infra/observers/sqlite.py`、`product/backend/infra/observers/audit_log.py` | Locator、秘密引用、游标和直接适配器测试 |
| 后台任务、Queue、Blob | `product/backend/infra/observers/async_task.py`、`azure_queue.py`、`azure_blob.py` | EVENTUAL 预算、终态闭合、相关性与模拟服务测试 |
| 本地应用的六面观察接线 | `product/backend/workflows/security_setup/local_observer_wiring.py` | `profile_builder.py`、生成 Profile、Sample 配置 |
| Runner 调用和 Evidence 组装 | `product/backend/infra/runtime/runner/case_orchestrator.py`、`result_builder.py` | `executor.py`、`product/protocols/runner/evidence.py` |
| 人类结果中的来源角色和状态 | `product/backend/workflows/results/presentation.py` | Effect binding、已发布 Evidence、前端结果组件 |

精确类名和导出清单由对应自动代码参考生成。本文维护修改路线和不能从符号表得出的语义边界。

## 先判断谁拥有事实

| 问题 | 权威来源 | Observer 可以做什么 | Observer 不能做什么 |
| --- | --- | --- | --- |
| 哪些来源要运行 | 冻结 Profile 中的 effect/observer bindings | 按绑定组成实际运行集合 | 根据当前响应或适配器可用性临时删减来源 |
| 来源是关键还是佐证 | `required_channels` 与 `corroborating_channels` | 保留角色并随结果发布 | 按 Observer 类型硬编码角色 |
| 来源看到了什么 | Adapter 形成的 Outcome 与 `ObservationFact` | 记录相关、受预算约束的事实 | 把 HTTP 403、任务名称或模型文本当成资源事实 |
| 事实是否足以闭合 | Observation completeness、causality、phase 和 closure policy | 明确 `CONFIRMED`、`ABSENT` 或不完整 | 在观察不足时补推断或给 PASS |
| 最终 Verdict | Verification | 提供既有事实 | 决定 PASS、BLOCK、INCONCLUSIVE |
| 页面来源状态 | ResultPresentation | 提供 Evidence ref 和冻结角色 | 输出面向页面的另一套安全结论 |

秘密始终只以受控引用进入最小运行时。密码、Cookie、Token、连接凭据、对象正文和未经净化的目标响应不得进入 Observer 公共协议、Evidence、reason code、日志或异常正文。

## 理解实际运行集合与判定集合

当前多来源行为分成两层：

```text
实际运行集合 = required + corroborating
判定阻塞集合 = required
```

`corroborating` 不是“可不运行”。它必须执行、投影并发布 Evidence，只是不阻塞 baseline、target 或 Verdict；它的 baseline 也不进入 baseline fingerprint 与 twin gate。结果页把 required 映射为 `KEY`，把 corroborating 映射为 `SUPPORTING`，但这只是解释角色，不改变 Verification。

修改调度时必须同时证明：

- 每个绑定来源只运行一次，且结果仍能追溯到原 observer requirement；
- required 与 corroborating 的角色没有在 CaseResult、Evidence 或 presentation 中丢失；
- corroborating 不完整时仍被发布，但不会单独把本来可闭合的结论改为 INCONCLUSIVE；
- required 不完整时不能被 supporting 的数量、文本或“看起来一致”所替代；
- 未进入冻结绑定的来源不能被临时加入当前 Verdict。

## 新增或修改 Observer 协议

正常步骤：

1. 先确认需求是独立持久化/跨进程协议变化，还是现有模型内部实现变化；只有前者才考虑 Schema。
2. 在 `config.py` 明确 Locator、预算、允许阶段、受控身份引用和目标范围；不要把秘密值放进模型。
3. 在 `invocation.py` 与 `result.py` 保持输入输出的封闭字段、稳定枚举、界限和 one-to-one binding。
4. 在 `codec.py` 使用确定性 canonical 编码，并拒绝重复键、非有限数和已知秘密材料。
5. 若公共根文档变化，同步 schema registry 和生成物；嵌套 DTO 不重复增加 `schema_version`。
6. 更新协议往返、负向解析、canonical/hash 和秘密拒绝测试。

内部 reason code 也会进入受控投影，必须使用稳定公开 token；不要用前导下划线表示“内部”。异常正文只描述安全、有限的信息，诊断细节留在受控日志边界。

## 新增或修改真实适配器

适配器只负责一次受限观察。通用路线是：

```text
校验 Invocation 与 Locator
→ 解析受控 secret reference
→ 在预算和目标范围内读取
→ 校验 Case/资源相关性
→ 形成 Outcome、Fact 和下一游标
→ 净化后返回
```

必须保持以下边界：

- Owner API 只用只读观察身份；不能复用被测主体身份冒充独立事实。
- SQLite 只打开配置允许的文件和查询模板；不接受任意 SQL 或仓库外路径。
- 审计日志按字节游标增量读取。文件没有新增字节时复用当前有效游标，不能制造“末端到末端”的零长度非法锚点。
- AsyncTask 只接受同一 Case 的任务，并在有限轮询预算内识别可靠终态。
- Queue 只 peek，不消费、不删除；消息必须与当前 Case 相关。
- Blob 只做受限 metadata/range 读取，不把整个对象正文放进 Evidence。
- 任何来源超时、不可达、响应超限或相关性不足都应显式变成不完整 Outcome，不能伪装成 `ABSENT`。

Windows 上日志和 Sample 状态可能由原子替换写入。读路径必须与写路径共享适当的进程内锁或打开策略，避免把短暂文件替换竞态误报成资源不可用；修复竞态不能通过无限重试扩大预算。

## 修改阶段、游标和 EVENTUAL 闭合

`BEFORE` 建立执行前事实或游标，`AFTER` 观察同步结果，`EVENTUAL` 在有限窗口内确认异步终态。阶段不是通用重试标签：

- AsyncTask 与 Queue 可以使用冻结的 EVENTUAL 专用闭合语义；
- Owner API、SQLite、审计日志和 Blob 不因“多等一会也许会出现”自动获得 EVENTUAL 语义；
- 扩大阶段集合属于公共执行语义变化，必须先由主线程裁决；
- 达到预算上限后输出不完整事实，不得继续后台轮询或把超时当作未发生。

游标必须能证明“从哪个可信位置继续”。游标 round-trip 后应保持同一资源、同一锚点和合法范围；文件无新增内容、Queue 无相关消息等正常空观察不能生成不可解析的下一游标。

## 修改调度、Evidence 与展示映射

Coordinator 负责按 Case 阶段调用 Adapter，并校验返回的 observer id、requirement id、phase 和目标绑定。Runner 负责把全部实际运行来源放入 CaseResult 与 Evidence。Evidence 的 semantic hash 必须基于模型规范化后的稳定顺序；如果模型会排序 `observation_facts` 或 `reason_codes`，哈希输入也必须先做同样规范化，否则跨进程发布会出现摘要漂移。

结果页来源状态只按已发布事实映射：

```text
FOUND       = 完整、可靠、相关的 CONFIRMED
NOT_FOUND   = 完整闭合的 ABSENT
UNAVAILABLE = 观察不完整、无关、失败或无法证明闭合
```

不能要求六个来源在同一状态。真实 BLOCK 可以同时包含关键 `FOUND`、支持来源 `FOUND` 或 `UNAVAILABLE`；PASS 要求关键来源充分闭合为 `NOT_FOUND`；关键 Blob 不可用时必须保留 INCONCLUSIVE。页面顺序和中文标签可以稳定，但它们不参与 Verdict。

## 测试、Golden 与真实运行验证

所有命令从仓库根运行。Python 检查同时设置 `PYTHONDONTWRITEBYTECODE=1` 并使用 `python -B`；正式 pytest 只经 `dev.ps1 test`。

适配器或调度的最小直接验证示例：

```powershell
.\scripts\dev.ps1 test tests/backend/infra/observers
.\scripts\dev.ps1 test tests/backend/workflows/security_setup/test_local_observer_wiring.py
.\scripts\dev.ps1 test tests/protocols/runner/test_runner_evidence.py
```

公共模型变化再补：

```powershell
.\scripts\dev.ps1 test tests/protocols/observer
.\scripts\dev.ps1 test tests/protocols/test_schema_registry.py
.\scripts\dev.ps1 schema
```

代表性 Golden 必须走真实 Sample 和实际六面 Observer，证明来源 one-to-one 绑定、Evidence 已发布、角色正确、关键状态与 Verdict 一致。测试失败诊断只能使用公开且有界的 run/job/result/evidence 摘要；不要在正式 E2E 中保留读取 Runner 内部 progress 文件、attempt 私有目录或进程内部对象的诊断债务。

涉及真实 GUI 流程、Windows 文件替换或本地服务组合时，L4 后单独做 L5。L5 检查页面来源、真实业务状态、清理与进程回收，不用页面颜色替代后端 Evidence 核验。

## 常见失败怎样定位

- HTTP 403 但 Verdict 是 BLOCK：这可能是正确结果；检查关键 Observer 是否确认真实副作用，不要把 403 当作安全证明。
- supporting 来源 `UNAVAILABLE` 导致 INCONCLUSIVE：检查调度或 Verification 是否错误把 corroborating 加进阻塞集合。
- 六个来源都运行了但页面少一项：按 ObserverBinding → CaseResult → Evidence → ResultPresentation 逐段检查 one-to-one 绑定。
- 审计文件没有新增内容时报游标无效：确认复用了当前游标，没有创建零长度 anchor。
- BEFORE 可读而 AFTER 偶发文件不存在：检查 Windows 原子替换的读写锁，而不是增加无界重试。
- Evidence 内容相同但 publication hash 不同：检查 facts/reason codes 是否在计算 hash 前按模型规则规范化。
- AsyncTask/Queue 闭合正常但其他来源被反复轮询：检查 EVENTUAL 语义是否被错误扩大。
- 页面把某类 Observer 永远标成 KEY：停止前端修补，回查冻结 EffectBinding 的 required/corroborating 角色。

## 最终检查清单

Observer 变化至少确认：

```text
实际运行集合仍是 required + corroborating
只有 required 阻塞 Verdict、baseline 与 twin gate
每个来源只运行一次并保留冻结角色和 Evidence ref
EVENTUAL 专用闭合没有扩大到 AsyncTask/Queue 之外
游标、预算、相关性、完整性和因果性仍严格
秘密、目标正文和安全结论没有进入公共观察协议
Evidence canonical/hash 与模型规范化顺序一致
直接适配器、调度、协议和必要 Golden 通过
正式测试没有保留私有 progress/attempt 诊断依赖
运行数据、缓存和生成物只进入 var/
```

进一步约束见[执行与观察](../../01_系统地图/执行与观察.md)、[Observer 观察协议](../../03_参考手册/协议/Observer观察协议.md)、[权限验证与结果](../../01_系统地图/权限验证与结果.md)和[验证与测试](../../04_工程约束/验证与测试.md)。
