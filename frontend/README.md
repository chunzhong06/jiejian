# Frontend

## 定位

`frontend` 是回环控制面的 React 客户端，把“接入、录制、建约、测试、验证、报告”六个用户阶段映射到 FastAPI 能力。服务端数据库、Contract、Job 和 Result 始终是状态真源。

## 负责 / 不负责

- 负责路由、当前项目选择、可恢复 UI 状态、表单、SSE/轮询展示和 API 错误呈现。
- 按能力拆分 Page 和 API client，保持简单的用户阶段名称。
- 不在浏览器复制 Contract 合并、状态机、Job 生命周期、Evidence 判定或 Verdict 规则。

## 子模块与 public API

- `src/app/ControlShell.tsx`：六阶段路由、跨页面状态和 API/Worker/浏览器/LLM 状态区；模型服务设置不是第七阶段。
- `src/features/`：access、recording、contracts、runs、verification、results 页面。
- `src/api/`：按服务端能力拆分的 HTTP/SSE client；`http.ts` 统一错误边界。
- `src/api/llm.ts`、`src/api/system.ts`：模型服务 profile 和只读系统状态客户端；API Key 只作为单次写入字段，不进入 localStorage/sessionStorage。
- `src/main.tsx`：Vite/React 入口。

前端没有对仓库外承诺的 TypeScript API；与后端的稳定边界是当前 HTTP/OpenAPI 行为。

## 调用与数据流

```text
用户操作
→ ControlShell / feature Page
→ api/* client
→ jiejian.api
→ 共享 ApplicationContext
→ 服务端状态返回页面
```

## 关键不变量和失败语义

- localStorage 只保存用户选择和恢复游标，不是 Project、Job 或 Contract 状态真源。
- 页面取消、重试和恢复必须调用服务端能力，不能只改变本地展示。
- SSE/轮询中断不等于 Job 失败；页面重新连接后从服务端恢复。
- API 错误按稳定错误结构展示，不在前端根据文本猜测安全结论。
- 模型服务状态来自显式 profile/状态 API；六阶段路由保持“接入、录制、建约、测试、验证、报告”，窄屏布局不得隐藏真实状态或阶段入口。

## 修改与测试入口

- 组件测试：`src/app/ControlShell.test.tsx`、`src/features/contracts/ContractPage.test.tsx`
- 完整前端：`pnpm test`、`pnpm build`
- 后端行为：[`tests/api`](../tests/api/)

## 相关规范、协议与 ADR

- [系统架构](../docs/01_架构设计/系统架构.md)
- [项目模块地图](../docs/模块地图.md)
- [ADR-0010](../docs/03_技术决策/ADR-0010-阶段4控制面与WebGUI.md)、[ADR-0016](../docs/03_技术决策/ADR-0016-阶段5.4C-CLI与GUI建约接入.md)、[ADR-0020](../docs/03_技术决策/ADR-0020-阶段5.6-LLM配置秘密与协议边界.md)
