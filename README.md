# 界鉴 JIEJIAN 1.0.3

> 界鉴是一款面向 AI 快速开发 Web 应用的权限安全检查工具，用来确认不同身份是否真的只能访问和操作自己有权限的数据与业务功能。

应用可能返回“禁止访问”，但真实数据或后台状态仍可能发生变化。界鉴结合接口结果和真实副作用判断权限是否真正生效，而不是只看一个 HTTP 状态码。

## Windows 源码快速启动

在 Windows 上进入项目根目录运行：

```bat
.\start.cmd
```

启动器会准备或复用项目专用 Conda 环境 `jiejian_env`，由仓库受控 uv 按 `uv.lock` 精确同步并 editable 指向当前源码。uv、Node、pnpm、Playwright、下载缓存、前端依赖工作区和不可变网页 build 统一复用 `var/development/`；每个实际 `-VarDir` 只接收自己的数据库、Source Receipt 和 `runtime/frontend` 副本。普通源码变化只生成新的 build，不重复安装未变化的依赖。全部开发资产和运行数据都留在本地 `var/`，不进入 Git，也不修改系统 PATH 或全局安装；首次准备需要网络。

## Windows x64 Portable

正式便携版解压后直接运行包根 `start.cmd`。Portable 已包含固定 CPython、界鉴 1.0.3、前端和 Playwright Chromium；启动时不需要 Conda、uv、pip、Node、pnpm、源码仓库或网络，运行数据只写入发行目录自己的 `var/`。

- `JieJian-WebV1-1.0.3-Windows-x64.zip`：完整产品，包含官方“协作空间” Sample。
- `JieJian-WebV1-1.0.3-Windows-x64-nosamples.zip`：完整产品，不包含官方 Sample。
- `SHA256SUMS.txt`：两个 ZIP 的固定 SHA256 校验和。

两个 ZIP 除 `samples/` 外的产品文件完全相同。发行目录可以整体移动到中文或带空格路径；版本可在“运行环境”设置页或 `jiejian --version` 查看。开发者构建与仓库外验收见[修改发布与便携版](docs/02_开发指南/任务/修改发布与便携版.md)。

## 界面预览

界面围绕工作台、应用接入、测试账号、业务流程、权限规则、开始检查和检查结果组织。

<!-- 后续仅在真实运行 GUI 并有可靠数据后，在此放置工作台或检查结果截图。当前不添加图片链接。 -->

## 界鉴能做什么

- 定义权限规则，明确不同身份可以做什么。
- 执行 Web 应用权限安全检查。
- 查看接口结果、真实副作用和其他证据。
- 查看历史变化与回归情况。
- 导出检查报告，供交付和自动化使用。

## 快速开始

1. 获取项目并打开项目根目录。
2. 运行 `.\start.cmd`。
3. 等待界鉴准备源码运行环境、浏览器、数据库和前端资源；Node/pnpm 只会在前端需要重建时出现。
4. 选择图形界面、命令行或仅完成环境准备。

启动脚本会按“工具链、Python、浏览器、界面、本地数据、启动”六个真实阶段持续显示当前任务和耗时，并自动准备 Conda + uv.lock + editable 当前源码、浏览器、数据库和前端资源；准备完成后，控制台会给出适用于本机的 CLI 调用方式。Portable 只可通过 `./scripts/dev.ps1 package` 独立生成，不参与普通源码启动。

## 第一次使用

默认从工作台开始，按下面的路径完成第一次检查：

1. **应用接入**：选择应用目录；界鉴先寻找本地回环地址，由你确认后再单独授权只读源码分析，并审阅带来源的角色与关键操作候选。
2. **测试账号**：为已确认角色登记可读账号，并在独立浏览器中自行登录；界鉴不保存密码，只在你明确确认后保存当前目标所需的有限 Cookie 或 Bearer 状态。
3. **业务流程**：录制需要检查的关键业务动作。
4. **权限规则**：说明不同身份允许执行的操作，以及哪些操作必须被阻止。
5. **开始检查**：查看当前将检查的业务动作、身份差分和覆盖缺口，确认后执行真实权限安全检查并收集证据；普通流程不要求选择内部执行配置。
6. **检查结果**：查看结论、问题、证据和报告。

