# 控制面与 Machine 输出协议

> 状态：CURRENT。本文解释 GUI、CLI Human/Verbose、Machine v1、API envelope、MCP 工具与同一产品事实的关系；字段以当前代码和直接测试为准。

## 先理解：多个入口只有一套产品状态

界鉴可以从 GUI、CLI 或自动化脚本进入，但这些入口不能各自维护业务进度。`ProductStatusService` 从 Project、Readiness、活动 Job/Run 和最近可信结果形成统一工作台状态；GUI 与 CLI `status` 都消费这份投影。检查完成后，`ResultPresentation` 从已发布 Run/Evidence/Finding 形成可读结果；GUI 结果页与 CLI result 命令分别渲染同一个对象。

```text
ApplicationCore / Published facts
  → ProductStatus / ProjectReadiness / ResultPresentation / HistoryView
  → loopback API envelope → GUI
  → CLI Human / Verbose / Machine v1
  → MCP Streamable HTTP → 固定工具白名单
  → Report publication（独立不可变交付物）
```

页面文案、终端颜色或 JSON 格式都不能反向改变事实。Report 是独立不可变交付物，也不由 CLI stdout 代替。

## ProductStatus 与 GUI

`ProductStatus` 只读汇总当前项目、六步准备状态、唯一下一步、活动任务和最近可信结果，不保存独立“向导进度”。浏览器本地状态只记当前选择和页面；刷新后由 API 恢复权威事实。Workbench 不常驻显示产品版本，产品版本在 `/settings/system` 等明确诊断位置展示。

GUI 通过固定 loopback API 读取 envelope。API 成功 envelope 使用根 `schema_version="1"` 与 `data`；异常由稳定 error code、trace 和有界 details 映射。API envelope 版本描述控制面机器格式，不是产品版本 1.0.2。

## CLI Human、Verbose 与 Machine

CLI 默认按 TTY 选择人类输出；`--human` 强制人类可读，`--verbose` 在人类结果后追加有界技术引用，`--json` 强制 Machine 输出。三种模式互斥地选择 renderer，不在一个 stdout 中混写。

Human 先给结论、关键事实与下一步，默认隐藏内部 ID、reason code 和复杂结构。Verbose 可以增加 run/evidence 等技术引用，但不能泄漏秘密或完整环境。Machine v1 成功对象固定包含：

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

## MCP Streamable HTTP 与工具输出

MCP 精确挂载在同一 loopback FastAPI 服务的 `/mcp`，由官方 Python SDK v2 提供 Streamable HTTP；不保留 SSE 路由，也不创建第二个 ApplicationCore、Worker 或监听端口。首次配对签发的 Authorization Bearer 只经精确 SecretStore 引用长期保存，后续启动自动恢复 READ。GUI control session Cookie、模型 Provider Key 和其他 SecretStore 引用都不能替代该令牌；SDK 继续独立校验 Host 与 Origin。

MCP 工具不套用 API envelope 或 CLI Machine envelope，而按 SDK 协议返回现有 Pydantic View 的 structured content 或有界轻量投影。根 View 自身已有 `schema_version` 时保持原值；不能为每个嵌套 DTO重复制造版本，也不能把 MCP 协议版本当作产品版本。ProductStatus 与 ResultPresentation 必须和 GUI/CLI 读取同一应用服务，Evidence 只返回已发布索引而非完整文档。

权限固定为逐 Project 层级：长期配对只恢复 `READ`，显式确认后才可在当前 serve 临时提升为 `PREPARE` 或 `EXECUTE`。暂停和 shutdown 撤销活动会话与全部提升但保留配对；轮换立即废止旧令牌并保存新令牌；忘记连接删除配对。普通状态不返回明文令牌，访问边界只使用 `MCP_DISABLED`、`MCP_AUTH_REQUIRED`、`MCP_PERMISSION_REQUIRED` 三个稳定错误；权限不足 details 只允许 `required_level` 和 `project_id`。

## ResultPresentation 与 Evidence

`ResultPresentation` 回答“谁对什么执行了什么、预期是什么、表面请求怎样、真实对象怎样、为何形成结论”。它可以把冻结 EffectBinding 与实际 Observation 投影为 KEY/SUPPORTING、FOUND/NOT_FOUND/UNAVAILABLE，但不能重算 Verification。

`ResultPresentation.execution_traces` 从冻结 request snapshot 与已发布 Evidence 还原每个 Case/Action 的实际事件 DAG。它可以表达入口 subject、实际 actor、权限 decision、后台代表关系和最终产物；缺少关键来源时只发布已有节点并标记 partial。GUI、CLI 或 MCP 只能投影这些节点，不能借事件顺序产生新的安全结论。

CLI JSON evidence 命令与 API evidence index 比较的是已发布索引；完整 Evidence detail 是另一资源。索引与文档不能逐字比较，Human/Machine 也不应为方便展示复制整份 Evidence。报告投影关系见[报告与格式投影协议](报告与格式投影协议.md)。

## LocalControl 与 ServeLock

loopback 不等于自动可信。API 先校验实际 Host；GUI 根页面取得当前服务进程签发的 HttpOnly、SameSite=Strict control session；全部 `/api` 请求要求该会话，写请求再要求 Origin 与控制面 origin 完全一致。MCP 使用独立 Bearer 与 SDK Host/Origin 防护。代理头不能改变授权 Host，测试 header 不能变成生产旁路。

GUI serve 与会创建 ApplicationCore 的 CLI 命令共享 `ServeLock`。同一 VarDir 已有控制者时，第二入口在创建 ApplicationCore 前返回 `WORKSPACE_ALREADY_CONTROLLED`。锁文件是所有权记录，不是 daemon 或 IPC；持有者仍存活时不能靠删除文件绕过，进程正常/异常退出后必须可重新获取。

## 状态、错误与长时过程

控制面显示的状态必须来源明确：ProductStatus/Readiness 是产品事实，Job/Run 是生命周期，Runner progress 是非权威展示旁路，ResultPresentation 是已发布结果。多阶段长时过程应展示稳定阶段并即时刷新；没有权威 completed/total 时不伪造百分比，而是显示当前阶段和有界等待说明。

发生错误时先保留第一主错误及 trace，再执行正式 cleanup。cleanup warning 单独展示，不覆盖 primary failure。安全 BLOCK/INCONCLUSIVE 不是控制面执行错误，不能被 ErrorRecovery 当作异常页面。

## 查询入口

| 要查什么 | 当前真源 |
| --- | --- |
| ProductStatus | `product/backend/workflows/control.py` |
| API envelope 与 LocalControl | `product/backend/api/envelope.py`、`product/backend/api/local_control.py` |
| MCP transport、工具与授权 | `product/backend/api/mcp.py`、`product/backend/workflows/mcp_access.py` |
| CLI 命令与 Machine renderer | `product/backend/cli/app.py`、`product/backend/cli/presentation.py`、`product/backend/cli/commands/control.py` |
| ResultPresentation/ExecutionTrace/History | `product/backend/workflows/results/presentation.py`、`product/backend/workflows/results/trace.py`、`product/backend/workflows/results/history.py` |
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
