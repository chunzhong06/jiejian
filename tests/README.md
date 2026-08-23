# 测试导航

> 测试目录按生产代码责任组织；少量 pytest marker 表示稳定测试属性，L1～L5 表示一次具体改动的验证策略。系统边界仍以 [docs/README.md](../docs/README.md) 路由的 Architecture 为准。

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

## 模块 × 验证程度

正式测试模型是：

`测试范围 = 模块范围 × 验证程度`

“模块”回答修改影响了哪里，继续由目录和生产责任决定；“验证程度”回答证明这次修改需要把证据扩展多远。不要把测试移动到程度目录，也不要创建 `l1`、`l2`、`l3`、`full` 或 `dynamic` 测试树。

| 程度 | 证明什么 | 典型范围 |
| --- | --- | --- |
| L1 最小验证 | 这一次边界明确的局部修改没有写错 | 相关语法/类型检查、`git diff --check`、直接保护行为的少量测试 |
| L2 模块验证 | 一个生产模块内的完整能力仍然成立 | 先跑新增/失败项，再跑该模块目录；只按真实依赖补少量协议或边界测试 |
| L3 集成验证 | 被修改连接起来的多个模块形成完整能力链 | 涉及模块的直接测试、边界协议和一个或少量代表性闭环 |
| L4 全量回归 | 共享高风险边界或阶段最终稳定树没有发生仓库级退化 | pytest 全量、前端 Vitest 全量、前端生产构建及 architecture 检查 |
| L5 真实动态验收 | 自动化局部测试无法证明的真实产品边界成立 | Windows Terminal、PowerShell、`start.cmd`、浏览器/GUI、真实子进程、Target、Observer、数据库或竞态 |

L5 是独立维度，不是“比 L4 更大”的测试集合，可以与任一自动化等级组合。例如 Banner 修改使用 `scripts + L1 + L5`；完整权限关系图使用 `frontend/permissions + L2 + L5`；跨 Protocol、Workflow、Runner 的状态化能力使用相关模块 `+ L3 + L5`；共享 Verification 语义变化才可能需要 `L3 + L4 + L5`。

### `essential` 的定位

`essential` 覆盖架构边界、核心权限语义、公共协议、数据库迁移、Job 恢复、启动入口、控制面和一个授权黄金闭环，是稳定的跨模块重要回归集合，不等于 L1 最小验证，也不能替代改动相关的定向测试。

- L1、L2 默认不运行 `essential`。
- L3 只有确实触及核心跨模块边界，或阶段中间需要一次重要门禁时才考虑它。
- L4 全量已经包含 `essential`，同一代码状态不得先跑 `essential` 再立即跑全量。
- 前端组件测试与源码共置，不受 pytest marker 管理。

目录表示模块责任，`essential`、`browser`、`process`、`database`、`e2e`、`slow` 等少量 marker 表示稳定测试属性；L1～L5 是本次改动的执行策略，不建立同名 pytest marker。

### 验证合同与逐级升级

每个非平凡验证批次开始前明确：测试模块、L1～L4 程度、是否需要 L5、当前等级为何足够，以及出现什么证据才升级。通常按以下顺序选择证据：

```text
局部修改 → L1
形成完整模块 → L2
实际跨多个模块 → L3
触及共享高风险边界或阶段最终稳定树 → L4
需要证明真实运行边界 → 在对应等级追加 L5
```

不要按代码行数、任务名称或“更保险”的主观感觉直接选择 L4。一个大型阶段可以在各子阶段使用 L1～L3 和必要 L5，只在全部生产代码稳定后执行一次 L4。

测试失败后先区分产品逻辑、测试/fixture 与环境工具问题。修复后第一步只重跑失败项；通过后按修复真实影响补直接邻域。只有修复触及更大的共享边界，才重新运行完整 L2/L3 或评估 L4。错误 Python、缺失依赖、框架限制、jsdom 能力缺口、浏览器 locator、路径错误和陈旧 fixture 不算产品逻辑失败，不能为适配验证工具修改正确的生产行为。

