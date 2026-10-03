# 修改 Agent 变更影响

> 状态：CURRENT。用于真实变化登记、修复引用、源码对应和检查续接。普通未关联 PASS 不能作为修复通过。

开发任务入口为 `workflows/development/`：`service.py` 拥有命令与回执事务，`reading.py` 读取历史、交付差异和精确检查关联，`operations.py` 供开发与运行加载共用操作指纹及版本检查。`DevelopmentService` 保留稳定入口；查询不能扫描源码或创建交付，`write_prepared_change` 继续复用命令持有的 UoW。

## 快速找到修改位置

| 要改什么 | 实现入口 | 直接测试 |
| --- | --- | --- |
| 变化模型、真实扫描与原子登记 | `product/backend/core/changes/models.py`、`product/backend/workflows/changes/service.py` | `tests/backend/workflows/changes/test_current_source_changes.py` |
| 源码身份与历史观察 | `product/backend/workflows/changes/identity.py`、`product/backend/workflows/changes/observations.py` | `tests/backend/workflows/changes/test_source_identity.py`、`tests/backend/workflows/changes/test_code_observations.py` |
| 原题合同与复验语义 | `product/backend/core/checks/repair.py`、`product/backend/workflows/checks/repairs/repair.py` | `tests/backend/core/checks/test_check_repair.py`、`tests/backend/workflows/checks/test_repair_publication.py` |
| 项目修复七态与唯一主任务 | `product/backend/workflows/projects/repair.py`、`product/backend/workflows/workspace/service.py` | `tests/backend/workflows/checks/test_project_repair_states.py`、`tests/backend/workflows/workspace/test_repair_task.py` |
| 完整请求冻结与元数据回调 | `product/backend/workflows/checks/service.py` | `tests/backend/infra/runtime/jobs/control/test_provenance_callback.py` |
| 控制面与界面交付 | `product/backend/api/routers/changes/source_changes.py`、`product/backend/api/mcp/server.py`、`product/frontend/src/features/changes/` | `tests/backend/api/system/test_current_mcp.py`；对应前端组件测试 |

## 修改与直接验证

默认客户端先读取 registration-preview，再用稳定 operation_id 调用 register；GUI 无需手工建立任务。一次登记事务与旧接口兼容边界见[一次登记与可靠回执](../../参考/协议/变化与原题复验契约.md#一次登记与可靠回执)。直接回归包括 `test_development.py`、`test_current_mcp.py` 与 `ChangesPage.test.tsx`。

先沿真实链定位：扫描前权限/理解 → 重扫源码 → 同一事务登记 manifest/diff/assessment → inspection → 带精确 change_id 的检查 → publication → 修复与工作台只读投影。

```powershell
.\scripts\dev.ps1 test tests/backend/workflows/changes/test_current_source_changes.py tests/backend/workflows/checks/test_project_repair_states.py
.\scripts\dev.ps1 frontend-test src/features/checks/CurrentTestsPage.test.tsx src/features/changes/ChangesPage.test.tsx
```

命令为相关邻域示例，按上表选择真实受影响文件。跨页丢引用时先测“准备 → 返回 → 显式提交”；不要修改后端标准来接受普通 Run。修改 Verification / 公共合同再按[验证规范](../验证.md#4-模块范围--验证程度)选择范围。

## 必须保持

- Agent 的 claimed_paths、理由、Git 和 mtime 不是安全事实；实际差异由授权根内两份服务端内容快照产生，最多接受 128 条相对路径线索。
- 变化登记不审批权限、不自动重绑、不推进 policy_epoch；扫描时发生权限变化则拒绝登记，不回滚人的并发审批。
- 影响分析不裁剪完整当前考题；普通提交和带 change_id 的提交均重新核对 live 源码。
- 原题必须来自本项目已发布 BLOCK / VULNERABLE Case；NEW Run 冻结精确 change 和 repair context。原规则、身份、资源、证明标准及正常能力不能降低。
- VERIFIED 只从两份完整 publication 派生；Agent 声明、关闭功能、改权限或未关联 PASS 均不能替代。
- 回执 RECORDED 只证明登记完成；不要求用户为同批 MCP 交付重复登记。GET 与刷新不创建检查。
- 源码对应只能说明受控扫描范围，不证明目标部署版本。MCP 不输出绝对路径、源码正文、原始 Evidence/Trace、Git 身份或秘密。

## 按问题读取细节

| 当前问题 | 唯一详细说明 |
| --- | --- |
| inspection 的五态及变化范围 | [影响与现场重验](../../参考/协议/变化与原题复验契约.md#影响与现场重验) |
| 原题冻结标准、正常对照、回归与七态 | [原题修复](../../参考/协议/变化与原题复验契约.md#原题修复) |
| MCP 权限、回执与脱敏输出 | [API 与 MCP](../../参考/协议/变化与原题复验契约.md#api与mcp)；鉴权修改再读[控制面](修改API与控制面.md) |
| 当前源码、历史 Git 与读取失败 | [源码对应](../../参考/协议/变化与原题复验契约.md#源码对应与交付阅读)、[历史观察](../../参考/协议/变化与原题复验契约.md#历史代码观察) |

不恢复旧 ProjectRevalidation、DeliveryCheck、ResultPresentation 或旧 CLI 链补充当前能力。
