# 界鉴

界鉴用于验证 Vibe Coding Web 应用是否真正满足安全意图。当前核心链路是：

```text
安全意图 -> 可执行契约 -> 关系变异 -> 多面观察 -> 确认证据 -> 回归门禁
```

仓库已完成阶段 1 安全验证和阶段 2 基础链路：Runner 协议、SQLite 持久化、Job 控制面、隔离 Runner、原子工件发布与恢复。`run` 与 `ci` 提交持久 Job，由独立 Worker 启动 Runner；所有目标流量只由 Runner 进程发出。

第一次了解项目，依次阅读 [项目总览](docs/项目总览.md)、[架构说明](docs/架构说明.md)和[模块地图](docs/模块地图.md)。按开发、审查和比赛展示分类的完整入口见[文档导航](docs/README.md)。

## 环境

项目使用 Python 3.13 的 Conda 环境 `jiejian_env`：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\setup-conda.ps1
conda activate jiejian_env
jiejian --help
```

脚本使用环境内 pip 从 `pyproject.toml` 安装项目和开发依赖。`uv.lock` 只保留为未启用的兼容锁，不用于创建或运行环境。

## 当前入口

唯一安装的产品命令入口是 `jiejian`：

```powershell
jiejian doctor --json
jiejian project validate .\samples\fixed_apps\ownership\project.yaml
jiejian contract validate .\samples\fixed_apps\ownership\contract.yaml
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

`report <run_id>` 会校验已发布 manifest、文件哈希和数据库完成态。发布后提交失败的目录由 reconciliation 幂等补齐；旧 fencing token 和孤儿目录不能写完成态，只能进入受控 quarantine。当前仍没有 API、浏览器录制、GUI、LLM、插件或完整 HTML/SARIF/JUnit 报告。
