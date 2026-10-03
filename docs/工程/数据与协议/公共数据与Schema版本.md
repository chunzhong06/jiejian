# 公共数据、根版本与reader

> 状态：CURRENT。本页说明独立交换根的责任和读取边界；具体注册模型、Schema路径及根版本由[注册与格式](../../参考/生成/注册与格式.md)生成。

## 什么携带schema_version

只有独立持久化、跨进程或对外交换且有独立reader的根文档携带版本。嵌套DTO、关系字段、Plan组成对象及API data不重复版本。产品版本、根格式版本与数据库revision分别演进，不能互相替代。

字段、required、枚举、canonical/hash、大小与秘密过滤以严格模型、Schema及reader为准。生成参考从签入Schema投影版本；模型与Schema一致性由 `dev.ps1 schema`验证，不由Docs索引代替。

## 当前数据族及消费关系

| 数据族 | writer与用途 | reader与范围 | 详细语义 |
| --- | --- | --- | --- |
| Permission/规则候选 | 正式批准事务、RuleCandidateService | 准备、计划、候选审阅 | [批准协作](../../能力/权限规则/批准协作.md) |
| v3执行请求 | CheckService冻结完整当前考题 | CHECK Worker/Runner | [权限与计划](../../能力/检查执行/协议/权限与检查计划.md) |
| CHECK runtime | RuntimeBuilder按当前运行provider与来源构建 | runtime严格parser识别基础、受控Python、Node、历史JSON及managed变体；reader可读不等于新writer可再次采用 | [Runner协议](../../能力/检查执行/协议/Runner执行协议.md) |
| CHECK结果/证据/publication | Runner、Worker发布 | CheckResultReader/Story/History/Repair；运行对应有独立结果变体 | [检查与发布](../../能力/检查执行/检查与发布协作.md) |
| 身份准备 | 独立受控登录准备 | 主进程接受非秘密结果和SecretStore引用 | [身份准备](../../能力/账号与材料/协议/测试身份准备协议.md) |
| Recording/FlowDraft/Flow | Recording Runner与人审阅 | 当前严格reader、材料绑定及明确的历史只读reader | [录制协议](../../能力/账号与材料/协议/录制与Flow协议.md) |
| 证明来源/scope/preflight/report/adoption | ProofPreparationService与独立Runner | 发布校验、GUI采用、CHECK冻结 | [证明来源契约](../../能力/证明来源/证明来源契约.md) |
| Node/受控Python运行、事务记录 | 运行provider、持有目标树的Worker | 回执读取、实例核验、独立观察 | [受控运行](../../能力/应用接入/受控运行对应.md) |
| 开发任务/上下文/交付/回执 | DevelopmentService同事务提交 | DevelopmentReader及精确Run关联 | [交付回执](../../能力/结果与变化/协议/开发任务与交付回执.md) |
| Observer/Web | 当前配置、Runner调用、来源适配 | 各严格codec与执行消费者；独立WebProfile另有保留reader | [Observer](../../能力/检查执行/协议/Observer观察协议.md)、[Web配置](../../能力/检查执行/协议/Web执行配置与冻结快照.md) |
| 独立Report/Artifact/旧Contract | 独立writer/reader或历史实现 | 不属于当前GUI/MCP/CLI结果主链，不能作为CHECK fallback | [保留报告](../../参考/保留实现/报告与格式投影协议.md)、[产物扫描](../../参考/保留实现/产物检查协议.md) |

## 没有checked-in Schema的根

API envelope、健康/就绪、Settings、Doctor输出、AI模板输入/受限输出/缓存等在对应模块拥有严格reader。它们是否独立以及接受哪一个版本须读该reader；不能因没有Schema就删版本，也不能给每个Pydantic模型加版本。

前端只验证最外层ApiResponse根，再读取data或脱敏error；嵌套ApplicationUnderstanding、Guidance、模型目录及错误诊断不重复根版本。前端资产manifest独立由构建器写、API核验，build_id证明资源对应，不是可信签名或操作授权。Runner进度位于staging外，只供展示，不参与Verdict或恢复判断。

## 兼容与拒绝

每个根按其明确reader接受版本；不从公共基类默认值或相似字段猜版本。未知字段、未知版本、非有限数、canonical/hash不符、身份关联错误、超限或秘密泄漏应失败。历史只读解析入口只允许其明确的格式，不自动升级成可执行输入。

数据库head与完整迁移链只查[数据库迁移](../../参考/生成/数据库迁移.md)。数据保留/拒绝条件由迁移源码与[数据架构](数据与持久化.md)解释；本文不重复手写当前head。

变更步骤见[修改公共协议](修改公共协议.md)。
