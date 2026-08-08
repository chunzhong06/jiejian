# 界鉴项目设计与开发规范

> 状态：当前制作阶段 V1 设计基线
> 生效日期：2026-08-08
> 适用范围：界鉴的源代码、配置、测试、运行数据、报告、插件和部署资产
> 规范级别：本文件是项目设计与实现的主要依据；入口决策见 docs/decisions/ADR-0001-entrypoints.md

## 1. 规范用语与约束优先级

本文中的“必须”“不得”是强制约束，“应该”是默认约束，“可以”是可选能力。

发生冲突时，按以下顺序处理：

1. 法律、比赛规则、目标系统授权边界和安全要求。
2. AGENTS.md 中的协作与变更规则。
3. 已接受的架构决策记录。
4. 本规范。
5. 模块内说明、注释和临时实现方案。

实现不能满足本规范时，不得静默绕过。应先记录事实、影响和替代方案；若涉及架构、入口、状态机、存储、安全边界或公开接口，必须新增或修订 ADR，并在同一次变更中更新本规范、迁移方案和相应测试。

## 2. 项目定义

### 2.1 名称与定位

项目名称：界鉴。

项目定位：面向 Vibe Coding Web 应用的安全意图差分验证与交付门禁系统。

界鉴不是另一个通用漏洞扫描器。它围绕 AI 生成或 AI 大量参与生成的 Web 应用，将自然语言需求、页面交互、接口行为和部署产物转化为可执行安全契约，再通过关系变异、多观察者取证和持续回归，回答以下问题：

- 开发者声明的安全意图是否真正落实到运行行为。
- 正常请求与攻击变体之间是否保持应有的安全关系。
- 前端提示、HTTP 状态和后端真实副作用是否一致。
- 一次修复是否在后续 AI 修改中再次退化。
- 当前构建是否满足交付门禁。

### 2.2 核心验证链

界鉴的主链固定为：

安全意图 → 可执行契约 → 关系变异 → 多面观察 → 确认证据 → 回归门禁

每一条最终结论必须能够沿此链回溯。不能只有“模型认为有风险”而缺少规则、请求、观察和证据。

### 2.3 核心创新约束

V1 的技术中心只保留两个：

1. 安全意图—运行行为契约编译与漂移检测。
2. 带因果标记的多观察者副作用判定。

其他扫描器、模型、报告格式和插件均围绕这两个中心服务，不得反客为主。

## 3. 范围与非目标

### 3.1 V1 范围

- 本地或明确授权环境中的 Web 应用验证。
- 从需求、配置、录制流量和人工输入建立安全契约。
- 身份交换、资源交换、字段缺失、字段越权、重放和有限序列变异。
- 浏览器、HTTP、业务 API、数据库代理、日志和部署产物观察。
- 证据归一化、结论分级、人工确认、回归基线和交付门禁。
- JSON、HTML、SARIF、JUnit 报告。
- CLI、Web GUI、CI 和内部 REST API 入口。

### 3.2 V1 非目标

- 未经授权的公网批量扫描。
- 替代人工渗透测试或完整代码审计。
- 以 LLM 文本判断直接给出最终漏洞结论。
- 一开始支持所有语言、框架、数据库和云平台。
- 一开始建设微服务、分布式调度或插件市场。
- 一开始提供 TUI 或原生桌面应用。
- 自动执行不可逆破坏性测试。

## 4. 启动方式与产品入口

入口决策以 docs/decisions/ADR-0001-entrypoints.md 为准。

### 4.1 入口角色

| 入口 | V1 地位 | 主要用户 | 职责 |
| --- | --- | --- | --- |
| Web GUI | 主要产品入口 | 开发者、评委、安全分析人员 | 项目接入、流量录制、契约确认、运行观察、证据分析、报告展示 |
| CLI | 首个实现入口、能力基线 | 开发者、自动化脚本、调试人员 | 配置校验、录制、运行、回归、报告、服务启动和故障诊断 |
| CI | 强制交付入口 | CI/CD 系统 | 复用 CLI 执行无交互门禁并返回稳定退出码 |
| REST API | 内部控制面 | GUI、CLI、集成程序 | 管理资源和任务，不直接执行目标请求 |
| TUI | V1 不实现 | 远程终端用户 | 仅在后续确有远程只读监控需求时评估 |
| 桌面壳 | V1 不实现 | 单机非技术用户 | 后续仅在安装、托盘、系统代理等需求成立时评估 |
| Docker Compose | 部署方式 | 团队、演示、复现实验 | 提供可复现服务环境，不作为本机浏览器录制的唯一方式 |

### 4.2 推荐启动命令

主要本地入口：

~~~text
jiejian serve --open
~~~

该命令负责加载配置、检查迁移、启动 API、Worker 和静态 Web 服务，并在健康检查通过后打开浏览器。它不得隐藏启动失败；任一必要组件失败时必须退出并给出结构化错误。

能力型 CLI：

