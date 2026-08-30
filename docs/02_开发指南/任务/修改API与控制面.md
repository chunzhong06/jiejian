# 修改 API 与控制面

> 状态：CURRENT。用于修改 loopback API、CLI/MCP 控制入口、ApplicationCore 接线、统一状态投影与本地单控制者边界。

## 这是什么

控制面把 GUI、CLI、MCP 和自动化请求翻译为同一 ApplicationCore 调用，再把已形成的产品事实投影给用户。它负责 transport、严格输入、LocalControl/MCP 授权、错误映射、生命周期接线和输出格式，但不负责执行目标请求，也不在路由或工具里重新判断权限安全。

`ProductStatus`、`ProjectReadiness`、`ResultPresentation` 和 `HistoryView` 分别拥有工作台状态、准备度、单次结果与历史变化。API 和 CLI 只能消费这些事实；页面、命令或 Router 不能各自保存另一套进度。Worker 使用独立 `WorkerContainer`，高风险 Web 请求只在 Worker/Runner 中产生。

## 快速找到修改位置

| 要改什么 | 先看哪里 | 事实所有者或直接测试 |
| --- | --- | --- |
| FastAPI 组合、启动/关闭、Worker 生命周期 | `product/backend/api/app.py` | `tests/backend/api/test_control_plane.py` |
| 资源路由与 DTO 映射 | `product/backend/api/routers/` | `tests/backend/api/` |
| API envelope、异常与 trace | `product/backend/api/envelope.py`、`product/backend/api/errors.py` | `tests/backend/api/test_control_plane.py` |
| Host、session、Origin 控制 | `product/backend/api/local_control.py` | `tests/backend/api/test_control_plane.py` |
| MCP Streamable HTTP、固定工具白名单 | `product/backend/api/mcp.py` | `tests/backend/api/test_mcp.py` |
| Human GUI 权限审批与 Agent proposal 路由 | `product/backend/api/routers/permission_intents.py` | `tests/backend/api/test_permission_intent_human_approval.py` |
| MCP 长期配对与逐 Project 临时权限 | `product/backend/workflows/mcp_access.py`、`product/backend/api/routers/mcp_access.py` | `tests/backend/api/test_mcp.py` |
| ApplicationCore 组合 | `product/backend/workflows/context.py` | `tests/backend/workflows/` |
| ProductStatus 与唯一下一步 | `product/backend/workflows/control.py` | `tests/backend/workflows/control/test_status.py` |
| 普通 CLI 命令与 Machine 输出 | `product/backend/cli/app.py`、`product/backend/cli/commands/control.py`、`product/backend/cli/presentation.py` | `tests/backend/cli/test_control.py` |
| 同一 VarDir 单控制者 | `product/backend/infra/runtime/serve_lock.py`、`product/backend/cli/bootstrap.py` | `tests/backend/api/test_control_plane.py`、`tests/backend/cli/test_control.py` |

## 正常修改路线

先确定变化属于 transport 还是应用服务。只是新增查询或写入入口时，先在已有 workflow/application service 中确认唯一职责，再让 Router 完成 strict DTO 解析、调用和 envelope 映射。需要 GUI 与 CLI 同时展示的新事实，应先进入共享只读投影，再由两端分别做格式投影；不要先改页面或 CLI 字符串，再回填后端。

本地 API 固定绑定 IPv4 loopback。GUI 根页面取得当前服务进程的 HttpOnly、SameSite=Strict control session；所有 `/api` 请求验证 Host 与 session，写请求再验证精确 Origin。`X-Forwarded-*` 等代理头不能扩大授权。错误必须通过稳定 `ErrorCode`、有界 details 和 trace 映射；异常正文、环境变量和秘密值不能进入响应。

权限意图写入只走 `POST /api/projects/{project_id}/permission-intents/approvals` 和 proposal approve/reject。审批 body 不接受自由 actor，Router 只做严格 DTO 映射，正式 revision/binding/epoch 事务由 `PermissionIntentService` 拥有。对已有 cell 选择未确认必须追加 RETIRED revision，不能删除历史。对应交互和 Oracle 边界见[修改权限意图与 Agent 授权](修改权限意图与Agent授权.md)。

MCP 使用官方 Python SDK v2 的 Streamable HTTP，精确挂载在同一 FastAPI 服务的 `/mcp`，不提供 SSE 兼容入口，不创建第二个服务或 ApplicationCore。SDK 自身启用 Host/Origin 与 DNS rebinding 防护；transport 只接受当前配对 Bearer，不能使用 GUI control session Cookie。首次配对或轮换生成至少 256-bit 随机令牌，并只通过 `cred:jiejian/mcp-control/pairing` 的精确 SecretStore 操作保存；普通 status 永不返回正文。启动存在配对时自动恢复 READ，PREPARE/EXECUTE 只驻留当前 serve。暂停或 shutdown 清除活动会话与提升但保留配对，轮换替换旧令牌并清除提升，忘记连接才删除长期配对。

