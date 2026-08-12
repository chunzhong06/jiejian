# Demo 流程

## 目标

用本机黄金样例展示：HTTP `403` 不足以证明安全，必须观察后端副作用；证据不足时使用独立的 INCONCLUSIVE bundle。

## 准备

```powershell
.\start.cmd -PrepareOnly
$env:JIEJIAN_SAMPLE_OWNER_TOKEN = "sample-owner-token"
$env:JIEJIAN_SAMPLE_ATTACKER_TOKEN = "sample-attacker-token"
```

`PrepareOnly` 不会激活或修改当前 PowerShell 父 shell。准备成功后，按脚本输出的后续 CLI 用法执行演示：Conda 使用 `conda run --no-capture-output --name jiejian_env jiejian <命令>`，uv 使用输出的 uv 可执行文件配合 `run --locked --no-sync jiejian <命令>`；也可以先显式执行 `conda activate jiejian_env`，再使用下方短命令。它最终复用稳定入口 `jiejian serve --open`，也可以只运行 `jiejian ci` 做无服务黄金样例演示。Node.js 与 pnpm 由脚本先做独立预检。

在两个终端启动样例：

```powershell
python -B -m jiejian.sample_app --variant safe --port 8765
python -B -m jiejian.sample_app --variant vulnerable --port 8766
```

## 演示输入

先展示自包含 bundle：

- `samples/fixed_apps/ownership/project.yaml`
- `samples/vulnerable_apps/ownership/project.yaml`
- `samples/inconclusive_apps/ownership/project.yaml`

fixed/vulnerable 都有 owner、attacker、资源、Flow、ACTIVE Contract 和 owner API 观察者；inconclusive 使用 safe variant 的 8767 端口并显式关闭 owner observer。

## 执行

```powershell
jiejian project validate .\samples\fixed_apps\ownership\project.yaml
jiejian contract validate .\samples\fixed_apps\ownership\contract.yaml
jiejian ci .\samples\fixed_apps\ownership\project.yaml
jiejian ci .\samples\vulnerable_apps\ownership\project.yaml
```

## 讲解顺序

1. safe 运行返回 `PASS`/退出码 0：越权请求被拒绝，owner API 确认资源未变化。
2. vulnerable 运行返回 `BLOCK`/退出码 1：接口可能同样返回 `403`，但 owner API 看到资源已经变化。
3. 展示 JSON 中的 reason code、Evidence 引用和 run_id。
4. 运行 `jiejian report <run_id> --format json`，说明报告会复验 publication manifest 与数据库完成态。
5. 强调目标请求来自隔离 Runner，CLI 和 Worker 不直接访问目标。

如需展示证据不足，直接使用已签入的 `samples/inconclusive_apps/ownership/`，结果应为 `INCONCLUSIVE`/退出码 2；不要临时复制或修改样例。

