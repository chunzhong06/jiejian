# 后端模块

> 状态：CURRENT。`product/backend` 以 ApplicationCore 为共享组合根，按纯领域、应用编排、基础设施和控制面适配分层。

## 职责

后端负责项目、应用理解、测试身份、Recording、安全准备、权限契约、执行任务、可信结果和系统维护的正式业务能力。`core/` 保存不依赖 I/O 的领域规则；`workflows/` 组合事务和用例；`infra/` 实现数据库、进程、Observer 与外部适配；`api/`、`cli/` 只把同一应用服务映射为不同控制入口。

## 非职责

后端不把前端页面状态当业务真源，不在 API 进程产生目标流量，不把公共协议字段复制成内部兼容模型，也不让 Storage、日志、AI 或 renderer 决定 Verification。Worker/Runner 是独立进程组合，不是 ApplicationCore 的“精简模式”。

## 稳定入口与分层边界

GUI/CLI/API 的组合根是 `product/backend/composition/application.py` 的 `ApplicationCore`；独立 Worker 的组合根是 `product/backend/composition/worker.py` 的 `WorkerContainer`。新增控制面能力前先确认它属于哪个 workflow；入口层不能绕过组合根直接拼 Repository 或 Adapter，Infra 也不能反向创建具体 Workflow Service。

| 位置 | 负责什么 | 不负责什么 |
| --- | --- | --- |
| `product/backend/core/` | 领域模型、Contract/Coverage、Verification、Finding/Gate 纯规则、稳定错误 | FastAPI、SQLAlchemy、HTTP、Playwright、进程和文件 I/O |
| `product/backend/composition/` | ApplicationCore、WorkerContainer 与系统级依赖注入 | 新业务规则、Repository 查询或目标执行细节 |
| `product/backend/workflows/` | 事务用例、Readiness、Recording、安全编译、结果最终化 | 目标适配细节、跨进程 wire 格式定义 |
| `product/backend/infra/` | Storage、SecretStore、Job、Worker/Runner、Observer、Recording Process、发布与外部 adapter | 用户交互设计、权限意图和 Verdict 规则 |
| `product/backend/api/` | loopback Router、strict DTO、LocalControl、envelope、错误/trace 映射 | 第二套业务编排、目标请求和秘密读取 |
| `product/backend/cli/` | Human/Verbose/Machine 投影、普通任务命令和高级维护入口 | 独立状态、daemon、HTTP 旁路和安全结论重算 |
| `product/backend/migrations/` | 唯一数据库结构历史 | 运行时猜测升级、兼容读写和 fixture 建表 |

精确公开符号与路径见 [Core](../../03_参考手册/代码/backend-core.md)、[Workflows](../../03_参考手册/代码/backend-workflows.md)、[Runtime](../../03_参考手册/代码/backend-infra-runtime.md)、[Storage](../../03_参考手册/代码/backend-infra-storage.md)和[API/CLI](../../03_参考手册/代码/backend-api-cli.md)自动参考。

## 我想修改什么

| 任务 | 主要位置 | 先读与直接验证 |
| --- | --- | --- |
| 修改权限合同、事实或三态 | `core/verification/permissions/`、`facts.py`、`gating.py` | [修改权限判断](../任务/修改权限判断.md)；`test_contract.py`、`test_evaluation.py`、`test_gating.py` |
| 从正式权限编译测试需要 | `core/permission_semantics.py`、`core/assurance.py`、`workflows/preparation/` | [修改业务边界与权限意图](../任务/修改权限意图与Agent授权.md)；`tests/backend/core/test_assurance.py`、`tests/backend/workflows/preparation/` |
| 修改项目、接入或工作区状态 | `workflows/projects/`、`onboarding/`、`application_understanding/`、`workflows/workspace/` | 当前主任务先看 Workspace；旧 `projects/preparation.py` 与 `projects/readiness.py` 仅作迁移资产，不得接回当前产品；直接验证 `tests/backend/workflows/workspace/` |
| 新增或修改应用用例 | 对应 `product/backend/workflows/` 子目录、`product/backend/composition/application.py` | 对应 `tests/backend/workflows/` 子目录；若改变装配再加 `tests/backend/composition/` |
| 修改 API/CLI 控制面 | `product/backend/api/routers/`、`product/backend/cli/commands/` | [修改 API 与控制面](../任务/修改API与控制面.md)；`test_control_plane.py`、`test_control.py` |
| 修改数据库或事务 | `infra/storage/`、`migrations/versions/` | [修改数据库](../任务/修改数据库.md)；storage/migration 直接测试 |
| 修改 Worker/Runner/Job | `infra/runtime/jobs/`、`worker/`、`runner/`、`process/` | [修改 Worker 与 Runner](../任务/修改Worker与Runner.md)；所属 runtime 目录测试 |
| 修改 Observer | `product/backend/infra/observers/`、`product/protocols/observer/` | [修改 Observer](../任务/修改Observer.md)；adapter + observer protocol 测试 |
| 修改 Recording | `workflows/recording/`、`infra/recording/`、Recording 协议 | [修改 Recording](../任务/修改Recording.md)；workflow + process + protocol 测试 |
| 修改模型与 AI 辅助 | `infra/llm/`、`workflows/assistant/` | [修改模型服务](../任务/修改模型服务.md)；fake transport + assistant workflow 测试 |
| 修改结果、历史或报告 | `workflows/results/`、`infra/artifacts/`、`storage/results/` | [修改结果与报告](../任务/修改结果与报告.md)；results + artifact publication 测试 |

