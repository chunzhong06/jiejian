# 界鉴

界鉴用于验证 Vibe Coding Web 应用是否真正满足安全意图。当前核心链路是：

```text
安全意图 -> 可执行契约 -> 关系变异 -> 多面观察 -> 确认证据 -> 回归门禁
```

仓库已完成阶段 0～5 及阶段 5.6 工程与联调：Runner 协议、SQLite 持久化、Job 控制面、隔离 Runner、录制审阅、Contract 治理、FastAPI、React GUI、SSE、Results 读取、原子工件发布与恢复、测试/样例/Schema/启动资产，以及三层解释体系均已落地。`run`、API 和 GUI 提交同一类持久 Job，由独立 Worker 启动 Runner；所有目标流量只由 Runner 进程发出。阶段 6/7 尚未开始。

第一次了解项目，依次阅读 [项目总览](docs/项目总览.md)、[架构说明](docs/架构说明.md)和[模块地图](docs/模块地图.md)。按开发、审查和比赛展示分类的完整入口见[文档导航](docs/README.md)。

## 环境

首次使用 Windows 时，唯一入口是根部薄转发壳：

```bat
.\start.cmd
```

它只转发到 `scripts/start.ps1`，不包含环境判断。PowerShell 逻辑优先复用或创建 Conda `jiejian_env`，无 Conda 时才使用固定版本的 uv；Node.js 与 pnpm 是独立系统前置，不由 Python 环境安装。准备过程会执行依赖、Chromium、doctor、数据库迁移和前端构建，日志写入 `var/logs/`（可用参数指定）。

准备状态按内容 SHA-256 指纹记录在 `var/startup/prepare-state.json`，有效命中时跳过缓存阶段，`-ForcePrepare` 强制重做；迁移缓存必须与当前 revision 一致，失败会显示日志、退出码和恢复命令。

进阶或自动化场景可直接调用 PowerShell：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\start.ps1 -PrepareOnly
```

默认流程最后调用稳定入口 `jiejian serve --open`；服务仅在本机 `/ready` 返回 `schema_version="1"`、`status="ready"` 后尝试打开浏览器；`-PrepareOnly` 只准备环境，不启动长驻服务。
`-PrepareOnly` 不会激活或修改当前 PowerShell 父 shell。手工 CLI 演示请使用脚本成功输出的后续命令：Conda 使用 `conda run --no-capture-output --name jiejian_env jiejian <命令>`，uv 使用输出的 uv 可执行文件配合 `run --locked --no-sync jiejian <命令>`；也可以先显式执行 `conda activate jiejian_env`，再使用下方的短命令。普通 GUI 启动仍只推荐 `.\start.cmd`。

## 当前入口

唯一安装的产品命令入口是 `jiejian`：

```powershell
jiejian doctor --json
jiejian project validate .\samples\fixed_apps\ownership\project.yaml
jiejian contract validate .\samples\fixed_apps\ownership\contract.yaml
jiejian contract workspace .\samples\fixed_apps\ownership\project.yaml
jiejian contract derive .\samples\fixed_apps\ownership\project.yaml --include-flow
jiejian run .\samples\fixed_apps\ownership\project.yaml --contract .\samples\fixed_apps\ownership\contract.yaml
jiejian report <run_id> --format json
jiejian ci .\samples\fixed_apps\ownership\project.yaml
```

本机黄金样例入口保持为：

```powershell
python -B -m jiejian.sample_app --variant safe --port 8765
python -B -m jiejian.sample_app --variant vulnerable --port 8766
```

safe 预期 `PASS`/退出码 0，vulnerable 预期 `BLOCK`/退出码 1；缺少必要观察时为 `INCONCLUSIVE`/退出码 2。

阶段 2.1 的生产建库入口是 `jiejian.storage.upgrade_database()`，默认数据库路径为 `<var_dir>/jiejian.db`。持久请求和 attempt staging 位于 `<var_dir>/jobs/<job_id>/`；验证通过的完整 staging 原子发布到 `<var_dir>/projects/<project_id>/runs/<run_id>/`，随后才写数据库完成态。真实秘密只进入当前 Runner 的最小环境。

`report <run_id>` 会校验已发布 manifest、文件哈希和数据库完成态。发布后提交失败的目录由 reconciliation 幂等补齐；旧 fencing token 和孤儿目录不能写完成态，只能进入受控 quarantine。当前已提供 `jiejian serve --open` 本地回环控制面、项目来源重新校验、显式 ACTIVE Contract 选择、Contract 治理工作台 REST、Recording/Run API、SSE、Finding/Evidence/JSON 报告读取和 React GUI。录制仍使用独立 Worker/Runner、脱敏事件和 FlowDraft 审阅；`replay` 默认连续执行三次，每次使用新的隔离会话。Contract CLI 与 GUI 均复用工作台；默认 LLM 保持离线，显式 YAML 入口继续兼容。阶段 5.6 增加模型服务 profile 设置、显式测试连接、真实 API/Worker/浏览器/LLM 状态观察和候选联调，但模型只能生成待审 Candidate，不能激活契约或决定 Verdict；API Key 不进入数据库、响应、日志或浏览器存储。

启动本地产品：

```powershell
jiejian serve --open
```

启动前需要先完成前端生产构建，使 `frontend/dist/index.html` 可读；`serve` 不会自动安装依赖或构建前端。也可以用 `--frontend-dir <dist目录>` 指定静态资源目录。

录制入口示例：

```powershell
jiejian recording start .\samples\fixed_apps\ownership\project.yaml --identity owner
jiejian recording status <recording_id>
jiejian recording review <recording_id> --command .\review.json
jiejian recording finalize <recording_id>
jiejian recording replay <recording_id> --project .\samples\fixed_apps\ownership\project.yaml --runs 3
```
