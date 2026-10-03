# 修改 Observer

> 状态：CURRENT。适用于当前 CHECK 的真实来源读取、业务效果投影与发布证据。

## 快速找到修改位置

| 任务 | 唯一入口 | 直接验证 |
| --- | --- | --- |
| 当前 Case/proof 观察调度 | `product/backend/infra/observers/checks/check_runtime.py` | `tests/backend/infra/observers/` |
| 只读 SQLite、Owner API、审计、任务、Queue、Blob | `product/backend/infra/observers/`，其中 SQLite 为 `product/backend/infra/observers/adapters/sqlite.py` | 同目录适配器测试，必要时真实 Sample |
| 已授权描述与来源接线 | `product/backend/workflows/checks/local_observer_wiring.py`、`product/backend/workflows/checks/runtime_bundle.py` | `tests/backend/workflows/` 中当前 observer wiring 和 runtime bundle 测试 |
| Envelope 投影为业务效果 | `product/backend/infra/observers/effect_projector.py` | `tests/backend/infra/observers/` |
| Trace 与权限范围 | `product/backend/infra/observers/checks/check_trace.py` | `tests/backend/infra/execution/test_check_trace.py` |
| 观察协议、严格解析与 canonical | `product/protocols/observer/` | `tests/protocols/observer/` |
| 发布与结果解释 | `product/backend/infra/execution/check_executor.py`、`product/backend/workflows/checks/reading/story.py` | `tests/backend/infra/runtime/jobs/publication/test_check_audit_scope_publication.py` |

## 修改路线

先确认冻结 `CheckRuntimeBundle` 中本 Case 的 proof、scope、来源与角色，再修改 adapter 或 projector。adapter 只形成受预算约束的事实；`EffectProjector.project_check` 解释事实能否证明具体业务效果；只有 `core/verification/checks.py` 裁决三态。来源新增时同步严格模型、接线、准备检查、实际执行、证据发布与只读展示，不能只增加页面标签。

`VERDICT_REQUIRED` 是必需证明，`SUPPORTING` 和 `DIAGNOSIS_REQUIRED` 保持辅助角色。实际身份来自同一会话的独立核验，不从 Trace 或计划身份补值。官方导出的决定性来源是 ZIP；后台任务完成或派发成功不等于 ZIP 已形成。

每个 Case/proof 独立保留游标和观察历史。审计 AFTER/EVENTUAL 回读同一个 BEFORE 锚点；空尾段不是闭合证明。任务可信终态、非空 task_id 和精确关联只能形成私有 execution_completed。只有来源完整、可靠、相关且观察窗口闭合，缺失才可作为不存在证明；观察失败不能解释为安全。辅助来源失败不能抹去独立必需来源已经确认的禁止效果。

结构化 Trace 只接受显式关联与允许字段；范围数组、大小预算和 canonical 规则见[Observer 协议](../../参考/协议/Observer观察协议.md)。不按时间相邻、列表顺序或名称相似补因果边。权限断裂修改见[诊断指南](修改权限断裂诊断.md)。

Queue 只读 Peek，Blob 只读已授权 namespace，SQLite 只读，Owner 只注入精确受控身份。秘密和原始敏感正文不得进入 Envelope、Evidence、日志或异常。Evidence 的事实排序与 canonical/hash 必须遵循同一模型规则，避免跨进程摘要漂移。

## 验证与排障

通用来源由 `check_records.py` 消费受控记录组件的有界读取结果。`source_contracts.py` 核对 Runtime Worker 的内核拥有关系、独立端口与产品组件指纹，不再识别接入应用的名称、文件摘要、角色或业务专用语法。`record_source.py` 只由 Runner 调用；来源读取能力经 DPAPI 保存为运行期引用，业务 Node 进程不能取得证明读取能力。

`transaction_store.py` 在内存 SQLite 事务内同时保存所选资源数据和每一步变化；完整快照写入 OS 独占的持久日志并 fsync 后才返回。原生日志文件无法被仍在运行的目标直接改写，损坏或截断不自动重置。记录日志有 128 MiB 上限，超限停止服务并要求处理；不是无限容量业务数据库。目标退出确认后才释放独占文件。

可信宿主为实际 HTTP 请求建立 scope；Runner 生成随机请求标记，宿主记录请求摘要，业务事务自动关联同一 scope。所有同步写入均已等待时才能完成 scope；响应结束后的写入被拒绝，未等待写入或异常关闭不能证明未发生。只支持接入受控资源集合的同步状态变化和有限 JSON 字段读取。外部数据库、文件、消息队列、后台任务及任意 JSON 日志不因此获得完整证明；Node VM 不作为对抗恶意应用代码的沙箱。

发生后恢复仍保留中间变化。已关联的禁止变化可以确认发生；未发生还必须有完整请求终态、连续版本、相同资源和完整前后记录。身份、字段与语义映射需要预检查和人工采用，组件真实性不能代替用户确认“这个字段就是要保护的业务结果”。

JSON 证明的完整性、关联性与 Trace 定位分别表达。没有 Trace 不补因果边；必要证明确认违例时，辅助来源不足不能抹去 BLOCK。

经 `dev.ps1 test` 选择表中直接测试；公共模型变动再同步 Schema 并验证 reader。403 后 BLOCK 可以是正确结果；先查决定性效果。相同证据摘要漂移查规范排序；NOT_FOUND 异常查闭合、分页和关联；辅助错误盖过 BLOCK 查角色消费。真实进程与来源组合按[验证](../验证.md)选择 L5，不能用预设返回或页面颜色代替证据。

共享 Observer 独立格式及底层消费者仍保留；其 `EffectBinding.required_channels/corroborating_channels` 不是当前 CHECK 页面角色。需要维护该独立格式时才读协议的相应章节，不恢复已退役的 SecuritySetup 装配。
