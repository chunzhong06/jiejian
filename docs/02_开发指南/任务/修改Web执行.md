# 修改 Web 执行

> 状态：CURRENT。适用于 Web Target 的冻结 Profile、HTTP workflow、身份准备、请求范围、响应分类、202 异步完成绑定、本地 Observer 接线和状态化 Sample。

## Web 执行解决什么问题

界鉴当前唯一生产 Target 是 `WEB`。Web 执行把已经确认的权限意图和录制事实编译为可离线校验的冻结 Profile，再由隔离 Runner 使用受控测试身份执行 HTTP workflow。它负责“按冻结计划发出什么请求、目标怎样回应”，不负责把表面 HTTP 状态直接解释成真实安全结果。

正式链路是：

```text
PermissionIntent + 已确认应用事实
→ PermissionContract
→ WebExecutionProfile / Snapshot / hash
→ Worker 启动隔离 Runner
→ 身份 bootstrap
→ SETUP / TARGET / CLEANUP workflow
→ HTTP outcome + 独立 Observer facts
→ Verification
```

Profile 编译阶段是只读、确定性的。它不能访问真实目标来“补配置”，Runner 也不能根据当前页面或数据库重新编译 Profile。

## 快速找到修改位置

| 我想修改什么 | 主要位置 | 通常需要一起核对 |
| --- | --- | --- |
| 目标 origin、私网/loopback、作用域 | `product/protocols/web/target.py` | `identity.py`、执行 adapter、SSRF/redirect 测试 |
| HTTP 请求模板与变量绑定 | `product/protocols/web/request.py` | workflow、Profile canonical/hash、录制产物 |
| 响应 predicate 与 outcome classifier | `product/protocols/web/response.py` | 202 completion binding、Web response 测试 |
| SETUP/TARGET/CLEANUP workflow | `product/protocols/web/workflow.py` | Runner executor、Case marker、Sample cleanup |
| 身份类型、bootstrap 和 secret refs | `product/protocols/web/identity.py` | 测试账号准备、子进程角色环境、目标作用域 |
| 冻结 Profile、Snapshot 与 effect bindings | `product/protocols/web/profile.py` | security setup compiler、schema registry |
| Contract 与 Profile 生成 | `product/backend/workflows/security_setup/contract_builder.py`、`profile_builder.py` | compiler checks、local observer wiring |
| 本地六面 Observer 配置 | `product/backend/workflows/security_setup/local_observer_wiring.py` | 项目 wiring 文件、生成 Profile 测试 |
| Web Runtime 与请求执行 | `product/backend/infra/execution/web/` | Runner executor、身份 bootstrap、网络预算 |
| 可执行本地 Sample | `samples/web/` | `tests/samples/web/`、Golden fixture、精确 cleanup |

公共模型和生成物的版本边界见[Web 执行配置与冻结快照](../../03_参考手册/协议/Web执行配置与冻结快照.md)。

## 先判断哪个事实属于哪一层

| 问题 | 权威来源 | Web 执行可以做什么 | Web 执行不能做什么 |
| --- | --- | --- | --- |
| 本次允许访问哪里 | 冻结 `WebTargetScope` | 校验 origin、路径、redirect 和预算 | 跟随任意跳转或扩大到新域名/IP |
| 用哪个测试身份 | 冻结 identity binding 与受控 secret refs | bootstrap 最小会话并执行 | 把角色名或计划 subject 当作目标实际识别事实 |
| 请求怎样构造 | 冻结 workflow/request template | 绑定已声明变量并确定性发送 | 从目标响应或 LLM 临时生成新请求 |
| HTTP 怎样分类 | `HttpOutcomeClassifier` | 形成 ACCEPTED/DENIED/UNKNOWN | 形成 PASS/BLOCK/INCONCLUSIVE |
| 202 是否完成 | classifier completion binding + 同 Case 终态 Observer fact | 满足两者时分类 ACCEPTED | 仅凭 202 或任务 ID 文本推断完成 |
| 真实资源是否变化 | Observer Evidence | 提供 Case 关联和执行上下文 | 用响应码替代独立观察 |
| 最终安全结论 | Verification | 传递已有 HTTP/观察事实 | 从 HTTP outcome 重算 Verdict |

## 修改请求模板、变量和目标范围

请求模板必须能在冻结输入和 Case 运行上下文中确定性求值。新增变量时先确认它来自公开冻结字段、身份 bootstrap 输出还是 Runner 注入的受控 Case marker；不能读取任意环境变量、当前数据库记录或用户目录。

目标范围必须同时约束：

