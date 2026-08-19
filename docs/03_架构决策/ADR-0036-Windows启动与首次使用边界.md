# ADR-0036：Windows 启动与首次使用边界

- 状态：已接受
- 日期：2026-08-19
- 适用范围：`start.cmd`、PowerShell 准备、浏览器就绪和 onboarding

## 背景

普通用户需要一个稳定的 Windows 入口，同时首次使用的项目识别不能执行未知命令、联网扫描或读取秘密。启动准备、浏览器和本机服务失败时也必须可诊断、可恢复。

## 决策

根 `start.cmd` 是唯一默认双击入口，调用 `scripts/start.ps1`，完成既有六阶段 Node/pnpm 预检、Python 运行环境、依赖、Chromium、数据库和前端准备。准备完成后，交互入口用方向键和 Enter 提供“图形界面 / 命令行 / 仅完成环境准备”：图形界面继续执行 `serve --open`；命令行进入使用同一已准备解释器、项目模块和 `VarDir` 的普通 PowerShell 子会话；仅准备直接成功退出。准备状态只保存非秘密事实和 fingerprint；配置与秘密不被启动器覆盖。

自动化和重定向输入场景必须显式选择 GUI、CLI 或 prepare 模式，不能依赖菜单。CLI 准备只影响子进程，不永久写入 `PATH`、PowerShell profile 或系统环境变量。为兼容已有自动化，旧 `PrepareOnly` 入口继续映射到 prepare，冲突参数严格失败。

失败输出固定包含失败阶段、稳定错误码、主要错误、日志位置和恢复建议。`scripts/start.ps1` 直接调用及显式非交互模式保持原始退出码且不等待；只有 `start.cmd` 发出的隐藏交互标记允许在错误和恢复信息完整输出后等待 Enter，避免双击窗口消失。该标记不得成为公共自动化模式。

PowerShell 启动脚本统一保存为带 BOM 的 UTF-8，使 Windows PowerShell 5.1 在系统“Beta：使用 Unicode UTF-8”关闭时仍能确定性解析中文。`start.cmd` 保持无 BOM 且仅含 ASCII；代码页 65001 只负责后续控制台输入输出，不能让 `cmd.exe` 可靠解析 UTF-8 中文批处理字节，也不能替代 PowerShell 脚本文件的编码标记。

Onboarding 先让用户选择目录，再在 allowlist、深度、文件数和字节预算内只读识别。识别不运行目标命令、不联网、不读取源码正文或秘密；推断出的地址、身份、写操作和 reset 必须由用户确认。快速检查和演示仍走普通 Contract/Profile/ExecutionWorkflow。

## 理由与取舍

单一入口降低首次使用成本，准备后的明确分流兼顾普通用户和命令行用户，受限识别降低把未知仓库当作可执行脚本的风险。代价是准备可能需要网络，且用户必须补充系统无法安全推断的信息。

## 影响

启动、浏览器、运行环境、数据库、前端或项目识别失败时停止当前动作并提供日志和手工恢复路径；双击失败保持窗口可读，自动化失败仍可由退出码组合。onboarding 不创建第二套 Runner、Verification 或结果链。

## 迁移与兼容

启动脚本和准备状态只按当前运行时事实严格判断；旧 prepare-state、旧环境或未知 revision 不猜测复用。产品入口仍只服务当前 Web Target。

## 相关真源

- [产品入口与控制面架构](../02_架构设计/产品入口与控制面架构.md)
- 根 [README.md](../../README.md)
- `start.cmd`、`scripts/start.ps1`、`scripts/startup/`
