# 当前检查文件包的受限路径、完整集合和关联验证；只读发布事实，不执行目标或重新裁决。
from __future__ import annotations

import hashlib
import os
import re
import stat
from dataclasses import dataclass
from pathlib import Path

from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.infra.artifacts.check_validation import validate_check_inputs
from product.backend.infra.runtime.paths import RuntimePaths
from product.protocols.check_publication import CheckPublicationManifest, CheckPublishedFile
from product.protocols.check_result import CheckEvidence, CheckRunnerResult, check_request_marker, parse_check_document
from product.protocols.check_runtime import CheckRuntimeBundle, parse_check_runtime
from product.protocols.execution_v3 import PersistedExecutionRequestV3, parse_execution_request_v3

MANIFEST_NAME = "publication-manifest.json"
MAX_FILE_BYTES = 1_048_576
MAX_FILES = 4097
MAX_PACKAGE_BYTES = 268_435_456


@dataclass(frozen=True)
class CheckPackage:
    directory: Path
    request: PersistedExecutionRequestV3
    bundle: CheckRuntimeBundle
    result: CheckRunnerResult
    evidence: tuple[CheckEvidence, ...]
    files: tuple[CheckPublishedFile, ...]
    manifest: CheckPublicationManifest | None = None


def check_final_directory(var_dir: Path, project_id: str, run_id: str) -> Path:
    if re.fullmatch(r"[a-z][a-z0-9_-]{0,63}", project_id) is None or re.fullmatch(r"run_[0-9a-f]{32}", run_id) is None:
        raise JiejianError(ErrorCode.ARTIFACT_PUBLISH, "最终运行目录越界")
    root = RuntimePaths(var_dir).projects
    path = root / project_id / "runs" / run_id
    reject_check_links(root, path)
    return path


def reject_check_links(root: Path, path: Path) -> None:
    root, path = Path(os.path.abspath(root)), Path(os.path.abspath(path))
    if not path.is_relative_to(root):
        raise JiejianError(ErrorCode.ARTIFACT_MANIFEST, "工件路径越界")
    for item in (path, *path.parents):
        if item.exists() or item.is_symlink():
            info = item.lstat()
            if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT:
                raise JiejianError(ErrorCode.ARTIFACT_MANIFEST, "工件路径越界")
        if item == root:
            break


def read_check_bytes(path: Path, *, known_secrets=()) -> bytes:
    try:
        reject_check_links(path.parent, path)
        if not path.is_file() or path.stat().st_size > MAX_FILE_BYTES:
            raise ValueError("invalid file")
        with path.open("rb") as stream:
            raw = stream.read(MAX_FILE_BYTES + 1)
        if len(raw) > MAX_FILE_BYTES or any(secret and secret.encode() in raw for secret in known_secrets):
            raise ValueError("unsafe file")
        return raw
    except (ValueError, OSError):
        raise JiejianError(ErrorCode.ARTIFACT_MANIFEST, "工件内容校验失败") from None


