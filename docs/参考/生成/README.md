# 生成参考入口

> 自动生成。当前源码结构与注册投影，不代表运行验收或完整调用图。

<!-- GENERATED:START -->

## 如何查询

从功能指南确定owner，用rg搜索本目录的路径或符号，只读取命中的分片。静态import只表示依赖；运行条件和完整业务调用需读源码。

## 覆盖与限制

覆盖product、scripts中的源码、脚本、样式、HTML及JSON/YAML/TOML/INI配置，另含根入口与测试catalog。Schema由注册参考覆盖。依赖锁、二进制资源、缓存、node_modules、dist、coverage不作符号索引；测试按tests/suites.toml及指南定位。

Python使用AST；JS/TS/PowerShell为有限词法提取；配置/样式只记录位置。每个受管文件恰有一个分片，空包仍列出；解析失败拒绝生成。

根输入：`pyproject.toml`、`environment.yml`、`jiejian.code-workspace`、`start.cmd`、`tests/suites.toml`

## 分片

| 分片 | 文件数 |
| --- | ---: |
| [backend/_root](代码/backend/_root.md) | 2 |
| [backend/api/_root](代码/backend/api/_root.md) | 6 |
| [backend/api/mcp](代码/backend/api/mcp.md) | 6 |
| [backend/api/routers](代码/backend/api/routers.md) | 25 |
| [backend/cli](代码/backend/cli.md) | 10 |
| [backend/composition](代码/backend/composition.md) | 3 |
| [backend/core/_root](代码/backend/core/_root.md) | 7 |
| [backend/core/applications](代码/backend/core/applications.md) | 2 |
| [backend/core/boundaries](代码/backend/core/boundaries.md) | 9 |
| [backend/core/changes](代码/backend/core/changes.md) | 2 |
| [backend/core/checks](代码/backend/core/checks.md) | 3 |
| [backend/core/contracts](代码/backend/core/contracts.md) | 3 |
| [backend/core/identities](代码/backend/core/identities.md) | 2 |
| [backend/core/preparation](代码/backend/core/preparation.md) | 4 |
| [backend/core/recording](代码/backend/core/recording.md) | 3 |
| [backend/core/reports](代码/backend/core/reports.md) | 2 |
| [backend/core/verification](代码/backend/core/verification.md) | 16 |
| [backend/infra/_root](代码/backend/infra/_root.md) | 2 |
| [backend/infra/artifacts](代码/backend/infra/artifacts.md) | 15 |
| [backend/infra/execution](代码/backend/infra/execution.md) | 7 |
| [backend/infra/identity](代码/backend/infra/identity.md) | 4 |
| [backend/infra/observers](代码/backend/infra/observers.md) | 30 |
| [backend/infra/recording](代码/backend/infra/recording.md) | 8 |
| [backend/infra/runtime/_root](代码/backend/infra/runtime/_root.md) | 12 |
| [backend/infra/runtime/capture_runner](代码/backend/infra/runtime/capture_runner.md) | 4 |
| [backend/infra/runtime/check_runner](代码/backend/infra/runtime/check_runner.md) | 4 |
| [backend/infra/runtime/jobs](代码/backend/infra/runtime/jobs.md) | 17 |
| [backend/infra/runtime/process](代码/backend/infra/runtime/process.md) | 19 |
| [backend/infra/runtime/proof_runner](代码/backend/infra/runtime/proof_runner.md) | 4 |
| [backend/infra/runtime/runner](代码/backend/infra/runtime/runner.md) | 1 |
| [backend/infra/runtime/worker](代码/backend/infra/runtime/worker.md) | 6 |
| [backend/infra/samples](代码/backend/infra/samples.md) | 3 |
| [backend/infra/secrets](代码/backend/infra/secrets.md) | 4 |
| [backend/infra/storage/_root](代码/backend/infra/storage/_root.md) | 5 |
| [backend/infra/storage/applications](代码/backend/infra/storage/applications.md) | 3 |
| [backend/infra/storage/boundaries](代码/backend/infra/storage/boundaries.md) | 5 |
| [backend/infra/storage/changes](代码/backend/infra/storage/changes.md) | 4 |
| [backend/infra/storage/execution](代码/backend/infra/storage/execution.md) | 5 |
| [backend/infra/storage/preparation](代码/backend/infra/storage/preparation.md) | 10 |
| [backend/infra/storage/results](代码/backend/infra/storage/results.md) | 7 |
| [backend/infra/storage/runtime](代码/backend/infra/storage/runtime.md) | 4 |
| [backend/infra/storage/settings](代码/backend/infra/storage/settings.md) | 2 |
| [backend/migrations](代码/backend/migrations.md) | 22 |
| [backend/workflows/_root](代码/backend/workflows/_root.md) | 1 |
| [backend/workflows/agent_access](代码/backend/workflows/agent_access.md) | 7 |
| [backend/workflows/application_understanding](代码/backend/workflows/application_understanding.md) | 9 |
| [backend/workflows/business_boundaries](代码/backend/workflows/business_boundaries.md) | 20 |
| [backend/workflows/changes](代码/backend/workflows/changes.md) | 4 |
| [backend/workflows/checks](代码/backend/workflows/checks.md) | 17 |
| [backend/workflows/contracts](代码/backend/workflows/contracts.md) | 1 |
| [backend/workflows/development](代码/backend/workflows/development.md) | 4 |
| [backend/workflows/examples](代码/backend/workflows/examples.md) | 10 |
| [backend/workflows/onboarding](代码/backend/workflows/onboarding.md) | 5 |
| [backend/workflows/preparation](代码/backend/workflows/preparation.md) | 33 |
| [backend/workflows/projects](代码/backend/workflows/projects.md) | 4 |
| [backend/workflows/recording](代码/backend/workflows/recording.md) | 10 |
| [backend/workflows/reports](代码/backend/workflows/reports.md) | 1 |
| [backend/workflows/runtime](代码/backend/workflows/runtime.md) | 6 |
| [backend/workflows/test_identities](代码/backend/workflows/test_identities.md) | 4 |
| [backend/workflows/workspace](代码/backend/workflows/workspace.md) | 6 |
| [frontend/_root](代码/frontend/_root.md) | 2 |
| [frontend/api](代码/frontend/api.md) | 28 |
| [frontend/app](代码/frontend/app.md) | 28 |
| [frontend/features/access](代码/frontend/features/access.md) | 11 |
| [frontend/features/boundaries](代码/frontend/features/boundaries.md) | 26 |
| [frontend/features/changes](代码/frontend/features/changes.md) | 19 |
| [frontend/features/checks](代码/frontend/features/checks.md) | 5 |
| [frontend/features/environment](代码/frontend/features/environment.md) | 8 |
| [frontend/features/history](代码/frontend/features/history.md) | 5 |
| [frontend/features/identities](代码/frontend/features/identities.md) | 3 |
| [frontend/features/preparation](代码/frontend/features/preparation.md) | 26 |
| [frontend/features/recording](代码/frontend/features/recording.md) | 5 |
| [frontend/features/results](代码/frontend/features/results.md) | 20 |
| [frontend/features/settings](代码/frontend/features/settings.md) | 1 |
| [frontend/features/system](代码/frontend/features/system.md) | 5 |
| [frontend/features/tools](代码/frontend/features/tools.md) | 6 |
| [frontend/features/workspace](代码/frontend/features/workspace.md) | 3 |
| [frontend/shared](代码/frontend/shared.md) | 45 |
| [protocols/_root](代码/protocols/_root.md) | 3 |
| [protocols/checks](代码/protocols/checks.md) | 7 |
| [protocols/observer](代码/protocols/observer.md) | 5 |
| [protocols/preparation](代码/protocols/preparation.md) | 5 |
| [protocols/recording](代码/protocols/recording.md) | 5 |
| [protocols/runner](代码/protocols/runner.md) | 7 |
| [protocols/runtime](代码/protocols/runtime.md) | 7 |
| [protocols/web](代码/protocols/web.md) | 8 |
| [scripts/_root](代码/scripts/_root.md) | 2 |
| [scripts/build](代码/scripts/build.md) | 3 |
| [scripts/dev](代码/scripts/dev.md) | 7 |
| [scripts/docs](代码/scripts/docs.md) | 3 |
| [scripts/editor](代码/scripts/editor.md) | 3 |
| [scripts/startup](代码/scripts/startup.md) | 5 |
| [配置与入口](代码/配置与入口.md) | 15 |

合计：785个文件、93个分片。

[注册与格式](注册与格式.md) · [数据库迁移](数据库迁移.md)。仅读源码文本，不import产品、打开数据库或读取var运行数据。

<!-- GENERATED:END -->
