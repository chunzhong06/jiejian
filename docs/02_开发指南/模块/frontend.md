# 前端模块

> 状态：CURRENT。`product/frontend` 按用户任务组织 Web GUI，只投影后端权威事实，不成为第二套业务状态机。

## 职责

前端负责 Web 产品壳、应用接入、Business Boundary 首次建立与持续维护、loopback API DTO、响应式布局、可访问交互和错误恢复。它把 `WorkspaceView`、`BusinessBoundaryView`、维护草稿与服务端 Proposal 变更摘要翻译为用户能理解的页面和操作；不重算 `PrimaryTask` 或 implementation currentness。

## 非职责

前端不执行目标请求、不读取 SecretStore、不持久化 Cookie/Token，也不重新计算 Contract、coverage、Observer 充分性、Verdict、Finding 或 Gate。页面步骤、loading 和本地路由不是产品进度真源；刷新后必须从后端恢复。

## 稳定入口与目录边界

| 位置 | 负责什么 | 不负责什么 |
| --- | --- | --- |
| `product/frontend/src/app/` | ControlShell、正式路由、项目切换、亮暗主题、全局状态恢复、错误与通知 | 各业务页面内部实现、后端事实重算 |
| `product/frontend/src/api/` | 当前 loopback DTO、request/envelope、资源 client | 浏览器存储秘密、兼容旧 DTO |
| `product/frontend/src/features/` | workspace、changes、access、preparation、identities、recording、testing、boundaries、tools、settings、system 用户任务 | 跨任务真源和通用基础设施 |
| `product/frontend/src/shared/ui/`、`product/frontend/src/shared/styles/` | 唯一视觉 token、编辑式任务骨架与共享排版 | 权限、任务优先级和安全结论 |
| `product/frontend/src/components/` | 导航、页头、状态提示、通用状态与可访问组件 | 业务规则、API 写入副作用 |
| `product/frontend/package.json`、`product/frontend/tsconfig*.json` | 源码依赖/类型/构建合同 | 产品版本真源、node_modules 或 dist |
| `var/development/frontend/` | 受控 Node/pnpm、workspace、依赖与不可变 build | Git 管理源码、产品运行数据 |

一级导航是 `/workspace 当前工作`、`/permissions 权限规则`、`/changes 代码变化`、`/history 检查历史`。系统状态入口位于桌面导航左下角和窄屏菜单底部，统一进入系统详情；顶部更多菜单不重复此入口。当前工作直接装配服务端 PrimaryTask 指向的权限、应用或 CurrentTestsPage；`/tests` 与 `/changes` 保留精确 task/run/change/repair 深链。权限编辑从主任务和自由入口共用同一页面。权限总览按动作索引展示规则摘要，业务定义单独管理；单条编辑先保存到浏览器会话草稿，再统一生成待审提案并显式批准。代码变化以记录列表与当前详情组织，区分 Agent 声明、实际源码变化和原题复验；示例环境控制只展开一层。Preparation 只展开当前缺口，其他有效材料保留；成功回执和后续同步失败分开。OfficialSamplePanel 仅提供中性环境管理，普通 Proposal/Human Approval、材料采用和显式检查仍是唯一业务入口。ToolsPage 管理连接与逐项目临时授权，不把连接当作正在执行。

