# 控制面与 Machine 输出协议

> 状态：CURRENT。本文解释 GUI、CLI Human、Machine v1、API envelope、MCP 工具与同一产品事实的关系；字段以当前代码和直接测试为准。

## 先理解：多个入口只有一套产品状态

界鉴可以从 GUI、CLI 或自动化脚本进入，但这些入口不能各自维护业务进度。当前 GUI 状态由 `WorkspaceService` 从 Project、ApplicationUnderstanding、正式 Business Boundary、Permission、pending Proposal、实时 implementation inspection 与 PreparationView 形成；当前检查与结果由 CheckService、严格发布 Reader 和 ResultStory 提供，SourceChange/ProjectRepair 负责真实变化与原题复验。

```text
ApplicationCore / Published facts
  → WorkspaceView / BusinessBoundaryView / ResultStory / ProjectRepair
  → loopback API envelope → GUI
  → CLI Human / Machine v1
  → MCP Streamable HTTP → 固定工具白名单
  → 当前 Evidence publication（只读已发布事实）
```

页面文案、终端颜色或 JSON 格式都不能反向改变事实。Report 是独立不可变交付物，也不由 CLI stdout 代替。

## WorkspaceView 与 GUI

使用独立 `WorkspaceView` 作为 GUI 唯一工作区 DTO。它包含当前项目与连接、Actor/Action 动作级视图、current Permission、实时 implementation inspection、四个长期区域，以及服务端按固定优先级选出的唯一 `PrimaryTask`。稳定 task ID 与 stale fingerprint 由服务端事实生成；前端不得重算优先级、binding currentness 或权限状态。

Business Boundary API 位于 `/api/projects/{project_id}/business-boundaries`。无正式边界时，`preview` 与首次 Proposal create 建立稳定 identity；已有边界后，普通 create 返回 `BOUNDARY_MAINTENANCE_REQUIRED`，客户端改用 `maintenance-draft` 和唯一 `maintenance-proposals` desired-state 写入口。客户端不提交 `write_mode`，服务端用 `boundary_state_fingerprint` 校验并发后自动形成 CREATE/REFERENCE/APPEND Proposal；Proposal 列表/读取/批准/拒绝继续复用，Approve body 只含预期 `proposal_fingerprint` 与 reason，审批身份和渠道固定为 `LOCAL_GUI`。没有 official recipe 普通路由、PATCH Proposal、旧 matrix cell writer 或自动 approve；应用候选决定不属于权限批准。current 响应只含精确匹配当前 ACTIVE Actor/Action revision 与 Effect catalog 的 latest ACTIVE Permission；历史 revision 仍由历史读取入口保存。

GUI 通过固定 loopback API 读取 envelope。当前工作区入口只有 `GET /api/projects/{project_id}/workspace`，旧 `/status` 返回 404。API 成功 envelope 使用根 `schema_version="1"` 与 `data`；异常由稳定 error code、trace 和有界 details 映射。API envelope 版本描述控制面机器格式，不是产品版本。

当前准备和权限由 PreparationService 与 BusinessBoundaryService 提供；旧 ProductStatus、Delivery 和 History 服务已移除，保留的旧准备/矩阵类型不构成当前写入口。

当前 GUI 与 projects API 不提供独立交付检查入口；Workspace 不产生交付结论。

## 应用候选批量决定

`PUT /api/projects/{project_id}/candidate-decisions` 复用 application-understanding 格式，命令根版本为 1，携带 understanding revision 和 1 至 256 个不重复候选决定。嵌套决定仅包含种类、候选引用、显示名称与决定，不另设版本。服务端先检查所有项，再在同一事务保存并只推进一次 revision；未知、重复、失效或非法候选使整批失败。MANUAL 候选不能转成系统 PROPOSED。成功后只更新理解与既有绑定刷新，不创建或批准权限。

回执不明先读当前理解，匹配新 revision 与全部决定才展示保存事实；旧 revision 不自动重放。Workspace journey 是嵌套只读位置投影，复用唯一 PrimaryTask，不建立任务表或新的裁判逻辑。首次存在有效待审候选且没有正式边界、未同时确认权限组和动作时，发布 REVIEW_APPLICATION_CANDIDATES。

## 当前 CHECK 历史与执行路径

