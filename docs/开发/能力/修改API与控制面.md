# 修改 API 与控制面

> 状态：CURRENT。用于修改 loopback API、CLI/MCP 控制入口、ApplicationCore 接线、统一状态投影与本地单控制者边界。

## 这是什么

控制面把 GUI、CLI、MCP 和自动化请求翻译为同一 ApplicationCore 调用，再把已形成的产品事实投影给用户。它负责 transport、严格输入、LocalControl/MCP 授权、错误映射、生命周期接线和输出格式，但不负责执行目标请求，也不在路由或工具里重新判断权限安全。

当前 GUI 工作台只消费 `WorkspaceView`：`WorkspaceService` 组合 Project、ApplicationUnderstanding、Business Boundary、Permission、实时 implementation inspection 与 PreparationView，并按固定优先级生成唯一 `PrimaryTask`。当前结果由 CheckResultReader/CheckStoryBuilder 提供；旧 ProductStatus、Delivery 和 History 服务已移除，独立报告格式不属于当前控制面结果入口。

## 快速找到修改位置

| 要改什么 | 先看哪里 | 事实所有者或直接测试 |
| --- | --- | --- |
| FastAPI 组合、启动/关闭、Worker 生命周期 | `product/backend/api/app.py` | `tests/backend/api/test_control_plane.py` |
| 资源路由与 DTO 映射 | `product/backend/api/routers/` | `tests/backend/api/` |
| API envelope、异常与 trace | `product/backend/api/envelope.py`、`product/backend/api/errors.py` | `tests/backend/api/test_control_plane.py` |
| Host、session、Origin 控制 | `product/backend/api/local_control.py` | `tests/backend/api/test_control_plane.py` |
| MCP Streamable HTTP、固定工具白名单 | `product/backend/api/mcp.py` | `tests/backend/api/test_mcp.py` |
| Human GUI 权限草稿、审批与 Agent proposal 路由 | `product/backend/api/routers/permission_intents.py` | `tests/backend/api/test_business_boundaries.py`、权限草稿 API 测试 |
| MCP 长期配对与逐 Project 临时权限 | `product/backend/workflows/agent_access/service.py`、`product/backend/api/routers/mcp_access.py` | `tests/backend/api/test_mcp.py` |
| ApplicationCore 组合 | `product/backend/composition/application.py` | `tests/backend/composition/`、`tests/architecture/test_storage_composition.py` |
| Action Workspace、唯一 PrimaryTask 与动作级权限/实现摘要 | `product/backend/workflows/workspace/` | `tests/backend/workflows/workspace/test_service.py`、`tests/backend/api/test_workspace.py` |
| 普通 CLI 命令与 Machine 输出 | `product/backend/cli/app.py`、`product/backend/cli/commands/system.py`、`product/backend/cli/presentation.py` | `tests/backend/cli/test_current_cli.py` |
| 同一 VarDir 单控制者 | `product/backend/infra/runtime/serve_lock.py`、`product/backend/cli/bootstrap.py` | `tests/backend/api/test_control_plane.py`、`tests/backend/cli/test_current_cli.py` |

## 正常修改路线

先确定变化属于 transport 还是应用服务。只是新增查询或写入入口时，先在已有 workflow/application service 中确认唯一职责，再让 Router 完成 strict DTO 解析、调用和 envelope 映射。需要 GUI 与 CLI 同时展示的新事实，应先进入共享只读投影，再由两端分别做格式投影；不要先改页面或 CLI 字符串，再回填后端。

本地 API 固定绑定 IPv4 loopback。GUI 根页面取得当前服务进程的 HttpOnly、SameSite=Strict control session；所有 `/api` 请求验证 Host 与 session，写请求再验证精确 Origin。`X-Forwarded-*` 等代理头不能扩大授权。错误必须通过稳定 `ErrorCode`、有界 details 和 trace 映射；异常正文、环境变量和秘密值不能进入响应。

正式业务边界和权限写入只走普通business-boundaries Proposal approve/reject事务，LOCAL_GUI由服务端固定；自然语言permission-drafts只返回有限待审草稿，不写Proposal/Permission。修复、MCP、Runner和结果均不能成为审批者。

