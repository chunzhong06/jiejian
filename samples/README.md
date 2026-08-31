# 官方 Sample

`samples/web/collaboration_space` 是界鉴随源码提供的唯一 Web 演示应用：“协作空间——项目资料管理应用”。固定项目为“校园数字展馆”，Alice 是项目负责人，Bob 是普通成员；Bob 可以查看日常协作资料，但不能导出完整项目交付包。

同一个应用通过授权顺序和关键观察可用性形成漏洞、修复、观察受限三种事实。Sample 不包含预设 Verdict，最终 `BLOCK`、`PASS`、`INCONCLUSIVE` 只能由界鉴正式 Verification 和 Evidence 路径产生。

## 从界鉴 GUI 启动

从仓库根运行：

```powershell
.\start.cmd
```

进入 GUI 后使用“评委导览”。界鉴会通过正式 ApplicationCore 启动官方 Sample、接入应用并引导完成应用理解、Recording、权限准备与检查。不要直接调用 Sample 内部 manager 来伪造导览状态。

Sample Bundle 位于：

```text
samples/web/collaboration_space/
├── sample.json
└── source/
    ├── background.py
    ├── openapi.json
    ├── page.py
    ├── server.py
    └── storage.py
```

每次体验把独立源码副本和状态写入当前实例 `var/runtime/official-samples/<experience-id>/source|state`；数据库、Task、Audit、Queue、Blob、ZIP 和环境描述符都位于 `state`，日志进入 `var/logs/official-samples`，不写回 Sample Bundle 或 `var/data`。结束体验、移除应用和 ApplicationCore 安全退出都会回收本次 source/state。

## 业务模式和六面观察

同一个导出 API 支持两种授权顺序：

- `AUTHORIZE_BEFORE_ENQUEUE`：先检查权限。Bob 收到 403，且不会产生导出副作用。
- `ENQUEUE_BEFORE_AUTHORIZE`：先进入后台导出链，再返回 Bob 的权限拒绝。HTTP 仍为 403，但 Task、Queue、Audit 和最终 ZIP 会真实形成。

关键 Blob 读取面可以由正式受控机制设为 `UNAVAILABLE`，用于证明业务已修复但关键事实暂时不可可靠读取的 `INCONCLUSIVE`。它不能扩大成所有 Observer 的通用不可用模式。

界鉴的正式接线把 Owner API 与最终 Blob 对象作为关键来源，把 SQLite、结构化 Audit、后台 Task 和 Queue 作为佐证来源。接线逻辑位于产品的安全准备工作流，不写入 Sample Bundle，也不由 Sample 决定观察角色。

## “撤销本次导出”不是删除历史

Alice 在资料包生成成功后可以执行：

```text
撤销本次导出
→ 确认撤销
→ 当前导出状态：已撤销
→ 可以重新生成交付包
```

这是正常业务撤销：

- Project 进入 `REVOKED` 并清空当前 task、artifact、case 指针；
- export job 和 Task 保留并进入 `REVOKED`；
- 原 Audit、Queue 历史保留，并追加一次 `EXPORT_REVOKED`；
- 历史 Blob 文件可以保留，但不再出现在当前有效 Blob namespace；
- Owner API 与 Blob 都表达当前资源不存在；
- 重复撤销幂等；Bob 不能撤销 Alice 的资料包；
- 重新生成会创建新的 marker、job 和 artifact，不复活旧记录。

HTTP `DELETE /api/projects/{project_id}/exports` 表达“撤销当前有效交付物”，不表示这次导出从未发生。

## `/reset` 才负责测试基线重建

`POST /reset` 或 `POST /api/reset` 是官方 Sample 的测试基础设施入口，只接受 loopback 请求和 `X-Jiejian-Test-Mode: 1`。它可以停止后台 Worker、清空测试 runtime，并恢复 `NOT_CREATED`。

业务撤销与测试 reset 不能共用物理清理实现：

```text
DELETE /api/projects/.../exports
→ Business Revoke
→ 保留历史，当前资源 ABSENT

POST /reset
→ Test Baseline Reset
→ 清空 Job、Task、Audit、Queue 和 Blob
```

普通页面和 Recording Recovery 只使用业务撤销。测试 fixture 需要全新基线时才使用 reset。

## 自动 L5 与直接验证

唯一自动 L5 技术入口是：

```powershell
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File .\scripts\dev.ps1 sample-test
```

它从真实 `start.cmd` 启动 fresh `var/test/sample-test/<uuid>`，通过正式 Worker 和独立 Recording Process 创建 headed Chromium，再由 Windows UI Automation 的 InvokePattern 操作页面按钮。完整 L5 分别录制导出和日常查看，形成三条 Case 与一组导出孪生，并同时验证 capture 生命周期、真实 FlowDraft、三态 Runner、六面 Evidence、GUI/CLI/JSON 等价、Report、History 和安全退出。

修改 Sample 后优先运行现有直接测试：

```powershell
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File .\scripts\dev.ps1 test tests/samples/web/test_collaboration_space.py
```

跨正式接线或三态语义时，再按影响范围运行安全准备和 Golden 测试。`sample-test` 只在阶段收口运行一次，不作为日常 Debugger。具体规则见[修改官方示例与整链验收](../docs/02_开发指南/任务/修改官方示例与整链验收.md)。

## 安全边界

- Sample 只绑定 loopback，不扫描公网，不调用真实付费接口。
- 密码、Cookie、Token、SAS、owner token、权限契约、Evidence 和 Report 不写入 Sample 源码。
- 运行环境描述符只保存非秘密 locator 和 `env:` 引用，不保存 secret value。
- 自动 L5 不使用 controlled runner、伪造 RecordingEvent、预制 FlowDraft、CDP、remote debugging 或测试专用生产 API。
- 停止官方示例和清理测试身份优先走正式控制面；不能枚举并终止用户已有的 Python、Chromium、Node 或 PowerShell。
