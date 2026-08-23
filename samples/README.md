# 官方 Samples

`samples/web` 是界鉴随源码仓库提供的唯一 Web 演示真源，包含同一个 Authorization Target 的三种行为变体、权限契约、执行配置、外部预期和公开启动脚本。界鉴产品代码不包含被测 Demo 应用，也不会读取 Sample Truth 决定结论。

## 三态权限检查 Golden

- `fixed`：接口拒绝攻击者修改，真实资源没有变化，正常执行链应形成 PASS。
- `vulnerable`：接口表面拒绝，但真实资源发生变化，正常执行链应形成 BLOCK。
- `inconclusive`：必需的资源状态观察不可用，正常执行链应形成 INCONCLUSIVE。

三个变体属于同一个业务 Target，不是三套应用。Ownership 只是本 Sample 的关系场景；tenant、department、hierarchy、workflow、batch、异步和多观察器能力由 Core、Coverage 与 Observer 定向测试保护。

每个 Bundle 位于 `samples/web/{fixed|vulnerable|inconclusive}/`：

- `contract.json`：描述 attacker 对 owner-resource 执行 modify 时的 DENY 意图。
- `profile.json`：通过当前 Web Target Runtime 执行的正式配置。
- `scenario.json`：Target、观察器和验证条件说明。
- `truth.json`：只供测试在产品完成真实执行和发布后比较的外部预期。

唯一 Target 实现在 `samples/web/target/server.py`。固定端口分别为 `8865`、`8766`、`8767`；界鉴控制面默认使用 `8765`。Target 只绑定 `127.0.0.1`，reset 只接受回环请求和 `X-Jiejian-Test-Mode: 1`。Owner、attacker、peer 与独立 Owner Observer 使用不同临时凭据。

## 图形界面入口

从仓库根目录执行：

```powershell
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File .\samples\web\launch\gui.ps1 -Variant vulnerable
```

脚本会准备或复用当前源码运行环境，启动唯一 Sample Target，再通过公开 `start.cmd -Mode Gui` 打开界鉴。终端会显示 Target 地址、`profile.json` 和 `contract.json` 路径；请通过正常应用接入、权限治理和检查入口使用这些信息。脚本不写产品数据库、不调用私有 Demo API，也不提供预设 Verdict。

## 命令行入口

在已经通过正常产品流程登记项目并激活对应 Contract 后执行：

```powershell
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File .\samples\web\launch\cli.ps1 -Variant vulnerable
```

脚本只负责启动 Sample Target、注入当前进程临时凭据，并通过通用源码 CLI 入口调用公开的 `jiejian run samples/web/<variant>/profile.json`。它不会新增 `jiejian demo`、`--demo`，也不会绕过 Contract Governance。运行日志进入 `var/logs/samples/`；脚本退出时停止 Target 并恢复调用进程原有环境变量。

## 直接运行 Target

需要单独调试 Target 时，可显式设置四个不同的临时不透明凭据后运行：

```powershell
$env:JIEJIAN_AUTHORIZATION_OWNER_TOKEN = '<temporary owner value>'
$env:JIEJIAN_AUTHORIZATION_ATTACKER_TOKEN = '<temporary attacker value>'
$env:JIEJIAN_AUTHORIZATION_PEER_TOKEN = '<temporary peer value>'
$env:JIEJIAN_AUTHORIZATION_OWNER_OBSERVER = '<temporary observer value>'
$env:PYTHONDONTWRITEBYTECODE = '1'
python -B -m samples.web.target.server --variant vulnerable --port 8766
```

INCONCLUSIVE 表示证据不足，不表示安全。Sample 不联网、不扫描公网；凭据不得写入 Profile、日志、Evidence 或报告，完成后应停止 Target 并清理不再需要的本地运行数据。
