# 自动代码参考：backend/cli

> 自动生成。当前源码结构与注册投影，不代表运行验收或完整调用图。

<!-- GENERATED:START -->

### `product/backend/cli/__init__.py`

[打开源码](../../../../../product/backend/cli/__init__.py) · Python AST；作用域内import不表示每次调用均执行。


静态import / dot-source：`.app`

### `product/backend/cli/__main__.py`

[打开源码](../../../../../product/backend/cli/__main__.py) · Python AST；作用域内import不表示每次调用均执行。


静态import / dot-source：`product.backend.cli`

### `product/backend/cli/app.py`

[打开源码](../../../../../product/backend/cli/app.py) · Python AST；作用域内import不表示每次调用均执行。

- `root(context, var_dir, json_output, version) -> None`
- `main() -> None`

静态import / dot-source：`__future__`、`pathlib`、`product.backend`、`product.backend.cli.bootstrap`、`product.backend.cli.commands.system`、`product.backend.cli.localization`、`product.backend.cli.presentation`、`product.backend.core.errors`、`product.backend.infra.runtime.process.controlled.identity`、`sys`、`typer`、`uuid`

### `product/backend/cli/bootstrap.py`

[打开源码](../../../../../product/backend/cli/bootstrap.py) · Python AST；作用域内import不表示每次调用均执行。

- `class CliOptions`
- `runtime_settings(context) -> Settings`
- `application_scope(context, environ) -> Iterator[object]`
- `default_frontend_dir() -> Path`

静态import / dot-source：`__future__`、`collections.abc`、`contextlib`、`dataclasses`、`pathlib`、`product.backend.infra.runtime.logging`、`product.backend.infra.runtime.settings`、`typer`、`作用域内：product.backend.composition`、`作用域内：product.backend.core.errors`、`作用域内：product.backend.infra.runtime.serve_lock`

### `product/backend/cli/commands/__init__.py`

[打开源码](../../../../../product/backend/cli/commands/__init__.py) · Python AST；作用域内import不表示每次调用均执行。


### `product/backend/cli/commands/system.py`

[打开源码](../../../../../product/backend/cli/commands/system.py) · Python AST；作用域内import不表示每次调用均执行。

- `class GuiBrowser`
- `class ServeReadinessStatus`
- `serve_command(context, host, port, open_browser, launcher_event, browser, frontend_dir, official_sample_root) -> None`
- `doctor_command(context) -> None`
- `maintenance_clean_assistant_command(context, confirm) -> None`
- `maintenance_clean_logs_command(context, confirm) -> None`
- `maintenance_clean_temporary_command(context, confirm) -> None`
- `maintenance_clean_all_command(context, confirm) -> None`
- `maintenance_repair_command(context, confirm) -> None`

静态import / dot-source：`__future__`、`enum`、`logging`、`os`、`pathlib`、`product.backend.cli.bootstrap`、`product.backend.cli.presentation`、`product.backend.core.errors`、`product.backend.infra.runtime.diagnostics`、`time`、`typer`、`作用域内：httpx`、`作用域内：ipaddress`、`作用域内：product.backend.api`、`作用域内：product.backend.cli.gui_browser`、`作用域内：product.backend.cli.gui_console`、`作用域内：product.backend.infra.runtime.serve_lock`、`作用域内：threading`、`作用域内：uvicorn`、`动态引用：webbrowser`

### `product/backend/cli/gui_browser.py`

[打开源码](../../../../../product/backend/cli/gui_browser.py) · Python AST；作用域内import不表示每次调用均执行。

- `class GuiBrowserSession`
- `GuiBrowserSession.closed(self) -> bool`
- `GuiBrowserSession.adopt(self, process) -> bool`
- `GuiBrowserSession.close(self) -> None`
- `open_gui_browser(url, var_dir, session, system_browser) -> bool`

静态import / dot-source：`__future__`、`json`、`logging`、`os`、`pathlib`、`product.backend.infra.runtime.paths`、`product.backend.infra.runtime.process.tree`、`subprocess`、`threading`、`urllib.parse`、`webbrowser`、`作用域内：ctypes`

### `product/backend/cli/gui_console.py`

[打开源码](../../../../../product/backend/cli/gui_console.py) · Python AST；作用域内import不表示每次调用均执行。

- `console_key_reader() -> Callable[[], str &#124; None] &#124; None`
- `launcher_key_reader(event_name)`
- `run_gui_console(open_browser, stopped, is_stopping, emit, read_key, monotonic) -> None`

静态import / dot-source：`__future__`、`collections.abc`、`contextlib`、`os`、`sys`、`threading`、`time`、`作用域内：ctypes`、`作用域内：msvcrt`、`作用域内：re`

### `product/backend/cli/localization.py`

[打开源码](../../../../../product/backend/cli/localization.py) · Python AST；作用域内import不表示每次调用均执行。

- `class ChineseHelpFormatter`
- `ChineseHelpFormatter.write_usage(self, prog, args, prefix) -> None`
- `configure_cli_localization() -> None`

静态import / dot-source：`__future__`、`collections.abc`、`re`、`typer`

### `product/backend/cli/presentation.py`

[打开源码](../../../../../product/backend/cli/presentation.py) · Python AST；作用域内import不表示每次调用均执行。

- `configure_presentation(mode, machine_only) -> None`
- `presentation_mode(context) -> str`
- `_FIELD_LABELS`
- `_DOCTOR_LABELS`
- `emit_human(payload) -> None`
- `emit_doctor(report) -> None`
- `emit_command(kind, data, next_actions, warnings, human) -> None`
- `emit_json(payload) -> None`
- `fail(error) -> NoReturn`
- `human_wait(message)`

静态import / dot-source：`__future__`、`click`、`collections.abc`、`contextlib`、`json`、`product.backend.core.errors`、`threading`、`typer`、`typing`、`uuid`

<!-- GENERATED:END -->
