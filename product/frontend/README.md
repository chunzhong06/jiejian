# 前端代码导航

> 本页是 Web GUI 的局部导航，不替代 [产品入口与控制面架构](../../docs/02_架构设计/产品入口与控制面架构.md)。

## 页面与用户路径

普通用户主路径是：工作台 → 应用接入 → 权限规则 → 开始检查 → 检查结果。历史变化用于查看回归；流程录制、模型服务和运行环境放在高级能力中。

展示层以中文任务表达为默认。按钮、状态、说明和已知业务枚举使用中文；品牌、命令、JSON 等文件格式、协议字段、路径和需要对照的原始标识保留原文。已知机器值需要同时可辨识时使用“中文含义（原值）”，不得修改 API 数据完成翻译。

页面主要位于 `src/features/`：

- `workspace/`：工作台和下一步提示。
- `access/`：应用接入；`onboarding/` 内分别组织欢迎页、步骤表单和向导编排。
- `permissions/`：权限规则；`explorer/` 放矩阵、关系图与纯 projection，`governance/` 放规则版本治理。
- `checks/`：检查提交、进度、结果、证据、报告和历史变化。
- `recording/`：分别组织录制准备、采集控制、FlowDraft 审阅和页面编排。
- `settings/`、`system/`：模型服务和运行环境。

## src 目录职责

| 路径 | 职责 |
| --- | --- |
| `src/app/` | 控制壳、路由级状态、允许持久化的 browserState 和统一展示投影。 |
| `src/api/` | loopback API 客户端、命名 DTO 和稳定错误处理。 |
| `src/features/` | 按用户任务组织页面与局部组件。 |
| `src/components/` | 多个 feature 复用的通用展示组件。 |
| `src/main.tsx` | React 入口。 |
| `src/styles.css` | 只保留应用壳与跨页面全局样式；Feature 样式跟随所属目录。 |
| `src/test-setup.ts` | Vitest/Testing Library 公共测试环境。 |

## 开发与验证

前端测试统一从仓库根运行：

```powershell
.\scripts\dev.ps1 frontend-test
.\scripts\dev.ps1 frontend-test src/features/checks/StartCheckPage.test.tsx --reporter=verbose
```

`scripts/dev.ps1 frontend-test` 与源码启动共用 `var/runtime/build/frontend-workspace`：同一份前端源码输入集合在排除 `node_modules`、`dist`、`*.tsbuildinfo` 等明确生成物后，同时形成构建指纹和工作区镜像。pnpm 安装视图与 TypeScript 增量文件只留在该工作区，内容寻址 store 位于 `var/cache/pnpm-store`，Vite 缓存位于 `var/cache/vite`，最终网页只进入 `var/runtime/frontend`。不要在 `product/frontend` 直接执行 pnpm install、test 或 build；该目录始终只保留 Git 管理的源码与配置。

生产构建由 `start.cmd` 或 `scripts/dev.ps1 prepare` 按指纹执行。可选 Wheel 使用 `scripts/dev.ps1 package`，直接把 `var/runtime/frontend` 映射为包内 `product/frontend/dist`，不会回写源码目录。

组件测试与源码放在一起，文件名使用 `*.test.tsx` 或 `*.test.ts`。涉及真实路由、下拉交互、浏览器或完整产品闭环时，再补后端 `tests/e2e/` 测试。

权限矩阵负责完整权限集合；关系图全局模式只表达身份、资源和业务关系，角色显示为身份属性。聚焦具体身份后，projection 才过滤到相关节点并加入该身份自己的权限边。布局使用确定性的身份 lane，不引入大型自动布局依赖；节点中文含义与原始 ID 分层展示。

前端只展示已经发布的 Contract、Evidence、Finding、Verification 和 Gate 事实。它不能自行决定漏洞结论，不能把 HTTP 状态当作真实资源状态，也不能直接访问目标或持久化秘密。深入理解数据流时，从[技术文档入口](../../docs/README.md)进入对应 Architecture。
