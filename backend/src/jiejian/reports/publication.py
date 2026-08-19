# =============================================================================
# 统一报告独立 publication
#
# report publication 与 Run publication 分离；所有包文件固定、原子替换，
# 不同内容不得覆盖既有报告。
# =============================================================================

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import stat
from pathlib import Path
from uuid import uuid4

from ..errors import ErrorCode, JiejianError
from .models import ReportPackageFileV2, ReportPackageManifestV2, ReportV2
from .renderers import render_format

_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_REPARSE_POINT = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
_FORMATS = ("json", "html", "sarif", "junit")
_NAMES = {"json": "report.json", "html": "report.html", "sarif": "report.sarif.json", "junit": "report.junit.xml"}


class ReportPublication:
    def __init__(self, var_dir: Path) -> None:
        self._var_dir = var_dir.resolve()
        self._root = self._var_dir / "reports" / "runs"

    def publish(self, report: ReportV2) -> ReportPackageManifestV2:
        files = {name: render_format(report, fmt) for fmt, name in _NAMES.items()}
        manifest = ReportPackageManifestV2(
            report_id=report.report_id,
            run_id=report.run_id,
            gate_result_id=report.gate_result_id,
            report_sha256=hashlib.sha256(files["report.json"]).hexdigest(),
            files=tuple(
                ReportPackageFileV2(path=name, byte_count=len(raw), sha256=hashlib.sha256(raw).hexdigest())
                for name, raw in sorted(files.items())
            ),
        )
        final_dir = self._path(report.run_id, report.report_id)
        if os.path.lexists(final_dir):
            self._regular_directory(final_dir)
            if self._same_package(final_dir, files, manifest):
                return manifest
            raise JiejianError(ErrorCode.REPORT_PUBLISH_FAILED, "既有报告不可覆盖")
        temporary = final_dir.parent / f".{report.report_id}.tmp-{uuid4().hex}"
        try:
            temporary.mkdir(parents=True, exist_ok=False)
            for name, raw in files.items():
                (temporary / name).write_bytes(raw)
            (temporary / "report-manifest.json").write_bytes(
                json.dumps(manifest.model_dump(mode="json"), ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
            )
            final_dir.parent.mkdir(parents=True, exist_ok=True)
            self._check_parent_chain(final_dir)
            os.replace(temporary, final_dir)
        except (OSError, ValueError):
            raise JiejianError(ErrorCode.REPORT_PUBLISH_FAILED, "报告原子发布失败") from None
        finally:
            if temporary.exists():
                shutil.rmtree(temporary, ignore_errors=True)
        return manifest

    def read(self, run_id: str, report_id: str) -> ReportV2:
        final_dir = self._path(run_id, report_id)
        files, manifest = self._validated_files(final_dir, run_id, report_id)
        try:
            report = ReportV2.model_validate_json(files["report.json"], strict=True)
        except ValueError:
            raise JiejianError(ErrorCode.REPORT_INTEGRITY, "统一报告 JSON 无效") from None
        if report.run_id != run_id or report.report_id != report_id or report.gate_result_id != manifest.gate_result_id:
            raise JiejianError(ErrorCode.REPORT_INTEGRITY, "统一报告身份不一致")
        for fmt, name in _NAMES.items():
            if render_format(report, fmt) != files[name]:
                raise JiejianError(ErrorCode.REPORT_INTEGRITY, "统一报告派生工件不一致")
        return report

    def read_format(self, run_id: str, report_id: str, output_format: str) -> bytes:
        if output_format not in _FORMATS:
            raise JiejianError(ErrorCode.INPUT_INVALID, "报告格式无效")
        report = self.read(run_id, report_id)
        return render_format(report, output_format)

    def list(self, run_id: str) -> list[dict[str, str]]:
        if not re.fullmatch(r"^run_[0-9a-f]{32}$", run_id):
            raise JiejianError(ErrorCode.REPORT_NOT_FOUND, "运行标识无效")
        run_dir = self._root / run_id
        self._check_parent_chain(run_dir)
        if not os.path.lexists(run_dir):
            return []
        self._regular_directory(run_dir)
        output = []
        for entry in sorted(run_dir.iterdir(), key=lambda item: item.name):
            if not _SAFE_ID.fullmatch(entry.name):
                raise JiejianError(ErrorCode.REPORT_INTEGRITY, "报告目录标识无效")
            report = self.read(run_id, entry.name)
            output.append({"schema_version": "2", "report_id": report.report_id, "run_id": run_id, "gate_result_id": report.gate_result_id, "gate_decision": report.gate.decision, "canonical_sha256": report.canonical_sha256})
        return output

    def _validated_files(self, final_dir: Path, run_id: str, report_id: str) -> tuple[dict[str, bytes], ReportPackageManifestV2]:
        if not _SAFE_ID.fullmatch(run_id) or not _SAFE_ID.fullmatch(report_id):
            raise JiejianError(ErrorCode.REPORT_NOT_FOUND, "报告标识无效")
        self._regular_directory(final_dir)
        entries = list(final_dir.iterdir())
        if {item.name for item in entries} != {"report.json", "report.html", "report.sarif.json", "report.junit.xml", "report-manifest.json"}:
            raise JiejianError(ErrorCode.REPORT_INTEGRITY, "报告发布清单不完整")
        for item in entries:
            self._regular_file(item)
        try:
            manifest = ReportPackageManifestV2.model_validate_json((final_dir / "report-manifest.json").read_bytes(), strict=True)
            files = {name: (final_dir / name).read_bytes() for name in _NAMES.values()}
            expected = {item.path: item for item in manifest.files}
            if manifest.run_id != run_id or manifest.report_id != report_id or manifest.report_sha256 != hashlib.sha256(files["report.json"]).hexdigest():
                raise ValueError("report manifest identity")
            for name, raw in files.items():
                item = expected[name]
                if item.byte_count != len(raw) or item.sha256 != hashlib.sha256(raw).hexdigest():
                    raise ValueError("report package hash")
        except (OSError, ValueError, KeyError):
            raise JiejianError(ErrorCode.REPORT_INTEGRITY, "报告发布完整性校验失败") from None
        return files, manifest

    def _path(self, run_id: str, report_id: str) -> Path:
        target = self._root / run_id / report_id
        if not target.is_relative_to(self._root):
            raise JiejianError(ErrorCode.REPORT_NOT_FOUND, "报告路径越界")
        self._check_parent_chain(target)
        return target

    def _same_package(self, final_dir: Path, files: dict[str, bytes], manifest: ReportPackageManifestV2) -> bool:
        try:
            for name in (*_NAMES.values(), "report-manifest.json"):
                self._regular_file(final_dir / name)
            stored = ReportPackageManifestV2.model_validate_json((final_dir / "report-manifest.json").read_bytes(), strict=True)
            return stored == manifest and all((final_dir / name).read_bytes() == raw for name, raw in files.items())
        except (OSError, ValueError):
            return False

    @staticmethod
    def _regular_directory(path: Path) -> None:
        try:
            mode = os.lstat(path).st_mode
        except OSError:
            raise JiejianError(ErrorCode.REPORT_NOT_FOUND, "报告不存在") from None
        attributes = getattr(os.lstat(path), "st_file_attributes", 0)
        if stat.S_ISLNK(mode) or bool(attributes & _REPARSE_POINT) or not stat.S_ISDIR(mode):
            raise JiejianError(ErrorCode.REPORT_INTEGRITY, "报告目录不是普通目录")

    @staticmethod
    def _regular_file(path: Path) -> None:
        try:
            mode = os.lstat(path).st_mode
        except OSError:
            raise JiejianError(ErrorCode.REPORT_INTEGRITY, "报告文件不可读取") from None
        attributes = getattr(os.lstat(path), "st_file_attributes", 0)
        if stat.S_ISLNK(mode) or bool(attributes & _REPARSE_POINT) or not stat.S_ISREG(mode):
            raise JiejianError(ErrorCode.REPORT_INTEGRITY, "报告文件不是普通文件")

    def _check_parent_chain(self, target: Path) -> None:
        if not target.is_relative_to(self._var_dir):
            raise JiejianError(ErrorCode.REPORT_NOT_FOUND, "报告路径越界")
        self._regular_directory(self._var_dir)
        current = self._var_dir
        for part in target.relative_to(self._var_dir).parts:
            current = current / part
            if not os.path.lexists(current):
                break
            self._regular_directory(current)
