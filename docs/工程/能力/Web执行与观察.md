# Web执行与观察

本页面向维护者，说明能力协作、持久事实、拒绝边界和恢复方式。用户操作从[文档入口](../../README.md)选择；源码定位查[模块索引](../../参考/模块索引.md)。

## Observer

### 修改路线

先确认冻结 `CheckRuntimeBundle` 中本 Case 的 proof、scope、来源与角色，再修改 adapter 或 projector。adapter 只形成受预算约束的事实；`EffectProjector.project_check` 解释事实能否证明具体业务效果；只有 `product/backend/domain/verification/checks.py` 裁决三态。来源新增时同步严格模型、接线、准备检查、实际执行、证据发布与只读展示，不能只增加页面标签。

`VERDICT_REQUIRED` 是必需证明，`SUPPORTING` 和 `DIAGNOSIS_REQUIRED` 保持辅助角色。实际身份来自同一会话的独立核验，不从 Trace 或计划身份补值。官方导出的决定性来源是 ZIP；后台任务完成或派发成功不等于 ZIP 已形成。

每个 Case/proof 独立保留游标和观察历史。审计 AFTER/EVENTUAL 回读同一个 BEFORE 锚点；空尾段不是闭合证明。任务可信终态、非空 task_id 和精确关联只能形成私有 execution_completed。只有来源完整、可靠、相关且观察窗口闭合，缺失才可作为不存在证明；观察失败不能解释为安全。辅助来源失败不能抹去独立必需来源已经确认的禁止效果。

结构化 Trace 只接受显式关联与允许字段；范围数组、大小预算和 canonical 规则见Observer 协议。不按时间相邻、列表顺序或名称相似补因果边。权限断裂修改见[诊断指南](结果读取与诊断.md)。

Queue 只读 Peek，Blob 只读已授权 namespace，SQLite 只读，Owner 只注入精确受控身份。秘密和原始敏感正文不得进入 Envelope、Evidence、日志或异常。Evidence 的事实排序与 canonical/hash 必须遵循同一模型规则，避免跨进程摘要漂移。

### 验证与排障

通用来源由 `check_records.py` 消费受控记录组件的有界读取结果。`source_contracts.py` 核对 Runtime Worker 的内核拥有关系、独立端口与产品组件指纹，不再识别接入应用的名称、文件摘要、角色或业务专用语法。`record_source.py` 只由 Runner 调用；来源读取能力经 DPAPI 保存为运行期引用，业务 Node 进程不能取得证明读取能力。

`transaction_store.py` 在内存 SQLite 事务内同时保存所选资源数据和每一步变化；完整快照写入 OS 独占的持久日志并 fsync 后才返回。原生日志文件无法被仍在运行的目标直接改写，损坏或截断不自动重置。记录日志有 128 MiB 上限，超限停止服务并要求处理；不是无限容量业务数据库。目标退出确认后才释放独占文件。

持续开发场景的后续容量设计需单独裁决：比较增量记录与检查点方案，保持完整性链、独立提交历史、崩溃恢复及旧格式读取。不能仅提高上限或删除历史来取得通过。材料准备提速不改变上述容量机制；连续使用和完整GUI验收需覆盖真实记录增长。

可信宿主为实际 HTTP 请求建立 scope；Runner 生成随机请求标记，宿主记录请求摘要，业务事务自动关联同一 scope。所有同步写入均已等待时才能完成 scope；响应结束后的写入被拒绝，未等待写入或异常关闭不能证明未发生。只支持接入受控资源集合的同步状态变化和有限 JSON 字段读取。外部数据库、文件、消息队列、后台任务及任意 JSON 日志不因此获得完整证明；Node VM 不作为对抗恶意应用代码的沙箱。

原子记录格式2按独立提交比较首尾；事务内变化后还原不冒充对外提交。两次独立提交中的开放与撤回仍分别保留，撤回不能抹去已经发生的开放。scope顺序与事务内部变化顺序分开；关闭scope拒绝新命令，已确认同文命令可读回原回执。旧格式1保持原读取语义，旧日志只在独占核验后导入新记录的起始状态。

已关联的禁止变化可以确认发生；未发生还必须有完整请求终态、连续版本、相同资源和完整前后记录。身份、字段与语义映射需要预检查和人工采用，组件真实性不能代替用户确认“这个字段就是要保护的业务结果”。

