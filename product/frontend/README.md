# 前端代码导航

> 本页是 Web GUI 的局部导航，不替代 [产品入口与控制面架构](../../docs/02_架构设计/产品入口与控制面架构.md)。

## 页面与用户路径

普通用户主路径是：工作台 → 应用接入 → 权限规则 → 开始检查 → 检查结果。历史变化用于查看回归；流程录制、模型服务和运行环境放在高级能力中。

页面主要位于 `src/features/`：

- `workspace/`：工作台和下一步提示。
- `access/`：应用接入、目录选择和 onboarding。
- `permissions/`：权限规则、可筛选矩阵和关系图。
- `checks/`：检查提交、进度、结果、证据、报告和历史变化。
- `recording/`：浏览器录制、FlowDraft 审阅和确认保存。
- `settings/`、`system/`：模型服务和运行环境。

## src 目录职责

| 路径 | 职责 |
| --- | --- |
| `src/app/` | 控制壳、路由级状态和统一展示投影。 |
| `src/api/` | loopback API 客户端、DTO 和稳定错误处理。 |
| `src/features/` | 按用户任务组织页面与局部组件。 |
| `src/components/` | 多个 feature 复用的通用展示组件。 |
| `src/main.tsx` | React 入口。 |
| `src/styles.css` | 当前产品的全局样式。 |
| `src/test-setup.ts` | Vitest/Testing Library 公共测试环境。 |

## 开发与验证

在 `product/frontend` 目录运行：

```powershell
pnpm dev
pnpm test
pnpm build
```

组件测试与源码放在一起，文件名使用 `*.test.tsx` 或 `*.test.ts`。涉及真实路由、下拉交互、浏览器或完整产品闭环时，再补后端 `tests/e2e/` 测试。

前端只展示已经发布的 Contract、Evidence、Finding、Verification 和 Gate 事实。它不能自行决定漏洞结论，不能把 HTTP 状态当作真实资源状态，也不能直接访问目标或持久化秘密。深入理解数据流时，从[技术文档入口](../../docs/README.md)进入对应 Architecture。