同一 HEAD 和 working-tree 状态禁止重复 L4。L4 后只修改 README、注释或无行为影响文案时，不机械重跑产品全量；L4 发现失败时也先运行修复项和直接邻域，只有共享核心发生变化或原证据失效才考虑第二次 L4。

## 常用命令

命令只是执行手段，先根据验证合同选择实际模块和程度。所有仓库 pytest 都经 `scripts/dev.ps1 test` 运行；脚本会固定解释器与完整运行身份，并自行设置 `-B`、禁用 cacheprovider、创建和精确清理唯一 basetemp。不要直接运行 `python -m pytest`，仅激活 `jiejian_env` 并不足以建立 Worker、Runner 和 Observer 所需的受控身份。

L3 确实需要阶段中间 `essential` 门禁时：

```powershell
.\scripts\dev.ps1 test -CommandArguments @('-m', 'essential')
```

L4 直接运行全量，不先运行上面的 `essential`：

```powershell
.\scripts\dev.ps1 test
```

L1～L3 优先把命令末尾替换为直接测试文件或对应模块目录，例如 `tests/backend/cli`、`tests/backend/workflows/recording`、`tests/protocols/test_example.py`。L4 仓库级全量还要运行：

```powershell
.\scripts\dev.ps1 frontend-test
.\scripts\dev.ps1 prepare -ForcePrepare
```

前端测试、TypeScript 和 Vite 只允许在 `var/runtime/build/frontend-workspace` 中运行；不要从 `product/frontend` 直接调用 pnpm。`frontend-test` 接受 Vitest 参数，前端 production build 由受控 prepare 写入 `var/runtime/frontend`。

只收集不执行时加 `--collect-only -q`。E2E 和 architecture 可分别运行：

```powershell
.\scripts\dev.ps1 test tests/e2e
.\scripts\dev.ps1 test tests/architecture
```

测试路径或测试节点直接追加在命令末尾；pytest 选项通过 `-CommandArguments` 数组传递。`dev.ps1` 负责 `var/test/` 下本次唯一 basetemp 的创建与精确清理；`var/test` 整体都不属于产品事实。需要 `--lf`、`--ff` 或 `--stepwise` 时才临时启用 pytest cache。

## fixture 规则

- 根 `conftest.py` 只放跨多个测试域使用的环境和本地 Sample 服务 fixture。
- 某一层或某个能力专用的 fixture 放在最近的 `conftest.py`，例如 `backend/infra/runtime/` 和其 `jobs/` 子树。
- 跨能力域复用的稳定构造器放在 `fixtures/`，不要从另一个 `test_*.py` 导入通用 Runner 或 Evidence 构造器。同一能力内只服务一个边界 harness 的辅助对象可以留在该边界测试旁，但不得形成循环依赖或进入根 `conftest.py`。
- 只被一个文件使用的 fixture 留在该文件。没有多个真实消费者时不要上移到根。
- 启动真实 Python 子进程的正向 fixture 使用 `{**os.environ, "本用例秘密": "值"}` 保留官方测试入口建立的完整身份；只有专门验证环境闸门拒绝行为的负向测试才传入缺失或伪造的环境。
- 只有两个测试确实保护同一行为，或旧行为已经不存在，才允许删除、合并或参数化；目录变整齐不是删测试的理由。

## 新测试放在哪里

先定位生产责任，再决定测试层级：纯规则进 `core`，应用编排进 `workflows`，外部资源/进程/持久化进 `infra`，transport 进 `api` 或 `cli`，公共 wire 格式进 `protocols`。已有文件已经覆盖同一边界时扩展它；属于新的独立失败边界或不同生产模块时再新建文件。

新增测试文件必须使用全树唯一 basename，并在移动或重命名后运行全量 `--collect-only`。这条规则用于避免非包测试树出现 import file mismatch；不能用删除缓存掩盖同名文件冲突。