Evidence格式2保存有限业务事实，来源包括实际身份、独立提交、受保护字段、参照摘要和实际文件接收。`business_facts.py`纯归约同一批采集事实，`fact_validation.py`在发布及严格reader中核对归属、窗口、冻结方法和Observation一致性；读取不重新执行Verification。旧Evidence格式1按原格式读取，不补造新事实。

文件接收由真实HTTP实体流计数与摘要，只有完整且匹配已确认参照的内容才能证明完整接收。403不抹除实际已经接收的完整正文；空、206、超限、中断和不完整重定向均不足。正文不进入Evidence、日志或公共接口。文件私有准备见[证明来源](证明来源.md)。

JSON 证明的完整性、关联性与 Trace 定位分别表达。没有 Trace 不补因果边；必要证明确认违例时，辅助来源不足不能抹去 BLOCK。

经 `dev.ps1 test` 选择表中直接测试；公共模型变动再同步 Schema 并验证 reader。403 后 BLOCK 可以是正确结果；先查决定性效果。相同证据摘要漂移查规范排序；NOT_FOUND 异常查闭合、分页和关联；辅助错误盖过 BLOCK 查角色消费。真实进程与来源组合按[验证](../测试.md)选择 L5，不能用预设返回或页面颜色代替证据。

共享 Observer 独立格式及底层消费者仍保留；其 `EffectBinding.required_channels/corroborating_channels` 不是当前 CHECK 页面角色。需要维护该独立格式时才读协议的相应章节，不恢复已退役的 SecuritySetup 装配。

通用记录来源在每个采集阶段按已采用配置核对实际操作人、资源所有者和观察账号的主体及角色；外层Observer不再为同一观察账号额外重复一次身份请求。其他来源保留原独立身份核对。目标请求、身份读取与恢复仍受原冻结预算限制，预算耗尽明确保留EXEC_BUDGET原因，不放宽范围或补造可靠事实。

## Web执行

### 冻结输入与职责

当前链为正式BusinessBoundary/Permission与已审阅Recording、Preparation、受控Registry，经`product/backend/application/checks/runtime_bundle.py`生成`CheckRuntimeBundle`，与`ExecutionRequest`一起冻结。`product/backend/infrastructure/execution/check_executor.py`编排Case，`product/backend/infrastructure/execution/web/check_runtime.py`执行请求，`product/backend/infrastructure/observers/checks/check_runtime.py`保存独立来源。旧Contract/Profile builder不是当前装配入口。

builder只读核对Flow/Draft/绑定hash，不为补配置访问目标，也不改已持久Flow。请求模板、目标scope、秘密引用与预算沿`product/protocols/web/`共享叶模型，canonical/config_hash冻结运行输入。

### 请求和身份

目标scope约束scheme/host/port、私网与loopback策略、路径、每次redirect、DNS/Host一致性、请求数/超时/字节预算。不得根据页面、数据库或LLM临时构造范围外请求。

秘密只通过受控引用最小注入，登录会话不进入普通数据库、公共协议、Evidence或日志。计划账号不能冒充目标实际身份；TARGET主体及独立观察身份分别验证。身份失败是准备或执行事实，不是权限漏洞。

每Case只执行一次TARGET。SETUP与精确资源恢复使用冻结的合法身份，恢复保留历史，不能用全局reset冒充业务撤销。请求marker把本Case、资源、Task、Audit、Queue和最终对象关联在同一实验窗口中；恢复失败不得抹除已确认禁止后果。

### HTTP分类

`HttpOutcomeClassifier`只产生ACCEPTED/DENIED/UNKNOWN，不产生安全Verdict。冲突、不足、网络或解析失败不能伪装成拒绝或安全。

当前builder仅为TARGET派生缺省拒绝：denied为空、accepted非空且全部STATUS_IN时，补401/403中未被显式accepted接受的状态。原denied非空或含复杂accepted谓词时完整保留，不尝试消除显式冲突。SETUP不改，404、重定向、429、5xx均无缺省拒绝。历史Flow字节不变。

### 202完成绑定

自动绑定只适用于accepted STATUS_IN明确含202的TARGET。候选必须是同Action合格proof的ASYNC_TASK_STATUS辅助来源，具备EVENTUAL、准确descriptor引用和独立身份验证声明。同observer完整spec/身份/descriptor相同才去重；冲突或歧义产生结构化准备缺口。0候选保留None，唯一候选冻结observer_id。已有合法显式绑定尊重；跨动作、错误类型/阶段/身份的绑定拒绝。