~~~text
jiejian doctor
jiejian project validate <path>
jiejian record <project_id>
jiejian contract build <project_id>
jiejian run <project_id>
jiejian regression <project_id>
jiejian report <run_id> --format html
jiejian ci <project_id>
~~~

CLI、GUI 和 CI 必须调用同一应用服务与验证引擎，不得维护三套业务逻辑。

## 5. 总体架构

V1 采用模块化单体加独立 Worker 和隔离 Runner。控制面与数据面分离，但共享同一领域模型和应用服务契约。

~~~mermaid
flowchart LR
    U["用户 / CI"] --> GUI["Web GUI"]
    U --> CLI["CLI"]
    GUI --> API["FastAPI 控制面"]
    CLI --> APP["应用服务"]
    API --> APP
    APP --> DB["SQLite / PostgreSQL"]
    APP --> FS["工件与证据存储"]
    APP --> Q["持久化任务队列"]
    Q --> W["Worker"]
    W --> R["隔离 Runner"]
    R --> B["浏览器 / HTTP 执行器"]
    R --> O["多观察者"]
    B --> T["授权目标应用"]
    O --> T
    R --> E["证据归一化与判定"]
    E --> DB
    E --> FS
~~~

### 5.1 进程职责

- API 进程：资源管理、权限检查、任务提交、进度查询和事件推送。
- Worker 进程：租约获取、任务编排、重试、取消和状态持久化。
- Runner 进程：在明确安全策略内执行目标请求、浏览器操作和观察器。
- 前端进程或静态站点：只通过 API 访问后端能力。
- CLI 进程：调用应用服务或 API；无交互模式必须稳定可脚本化。

API 进程不得直接向目标应用发起测试请求。所有主动验证流量必须经过 Worker、Runner 和安全内核。

### 5.2 技术栈基线

| 层次 | V1 基线 |
| --- | --- |
| 后端语言 | Python 3.12 或项目锁定的兼容版本 |
| API | FastAPI |
| 数据模型 | Pydantic v2 |
| ORM 与迁移 | SQLAlchemy 2、Alembic |
| 初始数据库 | SQLite WAL |
| 可扩展数据库 | PostgreSQL |
| HTTP 执行 | httpx |
| 浏览器执行 | Playwright |
| CLI | Typer |
| 前端 | React、TypeScript、Vite、Ant Design |
| Python 依赖 | uv |
| 前端依赖 | pnpm |
| 报告 | JSON、HTML、SARIF、JUnit |
| 测试 | pytest、Vitest、Playwright |

更换基线组件需要说明动机、迁移成本和对比赛演示环境的影响。

## 6. 仓库和文件规范

### 6.1 目标目录

~~~text
界鉴/
├─ AGENTS.md
├─ README.md
├─ LICENSE
├─ pyproject.toml
├─ uv.lock
├─ pnpm-workspace.yaml
├─ package.json
├─ .gitignore
├─ .editorconfig
├─ config/
│  ├─ default.toml
│  ├─ development.toml
│  └─ logging.toml
├─ docs/
│  ├─ PROJECT_SPEC.md
│  ├─ INITIAL_DEVELOPMENT_PLAN.md
│  ├─ decisions/
│  │  └─ ADR-0001-entrypoints.md
│  ├─ threat-model/
│  ├─ protocols/
│  └─ user-guide/
├─ schemas/
│  ├─ project.schema.json
│  ├─ contract.schema.json
│  ├─ evidence.schema.json
│  ├─ plugin.schema.json
│  └─ report.schema.json
├─ backend/
│  ├─ alembic.ini
│  ├─ migrations/
│  └─ src/
│     └─ jiejian/
│        ├─ __init__.py
│        ├─ main.py
│        ├─ cli.py
│        ├─ worker_main.py
│        ├─ runner_main.py
│        ├─ config.py
│        ├─ logging.py
│        ├─ api/
│        │  ├─ app.py
│        │  ├─ dependencies.py
│        │  ├─ errors.py
│        │  └─ routes/
│        ├─ domain/
│        │  ├─ models/
│        │  ├─ values/
│        │  ├─ events.py
│        │  ├─ policies.py
│        │  └─ state_machines.py
│        ├─ engine/
│        │  ├─ planner.py
│        │  ├─ orchestrator.py
│        │  ├─ mutators/
│        │  ├─ executors/
│        │  ├─ observers/
│        │  ├─ oracle/
│        │  └─ evidence/
│        ├─ services/
│        │  ├─ projects.py
│        │  ├─ recordings.py
│        │  ├─ contracts.py
│        │  ├─ runs.py
│        │  ├─ regressions.py
│        │  └─ reports.py
│        ├─ adapters/
│        │  ├─ browser/
│        │  ├─ http/
│        │  ├─ observations/
│        │  ├─ artifacts/
│        │  ├─ llm/
│        │  ├─ crypto/
│        │  └─ notifications/
│        ├─ storage/
│        │  ├─ db.py
│        │  ├─ orm/
│        │  ├─ repositories/
│        │  ├─ unit_of_work.py
│        │  └─ artifacts.py
│        ├─ worker/
│        │  ├─ queue.py
│        │  ├─ lease.py
│        │  ├─ dispatcher.py
│        │  └─ handlers/
│        ├─ reporting/
│        │  ├─ builders.py
│        │  ├─ html/
│        │  ├─ sarif.py
│        │  └─ junit.py
│        └─ plugins/
│           ├─ contracts.py
│           ├─ registry.py
│           └─ sandbox.py
├─ frontend/
│  ├─ package.json
│  ├─ vite.config.ts
│  └─ src/
│     ├─ main.tsx
│     ├─ app/
│     ├─ pages/
│     ├─ features/
│     ├─ components/
│     ├─ api/
│     ├─ stores/
│     └─ styles/
├─ benchmarks/
│  ├─ manifests/
│  ├─ generated-apps/
│  ├─ patched-pairs/
│  └─ expected/
├─ samples/
│  ├─ projects/
│  ├─ contracts/
│  └─ plugins/
├─ tests/
│  ├─ unit/
│  ├─ integration/
│  ├─ e2e/
│  ├─ security/
│  ├─ fixtures/
│  └─ golden/
├─ scripts/
├─ deploy/
│  ├─ docker/
│  └─ compose.yaml
└─ var/
   ├─ jiejian.db
   ├─ projects/
   ├─ cache/
   ├─ jobs/
   ├─ logs/
   └─ tmp/
