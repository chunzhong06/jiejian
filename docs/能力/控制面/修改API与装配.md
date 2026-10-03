# 修改 API 与控制面

> 状态：CURRENT。用于修改 loopback API、CLI/MCP 控制入口、ApplicationCore 接线、统一状态投影与本地单控制者边界。

## 这是什么

控制面把 GUI、CLI、MCP 和自动化请求翻译为同一 ApplicationCore 调用，再把已形成的产品事实投影给用户。它负责 transport、严格输入、LocalControl/MCP 授权、错误映射、生命周期接线和输出格式，但不负责执行目标请求，也不在路由或工具里重新判断权限安全。

工作台的读取与主任务选择见[工作台指南](修改工作台与任务.md)，MCP授权与工具见[MCP指南](修改MCP与授权.md)。

## 快速找到修改位置

| 要改什么 | 先看哪里 | 事实所有者或直接测试 |
| --- | --- | --- |
| FastAPI 组合、启动/关闭、Worker 生命周期 | `product/backend/api/app.py` | `tests/backend/api/system/test_control_plane.py` |
| 资源路由与 DTO 映射 | `product/backend/api/routers/` | `tests/backend/api/` |
| API envelope、异常与 trace | `product/backend/api/envelope.py`、`product/backend/api/errors.py` | `tests/backend/api/system/test_control_plane.py` |
| Host、session、Origin 控制 | `product/backend/api/local_control.py` | `tests/backend/api/system/test_control_plane.py` |
| MCP Streamable HTTP、固定工具白名单 | `product/backend/api/mcp/server.py` | `tests/backend/api/system/test_mcp.py` |
| Human GUI 权限草稿、审批与 Agent proposal 路由 | `product/backend/api/routers/boundaries/permission_intents.py` | `tests/backend/api/boundaries/test_business_boundaries.py`、权限草稿 API 测试 |
| MCP 长期配对与逐 Project 临时权限 | `product/backend/workflows/agent_access/service.py`、`product/backend/api/routers/system/mcp_access.py` | `tests/backend/api/system/test_mcp.py` |
| ApplicationCore 组合 | `product/backend/composition/application.py` | `tests/backend/composition/`、`tests/architecture/test_storage_composition.py` |
| Action Workspace、唯一 PrimaryTask 与动作级权限/实现摘要 | `product/backend/workflows/workspace/` | `tests/backend/workflows/workspace/test_service.py`、`tests/backend/api/test_workspace.py` |
| 普通 CLI 命令与 Machine 输出 | `product/backend/cli/app.py`、`product/backend/cli/commands/system.py`、`product/backend/cli/presentation.py` | `tests/backend/cli/test_current_cli.py` |
| 同一 VarDir 单控制者 | `product/backend/infra/runtime/serve_lock.py`、`product/backend/cli/bootstrap.py` | `tests/backend/api/system/test_control_plane.py`、`tests/backend/cli/test_current_cli.py` |

## 正常修改路线

ApplicationCore 对无环依赖使用构造注入；变化/原题、运行提供方和交付关联使用具名连接方法，最后只检查生产所需连接，不执行回调。MCP 撤权回调在控制器构造时传入，证明准备的授权查询由控制面明确连接。连接整理不得改变原 UoW、关闭顺序或失败后保留资源的条件。

MCP 的工具注册入口仍为 `product/backend/api/mcp/server.py`；`mcp/errors.py` 统一分级授权与净化错误，`mcp/transport.py` 处理 Bearer 和 ASGI 挂载，`mcp/views.py` 维护给 Agent 的有限事实投影。修改工具业务先核对原 workflow，不能在投影或传输模块执行事务。

先确定变化属于 transport 还是应用服务。只是新增查询或写入入口时，先在已有 workflow/application service 中确认唯一职责，再让 Router 完成 strict DTO 解析、调用和 envelope 映射。需要 GUI 与 CLI 同时展示的新事实，应先进入共享只读投影，再由两端分别做格式投影；不要先改页面或 CLI 字符串，再回填后端。

