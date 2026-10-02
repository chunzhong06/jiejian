# 检查当前文档的内部链接、路由、实现路径与数据库声明。
from __future__ import annotations
import ast
import re
from pathlib import Path
from urllib.parse import unquote

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



def check_documentation(root: Path) -> list[str]:
    return _markdown_links(root) + _llms_targets(root) + _source_paths(root) + _database_head(root)
