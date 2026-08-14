# 本机样例

`fixed_apps/permissions_v2/`、`vulnerable_apps/permissions_v2/` 和 `inconclusive_apps/permissions_v2/` 是阶段 6.2 的 V2 权限关系规划样例。三套目录的 `contract.json` 与 `profile.json` 语义分别相同；`scenario.json` 和 `truth.json` 只描述变体与预期观察，不是 V1 `project.yaml`，也不接入 Runner V1。

样例进程仅绑定 `127.0.0.1`，通过以下模块入口启动：

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
& 'D:\Miniconda\envs\jiejian_env\python.exe' -B -m jiejian.permission_sample_app --variant fixed --port 8765
```

`fixed` 严格执行权限和原子批量语义，`vulnerable` 保留可观测的越权/部分副作用缺陷，`inconclusive` 使 `owner_api` 返回稳定 503。Profile 可由后端 `PermissionExecutionService` 注册并由独立 Worker/Runner V2 执行；三者仍只绑定回环地址，不代表阶段 7 报告已实现。

阶段 6.3 的配对测试为 fixed/vulnerable 使用测试临时目录中的 `resource_state` SQLite 数据源，通过 `resource-state` 固定观察模板比较 BEFORE/AFTER envelope。它验证 HTTP 403 后是否发生数据库副作用；数据库路径和 secret 只存在于测试进程环境，不写入这些资产。

正式 Profile 入口需要先在当前 PowerShell 会话设置临时、不落盘的凭据值，再启动样例。所需环境变量为 `JIEJIAN_PERMISSION_MEMBER_A`、`JIEJIAN_PERMISSION_MEMBER_A2`、`JIEJIAN_PERMISSION_MEMBER_B`、`JIEJIAN_PERMISSION_DEPT_ADMIN_A`、`JIEJIAN_PERMISSION_DEPT_ADMIN_A2`、`JIEJIAN_PERMISSION_TENANT_ADMIN_A`、`JIEJIAN_PERMISSION_PEER_A` 和 `JIEJIAN_PERMISSION_OWNER_OBSERVER`。启动示例：

```powershell
$env:JIEJIAN_PERMISSION_MEMBER_A = '<temporary opaque value>'
$env:JIEJIAN_PERMISSION_MEMBER_A2 = '<temporary opaque value>'
$env:JIEJIAN_PERMISSION_MEMBER_B = '<temporary opaque value>'
$env:JIEJIAN_PERMISSION_DEPT_ADMIN_A = '<temporary opaque value>'
$env:JIEJIAN_PERMISSION_DEPT_ADMIN_A2 = '<temporary opaque value>'
$env:JIEJIAN_PERMISSION_TENANT_ADMIN_A = '<temporary opaque value>'
$env:JIEJIAN_PERMISSION_PEER_A = '<temporary opaque value>'
$env:JIEJIAN_PERMISSION_OWNER_OBSERVER = '<temporary opaque value>'
& 'D:\Miniconda\envs\jiejian_env\python.exe' -B -m jiejian.permission_sample_app --variant fixed --port 8871
```

从同一父 PowerShell 会话启动样例和 CLI，或在两个终端分别设置相同的临时环境值，再执行项目 console entrypoint `jiejian permission-run samples/fixed_apps/permissions_v2/profile.json`。占位值不是可用凭据；真实值不要写入 Profile、命令行参数、文件或日志。

阶段 6.4 的异步因果样例由 `tests/verification/test_async_causal_observation.py` 通过 loopback 运行：同一 Contract 下，`fixed` 的任务权威负观察为 `NOT_CREATED`，`vulnerable` 通过显式 case tag 关联真实后台任务和 SQLite 副作用，`inconclusive` 的任务状态 API 稳定 503，不能由 HTTP、审计或 SQLite 单独替代。测试侧将 `http`、`audit_log`、`async_task`、`final_side_effect` 四面事实分开保存；这些资产不是 V1 `project.yaml`，不接入 Runner V1。V2 Evidence 已随 Runner publication 产生并可读取；阶段 7 统一报告、Finding/Gate、MQ/对象存储正式 Profile 接入仍未实现。
