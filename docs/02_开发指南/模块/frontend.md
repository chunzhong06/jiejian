# 前端模块

> 状态：CURRENT。`product/frontend` 按用户任务组织 Web GUI，只投影后端权威事实，不成为第二套业务状态机。

## 职责

前端负责 Web V1 产品壳、应用接入到结果查看的普通路径、loopback API DTO、响应式布局、可访问交互、错误恢复和比赛展示体验。它把 ProductStatus、ProjectReadiness、Job/Run、ResultPresentation 与 HistoryView 翻译为用户能理解的页面和操作。

## 非职责

前端不执行目标请求、不读取 SecretStore、不持久化 Cookie/Token，也不重新计算 Contract、coverage、Observer 充分性、Verdict、Finding 或 Gate。页面步骤、loading 和本地路由不是产品进度真源；刷新后必须从后端恢复。

## 稳定入口与目录边界

| 位置 | 负责什么 | 不负责什么 |
| --- | --- | --- |
| `product/frontend/src/app/` | ControlShell、正式路由、项目切换、全局状态恢复、错误与通知 | 各业务页面内部实现、后端事实重算 |
| `product/frontend/src/api/` | 当前 loopback DTO、request/envelope、资源 client | 浏览器存储秘密、兼容旧 DTO |
| `product/frontend/src/features/` | access、workspace、identities、recording、permissions、checks、settings、system 用户任务 | 跨任务真源和通用基础设施 |
| `product/frontend/src/components/` | 导航、页头、导览、通用状态与可访问组件 | 业务规则、API 写入副作用 |
| `product/frontend/package.json`、`product/frontend/tsconfig*.json` | 源码依赖/类型/构建合同 | 产品版本真源、node_modules 或 dist |
| `var/development/frontend/` | 受控 Node/pnpm、workspace、依赖与不可变 build | Git 管理源码、产品运行数据 |

普通路由围绕 `/workspace /application /identities /flows /check /results /history`；系统与模型设置是明确辅助入口。`/check` 连续承载权限确认、准备、预览、开始、进度与完成，Report 是结果内视图，不建立平行流程。

精确组件和类型见[前端自动代码参考](../../03_参考手册/代码/frontend.md)。

## 我想修改什么

| 任务 | 主要位置 | 先读与直接验证 |
| --- | --- | --- |
| 修改产品壳、路由或恢复 | `product/frontend/src/app/ControlShell.tsx`、`presentation.ts` | [修改前端](../任务/修改前端.md)；`frontend-test src/app/ControlShell.test.tsx` |
| 修改 API envelope、错误或请求基础层 | `product/frontend/src/api/http.ts` | `frontend-test src/api/http.test.ts`；再测一个直接消费者 |
| 修改某类 API DTO/client | `product/frontend/src/api/*.ts` 与对应 `product/backend/api/routers/*.py` | 对应后端 Router 测试 + DTO 消费页测试 |
| 修改工作台、下一步或评委导览 | `features/workspace/WorkbenchPage.tsx`、`components/JudgeGuideBar.tsx` | Workbench、JudgeGuideBar 与 ProductStatus/experience 测试 |
| 修改应用接入与理解 | `features/access/AccessPage.tsx`、`ApplicationSetup.tsx` | `frontend-test src/features/access`；onboarding/application-understanding API 测试 |
| 修改测试身份 | `features/identities/TestIdentityPage.tsx` | [修改测试账号](../任务/修改测试账号.md)；`frontend-test src/features/identities` |
| 修改录制与安全准备 | `features/recording/` | [修改 Recording](../任务/修改Recording.md)；`frontend-test src/features/recording` |
| 修改权限确认 | `features/permissions/`、`features/checks/PermissionCheckPage.tsx` | [修改权限判断](../任务/修改权限判断.md)；两个所属组件测试 |
| 修改结果、历史、Evidence 或报告 | `features/checks/CheckResultsPage.tsx`、`CheckHistoryPage.tsx`、`EvidenceTimeline.tsx`、`ReportPanel.tsx` | [修改结果与报告](../任务/修改结果与报告.md)；对应单文件测试 |
| 修改模型或运行环境设置 | `features/settings/`、`features/system/` | settings/system 组件与对应 API 测试 |
| 修改样式、响应式或可访问性 | 所属 feature CSS/TSX 与 `product/frontend/src/components/` | 定向 Vitest；生产 build；展示验收 |
| 修改依赖或构建 | `product/frontend/package.json`、`product/frontend/pnpm-lock.yaml`、`scripts/dev/frontend.ps1` | `dev.ps1 frontend-test`、`prepare -ForcePrepare` |

## 事实与页面状态

`ProjectReadiness` 决定六步完成状态和唯一下一步；Job/Run 决定运行生命周期；Runner progress 只提供可丢失的阶段展示；`ResultPresentation` 决定单次结果故事；`HistoryView` 决定跨次变化。前端可以保留当前选择的项目、页面和未提交表单，但不能把它们当作已确认后端事实。

所有写操作要有清楚的 busy、成功、失败和恢复路径。需要长时间的多阶段过程必须展示稳定阶段边界，服务端有进度时流式呈现；没有权威进度时说明当前阶段和静默上限，不伪造百分比。首个主错误保留，cleanup warning 单独展示。

## 一次前端变更的完整路线

1. 从用户正在完成的任务和正式路由开始，不先从组件名称猜归属。
2. 找到 `ControlShell.tsx` 实际装配的 feature，再找到该 feature 调用的 `src/api/*.ts`。
3. 判断页面展示的是本地交互态还是后端权威事实；后者先核对对应 Router、DTO 和 workflow。
4. 保持当前 design token、布局、文案层级和可访问性结构，在原组件内完成最小改动。
5. 先跑所属 Vitest；DTO 或路由变化再补后端直接测试和 ControlShell 测试；最后只在需要时做 production build 与展示验收。

## 必须保持的边界

- API DTO 只接受当前 envelope；未知 schema/字段按 request 层失败，不在组件里猜旧格式。
- 权限、Observer、ResultPresentation 与 History 由后端拥有；组件不按 HTTP 状态或文本正则自行判断安全。
- 计划身份来自冻结请求；没有独立实际身份事实时显示无法确认，不用计划值冒充实际值。
- 密码、Cookie、Token、API Key 不进 localStorage、普通 React state 日志、错误详情或 DOM 长期展示；临时 Key 成功失败后立即清空。
- 普通用户先看到任务语言和唯一主动作，内部 ID、reason code、Schema、路径和原始 Evidence 进入高级信息。
- 真正 `<button>`、label、dialog 和状态文本保持可访问；自动 L5 通过 UI Automation InvokePattern 操作正式按钮，不为测试增加隐藏入口。
- `product/frontend` 只保存源码/配置，禁止 node_modules、dist、测试缓存和 tsbuildinfo。
- Workbench 不常驻显示产品版本；1.0.1 只在系统设置等明确诊断位置展示。

## 直接验证

前端测试只能通过受控入口：

```powershell
.\scripts\dev.ps1 frontend-test src/features/system/RuntimePage.test.tsx
.\scripts\dev.ps1 frontend-test src/app/ControlShell.test.tsx
.\scripts\dev.ps1 prepare -ForcePrepare
```

普通 TS/TSX/CSS 变化先跑所属测试文件；跨 DTO/路由才补相邻 API/ControlShell。生产源码变化在收口前跑一次 TypeScript + Vite build；视觉、窗口节奏和文案由展示验收判断。自动 L5 只在阶段最终收口运行，不为每个组件改动重复启动。

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
