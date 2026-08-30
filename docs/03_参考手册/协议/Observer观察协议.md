# Observer 观察协议

> 状态：CURRENT。本文先解释为什么需要真实观察以及六类来源怎样形成证据，再给出查询入口；完整字段以 `product/protocols/observer/` 与 Observer Schema 为准。

## 先用 Bob 导出故事理解 Observer

协作空间的项目资料只应由负责人 Alice 导出。界鉴让 Bob 执行“生成完整项目资料包”时，页面或接口可能返回 403，但 403 只能证明表面请求被拒绝，不能证明后台没有排队、任务没有运行、数据库没有改变、Blob 没有生成。

因此界鉴在同一 Case、同一逻辑资源和有界观察窗口内读取六个独立来源：

```text
Owner API        当前项目是否存在有效导出
Azure Blob       当前有效 Blob namespace 是否存在资料包对象
SQLite           Sample 当前项目/导出记录怎样投影
Audit Log        请求、任务与撤销留下了哪些结构化事件
Async Task       对应导出任务是否进入终态
Azure Queue      对应消息生命周期是否真实发生
```

如果漏洞态虽然返回 403，Owner API 与 Blob 都确认资料包存在，界鉴仍据真实副作用形成 BLOCK。修复态中 403 且两个关键来源都在闭合窗口内可靠确认不存在，结合有效 ALLOW control、基线和其他必需事实，才可能 PASS。关键读取失败或“不存在”尚未闭合时只能 INCONCLUSIVE。

Observer 的价值不是“多看几个日志”，而是让安全结论依赖真实系统事实，而不是 HTTP 表面或模型猜测。

## 六个来源分别证明什么

| 来源 | 当前职责 | 能证明 | 不能单独证明 |
| --- | --- | --- | --- |
| Owner API | 读取业务所有者对当前有效资源的权威投影 | 项目当前是否 READY/ABSENT | 物理 Blob、异步过程与历史是否完整 |
| Azure Blob Object | 读取 Sample Azure compatibility 层的当前有效对象 | 当前交付物对象 FOUND/NOT_FOUND | 项目权限规则、任务历史或 HTTP 是否正确 |
| SQLite | 读取 Sample 当前状态与关联记录 | 数据库投影是否与业务状态一致 | 外部对象或 API 最终可见性 |
| Structured Audit | 读取有界、结构化、可关联事件 | 请求和状态转换曾经发生 | 当前资源仍然有效 |
| Async Task | 读取对应 marker/task 的终态 | 异步副作用是否完成、失败或撤销 | Blob 当前是否可见 |
| Azure Queue | 只读 Peek 有界关联消息 | 调度链是否曾发生且关联唯一 | 当前最终资源状态 |

六个生产 adapter 的当前入口依次是 `product/backend/infra/observers/owner_api.py`、`azure_blob.py`、`sqlite.py`、`audit_log.py`、`async_task.py`、`azure_queue.py`。先按来源进入唯一文件，不在 Runner 中复制 adapter。

Owner API 与 Blob 是当前 OBJECT_CREATION 的关键来源，因为一个代表业务所有者的当前有效状态，另一个代表交付物对象的当前有效 namespace。SQLite、Audit、Task 与 Queue 解释过程、关联和限制，属于佐证；它们不能在两个关键来源都确认 ABSENT 时仅凭历史事件把已撤销对象解释为仍存在，也不能在关键来源失败时替代不存在证明。

业务撤销尤其说明了这种区别：撤销后 Audit、Queue、Task 与 export history 保留 `REVOKED` 历史，Owner API 和 Blob 当前投影为 ABSENT/NOT_FOUND。恢复当前副作用不等于删除历史证据。

## required、corroborating 与 KEY、SUPPORTING

冻结 EffectBinding 使用 required channel 与 corroborating channel 描述执行和充分性。两类来源都进入实际调度、投影、Evidence 和 CaseResult，并进行角色校验，不存在“supporting 只写配置但不运行”的路径。

当前协作空间中 Owner API 与 Azure Blob 属于 required，SQLite、Audit、Async Task 与 Queue 属于 corroborating。corroborating 会发布完整证据，但不进入 baseline fingerprint、twin gate 或 PASS 的必需闭合；它们的失败不能抹去关键来源已经确认的漏洞，也不能被人为删除来制造 INCONCLUSIVE。

`ResultPresentation` 再把冻结角色翻译为用户可读的 KEY/SUPPORTING，并把来源状态翻译为 FOUND/NOT_FOUND/UNAVAILABLE。KEY/SUPPORTING 是展示投影，不是第二套 Verification 规则。

## 为什么 NOT_FOUND 必须等待闭合

“暂时没有看到”不是“确定不存在”。异步导出可能仍在 Queue、Task 运行或最终一致窗口中；Blob list 也可能只读到部分分页。只有满足 EffectBinding 的闭合策略、观察预算与关联条件后，NOT_FOUND 才能参与 ABSENT 证明。