~~~

### 6.2 源码与运行态边界

- var/ 只保存本地运行态，不提交版本库。
- 任何测试不得把临时文件写入源码目录。
- 测试使用独立临时根目录和独立数据库。
- 密钥不得写入项目配置、日志、证据、快照或报告。
- samples/ 中只允许使用无效示例密钥。
- benchmarks/generated-apps/ 若体积过大，使用清单和可复现生成脚本管理，不直接无约束提交。

### 6.3 模块粒度

优先按稳定领域职责拆分，不按每一个动作创建新文件。一个模块若能保持单一责任和可测试性，应保持内聚。仅在出现明确边界、独立演进、循环依赖或测试隔离需求时再拆分。

- 私有辅助函数默认应至少有三个生产代码调用点，测试调用不计入生产复用证据。
- 框架入口、领域不变量、安全边界、独立失败或清理职责，以及能够阻止主流程膨胀的独立检查，可以低于三个生产调用点，但必须能够说明其边界价值。
- 零调用且没有框架发现机制、当前需求或测试约束的符号应删除或延后实现，不得仅以未来可能使用为由保留。
- 三百至五百非注释代码行是模块职责审查提醒，不是文件最低行数。不得为凑行数合并不相关职责；超过约五百非注释代码行时，应审查是否混合了多个演进方向。
- 小文件只有在缺乏独立业务、框架或安全边界时才应合并。`__init__`、程序入口、配置、Schema 和测试文件不要求承担三百行以上业务逻辑。

## 7. 分层规范

### 7.1 Domain

包含实体、值对象、领域事件、状态机和纯策略。不得依赖 FastAPI、SQLAlchemy、Playwright、文件系统或第三方模型 SDK。

### 7.2 Engine

实现计划、变异、执行协议、观察协议、判定和证据归一化。只依赖领域协议和抽象端口，不绑定具体数据库或 UI。

### 7.3 Services

实现用例编排、事务边界、权限和状态转换。CLI、API 和任务处理器共享此层。

### 7.4 Adapters

实现浏览器、HTTP、数据库观察、日志、产物扫描、模型、加密和通知等外部接口。适配器故障必须映射为稳定内部错误。

### 7.5 Storage

实现仓储、工作单元、ORM 和工件存储。领域对象不得暴露 ORM 会话。

### 7.6 API 与 CLI

只负责输入解析、身份验证、调用服务和输出序列化。不得复制判定规则或直接操作 ORM。

### 7.7 Frontend

按用户能力域组织 features，页面负责组合，不在组件内重新实现后端状态机和门禁规则。

## 8. 核心领域模型

| 实体或值对象 | 关键字段 | 说明 |
| --- | --- | --- |
| Project | id、name、target、source、safety_policy、status | 一个受测应用及授权边界 |
| TargetScope | origins、hosts、ports、redirect_policy、dns_policy | 可访问目标集合 |
| Identity | id、role、secret_ref、session_strategy | 测试身份，不保存明文凭据 |
| Flow | id、steps、dependencies、redactions、source | 可重放交互流程 |
| Requirement | id、source_ref、text、security_tags | 原始安全意图 |
| Contract | id、version、rules、status、provenance | 可执行安全契约版本 |
| ContractRule | subject、action、resource、relation、expected、observers | 一条可判定安全关系 |
| MutationPlan | cases、seed、budgets、engine_version | 可复现变异计划 |
| TestCase | baseline、mutation、preconditions、cleanup | 单个测试用例 |
| Observation | observer、before、after、confidence、causal_tag | 某观察面的事实 |
| Evidence | case_id、inputs、observations、reasoning、hashes | 不可变确认材料 |
| Finding | rule_id、severity、verdict、evidence_refs、status | 可跟踪问题 |
| Run | contract_version、engine_version、lifecycle、verdict | 一次完整验证 |
| RegressionBaseline | accepted_run、case_fingerprints、expectations | 回归基线 |
| GatePolicy | thresholds、required_observers、inconclusive_policy | 交付门禁规则 |
| Job | type、payload_ref、state、lease、attempts | 可恢复后台任务 |

