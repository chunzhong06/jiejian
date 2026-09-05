# 控制面与 Machine 输出协议

> 状态：CURRENT。本文解释 GUI、CLI Human、Machine v1、API envelope、MCP 工具与同一产品事实的关系；字段以当前代码和直接测试为准。

## 先理解：多个入口只有一套产品状态

界鉴可以从 GUI、CLI 或自动化脚本进入，但这些入口不能各自维护业务进度。当前 GUI 状态由 `WorkspaceService` 从 Project、ApplicationUnderstanding、正式 Business Boundary、Permission、pending Proposal、实时 implementation inspection 与 PreparationView 形成；保留的已发布结果读取仍由 `ResultPresentation` 负责，但完整新检查主链尚未重新接入当前产品入口。

```text
ApplicationCore / Published facts
  → WorkspaceView / BusinessBoundaryView
  → loopback API envelope → GUI
  → CLI Human / Machine v1
  → MCP Streamable HTTP → 固定工具白名单
  → 保留的 ResultPresentation / Report publication（只读已发布事实）
```

页面文案、终端颜色或 JSON 格式都不能反向改变事实。Report 是独立不可变交付物，也不由 CLI stdout 代替。

## WorkspaceView 与 GUI

使用独立 `WorkspaceView` 作为 GUI 唯一工作区 DTO。它包含当前项目与连接、Actor/Action 动作级视图、current Permission、实时 implementation inspection、四个长期区域，以及服务端按固定优先级选出的唯一 `PrimaryTask`。稳定 task ID 与 stale fingerprint 由服务端事实生成；前端不得重算优先级、binding currentness 或权限状态。

Business Boundary API 位于 `/api/projects/{project_id}/business-boundaries`。无正式边界时，`preview` 与首次 Proposal create 建立稳定 identity；已有边界后，普通 create 返回 `BOUNDARY_MAINTENANCE_REQUIRED`，客户端改用 `maintenance-draft` 和唯一 `maintenance-proposals` desired-state 写入口。客户端不提交 `write_mode`，服务端用 `boundary_state_fingerprint` 校验并发后自动形成 CREATE/REFERENCE/APPEND Proposal；Proposal 列表/读取/批准/拒绝继续复用，Approve body 只含预期 `proposal_fingerprint` 与 reason，审批身份和渠道固定为 `LOCAL_GUI`。没有 official recipe 普通路由、PATCH Proposal、旧 matrix cell writer、candidate decide 或自动 approve。current 响应只含精确匹配当前 ACTIVE Actor/Action revision 与 Effect catalog 的 latest ACTIVE Permission；历史 revision 仍由历史读取入口保存。

GUI 通过固定 loopback API 读取 envelope。当前工作区入口只有 `GET /api/projects/{project_id}/workspace`，旧 `/status` 返回 404。API 成功 envelope 使用根 `schema_version="1"` 与 `data`；异常由稳定 error code、trace 和有界 details 映射。API envelope 版本描述控制面机器格式，不是产品版本。

保留的 `ProductStatus`、`ProjectReadiness`、`ProjectPreparation`、权限矩阵和 CheckPreview DTO 不属于 current 写链。GUI 不得因为这些类型仍存在就重新注册旧权限审批或检查入口。

Delivery Check 在 当前 GUI 与 projects API 明确不可用；不得用旧服务查询结果替代 Workspace 或伪造本版可交付结论。

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

MCP 精确挂载在同一 loopback FastAPI 服务的 `/mcp`，由官方 Python SDK v2 提供 Streamable HTTP；不保留 SSE 路由，也不创建第二个 ApplicationCore、Worker 或监听端口。当前只装配录制 Worker；System、`/ready` 与 `jiejian_system_status` 共享真实 `worker`、`worker_capabilities`、检查可用性和恢复计数。只有实际线程存活且仅录制能力装配才报告 running；CHECK 不可用。首次创建的 Authorization Bearer 只经精确 SecretStore 引用长期保存，后续启动自动恢复 READ。

GUI 读取的 `MCPAccessView` 明确区分凭据与连接：`DISABLED → CREDENTIAL_READY → AUTHENTICATED → CONNECTED` 是正常建立过程，认证失败投影为 `CREDENTIAL_REJECTED`，人工暂停投影为 `PAUSED`。`last_authenticated_at_us` 只证明 Bearer 通过，`last_seen_at_us` 才代表 SDK 已观测到完成 initialize 的客户端活动；状态页面不能把凭据生成、配置复制或客户端自报当成连接成功。恢复、轮换、暂停和 shutdown 都清除旧活动与逐 Project 提升，避免上一客户端或上一 serve 冒充当前连接。

MCP 工具不套用 API envelope 或 CLI Machine envelope，而按 SDK 协议返回现有 Pydantic View 的 structured content 或有界轻量投影。根 View 自身已有 `schema_version` 时保持原值；不能为每个嵌套 DTO 重复制造版本，也不能把 MCP 协议版本当作产品版本。当前 MCP 不暴露 Workspace 写操作、Proposal 决定或执行能力。

