# Runtime、Worker 与 Runner 模块

> 状态：CURRENT。`product/backend/infra/runtime` 拥有持久 Job、attempt/lease/fencing、角色化子进程、Worker/Runner 生命周期、staging、恢复和运行诊断。

1.1.0 当前控制面没有装配完整执行 Worker/Runner；System、`/ready` 与 MCP 明确报告 Worker `unavailable`。本模块说明保留实现及未来重新接入时仍必须满足的安全边界，不表示当前 GUI 可以运行检查。

## 职责

Runtime 把 ApplicationCore 创建的冻结执行请求交给独立 Worker，再由 Worker 启动独立 Runner/Recording Process。它确保只有当前 attempt 和 fencing token 能完成 Job、过期执行不能覆盖发布事实、主错误与 cleanup 分离、进程和锁可以证明回收。

## 非职责

不在进程管理、Job 状态或 progress 旁路中重算 Evidence、Verdict、Finding、Gate 或 Report，不让 API 进程成为 Target Runtime，也不把测试 fake/controlled runner 注入正式 Worker factory。

## 稳定入口与模块边界

| 位置 | 负责什么 | 不负责什么 |
| --- | --- | --- |
| `product/backend/infra/runtime/jobs/` | Job、request、claim、attempt、lease/fencing、取消与 reconciliation | 目标请求和安全结论 |
| `product/backend/composition/worker.py` | 独立 WorkerContainer 与 HandlerFactory 装配 | ApplicationCore 复用、运行时进程监督 |
| `product/backend/infra/runtime/worker/` | LocalWorkerSupervisor、Worker process、dispatcher 与 handler 执行 | 组合根、测试专用 runner |
| `product/backend/infra/runtime/runner/` | 独立 Runner、Case 编排、Observer 调度、staging、progress 与 result | API/GUI 展示和 publication 接受 |
| `product/backend/infra/runtime/process/` | Python 身份、角色环境、子进程启动与进程树 | 业务请求内容、秘密长期保存 |
| `product/backend/infra/runtime/paths.py` | 当前 VarDir 的 data/runtime/cache/logs/temp/test 边界 | 开发工具缓存和源码路径 |
| `product/backend/infra/runtime/serve_lock.py` | 同一 VarDir 单控制者 | daemon/IPC 与业务锁 |
| `product/backend/infra/execution/` | TargetRuntimeRegistry 与当前 Web Runtime | Worker 调度、通用 Verification |

精确函数与进程入口见[Runtime 自动代码参考](../../03_参考手册/代码/backend-infra-runtime.md)和[Runner 执行协议](../../03_参考手册/协议/Runner执行协议.md)。

## 我想修改什么

| 任务 | 主要位置 | 先读与直接验证 |
| --- | --- | --- |
| 修改 Job 模型、request 或 claim | `runtime/jobs/models.py`、`requests.py`、`queue.py` | `test_job_models.py`、`test_request_store.py`、`test_queue_attempts.py` |
| 修改 attempt、lease 或 fencing | `runtime/jobs/attempts.py`、`reconciliation.py`、`recovery.py` | concurrency/publication recovery 测试 |
| 修改 Worker 进程、dispatcher 或 handler | `runtime/worker/`、`runtime/jobs/dispatch.py`、`handlers.py` | worker supervisor、dispatch、正式 factory 架构测试 |
| 修改 Runner Case、观察或清理 | `runtime/runner/case_orchestrator.py`、`executor.py`、`result_builder.py` | runner execution/orchestration/attempt completion 测试 |
| 修改 staging 与 publication 交接 | `runtime/runner/staging.py`、`infra/artifacts/run_publication.py` | staging、publication、过期 attempt 回归 |
| 修改 progress 展示旁路 | `runtime/runner/progress.py` 与只读 API/前端 | progress reader/writer + 页面测试；不改完成状态 |
| 修改 Python 身份、环境或进程树 | `runtime/process/identity.py`、`environment.py`、`control.py`、`tree.py` | identity/environment/process control 直接测试；必要时真实子进程 probe |
| 修改 Web Runtime | `product/backend/infra/execution/web/` | [修改 Web 执行](../任务/修改Web执行.md)；execution 测试 |
| 修改单控制者或安全退出 | `runtime/serve_lock.py`、`service_lifetime.py`、CLI bootstrap、system shutdown | control plane、CLI、process 与锁测试 |

## 进程与状态关系

