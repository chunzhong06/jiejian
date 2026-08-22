# ADR-0040：Web V1 运行环境、结果最终化与 Target Runtime 边界

- 状态：已接受
- 日期：2026-08-22
- 适用范围：开发与发布环境、运行目录、进程所有权、结果派生、报告、Target Runtime、当前协议与数据库

## 背景

阶段 10.5 已形成状态化 Web 权限验证、差分孪生和唯一 Verification，但运行环境、结果派生和执行组织仍保留开发期耦合：Windows 启动同时准备前端与运行产品，Conda 与 uv 重复解析依赖，`var` 中产品事实与可重建内容混放，子进程只围绕根 PID 回收，Finding 会在读取时物化，基础报告依赖 Gate，通用 Runner 直接接收 HTTP 类型，协议和文档仍保存未实现 Target 与旧 reader。

继续在这些边界上增加 CLI Target 会复制环境、执行和结果链，并使失败恢复依赖 PID、访问顺序或历史兼容分支。因此需要在不改变 PermissionContract、Evidence 和 Verification 安全语义的前提下，先形成 Web V1 的单一内部基线。

## 决策

### 1. 开发依赖只有一个解析真源

开发继续使用全局但项目专用的 Conda 环境 `jiejian_env`。`environment.yml` 只固定 CPython 基线和必要 Conda 工具；`pyproject.toml` 声明项目直接依赖；`uv.lock` 固定全部传递依赖和来源。开发同步由仓库受控 uv 对解析出的 Conda Prefix 执行 frozen 精确同步，并以 editable 方式安装当前源码。普通启动不求解 Conda、不修改锁文件；只有显式 update 命令可以更新锁文件。

### 2. 正式运行不依赖开发工具链

正式发布携带 Wheel 与预构建前端 `dist`，使用 uv 管理的私有 Python 环境和非 editable 安装。正式 `start.cmd` 不调用 Conda、Node、pnpm、TypeScript 或 Vite，也不创建 `node_modules`。仓库开发通过独立 `scripts/dev.ps1` 完成 bootstrap、sync、update、start、test 和 shell。

### 3. Node 与 pnpm 只属于开发和发布构建

`product/frontend/node_modules` 是开发安装视图，`product/frontend/node_modules/.pnpm` 是 pnpm 虚拟依赖目录，`var/cache/pnpm-store` 才是内容寻址缓存；Vite 缓存固定进入 `var/cache/vite`。正式构建记录精确 Node、pnpm、锁文件和资源摘要，把唯一 Wheel 写入 `var/runtime/release-artifacts`；正式运行只读取随 Wheel 发布的 `dist`。

### 4. 运行目录由唯一路径对象分区

唯一 `RuntimePaths` 生成全部路径。`var/data` 保存数据库、Job、项目、报告和其他不可重建事实；`runtime` 保存当前 Python、uv、Node、pnpm、Playwright、Worker 与锁；`cache` 保存 uv、pnpm store、npm、下载和启动缓存；`logs`、`temp`、`test` 分别保存诊断、短期运行物和测试物。旧布局不迁移、不双读。

### 5. 缓存维护与数据重置分离

自动回收和 `cache status/prune/clean` 只能处理可重建内容；`runtime repair` 只修复运行时；它们都不得触碰 `var/data`、当前运行时、活锁、Evidence、报告或凭据。uv、pnpm、npm、日志和旧运行时采用明确预算、引用状态和最后成功使用事实，不单独依赖访问时间。GUI、CLI 和 API 复用 ApplicationCore 下同一缓存维护服务，破坏性操作先预览并确认。`data reset` 是独立危险能力，不进入缓存入口。

### 6. 同一解释器和内核进程树是恢复前提

主进程、Worker、Runner、Recording、Observer 和 Demo 使用启动阶段确认的同一绝对 Python。开发依赖当前 editable 安装，发布依赖当前 Wheel；任何子进程都不依赖调用者 cwd、用户 `PYTHONPATH` 或旧 Wheel。Windows 使用 Job Object 并在关闭所有者句柄时终止后代，POSIX 使用独立 session/process group。只有 Worker 内核锁可重新获取、进程树确认无存活后代且旧 fencing 已失效，才允许恢复 attempt。

### 7. publication、结果派生和 Gate 分层

Run publication 与 Verdict 先完成。随后唯一、幂等的 `ResultFinalizer` 物化 Finding/Occurrence 和基础 RunReport，并以独立派生状态记录成功、失败和重试。派生失败不回滚 publication，不修改 Evidence 或 Verdict。每个完整性已验证的 Run 都有基础报告；Gate 是可选后续派生，生成另一份不可变 Gate 报告。GET 只能读取已物化事实。

### 8. 当前协议只表达 Web，内部使用 Target Runtime Port

生产 `TargetType` 只保留 WEB，Web 专属 wire 类型明确命名。通用 Case Orchestrator 只认识 case、阶段、ExecutionFact、ObservationFact、SecurityEffectFact、基线、孪生和 Verification；HTTP Workflow、身份、Cookie、OAuth、Slot 与响应分类留在 Web Target Runtime。Registry 以 runtime factory 创建当前 Web Runtime；测试 Fake Target 必须能在不修改 Web Runtime 和 Verification 的情况下注册并执行。

### 9. 当前开发基线不保留历史兼容

旧数据库、旧 Profile、旧 Runner/Evidence/Report、旧路由 alias、旧参数位置、旧类名 re-export、旧 Demo Target 和旧 Schema reader 一次删除。当前 parser 每个根文档只接受一个明确版本；最终数据库只保留基于当前 ORM 生成的 `0001_initial`。Repository-owned Sample、fixture、Schema、客户端和 CURRENT 文档同步迁移，不提供 fallback 或 wrapper。

## 理由与取舍

这组决策把可重建环境、受控执行、不可变 publication 和可重试派生分开，使启动、恢复和结果不再依赖用户环境、PID、访问顺序或旧格式。代价是开发环境、`var`、公共 wire 与数据库发生不兼容重置，并需要一次跨脚本、运行时、存储、协议、前端和文档的迁移。

## 影响

新增开发入口、发布构建边界、RuntimePaths、缓存维护服务、进程树控制器、ResultFinalizer、派生持久状态、Target Runtime Port/Registry、独立应用与 Worker 容器。RunLifecycle、Report、Artifact 状态和 Web wire 类型收敛到当前唯一格式。现有 PermissionContract、Coverage、差分孪生、Baseline Integrity、Temporal Closure、SecurityEffectFact 与 PASS/BLOCK/INCONCLUSIVE 规则保持不变。

## 迁移与兼容

阶段 10.6 使用空 `var/data`，不读取或迁移旧运行目录和旧数据库。仓库自身调用方、Sample、fixture、Schema、前端客户端和文档一次迁移。正式发布通过 Wheel 和预构建前端验收；旧源码启动模式与旧兼容入口直接删除。

## 相关真源

- [系统总体架构](../02_架构设计/系统总体架构.md)
- [产品入口与控制面架构](../02_架构设计/产品入口与控制面架构.md)
- [执行与观察架构](../02_架构设计/执行与观察架构.md)
- [数据与持久化架构](../02_架构设计/数据与持久化架构.md)
- [安全意图与验证架构](../02_架构设计/安全意图与验证架构.md)
- [Runner执行协议](../04_协议与数据/Runner执行协议.md)
- [报告与格式投影协议](../04_协议与数据/报告与格式投影协议.md)
