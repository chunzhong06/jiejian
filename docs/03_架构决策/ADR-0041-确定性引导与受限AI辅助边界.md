# ADR-0041：确定性引导与受限 AI 辅助边界

- 状态：已接受
- 日期：2026-08-24
- 适用范围：项目下一步引导、错误诊断、模型模板、模型出站、缓存与界面标识
- 取代：[ADR-0034：模型服务、候选生成与秘密边界](ADR-0034-模型服务候选生成与秘密边界.md)

## 背景

模型可以帮助普通用户理解下一步，但权限预期、真实执行、可信观察和 Verification 都必须继续以确定性事实为真源。原先由模型从 Requirement 生成 Contract Candidate 的产品路线让模型过早进入安全意图形成过程，也不能为当前普通用户主路径提供稳定、可恢复的引导。

## 决策

删除模型生成 Contract Candidate 的当前产品入口；Requirement parser、确定性 Candidate、Assessment、Drift、Diff、人工治理和 Contract 状态机继续保留。历史 LLM 来源字段只服务既有记录读取，不允许当前入口据此新建 Candidate。

`GuidanceSnapshot` 每次从 ProjectReadiness、CheckPreview、活动任务和可信结果等权威事实确定性计算下一步选项、服务端路由和稳定事实指纹；`ErrorDiagnosis` 只根据稳定错误码、Runner 阶段、原因、生命周期与 cleanup issue 形成恢复入口。二者都不调用模型、不持久化、不创建 CheckPlan，也不改变权限预期、安全结论或运行事实。

AI 辅助第一版只接受 `jiejian.next_step`、`jiejian.identity_preparation`、`jiejian.recording_priority`、`jiejian.permission_review_priority`、`jiejian.observation_recovery`、`jiejian.coverage_gap_summary` 和 `jiejian.error_explanation` 七个版本 1 模板。模板只传稳定 ID、短显示名、确定性状态、gap/error code 和系统给出的有限选项。模型输出必须通过严格 JSON、模板版本、数量、长度、去重和 option ID 白名单整体验证；任何越界都拒绝，不做猜测式修正。

GET 只重算确定性事实并读取缓存，不连接供应商。只有前端收到 `REFRESH_NEEDED` 后发出的明确 POST 才能调用默认启用且已配置秘密的模型 profile。同一项目、模板和事实指纹只允许一个生成任务；其他请求得到 `GENERATING`。成功结果和短失败退避只写 `var/cache/assistant/`，缓存命中时再次执行本地白名单校验。缓存不保存 raw prompt、供应商原始响应、隐藏思考、秘密、源码、Evidence 原文、数据库内容或日志。

模型关闭、缺少秘密、超时、限流或返回非法内容时，确定性 Guidance 和 ErrorDiagnosis 仍完整工作。真正使用模型的排序或解释统一显示紫色 `[AI辅助]`，并置于“界鉴确定”的事实之后；模型不参与 ALLOW/DENY、PASS/BLOCK/INCONCLUSIVE 或真实执行。

## 理由与取舍

先形成有限事实和动作，再让模型只选择已有 ID，可以获得可读排序与解释，同时不扩大安全信任边界；纯读 GET 与显式 POST 分离也避免页面读取或刷新偷偷联网。代价是模板和本地 validator 必须逐类维护，模型不能自由补充看似合理但未经系统确认的建议。

## 影响

模型 Provider、Profile、动态模型发现、推理强度、连接测试和共享 SecretStore 继续作为全局可选控制面。模型不再是 Contract Candidate 来源；Verification、Finding、Gate、Report、Observer、Runner 和 WebExecutionProfile 均不消费 AI 推荐。错误恢复页面改为读取服务端确定性诊断，不再按错误字符串或错误码正则猜测页面。

## 迁移与兼容

不新增数据库表或 migration。历史 Contract Candidate 元数据可按当前严格模型读取，但不能经当前服务/API 新建 LLM Candidate。AI 辅助缓存是可删除运行缓存，格式不兼容时直接视为未命中并重建；它不是产品数据或历史 Run 真源。模板、请求体和缓存根文档各自只接受版本 1，嵌套 API 读模型不重复携带 `schema_version`。

## 相关真源

- [产品入口与控制面架构](../02_架构设计/产品入口与控制面架构.md)
- [安全意图与验证架构](../02_架构设计/安全意图与验证架构.md)
- [数据与持久化架构](../02_架构设计/数据与持久化架构.md)
- [公共数据与 Schema 版本](../04_协议与数据/公共数据与Schema版本.md)
- `product/backend/workflows/assistant/`
- `product/backend/infra/llm/`
- `product/backend/api/routers/assistant.py`
- `product/frontend/src/features/workspace/`