`GET /api/projects/{project_id}/check-history` 只读当前 CHECK，保留原 `/runs` 列表契约。默认 limit 25、最大 50；query 最长 128，trim 后大小写不敏感的字面子串匹配 run_id 和已验证冻结动作名，可按 verdict/lifecycle 筛选。成对 cursor 使用 created_at_us 降序与 run_id 升序的严格 keyset，项目条件在 SQL 中限制；每次最多校验 250 条候选，返回最后实际扫描键之后的继续位置，只有后面仍有候选才提供 cursor。因此空 items 加非空 cursor 合法，不提供 total 或跨请求快照保证。INVALID 不使用数据库 Verdict、未知标签或上下文冒充已发布事实；NOT_PUBLISHED 原义保持。精确 DTO 由 `workflows/checks/results.py` 和自动代码参考维护。

`ActionResultStory.execution_path` 是同 Case 的只读嵌套投影，不写回发布包，不携带 schema_version。没有非空 Trace 或多个 Trace 冲突时为 null；相同 Trace 保留一份完整拓扑图，partial/空 partial 的 complete/reasons 原样保持。全部最多 512 个节点与显式 parent_event_ids 逐项复制，不按时间补边；文档引用只包含实际承载该 Trace 的 CheckEvidence ID，保序去重，不混用事件的其他来源引用。节点不包含时间、凭据、authority scope、semantic_key 或原始正文；字段真源为 `workflows/checks/story.py`。完整性错误仍传播，不能以空图吞错。

Workspace 的 active_check 只表示本项目最新 QUEUED/RUNNING，终态后为空不代表 PASS；source_change.submitted_by 直接复制登记来源。四个一级入口、会话保留、结果通知和局部证据区的详细消费职责见[前端模块](../../02_开发指南/模块/frontend.md)。这些读取不改变 PrimaryTask、修复合同或安全结论，也不恢复旧 History/Report writer。

## CLI Human 与 Machine

CLI 默认输出人类可读结果；`--json` 是唯一显式 Machine 模式。两种模式不会在同一个 stdout 中混写。`--var-dir` 只保留给源码启动、开发脚本和 Portable 的内部运行时接线，不出现在普通 help 或 README 中。

Human 先给结论、关键事实与下一步，隐藏内部 ID、reason code 和复杂结构。需要完整稳定结构时使用 Machine v1；诊断环境问题时使用 `system doctor`。Machine v1 成功对象固定包含：

```text
schema_version
kind
status
data
next_actions
warnings
```

失败对象使用 `kind=error` 并增加有界 `error`，其中保存稳定 `error_code`、trace、恢复建议和允许的结构化 details。Machine stdout 必须只有一个 JSON 对象；stderr 不混入 INFO、traceback 或人类提示。结构化脱敏日志单独进入当前 VarDir 的 logs。

CLI `--version` 直接输出 `product.backend.__version__` 并退出，它是产品版本查询，不使用 Machine envelope，也不创建 ApplicationCore。

CLI 与 Machine 输出是控制和投影通道，不是审批人。公开命令树不提供 PermissionIntent ALLOW/DENY 写入，也不提供角色/动作候选的确认、拒绝或手工创建；自动化只能准备既有事实、执行已冻结操作或读取结果。

普通命令当前只公开 `serve`、产品版本与 `system doctor/repair/clean`。`status`、`application`、`change`、`check`、`result` 和 `history` 在当前 暂不公开；Business Boundary 创建与 Proposal 决定只在 GUI/loopback Human API 完成，Agent 自动化不能取得审批能力。

## MCP Streamable HTTP 与工具输出

MCP精确挂载同一loopback FastAPI的/mcp，由官方SDK提供Streamable HTTP，不创建第二个ApplicationCore或端口。当前Worker支持CHECK与RECORDING，System/ready/MCP投影同一真实存活与能力事实；只有Worker running不能证明Plan可执行。长期Bearer只经精确SecretStore保存，启动恢复READ。

GUI 读取的 `MCPAccessView` 明确区分凭据与连接：`DISABLED → CREDENTIAL_READY → AUTHENTICATED → CONNECTED` 是正常建立过程，认证失败投影为 `CREDENTIAL_REJECTED`，人工暂停投影为 `PAUSED`。`last_authenticated_at_us` 只证明 Bearer 通过，`last_seen_at_us` 才代表 SDK 已观测到完成 initialize 的客户端活动；状态页面不能把凭据生成、配置复制或客户端自报当成连接成功。恢复、轮换、暂停和 shutdown 都清除旧活动与逐 Project 提升，避免上一客户端或上一 serve 冒充当前连接。

MCP工具按SDK返回structured content，不套API/CLI envelope；仅独立持久根有schema_version。当前提供有界事实、SourceChange和完整Check提交/取消，不开放Proposal决定、权限writer或任意执行。

