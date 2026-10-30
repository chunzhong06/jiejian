# 有界读取本地源码并组合各格式检测器；排除约定的敏感与生成路径，不执行源码。
from __future__ import annotations
import hashlib
import os
import re
from pathlib import Path
from product.backend.domain.errors import ErrorCode, JiejianError
from product.backend.domain.changes.models import SourceFileFingerprint
from product.backend.application.onboarding.discovery import canonical_folder, is_reparse_point
from product.backend.application.application_understanding.analysis.models import (
    ApplicationAnalysisResult,
    SourceAnalysisLimits,
)
from product.backend.application.application_understanding.analysis.findings import (
    CandidateCollector,
)
from product.backend.application.application_understanding.analysis.javascript import (
    analyze_javascript,
)
from product.backend.application.application_understanding.analysis.openapi import analyze_openapi
from product.backend.application.application_understanding.analysis.python import analyze_python


_IGNORED_DIRECTORIES = frozenset(
    {
        ".git",
        ".next",
        ".nuxt",
        ".venv",
        "__pycache__",
        "build",
        "coverage",
        "dist",
        "node_modules",
        "var",
        "venv",
    }
)

_SOURCE_SUFFIXES = frozenset({".py", ".js", ".mjs", ".jsx", ".ts", ".tsx"})

_OPENAPI_NAMES = frozenset(
    {"openapi.json", "openapi.yaml", "openapi.yml", "swagger.json", "swagger.yaml", "swagger.yml"}
)

_SENSITIVE_FILE = re.compile(
    "(?:^\\.env(?:\\.|$)|credential|secret|private[_-]?key|\\.pem$|\\.key$)", re.IGNORECASE
)


class ApplicationUnderstandingAnalyzer:
    def __init__(self, *, limits: SourceAnalysisLimits | None = None) -> None:
        self.limits = limits or SourceAnalysisLimits()

    def analyze(self, project_id: str, source_root: str | Path) -> ApplicationAnalysisResult:
        """有界读取源码并返回确定性候选，不执行目标代码或自动批准规则。"""
        root = canonical_folder(source_root)
        files = self._read_sources(root)
        findings = CandidateCollector()
        for relative, raw in files:
            text = raw.decode("utf-8")
            content_hash = hashlib.sha256(raw).hexdigest()
            if Path(relative).name.casefold() in _OPENAPI_NAMES:
                analyze_openapi(
                    findings, relative, text, content_hash, max_bytes=self.limits.max_file_bytes
                )
            elif Path(relative).suffix.casefold() == ".py":
                analyze_python(findings, relative, text, content_hash)
            else:
                analyze_javascript(findings, relative, text, content_hash)
        # 摘要覆盖本次成功读取的相对路径和原始内容；它不表示忽略目录或不可读文件的完整快照。
        # 文件排序和路径分隔参与身份，不能只对检测出的候选做摘要。
        digest = hashlib.sha256()
        for relative, raw in files:
            digest.update(relative.encode("utf-8"))
            digest.update(b"\x00")
            digest.update(hashlib.sha256(raw).digest())
        return ApplicationAnalysisResult(
            source_fingerprint=digest.hexdigest(),
            files=tuple(
                (
                    SourceFileFingerprint(
                        relative_path=relative, content_sha256=hashlib.sha256(raw).hexdigest()
                    )
                    for relative, raw in files
                )
            ),
            role_candidates=findings.role_candidates(self.limits.max_roles),
            action_candidates=findings.action_candidates(self.limits.max_actions),
            files_read=len(files),
            total_bytes=sum((len(raw) for _, raw in files)),
        )

    def _read_sources(self, root: Path) -> tuple[tuple[str, bytes], ...]:
        entries_seen = 0
        files_seen = 0
        total_bytes = 0
        values: list[tuple[str, bytes]] = []
        stack: list[tuple[Path, int]] = [(root, 0)]
        while stack:
            directory, depth = stack.pop()
            try:
                with os.scandir(directory) as scanner:
                    entries = sorted(scanner, key=lambda item: item.name.casefold())
            except OSError:
                continue
            for entry in entries:
                entries_seen += 1
                if entries_seen > self.limits.max_entries:
                    self._budget_error("源码分析超过目录条目预算")
                path = Path(entry.path)
                try:
                    if is_reparse_point(path):
                        continue
                    if entry.is_dir(follow_symlinks=False):
                        if (
                            entry.name.casefold() not in _IGNORED_DIRECTORIES
                            and depth < self.limits.max_depth
                        ):
                            stack.append((path, depth + 1))
                        continue
                    if not entry.is_file(follow_symlinks=False):
                        continue
                except OSError:
                    continue
                lower_name = entry.name.casefold()
                if _SENSITIVE_FILE.search(lower_name):
                    continue
                if (
                    path.suffix.casefold() not in _SOURCE_SUFFIXES
                    and lower_name not in _OPENAPI_NAMES
                ):
                    continue
                try:
                    canonical = path.resolve(strict=True)
                    if canonical != root and root not in canonical.parents:
                        continue
                    size = canonical.stat().st_size
                except (OSError, RuntimeError, ValueError):
                    continue
                files_seen += 1
                if files_seen > self.limits.max_files:
                    self._budget_error("源码分析超过文件数量预算")
                if size > self.limits.max_file_bytes:
                    self._budget_error("源码分析文件超过单文件字节预算")
                total_bytes += size
                if total_bytes > self.limits.max_total_bytes:
                    self._budget_error("源码分析超过总字节预算")
                try:
                    raw = canonical.read_bytes()
                    raw.decode("utf-8")
                except (OSError, UnicodeDecodeError):
                    continue
                values.append((canonical.relative_to(root).as_posix(), raw))
        values.sort(key=lambda item: item[0].casefold())
        return tuple(values)

    @staticmethod
    def _budget_error(message: str) -> None:
        raise JiejianError(ErrorCode.APPLICATION_ANALYSIS_BUDGET, message)
