# 黄金样例

`samples/` 只保存少量可读、可运行、可讲解的本机黄金场景；它们不是测试 fixture，也不是 benchmark。每个目录都是自包含 bundle，包含自己的 `project.yaml`、`flow.yaml` 和 `contract.yaml`。

## 场景地图

| Bundle | 目的与唯一价值 | 外部依赖/秘密 | 预期结果 | 竞赛演示 |
| --- | --- | --- | --- | --- |
| `fixed_apps/ownership/` | 安全版本：越权请求被拒绝且没有后端副作用。 | 仅本机 safe sample app（8765）；token 来自环境变量，不写入文件。 | `PASS`，CLI 退出码 0 | 适合，展示安全基线和 Evidence。 |
| `vulnerable_apps/ownership/` | 缺陷版本：HTTP 可以返回拒绝，但越权副作用已发生。 | 仅本机 vulnerable sample app（8766）；token 来自环境变量，不写入文件。 | `BLOCK`，CLI 退出码 1 | 适合，展示“拒绝不等于安全”。 |
| `inconclusive_apps/ownership/` | safe variant 的独立端口版本，显式关闭 `owner_api` 观察器。 | 仅本机 safe sample app（8767）；token 来自环境变量，不写入文件。 | `INCONCLUSIVE`，CLI 退出码 2 | 适合，展示观察不足，不代表安全或漏洞。 |

三个 bundle 都只允许环回地址：fixed 使用 `8765`，vulnerable 使用 `8766`，inconclusive 使用 `8767`。默认 token 仅用于本机演示；正式使用时通过环境变量提供，不写入 YAML 或其他文件。

## 最小运行方式

以下命令使用 Windows PowerShell。先在一个 PowerShell 窗口启动对应 sample app，再在另一个窗口运行 CLI；结束后停止样例进程。

```powershell
$env:JIEJIAN_SAMPLE_OWNER_TOKEN = "demo-owner-token"
$env:JIEJIAN_SAMPLE_ATTACKER_TOKEN = "demo-attacker-token"
$sample = Start-Process python -ArgumentList "-B -m jiejian.sample_app --variant safe --port 8765" -PassThru
try {
    jiejian ci .\samples\fixed_apps\ownership\project.yaml
} finally {
    Stop-Process -Id $sample.Id -Force
}
```

将端口和 bundle 替换为 `8766`/`vulnerable_apps` 或 `8767`/`inconclusive_apps` 即可运行另外两个场景。安全版本预期 `PASS`/0，缺陷版本预期 `BLOCK`/1，观察器关闭版本预期 `INCONCLUSIVE`/2。

离线检查每个 bundle 的项目与独立 Contract：

```powershell
jiejian project validate .\samples\fixed_apps\ownership\project.yaml
jiejian contract validate .\samples\fixed_apps\ownership\contract.yaml
jiejian project validate .\samples\vulnerable_apps\ownership\project.yaml
jiejian contract validate .\samples\vulnerable_apps\ownership\contract.yaml
jiejian project validate .\samples\inconclusive_apps\ownership\project.yaml
jiejian contract validate .\samples\inconclusive_apps\ownership\contract.yaml
```

## Recording 演示

Recording 复用 safe sample app，不复制另一套应用配置。它展示独立 Recording Runner、事件脱敏和 `PENDING_REVIEW`/FlowDraft 入口；命令不会声称完成全部人工浏览操作或自动生成可直接完成的 Flow。

```powershell
$env:JIEJIAN_SAMPLE_OWNER_TOKEN = "demo-owner-token"
$env:JIEJIAN_SAMPLE_ATTACKER_TOKEN = "demo-attacker-token"
$sample = Start-Process python -ArgumentList "-B -m jiejian.sample_app --variant safe --port 8765" -PassThru
try {
    jiejian recording start .\samples\fixed_apps\ownership\project.yaml --identity owner --duration-seconds 1 --headless
} finally {
    Stop-Process -Id $sample.Id -Force
}
```

录制后的 `status`/`review`/`finalize` 仍按实际人工审阅结果推进；不把一次短时演示描述为完整 Flow。

## Contract 与 Drift 演示

Contract/Drift 复用 fixed bundle，不复制 app 或配置。常见顺序如下；动态 Candidate ID 从上一步 JSON 输出中取得：

```powershell
$project = ".\samples\fixed_apps\ownership\project.yaml"
jiejian contract workspace $project
jiejian contract derive $project --include-flow
jiejian contract draft $project ownership-contract --candidate <从 derive JSON 取得>
jiejian contract transition $project ownership-contract 1 submit --actor reviewer
jiejian contract transition $project ownership-contract 1 activate --actor approver
jiejian contract assessment $project ownership-contract 1
jiejian contract drift $project ownership-contract 1
```

六类 Drift 由 Contract 测试固定覆盖；单次样例演示只展示工作台顺序，不制造全部六类漂移。
