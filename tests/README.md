# 测试导航

> 测试目录按生产代码责任组织；测试类型通过 pytest marker 表达，不再建立第二套产品架构。系统边界仍以 [docs/README.md](../docs/README.md) 路由的 Architecture 为准。

## 目录结构

| 路径 | 放什么测试 |
| --- | --- |
| `backend/core/` | 领域模型、生命周期、Contract、权限、Verification、Finding 和 Gate 的纯逻辑。 |
| `backend/workflows/` | Contract、onboarding、Recording、运行提交和结果投影等应用编排。 |
| `backend/infra/` | Storage/migration、Job/Worker/Runner、执行 adapter、Observer、LLM、工件和浏览器边界。 |
| `backend/api/` | FastAPI transport、OpenAPI、SSE、错误映射和控制面资源。 |
| `backend/cli/` | CLI 参数、doctor、展示模式和自动化语义。 |
| `protocols/` | 公共模型、Schema 漂移、严格解析、canonical 和 hash。 |
| `architecture/` | 目录形态、依赖方向、唯一入口和禁止边界。 |
| `e2e/` | 从真实产品入口穿过多个能力域的完整闭环。 |
| `scripts/` | Windows 启动、准备、编码和恢复行为。 |
| `fixtures/` | 确实跨多个测试域复用的构造器或受控测试目标。 |

跨边界测试按“被验证行为的主要所有者”放置。例如报告的 API/CLI 投影仍由 `backend/workflows/results/` 负责；HTTP scope 与预算由 `backend/infra/execution/` 负责。真正的 E2E 必须从产品入口验证完整事实链，不能只因为测试较慢就放进 `e2e/`。

## 必要测试与全量测试

目录回答“由谁负责”，marker 定义执行层级。

- 必要测试：`essential`，覆盖架构边界、核心权限语义、公共协议、数据库迁移、Job 恢复、启动入口、控制面和一个授权黄金闭环。它是跨模块改动合入前的最低门禁，不替代改动相关的定向测试；前端改动还要运行直接相关的共置组件测试。
- 全量测试：默认 `tests/` 下全部测试，并包含前端 Vitest 集合；它覆盖所有 integration、process、browser、slow 和 E2E 保护。发布前、跨模块合并或高风险共享边界变化时运行。

PowerShell 示例：

```powershell
$env:PYTHONDONTWRITEBYTECODE = '1'
python -B -m pytest -p no:cacheprovider --basetemp var/pytest-essential-local -m essential
python -B -m pytest -p no:cacheprovider --basetemp var/pytest-full-local
```

前端组件测试与源码共置，不受 pytest marker 管理。仓库级全量验证还要运行：

```powershell
pnpm --dir product/frontend test
pnpm --dir product/frontend build
```

只收集不执行时加 `--collect-only -q`。E2E 和 architecture 可分别运行：

```powershell
python -B -m pytest -p no:cacheprovider --basetemp var/pytest-e2e-local tests/e2e
python -B -m pytest -p no:cacheprovider --basetemp var/pytest-architecture-local tests/architecture
```

每次使用唯一 `--basetemp`，完成后只清理这次创建的目录。需要 `--lf`、`--ff` 或 `--stepwise` 时才临时启用 pytest cache。

## fixture 规则

- 根 `conftest.py` 只放跨多个测试域使用的环境和本地 Sample 服务 fixture。
- 某一层或某个能力专用的 fixture 放在最近的 `conftest.py`，例如 `backend/infra/runtime/` 和其 `jobs/` 子树。
- 跨能力域复用的稳定构造器放在 `fixtures/`，不要从另一个 `test_*.py` 导入通用 Runner 或 Evidence 构造器。同一能力内只服务一个边界 harness 的辅助对象可以留在该边界测试旁，但不得形成循环依赖或进入根 `conftest.py`。
- 只被一个文件使用的 fixture 留在该文件。没有多个真实消费者时不要上移到根。
- 只有两个测试确实保护同一行为，或旧行为已经不存在，才允许删除、合并或参数化；目录变整齐不是删测试的理由。

## 新测试放在哪里

先定位生产责任，再决定测试层级：纯规则进 `core`，应用编排进 `workflows`，外部资源/进程/持久化进 `infra`，transport 进 `api` 或 `cli`，公共 wire 格式进 `protocols`。已有文件已经覆盖同一边界时扩展它；属于新的独立失败边界或不同生产模块时再新建文件。

新增测试文件必须使用全树唯一 basename，并在移动或重命名后运行全量 `--collect-only`。这条规则用于避免非包测试树出现 import file mismatch；不能用删除缓存掩盖同名文件冲突。
