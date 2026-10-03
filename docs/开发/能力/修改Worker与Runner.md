# 修改 Worker 与 Runner

> 状态：CURRENT。当前装配 CHECK 与 RECORDING，以下入口优先指向实际生产链。

普通运行准备通过 `infra/runtime/process/controlled/artifact.py:inspect_runtime_files` 核对既有扫描文件，通过 `node_owned.py:node_execution_identity` 核对解释器和固定执行器。加载回执使用 `RuntimeLoadJobs.read_in_work` 复用调用方事务读取；这些入口不启动目标、不另开提交边界，实际加载仍归 Runtime Worker。

## 快速找到修改位置

| 任务 | 唯一入口 | 直接验证 |
| --- | --- | --- |
| Worker claim、取消、恢复与 shutdown | `product/backend/infra/runtime/worker/supervisor.py` | `tests/backend/infra/runtime/worker/` |
| Worker 进程与受控角色环境 | `product/backend/infra/runtime/worker/process.py`、`product/backend/infra/runtime/process/` | 进程身份、退出与租约测试 |
| 当前 CHECK 子进程监管 | `product/backend/infra/runtime/check_runner/supervisor.py` | `tests/backend/infra/runtime/jobs/` |
| 当前 Case 执行与验证 | `product/backend/infra/execution/check_executor.py` | `tests/backend/infra/execution/` |
| 来源观察 | `product/backend/infra/observers/checks/check_runtime.py` | `tests/backend/infra/observers/` |
| 请求持久化与严格发布 | `product/backend/infra/runtime/jobs/requests/checks.py`、`product/backend/infra/artifacts/checks/check_publication.py` | `tests/backend/infra/runtime/jobs/`、`tests/backend/infra/artifacts/` |
| 录制子进程 | `product/backend/infra/recording/` | `tests/backend/infra/recording/` |

API 接受和查询请求；Worker 持有 Job 租约与 fencing，启动独立 Runner；Runner 消费冻结 request/bundle，在受控范围内执行并形成 CheckEvidence/CheckRunnerResult；Worker 验证发布，再由 Reader/Story 只读投影。进度、退出码与日志不是安全结论。

## 修改 Worker 生命周期与租约

Worker 每次只能处理自己持有且 fencing token 仍有效的 Job。正常修改路线：

1. 从持久化仓储的状态转换和错误码开始，明确 claim、renew、complete、fail、cancel 的允许前态。
2. 在 `worker/supervisor.py` 只编排生命周期，不把 Runner 领域逻辑搬入 Worker。
3. 所有终态写入都携带当前 fencing 条件；失去租约后停止发布，不能覆盖新 Worker 的结果。
4. shutdown 先阻止新 claim，再取消当前可取消 Job，并等待/终止受控子进程。
5. 区分幂等冲突和真实故障：Job 已进入终态后再次取消返回 `JOB_TERMINAL_CONFLICT`，属于关机竞态的正常收口，不记录成运行错误；其他取消异常仍写稳定、净化的错误日志。

不要通过捕获所有异常消除噪声。只有已经证明语义等价的终态冲突可以忽略，权限、存储、租约、未知错误仍必须暴露。

## 修改子进程环境与隔离

运行引用由`workflows/runtime/ports.py`按持久项目归属选择提供方，检查和交付通过同一窄端口读取；归属冲突或加载失败不得回退到另一提供方。当前注册官方示例和受支持的普通 Node 应用；普通 Node 通过冻结副本、持久 RUNTIME_LOAD Job 与所有权回执接入，具体加载与存活核对见下文。

Runner 由正式受控 Python 以模块方式启动，不能继承完整父环境。环境按进程角色明确 allowlist：公共运行变量、该角色声明的额外名称和最小 secret references 可以进入；宿主身份、调试凭据、无关 Token 与完整 PATH 污染必须拒绝。

每次 attempt 需要可校验的 source receipt，证明正在运行的源码/构建身份与 Worker 准备的一致。输入、输出、progress 和临时文件只进入当前 attempt staging；路径必须在 `var/` 运行边界内，不能由请求提供绝对路径逃逸。

子进程异常时保留 primary error：清理或收尾又失败，只能附加稳定原因，不能覆盖最初导致 Case 失败的错误。日志和异常正文不得包含请求正文、密码、Cookie、Token、完整环境或秘密值。

## 恢复与发布

恢复候选只是待核对线索，不是完整 Job。确认子进程退出后，仍须回读持久 Job，核对 RUNNING、lease owner 与 fencing token；状态或代际变化时不得替另一所有者收口。旧进程未确认退出不能接管，未知 TARGET 结果不能自动重试。

Worker 发布核对 run/job/attempt/fencing、文档版本与 hash；所有终态写入使用同一所有权条件。发布前失败不暴露临时文件作为结果，已发布结果不可改写。规范排序与 canonical 输入必须一致，避免模型本地通过但跨进程摘要不一致。

## 普通应用运行加载

`RUNTIME_LOAD` 是独立 Job 目标，持久输入和启动回执位于 `runtime_loads`，不创建 Run 或 Verdict。普通 CHECK/Recording Worker 不领取它。`LocalRuntimeSupervisor` 只启动固定 Runtime Worker；Worker 核对冻结 Node ESM 副本、解释器、Windows Job 归属和精确 IPv4 监听者后，以租约和 fencing 条件发布回执，随后继续持有目标进程。历史 SUCCEEDED 仅说明启动曾经完成，当前存活需重新核对。

新控制面会话不重放旧会话待执行加载。关闭或移除项目仅回收界鉴拥有的树，不处理外部占用端口的进程。运行加载复用已有 Job 的取消、租约和恢复，不维护另一套调度生命周期。直接验证见 `test_runtime_load_jobs.py`、`test_runtime_supervisor.py`、`test_node_runtime.py` 与 `test_node_runtime_activation.py`。

## Case 执行与恢复的证据边界

具体顺序、身份、资源、proof 和恢复策略由冻结输入定义，不能从 live 页面状态重建。当前 Observation 角色为 VERDICT_REQUIRED、SUPPORTING、DIAGNOSIS_REQUIRED；必需证据的充分性由 Verification 判定。202 完成要求原响应谓词与精确可信任务终态同时成立，任务缺失、关联冲突或观察不完整不能变为成功，见[Web 执行](修改Web执行.md)。

恢复只撤销本 Case 的当前效果，使用明确 owner 与精确资源，不清空整个应用、不删除既有审计和任务历史。marker/引用不匹配拒绝；部分恢复失败保留独立状态，不覆盖首个执行错误，也不把曾经形成的禁止效果改为未发生。

## 验证与首错定位

按表选择一个职责和直接消费者，通过 `dev.ps1 test` 验证；进程或 publication 修改补真实跨进程测试，公开格式变化补 Schema。最终真实启动、GUI 和资源回收走唯一 sample-test，详见[验证](../验证.md)。

Job 长期 RUNNING 先查真实进程、结果消费与所有权；publication hash 失败查 canonical；辅助观察覆盖 BLOCK 查角色消费；清理影响其他资源立即停止并核对精确引用。正式失败输出只保存公开、有界的 run/job/result/evidence；私有 attempt 可临时诊断，但不能留作 E2E 成功依据。

独立 Contract Runner 仍有协议与直接消费者，位于 `product/backend/infra/runtime/runner/`，不作为当前 CHECK fallback。只有修改该独立实现才进入其 Case 编排和协议测试；对应说明见[Runner 协议](../../参考/协议/Runner执行协议.md)。