`CurrentResultStory` 默认展示所选 Case 的已发布执行路径，缺 Trace 时保留事实对照；仅布局显式父边，不从 HTTP、时间或效果事实补因果。桌面 Evidence 为不改变画布尺寸的 complementary 浮层，优先放在右侧并避开所选事实，窄屏为 dialog；来源证据继续回答四问，节点证据说明所选位置及承载文档。修复要求按需展开，RepairComparison 保留 DENY、SELECTED_ALLOW 和全部 REGRESSION，普通 PASS 不等于原题 VERIFIED。历史从 project → exact Run → exact Case → Evidence 下钻，返回保留筛选与位置；协议见[当前 CHECK 只读投影](../../03_参考手册/协议/控制面与Machine输出协议.md#当前-check-历史与执行路径)。

`api/currentChecks.ts` 负责当前 CHECK；`api/jobs.ts` 仅提供录制取消 Job 和 JobEventDto。旧 checks 页面与旧结果客户端已删除，旧 URL 只给不可用页。后台通知由 `app/useCheckActivity.ts` 提供，项目内会话由 `app/RetainedWorkPages.tsx` 保留。

精确组件和类型见[前端自动代码参考](../../03_参考手册/代码/frontend.md)。

候选审阅由 `CandidateReview` 保留本地选择，页签切换不提交；完整摘要确认才调用批量 API。首次权限编辑复用 `PermissionRuleForm`，单条保存只更新本地草稿。`TaskContinuity` 展示服务端位置与局部回执，编辑保护仅阻止后台任务替换当前输入；跨项目清空旧会话。批准成功而下一步读取失败时只重读，批准回执不明时只查询同一提案决定。

检查页观察到运行转为已发布后，先显示结果已保存，由用户点击查看；直接打开历史结果不产生新完成回执。已登记代码变化可只读核对最新材料任务，无需重复登记。

## 我想修改什么

| 任务 | 主要位置 | 先读与直接验证 |
| --- | --- | --- |
| 修改产品壳、路由或恢复 | `product/frontend/src/app/ControlShell.tsx`、`presentation.ts` | [修改前端](../任务/修改前端.md)；`frontend-test src/app/ControlShell.test.tsx` |
| 修改亮暗主题 | `shared/ui/tokens.ts`、`app/ThemeContext.tsx`、`app/theme.ts`、`shared/styles/editorial.css` | ThemeContext 测试、生产 build、亮暗 2560 与响应式 Playwright |
| 修改 API envelope、错误或请求基础层 | `product/frontend/src/api/http.ts` | `frontend-test src/api/http.test.ts`；再测一个直接消费者 |
| 修改某类 API DTO/client | `product/frontend/src/api/*.ts` 与对应 `product/backend/api/routers/*.py` | 对应后端 Router 测试 + DTO 消费页测试 |
| 修改动作级工作台 | `features/workspace/WorkbenchPage.tsx`、`api/workspace.ts`、`app/useProjectWorkspace.ts` | Workbench、Workspace API 与 ControlShell 测试 |
| 修改应用接入与理解 | `features/access/AccessPage.tsx`、`ApplicationSetup.tsx` | `frontend-test src/features/access`；onboarding/application-understanding API 测试 |
| 修改 Business Boundary 提案与审批 | `features/boundaries/`、`api/businessBoundaries.ts` | [修改业务边界、权限意图与 Agent 授权](../任务/修改权限意图与Agent授权.md)；BusinessBoundaryPage 与 ControlShell 测试 |
| 修改测试身份 | `features/identities/TestIdentityPage.tsx` | [修改测试账号](../任务/修改测试账号.md)；`frontend-test src/features/identities` |
| 修改录制与安全准备 | `features/recording/` | [修改 Recording](../任务/修改Recording.md)；`frontend-test src/features/recording` |
| 修改 Agent 变化与待办 | `features/changes/ChangesPage.tsx`、`api/sourceChanges.ts` | [修改 Agent 变更影响](../任务/修改Agent变更影响.md)；Workbench、ControlShell 与后端 change 测试 |
| 修改测试模块总览与当前结果 | `features/testing/CurrentTestsPage.tsx`、`CurrentResultStory.tsx`、`api/currentChecks.ts` | CurrentTestsPage 与 ControlShell 路由测试；服务端预览门禁、提交幂等、陈旧响应与证据完整性 |
| 修改测试准备总览 | `features/preparation/PreparationPage.tsx`、`api/preparation.ts` | PreparationView、Workspace PrimaryTask、页面直接测试与 ControlShell 权威刷新测试 |
| 修改当前结果、历史与 Evidence | `features/testing/CurrentResultStory.tsx`、`ExecutionPath.tsx`、`CheckHistoryPage.tsx` | [修改结果与报告](../任务/修改结果与报告.md)；对应单文件测试 |
| 修改模型或运行环境设置 | `features/settings/`、`features/system/` | settings/system 组件与对应 API 测试 |
| 修改样式、响应式或可访问性 | 所属 feature CSS/TSX 与 `product/frontend/src/components/` | 定向 Vitest；生产 build；展示验收 |
| 修改依赖或构建 | `product/frontend/package.json`、`product/frontend/pnpm-lock.yaml`、`scripts/dev/frontend.ps1` | `dev.ps1 frontend-test`、`prepare -ForcePrepare` |

## 事实与页面状态

`WorkspaceService` 决定唯一 PrimaryTask；active_check 仅投影同项目最新活动 Run，source_change.submitted_by 原样表示登记来源。CheckPreview、CheckRunStatus、ResultStory 分别负责门禁、生命周期和已发布结论。RetainedWorkPages 在当前项目页面会话内保留工作输入、权限草稿、历史筛选和位置；项目切换或明确重试重建，不用 localStorage 持久化这些状态，也不保留设置/密钥页面。Evidence Portal 离开页面必须关闭。后台完成只提供通知，不自动导航；短检查通过新的 latest_result 精确回读确认，首次加载已有结果不提示刚完成。

所有写操作要有清楚的 busy、成功、失败和恢复路径。需要长时间的多阶段过程必须展示稳定阶段边界，服务端有进度时流式呈现；没有权威进度时说明当前阶段和静默上限，不伪造百分比。首个主错误保留，cleanup warning 单独展示。

## 一次前端变更的完整路线

1. 从用户正在完成的任务和正式路由开始，不先从组件名称猜归属。
2. 找到 `ControlShell.tsx` 实际装配的 feature，再找到该 feature 调用的 `src/api/*.ts`。
3. 判断页面展示的是本地交互态还是后端权威事实；后者先核对对应 Router、DTO 和 workflow。
4. 遵守当前 design token、2560×1440 主基准、展示用语层级和可访问性结构；旧交互若与持续验证合同冲突，应删除而不是保留兼容层。
5. 先跑所属 Vitest；DTO 或路由变化再补后端直接测试和 ControlShell 测试；最后只在需要时做 production build 与展示验收。

## 必须保持的边界

- API DTO 只接受当前 envelope；未知 schema/字段按 request 层失败，不在组件里猜旧格式。
- 权限、Observer 与 ResultStory 由后端拥有；组件不按 HTTP 状态或文本正则自行判断安全。
- 计划身份来自冻结请求；没有独立实际身份事实时显示无法确认，不用计划值冒充实际值。
- 密码、Cookie、Token、API Key 不进 localStorage、普通 React state 日志、错误详情或 DOM 长期展示；临时 Key 成功失败后立即清空。
- 普通用户先看到任务语言和当前主动作，内部 ID、reason code、Schema、路径和原始 Evidence 只进入明确命名的证据、报告或 Machine 入口，不建立通用“高级信息”收纳箱。
- 真正 `<button>`、label、dialog 和状态文本保持可访问；自动 L5 通过 UI Automation InvokePattern 操作正式按钮，不为测试增加隐藏入口。
- `product/frontend` 只保存源码/配置，禁止 node_modules、dist、测试缓存和 tsbuildinfo。
- Workbench 不常驻显示产品版本；只在系统设置等明确诊断位置展示。
- 布局唯一真源是 tokens.ts：导航 200px、顶部 60px、窄屏摘要 52px、内容最大 1460px。中性浅灰/白完整工作面、有限深度及局部深色执行路径同时支持亮暗主题；普通返回与刷新不悬浮，确有主提交时 TaskActionBar 才在表单范围粘滞。动效只表达状态，180ms 并保持 reduce-motion 等价；菜单关闭后不保留旧浮层。
- 普通 Boundary 页面按同一 Proposal/Approval 流程处理业务边界。官方 recipe 只能由真实活动 Sample context 提交为普通待审提案，再由用户明确批准；不得按项目名猜 Sample，也不得自动批准。
- 视觉验收以 2560×1440、浏览器 100% 为主基准，工作台第一屏以应用、当前判断和唯一主任务为焦点，最近可信结果退为上下文，其他工作通过安静的文字入口访问；同时核对原生亮色与暗色，并覆盖 1280px、600px 和长表单内确有主提交时的 `TaskActionBar`。普通结果与展示模式复用同一事实链和颜色语义。

## 直接验证

前端测试只能通过受控入口：

```powershell
.\scripts\dev.ps1 frontend-test src/features/system/RuntimePage.test.tsx
.\scripts\dev.ps1 frontend-test src/app/ControlShell.test.tsx
.\scripts\dev.ps1 prepare -ForcePrepare
```

普通 TS/TSX/CSS 变化先跑所属测试文件；跨 DTO/路由才补相邻 API/ControlShell。生产源码变化在收口前跑一次 TypeScript + Vite build；视觉、窗口节奏和文案由展示验收判断。自动 L5 只在最终验收运行，不为每个组件改动重复启动。

## 首错定位

| 现象 | 先检查 | 不要先做 |
| --- | --- | --- |
| 刷新后状态回退或页面分叉 | 对应 API 响应、`ControlShell.tsx` 恢复路径、后端 Workspace/Run 真源 | 增加 localStorage 业务缓存 |
| 页面显示结论与 API 不一致 | ResultStory、发布完整性与 `src/api/currentChecks.ts` | 在组件里重算 Verdict 或解析文案 |
| 写操作成功但页面仍显示旧状态 | mutation 完成后的权威查询和失效刷新 | 用定时器永久轮询或手改前端对象 |
| 长任务看似卡死 | Job/Run 状态、正式 progress、当前阶段静默上限 | 伪造百分比或把 loading 当完成事实 |
| Vitest 通过但生产构建失败 | 受控 workspace 的 TypeScript/Vite build 和导入边界 | 在 `product/frontend` 直接安装依赖 |

## 相关真源

- [修改前端](../任务/修改前端.md)
- [产品入口与控制面](../../01_系统地图/产品入口与控制面.md)
- [权限验证与结果](../../01_系统地图/权限验证与结果.md)
- [控制面与 Machine 输出协议](../../03_参考手册/协议/控制面与Machine输出协议.md)
- [验证与测试](../../04_工程约束/验证与测试.md)
