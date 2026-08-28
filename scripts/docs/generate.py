# 生成界鉴的确定性代码参考与协议索引，不导入或执行生产模块。

"""从源码文本与 AST 元数据生成稳定的 Markdown 参考。"""

from __future__ import annotations

import argparse
import ast
import re
from pathlib import Path


START = "<!-- GENERATED:START -->"
END = "<!-- GENERATED:END -->"

CODE_GROUPS = {
    "backend-core": (("product/backend/core",), "后端 Core"),
    "backend-workflows": (("product/backend/workflows",), "后端 Workflows"),
    "backend-infra-runtime": (("product/backend/infra/runtime",), "后端 Runtime"),
    "backend-infra-storage": (("product/backend/infra/storage",), "后端 Storage"),
    "backend-api-cli": (("product/backend/api", "product/backend/cli"), "后端 API 与 CLI"),
    "frontend": (("product/frontend/src",), "前端"),
    "scripts": (("scripts",), "开发脚本"),
}


def _signature(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    """不求值注解或默认值，只渲染紧凑签名。"""
    args = list(node.args.posonlyargs) + list(node.args.args)
    rendered = [arg.arg for arg in args]
    if node.args.vararg:
        rendered.append(f"*{node.args.vararg.arg}")
    rendered.extend(arg.arg for arg in node.args.kwonlyargs)
    if node.args.kwarg:
        rendered.append(f"**{node.args.kwarg.arg}")
    result = ast.unparse(node.returns) if node.returns else ""
    suffix = f" -> {result}" if result else ""
    return f"{node.name}({', '.join(rendered)}){suffix}"


def _python_symbols(path: Path) -> list[str]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (OSError, SyntaxError):
        return []
    symbols: list[str] = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and not node.name.startswith("_"):
            symbols.append(f"- `{_signature(node)}`")
        elif isinstance(node, ast.ClassDef) and not node.name.startswith("_"):
            symbols.append(f"- `class {node.name}`")
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                if isinstance(target, ast.Name) and target.id.isupper():
                    symbols.append(f"- `{target.id}`")
    return symbols


def _python_imports(path: Path) -> list[str]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (OSError, SyntaxError):
        return []
    imports: list[str] = []
    for node in tree.body:
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imports.append("." * node.level + (node.module or ""))
    return sorted(set(imports))


def _typescript_symbols(path: Path) -> tuple[list[str], list[str]]:
    text = path.read_text(encoding="utf-8")
    symbols = sorted(
        set(
            re.findall(
                r"\bexport\s+(?:default\s+)?(?:async\s+)?(?:function|const|class)\s+([A-Za-z_$][\w$]*)|\bexport\s+(?:type|interface)\s+([A-Za-z_$][\w$]*)",
                text,
            )
        )
    )
    names = [next(value for value in item if value) for item in symbols]
    imports = sorted(set(re.findall(r"from\s+['\"]([^'\"]+)['\"]", text)))
    return [f"- `{name}`" for name in names], imports


def _powershell_param_names(text: str) -> list[str]:
    names: set[str] = set()
    for match in re.finditer(r"(?im)^\s*param\s*\(", text):
        start = match.end()
        depth = 1
        cursor = start
        while cursor < len(text) and depth:
            if text[cursor] == "(":
                depth += 1
            elif text[cursor] == ")":
                depth -= 1
            cursor += 1
        if depth:
            continue
        block = text[start : cursor - 1]
        names.update(re.findall(r"(?m)(?:^|,)\s*(?:\[[^\]]+\]\s*)*\$([A-Za-z_]\w*)", block))
    return sorted(names)


def _powershell_dot_sources(text: str) -> list[str]:
    dot_sources: set[str] = set()
    literal_pattern = re.compile(r"^\s*\.\s+(['\"])([^'\"]+)\1\s*(?:#.*)?$", re.I)
    join_pattern = re.compile(
        r"^\s*\.\s+\(\s*Join-Path\s+\$PSScriptRoot\s+(['\"])([^'\"$]+)\1\s*\)\s*(?:#.*)?$",
        re.I,
    )
    for line in text.splitlines():
        literal = literal_pattern.match(line)
        if literal:
            dot_sources.add(literal.group(2))
            continue
        joined = join_pattern.match(line)
        if joined:
            relative = joined.group(2).replace("\\", "/")
            while relative.startswith("./"):
                relative = relative[2:]
            dot_sources.add(f"$PSScriptRoot/{relative}")
    # 只投影可静态确定的路径；动态表达式若截取半行，会生成不存在的伪入口。
    return sorted(dot_sources)


def _powershell_symbols(path: Path) -> tuple[list[str], list[str]]:
    text = path.read_text(encoding="utf-8-sig")
    functions = sorted(set(re.findall(r"(?im)^\s*function\s+([\w-]+)", text)))
    parameters = _powershell_param_names(text)
    dot_sources = _powershell_dot_sources(text)
    symbols = [f"- `function {name}`" for name in functions]
    symbols.extend(f"- `param ${name}`" for name in parameters)
    return symbols, dot_sources


def _files(root: Path, relative: str) -> list[Path]:
    base = root / relative
    if not base.exists():
        return []
    return sorted(
        path
        for path in base.rglob("*")
        if path.is_file()
        and path.suffix.lower() in {".py", ".ts", ".tsx", ".ps1"}
        and "__pycache__" not in path.parts
        and "node_modules" not in path.parts
    )


def _render_code(root: Path, relatives: tuple[str, ...]) -> str:
    sources = "、".join(f"{relative}/" for relative in relatives)
    blocks: list[str] = [START, "", f"<!-- 此区域由 scripts/docs/generate.py 从 {sources} 读取。 -->", ""]
    for relative in relatives:
        for path in _files(root, relative):
            rel = path.relative_to(root).as_posix()
            imports: list[str] = []
            symbols: list[str] = []
            if path.suffix == ".py":
                symbols = _python_symbols(path)
                imports = _python_imports(path)
            elif path.suffix in {".ts", ".tsx"}:
                symbols, imports = _typescript_symbols(path)
            else:
                symbols, imports = _powershell_symbols(path)
            if not symbols and not imports:
                continue
            blocks.append(f"### `{rel}`")
            if symbols:
                blocks.append("\n".join(symbols))
            if imports:
                blocks.append("主要 import / dot-source：" + ", ".join(f"`{item}`" for item in imports))
            blocks.append("")
    blocks.extend([END, ""])
    return "\n".join(blocks)


def _render_code_document(title: str, generated: str) -> str:
    """渲染整份机器维护文档，避免陈旧文件头在生成区外累积。"""
    header = f"# 自动代码参考：{title}\n\n> 生成区域只描述当前代码结构；职责与安全理由由模块参考和任务指南维护。"
    return header + "\n\n" + generated.strip() + "\n"


def _replace_generated(path: Path, generated: str) -> None:
    original = path.read_text(encoding="utf-8") if path.exists() else ""
    pattern = re.compile(re.escape(START) + r".*?" + re.escape(END), re.S)
    if pattern.search(original):
        updated = pattern.sub(generated.strip(), original, count=1)
    else:
        updated = original.rstrip() + "\n\n" + generated
    path.write_text(updated.rstrip() + "\n", encoding="utf-8", newline="\n")


def _generated_block(path: Path) -> str:
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    match = re.search(re.escape(START) + r".*?" + re.escape(END), text, re.S)
    return match.group(0).strip() if match else ""


def _markdown_links(root: Path) -> list[str]:
    failures: list[str] = []
    files = list((root / "docs").rglob("*.md"))
    for entry in (root / "README.md", root / "AGENTS.md"):
        if entry.exists():
            files.append(entry)
    pattern = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
    for source in sorted(files):
        text = source.read_text(encoding="utf-8")
        for raw_target in pattern.findall(text):
            target = raw_target.strip().strip("<>").split("#", 1)[0]
            if not target or target.startswith(("http://", "https://", "mailto:")):
                continue
            resolved = (source.parent / target).resolve()
            try:
                resolved.relative_to(root.resolve())
            except ValueError:
                failures.append(f"{source.relative_to(root)} -> {target}（越出仓库）")
                continue
            if not resolved.exists():
                failures.append(f"{source.relative_to(root)} -> {target}（目标不存在）")
    return failures


def _llms_targets(root: Path) -> list[str]:
    failures: list[str] = []
    route = root / "docs/llms.txt"
    for line_number, line in enumerate(route.read_text(encoding="utf-8").splitlines(), 1):
        if "→" not in line:
            continue
        target = line.split("→", 1)[1].strip()
        target = target.strip("` ")
        if not target or target.startswith(("http://", "https://")):
            continue
        candidates = [root / target, root / "docs" / target]
        if not any(candidate.exists() for candidate in candidates):
            failures.append(f"docs/llms.txt:{line_number} -> {target}")
    return failures


def _render_schema_index(root: Path) -> str:
    schemas = sorted((root / "product/protocols/schemas").rglob("*.json"))
    lines = [START, "", "<!-- Schema 文件由 product/protocols/schema.py 注册表治理；本区只列当前文件。 -->", ""]
    for schema in schemas:
        lines.append(f"- `{schema.relative_to(root).as_posix()}`")
    lines.extend(["", END, ""])
    return "\n".join(lines)


def generate(root: Path, update: bool) -> list[Path]:
    changed: list[Path] = []
    failures: list[str] = []
    code_dir = root / "docs/03_参考手册/代码"
    for name, (relatives, title) in CODE_GROUPS.items():
        path = code_dir / f"{name}.md"
        document = _render_code_document(title, _render_code(root, relatives))
        if update:
            before = path.read_text(encoding="utf-8") if path.exists() else ""
            if before != document:
                path.write_text(document, encoding="utf-8", newline="\n")
                changed.append(path)
        elif not path.exists():
            failures.append(f"代码参考缺失：{path.relative_to(root)}")
        elif path.read_text(encoding="utf-8") != document:
            failures.append(f"代码参考漂移：{path.relative_to(root)}")
    protocol = root / "docs/03_参考手册/协议/公共数据与Schema版本.md"
    if update:
        before = protocol.read_text(encoding="utf-8")
        _replace_generated(protocol, _render_schema_index(root))
        if protocol.read_text(encoding="utf-8") != before:
            changed.append(protocol)
    else:
        expected = _render_schema_index(root).strip()
        if _generated_block(protocol) != expected:
            failures.append(f"协议参考漂移：{protocol.relative_to(root)}")
        failures.extend(_markdown_links(root))
        failures.extend(_llms_targets(root))
    if failures:
        raise SystemExit("\n".join(failures))
    return changed


def main() -> int:
    parser = argparse.ArgumentParser(description="生成界鉴代码与协议参考")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--update", action="store_true")
    args = parser.parse_args()
    generate(args.root.resolve(), args.update)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
