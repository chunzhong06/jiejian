# 修改 Worker 与 Runner

> 状态：CURRENT。适用于 Job 生命周期、Worker 租约与 fencing、Runner 子进程、Case 编排、目标执行、Observer 调度、清理、结果封装和发布。

## Worker 与 Runner 解决什么问题

API 只接受、治理和查询检查请求，不直接访问高风险目标。Worker 从持久化队列取得 Job，持有租约并启动隔离 Runner；Runner 在冻结输入、受控身份、预算和目标范围内执行 Case，形成可验证的 CaseResult 与 Evidence；Worker 最后按 fencing 条件发布结果并收口生命周期。

完整链路是：

```text
API 提交 Run/Job
→ Worker claim + lease/fencing
→ 准备 attempt staging 和最小子进程环境
→ Runner 校验冻结请求与 source receipt
→ baseline observer
→ TARGET workflow
→ target/eventual observer
→ Verification 与 CaseResult
→ CLEANUP
→ Worker 校验并发布
```

进度文件、控制台输出和子进程退出码只帮助解释生命周期，不是 Verdict 或已发布结果的权威来源。

## 快速找到修改位置

| 我想修改什么 | 主要位置 | 通常需要一起核对 |
| --- | --- | --- |
| Worker 启停、轮询、取消和错误日志 | `product/backend/infra/runtime/worker/supervisor.py` | `lifetime.py`、Worker 直接测试、启动编排 |
| Worker 子进程环境和模块启动 | `product/backend/infra/runtime/worker/process.py` | source receipt、角色环境 allowlist、秘密注入 |
| Runner 进程监管与退出 | `product/backend/infra/runtime/runner/supervisor.py` | Worker supervisor、timeout/cancel、Windows 进程树 |
| Runner 依赖装配 | `product/backend/infra/runtime/runner/composition.py` | Observer registry、执行 adapter、storage/publication |
| Case 生命周期与观察阶段 | `product/backend/infra/runtime/runner/case_orchestrator.py` | `executor.py`、Observer coordinator、Verification |
| 冻结请求执行和 workflow | `product/backend/infra/runtime/runner/executor.py` | Web runtime、身份准备、目标范围和预算 |
| CaseResult/Evidence 组装 | `product/backend/infra/runtime/runner/result_builder.py` | `product/protocols/runner/`、publication reader |
| attempt 输入、输出和原子文件 | `product/backend/infra/runtime/runner/staging.py` | 路径约束、canonical hash、cleanup |
| 人类可读的运行进度 | `product/backend/infra/runtime/runner/progress.py` | API progress 投影；不能用于结果判断 |
| Job、Run 与结果持久化 | `product/backend/infra/storage/execution/`、`product/backend/infra/storage/results/` | UoW、fencing、published result reader |

函数与签名由自动代码参考生成。修改前还应阅读[执行与观察](../../01_系统地图/执行与观察.md)和对应协议，不从 runtime 代码反推公共语义。

## 先判断哪个层拥有状态

| 状态或事实 | 权威来源 | 可以怎样使用 | 不能怎样使用 |
| --- | --- | --- | --- |
| Job 是否可执行 | 持久化 Job 状态、租约和 fencing token | claim、续租、取消、终态提交 | 仅凭本地进程仍存在就认为拥有 Job |
| Runner 输入 | 已冻结 execution request、Profile 和 source receipt | 校验后只读执行 | 从当前数据库或 UI 选择重新拼输入 |
| Case 生命周期 | Runner 编排和受控错误分类 | 区分执行、观察、清理和发布失败 | 把 lifecycle failure 转成 BLOCK |
| 真实资源事实 | Observer Outcome/Evidence | 交给 Verification | 从进度文本或 HTTP 表面响应补事实 |
| PASS/BLOCK/INCONCLUSIVE | Verification | 原样写入 CaseResult | 由 Worker、LLM 或发布器重算 |
| 已发布结果 | 成功 fencing 的 publication | 供 API、报告和历史读取 | 读取未完成 attempt 私有文件冒充正式结果 |

## 修改 Worker 生命周期与租约

