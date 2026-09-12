# 修改 Agent 变更影响

> 状态：CURRENT。适用于当前 SourceChange、原题 Repair、完整检查提交与只读结果投影。

## 事实与权限边界

Agent 提交修改理由、至多128条相对 `claimed_paths` 和可选 `CurrentRepairReference`。路径仅为线索：界鉴在已授权源码根内重新扫描，用两份服务端快照的内容hash计算真实增删改。Git、mtime和Agent声明都不是安全事实。密码、Cookie、Token和源码正文不进入变化公共投影。

Actor、Action、Effect、Permission与正式实现映射仍由普通Human Approval批准。变化提交不调用旧 `refresh_bindings`，不自动重绑、不推进 `policy_epoch`，不允许客户端选择Permission、Case或Effect。

## 当前实现链

```text
CurrentSourceChangeService.submit
→ 保存扫描前理解/权限epoch及全部PermissionReference
→ analyze_source_for_change形成真实SourceRevisionSnapshot
→ 同一事务重核理解/权限、计算ChangeSet与Assessment并登记
→ SourceRevalidationInspection
→ CheckService.preview/submit(change_id)
→ PersistedExecutionRequestV3.ChangeContext / RepairContext
→ CHECK Worker / Runner / publication
→ ResultStory / CurrentRepairVerification / ProjectRepair / Workspace
```

Manifest、diff和assessment在同一事务保存；扫描期间权限变化使整个登记失败，但不回滚用户的并发审批。扫描产生的真实理解与快照可以保留，不能称为变化登记成功。复用既有四张source change表，无新增DDL；旧格式不靠猜测shape读作current。

| 责任 | 当前入口 |
| --- | --- |
| 路径、快照、变化DTO | `product/backend/core/source_changes.py` |
| 扫描、影响、登记、inspection | `product/backend/workflows/changes/service.py` |
| 聚合持久化 | `product/backend/infra/storage/source_changes.py` |
| 原题语义与标准比较 | `product/backend/core/check_repair.py` |
| 从已发布包重建合同 | `product/backend/workflows/checks/repair.py` |
| 项目问题族与状态 | `product/backend/workflows/projects/repair.py` |
| 完整请求冻结 | `product/backend/workflows/checks/service.py` |
| GUI/MCP入口 | `product/backend/api/routers/source_changes.py`、`product/backend/api/mcp.py` |

## 影响与现场重验

`DIRECTLY_AFFECTED`只表示真实变化与当前Action、subject/owner Actor实现路径相交；`NO_DIRECT_EVIDENCE`不是安全结论。缺基线、绑定失效或映射不可靠形成`MAPPING_REVIEW_REQUIRED`。影响列表准确记录受影响动作，冻结的`required_intent_ids`保守包含全部当前Permission；完整Plan永不裁剪。

Inspection仅有`READY / NO_BASELINE / SOURCE_STALE / POLICY_STALE / MAPPING_REVIEW_REQUIRED`，准备缺口另行结构化保留。所有Check提交，包括不带change_id的普通提交，都在提交前及事务内重新核对live源码；陈旧preview或后续磁盘变化不能绕过。

## 原题修复

引用由`source_run_id/source_case_id/64位repair_fingerprint`构成，必须指向本项目已发布BLOCK中的VULNERABLE Case。服务端从不可变包重建完整合同，不接受客户端合同正文。冻结原Permission集合与epoch、subject/owner真实身份、具体资源、全部禁止效果、选定ALLOW控制和原Run全部实际SAFE的ALLOW_REGRESSION。

superset控制与完整回归分别保留；历史SAFE回归可以为空，但NEW控制仍必须SAFE。路径匹配排除新source/config/Flow等技术标识，保留全部业务身份；每条VERDICT_REQUIRED的完整Observer/HTTP模板、独立观察身份、descriptor、scope/phase/closure/budget等标准必须严格相同，不能降低标准。

NEW Run必须不同于source，并冻结精确change及repair context。权限变化为STALE；可信原禁止效果仍存在为NOT_VERIFIED；路径、归因、观察、控制或完整当前Run不足为INCONCLUSIVE；只有所有原题要求和完整当前Run都成立才VERIFIED。普通未关联PASS不能冒充修复。验证是两份publication的只读派生，不建可变修复结论表。

ProjectRepair按最早BLOCK建立问题族，取最新精确关联变化与NEW Run。状态为`REPAIR_REQUIRED / CHANGE_SUBMITTED / READY_TO_VERIFY / VERIFIED / NOT_VERIFIED / INCONCLUSIVE / STALE`；没有问题时为null。Workspace保留接入、边界、重绑、准备的优先级，再选择登记变化、复验原题、运行当前检查或查看结果，携带精确change_id/run_id。

## API与MCP

GUI使用`/api/projects/{id}/source-changes`、`/repair`、`/check-preview?change_id=...`及schema2的`/runs`；原题列表在`/api/runs/{run_id}/repair-contracts`。MCP只有`change_submit`为PREPARE，`check_run/check_cancel`为EXECUTE，其他当前工具READ。项目授权临时保存在当前进程，pause/resume/rotate/forget/close清除；权限审批不开放给MCP。

MCP只返回相对路径、有界影响和业务结果，隐藏绝对路径、源码/config hash、原始Evidence/Trace与秘密。客户端来源从认证SDK会话取，不由Agent自报。

## 直接验证

使用`dev.ps1 test`按受影响范围选择`tests/backend/workflows/changes/test_current_source_changes.py`、`tests/backend/core/test_check_repair.py`、`tests/backend/workflows/checks/test_repair_publication.py`、`test_project_repair_states.py`、`tests/backend/api/test_current_mcp.py`及`test_permission_oracle_invariant.py`。覆盖真实扫描、原子回滚、权限并发、superset/空回归、错误原题、公开SDK及秘密边界。公共模型变化同步schema；文档使用docs检查。不要恢复旧ProjectRevalidation、DeliveryCheck、ResultPresentation或旧CLI链来补current能力。
