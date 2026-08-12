# CLI

## 定位

`cli` 是安装后的 `jiejian` 命令入口。它负责参数、配置覆盖、命令分组和稳定输出，把实际业务委托给与 API/GUI 相同的应用能力。

## 负责 / 不负责

- 负责 `jiejian.cli:main`、Typer 命令树、运行时 bootstrap、JSON 展示、脱敏错误和退出码。
- 命令按 projects、contracts、recordings、runs、results、system 分组。
- 不实现 Contract 状态机、Job 核心、Verification 判定或持久化规则。

## 子模块与 public API

- `jiejian.cli:main` 是正式稳定入口，也是 `pyproject.toml` 的 console script。
- `app.py`：Typer 组合根，只注册叶命令。
- `commands/`：各能力命令适配。
- `bootstrap.py`：配置、Storage 和前端资源定位。
- `presentation.py`：JSON 输出和稳定失败出口。

仓库内部测试和实现应直接导入叶模块；package 根除 `main` 外不提供旧结构 facade。

## 调用与数据流

```text
jiejian 命令
→ cli.app / commands
→ ApplicationContext 或能力服务
→ 持久 Job / Contract / Recording / Results
→ JSON、日志和稳定退出码
```

## 关键不变量和失败语义

- CLI、API、GUI 的同一操作必须得到相同状态和错误语义。
- `ci` 的 PASS/BLOCK/INCONCLUSIVE 退出语义不得与 Job FAILED/CANCELLED 混合。
- 用户可见错误必须脱敏；secret 只在执行前从环境读取。
- Typer command docstring 可能影响 `--help`，修改时需要比较帮助输出。

## 修改与测试入口

- CLI Contract：[`tests/e2e/test_cli_contract_workbench.py`](../../../../tests/e2e/test_cli_contract_workbench.py)
- 安全门禁：[`tests/e2e/test_cli_security_gate.py`](../../../../tests/e2e/test_cli_security_gate.py)
- 启动与 doctor：[`tests/runtime`](../../../../tests/runtime/)

## 相关规范、协议与 ADR

- [根 README](../../../../README.md)
- [ADR-0001](../../../../docs/03_技术决策/ADR-0001-用户入口设计.md)、[ADR-0016](../../../../docs/03_技术决策/ADR-0016-阶段5.4C-CLI与GUI建约接入.md)、[ADR-0019](../../../../docs/03_技术决策/ADR-0019-Windows首次使用与一键启动.md)
