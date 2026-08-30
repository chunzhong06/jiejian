# 界鉴 JIEJIAN 1.0.5

> 面向 Vibe Coding 的权限意图验证与断裂诊断系统。

人定义权限边界；Agent 可以改代码和提建议，但不能改写权限考题；界鉴观察真实后果，并定位第一次权限断裂。

## 为什么不能只看 403

在官方“协作空间”故事里，普通成员 Bob 请求生成完整项目资料包。页面和接口先返回 `403`，但请求已经创建 Task、进入 Queue、被 Worker 继续处理，最终 ZIP 仍然生成。界鉴把这条真实链路判为：

```text
403 → Task → Queue → Worker → ZIP
BLOCK / AUTHORIZATION_LATE
```

表面拒绝不等于真实副作用被阻止。界鉴同时核对服务响应、实际身份、权限决定、后台执行和最终业务结果。

## 三项核心能力

1. **人的权限意图**：由人明确哪些账号应该允许或拒绝哪些业务动作，Agent 只能提出待审建议。
2. **真实效果验证**：通过受控浏览器、隔离 Runner 和可信观察确认资源最终发生了什么。
3. **权限断裂诊断**：从已发布证据中定位权限要求第一次失效的位置，不用状态码猜结论。

## 人、Agent 与界鉴的职责

| 参与者 | 可以做什么 | 不能做什么 |
| --- | --- | --- |
| 人 | 确认权限组、业务动作、ALLOW/DENY 与实现映射 | 不适用 |
| Agent | 分析代码、提交建议、准备并执行已批准的检查 | 批准权限变化、退休人的要求或改变安全结论 |
| 界鉴 | 冻结人的考题、执行真实验证、形成 PASS/BLOCK/INCONCLUSIVE 与断裂诊断 | 用模型或表面响应替人决定权限 |

## AI 工具连接

GUI 顶部的“AI 工具”进入独立 `/tools` 页面，可连接 Codex、DSH 或其他 MCP 客户端。长期凭据只保存在 SecretStore/Windows Credential Manager；界鉴不会写 `token.json`，也不会自动修改 Codex 配置。

权限分为 `READ / PREPARE / EXECUTE`。`PREPARE` 可重新分析源码、提交建议并准备已经批准的检查；`EXECUTE` 可启动或停止受控任务。两者都不能批准权限变化。

Codex 使用固定端点 `http://127.0.0.1:8765/mcp` 和用户显式配置的 `JIEJIAN_MCP_TOKEN`：

```powershell
codex mcp add jiejian `
  --url "http://127.0.0.1:8765/mcp" `
  --bearer-token-env-var JIEJIAN_MCP_TOKEN
```

Agent 完成代码修改后，可以提交一条有界的变化说明。界鉴会重新分析已经授权的源码，以服务端看到的真实文件变化为准，再判断哪些现有权限要求需要重验。Agent 不能自行指定权限、用例或安全结论；实现映射有疑问时，检查会停在权限页，等人确认后再继续。

```text
Agent 提交变化说明
→ 界鉴重算真实文件变化
→ 关联现有权限要求
→ 必要时由人复核实现映射
→ 按当前完整检查范围重新验证
→ 在结果与历史中标记代码变化重验
```

## 完成一次检查

1. 选择应用目录，确认本地地址并授权只读源码分析。
2. 确认业务权限组和关键业务动作。
3. 为权限组准备测试账号；密码始终由用户在独立浏览器中输入。
4. 演示一次业务动作；界鉴自动整理业务含义，只在真实歧义时请用户选择。
5. 缺独立验证或恢复方法时，按页面提示补录对应操作；补录不创建新业务 Flow 或权限要求。
6. 人在权限页确认谁应该允许或拒绝，然后启动受控检查。
7. 在结果和历史中查看真实效果、断裂位置和变化轨迹。

后续代码有变化时，不需要重建一套权限规则。Agent 提交变化说明后，界鉴沿用人的长期权限意图，重新确认实现映射并冻结本次重验上下文。

## 三态结果

| 结果 | 含义 |
| --- | --- |
| `PASS` | 当前已执行规则与可用证据范围内未发现确认问题 |
| `BLOCK` | 已确认权限要求与真实效果冲突 |
| `INCONCLUSIVE` | 必需证据不足，不能说安全，也不能确认漏洞 |

执行失败和结果完整性无效是独立状态，不冒充第四种安全结论。

## 官方 Sample

仓库只保留一个官方 Web Sample：“协作空间：项目资料管理应用”。Alice、Bob 和“生成完整项目资料包”这一业务动作会分别呈现漏洞、修复、关键观察受限三种状态，不预制 Verdict。普通用户可从工作台启动“评委导览”；开发说明见 [Samples 说明](samples/README.md)。

## 启动界鉴

Windows 源码仓库在项目根目录运行：

```bat
.\start.cmd
```

启动器按锁文件准备项目专用环境、Chromium、数据库和前端资源，运行数据只写入 `var/`。首次准备需要网络；后续复用未变化依赖。

仓库支持构建 Windows x64 Portable，目前没有已发布的 GitHub Release。开发者按[修改发布与便携版](docs/02_开发指南/任务/修改发布与便携版.md)在仓库外验收构建产物。

## CLI 与 Machine 自动化

CLI 只保留有独立非交互价值的控制任务：

```text
status / serve
app list/show/remove
check preview/prepare/run/cancel
result show/reports/report
history show
system doctor/repair/clean
```

示例：

```powershell
jiejian status
jiejian check preview <project_id>
jiejian result show --project <project_id>
jiejian --json status
```

人类模式只输出业务语言；完整稳定结构使用 `--json`；诊断使用 `system doctor`。首次应用接入、登录与 Recording 只在 GUI 完成，Agent 自动化使用 MCP。

## 当前范围

界鉴当前只检查用户明确授权的本机 Web 应用。被测 CLI、MCP/Agent Target、主动探针、自动修复和第二应用不在当前范围；本地 MCP 只是现有 Web 产品的控制入口。

## 开发文档

- [开发知识库入口](docs/README.md)
- [系统全景](docs/01_系统地图/系统全景.md)
- [权限验证与结果](docs/01_系统地图/权限验证与结果.md)
- [修改 Agent 变更影响](docs/02_开发指南/任务/修改Agent变更影响.md)
- [Runner 执行协议](docs/03_参考手册/协议/Runner执行协议.md)
- [修改官方示例与整链验收](docs/02_开发指南/任务/修改官方示例与整链验收.md)
