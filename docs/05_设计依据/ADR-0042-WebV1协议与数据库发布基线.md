# ADR-0042：Web V1 协议与数据库发布基线

- 状态：已接受
- 日期：2026-08-25
- 适用范围：独立根文档、JSON Schema、严格 reader 与数据库迁移身份

原统一格式 1 与旧根迁移描述已由当前独立格式和签入迁移链取代；下文只保留仍适用的边界。

## 背景

公共文档需要明确的兼容边界，但产品版本、协议格式和数据库 revision 不能混为一谈。内部关系记录、普通 data view 和嵌套 DTO 不应冒充独立根文档。

## 仍适用的决策

只有独立持久化、跨进程或对外交换且有独立严格 reader 的根文档携带 schema_version。字段变化由所属根的 parser、canonical/hash、Schema 与消费者共同约束；嵌套 DTO 不重复版本。

Schema 的唯一登记入口是 `product/protocols/schema.py`。默认 `scripts/dev.ps1 schema` 只检查，不能为了消除漂移修改 Schema 而不核对公共语义。版本不支持、字段、关联或 hash 不符时拒绝读取，不增加猜测式 fallback。

数据库迁移由签入 revision 明确表达；不调用当前 ORM metadata 代替冻结历史，不改写已接受的 migration。未知 revision、结构或外键漂移在写入前拒绝；失败不删除未知数据，也不通过改 revision 伪装兼容。

## 当前适用事实

当前根格式各自演进，不再全部是字符串 1。HTTP runs 提交格式 2、持久 CHECK 请求格式 3、独立 Report 格式 5 和报告包 manifest 格式 1 分别由独立 reader 约束。完整根集合和允许的严格历史入口见[公共数据与 Schema 版本](../03_参考手册/协议/公共数据与Schema版本.md)。

当前数据库从 `0001_business_boundary_v2` 沿签入的 0002、0003、0004、0005 到 `0006_product_provenance`。精确升级条件、拒绝非空旧执行事实和数据保留规则由各 migration 与[数据与持久化](../01_系统地图/数据与持久化.md)定义。原统一格式和旧根迁移方案不作为当前代码或兼容承诺。

## 理由与取舍

按独立 reader 确定版本，避免产品发行号牵动全部机器协议；保留迁移身份使历史结构与当前 ORM 分开验证。代价是每次真实不兼容变化都需明确消费者、严格解析和迁移证据，不能用宽松回退掩盖不一致。

## 相关真源

- [公共数据与 Schema 版本](../03_参考手册/协议/公共数据与Schema版本.md)
- [数据与持久化](../01_系统地图/数据与持久化.md)
- `product/protocols/schema.py`
- `product/backend/migrations/versions/`
- `product/backend/infra/storage/db.py`