执行器保留原TARGET响应，在EVENTUAL后仅对原status202调用原classifier重新分类，不重发TARGET、不硬编码接受。可信完成需要TARGET身份MATCH、当前Case实际参与proof、精确observer/resource/binding/proof/effect/marker，且所有匹配事实都可信。Observer生产端必须核准完整相关的包络、AVAILABLE、独立观察身份MATCH、真实非空task_id和SUCCESS终态。缺失、FAILED、TIMED_OUT、NOT_CREATED、partial、错误相关性或冲突均不提升。

Task的业务效果可以仍UNKNOWN；它证明执行终态，不证明ZIP。仅ZIP确认不能代替Task完成绑定。其他HTTP状态保留首次分类。即使202已ACCEPTED，ALLOW安全仍需决定性业务事实、基线、恢复及完整控制，403也不能抹去真实越权。

### Observer与Sample

严格本地descriptor从`product/backend/application/checks/local_observer_wiring.py`加载：拒绝重复/未知字段、越界路径、inline秘密与不匹配origin/resource。只读编译六来源，不读取目标数据。

官方导出仅最终AZURE_BLOB_OBJECT是VERDICT_REQUIRED；STRUCTURED_AUDIT_LOG为DIAGNOSIS_REQUIRED；Owner API、SQLite、Task和Queue为SUPPORTING。来源全部执行，角色不能按结果便利调整。Owner通过合法Alice Cookie独立观察；旧独立Bearer只读端点保留各自职责。

问题版真实enqueue在authorization前，Worker等待HTTP响应完成后形成ZIP；固定版先authorize，拒绝分支不派发。Trace的dispatch_effect_ids只说明派发关联，不是最终效果，最终效果归属archive节点。Sample只是受控业务实现，生产Runner/evaluator不得按Sample名称或路径分支。

### 验证入口

优先`tests/application/checks/test_http_classification.py`、`tests/contracts/protocols/test_check_runtime.py`及`tests/infrastructure/execution/test_check_executor.py`的直接项。Sample端点与恢复见`tests/runtime/test_baseline.py`；完整当前发布三态见`tests/application/examples/test_current_official_sample.py`。经`dev.ps1 test`串行，协议变化更新并检查schema。

最终默认sample-test保留真实新实例、浏览器控制会话、Worker/Runner与精确清理；关键GUI技术动作须与实际前端接通，API成功和截图不替代交互验收。视觉验收另核视口、主题、焦点与遮挡。不用完整L5反复调试局部分类问题。

## Observer观察契约

### 当前 CHECK 消费者与数据流

Observer 公共模型仍由 `product/protocols/observer/` 定义，独立 Invocation/Envelope 根格式为字符串 `"1"`；嵌套 Spec、locator、scope 不增加版本。六类真实 adapter 复用，但当前来源等级由 `CheckRuntimeBundle` 的主证明及辅助注册冻结，不按 Sample 来源名自动赋予权威性。

`ExecutionRequest + CheckRuntimeBundle → CHECK Worker → Check Runner/CheckExecutor → CheckObserverRuntime → adapter → ObservationEnvelope → EffectProjector.project_check → CheckObservation/CheckEvidence → fenced publication → CheckResultReader/ResultStory` 是当前链。`VERDICT_REQUIRED` 进入唯一 `product/backend/domain/verification/checks.py`；`SUPPORTING / DIAGNOSIS_REQUIRED` 不替代主证明。实际身份独立验证，Trace 不兜底身份或决定 Verdict。

`StructuredAuditLogLocator.allowed_fields` 是 25 个已命名字段的封闭集合，原六个必需字段不变。可选 `allowed_action_ids` 与 `allowed_resource_ids` 是唯一允许的数组值，每组 0～64 个唯一严格字符串，每项 1～160 字符且匹配 `^[A-Za-z0-9][A-Za-z0-9_.:/-]{0,159}$`，同时拒绝既有内联秘密模式。null、标量、布尔、数值、对象、嵌套、重复、超长或超量均使整个事件成为 `AUDIT_EVENT_INVALID` 并保留不完整，不能截断或过滤为完整结果。

出现范围键必须同时满足既有完整 Trace 必需字段。缺失保持缺失，空数组保持空数组；两者均不证明授权范围。记录 canonical、冲突检测和 provenance hash 保留源数组顺序，经校验投影到 `TraceAuthorityScope` 后集合才规范排序。不改原始日志或旧发布文件，无新增字段的字节规则不变。行、文件、字节、时间、游标、关联和闭合预算不变，Trace 仍最多 512 事件、256 KiB。