def validate_check_package(directory: Path, *, published=False, known_secrets=()) -> CheckPackage:
    """校验所有根、文件字节与完整 Case/Evidence 集合；不接受额外文件或其他尝试结果。"""
    try:
        reject_check_links(directory.parent, directory)
        raw_files = {}
        total_bytes = 0
        for parent, directories, names in os.walk(directory, followlinks=False):
            for name in directories:
                child = Path(parent) / name
                reject_check_links(directory, child)
                if child.relative_to(directory).as_posix() != "evidence":
                    raise ValueError("unexpected package directory")
            for name in names:
                child = Path(parent) / name
                relative = child.relative_to(directory).as_posix()
                if relative != MANIFEST_NAME:
                    CheckPublishedFile(path=relative, sha256="0" * 64, byte_count=1)
                elif not published:
                    raise ValueError("unexpected publication manifest")
                reject_check_links(directory, child)
                raw = read_check_bytes(child, known_secrets=known_secrets)
                total_bytes += len(raw)
                if len(raw_files) >= MAX_FILES + int(published) or total_bytes > MAX_PACKAGE_BYTES:
                    raise ValueError("package budget exceeded")
                raw_files[relative] = raw
        result = parse_check_document(raw_files["result.json"], CheckRunnerResult, known_secrets=known_secrets)
        request = parse_execution_request_v3(raw_files["request.json"])
        bundle = parse_check_runtime(raw_files["runtime.json"])
        validate_check_inputs(request, bundle)
        if (result.request_hash, result.config_hash) != (
            hashlib.sha256(raw_files["request.json"]).hexdigest(), hashlib.sha256(raw_files["runtime.json"]).hexdigest()
        ):
            raise ValueError("result request association")
        cases = {case.case_id: (action, case) for action in request.actions for case in action.cases}
        if set(cases) != {item.case_id for item in result.case_results}:
            raise ValueError("result case coverage")
        evidence = {}
        for path, raw in raw_files.items():
            if not path.startswith("evidence/"):
                continue
            item = parse_check_document(raw, CheckEvidence, known_secrets=known_secrets)
            if path != f"evidence/{item.evidence_id}.json" or item.evidence_id in evidence:
                raise ValueError("evidence content path")
            if (item.run_id, item.job_id, item.attempt, item.request_hash, item.config_hash) != (
                result.run_id, result.job_id, result.attempt, result.request_hash, result.config_hash
            ):
                raise ValueError("evidence result association")
            action, case = cases[item.case.case_id]
            if item.case != case or (item.action_id, item.action_revision) != (action.action_id, action.action_revision):
                raise ValueError("evidence frozen case association")
            configured = next(config for config in bundle.actions if config.action_id == action.action_id)
            proof_configs = {proof.binding_fingerprint: proof for proof in configured.proofs}
            case_proofs = {proof.proof_fingerprint: proof for proof in case.proof_requirements}
            for observation in item.observations:
                proof = proof_configs[case_proofs[observation.proof_fingerprint].binding_fingerprint]
                expected_observer = proof.observer_id or "recorded-" + proof.binding_fingerprint[:32]
                sources = {expected_observer: case_proofs[observation.proof_fingerprint].level,
                    **{source.observer_id: source.level for source in proof.auxiliary_sources}}
                if sources.get(observation.observer_id) != observation.level or not (
                    result.started_at_us <= observation.window_start_us <= observation.window_end_us <= result.completed_at_us
                ):
                    raise ValueError("observation source or window association")
                if observation.correlated and check_request_marker(result.run_id, result.job_id, result.attempt, case.case_id) not in observation.correlation_refs:
                    raise ValueError("observation run marker association")
            evidence[item.evidence_id] = item
        referenced = []
        for item in result.case_results:
            action, case = cases[item.case_id]
            if item.action_id != action.action_id or not item.evidence_ids:
                raise ValueError("case result association")
            for evidence_id in item.evidence_ids:
                document = evidence[evidence_id]
                if document.case != case or document.outcome != item.outcome:
                    raise ValueError("case evidence outcome association")
                referenced.append(evidence_id)
        if len(referenced) != len(set(referenced)) or set(referenced) != set(evidence):
            raise ValueError("evidence coverage")
        files = tuple(CheckPublishedFile(path=name, sha256=hashlib.sha256(raw).hexdigest(), byte_count=len(raw))
            for name, raw in sorted(raw_files.items()) if name != MANIFEST_NAME)
        manifest = None
        if published:
            manifest = parse_check_document(raw_files[MANIFEST_NAME], CheckPublicationManifest, known_secrets=known_secrets)
            if manifest.files != files or (manifest.project_id, manifest.run_id, manifest.job_id, manifest.attempt,
                manifest.lease_owner, manifest.fencing_token, manifest.request_hash, manifest.config_hash) != (
                request.project_id, result.run_id, result.job_id, result.attempt, result.lease_owner,
                result.fencing_token, result.request_hash, result.config_hash
            ):
                raise ValueError("publication manifest association")
        return CheckPackage(directory, request, bundle, result, tuple(evidence[key] for key in sorted(evidence)), files, manifest)
    except (ValueError, OSError, KeyError, TypeError):
        raise JiejianError(ErrorCode.ARTIFACT_MANIFEST, "工件内容校验失败") from None
