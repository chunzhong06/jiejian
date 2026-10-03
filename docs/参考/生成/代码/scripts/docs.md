# 自动代码参考：scripts/docs

> 自动生成。当前源码结构与注册投影，不代表运行验收或完整调用图。

<!-- GENERATED:START -->

### `scripts/docs/generate.py`

[打开源码](../../../../../scripts/docs/generate.py) · Python AST；作用域内import不表示每次调用均执行。

- `START`
- `END`
- `GENERATED_DIR`
- `render(root) -> dict[str, str]`
- `generate(root, update) -> list[Path]`
- `main() -> int`

静态import / dot-source：`__future__`、`argparse`、`os`、`pathlib`、`scripts.docs.registrations`、`scripts.docs.sources`、`sys`、`作用域内：tests.docs.checks`

### `scripts/docs/registrations.py`

[打开源码](../../../../../scripts/docs/registrations.py) · Python AST；作用域内import不表示每次调用均执行。

- `api_routes(root) -> list[tuple[str, str, str]]`
- `mcp_tools(root) -> list[tuple[str, str]]`
- `worker_branches(root)`
- `root_versions(schema) -> str`
- `schema_entries(root)`
- `migration_rows(root)`

静态import / dot-source：`__future__`、`ast`、`json`、`pathlib`、`scripts.docs.sources`

### `scripts/docs/sources.py`

[打开源码](../../../../../scripts/docs/sources.py) · Python AST；作用域内import不表示每次调用均执行。

- `SOURCE_SUFFIXES`
- `CONFIG_SUFFIXES`
- `ROOT_INPUTS`
- `IGNORED_DIRECTORIES`
- `parse_python(path) -> ast.Module`
- `signature(node) -> str`
- `public_symbols(tree) -> list[str]`
- `powershell(text) -> tuple[list[str], list[str]]`
- `describe(path) -> tuple[list[str], list[str], str]`
- `source_files(root) -> list[Path]`
- `bucket(relative) -> str`
- `grouped_sources(root) -> dict[str, list[Path]]`

静态import / dot-source：`__future__`、`ast`、`collections`、`pathlib`、`re`

<!-- GENERATED:END -->
