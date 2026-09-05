# ADR-0040：Web V1 运行环境、结果最终化与 Target Runtime 边界

- 状态：已接受
- 日期：2026-08-22
- 适用范围：源码运行与可选打包、运行目录、进程所有权、结果派生、报告、Target Runtime、当前协议与数据库

## 背景

此前产品已形成状态化 Web 权限验证、差分孪生和唯一 Verification，但运行环境、结果派生和执行组织仍保留开发期耦合：Windows 启动同时准备前端与运行产品，Conda 与 uv 重复解析依赖，`var` 中产品事实与可重建内容混放，子进程只围绕根 PID 回收，Finding 会在读取时物化，基础报告依赖 Gate，通用 Runner 直接接收 HTTP 类型，协议和文档仍保存未实现 Target 与旧 reader。

继续在这些边界上增加 CLI Target 会复制环境、执行和结果链，并使失败恢复依赖 PID、访问顺序或历史兼容分支。因此需要在不改变 PermissionContract、Evidence 和 Verification 安全语义的前提下，先形成 Web V1 的单一内部基线。

## 决策

### 1. 开发依赖只有一个解析真源

开发继续使用全局但项目专用的 Conda 环境 `jiejian_env`。`environment.yml` 只固定 CPython 基线和必要 Conda 工具；`pyproject.toml` 声明项目直接依赖；`uv.lock` 固定全部传递依赖和来源。开发同步由仓库受控 uv 对解析出的 Conda Prefix 执行 frozen 精确同步，并以 editable 方式安装当前源码。普通启动不求解 Conda、不修改锁文件；只有显式 update 命令可以更新锁文件。

### 2. 正式入口从源码仓库一键运行

`start.cmd` 是源码仓库中的正式产品入口，准备项目专用 Conda `jiejian_env`，由受控 uv 按 `uv.lock` frozen 同步并 editable 安装当前仓库。普通启动不改写锁文件，也不安装或运行 Wheel。`scripts/dev.ps1` 提供 bootstrap、sync、update、prepare、start、cli、test、frontend-test、shell 和独立可选的 package；Wheel 只可能由 package 产生，不参与普通启动。

### 3. Node 与 pnpm 只属于前端构建

`product/frontend` 只保存 Git 管理的源码与配置。依赖摘要只由 package/lock、固定 Node/pnpm 与受控编辑器插件形成；普通页面源码变化不重装依赖。pnpm install、TypeScript/Vite build 和 Vitest 都只在 `var/development/frontend/workspace` 运行，pnpm store 与 Vite cache 分别进入 `var/development/cache/pnpm-store` 和 `var/development/cache/vite`。完整网页按 build 摘要不可变保存到 `var/development/frontend/builds/<digest>`，每个产品实例只复制匹配 build 到自己的 `<VarDir>/runtime/frontend`。editable 安装明确跳过前端打包输入；独立 package 命令先验证当前实例网页，再通过 Hatch 构建钩子映射进 Wheel，不回写源码 dist。

### 4. 运行目录由唯一路径对象分区

`RuntimePaths` 只生成当前产品 `VarDir` 的路径：`data` 保存数据库、Job、项目、报告和其他不可重建事实，`runtime` 保存当前实例的前端副本、Worker 与锁，`cache/assistant` 保存可删除的产品 AI 辅助缓存，`logs`、`temp`、`test` 分别保存诊断、短期运行物和测试物。跨实例复用的 uv、Node、pnpm、Playwright、uv-managed Python、前端依赖/build、开发缓存、prepare lock 与 release 工作区全部从仓库唯一 `var/development` 派生，不属于 `RuntimePaths`，也不进入普通产品缓存维护。

### 5. 本地运行数据维护与数据重置分离

`LocalMaintenanceService` 只处理 AI 辅助缓存、历史运行日志、临时运行文件和可证明损坏的运行时。自动日志保留按每类最近 20 份且最长 14 天执行；手工日志清理保护当前 serve 会话，临时清理保护当前 Worker、Recording、Identity、Sample 与 ServeLock 路径。`clear-all` 不触发运行时修复，也不得触碰 `var/data`、`var/development`、Evidence、报告或凭据。GUI、CLI 和 API 复用 ApplicationCore 下同一服务，写操作先预览再确认；数据重置不进入该入口。