- scheme、host、port 与允许的 loopback/private-network 策略；
- relative path 和 path parameter 的编码；
- redirect 的每一跳；
- DNS/连接目标与 Host/authority 一致性；
- 请求数、超时、响应字节和提取器预算；
- header、cookie、body 与日志的秘密净化。

模板修改后重新核对 canonical Profile/hash。语义等价输入必须产生稳定摘要；快照变化必须让旧 preview/compile 失效，不能静默复用旧 hash。

## 修改身份准备和秘密引用

Web identity 只保存受控引用和非秘密描述。密码、Cookie、Bearer Token、客户端密钥和刷新 Token 不进入 Profile 公共 JSON、普通数据库字段、Evidence、Report、日志或 Git。

正常路线：

1. 在 `identity.py` 明确身份类型、必要 secret refs 和允许的 target scope。
2. 在受控 bootstrap 中解析引用，得到最小运行时 credential/session。
3. bootstrap 请求和后续 workflow 使用同一冻结作用域；不能借登录流程扩大 origin。
4. prepared cookie 或 header 仅在 Runner 生命周期内存在，不回写普通 DTO。
5. 实际识别身份只有独立可信事实时才展示；计划账号、subject binding 和角色名称不能冒充目标确认结果。

身份失败是执行/准备事实，不是权限漏洞。缺少引用、bootstrap 失败、scope 不匹配或凭据过期都应 fail closed，并给稳定、无秘密的原因码。

## 修改 HTTP 响应分类

`HttpOutcomeClassifier` 只根据冻结 predicate、状态码、有限 headers/body extractors 和可选异步完成事实分类：

```text
ACCEPTED = 满足冻结接受条件
DENIED   = 满足冻结拒绝条件
UNKNOWN  = 条件冲突、不足、超限或无法可靠分类
```

`DENIED` 不等于安全，`ACCEPTED` 也不等于一定存在越权；真实安全语义还依赖独立 Effect/Observer facts。

修改 classifier 时：

- 保持 predicate 顺序与冲突规则确定；
- 限制 body 读取和 JSON/path extractor；
- 401/403/404 等拒绝状态只按既有生成规则补入 DENIED，不把所有 4xx 一概等价；
- 不把网络错误、解析失败或响应超限伪装成 DENIED；
- 不在 adapter 中硬编码某个 Sample 的状态码。

## 正确处理 HTTP 202

若 TARGET 的 accepted statuses 包含 202，普通生成 Profile 必须绑定当前动作已经存在的 AsyncTask observer requirement；不存在该 requirement 时不能凭空创建新的未来模型，也不能仅为让 202 通过而放松 classifier。

运行时需要同时满足：

```text
classifier 声明 completion_binding
+ 对应 AsyncTask fact 属于同一 Case/动作
+ 任务达到冻结定义的可靠完成终态
= 202 可分类为 ACCEPTED
```

仅收到 202、任务不存在、关联 ID 不一致、轮询超时、任务仍在处理中或终态响应不完整，都保持 UNKNOWN。completion binding 是声明，不是事实；Runner 必须显式把观察到的 `terminal_completed=True` 交给 classifier。

Profile builder 只复用本地 wiring 中已有 AsyncTask requirement。若 accepted statuses 不含 202，或 classifier 已有显式 completion binding，不额外修改。对应测试要同时覆盖含 202、无 202、已有 binding 和缺少 AsyncTask wiring。

## 修改 SETUP、TARGET 与 CLEANUP

状态化 workflow 的三个 purpose 不能互换：

- SETUP 使用允许的 owner/准备身份创建最小前置状态；
- TARGET 使用被测 subject 执行冻结业务动作；
- CLEANUP 使用专用 owner 权限按 Runner 注入的 Case marker 精确撤销本次副作用。

Case marker 是关联和清理边界。TARGET 创建的任务、对象、审计、Queue、SQLite 状态都应带同一 marker；Observer 用它筛选当前 Case；CLEANUP 只删除相同 marker 的资源。不能用“清空 Sample”代替用例清理，也不能让 cleanup 结果反向改变已经形成的 Verdict。

Sample 是可执行参考，不是生产 adapter 的特例。为 Golden 增加状态时，应修改正式 workflow/wiring 能力和 Sample 可观察面，不在 Runner、Observer 或 Verification 中按 Sample 路径、项目名或测试 ID 分支。

## 修改本地 Observer wiring 与生成 Profile

本地 wiring 把同级受控配置编译为 Observer specs 和 effect channels。当前协作空间的关键来源为 Owner API 与最终 Blob，SQLite、审计、AsyncTask 和 Queue 为 corroborating。required/corroborating 角色进入 EffectBinding；Profile 还必须包含全部实际 observer specs。