所有公开 ID 使用不可猜测标识；日志可另带短显示 ID。所有版本化对象一旦被运行引用，不得原地改写。

## 9. 状态机规范

生命周期状态和安全结论必须分开存储，避免把“执行成功”误解为“安全通过”。

### 9.1 项目

~~~text
DRAFT → READY → ARCHIVED
~~~

- DRAFT：配置尚未通过校验。
- READY：授权边界、身份引用和最低运行配置有效。
- ARCHIVED：只读保留，不再接受新任务。

### 9.2 录制

~~~text
CREATED → STARTING → RECORDING → PROCESSING → REVIEWABLE → COMPLETED
              ↘ FAILED      ↘ FAILED          ↘ CANCELLED
~~~

录制结束后必须先脱敏、标准化和依赖解析，才能进入人工审阅。

### 9.3 契约

~~~text
DRAFT → REVIEW → ACTIVE → SUPERSEDED
          ↘ REJECTED
~~~

只有 ACTIVE 契约可用于正式门禁。激活后内容不可变；修改产生新版本。

### 9.4 运行生命周期

~~~text
QUEUED → PREFLIGHT → PLANNING → EXECUTING → VERIFYING → REPORTING → COMPLETED
           ↘ FAILED     ↘ FAILED      ↘ FAILED      ↘ FAILED
                         ↘ CANCELLED
                         ↘ SAFETY_STOPPED
~~~

### 9.5 运行结论

- PASS：所有强制规则满足且必要观察者完整。
- BLOCK：至少一项门禁规则被确认证据违反。
- INCONCLUSIVE：证据不足、关键观察者不可用或清理失败，不能声称通过。

### 9.6 用例生命周期

~~~text
PLANNED → SNAPSHOTTED → EXECUTED → OBSERVED → CLEANED → DONE
             ↘ ERROR       ↘ ERROR       ↘ ERROR
~~~

### 9.7 用例结论

- SAFE
- VULNERABLE
- INCONCLUSIVE
- SKIPPED
- ERROR

ERROR 表示执行问题，INCONCLUSIVE 表示执行完成但证据不足，两者不得合并。

### 9.8 任务

~~~text
PENDING → RUNNING → SUCCEEDED
              ↘ RETRY_WAIT → RUNNING
              ↘ FAILED
              ↘ CANCELLED
~~~

状态转换必须通过单一状态机函数完成，验证来源状态、目标状态、操作者和必要数据，并写入事件记录。不得在路由或 UI 中任意赋值。

## 10. 输入规范

### 10.1 项目配置

项目配置至少包含：

~~~yaml
schema_version: "1"
project:
  name: demo-shop
target:
  base_url: http://127.0.0.1:8080
  allowed_origins:
    - http://127.0.0.1:8080
  allowed_hosts:
    - 127.0.0.1
  allowed_ports:
    - 8080
  allow_private_network: true
  follow_redirects: false
source:
  kind: local
  path: ../demo-shop
requirements:
  files:
    - requirements/security.md
identities:
  - id: owner
    role: user
    secret_ref: env:JIEJIAN_DEMO_OWNER
  - id: attacker
    role: user
    secret_ref: env:JIEJIAN_DEMO_ATTACKER
reset:
  kind: http
  endpoint: /__test/reset
safety:
  max_requests: 200
  max_duration_seconds: 600
  max_parallel_cases: 2
  destructive_actions: deny
~~~

规则：

- schema_version 必须显式提供。
- target 先经过标准化再做授权校验。
- secret_ref 只引用外部秘密，配置文件不得保存明文。
- source.path 解析后必须处于允许的项目目录。
- reset 必须说明恢复策略；正式运行缺少恢复策略时，只允许只读测试集。
- 未显式允许的目标、端口、重定向和协议一律拒绝。

### 10.2 契约来源

来源优先级不是可信度优先级。每条规则必须保留来源：

1. 用户确认的显式安全需求。
2. 项目配置与角色资源清单。
3. 录制得到的正常交互。
4. 源码和路由分析候选。
5. LLM 提议候选。

第 4、5 类只能生成 DRAFT 候选；未经规则校验或用户确认不能成为 ACTIVE 门禁规则。

### 10.3 契约规则最小结构

~~~yaml
id: order-read-ownership
subject:
  identity_role: user
action:
  method: GET
  route: /api/orders/{order_id}
resource:
  type: order
  id_from: path.order_id
relation:
  baseline: owner
  mutation: non_owner