```text
ApplicationCore 冻结请求并创建 Job
  → LocalWorkerSupervisor / 独立 Worker claim
  → attempt + lease owner + fencing token
  → 独立 Runner / Recording Process
  → staging result
  → Worker 校验当前 attempt
  → 原子 publication / Job 终态
```

Run/Job 生命周期说明执行是否完成；RunnerResult 保存 attempt 结果与主错误；Evidence/Verification 保存安全事实。Runner progress 是可删除、非权威、受限 JSONL，只给 GUI 显示阶段，不参与完成、发布或恢复。

长时多阶段任务必须输出稳定边界并 flush；能提供真实进度时有界流式输出，没有时说明当前阶段和静默上限。失败证据保留所属 phase，cleanup 结果单独记录，避免“进程仍运行但用户看不到状态”的黑箱。

| 事实 | 权威所有者 | 能否由其他事实推断 |
| --- | --- | --- |
| Job 状态、attempt、lease、fencing | `runtime/jobs` + Storage | 不能由 PID 或 progress 推断 |
| 子进程存活与退出 | `runtime/process`、Supervisor 持有的进程句柄 | 不能由 Job 文本状态推断 |
| Runner 业务结果 | 当前 attempt 的 RunnerResult/staging | 不能由 exit code 单独推断 PASS/BLOCK |
| 已发布 Evidence/Report | 通过 manifest/hash 的 publication | 不能读取 staging 或孤儿文件替代 |
| GUI 进度 | 有界 `progress.jsonl` 旁路 | 可丢失，不参与恢复和最终化 |

## 必须保持的边界

- Worker 使用独立 `WorkerContainer`，不能继承或实例化 ApplicationCore；API/CLI 不导入 Runner/Web adapter。
- 当前正式 TargetRuntime 只有 Web；通用 orchestrator 输入输出不含 HTTP 类型。
- 只有当前 attempt/fencing 可以完成 Job；重复、过期租约和孤儿 staging 不覆盖 publication。
- Runner/Recording/Observer/Artifact Scan 使用同一已确认 Python 身份和角色白名单环境；秘密只在最小角色进程注入。
- 主错误先保存，cleanup issue 另列；超时、取消、crash 和清理失败不能冒充 PASS。
- 进程树强杀只是正式 cancel/shutdown 不可用后的最后应急，只回收当前任务拥有的 PID，不枚举杀所有 Python/Chromium。
- ServeLock、Worker lifetime lock、控制端口和子进程退出都要有可验证收口；不得靠删锁或改数据库掩盖活进程。
- `controlled_runner` 只用于 L1～L4 局部组合，正式 WorkerHandlerFactory 和自动 L5 不注入。

## 直接验证

```powershell
.\scripts\dev.ps1 test tests/backend/infra/runtime/jobs
.\scripts\dev.ps1 test tests/backend/infra/runtime/worker
.\scripts\dev.ps1 test tests/backend/infra/runtime/runner
.\scripts\dev.ps1 test tests/backend/infra/runtime/process
```

按一个职责目录和一个直接消费者选择最小范围。真实 Windows 子进程、Credential Manager、headed Chromium 和完整进程树只在相应局部 probe 或阶段最终自动 L5 验证；普通修改不反复运行 sample-test。

## 首错定位

| 现象 | 先检查 | 不要先做 |
| --- | --- | --- |
| Job 长期 QUEUED | Supervisor lifetime、claim 条件、request 可读性和 Worker 日志 | 在 API 进程直接执行 Job |
| Job RUNNING 但无对应进程 | attempt/lease、Worker watchdog、reconciliation 与 PID 所有权 | 删除锁或直接改 Job 终态 |
| 旧 attempt 覆盖新结果 | fencing 校验、staging 命名、publication 接受点 | 只靠文件时间判断新旧 |
| Runner 已退出但结果不明确 | exit code、RunnerResult、primary failure 与 cleanup issue | 把非零退出统一映射成安全结论 |
| 运行中没有可见进度 | phase 写入/flush、progress reader、静默上限 | 增加无权威依据的百分比 |
| shutdown 后仍占端口或锁 | 正式 shutdown、Supervisor/Runner/Recording 退出、ServeLock 句柄 | 枚举杀所有 Python/Chromium |

## 相关真源

- [修改 Worker 与 Runner](../任务/修改Worker与Runner.md)
- [执行与观察](../../01_系统地图/执行与观察.md)
- [Runner 执行协议](../../03_参考手册/协议/Runner执行协议.md)
- [工作区与权限](../../04_工程约束/工作区与权限.md)
- [验证与测试](../../04_工程约束/验证与测试.md)
