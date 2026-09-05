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
| `product/frontend/src/features/` | workspace、changes、access、preparation、identities、recording、checks、presentation、settings、system 用户任务 | 跨任务真源和通用基础设施 |
| `product/frontend/src/components/` | 导航、页头、状态提示、通用状态与可访问组件 | 业务规则、API 写入副作用 |
| `product/frontend/package.json`、`product/frontend/tsconfig*.json` | 源码依赖/类型/构建合同 | 产品版本真源、node_modules 或 dist |
| `var/development/frontend/` | 受控 Node/pnpm、workspace、依赖与不可变 build | Git 管理源码、产品运行数据 |

普通工作区以 `/workspace` 为主控工作台，保留 `/changes /permissions /tests` 三个辅助模块的视觉层级。只有 `/permissions` 接入 `BusinessBoundaryPage` 与 `BoundaryMaintenanceEditor`；`/changes` 与 `/tests` 明确不可用，不调用旧 writer。历史 Recording/Run/Result 深链只显示能力边界。

精确组件和类型见[前端自动代码参考](../../03_参考手册/代码/frontend.md)。

## 我想修改什么

| 任务 | 主要位置 | 先读与直接验证 |
| --- | --- | --- |
| 修改产品壳、路由或恢复 | `product/frontend/src/app/ControlShell.tsx`、`presentation.ts` | [修改前端](../任务/修改前端.md)；`frontend-test src/app/ControlShell.test.tsx` |
| 修改亮暗主题 | `app/ThemeContext.tsx`、`app/theme.ts`、`styles.css` | ThemeContext 测试、生产 build、亮暗 2560 与响应式 Playwright |
| 修改 API envelope、错误或请求基础层 | `product/frontend/src/api/http.ts` | `frontend-test src/api/http.test.ts`；再测一个直接消费者 |
| 修改某类 API DTO/client | `product/frontend/src/api/*.ts` 与对应 `product/backend/api/routers/*.py` | 对应后端 Router 测试 + DTO 消费页测试 |
| 修改动作级工作台 | `features/workspace/WorkbenchPage.tsx`、`api/workspace.ts`、`app/useProjectWorkspace.ts` | Workbench、Workspace API 与 ControlShell 测试 |
| 修改应用接入与理解 | `features/access/AccessPage.tsx`、`ApplicationSetup.tsx` | `frontend-test src/features/access`；onboarding/application-understanding API 测试 |
| 修改 Business Boundary 提案与审批 | `features/boundaries/`、`api/businessBoundaries.ts` | [修改业务边界、权限意图与 Agent 授权](../任务/修改权限意图与Agent授权.md)；BusinessBoundaryPage 与 ControlShell 测试 |
| 修改测试身份 | `features/identities/TestIdentityPage.tsx` | [修改测试账号](../任务/修改测试账号.md)；`frontend-test src/features/identities` |
| 修改录制与安全准备 | `features/recording/` | [修改 Recording](../任务/修改Recording.md)；`frontend-test src/features/recording` |
| 修改 Agent 变化与待办 | `features/changes/ChangesPage.tsx`、`api/sourceChanges.ts` | [修改 Agent 变更影响](../任务/修改Agent变更影响.md)；Workbench、ControlShell 与后端 change 测试 |
| 修改测试模块总览 | `features/testing/TestingPage.tsx` | TestingPage 与 ControlShell 路由测试；再按实际修改核对测试条件、运行或结果页面 |
| 修改测试准备总览 | `features/preparation/PreparationPage.tsx`、`api/projects.ts` | ProjectPreparation、Readiness、页面直接测试与 ControlShell 权威刷新测试 |
| 修改保留的验证/结果组件 | `features/checks/` | 先确认当前路由是否接入；不得把旧 permissions mode 恢复为 Human Approval 入口 |
| 修改结果、历史、Evidence 或报告 | `features/checks/CheckResultsPage.tsx`、`CheckHistoryPage.tsx`、`EvidenceTimeline.tsx`、`ReportPanel.tsx` | [修改结果与报告](../任务/修改结果与报告.md)；对应单文件测试 |
| 修改模型或运行环境设置 | `features/settings/`、`features/system/` | settings/system 组件与对应 API 测试 |
| 修改样式、响应式或可访问性 | 所属 feature CSS/TSX 与 `product/frontend/src/components/` | 定向 Vitest；生产 build；展示验收 |
| 修改依赖或构建 | `product/frontend/package.json`、`product/frontend/pnpm-lock.yaml`、`scripts/dev/frontend.ps1` | `dev.ps1 frontend-test`、`prepare -ForcePrepare` |

## 事实与页面状态

