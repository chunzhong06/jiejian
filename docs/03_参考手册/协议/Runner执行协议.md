# Runner 执行协议

> 状态：CURRENT。本文说明当前 CHECK 的跨进程输入、结果、发布和展示旁路；Recording 使用自身协议。

## 目的与消费者

控制面冻结实验，Worker 持有租约并监督独立 Runner，Runner 产生受限暂存事实，Worker 校验后发布。进程退出、执行生命周期与安全三态分别表达，Runner 不能自行宣布发布成功。

## 协议边界

- PersistedExecutionRequestV3 使用 schema_version="3"，保留完整动作、ALLOW、DENY、同题对照及来源/策略身份。
- CheckRuntimeBundle 使用格式1，冻结目标、串行预算、身份引用与映射、Flow、proof/辅助来源、恢复和业务标签；request.config_fingerprint 绑定其 canonical bytes，预算另有具名指纹。
- CheckRunnerInput 格式1绑定 run/job/attempt/lease owner/fencing token、request/config hash和两个受控资产引用。入口仅接受固定 input/staging 路径，独立校验所有关联。
- CheckEvidence 格式1保存冻结 Case、执行 outcome、按来源分级的观察和可选 Trace；内容地址排除自身 ID，完整文件字节 hash 由 manifest 单独保存。
- CheckRunnerResult 格式1返回完整 Case 集合、生命周期、Verdict、首错和清理问题；未知字段、错配 Case/hash、非 canonical 字节、秘密或超预算均拒绝。
- CheckPublicationManifest 格式1列出实际发布文件及 hash。数据库 check_publications 保存 Run/Job/attempt/fence 和 request/result/manifest hash，不能用可变结果缓存代替。

## 生命周期与数据流

```text
CheckService → 冻结 request/runtime → Run/Job
→ Worker claim → CheckRunnerSupervisor → 固定 check_runner 模块
→ CheckExecutor → 独立身份验证 / Web / Observer / 恢复
→ staging → 校验全包及唯一规则 → fenced CAS → 文件提升与收据提交
→ CheckResultReader / CheckStoryBuilder
```

TARGET 每 Case 至多一次；完整 ALLOW 控制先行。基础设施故障不自动重放业务动作。Worker 复用 JobAttempts、AttemptProcessControl、source receipt 和系统进程树；失去 lease、旧 fence、取消或不确定清理不能覆盖新状态。已完成文件提升但数据库提交失败时，只允许原 attempt/fence 的合法 manifest 对账，不再执行 TARGET。

## 运行中展示旁路

attempt/progress.json 是严格格式1 CheckRunnerProgress 根，原子替换。字段限于 Run/Job/attempt/fence/request hash、阶段 PREPARING/EXECUTING/FINALIZING、completed_cases/planned_cases 和时间。它不进入 staging、Evidence、结果或恢复真源。

只读状态从当前 Job 推导路径；文件缺失、超限、关联不符或含未知字段时省略进度。写入失败只使展示不可用，不改变 Verdict。这里没有 URL、实际身份或资源值、响应正文、秘密和安全结论。

## 失败与安全语义

scope、重定向、私网、请求与响应预算由 Web Adapter 强制执行。Observer 独立核验来源身份、关联、完整性与闭合，辅助或诊断来源不升级为必需证明。DATA_DISCLOSURE 不发布原始保护字段；Trace 不靠时间和名字补因果边。

取消、超时、进程树和恢复问题保留首错与后续清理信息。发布前检查请求预算与结果上限：最多240条 Case 观察，结果根1 MiB并按每 Case 4 KiB加固定8 KiB预留。请求/config/evidence/result 各自有严格解析与字节上限；协议模型上界不代表任意组合都能提交。

## 版本规则与 Schema 真源

CURRENT Check writer/reader/factory 只使用 v3 request 和 Check 根模型，没有旧 v2 request、Contract/Profile 或旧 RunnerInput fallback。旧协议可服务保留实现，不能重新进入当前执行入口。schema_version 表示独立文档格式，嵌套 DTO 不重复版本。

唯一模型位于 product/protocols/execution_v3.py、check_runtime.py、check_result.py、check_publication.py；Schema 由 product/protocols/schema.py 生成到 schemas/runner/。

## 查询入口

| 要查什么 | 当前真源 |
| --- | --- |
| 冻结提交与读取 | product/backend/workflows/checks/ |
| Worker/Runner 监督与入口 | product/backend/infra/runtime/check_runner/ |
| Web/Observer 编排 | product/backend/infra/execution/check_executor.py |
| 文件校验与 fenced publication | product/backend/infra/artifacts/check_packages.py、check_publication.py |
| 真实跨进程测试 | tests/backend/infra/execution/test_check_executor.py |

## 相关真源

- [执行与观察](../../01_系统地图/执行与观察.md)
- [权限验证与结果](../../01_系统地图/权限验证与结果.md)
- [数据与持久化](../../01_系统地图/数据与持久化.md)