合法委托只能由显式因果 `AUTHORIZATION/ALLOW` 祖先、非空来源范围、范围子集、实际动作/资源覆盖及凭据一致性证明；不能从角色、actor、资源名称或 ALLOW 结果补范围。定位与效果判定分离：诊断不足或合法委托不能抹去独立权威来源已确认的 DENY 禁止效果。相关真源为 `product/backend/infrastructure/observers/adapters/audit_log.py`、`check_trace.py`、`product/backend/domain/verification/trace.py` 和 `breakpoints.py`（均位于 `product/backend/`）。

当前 CHECK 仅调度辅助来源支持的阶段，不为 EVENTUAL-only 的任务或队列生成初始、操作后的失败占位。初始基线与恢复是否完成分别取自 CaseOutcome 的独立核对结果；单点业务效果 UNKNOWN 不等于初始化或恢复失败。

来源采集与业务效果投影分别解释。对于已可信取得的辅助审计或队列记录，CheckObservation 的原因码可标注 `SOURCE_RECORDS_AVAILABLE`；完整队列窗口没有关联消息时标注 `SOURCE_WINDOW_EMPTY`。这些标记不改变 state、证明等级或 Verdict，不将过程记录升级为交付物证明。适配器的公开原因码一并保留，读取上限、来源失败和不支持投影不能都显示成同一未知说明。历史 Evidence 不回写，新检查才生成新增的采集说明。

官方示例的消息历史继续保留在原文件中；Peek 投影只返回未撤销任务的当前消息窗口，并遵守 `numofmessages` 的 1～32 条范围。撤销后的历史不能挤占下一题的有界观察窗口；真实上限仍然报告不完整，不通过扩大预算或删除历史伪造完整性。

## 执行与观察

### 组件与边界

- Job 持有可恢复的执行意图、状态、尝试、租约和 fencing token。
- Worker 负责 claim、lease、fencing、cancel、retry、恢复、结果校验和 publication。
- `ExecutionRequest` 与 hash 绑定的 `CheckRuntimeBundle` 是冻结输入；Runner 不重新读取可变业务数据库、Profile 或 Contract。
- Runner 在受控进程中执行受预算约束的目标流量，并产生受限结果和证据；当前边界不宣称具备未来 CLI Target 的完整 OS 沙箱。
- 当前生产 Target 只有 WEB；CheckExecutor 编排纯 Case 与独立 CheckWebRuntime，HTTP 请求、会话和范围由 Web 层负责。保留 TargetRuntimeRegistry 不作为当前 fallback。
- Web Target Runtime 独立负责 identity bootstrap、SETUP、唯一 TARGET、CLEANUP、动态 Slot、HTTP 结果归约和 Web scope。
- Observer Registry 按冻结 binding 调用 Owner API、SQLite、Azure Queue、Azure Blob、结构化审计日志或异步任务观察器，并归一 `ObservationEnvelope`；ObserverCoordinator 只负责调度、游标、阶段、完整性、关联和来源，不解释业务效果。
- EffectProjector.project_check 按冻结效果 ID/kind 投影独立来源；OwnerAPI 验证业务投影，DATA_DISCLOSURE 使用受保护字段 HMAC，审计 FINAL_EFFECT 必须明确 APPLIED 与 effect_id。不支持的组合为 UNKNOWN，不回退整个状态 hash。
- Runner 从本 Case 受控审计来源构造 Trace，并随 CheckEvidence 一起封口。只接受显式父引用、效果 ID、来源与权限字段；发布后只读该 Trace，不访问实时审计或目标。父节点缺失、来源异常或超预算时保持 partial，不补造节点。
- `WebTargetDefinition` 分离 Business、Auth 和 Observer scope；每个 scope 都检查 origin、host、port、重定向、私网授权、请求数、响应字节和超时预算。
- `HttpWorkflowBinding` 持有 SETUP/TARGET/CLEANUP 步骤、受控请求模板、ValueSlot、结果分类、基线投影和清理策略；Core Action 不持有这些 HTTP 字段。
- `HttpIdentityBinding` 是 Bearer、静态头、Cookie 登录、已准备 Cookie 会话或受限 OAuth2 的有界联合；每个身份使用独立内存 Cookie jar，bootstrap 不属于业务效果。已准备 Cookie 只保存名称、域、路径、安全标志与 `env:` 引用，真实值由主进程按本次请求最小注入。
- Observer 按 BASELINE、BEFORE、AFTER、EVENTUAL phase 采集事实，使用 correlation、causality、completeness、reliability、closure 和 budget 约束观察。
- Recording 回放必须先经过 Recording 工作流和安全重验证，再复用同一执行边界。
- TestIdentity 身份准备使用独立受控 Python 进程、headed BrowserContext 和系统进程树；它复用 Web scope、逐跳授权、响应字节与请求预算，但不进入 Worker/Runner、不生成 RecordingEvent，也不执行权限差分。控制面只通过固定 ready/save/cancel 标记和非秘密结果协议交互。
- 普通 Recording 由已确认 action 与单一已准备 TestIdentity 生成短期 session 描述；ApplicationCore 只把该 TestIdentity 的精确 Cookie/Bearer 引用解析到本次 Worker/Recording Runner 的最小环境，Runner 在独立 BrowserContext 中恢复认证。动作 Flow 只保存唯一 TARGET、必要 SETUP 和 `CASE_SUBJECT`/`CASE_RESOURCE_ID` slot，不携带具体差分身份、资源、Observer 或恢复实现。
- Flow 完成后，控制面只从同一次录制中生成受限候选：测试资源来自用户已确认的资源位置；独立观察来自 TARGET 之后由资源所有者执行、成功且未截断的同资源 GET；恢复来自 TARGET 之后的同资源变更请求。候选由用户确认后分别形成 TestResource、required ObservationBinding 和 RecoveryBinding，仍不在该阶段执行目标流量。
- CheckRuntimeBundle 复用已确认 Flow，并冻结独立观察身份和精确资源恢复请求；准备身份、恢复方式或权威来源失效时拒绝提交，不匿名回退或自动重放 TARGET。
- Runner 原子写入 attempt/progress.json，严格 CheckRunnerProgress 仅含 Run/Job/attempt/fence/request hash、PREPARING/EXECUTING/FINALIZING、完成/计划数和时间。它位于 staging 外，读端只接受当前 attempt；不可用只降级展示，不进入结果或恢复判断。