expected:
  http:
    allowed_status: [401, 403, 404]
  side_effect:
    must_not_read_foreign_resource: true
observers:
  required: [http, owner_api]
severity: high
~~~

### 10.4 流程输入

Flow 由有序步骤和显式依赖组成。动态值必须由提取器提供，禁止通过全局文本替换猜测。

每一步至少包含：

- 动作类型。
- 目标模板。
- 输入模板。
- 身份。
- 前置依赖。
- 可提取变量。
- 脱敏字段。
- 超时。
- 是否允许重试。
- 清理动作引用。

## 11. 输出和证据规范

### 11.1 单次运行目录

~~~text
var/projects/<project_id>/runs/<run_id>/
├─ manifest.json
├─ mutation-plan.json
├─ events.ndjson
├─ cases/
│  └─ <case_id>/
│     ├─ input.json
│     ├─ request.json
│     ├─ response.json
│     ├─ observations.json
│     ├─ verdict.json
│     └─ artifacts/
├─ evidence/
│  └─ <evidence_id>.json
├─ regression.json
└─ report/
   ├─ report.json
   ├─ index.html
   ├─ results.sarif
   └─ junit.xml
~~~

### 11.2 manifest 必含字段

- schema_version
- run_id、project_id
- contract_id、contract_version、contract_hash
- engine_version、configuration_hash
- mutation_seed
- target_snapshot
- started_at、finished_at
- lifecycle、verdict
- artifact_hashes

### 11.3 证据对象

~~~json
{
  "schema_version": "1",
  "evidence_id": "ev_...",
  "run_id": "run_...",
  "case_id": "case_...",
  "rule_id": "order-read-ownership",
  "baseline": {"identity": "owner", "resource": "order-a"},
  "mutation": {"identity": "attacker", "resource": "order-a"},
  "observations": [],
  "reasoning": {
    "oracle": "ownership_relation",
    "decision": "VULNERABLE",
    "reason_codes": ["FOREIGN_RESOURCE_OBSERVED"]
  },
  "causal_tag": "jj-...",
  "content_hash": "sha256:..."
}
~~~

### 11.4 证据要求

- 输入、变异、观察、结论和版本必须闭环。
- 每份证据使用内容哈希，报告只引用不可变证据。
- 明文令牌、Cookie、口令和个人敏感信息在落盘前脱敏。
- 截图和响应体采用最小必要原则。
- 缺少必要观察面时输出 INCONCLUSIVE，不得以 HTTP 403 自动判定安全。
- 人工覆盖结论必须记录操作者、时间、理由和被覆盖证据，不得删除原结论。

## 12. 持久化设计

### 12.1 数据库与文件系统分工

数据库保存可查询元数据、状态、索引和引用；文件系统保存大对象、原始工件和报告。任何跨两者的写入通过工作单元和最终一致性状态管理。

核心表建议：

- projects
- target_scopes
- identities
- recordings
- flows
- requirements
- contracts
- contract_rules
- runs
- test_cases
- observations
- evidence_index
- findings
- regression_baselines
- gate_policies
- jobs
- job_events
- audit_events
- schema_migrations

### 12.2 并发与事务

- SQLite 启用 WAL、外键和 busy timeout。
- 单次状态转换、事件写入和任务租约更新必须在同一事务。
- Worker 使用带过期时间的租约，不用仅存内存的队列。
- 重试任务使用幂等键，防止重复创建运行和证据。
- 数据库不保存大型响应体、视频和浏览器追踪。
- 当写并发成为实测瓶颈时再迁移 PostgreSQL，不提前分布式化。

### 12.3 不可变性

ACTIVE 契约、完成运行的 manifest、证据和已接受回归基线均不可原地修改。修订通过新版本和引用关系表达。

## 13. 缓存设计

### 13.1 层次

- L0：进程内有界 LRU，只缓存纯函数结果和短期解析结果。
- L1：var/cache 下的内容寻址缓存，供进程间复用。
- 不设置隐式远程缓存。

### 13.2 缓存键

缓存键必须包含影响结果的所有版本因素：

~~~text
namespace /
engine_version /
schema_version /
project_hash /
contract_hash /
flow_hash /
adapter_version /
content_hash
~~~

### 13.3 可缓存内容

- 需求文档解析结果。
- 路由和源码静态索引。
- 契约编译中间表示。
- 脱敏后的浏览器静态资源元数据。
- 变异计划。
- 报告静态模板。

### 13.4 禁止缓存内容

- 明文凭据、会话 Cookie、访问令牌。
- 活跃数据库连接和浏览器上下文。
- 未完成状态机对象。
- 依赖当前目标副作用但缺少目标快照的判定结果。
- 含未脱敏个人信息的响应。

### 13.5 缓存状态

~~~text
MISSING → BUILDING → READY
            ↘ FAILED
READY → STALE → BUILDING
READY → EVICTED
~~~

缓存写入采用临时文件、校验哈希和原子重命名。崩溃后残留 BUILDING 项必须可识别并回收。

