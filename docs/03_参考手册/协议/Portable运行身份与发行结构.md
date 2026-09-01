# Portable 运行身份与发行结构

> 状态：CURRENT。本文解释 Windows x64 Portable 的发行根、包内 Python/Chromium、release.json、可选 Sample 层、可写 var 与移动目录信任。

## 先理解：Portable 是自包含发行，不是复制源码环境

源码仓库通过 `start.cmd → scripts/start.ps1 → dev.ps1 prepare` 使用 Conda、uv、Node/pnpm 和 `var/development`。Portable 则把已经冻结的 Python、生产依赖、界鉴 Wheel、前端 build 与 Playwright Chromium 组装进一个可移动目录；用户解压后从包根 `start.cmd` 进入，不安装、不更新、不构建，也不访问网络。

```text
JieJian-WebV1-<version>-Windows-x64/
├── start.cmd
├── README.txt
├── runtime/
│   ├── start.ps1
│   ├── release.json
│   ├── python/
│   └── playwright/
├── samples/          # 仅 full 包存在
└── var/              # 首次启动后在发行根内创建
```

full 与 nosamples 从同一个 Base Tree 生成。两包除 `samples/` 外的路径与文件 hash 必须逐项相同；nosamples 仍是完整产品，只是不提供官方协作空间 Sample。

## Release root 与相对启动

包根 `start.cmd` 只调用系统自带 Windows PowerShell 5.1，并把控制交给 `runtime/start.ps1`。PowerShell 从自己的 `$PSScriptRoot` 反推 release root，所有 Python、Chromium、前端、Sample 和 var 路径都相对发行根解析。

Portable 不读取仓库路径、当前工作目录、用户 PATH、Conda、uv、pip、Node、pnpm、源码 receipt 或 development cache。发行目录整体移动到另一个磁盘、中文或带空格路径后，身份与启动结果应保持一致。包内不存在 `direct_url.json`、editable path、源码绝对路径、node_modules、pycache 或构建临时目录。

## Portable 运行身份

Portable 主进程和受控子进程必须同时确认：

- `JIEJIAN_RUNTIME_MODE=portable`；
- `JIEJIAN_RELEASE_ROOT` 是当前真实发行根；
- 当前解释器位于 `<release>/runtime/python/python.exe`；
- `JIEJIAN_PLAYWRIGHT_EXECUTABLE` 与 `PLAYWRIGHT_BROWSERS_PATH` 都指向 `<release>/runtime/playwright` 内的唯一受控 Chromium；
- 关键包来源位于包内 Python，且 product frontend 使用 Wheel 内置 build；
- 开发态 `JIEJIAN_PROJECT_ROOT`、`PYTHONHOME`、`PYTHONPATH` 等身份不会泄漏进来。

身份验证形成 runtime fingerprint 和有限 report，Worker/Runner/Recording/Observer 等角色只继承自己的白名单变量。浏览器路径不只是“文件存在”，还必须证明落在当前发行根内；系统 Chrome、Edge、用户 Playwright cache 都不能替代。

## release.json 与产品版本

`runtime/release.json` 是发行元数据根，记录 schema、产品、产品/包版本、Windows x64、运行布局、CPython、Playwright 与 Chromium revision。产品版本来自 `product.backend.__version__`，Wheel 版本、文件名版本与 release.json 必须一致；不允许在 builder、前端清单或 API 中维护另一份产品版本。

`release.json.schema_version` 表示发行元数据格式，不等于产品版本。普通启动仍由代码内产品版本供 FastAPI、CLI `--version` 与系统设置页消费。

## 前端与 Sample 可选层

Portable 的前端由内部 Wheel 的 `product/frontend/dist` 提供，启动时不执行 TypeScript/Vite。full 包把仓库当前 `samples/` 作为只读发行输入复制到根层，并把明确存在的官方 Sample root 传给产品；nosamples 不创建虚假目录，也不启用测试开关，GUI 只如实显示官方 Sample 不可用。

Sample 是可选体验资产，不是产品依赖。产品包不从 Sample import，nosamples 的项目接入、Recording、Runner、Observer 与结果能力保持完整。

## 可写 var 与退出

Portable 第一次启动在 release root 内创建自己的 `var/`，其中 data/runtime/cache/logs/temp/test 各自遵守产品边界。TEMP/TMP 指向发行内任务拥有的可写目录，不能回退到系统目录。业务数据库、Evidence、Report 和项目事实进入 var/data；Worker、锁和当前前端运行事实进入 var/runtime；运行缓存和日志不写入 runtime/python、runtime/playwright 或源码包。

正常退出通过正式 `/api/system/shutdown`，依次停止 Worker、Runner/Recording/Chromium 和 ApplicationCore，释放控制端口、ServeLock 与 Worker lifetime lock。强制终止只能作为控制面不可用后的最后应急，且只回收当前启动拥有的进程。

## 构建与验证入口

`dev.ps1 package` 是唯一打包入口。`scripts/dev/package.ps1` 准备冻结材料与内部 Wheel，`scripts/build/portable.py` 以六个稳定阶段组装 Base Tree、双 ZIP 和 `SHA256SUMS.txt`：

```text
[1/6] 复制 CPython 与 Playwright
[2/6] 安装 frozen 生产依赖与 Wheel
[3/6] 元数据和 Base Tree 校验
[4/6] full ZIP
[5/6] nosamples ZIP
[6/6] 文件等价与 SHA256
```

每个阶段立即刷新；依赖安装使用 build 下任务拥有的 TEMP/TMP，失败保留所属阶段。正式验收把两个 ZIP 分别解压到仓库外中文空格路径，最好断网启动到 Workbench，检查 full/nosamples Sample 差异、1.0.15、正式 shutdown 和端口/进程/锁收口。

## 查询入口

| 要查什么 | 当前真源 |
| --- | --- |
| 产品版本 | `product/backend/__init__.py` |
| Portable identity | `product/backend/infra/runtime/process/identity.py`、`product/backend/infra/runtime/process/environment.py` |
| 打包总入口 | `scripts/dev/package.ps1` |
| Base Tree/双 ZIP/release.json | `scripts/build/portable.py` |
| Wheel 前端映射 | `scripts/build/hatch_build.py` |
| 直接/仓库外测试 | `tests/scripts/test_portable.py`、`tests/backend/infra/runtime/process/` |
| 操作 Guide | `docs/02_开发指南/任务/修改发布与便携版.md` |

## 相关真源

- [修改发布与便携版](../../02_开发指南/任务/修改发布与便携版.md)
- [修改开发环境](../../02_开发指南/任务/修改开发环境.md)
- [工作区与权限](../../04_工程约束/工作区与权限.md)
- [Windows 启动与首次使用边界](../../05_设计依据/ADR-0036-Windows启动与首次使用边界.md)