### 关键数据流

```text
CheckService → ExecutionRequest + CheckRuntimeBundle → Job/Run
→ Worker lease/fence → CheckRunnerInput → 独立 check_runner
→ CheckExecutor → Web TARGET / 独立 Observer / 恢复
→ CheckEvidence + CheckRunnerResult → staging
→ CheckPublisher 校验和 CAS → 不可变目录 + SQLite 收据
→ CheckResultReader → CheckStoryBuilder

旁路：attempt/progress.json → 当前 Job 只读状态
```

### 关键不变量

- 只有持有有效 lease 和 fencing token 的 Worker 能完成当前尝试。
- Supervisor 已为等待态 Job 建立启动责任后，若 Worker 在 claim 前不可恢复退出，只能通过 `job_id + waiting state + no lease` 的原子条件将 Job 及关联目标结束为 FAILED；条件失配时接受最新数据库状态，绝不覆盖已 claim 的 RUNNING Job。
- 每个 Worker 在 claim 前持有 `VarDir/runtime/workers/<job_id>.lock` 的系统文件锁，并在创建 Worker 前取得独立内核进程树的所有权。文件中的 PID、lease owner 和 token 只用于诊断；恢复证明必须同时满足系统锁可重新获取、进程树控制器确认无存活后代、旧 fencing 已失效，缺少任一事实都不得重新执行目标操作。
- Serve 同样持有带随机 owner token 的系统锁。Worker 只在 token 一致且锁仍被占用时认定控制面存活；窗口被强制关闭或新服务覆盖 token 后，Worker 请求持久取消，使 Runner 和受控浏览器沿既有清理链退出。遗留锁文件不决定有效性，下次启动可直接覆盖。
- 旧 token、过期 lease、重复 completion 和孤儿 staging 不得覆盖已发布结果。
- ExecutionTrace 只展示 Evidence 中真实存在的节点；父引用缺失、观察不完整或来源不可用时保持 partial，不补未知节点，也不修改 Finding、Report 或 Verdict。诊断不得把时间戳、状态码、列表位置或 live 现场当成缺失的血缘边。
- TargetRuntimeRegistry 对未知 TargetType fail closed；当前不提供 Process 或 MCP 目标执行入口。
- HTTP scope、重定向、私网、请求/响应字节、并发和时间预算在 adapter 边界强制执行。
- 普通请求模板不能直接注入 Authorization、Cookie、Host、长度/连接头或 `X-Jiejian-*`；身份与因果头只由适配器生成。
- TARGET 只能执行一次；身份准备、SETUP、值提取或基线失败时停止并形成 INCONCLUSIVE，不能匿名回退或继续使用空值。
- 普通 case 始终保持 `max_parallel_cases=1`，当前 Runner 不提供并发目标执行入口。
- Observer 的缺失、不完整、冲突或超预算结果不能被解释为安全通过。
- 写、改、删类 TARGET 的自身响应不得成为唯一 required observation；没有独立可信观察时只形成 coverage gap。状态变更动作没有已确认恢复或确定性一次性 fixture 时不得进入自动执行，不能为了得到 INCONCLUSIVE 而反复污染目标状态。
- CheckRuntimeBundle 复用已确认 Flow，并冻结独立观察身份和精确资源恢复请求；准备身份、恢复方式或权威来源失效时拒绝提交，不匿名回退或自动重放 TARGET。
- Web Runtime 从受信任的 attempt 上下文接收当前 Serve control origin，并在 Target Guard 中把同源目标收敛为 `SELF_TARGET_FORBIDDEN` 安全停止；该值不来自 Profile、Project、RunnerInput 或用户可编辑字段。
- API/GUI 只能提交、观察和读取，不直接操作目标流量。
- 进度不保存 URL、身份和资源实际值、请求响应、秘密或 Verdict；API 不接受用户提供路径或 attempt。