模型服务和运行环境维护属于高级能力。应用接入发现的角色与动作始终只是候选，不会自动生成允许/拒绝结论；旧版手工快速检查和 Profile 注册入口已经删除，不保留第二套新手或内部配置入口。

如果暂时没有准备自己的应用，可以从 GUI“评委导览”启动唯一官方 Sample“协作空间”。同一个应用、项目负责人 Alice、普通成员 Bob 和同一个“生成完整项目资料包”动作，分别运行在漏洞、修复和关键观察受限三种真实状态中，经正常 Worker/Runner、六面观察和确定性判断形成 `BLOCK`、`PASS`、`INCONCLUSIVE`；Sample 不预制 Verdict，也不绕过应用接入或权限治理。开发入口见 [`samples/README.md`](samples/README.md)。

## 结果怎么看

界鉴不会把“接口返回禁止访问”直接当作安全结论。例如：

```text
服务返回：403 禁止访问
真实观察：数据或后台状态已经发生变化
界鉴判断：发现可能的权限越界
```

结果含义如下：

| 结果           | 含义                         |
| -------------- | ---------------------------- |
| `PASS`         | 当前规则覆盖范围内未发现越权 |
| `BLOCK`        | 发现可能的权限越界，需要处理 |
| `INCONCLUSIVE` | 证据不足，暂时不能下结论     |

在检查结果中，可以继续查看执行路径、真实证据和完整报告。执行路径只从冻结请求与已发布 Evidence 还原实际发生的身份、权限检查、后台任务和最终产物；证据不完整时只展示已经确认的节点，不补画未知步骤，也不改变后端 Verdict。`INCONCLUSIVE` 不表示安全，也不表示未发现问题；执行失败或结果完整性无效会作为独立失败状态展示，不冒充第四种安全结论。

## 命令行与自动化

命令行是与图形界面共享同一应用状态、检查和结果服务的第二控制入口。准备完成后，按启动输出给出的本机 CLI 调用方式执行；下面的 `jiejian` 代表产品 CLI：

```powershell
jiejian status
jiejian check preview <project_id>
jiejian result show --project <project_id>
jiejian --json status
jiejian --version
```

全局 `--human` 用于人类可读输出，`--verbose` 只追加技术引用，`--json` 输出版本化 Machine envelope。普通命令围绕 `status / app / account / flow / check / result / history / settings / system` 组织，不保留旧 Profile、Contract、Recording、Baseline、Gate 或 run-profile 命令树。GUI 正在管理同一 `var` 时，CLI 会拒绝创建第二个控制者。

## 高级能力

需要更细控制时，可以使用模型服务、运行环境、原始证据查看和自动化/CI。它们服务于已经明确检查范围的用户，不改变第一次使用的主路径；业务流程仍是普通检查主路径的一部分。

### AI 工具连接（MCP）

界鉴可以通过同一个本地 Web 进程提供 MCP Streamable HTTP 控制入口。打开模型与 AI 设置中的“AI 工具连接（MCP）”完成一次首次配对后，长期 Token 会进入 Windows Credential Manager；以后启动界鉴会自动恢复只读连接。该 Token 与模型供应商 API Key、浏览器控制 Cookie 相互独立，普通状态、日志和报告都不会返回正文。

长期 Token 只恢复连接和默认 `READ`，可读取产品状态、项目、应用理解、身份、业务流程、检查预览、结果、证据索引、历史和系统状态。需要修改已有候选或准备检查时，必须在页面中按应用确认 `PREPARE`；需要启动或停止受控任务时，再按应用确认 `EXECUTE`。这些提升只属于当前 serve，每次启动都要重新授权。

Codex 固定使用 server name `jiejian`、endpoint `http://127.0.0.1:8765/mcp` 和环境变量 `JIEJIAN_MCP_TOKEN`：

```powershell
codex mcp add jiejian `
  --url "http://127.0.0.1:8765/mcp" `
  --bearer-token-env-var JIEJIAN_MCP_TOKEN
```

