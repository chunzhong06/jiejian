# ADR-0038：状态化 HTTP 身份与作用域边界

- 状态：已接受
- 日期：2026-08-20
- 适用范围：ExecutionProfile、HttpWorkflowBinding、身份准备、HTTP 适配器、Runner 工作流

## 背景

单次 Bearer 请求与状态码集合只能验证最简单接口，无法稳定表达登录、Cookie、CSRF、OAuth2 刷新、动态资源标识、表单、multipart、异步完成和多步骤业务流程。继续在 `ActionExecutionBinding` 上叠加特殊字段会把 transport 细节泄漏进 Contract，并产生多代执行链。

## 决策

PermissionContract 只表达安全意图；HTTP method、path、query、header、body、响应提取、身份引导、业务步骤、观察和清理全部位于 ExecutionProfile 与冻结执行快照。原 `ActionExecutionBinding` 单请求结构原地演进为 `HttpWorkflowBinding`，不保留并行旧执行链。

HTTP 请求模板只允许固定 method、相对 path、受控 query/header、显式 body 联合类型和有限 ValueSlot。body 仅支持 EMPTY、JSON、FORM_URLENCODED 与受控 MULTIPART；不得执行代码或表达式。普通请求模板拒绝 Host、Content-Length、Transfer-Encoding、Connection、Authorization、Cookie 与 `X-Jiejian-*`，身份头和 Cookie 只能由身份运行时注入。

响应分类由确定性 `HttpOutcomeClassifier` 完成。谓词只支持状态、有限 JSON path、header、重定向路径、HTML selector/attribute 和正文常量；accepted 与 denied 同时或同时不匹配均为 UNKNOWN。202 只有在声明完成绑定并观察到终态时才可判为 ACCEPTED。

身份绑定是有界联合：BEARER、STATIC_HEADERS、COOKIE_SESSION、LOGIN_WORKFLOW、OAUTH2_CLIENT_CREDENTIALS、OAUTH2_REFRESH_TOKEN。每个身份拥有独立、仅内存 Cookie jar；不读取系统代理或浏览器 Cookie，不跨 case 复用。bootstrap 与业务工作流分离，失败不得回退匿名。CSRF 值只在同身份、同 origin 和允许目标内作为 secret slot 传播，不写日志、Evidence 或持久化数据。认证端点使用独立 `AuthTargetScope`，不得扩大业务和 Observer scope；只在明确 token-expired 分类后刷新一次。

项目级 TestIdentity 只是已确认角色与可安全重放登录状态的控制面资产，不等同于 `HttpIdentityBinding`。其准备过程在独立 headed BrowserContext 中由用户登录并显式确认，只保存当前 host 的有限 Cookie 或当前 origin 的单一 Bearer 到共享 SecretStore；数据库保存元数据与精确引用。TestIdentity 在后续确定性编译前不得直接进入 Runner，身份准备也不生成业务 Recording 事件。

确认后的 Flow 编译为冻结 `HttpWorkflowBinding`。步骤目的只允许 SETUP、TARGET、CLEANUP，且恰有一个 TARGET；动态值只能从 case、固定常量、secret ref 或先前步骤的有限响应位置取得。执行顺序固定为恢复/清理、身份准备、SETUP、BASELINE、BEFORE、TARGET、AFTER、EVENTUAL、效果聚合、Verification、CLEANUP。TARGET 未执行、身份/SETUP/提取/基线失败均不得形成 PASS。

## 理由与取舍

把身份和工作流放在冻结执行配置中，既能支持真实状态化 Web，又保持 Contract 与 Verification 不依赖 HTTP。代价是 Profile 和 Runner wire format 发生一次不兼容升级，仓库样例与 fixture 必须同步迁移。

## 影响

ExecutionProfile、RunnerInput、Evidence、Flow 和相关 Schema 升级为单一当前格式；秘密仍只以引用进入协议并在 Runner 内存中解析。业务工作流、身份 bootstrap 和 Observer 使用互不混淆的 scope 与预算。

## 迁移与兼容

仓库样例、fixture 和生成 Schema 一次性迁移。旧单请求 binding、`accepted_statuses`/`denied_statuses` 与隐式 Bearer 模式不兼容读取，也不建立 v2→v3 双执行链。

## 相关真源

- [执行与观察架构](../02_架构设计/执行与观察架构.md)
- [Web 执行配置与冻结快照](../04_协议与数据/Web执行配置与冻结快照.md)
- [Runner执行协议](../04_协议与数据/Runner执行协议.md)
- [录制与Flow协议](../04_协议与数据/录制与Flow协议.md)