## 14. 调用逻辑

### 14.1 项目接入

1. CLI 或 GUI 提交配置。
2. API 或 CLI 解析并进行 schema 校验。
3. 安全内核规范化目标并验证授权边界。
4. 检查 secret_ref 是否可解析，但不得读取后写入日志。
5. 检查 reset 和只读策略。
6. 应用服务在事务中创建 Project。
7. 校验全部通过后从 DRAFT 转为 READY。

### 14.2 录制

1. 用户创建录制任务。
2. 服务写入 Recording 和 Job。
3. Worker 获取租约并启动隔离 Runner。
4. Runner 创建独立浏览器上下文和短期会话材料。
5. 用户完成正常业务流程。
6. 录制器捕获动作、请求、响应和变量来源。
7. 脱敏器在落盘前删除秘密。
8. 处理器把原始记录转换为 Flow，解析动态依赖。
9. 用户审阅并确认流程后完成录制。

### 14.3 契约构建

1. 收集需求、角色资源、Flow 和静态候选。
2. 编译为统一中间表示。
3. 生成候选安全关系和观察需求。
4. 对冲突、歧义和不可观察规则给出明确提示。
5. 用户确认、修订或拒绝。
6. 通过 schema、可执行性和观察完整性检查后激活新版本。
7. 旧版本标记为 SUPERSEDED，但保留历史运行引用。

### 14.4 验证运行

1. RunService 创建 QUEUED 运行和持久化 Job。
2. Worker 获取任务租约。
3. PREFLIGHT 校验目标范围、身份、重置能力、观察器、预算和契约版本。
4. Planner 根据契约、Flow、seed 和预算产生确定性 MutationPlan。
5. 每个用例执行前建立必要快照并生成 causal_tag。
6. Executor 通过安全内核发出请求或浏览器动作。
7. Observer 在执行前后采集多个观察面。
8. Cleanup 执行回滚或恢复，并验证恢复结果。
9. Oracle 仅根据结构化规则和观察给出用例结论。
10. Evidence Builder 归一化、脱敏、计算哈希并写入不可变证据。
11. Gate 聚合结论为 PASS、BLOCK 或 INCONCLUSIVE。
12. Reporter 生成报告，运行进入 COMPLETED。

### 14.5 回归

1. 选择已接受且证据完整的运行建立基线。
2. 保存用例指纹、期望关系和必要观察器。
3. 新构建复用契约版本或执行显式迁移。
4. 对比新增、消失、结论变化和证据变化。
5. 已修复用例重新变为 VULNERABLE 或关键用例变为 INCONCLUSIVE 时阻断。
6. 任何基线更新必须人工确认并记录审计事件。

## 15. 变异器、执行器与观察器协议

### 15.1 变异器

每个变异器必须声明：

- 名称和版本。
- 适用的契约关系。
- 所需输入和前置条件。
- 可能影响的字段。
- 安全风险等级。
- 是否需要重置。
- 产生用例的确定性规则。

V1 首批变异器：

- IdentitySwap：保持资源与动作不变，替换身份。
- ResourceSwap：保持身份与动作不变，替换为其他身份资源。
- FieldOmission：删除安全敏感字段。
- FieldPrivilegeEscalation：修改角色、所有者或状态字段。
- Replay：在受控预算内重放一次敏感动作。
- SequenceSkip：跳过应当建立授权前置条件的步骤。

### 15.2 执行器

HTTP 和 Browser 执行器都必须经过：

输入规范化 → 目标范围检查 → 预算占用 → 因果标记注入 → 执行 → 响应限流与脱敏

执行器不能自行判定漏洞。

### 15.3 观察器

统一协议包含：

- supports：是否支持当前项目。
- prepare：准备观察环境。
- snapshot_before：执行前快照。
- snapshot_after：执行后快照。
- correlate：依据 causal_tag 或资源关系关联副作用。
- cleanup：释放资源。
- health：报告观察能力是否完整。

V1 观察器优先级：

1. HTTP 状态、响应头和脱敏响应语义。
2. 所有者业务 API 观察。
3. 数据库只读代理观察。
4. 结构化日志观察。
5. 浏览器 UI 观察。
6. 邮件、对象存储或任务队列等插件观察。

### 15.4 判定器

Oracle 采用显式规则，不使用自由文本模型直接判定。一个高置信漏洞结论至少要求：

- 存在可追踪契约规则。
- 基线行为满足前置条件。
- 变异只改变声明的关系变量。
- 至少一个规定观察面确认不应发生的结果或副作用。
- 证据与当前请求可通过 causal_tag、资源 ID 或时间窗关联。

若响应拒绝但后端发生了不允许的副作用，判定仍为 VULNERABLE。若响应允许但所有观察面均无法确认资源结果，按规则输出 INCONCLUSIVE 或 VULNERABLE，不得默认 SAFE。

## 16. 安全内核

所有主动能力共用一个不可绕过的安全内核。

### 16.1 目标范围