闭合策略包括 IMMEDIATE、TERMINAL_STATE、BOUNDED_QUIESCENCE 与 EXCLUSIVE_CHANNEL_WINDOW。EVENTUAL-only 运行只适用于 AsyncTask 与 Queue，不扩展为全部 Observer 的通用语义。任务仍运行、终态冲突、观察窗口未闭合、分页/字节预算耗尽、部分尾行或关联不唯一，都只能形成 UNKNOWN/INCONCLUSIVE。

## 关联、完整性与只读边界

每次调用由 `ObserverSpec`、`ObserverInvocation` 和 `ObservationEnvelope` 绑定 phase、case、task、sequence、逻辑资源、window 与 correlation。只接受显式关联，不使用“时间接近”“标题相似”或资源名称猜测补链。缺失、冲突、重复或交错关联必须作为限制保留。

Queue 使用只读 Peek、固定 scope 和有界消息数，不改变 dequeue count；超出预算或无法唯一关联时返回不完整。Blob 使用固定 container/prefix、list/head/get 与有界分页；物理历史文件存在不等于当前业务对象存在，Sample compatibility 层只暴露仍有效的对象。Observer 不扩大凭据权限、不枚举无关资源、不保存 SAS、Cookie、Token 或响应秘密。

原始读取先形成有界 `ObservationEnvelope` 和 provenance；独立 `EffectProjector` 再按 `effect_id + projection_version` 投影 ObservationFact/SecurityEffectFact。Coordinator 不解释业务效果，Projector 不回读目标、不使用 whole-state hash。Observer 与 Projector 都不写 Verdict、Finding 或 Gate，也不直接修改目标。

## 失败为什么只能 INCONCLUSIVE

关键 Observer 缺失、读取异常、来源不完整、预算超限、correlation 冲突、可靠性不足或窗口未闭合时，系统不知道“副作用不存在”，只知道“当前证据不能证明”。因此它们只能支持 INCONCLUSIVE，不能被默认值、空列表或异常吞掉后解释为安全。

反过来，任一权威、完整、可靠、相关的关键通道确认禁止效果存在，就足以保留 CONFIRMED；Supporting 读取失败不能覆盖这个事实。这是“存在性证据”与“不存在证明”的非对称边界。

## 生命周期与查询入口

```text
Execution Case
  → ObserverSpec / EffectBinding
  → BASELINE / BEFORE / AFTER / EVENTUAL invocation
  → source read within scope and budget
  → ObservationEnvelope / ObserverOutcome
  → EffectProjector(effect_id + projection_version)
  → ObservationFact / SecurityEffectFact
  → Evidence
  → Verification
  → ExecutionTrace（只读路径）/ ResultPresentation（KEY/SUPPORTING 展示）
```

修改或查询时按职责进入：

- 公共模型、codec、canonical：`product/protocols/observer/`
- EffectBinding 的 `required_channels` / `corroborating_channels`：`product/protocols/execution.py`
- Schema：`product/protocols/schemas/observer/`
- SQLite adapter：`product/backend/infra/observers/sqlite.py`；其余五类位于同一 `product/backend/infra/observers/` 边界
- Runner 调度与投影：`product/backend/infra/runtime/runner/`
- 当前协作空间绑定：`product/backend/workflows/security_setup/local_observer_wiring.py`
- Observer outcome：`product/protocols/observer/result.py`；权限三态消费：`product/backend/core/verification/permissions/evaluation.py`
- 结果展示：`product/backend/workflows/results/presentation.py`
- 路径构建：`product/backend/workflows/results/trace.py`；只消费冻结 request snapshot 与已发布 Evidence
- Adapter 直接测试：`tests/backend/infra/observers/`
- outcome/INCONCLUSIVE 直接测试：`tests/protocols/observer/test_observer_result.py`、`tests/backend/core/verification/permissions/test_evaluation.py`
- 协作空间六面 Golden：`tests/fixtures/collaboration_golden.py`

## 版本与 Schema

`ObserverInvocation` 与 `ObservationEnvelope` 是独立根文档，当前 `schema_version` 均为字符串 `"1"`；`ObserverSpec`、`ObserverOutcome` 等嵌套 DTO 不重复根版本。结构化 Audit 的可选 Trace 字段仍属于现有根文档，不另建 Schema 版本。Schema 版本描述机器格式，不表示产品 1.0.7。字段、required、枚举、大小和 canonical 以代码与已签入 Schema 为准，旧开发格式不猜测读取。

## 相关真源

- [执行与观察](../../01_系统地图/执行与观察.md)
- [权限验证与结果](../../01_系统地图/权限验证与结果.md)
- [ADR-0039：关系差分孪生与证据闭合](../../05_设计依据/ADR-0039-关系差分孪生与证据闭合.md)
- [修改 Observer](../../02_开发指南/任务/修改Observer.md)