完整缓存统计和预算 prune 只在用户查看状态或显式维护时执行，不属于普通启动。在 ApplicationCore 与 MCP/control 生命周期成立后即可对外 ready，不启动 Worker；生命周期持有的后台任务随后清理缓存根直接临时项、过期 temp/test 顶层项和有界日志保留。按需维护用一个目录快照同时得到字节数、文件数、预算和递归 partial 候选；只有外部 prune 实际改变目录后才再扫描一次。无安全、并发或身份消费者的 cache digest 不计算。启动维护失败只记录诊断，不反向改变服务可用状态。

### 6. 同一解释器和内核进程树是恢复前提

主进程、Worker、Runner、Recording、Observer 和 Artifact Scan 使用启动阶段确认的同一绝对 Python，并依赖当前仓库的 editable 安装；任何子进程都不依赖调用者 cwd、用户 `PYTHONPATH` 或旧 Wheel。Windows 使用 Job Object 并在关闭所有者句柄时终止后代，POSIX 使用独立 session/process group。只有 Worker 内核锁可重新获取、进程树确认无存活后代且旧 fencing 已失效，才允许恢复 attempt。

### 7. publication、结果派生和 Gate 分层

Run publication 与 Verdict 先完成。随后唯一、幂等的 `ResultFinalizer` 物化 Finding/Occurrence 和基础 RunReport，并以独立派生状态记录成功、失败和重试。派生失败不回滚 publication，不修改 Evidence 或 Verdict。每个完整性已验证的 Run 都有基础报告；Gate 是可选后续派生，生成另一份不可变 Gate 报告。GET 只能读取已物化事实。

### 8. 当前协议只表达 Web，内部使用 Target Runtime Port

生产 `TargetType` 只保留 WEB，Web 专属 wire 类型明确命名。通用 Case Orchestrator 只认识 case、阶段、ExecutionFact、ObservationFact、SecurityEffectFact、基线、孪生和 Verification；HTTP Workflow、身份、Cookie、OAuth、Slot 与响应分类留在 Web Target Runtime。Registry 以 runtime factory 创建当前 Web Runtime；测试 Fake Target 必须能在不修改 Web Runtime 和 Verification 的情况下注册并执行。

### 9. 当前开发基线不保留历史兼容

旧数据库、旧 Profile、旧 Runner/Evidence/Report、旧路由 alias、旧参数位置、旧类名 re-export、旧 Demo Target 和旧 Schema reader 一次删除。当前 parser 每个根文档只接受一个明确版本；数据库以显式 `0001_web_v1` 为不可改写发布基线，后续只通过签入 migration 演进。Repository-owned Sample、fixture、Schema、客户端和 CURRENT 文档同步迁移，不提供 fallback 或 wrapper。

## 理由与取舍

这组决策把可重建环境、受控执行、不可变 publication 和可重试派生分开，使启动、恢复和结果不再依赖用户环境、PID、访问顺序或旧格式。代价是开发环境、`var`、公共 wire 与数据库发生不兼容重置，并需要一次跨脚本、运行时、存储、协议、前端和文档的迁移。

## 影响

新增源码准备入口、可选打包边界、RuntimePaths、本地运行数据维护服务、进程树控制器、ResultFinalizer、派生持久状态、Target Runtime Port/Registry、独立应用与 Worker 容器。RunLifecycle、Report、Artifact 状态和 Web wire 类型收敛到当前唯一格式。现有 PermissionContract、Coverage、差分孪生、Baseline Integrity、Temporal Closure、SecurityEffectFact 与 PASS/BLOCK/INCONCLUSIVE 规则保持不变。

## 迁移与兼容

当前单代基线不读取或迁移旧运行目录和旧开发数据库。仓库自身调用方、Sample、fixture、Schema、前端客户端和文档已一次迁移；数据库从唯一显式 `0001_web_v1` 基线沿签入 migration 演进。Windows 验收从全新本地运行态双击仓库根 `start.cmd`，证明 editable 当前源码、受控依赖和 `var/runtime/frontend` 可以完整再生；旧兼容入口直接删除。

## 相关真源

- [系统总体架构](../01_系统地图/系统全景.md)
- [产品入口与控制面架构](../01_系统地图/产品入口与控制面.md)
- [执行与观察架构](../01_系统地图/执行与观察.md)
- [数据与持久化架构](../01_系统地图/数据与持久化.md)
- [安全意图与验证架构](../01_系统地图/权限验证与结果.md)
- [Runner执行协议](../03_参考手册/协议/Runner执行协议.md)
- [报告与格式投影协议](../03_参考手册/协议/报告与格式投影协议.md)
