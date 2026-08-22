# Observer 观察协议

> 状态：CURRENT。本文解释观察语义和边界；字段约束以 `observer.py` 与 Observer Schema 为准。

## 目的与消费者

Observer 为 Runner 和 Verification 提供真实副作用、异步状态和审计事实。消费者包括 Runner 编排、Evidence 组装、Verification 和报告限制说明。

## 协议边界

- `ObserverSpec` 声明 observer 身份、类型、目标、BASELINE/BEFORE/AFTER/EVENTUAL phase、required 和 budget。
- `EffectBinding` 把 manifest effect 绑定到权威/佐证通道、版本化投影和时间闭合策略。
- `ObserverInvocation` 描述一次 phase 调用及其 correlation。
- `ObservationEnvelope` 携带 target、window、correlation、causality 和 completeness。
- `ObserverOutcome` 表达状态、观察事实、可靠性、原因和限制。
- 当前类型包括 API、SQLite、Azure Queue、Azure Blob、结构化审计和异步任务观察；具体外部读取边界由实现和配置决定。

## 生命周期与数据流

```text
Execution case → ObserverSpec
  → phase invocation/correlation
  → source read within budget
  → ObservationEnvelope/Outcome
  → ObservationFact/SecurityEffectFact/Evidence
  → Verification
```

phase、case、task、sequence 和逻辑资源事实必须可关联。观察窗口、关联标识、基线完整性与时间闭合共同决定观察是否可用于结论。任一权威完整通道可确认效果；ABSENT 必须由全部必需通道和 CLOSED closure 共同证明。

## 失败与安全语义

required observer 缺失、超预算、超窗口、关联冲突、来源不完整、读取失败或可靠性不足时，结果只能支持 INCONCLUSIVE，不能解释为安全或未发现问题。观察器不得直接写 Verdict、Finding 或 Gate。

Observer 只读取用户明确授权的目标或本机资源；凭据、日志和响应内容必须限长并脱敏。异步、Queue、Blob 和审计读取不得绕过 Runner/Worker 的执行范围、清理和 publication 边界。

## 版本规则与 Schema 真源

Observer 模型和当前 Observer Schema 主要为 2。协议正文不复制完整 JSON 字段；严格解析、required 和枚举以：

- `product/protocols/observer.py`
- `product/protocols/schemas/observer/`

为准。Schema 版本不表示产品代际，旧开发观察格式不兼容读取。

## 相关真源

- [执行与观察架构](../02_架构设计/执行与观察架构.md)
- [安全意图与验证架构](../02_架构设计/安全意图与验证架构.md)
- `product/protocols/observer.py`
- [因果关联实验](../05_路线与研究/技术实验/因果关联实验.md)
