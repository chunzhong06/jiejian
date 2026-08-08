# 界鉴

当前仓库已实现“阶段 1：CLI 安全验证纵切”。在阶段 0 配置、状态机、日志和脱敏基础上，可从人工 YAML 加载项目、Flow 与 Contract，在明确授权的本机目标上执行关系变异，并生成带哈希的 JSON 证据和 PASS/BLOCK/INCONCLUSIVE 门禁。

## 环境与安装

- Conda

项目统一使用名为 `jiejian_env` 的 Conda 环境，Python 固定为 3.13。首次配置或依赖变化后，在项目根目录执行：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\setup-conda.ps1
conda activate jiejian_env
jiejian --help
```

脚本根据 `environment.yml` 创建 Conda 环境，再使用该环境自己的 pip 从 `pyproject.toml` 安装项目及 `dev` 依赖组。重复运行脚本会复用现有环境。`uv.lock` 继续保留，但不参与 Conda 环境的创建、安装或运行。

不用脚本时，等价的手动流程是：

```powershell
conda env create --file .\environment.yml
conda activate jiejian_env
python -B -m pip install --group dev --editable .
```

## 当前可用命令

```powershell
jiejian doctor
jiejian doctor --json
jiejian project validate .\samples\projects\ownership-safe\project.yaml
jiejian contract validate .\samples\projects\ownership-safe\contract.yaml
jiejian run .\samples\projects\ownership-safe\project.yaml --contract .\samples\projects\ownership-safe\contract.yaml
jiejian report <run_id> --format json
jiejian ci .\samples\projects\ownership-safe\project.yaml
```

全局配置覆盖参数必须写在子命令之前：

```powershell
jiejian --config .\config\default.toml --var-dir .\var --log-level INFO doctor --json
```

配置优先级固定为：内置默认值 `<` `config/default.toml` `<` 显式配置文件 `<` `JIEJIAN_` 环境变量 `<` CLI 参数。相对 `var_dir` 按当前工作目录解析，目录由程序按需创建。

## 本机黄金样例

样例应用只绑定 `127.0.0.1`，身份值从环境变量读取。先在一个终端启动 safe 版本：

```powershell
$env:JIEJIAN_SAMPLE_OWNER_TOKEN = "local-owner-token"
$env:JIEJIAN_SAMPLE_ATTACKER_TOKEN = "local-attacker-token"
python -B -m jiejian.sample_app --variant safe --port 8765
```

再在另一个终端执行 safe 项目，预期 `PASS` 和 CI 退出码 0。vulnerable 项目使用端口 8766：

```powershell
python -B -m jiejian.sample_app --variant vulnerable --port 8766
jiejian ci .\samples\projects\ownership-vulnerable\project.yaml
```

缺陷版本会先写资源再返回 HTTP 403；owner_api 的前后观察仍会确认副作用，最终输出 `BLOCK`，CI 退出码为 1。关闭项目文件中的 `observers.owner_api` 时输出 `INCONCLUSIVE`，退出码为 2。

运行测试时禁止写入 Python 字节码缓存：

```powershell
$env:PYTHONDONTWRITEBYTECODE = "1"
python -B -m pytest -p no:cacheprovider
```

## 当前限制

阶段 1 只支持以 IPv4 字面量声明的同步 HTTP 目标、IdentitySwap、ResourceSwap、特权字段变异、HTTP/owner_api 观察和 JSON 报告。域名和 IPv6 暂不进入可执行目标；这是为了避免 DNS 校验与实际连接之间的重绑定窗口。HTTP 响应进入 Observation 前会按本次运行已解析的全部身份秘密做精确递归脱敏。尚未实现 API、业务数据库、Worker、Runner、浏览器录制、GUI、TUI、LLM、插件、SARIF、HTML 或 JUnit。`doctor` 只报告 Playwright 是否可用，缺失不会导致必要检查失败。
