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
    return bool(re.search(r"(?m)^(?:>|-)\s*状态[：:]\s*(?:提议|已取代|已废弃|已拒绝|PROPOSED|DEPRECATED|SUPERSEDED)\b", text))


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
            target, _, symbol = target.partition("::")
            base = root / "product/frontend" if target.startswith("src/") else root
            if target.startswith("features/"):
                base = root / "product/frontend/src"
            reason = _link_failure(root, base / "_paths", target)
            resolved = (base / target).resolve()
            if reason is None and resolved.is_dir() and not any(path.is_file() for path in resolved.rglob("*")):
                reason = "源码目录没有文件"
            if reason:
                failures.append(f"{source.relative_to(root)} -> `{target}`（静态源码路径：{reason}）")
            elif symbol:
                problem = _source_symbol(resolved, symbol)
                if problem:
                    failures.append(f"{source.relative_to(root)} -> `{target}::{symbol}`（{problem}）")
    return failures


def _database_head(root: Path) -> list[str]:
    """只解析声明常量，不导入 Storage 或打开数据库。"""
    source = root / "product/backend/infra/storage/db.py"
    guide = root / "docs/工程/数据与协议/修改数据库.md"
    if not source.exists() or not guide.exists():
        return []
    tree = ast.parse(source.read_text(encoding="utf-8"))
    head = None
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id == "_CURRENT_MIGRATION_REVISION" for target in node.targets):
            head = ast.literal_eval(node.value)
    declared = re.search(r"当前数据库 head 为 `([^`]+)`", guide.read_text(encoding="utf-8"))
    # 当前指南链接唯一生成head；旧式明确声明仍严格校验，防止散落的过期值。
    if head is None or (declared and declared.group(1) != head) or (not declared and "数据库迁移.md" not in guide.read_text(encoding="utf-8")):
        return [f"{guide.relative_to(root)}：数据库 head 与源码声明不一致（当前 {head}）"]
    return []



def _source_symbol(path: Path, symbol: str) -> str | None:
    """只检查明确可静态读取的符号，不调用描述符或import生产模块。"""
    if path.suffix == '.py':
        try:
            nodes = ast.parse(path.read_text(encoding='utf-8-sig')).body
        except SyntaxError:
            return '源码无法解析'
        for part in symbol.split('.'):
            match = None
            for node in nodes:
                if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == part:
                    match = node
                    break
                if isinstance(node, (ast.Assign, ast.AnnAssign)):
                    targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                    if any(isinstance(t, ast.Name) and t.id == part for t in targets):
                        match = node
                        break
            if match is None:
                return '静态符号不存在'
            nodes = getattr(match, 'body', [])
        return None
    if path.suffix in {'.ts', '.tsx', '.js', '.mjs', '.cjs'}:
        text = path.read_text(encoding='utf-8-sig')
        if re.search(r'\bexport\s+(?:default\s+)?(?:async\s+)?(?:function|const|class|type|interface)\s+' + re.escape(symbol) + r'\b', text):
            return None
        return 'JS/TS导出符号未静态确定，请引用真实定义'
    return '该文件类型尚不支持静态符号定位'


def _command_examples(root: Path, notices: list[str] | None = None) -> list[str]:
    """核对正式测试示例的字面路径；绝不执行文档中的命令。"""
    failures = []
    for source in sorted((root / 'docs').rglob('*.md')):
        if any(part in {'生成', '决策'} for part in source.relative_to(root / 'docs').parts):
            continue
        text = source.read_text(encoding='utf-8')
        if _noncurrent(text):
            continue
        for language, body in re.findall(r'(?ms)^```([^\n]*)\n(.*?)^```\s*$', text):
            if language.strip().lower() not in {'powershell', 'ps1', 'pwsh', 'shell', 'bash'}:
                continue
            for line in body.splitlines():
                match = re.search(r'''dev\.ps1["']?\s+(frontend-test|test)\s+(.+)''', line)
                if not match:
                    continue
                # 只检查可识别的路径参数；占位符、变量、筛选表达式不猜测成文件。
                arguments = re.findall(r'''"[^"]*"|'[^']*'|\S+''', match.group(2))
                for argument in arguments:
                    value = argument.strip("\"'").replace('\\', '/')
                    if value in {'...', '…'} or value.startswith('$') or (value.startswith(('tests/', 'src/', 'product/')) and any(c in value for c in '$*?[]{}<>…')):
                        if notices is not None:
                            notices.append(f'{source.relative_to(root)}：{value}')
                        continue
                    if not value.startswith(('tests/', 'src/', 'product/')):
                        continue
                    filename, _, nodeid = value.partition('::')
                    base = root / 'product/frontend' if match.group(1) == 'frontend-test' else root
                    path = (base / filename).resolve()
                    if not path.is_relative_to(base.resolve()) or not path.exists():
                        failures.append(f'{source.relative_to(root)} -> {value}（测试命令路径不存在或越界）')
                    elif nodeid and path.suffix == '.py' and '[' not in nodeid:
                        problem = _source_symbol(path, nodeid.replace('::', '.'))
                        if problem:
                            failures.append(f'{source.relative_to(root)} -> {value}（测试命令：{problem}）')
    return failures


def check_documentation(root: Path, *, notices: list[str] | None = None) -> list[str]:
    return _markdown_links(root) + _llms_targets(root) + _source_paths(root) + _database_head(root) + _command_examples(root, notices)
