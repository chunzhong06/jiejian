# ADR-0036：Windows 启动与首次使用边界

- 状态：已接受
- 日期：2026-08-20
- 适用范围：`start.cmd`、PowerShell 准备、浏览器就绪和 onboarding

## 背景

普通用户需要一个稳定的 Windows 入口，同时首次使用的项目识别不能执行未知命令、联网扫描或读取秘密。启动准备、浏览器和本机服务失败时也必须可诊断、可恢复。

## 决策

根 `start.cmd` 是唯一默认双击入口，调用 `scripts/start.ps1`，完成六阶段运行环境检查、Python、Chromium、数据库和前端准备。Node.js 不再是用户必须预先安装的条件：产品只支持 Node 24 LTS，`product/frontend/package.json` 用 `engines.node` 声明可复用的 `>=24.13.0 <25` 系统版本，并用 `packageManager` 固定 pnpm `11.21.0`。系统 Node 缺失、不可执行或超出范围时，启动器从 Node.js 官方发布地址下载固定的 `v24.19.0` Windows 便携 ZIP，分别支持 x64 和 ARM64，并在解压前核对内置的官方 SHA-256：x64 为 `57f71ab3652e797d84acddc79c81cc9ff1c6ddb2a1974cdb83f00fee9bff4c73`，ARM64 为 `8502f4a50b458d4cc38ed8f2001556c2cd239d464920f74017926ccb1e1c157f`。

受控 Node 放在 `VarDir/runtime/node/24.19.0/<arch>/`。pnpm 由已确认的 Node 和项目声明的精确版本准备，Corepack home、pnpm home 和内容寻址 store 分别限制在 `VarDir/runtime` 与 `VarDir/cache/pnpm-store`；已安装的前端依赖继续使用 `product/frontend/node_modules` 和其默认 `.pnpm` 虚拟依赖目录，保证 TypeScript 与 Vite 按标准祖先链解析类型。不得调用 `corepack enable`、全局安装 pnpm、安装 MSI、修改注册表或永久修改 PATH。准备状态保存版本、架构、解析后的可执行路径和输入 fingerprint，并在复用前再次验证路径与版本。下载、校验或架构识别失败沿用启动失败页和稳定错误码，不执行未校验文件，也不牵连 Python、Chromium、数据库等无关缓存。

`VarDir` 按生命周期分成六类：根部 `jiejian.db/jobs/projects/reports/artifact-checks` 保持既有产品事实路径；`logs` 保存有界诊断；`runtime` 和 `cache` 可重建；`temp` 正常结束后应为空；`test` 只供仓库测试。自动下载的 uv 固定进入 `runtime/uv/0.11.12/<arch>/`，uv Python 环境和解释器分别进入 `runtime/python/env/` 与 `runtime/python/installations/`；启动状态进入 `cache/startup/`，pip requirements 投影进入 `cache/python/`，Node/uv 下载只在 `temp/downloads/` 创建并精确清理。不得再向 `%LOCALAPPDATA%\jiejian`、`VarDir` 根部或 `product/` 写入这些运行时。

启动器选择 Conda 或 uv 后立即以实际 `sys.executable` 和 `sys.prefix` 固定 Python 身份，清除调用者的 `PYTHONHOME/PYTHONPATH`，启用 `PYTHONNOUSERSITE`，并检查 `sys.path` 与关键依赖 origin 是否落入 Windows 用户级 site-packages。身份随最小环境传给 Worker，Worker 在组合根初始化前再次核对，避免主进程和 Worker 使用不同解释器。Playwright 浏览器固定到 `VarDir/runtime/playwright`；删除整个 `VarDir` 后，Python、Node、pnpm store、浏览器和准备状态均可按真源重建。

日志统一位于 `logs/`：主日志 `jiejian.log` 单文件上限 5 MiB 并保留 3 个备份，启动日志进入 `logs/startup/` 且最多保留 20 次，Worker 保持既有单 Job 有界轮换，Demo 使用 `logs/onboarding-demo.log` 并在新会话开始时重建。Demo 的最小项目 source 只在 `temp/onboarding-demo/<session>/source/` 存活，停止、切换、异常退出或关闭时清理，不删除已提交的 Run、Job 或 Evidence。

准备完成后，第一层交互入口用方向键和 Enter 提供“图形界面 / 命令行 / 仅完成环境准备”。进入“命令行”后再选择“引导模式（推荐） / 普通命令行 / 返回”；返回只回到第一层。两个菜单都把“↑ ↓ 选择    Enter 确认”固定放在选项下方，方向键只重画选项行，Enter 后光标进入 footer 下一行。RawUI 不可靠时只显示一次编号列表和对应的输入说明。图形界面继续执行 `serve --open`；普通命令行进入使用同一已准备 Python 解释器、项目模块、`VarDir` 和已确认 Node/pnpm PATH 的 PowerShell 子会话；仅准备直接成功退出。准备状态只保存非秘密事实和 fingerprint；配置与秘密不被启动器覆盖。

交互式 Windows 终端支持可靠 TrueColor 时，六行 `JIEJIAN` Banner 从上到下使用 `(0,102,153)`、`(0,126,174)`、`(0,151,194)`、`(32,174,211)`、`(82,197,226)`、`(145,222,239)`。无法确认 24 位色时退回单色 Cyan；重定向和自动化输出不包含 ANSI escape code。六阶段展示中每项只允许一个主结果节点，版本、缓存状态和数据库修订只作为该节点详情。

