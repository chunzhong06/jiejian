# 样例说明

当前提供两套自包含 ownership bundle：

- `fixed_apps/ownership/`：修复版本，越权请求不产生后端副作用。
- `vulnerable_apps/ownership/`：缺陷版本，越权请求可能返回 `403`，但资源已经被修改。

每套目录都独立包含 `project.yaml`、`flow.yaml` 和 `contract.yaml`。两套 Flow/Contract 当前内容相同也不跨目录共享，因为输入安全规则要求 `project.yaml` 的 `flow` 和 `contract` 相对路径解析后不得越出项目目录。自包含 bundle 也便于单独复制、演示和复现。

```powershell
jiejian ci .\samples\fixed_apps\ownership\project.yaml
jiejian ci .\samples\vulnerable_apps\ownership\project.yaml
```

完整启动和环境变量见 [Demo 流程](../docs/06_竞赛资料/Demo流程.md)。

