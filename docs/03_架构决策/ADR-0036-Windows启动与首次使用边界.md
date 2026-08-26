# ADR-0036：Windows 启动与首次使用边界

- 状态：已接受
- 日期：2026-08-20
- 适用范围：`start.cmd`、PowerShell 准备、浏览器就绪和 onboarding

## 背景

普通用户需要一个稳定的 Windows 入口，同时首次使用的项目识别不能执行未知命令、联网扫描或读取秘密。启动准备、浏览器和本机服务失败时也必须可诊断、可恢复。

## 决策

根 `start.cmd` 是唯一默认双击入口，调用 `scripts/start.ps1`，完成六阶段运行环境检查、Python、Chromium、数据库和前端准备。Python 固定使用项目专用 Conda `jiejian_env`，由受控 uv 按 `uv.lock` frozen 同步并 editable 指向当前仓库。普通启动不安装或运行 Wheel，也不改写锁文件。

`scripts/dev.ps1 start` 仅作为开发者快捷入口薄转发到 `scripts/start.ps1 -Mode Gui`；它不再自行执行 `prepare → serve`。因此 `start.cmd`、直接调用 `start.ps1` 与 `dev.ps1 start` 只有一条产品启动编排，开发环境准备和普通用户启动展示仍保持职责分离。

Node/pnpm 只在 `var/runtime/frontend` 缺失或源码输入、配置、固定工具链构成的指纹变化时准备。前端以同一套“源码输入减明确生成物”同时计算指纹并镜像到 `VarDir/runtime/build/frontend-workspace`；pnpm 安装、TypeScript/Vite build 和 Vitest 都只在该工作区运行。内容寻址 store 进入 `VarDir/cache/pnpm-store`，Vite 缓存进入 `VarDir/cache/vite`，最终网页进入 `VarDir/runtime/frontend`。指纹与 `index.html` 同时命中时直接复用，不解析、下载或启动 Node/pnpm；命中路径仍清除源码树中旧设计遗留的明确生成物。

`VarDir` 按生命周期分成六类：`data` 保存数据库、Job、项目、报告等不可重建事实；`runtime` 保存 uv、Node/pnpm、Playwright、前端工作区与最终网页、Worker 和锁；`cache` 保存 uv、pnpm store、Vite、下载和启动缓存；`logs` 保存有界诊断；`temp` 正常结束后应为空；`test` 只供仓库测试。不得向 `%LOCALAPPDATA%\jiejian`、`VarDir` 根部或 `product/frontend` 写入安装/构建产物。

启动器准备 Conda 与 uv 后立即以实际 `sys.executable` 和 `sys.prefix` 固定 Python 身份，清除调用者的 `PYTHONHOME/PYTHONPATH`，启用 `PYTHONNOUSERSITE`，并检查 editable source root、`sys.path` 与关键依赖 origin。身份随最小环境传给 Worker，Worker 在组合根初始化前再次核对，避免主进程和 Worker 使用不同解释器。Playwright 浏览器固定到 `VarDir/runtime/playwright`；删除整个 `VarDir` 后，uv、Node/pnpm、前端、浏览器和准备状态均可按真源重建，但不删除全局项目 Conda 环境 `jiejian_env`，后续 prepare 只按 `environment.yml` 与 `uv.lock` 重新校准它。

日志统一位于 `logs/`：主日志 `jiejian.log` 单文件上限 5 MiB 并保留 3 个备份，启动日志进入 `logs/startup/` 且最多保留 20 次，Worker 保持单 Job 有界轮换。Sample Target 及其配置只位于 `samples/web`，由公开启动脚本和普通产品入口使用；产品运行时不创建 Sample 专用日志、临时源码、服务或状态。

准备完成后，第一层交互入口用方向键和 Enter 提供“图形界面 / 命令行 / 仅完成环境准备”。进入“命令行”后再选择“引导模式（推荐） / 普通命令行 / 返回”；返回只回到第一层。两个菜单都把“↑ ↓ 选择    Enter 确认”固定放在选项下方，方向键只重画选项行，Enter 后光标进入 footer 下一行。RawUI 不可靠时只显示一次编号列表和对应的输入说明。图形界面继续执行 `serve --open`；普通命令行进入使用同一已准备 Python 解释器、当前项目模块和 `VarDir` 的 PowerShell 子会话；仅准备直接成功退出。准备状态只保存非秘密事实和 fingerprint；配置与秘密不被启动器覆盖。

