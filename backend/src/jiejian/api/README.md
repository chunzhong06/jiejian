# API

## 定位

`api` 是回环 FastAPI 控制面。它把 HTTP 请求转换为共享应用能力调用，并提供 React GUI 所需的 JSON、SSE、错误和静态资源入口。

## 负责 / 不负责

- 负责 `create_app` 装配、请求追踪、异常映射、生命周期、router、wire schema 和前端静态挂载。
- 所有业务动作委托给 `ApplicationContext` 中的能力服务。
- 不直接操作 ORM Session，不复制 Contract/Job/Verdict 规则，也不发送目标流量。

## 子模块与 public API

- `jiejian.api:create_app` 是正式稳定入口。
- `app.py`：应用装配与进程资源生命周期。
- `routers/`：projects、contracts、recordings、runs、jobs、results、system 能力路由。
- `schemas/`：HTTP request/response DTO，只由 router 叶模块直接导入。
- `errors.py` / `responses.py`：稳定错误码、状态码和响应外壳。

## 调用与数据流

```text
HTTP / React GUI
→ FastAPI router + schema
→ ApplicationContext capability service
→ Execution / Contracts / Recording / Results
→ JSON / SSE response
```

## 关键不变量和失败语义

- API、CLI、GUI 必须复用同一应用能力，不能在 router 中复制状态机或安全判定。
- `JiejianError`、Pydantic 校验错误和 trace ID 通过统一响应边界输出并脱敏。
- Worker 由应用生命周期持有，shutdown 必须停止 Worker 并关闭数据库资源。
- endpoint docstring 可能进入 OpenAPI；修改时必须比较 OpenAPI 行为。
- `GET /api/v1/system/status` 使用现有 `schema_version="1"` data envelope，只读返回 API、Worker 和本机浏览器可用性，不启动浏览器或目标流量；LLM profile 响应不包含明文 secret。

## 修改与测试入口

- 控制面：[`tests/api/test_control_plane.py`](../../../../tests/api/test_control_plane.py)
- Contract REST：[`tests/api/test_contract_workbench.py`](../../../../tests/api/test_contract_workbench.py)
- 前端客户端：[`frontend/src/api`](../../../../frontend/src/api/)

## 相关规范、协议与 ADR

- [系统架构](../../../../docs/01_架构设计/系统架构.md)
- [ADR-0010](../../../../docs/03_技术决策/ADR-0010-阶段4控制面与WebGUI.md)、[ADR-0015](../../../../docs/03_技术决策/ADR-0015-阶段5.4B契约工作台与治理REST.md)、[ADR-0020](../../../../docs/03_技术决策/ADR-0020-阶段5.6-LLM配置秘密与协议边界.md)
