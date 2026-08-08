# 界鉴

当前仓库只完成了初步开发计划的“阶段 0：工程骨架与不变量”。现有能力包括配置加载、最小领域状态机、结构化日志基础、统一脱敏、`jiejian` CLI 和 `doctor` 自检。

## 环境与安装

- Python 3.12 或更高兼容版本
- uv

在项目根目录执行：

```powershell
uv sync
uv run jiejian --help
```

## 当前可用命令

```powershell
uv run jiejian doctor
uv run jiejian doctor --json
```

全局配置覆盖参数必须写在子命令之前：

```powershell
uv run jiejian --config .\config\default.toml --var-dir .\var --log-level INFO doctor --json
```

配置优先级固定为：内置默认值 `<` `config/default.toml` `<` 显式配置文件 `<` `JIEJIAN_` 环境变量 `<` CLI 参数。相对 `var_dir` 按当前工作目录解析，目录由程序按需创建。

运行测试时禁止写入 Python 字节码缓存：

```powershell
$env:PYTHONDONTWRITEBYTECODE = "1"
uv run python -B -m pytest
```

## 当前限制

阶段 0 未实现 API、数据库持久化、Worker、Runner、浏览器录制、HTTP 执行、变异器、观察器、Oracle、报告、GUI 或 CI 门禁。`doctor` 只报告 Playwright 是否可用，缺失不会导致必要检查失败。