既有等待动画只覆盖真实外部等待：查找 Node.js、检查 pnpm、查找或验证 Python、准备 Python 依赖、检查或准备 Chromium、检查或升级本地数据、准备前端依赖、构建界面和启动界面。动画子进程延迟 130 ms 显示首帧，每个 Start 必须在 finally 中 Stop；重定向、CI 和非交互输出完全禁用动画，动画自身失败不得改变准备逻辑或错误码。

`serve` 的 ready 探针成功后必须立即停止“正在启动界面”动画，并在终端提示网页已打开、GUI 退出入口和 `Ctrl+C`。GUI 退出请求携带专用本地控制头并进入 Uvicorn/FastAPI shutdown；该链停止 Worker、Runner、受控浏览器和 ApplicationCore。直接关闭窗口时，系统释放 Serve 锁，Worker 根据随机 owner token 失配请求取消；下次启动用系统锁证明恢复过期任务，遗留 PID 文件不能阻塞启动或决定锁是否有效。

自动化和重定向输入场景必须显式选择 GUI、CLI 或 prepare 模式，不能依赖菜单。显式 CLI 模式直接进入普通命令行，不读取键盘。CLI 子会话直接调用启动时解析出的 Python 绝对路径，不为每条命令重复执行 Conda 或 uv wrapper；运行环境只影响该子进程，不永久写入 `PATH`、PowerShell profile 或系统环境变量。为兼容已有自动化，旧 `PrepareOnly` 入口继续映射到 prepare，冲突参数严格失败。

CLI 引导只调用 ApplicationCore 和现有 onboarding、Project、Contract、Execution、Recording 与 Result 能力，不保存第二套进度。首页固定使用“开始第一次权限检查 / 检查运行环境 / 录制业务流程 / 查看最近检查结果 / 打开图形界面 / 进入普通命令行 / 退出”。首次检查优先提供内置“存在权限问题 / 权限限制正常 / 证据不足”三种演示，演示仍经过普通 Contract、Profile、Job、Worker、Runner 和已发布结果链；真实应用需要复杂权限矩阵或流程编辑时，引导用户进入现有 `serve --open`，不要求普通用户手写 JSON 或内部标识。

CLI 的人类结果、机器结果和运行日志分开：Human 只在终端展示任务结果与恢复建议；`--json` 的 stdout 只有一个稳定 JSON 对象；CI 保持机器模式和既有退出码；脱敏结构化日志写入 `VarDir/logs/jiejian.log`。普通 CLI 命令不把 INFO 日志写到 stderr，Worker、Runner 和 serve 仍保留所需日志。Human 默认隐藏内部标识和复杂技术字段，只有 `--verbose` 展示有界技术详情，`--verbose` 不得与 `--json` 或 CI 混用。

失败输出固定包含失败阶段、稳定错误码、主要错误、日志位置和恢复建议。`scripts/start.ps1` 直接调用及显式非交互模式保持原始退出码且不等待；根 `start.cmd` 在 PowerShell 返回任意非零退出码后统一等待用户关闭窗口，并在等待结束后返回原始退出码。等待由最外层入口负责，因此参数绑定、模块加载或 PowerShell 内部展示失效也不会让双击窗口直接消失；自动化需要立即获得退出码时直接调用 `scripts/start.ps1`。

运行环境页面展示当前 Python、Node、pnpm、Playwright、前端依赖和本次自动恢复数量。任务失败面向普通用户展示阶段、原因、Job、日志位置与下一步，并生成可直接复制给 AI 的脱敏文本；堆栈只进入有界日志。

PowerShell 启动脚本统一保存为带 BOM 的 UTF-8，使 Windows PowerShell 5.1 在系统“Beta：使用 Unicode UTF-8”关闭时仍能确定性解析中文。`start.cmd` 保持无 BOM 且仅含 ASCII；代码页 65001 只负责后续控制台输入输出，不能让 `cmd.exe` 可靠解析 UTF-8 中文批处理字节，也不能替代 PowerShell 脚本文件的编码标记。

Onboarding 先让用户选择目录，再在 allowlist、深度、文件数和字节预算内只读识别。识别不运行目标命令、不联网、不读取源码正文或秘密；推断出的地址、身份、写操作和 reset 必须由用户确认。快速检查和演示仍走普通 Contract/Profile/ExecutionWorkflow。

## 理由与取舍

单一入口和受控前端运行时降低首次使用成本，准备后的明确分流兼顾普通用户、熟练用户和自动化。固定版本、官方校验和私有运行目录避免把系统环境修改变成隐含副作用；受限识别降低把未知仓库当作可执行脚本的风险。代价是首次准备可能需要网络和额外磁盘空间，真实应用仍需用户补充系统无法安全推断的信息。

## 影响

启动、下载校验、浏览器、运行环境、数据库、前端或项目识别失败时停止当前动作并提供日志和恢复路径；双击失败保持窗口可读，自动化失败仍可由退出码组合。onboarding 和 CLI 引导不创建第二套 Runner、Verification 或结果链。

## 迁移与兼容

启动脚本和准备状态只按当前运行时事实严格判断；旧 `var/startup` 状态、旧用户级 uv、旧环境或未知 revision 不猜测复用，也不让新旧路径长期并存。Node 24 线之外的系统版本即使更新也不自动接受，升级受控运行时、pnpm 或校验值必须同步修改 package 真源、本 ADR 和定向测试。产品入口仍只服务当前 Web Target。

## 相关真源

- [产品入口与控制面架构](../02_架构设计/产品入口与控制面架构.md)
- 根 [README.md](../../README.md)
- `start.cmd`、`scripts/start.ps1`、`scripts/startup/`
