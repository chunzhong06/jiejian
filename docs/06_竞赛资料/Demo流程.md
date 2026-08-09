# Demo 流程

## 目标

用两套本机配对样例展示：HTTP `403` 不足以证明安全，必须观察后端副作用。

## 准备

```powershell
conda activate jiejian_env
$env:JIEJIAN_SAMPLE_OWNER_TOKEN = "sample-owner-token"
$env:JIEJIAN_SAMPLE_ATTACKER_TOKEN = "sample-attacker-token"
```

在两个终端启动样例：

```powershell
python -B -m jiejian.sample_app --variant safe --port 8765
python -B -m jiejian.sample_app --variant vulnerable --port 8766
```

## 演示输入

先展示两套自包含 bundle：

- `samples/fixed_apps/ownership/project.yaml`
- `samples/vulnerable_apps/ownership/project.yaml`

两者都有 owner、attacker、资源、Flow、ACTIVE Contract 和 owner API 观察者。

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

如需展示证据不足，可在临时副本中关闭 owner observer，结果应为 `INCONCLUSIVE`/退出码 2；不要修改签入样例。