交互式 Windows 终端支持可靠 TrueColor 时，六行 `JIEJIAN` Banner 从上到下使用 `(0,102,153)`、`(0,126,174)`、`(0,151,194)`、`(32,174,211)`、`(82,197,226)`、`(145,222,239)`。无法确认 24 位色时退回单色 Cyan；重定向和自动化输出不包含 ANSI escape code。六阶段展示中每项只允许一个主结果节点，版本、缓存状态和数据库修订只作为该节点详情。

既有等待动画只覆盖真实外部等待：查找 Node.js、检查 pnpm、查找或验证 Python、准备 Python 依赖、检查或准备 Chromium、检查或升级本地数据、准备前端依赖、构建界面和启动界面。动画子进程延迟 130 ms 显示首帧，每个 Start 必须在 finally 中 Stop；重定向、CI 和非交互输出完全禁用动画，动画自身失败不得改变准备逻辑或错误码。

`serve` 只在 `/ready` 返回 HTTP 200、根版本 1 且 `status=ready` 后认定服务可用。等待约 10 秒只产生一次“启动时间较长，仍在准备”软提示并继续探测，不代表失败，也不得尝试浏览器；serve 在 ready 前退出形成独立启动失败。ready 成立后才尝试 `webbrowser.open()`，浏览器调用失败只表示需要手工访问已经立即可用的地址。Python 产生 `still-starting`、`ready-browser-opened`、`ready-browser-open-failed`、`startup-failed` 稳定事件，PowerShell 只负责展示。ready 成立后必须立即停止“正在启动界面”动画，并在终端提示网页退出入口和 `Ctrl+C`。

创建 ApplicationCore、Run 恢复、结果最终化和 Worker 启动保留在 readiness 关键路径；只处理缓存根直接临时项、过期 temp/test 顶层项和有界日志保留的 startup maintenance 移到关键路径完成后的受控后台任务。该任务由应用生命周期持有，关闭时明确等待，失败只进入现有启动诊断且不撤销 ready。完整 pnpm store、uv cache 等预算统计和 prune 只在用户查看状态或显式维护时执行，并在单次操作复用同一目录快照；普通启动不再递归扫描大型工具缓存，也不计算没有消费者的缓存摘要。启动诊断分别记录关键阶段、有界启动维护、ready 总耗时和浏览器调用耗时。

GUI 退出请求复用由根页面取得的当前 control session，并由统一门禁验证真实 `Host` 与精确同源 `Origin` 后进入 Uvicorn/FastAPI shutdown；不再使用可重放的静态控制头。该链停止 Worker、Runner、受控浏览器和 ApplicationCore。直接关闭窗口时，系统释放 Serve 锁，Worker 根据随机 owner token 失配请求取消；下次启动用系统锁证明恢复过期任务，遗留 PID 文件不能阻塞启动或决定锁是否有效。

自动化和重定向输入场景必须显式选择 GUI、CLI 或 prepare 模式，不能依赖菜单。显式 CLI 模式直接进入普通命令行，不读取键盘。CLI 子会话直接调用启动时解析出的 Python 绝对路径，不为每条命令重复执行 Conda 或 uv wrapper；运行环境只影响该子进程，不永久写入 `PATH`、PowerShell profile 或系统环境变量。不保留旧 `PrepareOnly` 兼容参数，自动化使用 `-Mode Prepare`。

CLI 引导只调用 ApplicationCore 和现有 onboarding、Project、Contract、Execution、Recording 与 Result 能力，不保存第二套进度。首页固定使用“开始第一次权限检查 / 检查运行环境 / 录制业务流程 / 查看最近检查结果 / 打开图形界面 / 进入普通命令行 / 退出”。仓库 Sample 的 fixed、vulnerable、inconclusive 三种变体从 `samples/web` 通过普通 Contract、Profile、Job、Worker、Runner 和已发布结果链运行；产品不根据变体或 truth 特判结论。真实应用需要复杂权限矩阵或流程编辑时，引导用户进入现有 `serve --open`，不要求普通用户手写 JSON 或内部标识。