DSH 固定使用 `@deepseek-ai/dsh-mcp-client` 的 `streamable-http`，并从 `process.env.JIEJIAN_MCP_TOKEN` 形成 Authorization Bearer；完整可复制 composition 在 GUI 的 DSH 页签。轮换 Token 后只需更新该环境变量并让新客户端进程重新读取，不必重新添加 server；“暂停本次连接”保留长期配对，“忘记此连接”才会从 Credential Manager 彻底撤销配对。

MCP 只复用现有 ApplicationCore、Worker 和确定性结果投影，不建立第二套业务状态，也不把秘密、源码、请求正文、完整日志或完整 Evidence 暴露给工具。它是 Web 产品的本地控制入口，不是受检的 MCP/Agent Target。

## 官方示例

仓库内只保留一个官方 Web Sample：“协作空间——项目资料管理应用”。它用项目负责人 Alice、普通成员 Bob 和同一个“生成完整项目资料包”动作，真实形成漏洞、修复和关键观察受限三种运行状态；Sample 本身不预制 Verdict。

普通用户可以从 GUI 的“评委导览”启动官方示例并完成接入、Recording、权限准备和检查。开发者需要了解 Sample 的业务撤销、测试重置、六面观察或联调入口时，从 [Samples 说明](samples/README.md) 开始；需要修改 Sample 或唯一自动 L5 时，阅读[修改官方示例与整链验收](docs/02_开发指南/任务/修改官方示例与整链验收.md)。

阶段收口使用 `powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File .\scripts\dev.ps1 sample-test` 完成唯一自动 L5 技术验收。它从真实 `start.cmd` 启动隔离实例，验证正式 GUI、独立 Worker/Recording/Runner、headed Chromium、三态结果、GUI/CLI 等价、报告历史和安全退出。比赛前另做“展示验收”，只判断视觉、窗口体验、文案和演示节奏，不重复技术 L5。

## 遇到问题

- **启动失败**：`start.cmd` 会保留错误窗口；先查看屏幕上的失败阶段和恢复建议，再按需查看 `var/logs/startup/` 中最近的启动日志。
- **浏览器未打开**：只有终端明确提示“界鉴已经启动，但未能自动打开网页”时，才手工打开 [http://127.0.0.1:8765/](http://127.0.0.1:8765/)；“仍在准备”表示服务尚未 ready，需要继续等待或按 `Ctrl+C` 退出。
- **运行环境不可用**：按启动输出恢复。`jiejian system clean assistant|logs|temporary|all` 先预览再确认清理对应可删除内容，`jiejian system repair` 独立修复损坏运行时；这些操作不会删除应用、权限配置、数据库、证据、报告或凭据。删除整个 `var/` 表示从零重建仓库本地运行态，也会删除其中的产品事实，但不会删除全局项目 Conda 环境 `jiejian_env`。
- **检查无法开始**：确认已经完成应用接入，目标使用授权的回环地址，权限规则已准备好，运行环境状态正常。

`-Mode Prepare` 和 `-ForcePrepare` 仅用于高级恢复，不是正常启动流程。

## 适用范围

当前界鉴只检查 Web 应用，并要求目标处于用户明确授权的范围内。它不把本地命令行应用或 MCP/Agent 目标作为当前支持范围；本地 MCP 只用于控制现有 Web 产品能力。

## 更多文档

- [开发知识库入口](docs/README.md)：按任务路由到系统地图、开发指南、参考手册、工程约束和设计依据。
- [系统全景](docs/01_系统地图/系统全景.md)：模块化单体、ApplicationCore 和执行边界。
- [Runner 执行协议](docs/03_参考手册/协议/Runner执行协议.md)：Worker、Runner、Evidence 和发布边界。
- [ADR 与设计依据](docs/05_设计依据/)：仍约束当前实现的长期决策。
- [开发指南](docs/02_开发指南/)：按任务进入当前实现、边界与直接验证。
- [修改官方示例与整链验收](docs/02_开发指南/任务/修改官方示例与整链验收.md)：协作空间、Recording UIA、自动 L5 与失败收口。

深入技术内容以这些现有文档为准；后续文档入口调整时，再同步更新本页链接。
