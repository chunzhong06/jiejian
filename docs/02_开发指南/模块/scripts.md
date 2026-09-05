# 开发脚本模块

> 状态：CURRENT。`scripts/dev.ps1` 是受控 Python、前端、Schema、测试、自动 L5、启动准备、文档检查和 Windows x64 Portable 的唯一开发总控入口。

## 职责

开发脚本负责选择并校验受控工具链，按公开命令组合必要的准备能力，把运行依赖和生成物限制在 `var/`，并在退出前恢复调用者环境。产品启动由 `start.cmd → scripts/start.ps1` 统一编排，`dev.ps1 start` 只做薄转交。

## 非职责

本模块不承载产品领域逻辑，不建立第二套 serve 路线，不直接改变 Verification、权限契约或报告事实，也不把缓存、依赖或构建产物写回源码树。`package` 只组装已冻结的 Windows x64 Portable，不改变产品安全语义。

## 稳定入口与模块边界

只有仓库根的 `scripts/dev.ps1` 可以装配 `scripts/dev/` 下的模块。子模块共享入口建立的简单 `$script:` 上下文，但不能互相 dot-source。

| 位置 | 负责什么 | 不负责什么 |
| --- | --- | --- |
| `scripts/dev.ps1` | 参数合同、模块装配、公开命令分派、顶层环境恢复 | 具体 Python、前端、准备或打包实现 |
| `scripts/dev/common.ps1` | 统一失败、外部命令、摘要、状态、prepare lock、调用者环境保存与恢复 | 领域工具准备 |
| `scripts/dev/python.ps1` | Conda、uv、CPython 3.13、依赖同步、editable 拓扑和运行身份 | Node、Chromium、产品 serve |
| `scripts/dev/frontend.ps1` | 固定 Node/pnpm、受控工作区、编辑器插件、指纹和 production build | 正式前端源码、产品 UI 行为 |
| `scripts/dev/prepare.ps1` | Chromium、数据库、source receipt 和源码可启动组合 | Wheel 与普通产品启动展示 |
| `scripts/dev/commands.ps1` | start/test/schema/docs/frontend-test/cli/shell 的能力组合 | 重复实现各模块已有能力 |
| `scripts/dev/sample-test.ps1` | 自动 L5 的 PowerShell 入口、独立运行目录、Harness 调用与净化汇总发布位置 | 产品 prepare、UIA 或十阶段编排实现 |
| `scripts/dev/sample_test/driver.py` | `official/validation/competition/all` 参数解析、suite 分派与成功汇总原子发布 | 十阶段编排、30 Case 实现或 Windows UIA |
| `scripts/dev/sample_test/official.py` | 从真实 `start.cmd` 开始验证问题版、一键合同、Agent 修复、三态结果与资源收口 | 普通应用 Recording UIA 细节、生产领域语义 |
| `scripts/dev/sample_test/validation.py` | 30 Case 编排与正式 Continuity/Breakpoint 算法调用 | private oracle 定义或 Domain Model 重写 |
| `scripts/dev/sample_test/adapter.py`、`registry.py`、`oracle.py` | 公开事实适配、public registry 与 private oracle 外层验收 | 产品 Verdict 或目标授权输入 |
| `scripts/dev/sample_test/windows.py` | 普通应用 headed Recording 的 Windows UIA 能力探针 | 官方样例一键配置、前台激活、物理输入、CDP 或浏览器测试开关 |
| `scripts/dev/package.ps1` | Windows x64 Portable 的工具准备、内部 Wheel 与固定 artifacts 总编排 | Base Tree/ZIP 细节、产品领域语义 |
| `scripts/build/` | Hatch 前端映射与 Portable Base Tree、双 ZIP、校验和组装 | 开发命令分派、源码运行准备和产品领域逻辑 |
| `scripts/start.ps1`、`scripts/startup/` | 六阶段 Windows 产品启动、展示、运行状态、源码回执消费和产品入口 | 开发命令总控、第二套 prepare |
| `scripts/docs/generate.py` | 确定性生成代码参考并检查 Docs 路由和链接 | 人工文档内容裁决 |

精确函数、签名和加载关系见[开发脚本自动代码参考](../../03_参考手册/代码/scripts.md)。

## 我想修改什么

