# Storage

## 定位

`storage` 是 SQLite、Alembic metadata、ORM 映射、Repository、原子 Job SQL 和 UnitOfWork 的唯一持久化边界。

## 负责 / 不负责

- 负责数据库升级、Session、事务、Record 映射、secret 拒绝和条件更新。
- 为应用能力提供 `StorageUnitOfWork`，不把 ORM Row 或 Session 暴露给上层。
- 不执行业务流程、Verification 判定或 Runner 进程控制。

## 子模块与 public API

- `db.py`：SQLite engine、session factory、数据库路径和 Alembic 升级。
- `models/`：共享 Base/metadata 和按聚合拆分的 ORM Row。
- `repositories/`：不可变 Storage Record 与聚合读写。
- `job_control.py`：claim、lease、cancel、retry、complete 等原子条件 SQL。
- `unit_of_work.py`：事务范围与 Repository 聚合。
- `jiejian.storage` package 根导出的名称是正式稳定持久化入口；完整清单以 `storage/__init__.py::__all__` 为准。

## 调用与数据流

```text
Application / Contracts / Recording / Execution / Results
→ StorageUnitOfWork
→ Repository 或 JobControlRepository
→ SQLAlchemy Session
→ SQLite + Alembic schema
```

## 关键不变量和失败语义

- 生产建库和升级只使用签入 Alembic migration；`create_all` 不能替代升级链。
- 表名、列、约束、索引、metadata 和历史 migration 是兼容边界。
- Job 条件写入必须在数据库语句中检查 lease/fencing/state，不能先读后无条件写。
- UnitOfWork 只有显式 `commit` 才提交；异常和未提交退出都 rollback。
- secret 检查发生在序列化持久 payload 之前，数据库异常通过稳定错误码和脱敏消息上报。

## 修改与测试入口

- Storage：[`tests/storage`](../../../../tests/storage/)
- Job 原子状态：[`tests/execution/worker`](../../../../tests/execution/worker/)
- migration：[`backend/migrations`](../../../migrations/)
- 数据格式：[公共数据格式](../../../../docs/04_协议定义/数据格式.md)

## 相关规范、协议与 ADR

- [ADR-0003](../../../../docs/03_技术决策/ADR-0003-阶段2持久化设计.md)、[ADR-0005](../../../../docs/03_技术决策/ADR-0005-阶段2任务控制设计.md)
- [项目设计规范](../../../../docs/02_开发规范/项目设计规范.md)