当前动作准备、TestIdentity、Recording与CHECK均经ApplicationCore。Job取消将CHECK交给同一CheckService.cancel，Recording仍按正式队列取消。SourceChange/Repair、check-preview及 HTTP 提交格式 2 的 runs 已装配（其持久冻结请求为 PersistedExecutionRequestV3）；旧preparation writer、ProductStatus和旧结果链不回接。

MCP使用官方Python SDK Streamable HTTP，精确挂载同一FastAPI的/mcp，不创建第二个ApplicationCore。SDK核验Host/Origin/DNS rebinding，transport只接受Bearer；配对随机令牌只在精确SecretStore引用保存。启动恢复READ，GUI可对当前项目临时提升PREPARE/EXECUTE，pause/resume/rotate/forget/close清除提升，长期凭据与当前会话分开。

`MCPAccessView.connection_state` 是 GUI 的唯一连接阶段事实：`DISABLED` 表示尚无凭据，`CREDENTIAL_READY` 表示凭据已创建但尚未观测到客户端，`AUTHENTICATED` 表示 Bearer 已通过但 SDK 尚未成功处理 MCP 请求，`CONNECTED` 在 SDK 成功处理任一请求后成立，`CREDENTIAL_REJECTED` 表示最近一次认证失败，`PAUSED` 表示当前 serve 不接受连接。Streamable HTTP保留标准初始化会话，后续请求从同一会话读取客户端名称和版本；Bearer与项目授权仍逐请求核验，会话ID不代表授权。未声明客户端信息时只显示已验证连接，不猜测名称。创建凭据、复制配置或客户端自称已保存都不能提前显示“连接成功”；恢复连接清除旧活动和临时提升后回到 `CREDENTIAL_READY`。

唯一连接页提供 Codex、DeepSeek Harness（DSH）、ZCode 三种指导，使用“准备连接 → 配置客户端 → 验证与授权”三阶段。地址取当前服务返回的 endpoint，不固定端口。配置预览不含秘密，凭据由用户单独复制；Codex/DSH 使用用户级环境变量，ZCode 在本机 Headers 填写 Bearer。步骤来源见 `features/tools/clientGuides.ts` 官方链接；DSH/ZCode 尚未实机验收须明确标记。

教程选择与实际客户端身份独立；旧客户端名称如实展示，不因主引导调整而强行断开。界面使用“连接已验证/最近活动”，不表示实时在线或正在编码。管理连接为页内区域，凭据更新/删除只作最后一次确认；所有客户端共享现有凭据和授权，不能声称支持逐客户端撤权。

MCP instructions明确READ读取事实、PREPARE登记变化声明、EXECUTE运行完整当前权限或取消本项目检查，遇到人类决定返回GUI。基线跨用户任务保存；复制内容不含Bearer正文，也不要求把秘密发进对话。

每个MCP工具先统一连接认证，再按项目require授权。当前34工具：原有11个READ，加task_list/task_show/task_context/receipt_show四个READ；task_create/task_accept/change_submit为PREPARE，check_run/check_cancel为EXECUTE。另有rule_context、rule_candidate_show、rule_operation三个READ和rule_candidate_save一个PREPARE，候选不写正式权限；变化登记预览和一次登记分别沿已有READ/PREPARE边界。任务修订、结束与取消只由GUI执行。未声明参数按公开schema拒绝；不提供选Case/Effect/Permission、approval、任意路径/HTTP/shell或原始Evidence/Trace。错误沿既有MCP_DISABLED/MCP_AUTH_REQUIRED/MCP_PERMISSION_REQUIRED映射，不暴露输入秘密。

