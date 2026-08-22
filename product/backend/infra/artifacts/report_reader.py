# =============================================================================
# 已发布 Artifact Result 只读边界
#
# 只枚举固定 artifact-checks/jobs/<safe-id>/published 路径；请求、结果和
# artifact-check-manifest.json 三者必须相互绑定，任何损坏都拒绝报告生成。
# =============================================================================

from __future__ import annotations

import hashlib
import os
import re
import stat
from dataclasses import dataclass
from pathlib import Path

from product.protocols.artifacts import ArtifactCheckRequest, ArtifactResultManifest, ArtifactScanResult
from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.infra.runtime.paths import RuntimePaths

_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_REPARSE_POINT = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)


@dataclass(frozen=True, slots=True)
class PublishedArtifactResult:
    job_id: str
    request: ArtifactCheckRequest
    result: ArtifactScanResult | None


class ArtifactResultReader:
    """读取已发布产物检查结果，不扫描产物根目录也不执行工件。"""

    def __init__(self, var_dir: Path) -> None:
        self._var_dir = var_dir.resolve()

    def for_run(self, run_id: str, project_id: str) -> tuple[PublishedArtifactResult, ...]:
        """枚举并验证绑定到指定 Run/Project 的已发布产物检查结果。"""

        jobs_root = RuntimePaths(self._var_dir).artifact_checks / "jobs"
        self._check_parent_chain(jobs_root)
        if not os.path.lexists(jobs_root):
            return ()
        self._regular_directory(jobs_root)
        results: list[PublishedArtifactResult] = []
        # 任一目录结构异常都中止读取，不能跳过损坏项后生成看似完整的报告。
        for entry in sorted(jobs_root.iterdir(), key=lambda item: item.name):
            if not _SAFE_ID.fullmatch(entry.name):
                raise JiejianError(ErrorCode.REPORT_INTEGRITY, "产物检查任务目录标识无效")
            self._regular_directory(entry)
            request_path = entry / "request.json"
            if not os.path.lexists(request_path):
                continue
            self._regular_file(request_path)
            request = self._parse_request(request_path)
            if request.run_id != run_id:
                continue
            if request.project_id != project_id:
                raise JiejianError(ErrorCode.REPORT_INTEGRITY, "产物检查项目关联不一致")
            published = entry / "published"
            if not os.path.lexists(published):
                results.append(PublishedArtifactResult(entry.name, request, None))
                continue
            results.append(PublishedArtifactResult(entry.name, request, self._read_published(published, request, run_id, project_id)))
        return tuple(results)

    def _parse_request(self, path: Path) -> ArtifactCheckRequest:
        try:
            return ArtifactCheckRequest.model_validate_json(path.read_bytes(), strict=True)
        except (OSError, ValueError):
            raise JiejianError(ErrorCode.REPORT_INTEGRITY, "产物检查请求完整性无效") from None

    def _read_published(
        self,
        published: Path,
        request: ArtifactCheckRequest,
        run_id: str,
        project_id: str,
    ) -> ArtifactScanResult:
        self._regular_directory(published)
        entries = list(published.iterdir())
        if {item.name for item in entries} != {"artifact-result.json", "artifact-check-manifest.json"}:
            raise JiejianError(ErrorCode.REPORT_INTEGRITY, "产物检查发布清单不完整")
        for item in entries:
            self._regular_file(item)
        try:
            manifest = ArtifactResultManifest.model_validate_json(
                (published / "artifact-check-manifest.json").read_bytes(), strict=True
            )
            result_raw = (published / "artifact-result.json").read_bytes()
            result_hash = hashlib.sha256(result_raw).hexdigest()
            file_entry = manifest.files[0]
            if (
                file_entry.path != "artifact-result.json"
                or len(result_raw) != file_entry.byte_count
                or result_hash != file_entry.sha256
                or result_hash != manifest.result_sha256
            ):
                raise ValueError("artifact result hash")
            result = ArtifactScanResult.model_validate_json(result_raw, strict=True)
        except (OSError, ValueError):
            raise JiejianError(ErrorCode.REPORT_INTEGRITY, "产物检查发布内容无效") from None
        if (
            manifest.artifact_id != result.artifact_id
            or manifest.project_id != result.project_id
            or manifest.input_manifest_sha256 != result.manifest_sha256
            or result.run_id != run_id
            or result.project_id != project_id
            or request.artifact_id != result.artifact_id
            or request.ruleset_version != result.ruleset_version
        ):
            raise JiejianError(ErrorCode.REPORT_INTEGRITY, "产物检查发布关联不一致")
        return result

    @staticmethod
    def _regular_directory(path: Path) -> None:
        try:
            mode = os.lstat(path).st_mode
        except OSError:
            raise JiejianError(ErrorCode.REPORT_INTEGRITY, "产物检查目录不可读取") from None
        attributes = getattr(os.lstat(path), "st_file_attributes", 0)
        if stat.S_ISLNK(mode) or bool(attributes & _REPARSE_POINT) or not stat.S_ISDIR(mode):
            raise JiejianError(ErrorCode.REPORT_INTEGRITY, "产物检查目录不是普通目录")

    @staticmethod
    def _regular_file(path: Path) -> None:
        try:
            mode = os.lstat(path).st_mode
        except OSError:
            raise JiejianError(ErrorCode.REPORT_INTEGRITY, "产物检查文件不可读取") from None
        attributes = getattr(os.lstat(path), "st_file_attributes", 0)
        if stat.S_ISLNK(mode) or bool(attributes & _REPARSE_POINT) or not stat.S_ISREG(mode):
            raise JiejianError(ErrorCode.REPORT_INTEGRITY, "产物检查文件不是普通文件")

    def _check_parent_chain(self, target: Path) -> None:
        if not target.is_relative_to(self._var_dir):
            raise JiejianError(ErrorCode.REPORT_INTEGRITY, "产物检查路径越界")
        self._regular_directory(self._var_dir)
        current = self._var_dir
        for part in target.relative_to(self._var_dir).parts:
            current = current / part
            if not os.path.lexists(current):
                break
            self._regular_directory(current)