Worker 每次只能处理自己持有且 fencing token 仍有效的 Job。正常修改路线：

1. 从持久化仓储的状态转换和错误码开始，明确 claim、renew、complete、fail、cancel 的允许前态。
2. 在 `worker/supervisor.py` 只编排生命周期，不把 Runner 领域逻辑搬入 Worker。
3. 所有终态写入都携带当前 fencing 条件；失去租约后停止发布，不能覆盖新 Worker 的结果。
4. shutdown 先阻止新 claim，再取消当前可取消 Job，并等待/终止受控子进程。
5. 区分幂等冲突和真实故障：Job 已进入终态后再次取消返回 `JOB_TERMINAL_CONFLICT`，属于关机竞态的正常收口，不记录成运行错误；其他取消异常仍写稳定、净化的错误日志。

不要通过捕获所有异常消除噪声。只有已经证明语义等价的终态冲突可以忽略，权限、存储、租约、未知错误仍必须暴露。

## 修改子进程环境与隔离

Runner 由正式受控 Python 以模块方式启动，不能继承完整父环境。环境按进程角色明确 allowlist：公共运行变量、该角色声明的额外名称和最小 secret references 可以进入；宿主身份、调试凭据、无关 Token 与完整 PATH 污染必须拒绝。

每次 attempt 需要可校验的 source receipt，证明正在运行的源码/构建身份与 Worker 准备的一致。输入、输出、progress 和临时文件只进入当前 attempt staging；路径必须在 `var/` 运行边界内，不能由请求提供绝对路径逃逸。

子进程异常时保留 primary error：清理或收尾又失败，只能附加稳定原因，不能覆盖最初导致 Case 失败的错误。日志和异常正文不得包含请求正文、密码、Cookie、Token、完整环境或秘密值。

## 修改 Runner Case 编排

Runner 的顺序是安全语义的一部分。通常保持：

```text
冻结输入校验
→ BEFORE/baseline 观察
→ SETUP（如有）
→ TARGET
→ AFTER/EVENTUAL 观察
→ Verification
→ CLEANUP
→ CaseResult/Evidence 输出
```

具体 workflow 是否包含 SETUP/CLEANUP 由冻结 Profile 决定。Runner 不能临时生成未来模型，也不能在本阶段引入新的 Recovery 或 Effect projector。

实际 Observer 集合为 required 与 corroborating 的并集。两者都要运行、投影并发布，但只有 required 阻塞 baseline、target 和 Verdict；corroborating baseline 不进入 fingerprint/twin gate。修改 `case_orchestrator.py` 或 `result_builder.py` 时，要同时验证 CaseResult 和 Evidence 都保留全部实际来源及正确角色。

202 响应只有在冻结 classifier 声明 completion binding，且 Runner 从同一 Case 的可靠 AsyncTask 终态事实得到 `terminal_completed=True` 时才是 ACCEPTED。仅收到 202、任务缺失、任务身份不匹配或观察不完整都保持 UNKNOWN，不能继续推断权限结果。

## 修改 CaseResult、Evidence 与发布

Runner 输出必须在写入前通过严格协议模型。CaseResult 记录 Case 生命周期、Verdict 和全部实际 observer outcomes；Evidence 只包含已形成的受控事实、引用和稳定原因码。二者不能包含 progress 私有诊断、目标正文或秘密。

canonical/hash 必须以规范化模型为准：若模型会排序 observation facts 或 reason codes，计算 semantic hash 前必须执行相同排序。否则本地对象验证通过，跨进程 publication 仍会因摘要不一致失败。

Worker 发布前核对 run/job/attempt/fencing 身份、文档 hash 和协议版本。发布成功后，API、Finding、Report 和 History 只读取正式 publication；attempt 目录不是第二套查询接口。发布失败不能回写或改变 Runner 已形成的 Verdict，只能保留独立生命周期失败。

## 修改状态化 Web workflow 与清理

SETUP、TARGET、CLEANUP 使用 Runner 注入的 Case marker 关联本次副作用。清理必须精确且幂等：只删除本 Case 创建的任务、对象、审计、Queue 和数据库记录，不得清空 Sample 全局状态，也不得删除其他并发 Case。

