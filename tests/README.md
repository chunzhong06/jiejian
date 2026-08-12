# 测试资产地图

## 能力目录与主要不变量

| 目录 | 能力与主要不变量 |
| --- | --- |
| `api/` | 控制面路由、OpenAPI、生命周期和已发布结果读取。 |
| `architecture/` | 目录边界、依赖方向、稳定入口和兼容约束。 |
| `contracts/` | Contract 模型、治理、分析、Drift 和 LLM 候选信任边界。 |
| `contracts/`、`storage/`、`api/` | 阶段 5.6 profile 配置、秘密引用、适配器、Candidate provenance、OpenAPI 和错误脱敏。 |
| `domain/` | 共享生命周期枚举与 `DomainModel` 基线。 |
| `e2e/` | CLI→Job→Worker→Runner→publication 的产品闭环和退出语义。 |
| `execution/protocol/` | Runner/Recording 协议、Schema 和严格序列化。 |
| `execution/runner/` | 独立 Runner 进程、staging 和隔离边界。 |
| `execution/worker/` | Job/Attempt、租约、取消、重试、恢复、发布和并发。 |
| `execution/recording/` | Recording 模型、浏览器边界、持久执行和回放。 |
| `runtime/` | 配置、诊断、日志、运行时错误和 Windows 首次准备脚本黑盒验证。 |
| `storage/` | migration、metadata、ORM、Repository 和事务不变量。 |
| `verification/` | 输入、授权、变异、观察、Evidence 和 Verdict 语义。 |

根 `tests/conftest.py` 的 `sample_server_factory`、`stage1_project_factory` 和
`stage23_request_factory` 被 Verification、API、E2E、Runner/Worker/Recording
共同使用，因此保留在根部。`tests/execution/worker/conftest.py` 只承载 Worker
仓储和服务夹具。`tests/execution/recording/__init__.py` 是 pytest 同名测试模块的
收集边界，必须保留；它不是生产兼容层。

## 从生产变更定位最小集合

- API 路由、OpenAPI 或控制面生命周期：`tests/api/`，涉及正式 CLI 闭环时加 `tests/e2e/`。
- Contract、Drift 或 LLM 候选：对应 `tests/contracts/`，涉及持久化时加 `tests/storage/test_contract_storage.py`。
- Job、Attempt、租约、取消、重试、恢复或 publication：`tests/execution/worker/`。
- Runner 进程或协议：`tests/execution/runner/` 与 `tests/execution/protocol/`。
- Recording 浏览器、持久化或回放：`tests/execution/recording/`；协议变化再加 `tests/execution/protocol/test_recording_v1.py`。
- ORM、migration 或事务：`tests/storage/`。
- Verification 输入、观察、Evidence 或 Verdict：`tests/verification/`。
- 目录或依赖边界：`tests/architecture/test_dependencies.py`。
- Windows 首次准备与一键启动：`tests/runtime/test_start_script.py`；只使用临时 shim，覆盖 Conda/uv 选择、锁校验、下载哈希、失败码和幂等复用。
- 阶段 5.6 启动 `/ready`、系统状态和 GUI 外壳：`tests/runtime/`、`tests/api/`、`tests/architecture/` 及前端 `src/app`、`src/features/access`、`src/features/settings` 定向测试；均不得访问真实 LLM 或收费网络。

## Marker

- `browser`：启动或依赖 Playwright/浏览器边界。
- `process`：拉起独立 Runner、Worker、Recording Runner 或 CLI 子进程。
- `database`：创建、升级或通过事务访问数据库。
- `e2e`：通过产品入口验证跨能力端到端行为。
- `slow`：相对较慢的浏览器或多进程完整闭环；不代表整个测试仓库。

Marker 可组合筛选，例如 `-m "e2e and process"` 或 `-m "database and not slow"`。

## Windows 命令

以下命令从仓库根运行，均显式使用项目解释器、`-B`、禁用 pytest 缓存和 `var/` 下唯一 basetemp；每次运行后删除对应临时目录。

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
$env:PYTHONPATH='backend/src'
& 'D:\Miniconda\envs\jiejian_env\python.exe' -B -m pytest -p no:cacheprovider --collect-only --basetemp 'var/pytest-o4-test-assets-collect' tests
& 'D:\Miniconda\envs\jiejian_env\python.exe' -B -m pytest -p no:cacheprovider --collect-only -m 'browser' --basetemp 'var/pytest-o4-test-assets-browser' tests
& 'D:\Miniconda\envs\jiejian_env\python.exe' -B -m pytest -p no:cacheprovider --collect-only -m 'process' --basetemp 'var/pytest-o4-test-assets-process' tests
& 'D:\Miniconda\envs\jiejian_env\python.exe' -B -m pytest -p no:cacheprovider --collect-only -m 'database' --basetemp 'var/pytest-o4-test-assets-database' tests
& 'D:\Miniconda\envs\jiejian_env\python.exe' -B -m pytest -p no:cacheprovider --collect-only -m 'e2e' --basetemp 'var/pytest-o4-test-assets-e2e' tests
& 'D:\Miniconda\envs\jiejian_env\python.exe' -B -m pytest -p no:cacheprovider --collect-only -m 'slow' --basetemp 'var/pytest-o4-test-assets-slow' tests
& 'D:\Miniconda\envs\jiejian_env\python.exe' -B -m pytest -p no:cacheprovider --basetemp 'var/pytest-o4-test-assets-architecture' tests/architecture/test_dependencies.py
```

阶段 5 工程优化的最终完整回归由最终一致性审计统一执行；本页中的命令用于后续按能力选择最小验证集合。
