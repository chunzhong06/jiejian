# 官方 Sample

`samples/web/collaboration_space` 是界鉴随源码提供的唯一 Web 演示应用：“协作空间——项目资料管理应用”。固定项目为“校园数字展馆”，Alice 是项目负责人，Bob 是普通成员；Bob 可以查看日常协作资料，但不能导出包含申报书、预算、成员信息和评审材料的完整项目交付包。

问题版模拟 Vibe Coding Agent 为缩短等待，把后台任务创建提前到权限判断之前。Bob 的页面响应仍是 403，但 Task、Queue、Audit 和 ZIP 可能已经真实形成。Sample 不包含预设 Verdict，最终 `BLOCK`、`PASS`、`INCONCLUSIVE` 只能由界鉴正式 Verification 和 Evidence 路径产生。

## 从界鉴 GUI 启动

从仓库根运行：

```powershell
.\start.cmd
```

未接入工作台会展示样例背景。点击“启动官方示例”后：

1. 阅读“进入 Agent 写错的问题版？”并确认启动；
2. 点击“一键应用样例配置”，由正式服务建立固定角色、动作、账号、流程和三条公开权限规则；
3. 点击“检查问题版”，通过真实检查形成 `BLOCK`；
4. 点击“交给 Agent 修复”，查看 MCP 修复合同和 `authorization_policy.py` 修改说明；
5. 重新检查修复版，形成 `PASS`；
6. 可以切换证据受限版，在问题代码与两条关键业务结果观察不可用的条件下重新检查，形成 `INCONCLUSIVE`。

启动、配置和切换本身都不会创建 Run 或预制结论。普通应用不显示官方示例入口，也不复用样例的一键合同。

Sample Bundle 位于：

```text
samples/web/collaboration_space/
├── sample.json
└── source/
    ├── authorization_policy.py
    ├── background.py
    ├── openapi.json
    ├── page.py
    ├── server.py
    └── storage.py
```

每次体验把独立源码副本和状态写入当前实例 `var/runtime/official-samples/<experience-id>/source|state`；数据库、Task、Audit、Queue、Blob、ZIP 和环境描述符都位于 `state`，日志进入 `var/logs/official-samples`，不写回 Sample Bundle 或 `var/data`。结束体验、移除应用和 ApplicationCore 安全退出都会回收本次 source/state。

## 三个版本与六面观察

同一个导出 API 通过源码中的授权顺序形成两个实现：

- `AUTHORIZE_BEFORE_ENQUEUE`：先检查权限。Bob 收到 403，且不会产生导出副作用；
- `ENQUEUE_BEFORE_AUTHORIZE`：先进入后台导出链，再返回 Bob 的权限拒绝。HTTP 仍为 403，但 Task、Queue、Audit 和最终 ZIP 会真实形成。

三个用户可见版本是：

- 问题版：`ENQUEUE_BEFORE_AUTHORIZE`，只读业务状态与最终 ZIP 两条关键结果观察可用；
- 修复版：`AUTHORIZE_BEFORE_ENQUEUE`，两条关键结果观察可用；
- 证据受限版：`ENQUEUE_BEFORE_AUTHORIZE`，两条关键结果观察对 Bob 当前实验不可用。

界鉴把 Owner API 与最终 Blob 对象作为关键来源，把 SQLite、结构化 Audit、后台 Task 和 Queue 作为佐证来源。观察角色和 Verification 规则位于产品正式工作流，不写入 Sample Bundle，也不由 Sample 决定。

## 一键合同不是预制结果

“一键应用样例配置”通过正式 ApplicationUnderstanding、TestIdentity、RecordingLifecycle、FlowDraft、SafetySetup、PermissionIntent、SourceChange 和 ProjectPreparation 服务重放确定性操作。它等价于替用户完成固定样例里没有判断价值的逐项点击，但不得直接写数据库拼装状态，也不得创建 Run、Evidence、Finding、Report 或 Verdict。

修复按钮模拟 Codex 通过 MCP 读取界鉴对来源 `BLOCK` Run 发布的修复合同，随后真实修改当前体验副本中的 `authorization_policy.py`。变化模块必须能看到这次源码差异；是否修复成立仍由下一次独立检查决定。

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

## `/reset` 只负责测试基线重建

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

它从真实 `start.cmd` 启动 fresh `var/test/sample-test/<uuid>`，用 Playwright 从未接入工作台进入问题版，验证一键合同、三条 Case 与一组导出孪生、修复弹窗和代码变化、三态 Runner、六面 Evidence、GUI/CLI/JSON 等价、Report、History 和安全退出。

普通应用的 headed Recording 与 Windows UIA 能力有独立直接测试，不再作为官方样例的逐项准备步骤。

修改 Sample 后优先运行：

```powershell
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File .\scripts\dev.ps1 test tests/samples/web/test_collaboration_space.py
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File .\scripts\dev.ps1 test tests/backend/infra/samples/test_official.py tests/backend/api/test_experience.py
```

跨正式接线或三态语义时，再按影响范围运行安全准备、SourceChange 和 Golden 测试。`sample-test` 只在阶段收口运行一次，不作为日常 Debugger。具体规则见[修改官方示例与整链验收](../docs/02_开发指南/任务/修改官方示例与整链验收.md)。

## 安全边界

- Sample 只绑定 loopback，不扫描公网，不调用真实付费接口；
- 密码、Cookie、Token、SAS、owner token、权限契约、Evidence 和 Report 不写入 Sample 源码；
- 运行环境描述符只保存非秘密 locator 和 `env:` 引用，不保存 secret value；
- 一键合同不使用 controlled runner，不向生产代码加入 tests-only Verdict 开关；
- 停止官方示例和清理测试身份优先走正式控制面；不能枚举并终止用户已有的 Python、Chromium、Node 或 PowerShell。
