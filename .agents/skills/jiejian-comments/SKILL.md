---
name: jiejian-comments
description: 为界鉴项目自有源码和测试新增或更新中文注释。修改任一项目自有 Python 文件（包括 tests、fixture、Alembic 运行环境与 migrations/versions）、product/frontend、scripts、启动批处理或可执行 Sample 时使用；按模块职责维护文件头、公共边界契约和内部原因注释，并保证不改变可执行行为。
---

# 界鉴代码注释

## 目标

让维护者能够从注释快速确认模块定位、公共契约和危险边界，同时保持代码本身是实现真源。所有项目自有 Python 文件至少保留一行职责明确的 `#` 文件头；复杂文件再按职责增加信息卡、公共边界契约和内部原因说明。注释以中文为主，允许保留 Runner、Evidence、Schema、HTTP 等稳定工程术语。

## 工作顺序

1. 先阅读待改文件及其直接调用者，确认真实职责、输入输出、副作用、失败和清理路径。
2. 检查本次任务触及的全部项目自有 Python 文件是否具备职责性 `#` 文件头，再按模块角色选择密度，不使用统一长模板覆盖所有文件。
3. 更新已有注释，不在已有 docstring 前再叠加第二个字符串。Pydantic `BaseModel` 类的 docstring 会进入生成 Schema，注释专门优化中不得新增或改写；模型说明放在类定义前的 `#` 注释中。
4. 完成代码修改后补齐三层注释，并检查注释是否仍与最终实现一致。
5. 最终验证必须证明注释没有改变可执行结构；不得用“测试通过”替代结构等价性检查。

## 分模块密度

- Core、Protocol、Runner、Worker、事务、publication、安全边界：中等偏上至较高。必须说清不变量、失败语义和资源/事务边界。
- Workflow、复杂基础设施和启动脚本：中等偏上。突出编排阶段、补偿、并发、预算和清理。
- API、CLI、简单 Adapter、Repository：中等。文件头保持紧凑，只说明适配边界和不能承担的职责。
- 前端生产代码：中等；异步竞态、恢复路径、秘密处理和安全结论展示使用中等偏上密度。不得逐行解释 JSX。
- 测试、fixture、包标记、纯常量、明显胶水：低密度。除必需的一行文件头外，只在维护价值明确时补充。
- Alembic 运行环境与迁移辅助代码：按基础设施边界选择中等或更高密度；`migrations/versions/*.py` 使用低密度，保留生成结构，只解释人工迁移和反直觉数据库约束。

## 三层注释

### 文件信息卡

每个项目自有 Python 文件至少以一行 `#` 注释说明文件职责。该注释放在模块 docstring、`from __future__` 和普通 import 之前；存在 shebang 或编码声明时放在这些固定首行之后，shebang 或编码声明本身不替代职责注释。测试、fixture、包标记和 migration version 可只使用一行紧凑文件头，例如 `# 验证 Worker 租约到期后的恢复语义。`；不得用文件名、空泛的“测试模块”或 Alembic 生成标记代替职责说明。

独立业务、安全、协议、事务、编排或复杂基础设施文件使用完整卡片：

```text
# =============================================================================
# <模块名称>
#
# 定位
#   <模块在系统中的位置>
#
# 职责
#   <职责一>｜<职责二>｜<职责三>
#
# 边界
#   <明确不做什么，以及安全或失败约束>
#
# 调用链
#   <上游> → <本模块> → <下游>
# =============================================================================
```

Python 文件卡使用 `#`，不得用模块级字符串充当视觉文件头。简单 Router、CLI、Adapter、Repository 或前端文件只用一至三行紧凑说明，例如 `product/backend/api/routers/results.py` 和 `product/frontend/src/components/ErrorRecovery.tsx`；不要强行套长卡片。

### 测试与迁移

- 测试名称、fixture 名称和断言仍是行为真源。注释只补充无法从代码直接得出的场景前提、安全边界、并发时序、跨进程环境、预期失败原因和清理责任，不逐行讲解测试步骤。
- `product/backend/migrations/env.py` 及版本目录外的迁移辅助 Python 按生产基础设施处理。
- `product/backend/migrations/versions/*.py` 属于 Skill 范围，至少保留一行职责性 `#` 文件头。已提交的 revision 保留 Alembic revision 元数据、生成操作顺序和历史语义；只在人工触发器、数据回填、不可逆操作、方言限制或必须对称撤销等位置增加原因注释。
- `upgrade()`、`downgrade()` 和测试函数不为满足形式要求强制增加 docstring；需要函数级说明时可以在函数定义前或函数体相应阶段使用 `#`，避免把生成脚本改造成教程。

### 公共边界契约

为关键公共类和函数写短 docstring，优先说明：

- 输入必须满足的约束；
- 返回值、幂等或不可变语义；
- 会产生的事务、进程、文件、网络或凭据副作用；
- 失败如何表达，谁负责清理。

参考 `product/backend/infra/artifacts/run_publication.py`、`product/backend/infra/runtime/runner/execution.py` 和 `product/backend/workflows/onboarding/workflow.py`。显而易见的 getter、模型字段和框架样板不写教程式 docstring。

### 内部原因说明

行内注释只解释“为什么”：安全不变量、事务补偿、fencing、并发竞态、预算、资源生命周期、失败收敛和反直觉兼容。真实多阶段长流程可用 `# --- 阶段：... ---`，不使用编号步骤，也不复述下一行代码。

前端只在异步陈旧响应、恢复、秘密清理或安全结论投影处说明原因；PowerShell 说明外部命令、缓存事实、退出码和清理，并保留启动 `.ps1` 的 UTF-8 BOM；简单 CMD/BAT 启动薄壳可不写注释，且必须保持无 BOM、只含 ASCII。

## 禁止事项

- 不编造未实现的 Adapter、协议、执行能力、GUI 或安全保证。
- 不写作者、日期、历史开发阶段、营销措辞或失效的 V1/V2 双代叙事；真实 `schema_version` 和协议版本语义保留。
- 不逐行翻译代码，不建立注释覆盖率指标，不为注释拆分函数或模块。
- 不改变功能、Schema、数据库、协议、用户界面、测试期望或可执行语句。
- 不修改第三方代码、纯数据文件或可由构建重新生成的产物；纳入 Git 的 Alembic migration version 是本规则的明确例外，但不得仅为统一排版重写其生成语句。
- 不扩大到未触及文件；若发现真实代码问题，只报告，不借注释任务修复。

## 等价性验证

- Python：先确认本次触及的每个项目自有 `.py` 都有职责性 `#` 文件头，再用项目固定解释器、`PYTHONDONTWRITEBYTECODE=1` 和 `python -B`；剥离 module/class/function docstring 后比较 AST。对于 Pydantic 模型，还必须运行现有 Schema 漂移测试或比较生成 Schema，不能假设 docstring 不参与运行时元数据。
- TypeScript/TSX：使用 TypeScript parser 比较非注释语法节点；不要用无法正确处理 TSX/template literal 的通用文本扫描器。
- PowerShell：比较 parser token，排除 Comment、NewLine 和 EndOfInput；启动脚本另验证 UTF-8 BOM 未丢失。
- CMD/BAT：比较去除空行和独立 `REM` 注释后的可执行行。
- 最后运行 `git diff --check`，确认没有临时文件、缓存或范围外 diff。

若结构比较出现差异，先检查是否叠加了两个连续 docstring、误改字符串常量或把非 docstring 独立字符串当成注释；只修正注释变更，不用测试掩盖差异。