- 规范化 scheme、host、port 和 path。
- 每次请求和每次重定向都重新校验。
- DNS 解析结果必须落在允许地址集合；解析变化时重新判断。
- 默认拒绝云元数据地址、环回以外的私网和链路本地地址；仅在项目配置显式授权时开放。
- 浏览器子资源和 WebSocket 同样受范围约束。

### 16.2 预算

- 最大请求数。
- 最大运行时长。
- 最大并发用例数。
- 单主机速率。
- 单响应体大小。
- 浏览器页数和上下文数。
- 重试次数。

超出预算进入 SAFETY_STOPPED，不得伪装为普通失败。

### 16.3 秘密

- 秘密通过环境变量、系统密钥环或受控秘密适配器解析。
- Runner 只获得当前用例最小必要秘密。
- 日志、事件、错误和报告统一经过脱敏器。
- 浏览器存储状态按身份与运行隔离，运行结束销毁。
- 用户提供 API Key 时在保存前明确提示权限和用途。

### 16.4 破坏性控制

- 默认禁止删除、批量写入、资金动作和不可逆操作。
- 写操作必须有显式 reset 或补偿动作。
- 清理失败将当前用例与运行标记为 INCONCLUSIVE，必要时停止后续用例。
- 运行前后校验测试数据空间，禁止作用到真实生产数据。

## 17. 错误、重试与恢复

### 17.1 稳定错误码

建议命名空间：

- CFG：配置和 schema。
- SCOPE：目标授权边界。
- SECRET：秘密解析和脱敏。
- CONTRACT：契约编译和冲突。
- RECORD：录制和流程处理。
- EXEC：执行器。
- OBS：观察器。
- CLEANUP：恢复和清理。
- STORAGE：数据库和工件。
- JOB：队列、租约和取消。
- REPORT：报告生成。
- INTERNAL：未分类内部错误。

API、CLI、事件和报告共享错误码，显示文本可以本地化。

### 17.2 重试规则

- 只对明确可重试的瞬态故障重试。
- 非幂等动作默认不重试。
- 重试必须复用幂等键和因果标记族。
- 指数退避必须有上限和随机抖动。
- 观察器缺失不能通过重试降级为 SAFE。

### 17.3 崩溃恢复

- Worker 心跳过期后租约可被其他 Worker 接管。
- RUNNING 且租约失效的任务进入恢复审计。
- Runner 崩溃后先执行外部清理，再决定重试或失败。
- 未原子完成的工件保留为临时态，不进入证据索引。
- 进程启动时扫描孤儿临时目录和过期租约。

## 18. API 规范

API 前缀为 /api/v1。首批资源：

~~~text
GET    /health
GET    /ready
POST   /projects
GET    /projects
GET    /projects/{project_id}
POST   /projects/{project_id}/validate
POST   /projects/{project_id}/recordings
POST   /projects/{project_id}/contracts/build
GET    /contracts/{contract_id}
POST   /contracts/{contract_id}/activate
POST   /projects/{project_id}/runs
GET    /runs/{run_id}
POST   /runs/{run_id}/cancel
GET    /runs/{run_id}/events
GET    /runs/{run_id}/findings
GET    /evidence/{evidence_id}
POST   /runs/{run_id}/baseline
GET    /runs/{run_id}/report
~~~

规范：

- 创建类接口支持幂等键。
- 长任务返回资源 ID，不保持同步长连接等待完成。
- 进度优先使用 Server-Sent Events，必要时轮询兜底。
- API 返回稳定错误码、trace_id 和安全的用户消息。
- 取消是请求状态，不保证已发出的外部动作能够撤销；必须继续清理。
- OpenAPI 是对外接口真源之一，但不能代替领域状态机规范。

## 19. CLI 规范

- 命令输出默认适合人阅读；提供 --json 供脚本使用。
- stdout 输出正常结果，stderr 输出诊断。
- 无交互命令不得突然请求输入。
- 所有写操作支持 --yes 或显式交互确认。
- 支持 --config、--var-dir、--log-level 和 --trace-id。
- CI 命令固定退出码：

| 退出码 | 含义 |
| --- | --- |
| 0 | 门禁 PASS |
| 1 | 门禁 BLOCK |
| 2 | INCONCLUSIVE |
| 3 | 配置或输入错误 |
| 4 | 执行或基础设施错误 |
| 5 | 安全内核停止 |
| 130 | 用户取消 |

退出码一旦发布，不得无迁移说明地改变。

## 20. GUI 规范

V1 页面按用户流程组织：

1. 项目总览。
2. 接入。
3. 录制。
4. 建约。
5. 测试。
6. 验证。
7. 报告。

可见阶段名称固定使用“接入、录制、建约、测试、验证、报告”，不要把内部类名或长术语暴露为主导航。

GUI 必须清楚区分：

- 生命周期与安全结论。
- 已确认规则与模型候选。
- 执行失败与证据不足。
- HTTP 表象与后端副作用。
- 当前运行与回归基线。
- 自动结论与人工覆盖。

