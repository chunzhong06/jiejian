# 生成确定性代码参考与协议索引，检查文档路由及静态事实，不执行生产模块。

"""从源码文本与 AST 元数据生成稳定的 Markdown 参考。"""

from __future__ import annotations

import argparse
import ast
import re
from pathlib import Path
from urllib.parse import unquote


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
    header = f"# 自动代码参考：{title}\n\n> 生成区域只描述当前代码结构；职责与安全理由由能力映射和任务指南维护。"
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


def _prose(text: str) -> str:
    """忽略代码围栏，避免把示例标题、链接或路径当成正文。"""
    return re.sub(r"(?ms)^\s*(`{3,}|~{3,})[^\n]*\n.*?^\s*\1\s*$", "", text)


def _anchors(path: Path) -> set[str]:
    """按仓库使用的 Markdown 标题生成锚点，保留中文及重复标题序号。"""
    text = _prose(path.read_text(encoding="utf-8"))
    anchors = set(re.findall(r'<[^>]+\b(?:id|name)=[\"\']([^\"\']+)', text))
    for heading in re.findall(r"(?m)^#{1,6}\s+(.+?)\s*#*\s*$", text):
        heading = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", heading)
        slug = re.sub(r"[^\w\s-]", "", heading.lower()).replace(" ", "-")
        candidate, suffix = slug, 0
        while candidate in anchors:
            suffix += 1
            candidate = f"{slug}-{suffix}"
        anchors.add(candidate)
    return anchors


def _noncurrent(text: str) -> bool:
    """只识别文档自己的状态声明，正文引用历史状态不改变整篇的归属。"""
    return bool(re.search(r"(?m)^>\s*状态[：:]\s*(?:提议|已取代|已废弃|已拒绝|PROPOSED|DEPRECATED|SUPERSEDED)\b", text))


def _link_failure(root: Path, source: Path, target: str) -> str | None:
    """检查仓库内目标与 Markdown 章节；不联网或解析代码内容。"""
    filename, _, fragment = unquote(target).partition("#")
    resolved = (source.parent / filename).resolve() if filename else source.resolve()
    try:
        resolved.relative_to(root.resolve())
    except ValueError:
        return "越出仓库"
    if not resolved.exists():
        return "目标不存在"
    if fragment and resolved.suffix == ".md" and fragment not in _anchors(resolved):
        return "章节锚点不存在"
    return None


def _markdown_links(root: Path) -> list[str]:
    failures: list[str] = []
    files = list((root / "docs").rglob("*.md"))
    for entry in (root / "README.md", root / "AGENTS.md"):
        if entry.exists():
            files.append(entry)
    pattern = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
    for source in sorted(files):
        text = _prose(source.read_text(encoding="utf-8"))
        for raw_target in pattern.findall(text):
            target = raw_target.strip().strip("<>")
            if not target or target.startswith(("http://", "https://", "mailto:")):
                continue
            reason = _link_failure(root, source, target)
            if reason:
                failures.append(f"{source.relative_to(root)} -> {target}（{reason}）")
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
        filename = unquote(target).split("#", 1)[0]
        base = root if (root / filename).exists() else root / "docs"
        reason = _link_failure(root, base / "llms.txt", target)
        if not reason:
            text = (base / filename).read_text(encoding="utf-8")
            if _noncurrent(text):
                reason = "默认路由指向非当前内容"
        if reason:
            failures.append(f"docs/llms.txt:{line_number} -> {target}（{reason}）")
    return failures


def _source_paths(root: Path) -> list[str]:
    """检查当前人工正文的静态源码路径，历史提议与动态示例不作实现声明。"""
    failures: list[str] = []
    pattern = re.compile(r"`((?:product|samples|scripts|tests|src|features)/[^`\n]+)`")
    for source in sorted((root / "docs").rglob("*.md")):
        if any(part in {"生成", "决策"} for part in source.relative_to(root / "docs").parts):
            continue
        text = _prose(source.read_text(encoding="utf-8"))
        if _noncurrent(text):
            continue
        for target in pattern.findall(text):
            if any(character in target for character in "*?[]{}<>…") or "..." in target or re.search(r"\s", target):
                continue
            # 文档允许 file.py::symbol 定位；这里只验证文件，不猜测符号的运行时定义。
            target = target.split("::", 1)[0]
            base = root / "product/frontend" if target.startswith("src/") else root
            if target.startswith("features/"):
                base = root / "product/frontend/src"
            reason = _link_failure(root, base / "_paths", target)
            if reason:
                failures.append(f"{source.relative_to(root)} -> `{target}`（静态源码路径：{reason}）")
    return failures


def _database_head(root: Path) -> list[str]:
    """只解析声明常量，不导入 Storage 或打开数据库。"""
    source = root / "product/backend/infra/storage/db.py"
    guide = root / "docs/开发/能力/修改数据库.md"
    if not source.exists() or not guide.exists():
        return []
    tree = ast.parse(source.read_text(encoding="utf-8"))
    head = None
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id == "_CURRENT_MIGRATION_REVISION" for target in node.targets):
            head = ast.literal_eval(node.value)
    declared = re.search(r"当前数据库 head 为 `([^`]+)`", guide.read_text(encoding="utf-8"))
    if head is None or not declared or declared.group(1) != head:
        return [f"{guide.relative_to(root)}：数据库 head 与源码声明不一致（当前 {head}）"]
    return []


def _render_schema_index(root: Path) -> str:
    schemas = sorted((root / "product/protocols/schemas").rglob("*.json"))
    lines = [START, "", "<!-- Schema 文件由 product/protocols/schema.py 注册表治理；本区只列当前文件。 -->", ""]
    for schema in schemas:
        lines.append(f"- `{schema.relative_to(root).as_posix()}`")
    lines.extend(["", END, ""])
    return "\n".join(lines)


def generate(root: Path, update: bool) -> list[Path]:
    """显式更新只写生成区；只读检查失败抛出 SystemExit，不修正文或运行数据。"""
    changed: list[Path] = []
    failures: list[str] = []
    code_dir = root / "docs/参考/生成"
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
    protocol = root / "docs/参考/协议/公共数据与Schema版本.md"
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
        failures.extend(_source_paths(root))
        failures.extend(_database_head(root))
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