长期配对只恢复READ。精确14工具：原7个Project/ApplicationUnderstanding/BusinessBoundary/Intent/Identity/System READ，加change_show/check_status/result_show/repair_show；change_submit为PREPARE，check_run/check_cancel为EXECUTE。GUI对当前项目临时提升，pause/resume/rotate/forget/close清除；令牌、状态和错误继续沿同一受控边界。未声明参数拒绝，不能选择Case/Permission/Effect、提交源码/diff、执行Git/shell/任意HTTP或写权限。

## ResultStory 与 Evidence

当前 ResultStory 从严格发布 Reader 读取冻结请求、Case 结果、证据和 Breakpoint，组织权限要求、实际身份、表面响应、真实业务结果、定位和原题复验。它只解释已有事实，不重新运行 Verification，也不让模型补写结论或定位。

ExecutionTrace 提供同 Run 的派发、授权和真实业务效果因果；只有已确认禁止效果的 Case 才进入 Breakpoint，缺少中间来源只降低定位精度。原题要求从已发布 BLOCK 重建，复验状态读取精确关联的 NEW Run，不能用最新普通结果冒充修复。

API evidence index 只返回已发布索引；完整 Evidence detail 是另一资源，索引与文档不能逐字比较。独立报告格式和保留的 ResultPresentation 底层实现不接入当前检查入口。格式投影边界见[报告与格式投影协议](报告与格式投影协议.md)。

## LocalControl 与 ServeLock

loopback 不等于自动可信。API 先校验实际 Host；GUI 根页面取得当前服务进程签发的 HttpOnly、SameSite=Strict control session；全部 `/api` 请求要求该会话，写请求再要求 Origin 与控制面 origin 完全一致。MCP 使用独立 Bearer 与 SDK Host/Origin 防护。代理头不能改变授权 Host，测试 header 不能变成生产旁路。

GUI serve 与会创建 ApplicationCore 的 CLI 命令共享 `ServeLock`。同一 VarDir 已有控制者时，第二入口在创建 ApplicationCore 前返回 `WORKSPACE_ALREADY_CONTROLLED`。锁文件是所有权记录，不是 daemon 或 IPC；持有者仍存活时不能靠删除文件绕过，进程正常/异常退出后必须可重新获取。

## 状态、错误与长时过程

控制面显示的状态必须来源明确：当前 Workspace/PrimaryTask 是动作工作区事实，Job/Run 表示生命周期，Runner progress 是非权威展示旁路，ResultStory 只投影经校验的发布结果。Workspace 的活动检查与最近结果摘要必须来自当前 Reader，不能从进度推算安全结论。

发生错误时先保留第一主错误及 trace，再执行正式 cleanup。cleanup warning 单独展示，不覆盖 primary failure。安全 BLOCK/INCONCLUSIVE 不是控制面执行错误，不能被 ErrorRecovery 当作异常页面。

## 查询入口

| 要查什么 | 当前真源 |
| --- | --- |
| WorkspaceView / PrimaryTask | `product/backend/workflows/workspace/` |
| API envelope 与 LocalControl | `product/backend/api/envelope.py`、`product/backend/api/local_control.py` |
| MCP transport、工具与授权 | `product/backend/api/mcp.py`、`product/backend/workflows/mcp_access.py` |
| CLI 命令与 Machine renderer | `product/backend/cli/app.py`、`product/backend/cli/presentation.py`、`product/backend/cli/commands/system.py` |
| 当前结果/执行路径/检查历史 | `product/backend/workflows/checks/story.py`、`product/backend/workflows/checks/results.py` |
| ServeLock 与 CLI bootstrap | `product/backend/infra/runtime/serve_lock.py`、`product/backend/cli/bootstrap.py` |
| GUI API/控制壳 | `product/frontend/src/api/`、`product/frontend/src/app/` |
| 直接测试 | `tests/backend/cli/test_current_cli.py`、`tests/backend/api/test_control_plane.py`、`tests/backend/api/test_mcp.py`、对应前端测试 |

## 版本边界

产品版本唯一真源是 `product/backend/__init__.py::__version__`。API/Machine/协议中的 `schema_version` 分别描述各自机器格式；PermissionContract 的 `version` 描述业务治理版本。这三者不能互相替代，也不因为产品补丁版本自动一起升级。

## 相关真源

- [产品入口与控制面](../../01_系统地图/产品入口与控制面.md)
- [修改 API 与控制面](../../02_开发指南/任务/修改API与控制面.md)
- [报告与格式投影协议](报告与格式投影协议.md)
- [产品入口与控制面边界 ADR](../../05_设计依据/ADR-0035-产品入口与控制面边界.md)