`WorkspaceService` 决定 当前区域状态、动作级摘要和唯一 `PrimaryTask`；`BusinessBoundaryView` 决定正式 Actor/Action/Effect/Permission，维护草稿完整保留 stable identity，`BoundaryProposalView.change_summary` 决定待审变化说明。前端可以保留当前项目、页面和未提交草稿，但正式事实必须刷新 API。保留的 Job/Run、ResultPresentation 与 HistoryView 不属于当前检查入口。

所有写操作要有清楚的 busy、成功、失败和恢复路径。需要长时间的多阶段过程必须展示稳定阶段边界，服务端有进度时流式呈现；没有权威进度时说明当前阶段和静默上限，不伪造百分比。首个主错误保留，cleanup warning 单独展示。

## 一次前端变更的完整路线

1. 从用户正在完成的任务和正式路由开始，不先从组件名称猜归属。
2. 找到 `ControlShell.tsx` 实际装配的 feature，再找到该 feature 调用的 `src/api/*.ts`。
3. 判断页面展示的是本地交互态还是后端权威事实；后者先核对对应 Router、DTO 和 workflow。
4. 遵守当前 design token、2560×1440 主基准、展示用语层级和可访问性结构；旧交互若与持续验证合同冲突，应删除而不是保留兼容层。
5. 先跑所属 Vitest；DTO 或路由变化再补后端直接测试和 ControlShell 测试；最后只在需要时做 production build 与展示验收。

## 必须保持的边界

- API DTO 只接受当前 envelope；未知 schema/字段按 request 层失败，不在组件里猜旧格式。
- 权限、Observer、ResultPresentation 与 History 由后端拥有；组件不按 HTTP 状态或文本正则自行判断安全。
- 计划身份来自冻结请求；没有独立实际身份事实时显示无法确认，不用计划值冒充实际值。
- 密码、Cookie、Token、API Key 不进 localStorage、普通 React state 日志、错误详情或 DOM 长期展示；临时 Key 成功失败后立即清空。
- 普通用户先看到任务语言和当前主动作，内部 ID、reason code、Schema、路径和原始 Evidence 只进入明确命名的证据、报告或 Machine 入口，不建立通用“高级信息”收纳箱。
- 真正 `<button>`、label、dialog 和状态文本保持可访问；自动 L5 通过 UI Automation InvokePattern 操作正式按钮，不为测试增加隐藏入口。
- `product/frontend` 只保存源码/配置，禁止 node_modules、dist、测试缓存和 tsbuildinfo。
- Workbench 不常驻显示产品版本；只在系统设置等明确诊断位置展示。
- 桌面侧栏固定 224px，只承载四个产品区域；顶部固定 52px，承载应用切换、活动任务、AI 工具连接和“设置与更多”。AI 辅助、系统状态、模型、主题与安全退出都位于该菜单，退出是最后一项；菜单关闭后不得保留撑宽文档的旧浮层。
- 普通 Boundary 页面不展示或应用官方业务合同。官方 recipe 只作为后端内部冻结资产保留，等待未来正式 Sample context 通过普通 Proposal 与用户批准流程复用；不得按项目名猜 Sample，也不得把入口移到其他普通页面。
- 视觉验收以 2560×1440、浏览器 100% 为主基准，工作台第一屏必须容纳应用、当前判断、唯一主任务、最近可信结果与三项摘要；同时核对原生亮色与暗色，并覆盖 1280px、600px 和长页面滚动时内容框架内粘滞的 `TaskActionBar`。普通结果与展示模式复用同一事实链和颜色语义。

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
| 刷新后状态回退或页面分叉 | 对应 API 响应、`ControlShell.tsx` 恢复路径、后端 Readiness/Run 真源 | 增加 localStorage 业务缓存 |
| 页面显示结论与 CLI/API 不一致 | ResultPresentation/History DTO 与 `src/api/results.ts` | 在组件里重算 Verdict 或解析文案 |
| 写操作成功但页面仍显示旧状态 | mutation 完成后的权威查询和失效刷新 | 用定时器永久轮询或手改前端对象 |
| 长任务看似卡死 | Job/Run 状态、正式 progress、当前阶段静默上限 | 伪造百分比或把 loading 当完成事实 |
| Vitest 通过但生产构建失败 | 受控 workspace 的 TypeScript/Vite build 和导入边界 | 在 `product/frontend` 直接安装依赖 |

## 相关真源

- [修改前端](../任务/修改前端.md)
- [产品入口与控制面](../../01_系统地图/产品入口与控制面.md)
- [权限验证与结果](../../01_系统地图/权限验证与结果.md)
- [控制面与 Machine 输出协议](../../03_参考手册/协议/控制面与Machine输出协议.md)
- [验证与测试](../../04_工程约束/验证与测试.md)