本地 API 固定绑定 IPv4 loopback。GUI 根页面取得当前服务进程的 HttpOnly、SameSite=Strict control session；所有 `/api` 请求验证 Host 与 session，写请求再验证精确 Origin。`X-Forwarded-*` 等代理头不能扩大授权。错误必须通过稳定 `ErrorCode`、有界 details 和 trace 映射；异常正文、环境变量和秘密值不能进入响应。

正式业务边界和权限写入只走普通business-boundaries Proposal approve/reject事务，LOCAL_GUI由服务端固定；自然语言permission-drafts只返回有限待审草稿，不写Proposal/Permission。修复、MCP、Runner和结果均不能成为审批者。

当前动作准备、TestIdentity、Recording与CHECK均经ApplicationCore。Job取消将CHECK交给同一CheckService.cancel，Recording仍按正式队列取消。SourceChange/Repair、check-preview及 HTTP 提交格式 2 的 runs 已装配（其持久冻结请求为 PersistedExecutionRequestV3）；旧preparation writer、ProductStatus和旧结果链不回接。

MCP挂载同一个ApplicationCore，工具、会话、分级授权和恢复由[MCP与授权](修改MCP与授权.md)集中说明。精确注册见[注册参考](../../参考/生成/注册与格式.md)。

Machine 输出是 CLI 的稳定自动化表面，成功 envelope 固定为 `schema_version/kind/status/data/next_actions/warnings`，失败增加有界 `error`。默认 Human 只给结论与下一步，只有显式 `--json` 才进入 Machine 模式；两种输出都来自同一产品事实。更完整的关系见[控制面与 Machine 输出协议](控制面与Machine输出协议.md)。

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
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File .\scripts\dev.ps1 test tests/backend/api/system/test_control_plane.py tests/backend/cli/test_current_cli.py
```

只改一个资源 Router 时不要机械运行整组控制面。改 Machine envelope、ServeLock、启动/关闭或 ApplicationCore 组合时，必须覆盖 CLI/API 同事实、错误通道与单控制者。改 OpenAPI DTO 后再运行 schema/docs 检查；只有入口跨进程行为变化才增加少量 E2E。

MCP 变化使用官方 SDK 客户端直接验证未配对、错误/旧令牌、Host/Origin、精确当前 34 工具及其授权层级、暂停/轮换/忘记、跨启动配对恢复、非秘密投影和唯一 ApplicationCore；同时验证启动默认 READ、逐项目临时提升及审批隔离；检查提交/取消只调用当前 ApplicationCore，不暴露旧结果服务或任意 HTTP/shell。测试不得通过手写 JSON-RPC 代替 SDK 集成证据。

## 失败先查哪里

出现 403 先区分 Host、control session 和 Origin，不要立即放宽 LocalControl。GUI 与 CLI 不一致先比较它们读取的 workflow 投影是否相同，再检查 renderer；不要让两端互相抄输出。服务 ready 但页面打不开，先看 `/ready`、前端入口和浏览器打开诊断，不把三者合成一个错误。第二控制者错误先查 ServeLock 对应 VarDir 和真实持有者，禁止靠删除锁文件绕过仍存活的进程。

## 相关真源

- [产品入口与控制面](控制面与装配.md)
- [控制面与 Machine 输出协议](控制面与Machine输出协议.md)
- [修改 Agent 变更影响](../结果与变化/修改变化登记与交付.md)
- [工程设计](../../工程/规则/工程设计.md)
- [验证与测试](../../工程/验证.md)

## 专属能力的入口合同

普通运行调用[运行加载](../应用接入/修改运行加载.md)，补充材料调用[材料服务](../账号与材料/协议/材料与恢复契约.md)，证明预检查与采用调用[来源服务](../证明来源/证明来源契约.md)。Router只做严格解析、当前入口授权和输出转换；不能复制这些workflow事务。