Machine 输出是 CLI 的稳定自动化表面，成功 envelope 固定为 `schema_version/kind/status/data/next_actions/warnings`，失败增加有界 `error`。默认 Human 只给结论与下一步，只有显式 `--json` 才进入 Machine 模式；两种输出都来自同一产品事实。更完整的关系见[控制面与 Machine 输出协议](../../参考/协议/控制面与Machine输出协议.md)。

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
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File .\scripts\dev.ps1 test tests/backend/api/test_control_plane.py tests/backend/cli/test_current_cli.py
```

只改一个资源 Router 时不要机械运行整组控制面。改 Machine envelope、ServeLock、启动/关闭或 ApplicationCore 组合时，必须覆盖 CLI/API 同事实、错误通道与单控制者。改 OpenAPI DTO 后再运行 schema/docs 检查；只有入口跨进程行为变化才增加少量 E2E。

MCP 变化使用官方 SDK 客户端直接验证未配对、错误/旧令牌、Host/Origin、精确当前 34 工具及其授权层级、暂停/轮换/忘记、跨启动配对恢复、非秘密投影和唯一 ApplicationCore；同时验证启动默认 READ、逐项目临时提升及审批隔离；检查提交/取消只调用当前 ApplicationCore，不暴露旧结果服务或任意 HTTP/shell。测试不得通过手写 JSON-RPC 代替 SDK 集成证据。

## 失败先查哪里

出现 403 先区分 Host、control session 和 Origin，不要立即放宽 LocalControl。GUI 与 CLI 不一致先比较它们读取的 workflow 投影是否相同，再检查 renderer；不要让两端互相抄输出。服务 ready 但页面打不开，先看 `/ready`、前端入口和浏览器打开诊断，不把三者合成一个错误。第二控制者错误先查 ServeLock 对应 VarDir 和真实持有者，禁止靠删除锁文件绕过仍存活的进程。

## 相关真源

- [产品入口与控制面](../../架构/产品入口与控制面.md)
- [控制面与 Machine 输出协议](../../参考/协议/控制面与Machine输出协议.md)
- [修改 Agent 变更影响](修改Agent变更影响.md)
- [工程设计](../../约束/工程设计.md)
- [验证与测试](../验证.md)

## 普通运行入口

项目 `/controlled-runtime` 路由提供只读状态与原操作查询，`preview` 经显式源码读取授权生成有限入口/端口/冻结文件预览，`start` 核对预览指纹和稳定操作键后只提交持久 Job，`stop` 只停止当前空闲且归属确定的实例。首次源码读取可先于应用地址连通；它不授予目标访问或执行权限。仍须另行确认启动与被检查地址。

交付页的加载沿用已确认入口与端口，交付回执和运行 Job 在同一事务中形成。响应未知时查询原操作，不能产生另一份加载。API 不运行 Node；目标执行始终由固定 Runtime Worker 承担。普通运行暂限无外部依赖的受控 `.mjs` 静态模块，不接受自由命令、任意环境变量或自行指定解释器。

## 人工补充材料的写入边界

动作级 `supplemental-materials` 路由由 `SupplementalMaterialService` 统一校验和保存。preview 只读；create 绑定 expected_fingerprint 与 UUID request_id；revisions 仅追加说明，withdraw 追加撤回修订。请求 ID 按项目唯一绑定操作、目标和内容，冲突拒绝。所有项目/动作/修订精确核对，新登记必须匹配当前正式动作修订。

导入根 schema_version=1 仅允许项目/动作/动作修订、标题/来源/可选声明资源及1～100条时间/资源/事件记录，UTF-8 canonical 最多64KiB，拒绝额外字段和典型秘密。格式接受不证明真实性；association_status 仅 USER_DECLARED 或 UNCONFIRMED，usage 固定 SUPPLEMENTAL_ONLY。无路径读取、URL采集或脚本执行入口；材料不进入 MCP、Evidence、准备完整性、Plan 或 Verdict。每次列表及修订历史读取最多100项，显式 limit/has_more，不伪造总量；修订历史用正整数 before_revision 继续读取更早记录。直接测试为 `tests/backend/workflows/test_supplemental_materials.py`。

## 普通来源准备工具

新增 preparation_context、proof_source_show、proof_preflight_status、proof_adoption_preview、preparation_receipt 五个 READ；proof_source_save 为 PREPARE；proof_preflight_start/cancel 为 EXECUTE。来源只接受固定 JSON GET、账号/资源引用与有界字段映射，不接受任意 URL、SQL、代码、密码或可信性布尔值。读取范围和采用只由本机会话与同源 GUI 写入。预检查是独立 Job，成功生命周期与 USABLE、正式权限 Verdict 分别表达。

MCP EXECUTE 授权代次绑定每次预检查；降权、暂停、轮换、忘记和控制进程重启使旧任务失效。重新授权不会复活旧 Job。写操作按原操作标识回读；来源修订采用 CAS。