关键运行页至少展示：当前阶段、预算、目标范围、用例进度、观察器健康、发现数量和安全停止原因。

## 21. LLM 使用边界

LLM 可以：

- 从需求或代码中提出候选规则。
- 对冲突和缺失观察能力作解释。
- 辅助生成修复建议和报告摘要。

LLM 不得：

- 直接激活契约。
- 绕过安全内核生成或执行目标请求。
- 仅凭文本声称漏洞成立或修复成功。
- 接收未脱敏秘密。
- 在没有记录模型、提示模板和输入哈希时影响可复现门禁。

模型不可用时，核心录制、显式契约、变异、观察、判定和回归能力仍应工作。

## 22. 插件规范

V1 内部先使用稳定协议，不急于公开插件市场。

允许扩展：

- ContractSource
- Mutator
- Observer
- ArtifactScanner
- ReportExporter

插件必须声明 manifest、版本、兼容范围、所需权限、网络范围、秘密引用和资源预算。默认进程外运行；任何插件不能直接访问主数据库、主进程秘密或未授权网络。插件结果必须通过 schema 校验，插件崩溃不能破坏主任务状态。

## 23. 测试规范

### 23.1 测试层次

- unit：领域规则、状态机、变异器、判定器、脱敏器和缓存键。
- integration：仓储、工作单元、队列租约、适配器和报告。
- e2e：从项目接入到门禁报告的完整流程。
- security：SSRF、重定向绕过、DNS 变化、秘密泄漏、路径穿越、插件隔离和预算。
- golden：契约、证据、SARIF、JUnit 和 HTML 数据模型快照。
- benchmark：带真值的漏洞与修复配对。

### 23.2 必测不变量

- 非法状态转换必然失败。
- API 进程不直接执行目标请求。
- 未授权目标永不发出网络请求。
- 秘密不会出现在日志、事件、数据库和报告。
- ACTIVE 契约不可原地修改。
- 相同输入、版本和 seed 产生相同 MutationPlan。
- 缺少必要观察者不能得到 PASS。
- 清理失败不能被隐藏。
- 完成证据的哈希可重复验证。
- CLI、GUI、CI 对同一运行得到同一门禁结论。

### 23.3 Python 验证

所有 Python 检查设置 PYTHONDONTWRITEBYTECODE=1 并使用 python -B。语法检查优先使用 ast.parse，不使用 py_compile 或 compileall，避免在源码目录产生 __pycache__ 和 .pyc。

## 24. 日志、事件与可观测性

- 日志使用结构化 JSON，至少含 timestamp、level、component、trace_id、run_id、case_id 和 event_code。
- 用户可见进度来自领域事件，不解析日志猜测。
- 每个长任务记录开始、状态转换、预算变化、安全决策、重试、取消和结束。
- 默认不记录完整请求体和响应体。
- trace_id 贯穿 CLI、API、Worker、Runner、观察器和报告。
- 运行事件采用追加写入，不修改历史事件。

## 25. 配置和版本

- 配置优先级：内置默认值 < 配置文件 < 环境变量 < CLI 参数。
- 每个配置来源可追踪，但秘密值不回显。
- schema_version、engine_version、contract_version 和 plugin_version 必须独立。
- 数据库迁移只向前执行，降级需显式方案。
- 报告读取器至少兼容当前版本和前一稳定版本。

## 26. 规范修订流程

发现规范漏洞包括但不限于：

- 实现无法在不破坏安全或一致性的情况下满足规范。
- 状态机缺少必要中间态或恢复路径。
- 输入输出无法表达真实业务场景。
- 安全边界存在绕过。
- 目录或模块职责导致重复、循环依赖或不可测试。
- 公开接口已不足以支持确定需求。

修订时必须：

1. 提供复现、实验数据、失败测试或真实开发证据。
2. 标出受影响条款、模块、数据和兼容性。
3. 涉及架构级事项时新增或修订 ADR。
4. 在同一次变更中修改本规范。
5. 提供迁移和回滚说明。
6. 新增能够防止复发的测试。
7. 在下方变更记录中登记。

不能仅因“实现更方便”降低安全边界或证据要求。

## 27. 当前阶段禁止事项

- 在核心链未贯通前建设微服务。
- 在显式规则判定未稳定前让 LLM 参与最终门禁。
- 在只支持一个内置观察器时先建设复杂插件市场。
- 在没有恢复策略时执行写入型攻击用例。
- 以漂亮仪表盘代替真实证据闭环。
- 把 2xx、401、403、404 单独作为安全结论。
- 把运行完成状态当作 PASS。
- 把运行态数据混入源码目录或 Git。

## 28. V1 变更记录

| 日期 | 版本 | 变更 |
| --- | --- | --- |
| 2026-08-08 | V1.1 | 明确私有辅助函数复用、零调用符号清理与模块行数审查规则 |
| 2026-08-08 | V1 | 建立产品定位、目录、分层、状态机、输入输出、缓存、调用链、安全边界、入口和修订机制 |
