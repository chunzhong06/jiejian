# Storage 与发布模块

> 状态：CURRENT。`product/backend/infra/storage` 与 migration 拥有 SQLite、事务、Repository 和当前数据结构；不可变结果发布由独立 artifact publication 边界完成。

## 职责

Storage 负责把项目、身份、Flow、Contract、Job、Run、Finding、Gate 等产品事实持久化，并用 Unit of Work 保证一次应用用例的事务边界。发布模块负责 staging、manifest/hash 校验、原子落盘、索引登记和崩溃恢复，让 API/CLI/Report 只读取已验证 publication。

## 非职责

Storage 不重算权限、安全效果、Verdict、Finding 身份或 Report 语义，不保存秘密正文，不用数据库状态替代独立进程事实，也不绕过 manifest/hash 读取半成品。测试 fixture 不建立第二套 schema。

## 稳定入口与模块边界

| 位置 | 负责什么 | 不负责什么 |
| --- | --- | --- |
| `product/backend/infra/storage/unit_of_work.py` | 事务开始、Repository 聚合、commit/rollback | 业务用例编排和跨事务缓存 |
| `product/backend/infra/storage/setup/` | Project、身份、Contract、配置等准备事实 Repository | Runner attempt 与发布文件 |
| `product/backend/infra/storage/execution/` | Job、Run、Recording、请求等执行记录 | 目标请求、Runner 结果构造 |
| `product/backend/infra/storage/results/` | Finding、Gate、Report 索引等结果记录 | Verification 与报告正文生成 |
| `product/backend/migrations/` | 唯一 Alembic revision 与约束命名 | 运行时自动猜测建表 |
| `product/backend/infra/artifacts/` | staging、publication、manifest/hash、恢复和工件扫描 | 数据库 migration、权限判断 |
| `var/data/` | 数据库、已发布 Evidence/Report 与产品事实运行边界 | 源码、开发缓存和秘密明文 |

自动结构入口见[Storage 代码参考](../../03_参考手册/代码/backend-infra-storage.md)。

## 我想修改什么

| 任务 | 主要位置 | 先读与直接验证 |
| --- | --- | --- |
| 修改项目、测试身份或安全准备 Repository | `storage/setup/`、`projects.py`、`contracts.py` | [修改数据库](../任务/修改数据库.md)；所属 storage + workflow 测试 |
| 修改 Job、Run、Recording 或 request 持久化 | `storage/execution/`、`storage/recordings.py` | execution records + runtime jobs/recording 测试 |
| 修改 Finding、Gate、Evidence 或 finalization 索引 | `storage/results/` | result records + results workflow 测试 |
| 修改一次应用事务包含的写入 | `storage/unit_of_work.py` 与所属 workflow | storage rollback/commit + workflow 直接测试 |
| 修改表、约束、索引或 migration | `product/backend/migrations/versions/` | migration baseline/constraint 测试与 fresh DB |
| 修改 Job/Run 崩溃恢复 | execution Repository 与 `runtime/jobs/reconciliation.py`、`recovery.py` | concurrency/publication recovery 测试 |
| 修改 Evidence/Result publication | `infra/artifacts/run_publication.py`、`run_packages.py` | artifact publication、manifest/hash、过期 attempt 测试 |
| 修改 Report 文件与 manifest | `infra/artifacts/report_store.py`、`report_reader.py` | [修改结果与报告](../任务/修改结果与报告.md)；report workflow/format 测试 |
| 修改运行目录归属 | `product/backend/infra/runtime/paths.py` | runtime path、cache、startup 直接测试 |

## 变更路线

先确定事实所有者和事务：字段属于当前业务对象、执行 attempt、不可变 publication 索引还是可重建缓存。持久结构变化只通过当前 migration 演进；Repository、模型、约束和测试同步修改。应用服务通过 Unit of Work 完成事务，不在 Router 或 Adapter 中手工 commit。

发布先在 attempt/staging 形成完整文件和 manifest，校验大小、路径、hash、关联与当前 fencing 后原子发布，再登记数据库索引。进程退出、取消或 crash 时由 reconciliation 依据正式状态机恢复；禁止直接 UPDATE 数据库把孤儿状态“修好”。

## 数据库事务与文件发布的分界

```text
应用 workflow
  → UnitOfWork 打开一次数据库事务
  → Repository 写入当前业务/执行索引
  → commit 或 rollback

独立 Runner attempt
  → attempt staging 写完整文件
  → manifest/hash/路径/预算校验
  → 当前 lease + fencing 接受
  → 原子 publication
  → 数据库登记不可变发布索引
```

数据库事务保证结构化事实的一致提交，publication 保证多文件结果不会半发布。二者需要明确的接受顺序和恢复逻辑，但不能用“数据库已有一行”证明文件完整，也不能用“磁盘有文件”证明该 attempt 已被接受。

## 必须保持的边界

- 数据库是产品持久事实，不是秘密仓库；SecretStore 只保存秘密正文，SQLite 只保存有限引用和非秘密元数据。
- migration 是唯一结构真源，`create_all`、测试 fixture 或启动代码不能并行建表。
- Repository 不产生 Verdict/Finding/Gate；这些由 core/workflow 在已验证事实上形成。
- publication 只接受当前 attempt/fencing 的 staging；过期租约、重复完成和孤儿文件不能覆盖已发布事实。
- Evidence/Report 发布后不可变；修复派生结果要形成幂等重算或新 publication，不原地修改语义文件。
- 运行数据只进 `var/`，源码树不出现数据库、日志、Evidence、Report、缓存或生成 artifact。
- 删除/清理先区分可重建缓存、测试 runtime 与产品数据；普通 cache clean 不触碰 `var/data`。

## 直接验证

```powershell
.\scripts\dev.ps1 test tests/backend/infra/storage
.\scripts\dev.ps1 test tests/backend/infra/runtime/jobs
.\scripts\dev.ps1 test tests/backend/infra/artifacts
.\scripts\dev.ps1 test tests/architecture/test_dependencies.py
```

按实际目录缩小范围。结构变化必须验证 fresh DB、约束和 Repository；publication 变化验证 crash/重复/过期 attempt/hash 负向路径。只有跨数据库与真实进程恢复才升级到相应 E2E，不为普通查询机械跑 L4/L5。

## 首错定位

| 现象 | 先检查 | 不要先做 |
| --- | --- | --- |
| fresh DB 无法启动 | Alembic head、migration 顺序、约束命名和正式 bootstrap | 在启动代码调用 `create_all` |
| workflow 返回成功但刷新后事实缺失 | UnitOfWork commit/rollback、Repository 落点和读取事务 | 用前端缓存遮盖 |
| 数据库索引存在但 Evidence/Report 不可读 | publication manifest、hash、相对路径和 reader | 绕过 manifest 直接读文件 |
| crash 后遗留 staging/运行态 | attempt、lease/fencing、reconciliation 和正式 Job 状态机 | 删除 Job 或直接 UPDATE 终态 |
| fixture 通过但 migration 失败 | fixture 是否真的从 migration 建库 | 为测试复制一套 schema |
| 清理误删产品数据 | `RuntimePaths` 分类及 cache/test/data 边界 | 把整个 `var/` 当普通缓存 |

## 相关真源

- [数据与持久化](../../01_系统地图/数据与持久化.md)
- [修改数据库](../任务/修改数据库.md)
- [报告与格式投影协议](../../03_参考手册/协议/报告与格式投影协议.md)
- [工件发布完整性与恢复边界](../../05_设计依据/ADR-0033-工件发布完整性与恢复边界.md)
- [验证与测试](../../04_工程约束/验证与测试.md)