CLI 的人类结果、机器结果和运行日志分开：Human 只在终端展示任务结果与恢复建议；`--json` 的 stdout 只有一个稳定 JSON 对象；CI 保持机器模式和既有退出码；脱敏结构化日志写入 `VarDir/logs/jiejian.log`。普通 CLI 命令不把 INFO 日志写到 stderr，Worker、Runner 和 serve 仍保留所需日志。Human 默认隐藏内部标识和复杂技术字段，只有 `--verbose` 展示有界技术详情，`--verbose` 不得与 `--json` 或 CI 混用。

失败输出固定包含失败阶段、稳定错误码、主要错误、日志位置和恢复建议。`scripts/start.ps1` 直接调用及显式非交互模式保持原始退出码且不等待；根 `start.cmd` 在 PowerShell 返回任意非零退出码后统一等待用户关闭窗口，并在等待结束后返回原始退出码。等待由最外层入口负责，因此参数绑定、模块加载或 PowerShell 内部展示失效也不会让双击窗口直接消失；自动化需要立即获得退出码时直接调用 `scripts/start.ps1`。

运行环境页面展示当前 Python、Node、pnpm、Playwright、前端依赖和本次自动恢复数量。任务失败面向普通用户展示阶段、原因、Job、日志位置与下一步，并生成可直接复制给 AI 的脱敏文本；堆栈只进入有界日志。

PowerShell 启动脚本统一保存为带 BOM 的 UTF-8，使 Windows PowerShell 5.1 在系统“Beta：使用 Unicode UTF-8”关闭时仍能确定性解析中文。`start.cmd` 保持无 BOM 且仅含 ASCII；代码页 65001 只负责后续控制台输入输出，不能让 `cmd.exe` 可靠解析 UTF-8 中文批处理字节，也不能替代 PowerShell 脚本文件的编码标记。

Onboarding 先让用户选择目录，再在 allowlist、深度、文件数和字节预算内只读识别结构化配置元数据。基础识别不运行目标命令、不联网、不读取普通源码正文或秘密。系统可以从 OpenAPI、显式 IPv4 loopback 配置、启动参数字面量和已识别框架的有限默认端口产生候选，并以小超时、请求数和响应体预算探测 `127.0.0.1`；不扫描任意端口，不跟随离开 loopback 的重定向，最终地址必须由用户确认。

普通源码正文只有在用户确认 endpoint 后再次明确授权才可读取。源码理解拒绝 reparse point 逃逸，跳过秘密和生成目录，限制深度、文件数、单文件与总字节，不 import、eval、exec、启动项目子进程或联网；长期只保存相对路径、行号、符号、detector 和 hash 等结构证据。普通开始检查与 Sample 仍走唯一 Contract/Profile/ExecutionWorkflow，应用理解候选不得旁路该安全链；旧版手工快速检查不保留兼容入口。

## 理由与取舍

单一源码入口和受控前端运行时降低首次使用成本，准备后的明确分流兼顾普通用户、熟练用户和自动化。固定版本、官方校验、editable 当前仓库身份和私有运行目录避免把旧安装或系统环境修改变成隐含副作用；受限识别降低把未知仓库当作可执行脚本的风险。代价是首次准备可能需要网络和额外磁盘空间，真实应用仍需用户补充系统无法安全推断的信息。

## 影响

启动、下载校验、浏览器、运行环境、数据库、前端或项目识别失败时停止当前动作并提供日志和恢复路径；双击失败保持窗口可读，自动化失败仍可由退出码组合。onboarding 和 CLI 引导不创建第二套 Runner、Verification 或结果链。

## 迁移与兼容

启动脚本和准备状态只按当前运行时事实严格判断；旧 `var/startup` 状态、旧用户级 uv、旧环境或未知 revision 不猜测复用，也不让新旧路径长期并存。官方 prepare 精确删除旧设计遗留的 `product/frontend/node_modules`、`product/frontend/dist` 和 `product/frontend/tsconfig.tsbuildinfo`；可选 package 只把 `var/runtime/frontend` 映射进 Wheel。产品入口仍只服务当前 Web Target。

## 相关真源

- [产品入口与控制面架构](../02_架构设计/产品入口与控制面架构.md)
- 根 [README.md](../../README.md)
- `start.cmd`、`scripts/start.ps1`、`scripts/startup/`