修改 wiring 时保持：

- JSON/配置严格字段和重复键拒绝；
- 路径限制在允许的 `var/` 运行边界；
- secret 仅为引用，origin 与 loopback/private policy 显式；
- observer requirement id、action id 和 effect channel 稳定且唯一；
- 202 completion binding 只引用同一动作的实际 AsyncTask requirement；
- 编译失败给稳定 gap/error，不偷偷回退成单来源 Profile。

这一层只实现当前冻结模型。不要顺手引入 ApplicationTopology、BusinessAction、AuthorityFact、MeasurementFact、EffectProjector、ExperimentCase 或下一代权限编译模型。

## 测试、Sample 与 L5

协议、生成和 adapter 的最小验证示例：

```powershell
.\scripts\dev.ps1 test tests/protocols/web/test_web_response.py
.\scripts\dev.ps1 test tests/backend/workflows/security_setup/test_local_observer_wiring.py
.\scripts\dev.ps1 test tests/samples/web/test_collaboration_space.py
```

公共协议变化再补 architecture/schema registry 与 `dev.ps1 schema`。跨 Runner、真实六面观察和结果发布时，补三态 Golden：同一应用/项目/动作中，缺陷态真实形成副作用为 BLOCK，修复态关键来源完整未发现为 PASS，修复态关键 Blob 不可用为 INCONCLUSIVE。

Sample 测试还应覆盖 Range 边界、Case marker 关联、状态读取的 Windows 原子替换竞态，以及 owner-only 业务撤销。撤销应保留 Job、Task、Audit、Queue 和历史 Blob 文件，把当前 Project/Job/Task 置为 `REVOKED` 并从 Blob compatibility 当前命名空间隐藏；只有 `/reset` 可以物理清空测试 runtime。

唯一自动 L5 入口 `dev.ps1 sample-test` 检查应用接入、账号、Recording、流程、检查、结果和历史的完整用户路径。它不能以页面显示 403 作为安全验收；必须确认真实结果解释与已发布 Evidence 一致，并在退出后回收服务、Worker、Runner 和 Recording Chromium。人工只做展示验收。

## 常见失败怎样定位

- TARGET 收到 202 但 outcome 是 UNKNOWN：检查生成 Profile 是否绑定已有 AsyncTask requirement，以及同 Case 终态事实是否真正传入 classifier。
- TARGET 收到 403 但最终 BLOCK：先查 Observer 是否确认副作用；不要改 classifier 把 403 当 PASS。
- 新增 accepted status 后旧 preview 仍可提交：检查 Profile/hash 与 preview 失效链。
- 登录成功但后续请求越出 scope：检查 redirect、prepared session 作用域和每次请求的 authority 校验。
- 用户撤销后 Job、Task、Audit、Queue 或历史 Blob 文件消失：业务 DELETE 错接了测试 reset；恢复 `REVOKED` 当前态与历史保留的分层。
- `/reset` 没有恢复干净基线：检查它是否先停止 Sample Worker，再只清理当前隔离 Sample runtime；不要把 reset 逻辑复用到普通业务入口。
- Blob Range 少一字节或多一字节：按 HTTP inclusive end 语义检查 `bytes=0-N` 解析和预算。
- Windows 下任务状态偶发不可读：检查原子替换的共享读写锁，不要增加无界重试。
- wiring 可加载但页面缺来源：沿 Profile observer specs → EffectBinding → Runner Evidence 检查绑定，不在前端补假来源。

## 最终检查清单

Web 执行变化至少确认：

```text
当前生产 Target 仍只有 WEB，API 不直接执行目标
Profile 编译只读、确定、可 canonical/hash，旧 preview 正确失效
请求模板、redirect、目标范围和预算继续 fail closed
秘密只通过受控引用进入最小 Runner 生命周期
HTTP outcome 没有被当作 PASS/BLOCK/INCONCLUSIVE
202 同时具备声明 binding 和可靠同 Case 终态事实才 ACCEPTED
SETUP/TARGET/CLEANUP 身份和 Case marker 边界清楚
本地 wiring 保留六面来源及 required/corroborating 角色
直接协议、生成、Sample 和必要 Golden/L5 通过
没有引入未来模型或 Sample 专用生产分支
```

进一步约束见[执行与观察](../../01_系统地图/执行与观察.md)、[Web 执行配置与冻结快照](../../03_参考手册/协议/Web执行配置与冻结快照.md)、[权限契约与执行计划](../../03_参考手册/协议/权限契约与执行计划.md)和[验证与测试](../../04_工程约束/验证与测试.md)。
