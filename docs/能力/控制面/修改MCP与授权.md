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

## 三层授权

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
