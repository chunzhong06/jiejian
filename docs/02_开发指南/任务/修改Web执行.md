# 修改 Web 执行

> 状态：CURRENT。当前生产Target只有WEB；API不执行目标，真实HTTP与Observer进入隔离Runner。

## 冻结输入与职责

当前链为正式BusinessBoundary/Permission与已审阅Recording、Preparation、受控Registry，经`workflows/checks/runtime_bundle.py`生成`CheckRuntimeBundle`，与`PersistedExecutionRequestV3`一起冻结。`infra/execution/check_executor.py`编排Case，`infra/execution/web/check_runtime.py`执行请求，`infra/observers/check_runtime.py`保存独立来源。旧Contract/Profile builder不是当前装配入口。

builder只读核对Flow/Draft/绑定hash，不为补配置访问目标，也不改已持久Flow。请求模板、目标scope、秘密引用与预算沿`product/protocols/web/`共享叶模型，canonical/config_hash冻结运行输入。

## 请求和身份

目标scope约束scheme/host/port、私网与loopback策略、路径、每次redirect、DNS/Host一致性、请求数/超时/字节预算。不得根据页面、数据库或LLM临时构造范围外请求。

秘密只通过受控引用最小注入，登录会话不进入普通数据库、公共协议、Evidence或日志。计划账号不能冒充目标实际身份；TARGET主体及独立观察身份分别验证。身份失败是准备或执行事实，不是权限漏洞。

每Case只执行一次TARGET。SETUP与精确资源恢复使用冻结的合法身份，恢复保留历史，不能用全局reset冒充业务撤销。请求marker把本Case、资源、Task、Audit、Queue和最终对象关联在同一实验窗口中；恢复失败不得抹除已确认禁止后果。

## HTTP分类

`HttpOutcomeClassifier`只产生ACCEPTED/DENIED/UNKNOWN，不产生安全Verdict。冲突、不足、网络或解析失败不能伪装成拒绝或安全。

当前builder仅为TARGET派生缺省拒绝：denied为空、accepted非空且全部STATUS_IN时，补401/403中未被显式accepted接受的状态。原denied非空或含复杂accepted谓词时完整保留，不尝试消除显式冲突。SETUP不改，404、重定向、429、5xx均无缺省拒绝。历史Flow字节不变。

## 202完成绑定

自动绑定只适用于accepted STATUS_IN明确含202的TARGET。候选必须是同Action合格proof的ASYNC_TASK_STATUS辅助来源，具备EVENTUAL、准确descriptor引用和独立身份验证声明。同observer完整spec/身份/descriptor相同才去重；冲突或歧义产生结构化准备缺口。0候选保留None，唯一候选冻结observer_id。已有合法显式绑定尊重；跨动作、错误类型/阶段/身份的绑定拒绝。

执行器保留原TARGET响应，在EVENTUAL后仅对原status202调用原classifier重新分类，不重发TARGET、不硬编码接受。可信完成需要TARGET身份MATCH、当前Case实际参与proof、精确observer/resource/binding/proof/effect/marker，且所有匹配事实都可信。Observer生产端必须核准完整相关的包络、AVAILABLE、独立观察身份MATCH、真实非空task_id和SUCCESS终态。缺失、FAILED、TIMED_OUT、NOT_CREATED、partial、错误相关性或冲突均不提升。

Task的业务效果可以仍UNKNOWN；它证明执行终态，不证明ZIP。仅ZIP确认不能代替Task完成绑定。其他HTTP状态保留首次分类。即使202已ACCEPTED，ALLOW安全仍需决定性业务事实、基线、恢复及完整控制，403也不能抹去真实越权。

## Observer与Sample

严格本地descriptor从`workflows/checks/local_observer_wiring.py`加载：拒绝重复/未知字段、越界路径、inline秘密与不匹配origin/resource。只读编译六来源，不读取目标数据。

官方导出仅最终AZURE_BLOB_OBJECT是VERDICT_REQUIRED；STRUCTURED_AUDIT_LOG为DIAGNOSIS_REQUIRED；Owner API、SQLite、Task和Queue为SUPPORTING。来源全部执行，角色不能按结果便利调整。Owner通过合法Alice Cookie独立观察；旧独立Bearer只读端点保留各自职责。

问题版真实enqueue在authorization前，Worker等待HTTP响应完成后形成ZIP；固定版先authorize，拒绝分支不派发。Trace的dispatch_effect_ids只说明派发关联，不是最终效果，最终效果归属archive节点。Sample只是受控业务实现，生产Runner/evaluator不得按Sample名称或路径分支。

## 验证入口

优先`tests/backend/workflows/checks/test_http_classification.py`、`tests/protocols/test_check_runtime.py`及`tests/backend/infra/execution/test_check_executor.py`的直接项。Sample端点与恢复见`tests/samples/web/test_collaboration_space.py`；完整当前发布三态见`tests/backend/workflows/test_current_official_sample.py`。经`dev.ps1 test`串行，协议变化更新并检查schema。

最终默认sample-test保留真实新实例、浏览器控制会话、Worker/Runner与精确清理；关键GUI技术动作须与实际前端接通，API成功和截图不替代交互验收。视觉验收另核视口、主题、焦点与遮挡。不用完整L5反复调试局部分类问题。
