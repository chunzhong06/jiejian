# 修改MCP与Agent授权

> 状态：CURRENT。MCP连接原Agent和界鉴的同一ApplicationCore。连接凭据、逐项目权限、人的业务决定是不同边界。

## 快速找到修改位置

| 任务 | 主位置 | 消费者/验证 |
| --- | --- | --- |
| 当前工具注册与业务调用 | `product/backend/api/mcp/server.py`、`product/backend/api/mcp/preparation.py` | 当前registry及严格参数；`tests/backend/api/system/test_current_mcp.py`、`test_mcp.py`（同目录） |
| Bearer、ASGI挂载、SDK会话 | `product/backend/api/mcp/transport.py` | api/app、本机控制、当前SDK请求；不能创建第二个ApplicationCore |
| 授权与净化错误 | `product/backend/api/mcp/errors.py`、`product/backend/workflows/agent_access/service.py` | GUI授权、撤权回调、Worker执行授权 |
| 有限事实输出 | `product/backend/api/mcp/views.py`、preparation.py的public_preparation | 原领域reader、严格公开字段、秘密过滤 |
| 连接页面和客户端指引 | `product/frontend/src/features/tools/` | API返回的endpoint/connection_state、主题、客户端选择和真实身份分开 |

## 统一协助入口

权限页和检查材料页使用`shared/ui/AgentAssistEntry`，同一“Agent 协助”名称与次按钮样式。入口只读取当前业务依据和MCP状态，展开当前任务，复制有限请求交给原开发客户端；不会启动模型、保存候选或自动批准。复制前再次核对项目、依据与授权，依据变化先更新请求供核对。当前范围不足时由人进入已有开发工具授权，返回保留项目、候选/动作及变化引用。隐藏页停止读取，跨项目迟到响应失效。

规则区的“读取候选”、材料区的“读取建议”与“Agent 协助”并排，分别回读对应修订；没有实际新回执不显示Agent已完成。`jiejian_preparation_suggestion_save`要求PREPARE，`show/receipt`要求READ；五类有限字段和输入schema从`jiejian_preparation_context`的`suggestion_context`读取。复制请求使用该对象的`psb_…`依据，不误用证明来源的`pb_…`。保存未知只查原回执，人的规则批准、登录、scope/adopt保持原边界。内置模型解释已退出，录制与实现定位同样交给原Agent。

## Agent 协作的完整顺序

| 阶段 | Agent 做什么 | 界鉴与用户如何接续 |
| --- | --- | --- |
| 权限约定 | 读取上下文，整理角色、动作和允许/禁止要求，保存候选 | 用户审阅完整变更并批准 |
| 材料准备 | 读取当前缺口，保存实际来源候选，在已有授权下执行可用的准备/预检查；不能只重复给出操作建议 | 官方示例使用固定配方一键准备；普通项目集中核对账号、资源、读取位置和文件，再由界鉴顺序检查并采用 |
| 检查执行 | 先 jiejian_check_preview 读取计划；取得 EXECUTE 授权后，携带 expected_plan_fingerprint 提交或查询指定检查 | 人决定是否执行，界鉴保存操作与独立证据 |
| 结果解读 | 读取该 run_id 的结果、索引和具体证据，解释结论与缺口 | 整轮和具体证据入口随当前视图切换，同屏不重复显示两个 Agent 入口 |
| 修复复验 | 读取修复要求；获修改授权后完成代码修改，登记真实差异并核对新实例 | 按原要求检查，保留正常业务对照，将复验结果继续交给 Agent 解读 |

准备页有一个整体协作入口。文件准备内嵌在该页时不再增加第二个入口；独立来源页的入口只处理当前材料。统一上下文使用 jiejian_agent_context，不再提供内置模型短解释。

## 结果交接的读取范围

完成页和结果页复用 `ResultAgentHandoff`。用户展开“Agent 协助”，核对 MCP 连接后复制请求到原对话；这里只需要 READ。请求固定 project_id、run_id 及可选 case_id，不使用“最近一次”代替用户正在看的记录。复制成功仅表示剪贴板写入，不显示“已递交”或“Agent 已读取”。

Agent 先调用 `jiejian_result_show`，取得每项 evidence_refs、路径可用/完整状态和 review_url；再调用 `jiejian_evidence_show` 读取索引，以 record_ref 读取具体业务证明和 Trace。两步都核对项目与检查归属，使用同一已发布包。解释包括权限要求、实际账号与资源、执行、观察、结论与缺口，并给出可回看的引用。Trace 不取代独立业务证明。

BLOCK 沿 `jiejian_repair_show` 解释必须消除与保留的结果；INCONCLUSIVE 说明具体缺证；PASS 说明覆盖范围。讨论后获得用户修改授权，再使用已有 task/context、变化登记、运行加载、检查预览和复验流程。结果解读本身不提升权限、不修改应用、不批准业务规则或采用来源，也不自动提交下一轮。

## 三层授权边界

1. 长期配对凭据只保存在精确SecretStore引用，transport逐请求核对Bearer；连接会话ID不代表权限。
2. READ读取有限事实；PREPARE登记变化或候选；EXECUTE提交/取消当前完整检查及获授权的来源预检查。逐项目提升只属于当前控制会话，重启、暂停、旋转/删除凭据和关闭会清除提升。
3. 正式权限批准、证明读取范围、来源采用仍由GUI中人的决定形成。MCP提供context、candidate、preview及GUI去向，不能通过参数旁路人的决定。

精确工具名及注册位置查[注册与格式](../../参考/生成/注册与格式.md)。每个新工具先调用已有workflow能力，再处理严格参数、授权和有限输出；不在transport或views复制事务。

## 当前连接状态

`MCPAccessView.connection_state`拥有连接阶段：凭据准备、Bearer已认证和SDK已处理MCP请求各是不同事实。配置被复制或客户端声称保存成功，不能先显示连接成功；最近活动也不证明客户端此刻正在编码。

GUI提供Codex、DSH与ZCode的配置指引，教程选择与真实客户端名称分开；具体安装/联调证据另行记录。当前客户端共享连接授权，不能宣称按客户端独立撤权。服务地址取当前endpoint，不固定端口。秘密由用户在本机按指引配置，不进入对话、源码和导出的配置预览。

## 失败先查哪里

- 认证失败：transport与SecretStore精确引用；日志/异常不可回显输入令牌。
- 工具能列出但操作被拒绝：当前项目及权限级别、客户端会话、实际工具required level。
- 保存或登记响应未知：回读原领域operation receipt；MCP净化输出不能改变幂等身份或自动重放。
- 撤权后预检查未结束：authority回调、proof job_authorized、持久取消和Runner清理分别核对。
- 字段泄漏或结果失真：先核对原reader，再查views/public_preparation；不把隐藏字段删改传播回内部权威模型。

## 验证与深入

授权变化覆盖READ/PREPARE/EXECUTE、错误项目、撤权、暂停、重启与输入额外字段拒绝；纯投影变化测字段边界和对应业务reader。改变传输会话才补SDK/ASGI直接集成，不调用真实付费模型。装配见[API与装配](修改API与装配.md)，生命周期见[启动与退出协作](启动与退出协作.md)，公开格式见[控制面协议](控制面与Machine输出协议.md)。

## 持久材料批次

jiejian_preparation_batch_plan与status为READ；cancel要求EXECUTE。GUI确认后由后台自动推进，不开放MCP批准入口。批次保存精确来源修订、配置摘要、依据和读取授权引用；未知步骤只查原回执，撤权或重启后回GUI重新核对。