## 一次后端变更的落点顺序

1. 先用一句话写清要改变的产品事实及其唯一所有者；如果答案是页面、Router 或数据库字段，通常还没有找到真正所有者。
2. 纯判断放 `core/`；涉及事务和多个端口的用例放 `workflows/`；I/O、进程和供应商细节放 `infra/`。
3. `ApplicationCore` 和 `WorkerContainer` 只装配已经存在的端口和服务。新增能力先完成所属 workflow，再按控制面或执行面的真实消费者接入对应组合根。
4. 机器根文档先由 `product/protocols` 定义；Storage 只持久化当前业务事实，artifact publication 只发布已校验结果。
5. 从 owner 单测开始，再补一个直接消费者；只有越过进程、协议或数据库边界时才追加相应门禁。

## 必须保持的边界

- `core` 不导入 workflows、infra、API、CLI 或具体 Web Runtime；纯规则必须可以在无 I/O 条件下测试。
- API、CLI 和 GUI 复用 ApplicationCore，不各自复制事务、Readiness、ResultPresentation 或 History 逻辑。
- 旧 `ProjectPreparationService` 与 ProjectReadiness 仅为仓库保留的迁移资产，不在当前 ApplicationCore 装配；ActionSafetySetup 已被四类动作技术绑定取代，当前唯一 inspection 是 PreparationService；不得建立准备进度表或把旧权限矩阵接回业务边界。
- WorkerContainer 独立于 ApplicationCore；两个组合根只从 `product.backend.composition` 暴露，不在 Workflow 或 Infra 中建立第二个装配入口。
- API 进程只管理控制面与 Worker 生命周期；目标请求、浏览器和高风险观察进入 Worker/Runner 或独立 Recording Process。
- 当前生产 Target 只有 Web。新增 Target 必须先形成独立架构/协议决策，不能在现有枚举里预留空值。
- 秘密只通过 SecretStore 引用和角色化最小环境注入；普通数据库、协议、日志、异常、Evidence 和报告不保存秘密正文。
- 生命周期、RunnerResult、Verification Verdict、Finding 和 GateResult 分开；任一 renderer 都不能反向改写事实。
- 独立根协议由 `product/protocols` 拥有；后端消费者严格读取当前格式，不建立 fallback 或 alias。
- 修改项目自有 Python 要维护中文职责头；跨层变化先画数据流和唯一事实所有者。

## 直接验证

按“一个职责目录 + 一个直接消费者”选择最小测试，不机械运行整个后端：

```powershell
.\scripts\dev.ps1 test tests/backend/core/verification
.\scripts\dev.ps1 test tests/backend/workflows/results
.\scripts\dev.ps1 test tests/backend/api/test_control_plane.py tests/backend/cli/test_control.py
.\scripts\dev.ps1 test tests/architecture/test_dependencies.py
```

公共协议或数据库变化分别追加 Schema/migration 门禁；跨 Worker/Runner 进程时才升级到对应 process 测试。完整 L4 和自动 L5 只按[验证与测试](../../04_工程约束/验证与测试.md)在最终验收执行。最终对变更 Python 做 AST 与职责头检查，并运行 `git diff --check`。

## 首错定位

| 现象 | 先确认的事实所有者 | 常见错误方向 |
| --- | --- | --- |
| API 与 CLI 结果不一致 | workflow 返回值、控制面/Machine 投影 | 分别在 Router 和 CLI 重写业务逻辑 |
| Job 已终态但 Run/Recording 未收口 | runtime reconciliation 与正式状态机 | 直接 UPDATE 数据库 |
| Evidence 存在但 Verdict 异常 | Verification 输入、Observer 角色和覆盖事实 | 让 renderer、HTTP 状态或 LLM 决定结论 |
| 刷新后 Readiness 回退 | workflow 查询与 Storage 事务提交 | 用前端缓存补事实 |
| 子进程行为与 API 进程不同 | 冻结请求、角色环境、source receipt 和独立组合根 | 让 Worker 继承 ApplicationCore |

## 相关真源

- [系统全景](../../01_系统地图/系统全景.md)
- [产品入口与控制面](../../01_系统地图/产品入口与控制面.md)
- [权限验证与结果](../../01_系统地图/权限验证与结果.md)
- [执行与观察](../../01_系统地图/执行与观察.md)
- [工程设计](../../04_工程约束/工程设计.md)
