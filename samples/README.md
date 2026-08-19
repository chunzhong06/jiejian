# 官方 Samples

Samples 是界鉴随仓库提供的可重复 HTTP Target、权限契约和执行配置，供开发者验证真实副作用、观察证据和检查结果。当前只提供 Web Target。

## 三态权限检查 Golden

界鉴提供三套同一安全意图的权限检查 Golden：

- `fixed`：接口拒绝攻击者修改，真实资源没有变化，预期为 PASS。
- `vulnerable`：接口表面拒绝，但真实资源发生变化，预期为 BLOCK。
- `inconclusive`：必需的资源状态观察不可用，预期为 INCONCLUSIVE。

Ownership 只是这个示例中的一种关系场景，不是独立的产品或 Sample 家族。更复杂的 tenant、department、role、hierarchy、workflow、batch、异步和多观察器能力由 Core、Coverage 与 Observer 定向测试保护。

每个 Bundle 位于 `samples/http/{fixed|vulnerable|inconclusive}/`，包含：

- `contract.json`：完整 PermissionContract，描述 attacker 对 owner-resource 执行 modify 时的 DENY 意图。
- `profile.json`：当前正式 Web 执行配置。
- `scenario.json`：Target、观察器和验证条件的说明。
- `truth.json`：测试在产品真实执行和发布结果完成后才读取的外部预期；产品不会读取它来决定 Verdict。

Target 真源为 `samples/http/target/server.py`。三个 Bundle 使用固定回环端口 `8865`、`8866`、`8867`；产品控制面默认使用 `8765`，两者不会抢占端口。Target 只绑定 `127.0.0.1`，reset 只接受回环请求和 `X-Jiejian-Test-Mode: 1`。

## 运行 Target

从仓库根目录启动一个变体时，使用本机会话中的临时不透明凭据：

```powershell
$env:JIEJIAN_AUTHORIZATION_OWNER_TOKEN = '<temporary opaque value>'
$env:JIEJIAN_AUTHORIZATION_ATTACKER_TOKEN = '<temporary opaque value>'
$env:JIEJIAN_AUTHORIZATION_PEER_TOKEN = '<temporary opaque value>'
$env:JIEJIAN_AUTHORIZATION_OWNER_OBSERVER = '<temporary opaque value>'
$env:PYTHONDONTWRITEBYTECODE = '1'
python -B -m samples.http.target.server --variant vulnerable --port 8866
```

Target 启动后，可在已完成项目登记、契约治理和 Profile 准备的开发环境中，按启动输出提供的本机 CLI 调用方式运行对应 Profile。不要把上面的命令当作绕过 Contract Governance 的 Quick Start；`jiejian run` 不会自动激活契约。

## 预期结果与安全限制

一次完整的当前执行链应形成：

- `fixed`：HTTP 403、状态不变，最终 PASS。
- `vulnerable`：HTTP 403、状态改变，最终 BLOCK。
- `inconclusive`：表面请求完成但必需观察不可用，最终 INCONCLUSIVE。

INCONCLUSIVE 表示证据不足，暂时不能下结论，不表示安全或未发现问题。Truth 只用于测试最后比较，产品不会读取它来决定 Verdict。

官方 Target 不联网、不扫描公网、不依赖产品源码或测试代码。请使用临时凭据，避免把凭据放入 Profile、提交文件或日志；完成验证后停止 Target 并清理临时运行数据。