唯一连接向导位于 GUI“AI 工具连接（MCP）”：Codex 使用 server name `jiejian`、`http://127.0.0.1:8765/mcp` 和 `JIEJIAN_MCP_TOKEN`；DSH 使用 `@deepseek-ai/dsh-mcp-client` 的 `streamable-http`，Authorization 从 `process.env.JIEJIAN_MCP_TOKEN` 取得。首次配置后客户端可随界鉴自动重连；轮换只更新该环境变量并重启客户端进程，不重复添加 server。

每个工具必须经过统一 `require_mcp_level`。`READ` 只返回现有 Pydantic View 或有界轻量投影；`PREPARE` 只能重分析已授权应用、准备身份或检查条件，不能新选目录、首次授权、修改 PermissionIntent 或决定角色/动作候选；`EXECUTE` 只启动、停止或取消已经冻结的受控操作。权限意图白名单固定为 READ 的 `jiejian_intent_list/show` 和 PREPARE 的 `jiejian_intent_propose/rebind_propose`，proposal 不修改 revision、hash 或 epoch。代码变化白名单为 PREPARE 的 `jiejian_change_submit` 和 READ 的 `jiejian_change_show`；`jiejian_check_prepare/run` 只增加可选 `change_id`，不能接收权限、Case、Effect、Profile 或文件范围。任何 level 都不能提供 permission_set、candidate_decide、approve 或 reject。白名单不得扩展为 shell、任意 HTTP、任意路径、秘密、请求正文、完整日志或完整 Evidence。访问失败稳定映射为 `MCP_DISABLED`、`MCP_AUTH_REQUIRED`、`MCP_PERMISSION_REQUIRED`，权限不足 details 只包含 `required_level/project_id`。

Machine 输出是 CLI 的稳定自动化表面，成功 envelope 固定为 `schema_version/kind/status/data/next_actions/warnings`，失败增加有界 `error`。默认 Human 只给结论与下一步，只有显式 `--json` 才进入 Machine 模式；两种输出都来自同一产品事实。更完整的关系见[控制面与 Machine 输出协议](../../03_参考手册/协议/控制面与Machine输出协议.md)。

## 不能破坏

- API 与 CLI 不直接导入 Web adapter、Observer 或 Runner executor；目标流量不能在控制面进程产生。
- Router 不复制 workflow 事务，不自行写 Verdict、Finding、Gate、Readiness 或 ResultPresentation。
- API `schema_version` 描述机器 envelope；嵌套 DTO 不重复根版本，产品版本也不能冒充 Schema 版本。
- 同一 VarDir 只能有一个控制者。已有 GUI/CLI 持有 ServeLock 时，第二个入口必须在创建 ApplicationCore 前失败。
- GET 不产生供应商调用、目标请求或隐式写入；需要副作用的操作使用明确写端点和幂等/确认边界。
- `/health`、`/ready`、系统状态和业务状态各司其职；浏览器自动打开失败不能被解释为服务未 ready。
- MCP 是 Web 产品的控制入口，不是 `MCP_AGENT` Target；高风险动作仍通过共享 Worker/Runner，工具不能旁路检查主链。
- CLI、Machine 与 MCP 都不是权限审批人；不得增加直接修改 ALLOW/DENY、确认/拒绝正式实现映射或降低受保护效果的入口。
- MCP 的 claimed paths 只是有界线索；真实变化、影响分类和重验计划必须由 `SourceChangeService` 形成。读取投影只允许返回授权源码根下的 claimed/added/modified/removed 相对路径，不得返回绝对路径、hash、diff 或正文。

## 怎么验证

优先运行受影响 Router 的直接测试，再按变化补以下最小邻域：

```powershell
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File .\scripts\dev.ps1 test tests/backend/api/test_control_plane.py tests/backend/cli/test_control.py
```

只改一个资源 Router 时不要机械运行整组控制面。改 Machine envelope、ServeLock、启动/关闭或 ApplicationCore 组合时，必须覆盖 CLI/API 同事实、错误通道与单控制者。改 OpenAPI DTO 后再运行 schema/docs 检查；只有入口跨进程行为变化才增加少量 E2E。

MCP 变化使用官方 SDK 客户端直接验证未配对、错误/旧令牌、Host/Origin、精确工具白名单、READ 同一 ProductStatus/ResultPresentation、逐 Project 临时提权、暂停/轮换/忘记、跨启动配对恢复、shutdown 后提升清空、非秘密投影和唯一 ApplicationCore。测试不得通过手写 JSON-RPC 代替 SDK 集成证据。

## 失败先查哪里

出现 403 先区分 Host、control session 和 Origin，不要立即放宽 LocalControl。GUI 与 CLI 不一致先比较它们读取的 workflow 投影是否相同，再检查 renderer；不要让两端互相抄输出。服务 ready 但页面打不开，先看 `/ready`、前端入口和浏览器打开诊断，不把三者合成一个错误。第二控制者错误先查 ServeLock 对应 VarDir 和真实持有者，禁止靠删除锁文件绕过仍存活的进程。

## 相关真源

- [产品入口与控制面](../../01_系统地图/产品入口与控制面.md)
- [控制面与 Machine 输出协议](../../03_参考手册/协议/控制面与Machine输出协议.md)
- [修改 Agent 变更影响](修改Agent变更影响.md)
- [工程设计](../../04_工程约束/工程设计.md)
- [验证与测试](../../04_工程约束/验证与测试.md)
