# ADR-0042：Web V1 协议与数据库发布基线

- 状态：已接受
- 日期：2026-08-25
- 适用范围：界鉴自有独立根文档、JSON Schema、严格 reader、SQLite migration 与旧开发运行数据

## 背景

正式发布前的开发历史使不同自有根文档分别使用 1～5 的格式号，数据库也累积了多份只服务开发迭代的增量 migration。这些编号不能表达产品价值，却会让当前 reader、Schema、Sample、报告版本和数据库兼容判断长期携带尚未发布的历史。

Web V1 需要一个可以清楚解释、严格验证且便于未来演进的起点，同时不能把关系型内部记录、API data view 或嵌套 DTO 伪装成独立兼容边界。

## 决策

### 1. 自有独立根从格式 1 起步

只有能够独立持久化、跨进程或对外交换并拥有独立严格 reader 的界鉴自有根文档携带 `schema_version`。Web V1 的这些根全部使用字符串 `"1"`；嵌套 DTO、关系型拆列记录和普通 API data view 不重复版本。

每个根只接受一个当前格式。旧开发期 v2～v5 reader、fallback、alias 和猜测式兼容路径不进入 Web V1。业务治理版本、引擎/规则/模板/策略版本、供应商 API 版本、SARIF 版本和数据库 revision 继续保持各自语义，不能因根格式重基线而改写。

### 2. Schema 由唯一注册表治理

`product/protocols/schema.py` 是 checked-in JSON Schema 的唯一注册表和生成检查入口。默认 `scripts/dev.ps1 schema` 只检查运行时模型与签入文件是否一致；只有显式 `schema -Update` 才更新已登记文件。未登记、缺失或内容漂移都使检查失败。

没有 checked-in Schema 的内部有界根仍必须有专用严格 reader/codec 和直接测试；它们不能借此绕过版本、预算、秘密或 canonical 约束。

### 3. 数据库从唯一 0001_web_v1 起步

`product/backend/migrations/versions/0001_web_v1.py` 是 Web V1 唯一数据库发布基线，从空库显式创建当前全部表、列、约束、索引和触发器，不在 migration 中调用当前 ORM metadata 代建结构。

缺失或空数据库可以建立该基线；非空数据库必须已经具有精确 `0001_web_v1` revision 和当前结构签名。旧开发 revision、未知 revision，以及缺失、额外或错误的表、列、索引、约束或触发器都在写入前拒绝。

### 4. 旧开发 var 不自动迁移

旧开发数据库、旧公共根文档和旧运行目录不自动迁移、不双读，也不通过修改 revision 冒充当前结构。用户需要保留事实时先备份，再重新初始化本地 `var`；拒绝路径不得删除或改写未知数据。模型密钥和测试身份秘密继续由共享 SecretStore 的精确引用边界管理，不随数据库重建进入公共数据。

### 5. 发布后的未来演进

未来某个独立根发生真实不兼容变化时，只为该根升级到 `schema_version="2"`，并同时更新模型、严格 reader、canonical/hash、注册 Schema、消费者、Sample、测试和 CURRENT 文档。是否读取旧格式必须由新的兼容决策和明确迁移证明决定，不能静默加入 fallback。

Web V1 发布后的数据库结构变化新增 `0002_*`，其 `down_revision` 指向 `0001_web_v1`，并显式实现结构与必要数据迁移；不得改写已发布的 0001。根格式版本和 Alembic revision 始终是两个独立边界，不能互相替代。

## 理由与取舍

统一发布起点可以删除开发历史分支，让 parser、Schema、Sample、报告和数据库门禁只证明当前产品。代价是旧开发运行数据需要备份后重建，且未来不兼容演进必须显式增加版本、迁移和验证证据。

## 影响

协议根、API envelope、前端客户端、Sample、ReportVersions 和 checked-in Schema 统一到格式 1；内部伪版本字段删除。migration 目录只保留 Web V1 基线，Storage 启动门禁对旧 revision 和结构漂移 fail closed。Permission、Verification、Evidence、Finding、Gate 和报告真源语义不因本决策改变。

## 相关真源

- [工程设计规范](../01_技术规范/工程设计规范.md)
- [系统总体架构](../02_架构设计/系统总体架构.md)
- [数据与持久化架构](../02_架构设计/数据与持久化架构.md)
- [公共数据与 Schema 版本](../04_协议与数据/公共数据与Schema版本.md)
- `product/protocols/schema.py`
- `product/protocols/schemas/`
- `product/backend/migrations/versions/0001_web_v1.py`
- `product/backend/infra/storage/db.py`
