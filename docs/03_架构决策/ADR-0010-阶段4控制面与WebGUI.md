# ADR-0010：阶段 4 控制面与 Web GUI

- 取代者：ADR-0035
- 当前阅读提示：本文保留历史决策；当前边界以 ../README.md 和相关 CURRENT 文档为准。

## 状态

已取代

## 背景

阶段 1～3 已形成 CLI、持久 Job、独立 Worker/Runner、录制审阅和发布工件闭环，需要由本地 Web GUI 使用同一份持久记录。API 不能复制验证判定、录制状态机或目标传输，也不能因浏览器或 SSE 客户端断开而取消任务。

## 决策

1. API 由 FastAPI 提供，只允许绑定 `127.0.0.1` 或 `::1`；健康检查、OpenAPI、资源管理、任务提交、状态查询、SSE 和已发布结果读取均返回 `schema_version=1`，错误包含稳定错误码和脱敏 `trace_id`。
2. `application/` 保存 CLI、API 和 serve 共用的项目来源校验、Contract 选择和执行请求构造；Verification、Recording 和 Worker 的既有语义不复制到路由。
3. `projects` 向前增加可空来源路径/哈希及 ACTIVE Contract 路径/哈希。来源哈希覆盖 project 文件及其解析出的 Flow 路径和内容；Contract 仍以独立哈希绑定。旧记录可以查询；缺少来源身份的记录必须重新注册后才能创建任务。任一来源或 Contract 内容变化必须显式重新校验。
4. API 创建长任务只写持久请求和 Job，立即返回资源 ID。serve 管理独立 Worker 子进程；API 不执行目标 I/O。SSE 使用 `JobEvent.sequence` 作为事件 ID，支持 `after` 查询参数与 `Last-Event-ID`（显式 `after` 优先），断开不发送取消请求；serve 对同一 `var` 使用单实例锁并诊断陈旧锁。
5. Finding 由已发布且通过 manifest、路径、文件哈希、Evidence 语义哈希和数据库索引一致性校验的 Evidence/JSON report 确定性派生，不建立第二套判定。证据差分只使用已发布 mutation plan 与持久执行请求快照。
6. `product/frontend/` 使用 React、TypeScript、Vite、Ant Design 和 pnpm；GUI 只通过 API 恢复项目、Recording、Run、事件和报告状态。
7. Run 详情从持久 ExecutionRequest 快照提供目标范围、预算和观察器配置；终态必须先通过统一发布完整性读取服务，完整性失败直接返回稳定错误，不以数据库 verdict 降级。Finding 只由非 SAFE Evidence 派生；项目运行列表可将损坏终态标记为 `result_integrity=INVALID` 并隐藏 verdict。
8. `serve` 要求可读的前端 `dist/index.html`，缺失时以 `SERVE_FAILED` 非零退出并释放单实例锁；不自动安装或构建前端。

## 影响与迁移

新增 Alembic `0003_stage4_control_plane` 只增加可空列，阶段 2/3 数据保持可读。旧项目必须在 API 中重新注册或重新校验后才能创建新 Run/Recording。阶段 4 只提供 JSON 报告和 GUI 展示，HTML/SARIF/JUnit、漂移检测和候选 Contract 工作流继续留给后续阶段。Run 概览字段为只读派生数据；运行中尚无发布计划时，用例进度和 Finding 数量明确不可用，不在 API 中重新执行 Planner。

## 回滚

数据库不回滚；可停用 `serve` 与 API 入口，保留已发布历史工件和旧 CLI。不得删除项目来源记录、Job Event 或运行工件。
