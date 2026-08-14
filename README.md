# 界鉴

界鉴用于验证 Vibe Coding Web 应用是否真正满足安全意图。核心链路是：

```text
安全意图 -> 可执行契约 -> 关系变异 -> 多面观察 -> 确认证据 -> 回归门禁
```

阶段 0～6 已完成 Runner 协议、持久化 Job、隔离执行、录制审阅、Contract 治理、回环 API、React GUI、结果发布恢复、测试/样例/Schema、Windows 启动资产，以及复杂权限关系、确定性覆盖、Observer V2、多面观察和 V2 Evidence/Result 闭环。所有主动目标与观察流量仍只由独立 Runner 隔离域发出。

第一次使用先看本文，再看[项目设计规范](docs/01_开发规范/项目设计规范.md)、[开发路线图](docs/04_开发记录/开发路线图.md)和 [ADR 索引](docs/02_技术决策/README.md)。

## 首次使用

Windows 唯一入口是根部薄转发壳：

```bat
.\start.cmd
```

它调用 `scripts/start.ps1`。准备过程会检查并准备 Python 依赖、Chromium、doctor、数据库迁移和前端构建，日志写入 `var/logs/`；Node.js 与 pnpm 是系统前置，不由 Python 环境安装。

准备状态按内容 SHA-256 指纹记录在 `var/startup/prepare-state.json`，命中时跳过缓存阶段，`-ForcePrepare` 强制重做。服务仅在本机 `/ready` 返回 `schema_version="1"`、`status="ready"` 后尝试打开浏览器。

只准备不启动服务：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\start.ps1 -PrepareOnly
```

`-PrepareOnly` 不会修改当前 PowerShell 父 shell。准备成功后，手工 CLI 使用脚本输出的 Conda 或 uv 命令；普通 GUI 启动仍推荐 `.\start.cmd`。

## 当前入口

唯一安装的产品命令入口是 `jiejian`：

```powershell
jiejian doctor --json
jiejian project validate .\samples\fixed_apps\ownership\project.yaml
jiejian contract workspace .\samples\fixed_apps\ownership\project.yaml
jiejian contract derive .\samples\fixed_apps\ownership\project.yaml --include-flow
jiejian run .\samples\fixed_apps\ownership\project.yaml --contract .\samples\fixed_apps\ownership\contract.yaml
jiejian report <run_id> --format json
jiejian ci .\samples\fixed_apps\ownership\project.yaml
jiejian serve --open
```

录制入口示例：

```powershell
jiejian recording start .\samples\fixed_apps\ownership\project.yaml --identity owner
jiejian recording status <recording_id>
jiejian recording review <recording_id> --command .\review.json
jiejian recording finalize <recording_id>
jiejian recording replay <recording_id> --project .\samples\fixed_apps\ownership\project.yaml --runs 3
```

## 黄金样例

本机样例应用：

```powershell
python -B -m jiejian.sample_app --variant safe --port 8765
python -B -m jiejian.sample_app --variant vulnerable --port 8766
```

safe 预期 `PASS`/退出码 0，vulnerable 预期 `BLOCK`/退出码 1；缺少必要观察时为 `INCONCLUSIVE`/退出码 2。三套自包含 bundle 位于 `samples/fixed_apps/ownership/`、`samples/vulnerable_apps/ownership/` 和 `samples/inconclusive_apps/ownership/`。不要临时修改样例或写入真实秘密。

## 排错

- 首次准备失败：查看 `var/logs/` 阶段日志，按输出的恢复命令重试；需要强制重做时使用 `-ForcePrepare -PrepareOnly`。
- 服务未打开浏览器：确认 `frontend/dist/index.html` 存在，并确认 `/ready` 返回 `schema_version="1"` 和 `status="ready"`。
- CLI 未找到：使用准备脚本输出的 `conda run ... jiejian` 或 uv 命令；`-PrepareOnly` 不会改变父 PowerShell。
- 结果读取失败：不要手工修改 `var/`；`report` 会校验 publication manifest、文件哈希和数据库完成态。

协议、Schema、迁移和安全边界分别以 `docs/03_协议定义/`、`schemas/`、`backend/migrations/` 和[项目设计规范](docs/01_开发规范/项目设计规范.md)为准。