| 任务 | 主要位置 | 直接验证 |
| --- | --- | --- |
| 修改 Python/Conda/uv 或依赖同步 | `environment.yml`、`uv.lock`、`scripts/dev/python.ps1` | `dev.ps1 test tests/scripts/test_dev_script.py`；按需 `bootstrap` / `sync` / `prepare` |
| 修改 Node/pnpm、前端工作区或 build | `scripts/dev/frontend.ps1`、`product/frontend/package.json`、`product/frontend/pnpm-lock.yaml` | `dev.ps1 frontend-test`；`dev.ps1 prepare -ForcePrepare` |
| 新增或调整开发命令 | `scripts/dev.ps1`、`scripts/dev/commands.ps1` 和唯一所属模块 | `dev.ps1 test tests/scripts/test_dev_script.py`；直接运行目标命令 |
| 修改自动 L5 | `scripts/dev/sample-test.ps1`、`scripts/dev/sample_test/` | `dev.ps1 test tests/scripts/test_sample_test.py tests/scripts/test_dev_script.py`；最终验收时运行一次 `dev.ps1 sample-test` |
| 修改 prepare 的 Chromium、数据库或源码回执 | `scripts/dev/prepare.ps1` | `dev.ps1 prepare`；相关脚本测试 |
| 修改 Windows Banner、菜单、阶段或动画 | `scripts/start.ps1`、`scripts/startup/presentation.ps1`、`scripts/startup/runtime.ps1` | `dev.ps1 test tests/scripts/test_start_script.py`；自动 L5 与展示验收 |
| 修改启动对源码回执的校验 | `scripts/startup/source.ps1`、`scripts/dev/prepare.ps1` | 启动脚本测试；`dev.ps1 prepare` |
| 修改 CLI/serve 的受控调用 | `scripts/startup/product.ps1` | 启动脚本测试；自动 L5 |
| 修改 Windows x64 Portable | `scripts/dev/package.ps1`、`scripts/build/portable.py`、`scripts/build/hatch_build.py` | Portable 直接测试；`dev.ps1 package`；仓库外 full/nosamples 烟测 |
| 修改文档生成器 | `scripts/docs/generate.py` | `dev.ps1 test tests/scripts/test_docs.py`；`dev.ps1 docs` |

完整操作路线和故障入口见[修改开发环境](../任务/修改开发环境.md)。

## 必须保持的边界

- `start.cmd → start.ps1 → dev.ps1 prepare → serve` 是唯一产品启动路线；`dev.ps1 start` 不提前取得 prepare lock。
- `docs` 只定位已有且符合要求的受控 CPython 3.13，不为文档检查执行完整 uv 同步。
- `package` 准备冻结 CPython、生产依赖、前端与 Chromium，只从一个 Base Tree 生成 full/nosamples；正式产物只进入 `var/development/release/artifacts`。
- `scripts/dev.ps1` 只做总控；sample-test 的 PowerShell、Python Harness 和独立 Recording UIA 探针都留在 `scripts/dev/`，不回填总入口或 `commands.ps1`。
- `sample-test` 必须从真实 `start.cmd` 启动默认 GUI 控制面；不能改成直接 `serve`、`create_app()` 或 TestClient，也不能提前替产品完成前端、数据库和 source receipt 准备。
- validation 类 suite 只有在外层验收成功后才原子替换 `var/audit/competition/latest-validation-summary.json`；展示副本只含聚合计数与来源元数据，失败运行、逐 Case 结果和 private oracle 都不能覆盖或进入该文件。
- UIA 依赖只属于 dev dependency，`product/**` 不得导入 `pywinauto`；普通应用 Recording 仍由正式 Worker 和独立 Recording Process 创建 headed Chromium，官方样例不得为此恢复旧逐项录制导览。
- `-Update`、`-ForcePrepare` 和位置参数按入口合同显式允许，非法组合在锁和其他副作用前失败。
- 脚本设置的环境变量、控制台编码、当前目录和 prepare lock 在成功、失败与提前退出时都必须恢复。
- 前端 `node_modules`、构建输出、缓存、测试临时目录、下载和工具安装只进入 `var/`。
- 启动动画停止顺序是“通知 → 等待退出 → 必要时超时强杀 → 确认退出 → 清行 → 永久输出”；动画失败不能改变产品结果。

## 直接验证

按修改范围选择最小充分证据：

```powershell
.\scripts\dev.ps1 test tests/scripts
.\scripts\dev.ps1 test tests/architecture/test_dependencies.py
.\scripts\dev.ps1 docs
.\scripts\dev.ps1 schema
```

涉及真实工具准备或 Portable 时，再分别执行 `dev.ps1 prepare`、`dev.ps1 package`。发行路线见[修改发布与便携版](../任务/修改发布与便携版.md)。最终验收的唯一自动 L5 入口是 `dev.ps1 sample-test`；人工只做展示验收。PowerShell 改动还要确认 Windows PowerShell 5.1 解析与项目规定的 UTF-8 BOM，最终运行 `git diff --check`。