adapter 在 Web 边界完成 scope guard、binding 渲染、预算、脱敏和确定性响应谓词分类，但不决定 Permission Verdict。202 只有完成绑定已观察到终态时才可判为 ACCEPTED。

### 独立保留实现

旧 Contract Runner、TargetRuntimeRegistry、Runner/Observer 独立格式和报告派生仍有底层或测试消费者；当前 CHECK 不把它们作为 fallback。相关精确符号由自动代码参考维护，不据代码存在声明产品入口已装配。

### 失败语义

输入解析、租约、fencing、预算、目标范围、adapter、观察关联、协议校验或清理失败时，执行停止或进入明确失败状态；claim 前的 Worker bootstrap 失败记录 `JOB_FAILED / WORKER_FATAL`，不消耗或伪造 attempt/fencing token。已 claim 的 Worker 在可信终态前退出时，Supervisor 只用启动时保存的 lease owner 与数据库当前 fence 收口为 FAILED；owner 已变化时不得覆盖新 Worker。无法形成完整观察时向 Verification 提供 INCONCLUSIVE 证据，而不是伪造成功。

Worker 的 stdout/stderr 写入 `VarDir/logs/workers/<job_id>.log`，每次启动前按固定大小轮换并只保留有限备份；即使结构化 logging 尚未初始化，bootstrap traceback 也必须可定位。Worker 结构化日志同时进入主日志，并经过已知秘密脱敏。
主进程、Worker、Runner、Recording、TestIdentity 身份准备和 Observer 使用启动阶段确认的同一绝对 Python。Windows 由监督者持有启用关闭即终止后代的 Job Object，POSIX 使用独立 session/process group；取消、超时、租约失效、监督异常和服务关闭都终止并等待整棵受控树。不得扫描、按名称终止或接管用户浏览器。身份准备若在秘密提交前中断，以只含精确 `secret_ref` 的本地 journal 在下次启动补偿清理；journal 不决定凭据有效性且不含正文。

### 安全约束

Runner 只获得完成当前请求所需的最小环境和秘密引用，不能直接枚举或访问 Windows Credential Manager。身份准备进程只获得运行身份和 target scope，不通过环境接收登录秘密；它以严格 TestIdentity 命名空间精确写入共享 SecretStore。日志、异常、事件、观察和结果统一脱敏。清理失败必须阻止可能污染后续用例的继续执行。RunnerResult 分开保存主错误、有限失败阶段、底层稳定原因和结构化 cleanup issues；后置恢复失败不得覆盖更早的 TARGET、观察或验证失败，也不得据此发布新的 Verdict。

目标请求离开 adapter 边界前生成有界、脱敏的 input/output hash；失败输出使用确定性空输出 hash。

### 兼容与版本

当前执行产品只实现 Web + HTTP，生产 Target 枚举只保留 WEB。独立根使用各自严格版本，当前持久 CHECK 请求为格式 3；嵌套能力版本不代替根格式版本。每个根 parser 只接受一个当前格式，字段和解析规则以 Schema 和协议源码为准。已移除的 adapter 选择层、旧类名、旧开发执行请求和结果不兼容读取。
