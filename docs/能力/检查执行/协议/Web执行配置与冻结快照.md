# Web 执行配置与冻结快照

> 状态：CURRENT。当前CHECK冻结输入见本节；下方旧Profile/Snapshot内容仅说明保留格式，不是当前装配入口。

## 当前CHECK冻结合同

当前配置为基础CheckRuntimeBundle或由运行/来源决定的受控变体，根版本查[注册参考](../../../参考/生成/注册与格式.md)；请求是`PersistedExecutionRequestV3`，根格式3。请求冻结完整当前权限Plan、各Case双身份/具体资源/proof/恢复/预算与config_fingerprint；bundle冻结真实Flow派生的HTTP步骤、独立身份验证、Observer specs及完成绑定。builder先验持久Flow/raw/draft/hash，不改历史材料，不运行目标。

提交前及事务内重核live源码、当前权限和准备事实。`ChangeContext`冻结精确change_id、impact fingerprint和全部Permission引用范围；`RepairContext`冻结原题引用、原epoch/Permission、selected control、身份/资源、禁止效果、决定性标准与全部历史SAFE回归。两者为嵌套DTO不重复schema_version，空历史回归显式为空集合。

当前TARGET的保守401/403缺省及唯一合格Task完成绑定规则见[修改Web执行](../修改Web执行.md)。202仅在原响应谓词与精确可信EVENTUAL终态同时成立时重新分类，不重发TARGET、不用ZIP效果代替Task终态；无缺省404。

Worker/Runner只消费冻结输入，秘密按受控引用最小注入。CheckEvidence/CheckRunnerResult经canonical/hash、租约/fence、原子publication与Reader核验后供ResultStory/Repair读取。旧无可选字段的canonical保持逐字兼容；不把旧Profile reader接入新提交。

## 独立保留格式

`WebExecutionProfile`、`WebExecutionSnapshot` 与早期 PersistedExecutionRequest 的严格模型、codec 和直接 reader 仍位于 `product/protocols/web/`、`product/protocols/runner/execution.py`、`product/protocols/runner/execution_request.py`。独立 Web runtime 和直接协议测试消费这些格式；它们不是当前 ApplicationCore 提交入口，不再存在 SecuritySetupCompiler 或 ExecutionWorkflow 的产品装配。

Profile 只含引用、scope、受控请求模板、身份、bindings、预算与指纹，不含秘密值；Snapshot 表示不可变执行输入。唯一 TARGET、身份与业务 scope 分离、Cookie jar 按 identity 隔离、明确恢复策略、有限完成绑定仍由严格模型和 runtime 校验。旧格式的兼容范围由对应 reader 与 Schema 决定，不以当前 GUI 可读为依据。

修改独立格式时运行 `tests/protocols/web/`、`tests/backend/infra/execution/` 和稳定身份回归；当前 CHECK 则验证 `tests/backend/workflows/checks/` 与当前 request/bundle 生产消费者。字段以模型和 Schema 为准，勿把两条输入格式互相兜底。
