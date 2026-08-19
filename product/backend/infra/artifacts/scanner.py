# =============================================================================
# Artifact Check 确定性扫描器
#
# 只按 publication manifest 枚举文件；不执行内容、不联网、不解压、不遍历
# manifest 外路径。预算耗尽通过 INCONCLUSIVE 返回，绝不生成 SAFE。
# =============================================================================

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from product.backend.core.errors import JiejianError
from product.backend.infra.artifacts.run_packages import PublicationManifest
from product.protocols.artifacts import ArtifactCheckRequest, ArtifactEvidence, ArtifactFinding, ArtifactScanResult, ArtifactScanStatus, ArtifactVerdict, RULESET_VERSION, stable_artifact_fingerprint, stable_artifact_ids

_ASSIGNMENT = re.compile(
    r"(?i)\b(api[_-]?key|access[_-]?token|auth[_-]?token|client[_-]?secret|secret|password|private[_-]?key)\b\s*[:=]\s*['\"]?([A-Za-z0-9_./+=-]{12,})"
)
_PRIVATE_KEY = re.compile(r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----")
_PREFIX_SECRET = re.compile(r"\b(?:sk-[A-Za-z0-9]{20,}|gh[pousr]_[A-Za-z0-9]{20,}|xox[baprs]-[A-Za-z0-9-]{20,}|AKIA[0-9A-Z]{16})\b")
_FRONTEND_SECRET = re.compile(r"(?i)\b(?:DATABASE_URL|DB_PASSWORD|AWS_SECRET_ACCESS_KEY|JWT_SECRET|PRIVATE_KEY)\b\s*[:=]")
_SOURCE_MAPPING = re.compile(r"(?i)sourceMappingURL\s*=")
_FRONTEND_SUFFIXES = {".js", ".jsx", ".ts", ".tsx", ".html", ".css", ".mjs", ".cjs"}
_LOCK_NAMES = {"package-lock.json", "npm-shrinkwrap.json", "requirements.txt", "poetry.lock", "pipfile.lock"}


class ArtifactScanFailure(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def scan_artifact(request: ArtifactCheckRequest, *, clock: Callable[[], float] = time.monotonic) -> ArtifactScanResult:
    """按已发布清单进行确定性检查；预算或完整性失败返回不可放行结果。"""

    root = Path(request.artifact_root)
    manifest_path = Path(request.manifest_path)
    started = clock()
    try:
        manifest_raw, manifest = _load_manifest(root, manifest_path)
        if manifest.project_id != request.project_id or (request.run_id is not None and manifest.run_id != request.run_id):
            raise ArtifactScanFailure("MANIFEST_ID_MISMATCH")
        manifest_hash = hashlib.sha256(manifest_raw).hexdigest()
        entries = _manifest_entries(root, manifest)
        if len(entries) > request.budget.max_files:
            raise ArtifactScanFailure("FILE_COUNT_BUDGET")
        findings: list[ArtifactFinding] = []
        evidence: list[ArtifactEvidence] = []
        total_bytes = 0
        # 每个文件先重验清单绑定，再读取受预算限制的内容，避免 TOCTOU 被当作可信证据。
        for relative, expected_size, expected_hash in entries:
            _check_time(started, request, clock)
            path = root / relative
            metadata = _regular_file(path)
            if metadata.st_size != expected_size or _hash_file(path) != expected_hash:
                raise ArtifactScanFailure("MANIFEST_CONTENT_MISMATCH")
            if metadata.st_size > request.budget.max_file_bytes:
                raise ArtifactScanFailure("FILE_SIZE_BUDGET")
            total_bytes += metadata.st_size
            if total_bytes > request.budget.max_total_bytes:
                raise ArtifactScanFailure("TOTAL_SIZE_BUDGET")
            raw = path.read_bytes()
            if _is_zip_magic(raw):
                raise ArtifactScanFailure("COMPRESSED_LAYER_BUDGET")
            _scan_one_file(
                request,
                relative,
                raw,
                manifest_hash,
                findings,
                evidence,
            )
            if len(findings) > request.budget.max_results:
                raise ArtifactScanFailure("RESULT_COUNT_BUDGET")
        _reject_extra_files(root, {relative for relative, _, _ in entries})
        _scan_dependencies(request, root, entries, manifest_hash, findings, evidence)
        if len(findings) > request.budget.max_results:
            raise ArtifactScanFailure("RESULT_COUNT_BUDGET")
        return _result(request, manifest_hash, len(entries), total_bytes, findings, evidence)
    except ArtifactScanFailure as exc:
        manifest_hash = _safe_manifest_hash(manifest_path)
        return ArtifactScanResult(
            project_id=request.project_id,
            artifact_id=request.artifact_id,
            run_id=request.run_id,
            status=ArtifactScanStatus.INCONCLUSIVE,
            verdict=ArtifactVerdict.INCONCLUSIVE,
            error_code=exc.code,
            manifest_sha256=manifest_hash,
            scanned_file_count=0,
            scanned_byte_count=0,
        )
    except (OSError, ValueError, TypeError, JiejianError):
        return ArtifactScanResult(
            project_id=request.project_id,
            artifact_id=request.artifact_id,
            run_id=request.run_id,
            status=ArtifactScanStatus.INCONCLUSIVE,
            verdict=ArtifactVerdict.INCONCLUSIVE,
            error_code="SCAN_FAILED",
            manifest_sha256=_safe_manifest_hash(manifest_path),
            scanned_file_count=0,
            scanned_byte_count=0,
        )


def _load_manifest(root: Path, manifest_path: Path) -> tuple[bytes, PublicationManifest]:
    if not root.is_absolute() or not manifest_path.is_absolute():
        raise ArtifactScanFailure("PATH_INVALID")
    _reject_reparse_chain(root)
    _reject_reparse_chain(manifest_path)
    if manifest_path.parent.resolve() != root.parent.resolve():
        raise ArtifactScanFailure("MANIFEST_OUTSIDE_ROOT")
    _regular_file(manifest_path)
    raw = manifest_path.read_bytes()
    try:
        manifest = PublicationManifest.model_validate_json(raw, strict=True)
    except Exception:
        raise ArtifactScanFailure("MANIFEST_INVALID") from None
    return raw, manifest


def _manifest_entries(root: Path, manifest: PublicationManifest) -> tuple[tuple[str, int, str], ...]:
    entries: list[tuple[str, int, str]] = []
    folded: set[str] = set()
    for item in manifest.files:
        if not item.path.casefold().startswith("artifacts/"):
            continue
        relative = item.path[len("artifacts/"):]
        if not relative or relative.startswith("/") or ".." in relative.split("/"):
            raise ArtifactScanFailure("PATH_ESCAPE")
        if relative.casefold() in folded:
            raise ArtifactScanFailure("PATH_ALIAS")
        folded.add(relative.casefold())
        entries.append((relative, item.byte_count, item.sha256))
    return tuple(sorted(entries))


def _reject_extra_files(root: Path, expected: set[str]) -> None:
    if _is_reparse(root):
        raise ArtifactScanFailure("REPARSE_ROOT")
    actual: set[str] = set()
    for current, directories, filenames in os.walk(root, followlinks=False):
        current_path = Path(current)
        for name in directories:
            if _is_reparse(current_path / name):
                raise ArtifactScanFailure("REPARSE_PATH")
        for name in filenames:
            path = current_path / name
            _regular_file(path)
            actual.add(path.relative_to(root).as_posix())
    if {item.casefold() for item in actual} != {item.casefold() for item in expected}:
        raise ArtifactScanFailure("MANIFEST_FILE_SET_MISMATCH")


def _scan_one_file(
    request: ArtifactCheckRequest,
    relative: str,
    raw: bytes,
    manifest_hash: str,
    findings: list[ArtifactFinding],
    evidence: list[ArtifactEvidence],
) -> None:
    suffix = Path(relative).suffix.casefold()
    name = Path(relative).name.casefold()
    text = raw.decode("utf-8", errors="replace")
    if _forbidden_name(name):
        _add_finding(request, relative, "FORBIDDEN_FILE", "FORBIDDEN_PUBLISH_FILE", "critical", manifest_hash, None, "file", findings, evidence)
    if suffix == ".map" or (suffix in _FRONTEND_SUFFIXES and _SOURCE_MAPPING.search(text)):
        _add_finding(request, relative, "SOURCE_MAP", "SOURCE_MAP_EXPOSED", "medium", manifest_hash, None, "source-map", findings, evidence)
    frontend_match = _FRONTEND_SECRET.search(text) if suffix in _FRONTEND_SUFFIXES else None
    if frontend_match:
        _add_finding(request, relative, "FRONTEND_SERVER_SECRET", "FRONTEND_SERVER_SECRET", "critical", manifest_hash, _line_number(text, frontend_match.start()), "frontend-secret", findings, evidence)
    for match in (*_PRIVATE_KEY.finditer(text), *_PREFIX_SECRET.finditer(text), *_ASSIGNMENT.finditer(text)):
        line = _line_number(text, match.start())
        kind = "secret-candidate"
        _add_finding(request, relative, "SECRET_CANDIDATE", "SECRET_CANDIDATE", "critical", manifest_hash, line, kind, findings, evidence)


def _scan_dependencies(
    request: ArtifactCheckRequest,
    root: Path,
    entries: tuple[tuple[str, int, str], ...],
    manifest_hash: str,
    findings: list[ArtifactFinding],
    evidence: list[ArtifactEvidence],
) -> None:
    rules = _load_ruleset()
    minimums = rules["dependency_minimums"]
    for relative, _, _ in entries:
        if Path(relative).name.casefold() not in _LOCK_NAMES:
            continue
        text = (root / relative).read_text(encoding="utf-8", errors="replace")
        for name, version in _dependency_versions(relative, text):
            minimum = minimums.get(name.casefold())
            if minimum is not None and _version_tuple(version) < _version_tuple(minimum):
                _add_finding(request, relative, "DEPENDENCY_VERSION", "DEPENDENCY_VERSION_MINIMUM", "high", manifest_hash, None, f"dependency:{name}:{version}", findings, evidence)


def _dependency_versions(relative: str, text: str) -> tuple[tuple[str, str], ...]:
    name = Path(relative).name.casefold()
    if name in {"package-lock.json", "npm-shrinkwrap.json"}:
        try:
            document = json.loads(text)
        except json.JSONDecodeError:
            return ()
        values: list[tuple[str, str]] = []
        for key, value in document.get("packages", {}).items() if isinstance(document, dict) else ():
            package = key.rsplit("node_modules/", 1)[-1]
            if isinstance(value, dict) and isinstance(value.get("version"), str):
                values.append((package, value["version"]))
        return tuple(values)
    if name == "requirements.txt":
        return tuple((match.group(1), match.group(2)) for match in re.finditer(r"(?im)^\s*([A-Za-z0-9_.-]+)\s*==\s*([0-9]+(?:\.[0-9]+){1,3})", text))
    return tuple((match.group(1), match.group(2)) for match in re.finditer(r'(?im)^\s*name\s*=\s*["\']([^"\']+)["\']\s*\n\s*version\s*=\s*["\']([^"\']+)["\']', text))


def _add_finding(
    request: ArtifactCheckRequest,
    path: str,
    category: str,
    rule_id: str,
    severity: str,
    manifest_hash: str,
    line: int | None,
    kind: str,
    findings: list[ArtifactFinding],
    evidence: list[ArtifactEvidence],
) -> None:
    fingerprint = stable_artifact_fingerprint(rule_id, path, line, kind)
    finding_id, evidence_id = stable_artifact_ids(request.artifact_id, rule_id, path, fingerprint)
    if evidence_id in {item.evidence_id for item in evidence}:
        return
    message = {
        "SECRET_CANDIDATE": "检测到秘密候选",
        "FORBIDDEN_FILE": "检测到禁止发布文件",
        "SOURCE_MAP": "检测到 Source Map",
        "FRONTEND_SERVER_SECRET": "前端产物包含明显服务端秘密",
        "DEPENDENCY_VERSION": "依赖版本低于固定本地规则集要求",
    }[category]
    evidence.append(ArtifactEvidence(evidence_id=evidence_id, artifact_id=request.artifact_id, manifest_sha256=manifest_hash, rule_id=rule_id, path=path, fingerprint=fingerprint, line=line, reason_code=rule_id))
    findings.append(ArtifactFinding(finding_id=finding_id, artifact_id=request.artifact_id, rule_id=rule_id, category=category, severity=severity, path=path, evidence_id=evidence_id, message=message))


def _result(request: ArtifactCheckRequest, manifest_hash: str, file_count: int, total_bytes: int, findings: list[ArtifactFinding], evidence: list[ArtifactEvidence]) -> ArtifactScanResult:
    return ArtifactScanResult(
        project_id=request.project_id,
        artifact_id=request.artifact_id,
        run_id=request.run_id,
        status=ArtifactScanStatus.COMPLETE,
        verdict=ArtifactVerdict.VULNERABLE if findings else ArtifactVerdict.SAFE,
        manifest_sha256=manifest_hash,
        scanned_file_count=file_count,
        scanned_byte_count=total_bytes,
        findings=tuple(findings),
        evidence=tuple(evidence),
    )


def _forbidden_name(name: str) -> bool:
    return (
        name == ".env"
        or name.startswith(".env.")
        or name.endswith((".pem", ".key", ".p12", ".pfx"))
        or name in {"debug.log", "debug.config.json", "development.config.json", "dev.config.json", "npm-debug.log", "yarn-debug.log", ".ds_store"}
        or ("debug" in name and name.endswith((".json", ".yaml", ".yml", ".js")))
    )


def _line_number(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def _regular_file(path: Path) -> os.stat_result:
    try:
        if _is_reparse(path):
            raise ArtifactScanFailure("REPARSE_PATH")
        metadata = os.lstat(path)
    except OSError:
        raise ArtifactScanFailure("PATH_UNREADABLE") from None
    if not stat.S_ISREG(metadata.st_mode):
        raise ArtifactScanFailure("SPECIAL_FILE")
    return metadata


def _is_reparse(path: Path) -> bool:
    metadata = os.lstat(path)
    attributes = getattr(metadata, "st_file_attributes", 0)
    return stat.S_ISLNK(metadata.st_mode) or bool(attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400))


def _hash_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _safe_manifest_hash(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return "0" * 64


def _check_time(started: float, request: ArtifactCheckRequest, clock: Callable[[], float]) -> None:
    if (clock() - started) * 1_000_000 > request.budget.max_duration_us:
        raise ArtifactScanFailure("TIME_BUDGET")


def _reject_reparse_chain(path: Path) -> None:
    current = path
    while current != current.parent:
        if current.exists() and _is_reparse(current):
            raise ArtifactScanFailure("REPARSE_PATH")
        current = current.parent


def _load_ruleset() -> dict[str, Any]:
    path = Path(__file__).with_name("artifact_ruleset.json")
    document = json.loads(path.read_text(encoding="utf-8"))
    if document.get("ruleset_version") != RULESET_VERSION:
        raise ArtifactScanFailure("RULESET_INVALID")
    return document


def _version_tuple(value: str) -> tuple[int, ...]:
    match = re.match(r"^[v=]?([0-9]+(?:\.[0-9]+){0,3})", value.strip())
    if match is None:
        return (0,)
    return tuple(int(item) for item in match.group(1).split("."))


def _is_zip_magic(raw: bytes) -> bool:
    """只识别 ZIP 头，不解析或解压归档内容。"""

    return raw[:4] in {b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08"}