正常清理规则：

- CLEANUP 使用 owner 身份和专用精确端点，不复用被测 subject 的权限。
- marker 缺失、格式错误或与当前 Case 不一致时 fail closed。
- 资源本来不存在或已由同一 Case 清理可以幂等成功。
- 部分清理失败要保留 `cleanup` 独立状态，并保持 primary execution/observation error。
- Golden 结束后检查 marker 对应的所有面均已撤销，不以单一 HTTP 200 代替实际状态检查。

清理是测试安全边界，不是绕过结果的手段。它发生在事实已经形成之后，不能让“资源随后被删除”反向改写本次 BLOCK。

## 测试与分层验证

所有正式后端测试只经仓库根 `dev.ps1 test`。先做最小直接邻域：

```powershell
.\scripts\dev.ps1 test tests/backend/infra/runtime/worker
.\scripts\dev.ps1 test tests/backend/infra/runtime/runner
.\scripts\dev.ps1 test tests/protocols/runner
```

涉及 Worker→Runner→publication 再补代表性跨进程或 E2E；涉及公共协议再运行 schema registry 与 `dev.ps1 schema`。三态 Golden 要证明同一应用、同一动作下 BLOCK、PASS、INCONCLUSIVE 均由真实发布事实产生，并检查 cleanup 后 Sample 无残留。

正式 E2E 的失败报告使用公开 API 返回的 run/job/result/evidence 有界摘要。临时调查可以只读检查 attempt，但定位完成后必须删除这种依赖；测试不能靠读取 progress 文件、Runner 私有目录、反向导入其他测试模块或重建生产聚合逻辑才能判断成功。

自动 L5 与 L4 分开：阶段收口运行一次 `dev.ps1 sample-test`，检查 GUI 启动、Worker/Runner 生命周期、真实 Sample、页面结果、取消/退出和进程回收；人工只做展示验收。不要为 L5 调整全局沙箱、降低凭据持久性或放宽安全边界。

## 常见失败怎样定位

- Worker 关闭时报取消失败，但 Job 已终态：确认错误码是否精确为 `JOB_TERMINAL_CONFLICT`；不要吞掉所有取消异常。
- Runner 已结束而 Job 一直 RUNNING：检查退出结果消费、fencing token 和 publication，不要用 progress 终态直接改数据库。
- publication 报 hash mismatch：比较规范化后的协议对象与 hash 输入顺序。
- 202 一直 UNKNOWN：检查生成 Profile 是否绑定已有 AsyncTask requirement，以及最终任务事实是否属于同一 Case。
- supporting 不可用导致整个 Case 不可判定：检查 required gate 与实际运行集合是否被混为一谈。
- 清理后其他用例数据也消失：立即停止，检查 cleanup 是否按 Case marker 精确过滤。
- 原始执行错误被 cleanup error 覆盖：恢复 primary error，附加独立 cleanup 状态。
- E2E 只有读取 attempt 私有文件才能诊断：把必要的安全摘要补到测试失败信息，随后删除私有依赖。

## 最终检查清单

Worker/Runner 变化至少确认：

```text
API 仍不直接执行目标、浏览器或高风险变异
Job claim、租约、fencing 和终态转换保持严格
子进程只获得角色 allowlist、最小秘密引用和有效 source receipt
Runner 顺序、预算、实际 Observer 集合和 required gate 未改变
202 只有可靠同 Case 终态完成事实才能 ACCEPTED
CaseResult/Evidence 完整且 canonical/hash 稳定
progress、attempt 私有文件和退出码没有成为结果真源
CLEANUP 只撤销当前 Case，幂等且不覆盖 primary error
直接 runtime/protocol 测试及必要跨进程 Golden 通过
运行数据、日志、缓存和生成物只进入 var/
```

进一步约束见[执行与观察](../../01_系统地图/执行与观察.md)、[Runner 执行协议](../../03_参考手册/协议/Runner执行协议.md)、[工作区与权限](../../04_工程约束/工作区与权限.md)和[验证与测试](../../04_工程约束/验证与测试.md)。
