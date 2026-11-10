# scripts 模块

<!-- generated:modules -->

[返回总索引](../模块索引.md)

按目录定位后读取对应小节；每个文件有独立标题，源码链接用于核对声明与直接消费者。行数和公开声明由静态提取，不表示运行验收。

按目录定位：[build](#build)（9 个文件）、[根目录](#根目录)（2 个文件）、[development](#development)（10 个文件）、[development/startup](#developmentstartup)（6 个文件）、[docs](#docs)（7 个文件）、[quality](#quality)（7 个文件）。

## build

### build/archive.py

[源码](../../../scripts/build/archive.py)（58 行）。公开声明：`iter_files`、`write_zip`、`archive_content`。

### build/common.py

[源码](../../../scripts/build/common.py)（82 行）。公开声明：`excluded_from_release`、`inside`、`reset_directory`、`run`、`sha256`。

### build/hatch_build.py

[源码](../../../scripts/build/hatch_build.py)（30 行）。公开声明：`CustomBuildHook`。

### build/launcher.py

[源码](../../../scripts/build/launcher.py)（77 行）。公开声明：`launcher_icon`、`compile_launcher`。

### build/linux.py

[源码](../../../scripts/build/linux.py)（114 行）。公开声明：`run`、`copy_tree`、`build`、`assemble`、`main`。

### build/portable.py

[源码](../../../scripts/build/portable.py)（139 行）。公开声明：`build`、`main`。

### build/resources.py

[源码](../../../scripts/build/resources.py)（86 行）。公开声明：`write_update_manifest`、`write_runtime_files`。

### build/runtime.py

[源码](../../../scripts/build/runtime.py)（201 行）。公开声明：`runtime_environment`、`copy_runtime`、`install_product`、`copy_node_runtime`、`prune_installed_runtime`、`metadata`、`place_product`、`portable_environment`。

### build/validation.py

[源码](../../../scripts/build/validation.py)（62 行）。公开声明：`validate_tree_content`、`validate_base`。

## 根目录

### dev.ps1

[源码](../../../scripts/dev.ps1)（84 行）。公开声明：包、内部机制或样式。

### start.ps1

[源码](../../../scripts/start.ps1)（113 行）。公开声明：包、内部机制或样式。

## development

### development/commands.ps1

[源码](../../../scripts/development/commands.ps1)（148 行）。公开声明：包、内部机制或样式。

### development/context.ps1

[源码](../../../scripts/development/context.ps1)（127 行）。公开声明：包、内部机制或样式。

### development/files.ps1

[源码](../../../scripts/development/files.ps1)（44 行）。公开声明：包、内部机制或样式。

### development/frontend-workspace.ps1

[源码](../../../scripts/development/frontend-workspace.ps1)（116 行）。公开声明：包、内部机制或样式。

### development/frontend.ps1

[源码](../../../scripts/development/frontend.ps1)（152 行）。公开声明：包、内部机制或样式。

### development/node.ps1

[源码](../../../scripts/development/node.ps1)（79 行）。公开声明：包、内部机制或样式。

### development/package.ps1

[源码](../../../scripts/development/package.ps1)（94 行）。公开声明：包、内部机制或样式。

### development/prepare.ps1

[源码](../../../scripts/development/prepare.ps1)（188 行）。公开声明：包、内部机制或样式。

### development/python.ps1

[源码](../../../scripts/development/python.ps1)（252 行）。公开声明：包、内部机制或样式。

### development/session.ps1

[源码](../../../scripts/development/session.ps1)（49 行）。公开声明：包、内部机制或样式。

## development/startup

### development/startup/context.ps1

[源码](../../../scripts/development/startup/context.ps1)（79 行）。公开声明：包、内部机制或样式。

### development/startup/panel.ps1

[源码](../../../scripts/development/startup/panel.ps1)（152 行）。公开声明：包、内部机制或样式。

### development/startup/presentation.ps1

[源码](../../../scripts/development/startup/presentation.ps1)（380 行）。公开声明：包、内部机制或样式。

### development/startup/product.ps1

[源码](../../../scripts/development/startup/product.ps1)（78 行）。公开声明：包、内部机制或样式。

### development/startup/runtime.ps1

[源码](../../../scripts/development/startup/runtime.ps1)（211 行）。公开声明：包、内部机制或样式。

### development/startup/source.ps1

[源码](../../../scripts/development/startup/source.ps1)（134 行）。公开声明：包、内部机制或样式。

## docs

### docs/checks.py

[源码](../../../scripts/docs/checks.py)（64 行）。公开声明：`check_documents`。

### docs/context.py

[源码](../../../scripts/docs/context.py)（102 行）。公开声明：`rendered_text`、`page_text`、`main`。

### docs/generate.py

[源码](../../../scripts/docs/generate.py)（120 行）。公开声明：`module_page`、`render`、`generate`、`main`。

### docs/markdown.py

[源码](../../../scripts/docs/markdown.py)（51 行）。公开声明：`without_fences`、`heading_id`、`heading_rows`、`heading_ids`、`link_targets`。

### docs/reading.py

[源码](../../../scripts/docs/reading.py)（160 行）。公开声明：`digest`、`Reader`、`read_context`。

### docs/sources.py

[源码](../../../scripts/docs/sources.py)（103 行）。公开声明：`tree`、`literal`、`modules`、`routes`、`schemas`、`migrations`。

### docs/task_records.py

[源码](../../../scripts/docs/task_records.py)（200 行）。公开声明：`unique_object`、`load_json`、`fields`、`nonempty`、`block`、`checked_ref`、`read_task`、`resume_task`等。

## quality

### quality/__init__.py

[源码](../../../scripts/quality/__init__.py)（1 行）。公开声明：包、内部机制或样式。

### quality/catalog.py

[源码](../../../scripts/quality/catalog.py)（71 行）。公开声明：`cases`、`Area`、`plan`。

### quality/identity.py

[源码](../../../scripts/quality/identity.py)（35 行）。公开声明：`tree_identity`、`input_identity`。

### quality/pytest_reporter.py

[源码](../../../scripts/quality/pytest_reporter.py)（68 行）。公开声明：`save`、`public_node`、`pytest_sessionstart`、`pytest_collection`、`pytest_collection_finish`、`pytest_collectreport`、`pytest_runtest_logreport`、`pytest_sessionfinish`。

### quality/run.py

[源码](../../../scripts/quality/run.py)（42 行）。公开声明：`main`。

### quality/syntax.py

[源码](../../../scripts/quality/syntax.py)（31 行）。公开声明：`check`、`main`。

### quality/vitest-reporter.mjs

[源码](../../../scripts/quality/vitest-reporter.mjs)（32 行）。公开声明：`QualityReporter`。
