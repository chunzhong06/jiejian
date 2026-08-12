# ADR-0019：Windows 首次使用与一键启动

- 状态：Accepted
- 日期：2026-08-12

## 决策

Windows 只保留根部 `start.cmd` 作为首次用户和双击入口；它是无业务判断的薄转发壳，调用唯一的 `scripts/start.ps1`。PowerShell 脚本先只读预检 Node.js 与 pnpm；Python 环境始终 Conda 优先，只有 Conda 不可用时才使用固定的 uv 0.11.12 fallback。uv 只能管理 Python，不能安装 Node 或 pnpm。

准备流程支持 `-PrepareOnly` 与 `-ForcePrepare`，统一执行依赖同步、Chromium、doctor、数据库迁移和前端构建；`var/startup/prepare-state.json` 只保存 schema_version=1 的非秘密阶段 SHA-256 fingerprint 与运行时事实，以目录内临时文件加原子替换写入。缺失、损坏或未知版本安全按冷准备处理；每个阶段仍检查环境、输出、Chromium、数据库 revision 等事实后才允许跳过。非准备模式最后以前台方式调用稳定产品入口 `jiejian serve --open`。失败使用稳定阶段码，诊断、恢复命令和日志路径同时输出，下载临时目录在脚本结束时精确清理。重复运行复用既有环境和缓存，不覆盖配置或秘密。

无 Conda 且无 uv 时，只从 Astral 固定的 [uv 0.11.12 release](https://releases.astral.sh/github/uv/releases/download/0.11.12/) 下载对应 Windows AMD64/ARM64 归档，并严格校验同名 SHA-256 文件；安装依据见 [uv 官方安装说明](https://docs.astral.sh/uv/getting-started/installation/)。不执行远程脚本、不修改 PowerShell profile 或系统 PATH。

## 影响

根部只保留 `start.cmd` 薄壳，`scripts/` 只保留 `start.ps1` 启动逻辑，不创建其他启动入口。调用链固定为 `start.cmd` → `scripts/start.ps1` → `jiejian serve --open`；`jiejian` CLI、API、Worker、Runner、Recording、Contract 和公共协议行为不变。Node/pnpm 仍是系统前置。锁文件使用 uv fallback 时必须 `uv lock --check` 与 `uv sync --locked --all-groups`，锁不一致不得自动改写 `uv.lock`。

`jiejian serve --open` 保持原有 CLI 参数，但浏览器线程只有在 Uvicorn 已启动后读取本机 `/ready`，并验证 HTTP 200、`schema_version="1"` 和 `status="ready"` 才打开浏览器；探针使用短超时、禁用代理、不携带凭据，10 秒失败不影响服务主进程。
