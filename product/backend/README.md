# 后端代码导航

> 本页只说明代码从哪里读起。系统边界以 [技术文档入口](../../docs/README.md) 和对应 Architecture 为准。

## 目录职责

| 目录 | 负责什么 |
| --- | --- |
| `core/` | 领域模型、生命周期、权限规则、Verification、Finding、Gate 和稳定错误语义；不依赖 FastAPI、SQLAlchemy、Playwright 或具体 LLM SDK。 |
| `workflows/` | 应用编排，包括 Contract 治理、onboarding、Recording、检查提交和结果读取。 |
| `infra/` | Storage、事务、Job、Worker/Runner、Observer、发布、浏览器和外部服务适配。 |
| `api/` | FastAPI transport、请求解析、错误映射和资源路由；不直接执行目标请求。 |
| `cli/` | CLI 参数、等待/取消和 Human/JSON/CI 展示；复用同一应用工作流。 |
| `migrations/` | Alembic 数据库结构和 migration 真源。 |

组合根是 [`workflows/context.py`](workflows/context.py) 中的 `ApplicationCore`。GUI、CLI、API 和 Worker 通过它装配共享工作流，不在入口层另建领域引擎或存储事务。

## 一次检查经过哪里

```text
API / CLI
  → ApplicationCore
  → workflows/runs（冻结 Contract、Profile 与执行请求）
  → infra/runtime/jobs（持久 Job、租约、fencing、恢复）
  → Worker / 隔离 Runner
  → infra/execution + infra/observers
  → Evidence / Verification
  → workflows/results + infra/artifacts/storage
```

当前目标执行只有 Web + HTTP。API 和 GUI 只能提交、观察和读取，高风险目标流量必须经过 Worker 与隔离 Runner。完整边界见[系统总体架构](../../docs/02_架构设计/系统总体架构.md)和[执行与观察架构](../../docs/02_架构设计/执行与观察架构.md)。

## 修改功能时从哪里开始

- 权限、Verdict、Finding 或 Gate：先看 `core/verification/`，再看 `workflows/results/`。
- Contract 与候选治理：先看 `core/contracts/` 和 `workflows/contracts/`。
- 检查提交、执行快照和运行闭环：先看 `workflows/runs/`，再看 `infra/runtime/` 与 `infra/execution/`。
- Recording：应用状态和审阅在 `workflows/recording/`，浏览器、控制标记和请求存储在 `infra/recording/`。
- 数据库或恢复：先看 `infra/storage/`、`migrations/` 和 `infra/runtime/jobs/`。
- 新增 API 或 CLI 动作：先确认已有 `ApplicationCore` 能力，再修改 transport；入口不得复制编排。

对应测试按相同职责放在 [`tests/backend/`](../../tests/backend/)。测试层级和命令见 [`tests/README.md`](../../tests/README.md)。
