# Runtime

## 定位

`runtime` 管理本地进程启动所需的配置、诊断、日志、serve 锁和 Worker 资源生命周期，不承载产品业务规则。

## 负责 / 不负责

- 负责配置优先级、环境检查、结构化脱敏日志、单实例 serve 锁和本地 Worker 线程。
- 为 CLI serve 和 FastAPI 生命周期提供可清理的资源对象。
- 不 claim 或执行具体业务 Job；Job 语义属于 Execution。

## 子模块与 public API

- `config.py`：`Settings` 和配置加载。
- `diagnostics.py`：doctor 检查、人类可读输出和不启动 Chromium 的本机浏览器可用性探针。
- `logging.py`：结构化日志配置。
- `serve_lock.py`：本地服务互斥与锁文件清理。
- `worker_manager.py`：`LocalWorkerManager`，持有 Worker 循环线程。

## 调用与数据流

```text
CLI serve / API create_app / start.ps1
→ Runtime config + doctor + serve lock
→ LocalWorkerManager
→ Execution JobHandlerRegistry
```

## 关键不变量和失败语义

- 配置文件、CLI 覆盖和环境变量按固定优先级解析；运行态目录不得落入源码树。
- 日志和 doctor 输出经过统一脱敏。
- Worker manager 只拥有线程启动、等待和停止；Handler 负责具体 Job。
- stop/close 必须幂等并释放线程、锁和数据库资源。
- system status 观察只返回运行状态，不发目标请求、不启动浏览器、不读取秘密；启动浏览器前由 `/ready` 进行短超时本机门禁。

## 修改与测试入口

- [`tests/runtime`](../../../../tests/runtime/)
- 启动脚本行为：[`tests/runtime/test_start_script.py`](../../../../tests/runtime/test_start_script.py)
- API 生命周期：[`tests/api/test_control_plane.py`](../../../../tests/api/test_control_plane.py)

## 相关规范、协议与 ADR

- [根 README](../../../../README.md)
- [ADR-0010](../../../../docs/03_技术决策/ADR-0010-阶段4控制面与WebGUI.md)、[ADR-0019](../../../../docs/03_技术决策/ADR-0019-Windows首次使用与一键启动.md)、[ADR-0020](../../../../docs/03_技术决策/ADR-0020-阶段5.6-LLM配置秘密与协议边界.md)