长期配对只恢复 `READ`，current 工具白名单固定为 Project、ApplicationUnderstanding、Business Boundary、Intent、TestIdentity 与 System 的只读查询；`PREPARE / EXECUTE`、repair、change submit/show 与 check prepare/run 均未装配。工具清单也不含 permission_set、candidate_decide、approve 或 reject，不能接收源码正文、diff、Git 命令、补丁建议或客户端自报权限范围。暂停和 shutdown 撤销活动会话但保留配对；轮换立即废止旧令牌并保存新令牌；忘记连接删除配对。普通状态不返回明文令牌，访问边界只使用 `MCP_DISABLED`、`MCP_AUTH_REQUIRED`、`MCP_PERMISSION_REQUIRED` 三个稳定错误；权限不足 details 只允许 `required_level` 和 `project_id`。未来恢复更高 level 时必须另行扩展正式协议与验收，不能依赖现有保留代码自行生效。

## ResultPresentation 与 Evidence

`ResultPresentation` 回答“谁对什么执行了什么、预期是什么、表面请求怎样、真实对象怎样、为何形成结论”。它可以把冻结 EffectBinding 与实际 Observation 投影为 KEY/SUPPORTING、FOUND/NOT_FOUND/UNAVAILABLE，也可以从冻结请求投影变化重验标记和必需权限摘要，但不能重算 Verification 或显示源码指纹。

`ResultPresentation.execution_traces` 从冻结 request snapshot 与已发布 Evidence 还原每个 Case/Action 的实际事件 DAG。它可以表达入口 subject、实际 actor、权限 decision、后台代表关系和最终产物；缺少关键来源时只发布已有节点并标记 partial。GUI、CLI 或 MCP 只能投影这些节点，不能借事件顺序产生新的安全结论。

API evidence index 只返回已发布索引；完整 Evidence detail 是另一资源。索引与文档不能逐字比较，CLI 也不为方便展示复制整份 Evidence。报告投影关系见[报告与格式投影协议](报告与格式投影协议.md)。

## LocalControl 与 ServeLock

loopback 不等于自动可信。API 先校验实际 Host；GUI 根页面取得当前服务进程签发的 HttpOnly、SameSite=Strict control session；全部 `/api` 请求要求该会话，写请求再要求 Origin 与控制面 origin 完全一致。MCP 使用独立 Bearer 与 SDK Host/Origin 防护。代理头不能改变授权 Host，测试 header 不能变成生产旁路。

GUI serve 与会创建 ApplicationCore 的 CLI 命令共享 `ServeLock`。同一 VarDir 已有控制者时，第二入口在创建 ApplicationCore 前返回 `WORKSPACE_ALREADY_CONTROLLED`。锁文件是所有权记录，不是 daemon 或 IPC；持有者仍存活时不能靠删除文件绕过，进程正常/异常退出后必须可重新获取。

## 状态、错误与长时过程

控制面显示的状态必须来源明确：当前 Workspace/PrimaryTask 是动作工作区事实，Job/Run 是保留生命周期，Runner progress 是非权威展示旁路，ResultPresentation 是已发布结果。当前页面不能把后三者接回 Workspace 或伪造最近可信结果。

发生错误时先保留第一主错误及 trace，再执行正式 cleanup。cleanup warning 单独展示，不覆盖 primary failure。安全 BLOCK/INCONCLUSIVE 不是控制面执行错误，不能被 ErrorRecovery 当作异常页面。

## 查询入口

| 要查什么 | 当前真源 |
| --- | --- |
| WorkspaceView / PrimaryTask | `product/backend/workflows/workspace/` |
| API envelope 与 LocalControl | `product/backend/api/envelope.py`、`product/backend/api/local_control.py` |
| MCP transport、工具与授权 | `product/backend/api/mcp.py`、`product/backend/workflows/mcp_access.py` |
| CLI 命令与 Machine renderer | `product/backend/cli/app.py`、`product/backend/cli/presentation.py`、`product/backend/cli/commands/control.py` |
| ResultPresentation/ExecutionTrace/History | `product/backend/workflows/results/presentation/`、`product/backend/workflows/results/trace.py`、`product/backend/workflows/results/history.py` |
| ServeLock 与 CLI bootstrap | `product/backend/infra/runtime/serve_lock.py`、`product/backend/cli/bootstrap.py` |
| GUI API/控制壳 | `product/frontend/src/api/`、`product/frontend/src/app/` |
| 直接测试 | `tests/backend/cli/test_control.py`、`tests/backend/api/test_control_plane.py`、`tests/backend/api/test_mcp.py`、对应前端测试 |

## 版本边界

产品版本唯一真源是 `product/backend/__init__.py::__version__`。API/Machine/协议中的 `schema_version` 分别描述各自机器格式；PermissionContract 的 `version` 描述业务治理版本。这三者不能互相替代，也不因为产品补丁版本自动一起升级。

## 相关真源

- [产品入口与控制面](../../01_系统地图/产品入口与控制面.md)
- [修改 API 与控制面](../../02_开发指南/任务/修改API与控制面.md)
- [报告与格式投影协议](报告与格式投影协议.md)
- [产品入口与控制面边界 ADR](../../05_设计依据/ADR-0035-产品入口与控制面边界.md)
