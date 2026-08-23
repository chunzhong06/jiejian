# =============================================================================
# Artifact Check JobHandler
#
# Worker 只负责读取固定请求、启动隔离扫描子进程和原子保存脱敏结果；
# API 进程没有产物递归扫描能力，扫描失败不会覆盖既有可信结果。
# =============================================================================

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import time
from pathlib import Path
from typing import Any
from uuid import uuid4

from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.infra.runtime.jobs.handlers import JobHandler
from product.backend.infra.runtime.process_environment import ProcessEnvironmentRole, spawn_python_module
from product.backend.infra.runtime.paths import RuntimePaths
from product.backend.infra.runtime.process_tree import release_process_tree, terminate_process_tree
from product.protocols.artifacts import ArtifactCheckRequest, ArtifactResultFile, ArtifactResultManifest, ArtifactScanResult, parse_artifact_check_request, parse_artifact_scan_result

_JOB_ID = r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$"


class ArtifactCheckJobHandler(JobHandler[ArtifactScanResult]):
    """在现有 Worker 组合根内启动一次独立、无网络的产物检查。"""

    def __init__(
        self,
        var_dir: Path,
        *,
        python_executable: str | None = None,
        popen: Any = subprocess.Popen,
        monotonic: Any = time.monotonic,
        sleep: Any = time.sleep,
    ) -> None:
        self.var_dir = var_dir.resolve()
        self._python = python_executable
        self._popen = popen
        self._monotonic = monotonic
        self._sleep = sleep

    def run_job(self, job_id: str) -> ArtifactScanResult:
        """在隔离子进程中执行有预算的只读扫描，并原子发布经校验的结果。"""

        if not re.fullmatch(_JOB_ID, job_id):
            raise JiejianError(ErrorCode.ARTIFACT_SCAN_FAILED, "产物检查任务标识无效")
        job_dir = (RuntimePaths(self.var_dir).artifact_checks / "jobs" / job_id).resolve()
        request_path = job_dir / "request.json"
        request = self._load_request(job_dir, request_path)
        output_path = job_dir / f".artifact-result.tmp-{uuid4().hex}.json"
        source_environment = dict(os.environ)
        source_environment.setdefault("JIEJIAN_VAR_DIR", str(self.var_dir))
        runtime_paths = RuntimePaths(self.var_dir).ensure_layout()
        try:
            process = spawn_python_module(
                source_environment,
                "product.backend.infra.artifacts.scanner_process",
                "--request",
                str(request_path),
                "--output",
                str(output_path),
                role=ProcessEnvironmentRole.ARTIFACT_SCAN,
                cwd=runtime_paths.temp,
                python_executable=self._python,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                close_fds=True,
                popen=self._popen,
            )
        except OSError:
            raise JiejianError(ErrorCode.ARTIFACT_SCAN_FAILED, "产物检查进程启动失败") from None
        # 父进程只额外提供固定收尾宽限，不能让子进程绕过请求中的扫描预算。
        deadline = self._monotonic() + request.budget.max_duration_us / 1_000_000 + 2
        while process.poll() is None and self._monotonic() < deadline:
            self._sleep(0.01)
        if process.poll() is None:
            terminate_process_tree(process, 2.0)
            raise JiejianError(ErrorCode.ARTIFACT_SCAN_FAILED, "产物检查超过时间预算")
        try:
            if process.returncode != 0:
                raise JiejianError(ErrorCode.ARTIFACT_SCAN_FAILED, "产物检查进程失败")
            result = parse_artifact_scan_result(output_path.read_bytes())
            if (
                result.project_id != request.project_id
                or result.artifact_id != request.artifact_id
                or result.ruleset_version != request.ruleset_version
                or result.run_id != request.run_id
            ):
                raise JiejianError(ErrorCode.ARTIFACT_SCAN_FAILED, "产物检查结果关联不匹配")
            self._publish(job_dir, result)
            return result
        except (OSError, ValueError):
            raise JiejianError(ErrorCode.ARTIFACT_SCAN_FAILED, "产物检查结果无效") from None
        finally:
            release_process_tree(process)
            output_path.unlink(missing_ok=True)

    def _load_request(self, job_dir: Path, request_path: Path) -> ArtifactCheckRequest:
        if not job_dir.is_relative_to(RuntimePaths(self.var_dir).artifact_checks / "jobs"):
            raise JiejianError(ErrorCode.ARTIFACT_SCAN_FAILED, "产物检查任务路径越界")
        try:
            request = parse_artifact_check_request(request_path.read_bytes())
        except (OSError, ValueError):
            raise JiejianError(ErrorCode.ARTIFACT_SCAN_FAILED, "产物检查请求无效") from None
        root = Path(request.artifact_root).resolve()
        manifest = Path(request.manifest_path).resolve()
        paths = RuntimePaths(self.var_dir)
        allowed_roots = (paths.projects, paths.jobs)
        if not any(root.is_relative_to(allowed) and manifest.is_relative_to(allowed) for allowed in allowed_roots):
            raise JiejianError(ErrorCode.ARTIFACT_SCAN_FAILED, "产物检查根目录未授权")
        if not manifest.is_relative_to(root.parent) or manifest.parent != root.parent:
            raise JiejianError(ErrorCode.ARTIFACT_SCAN_FAILED, "产物检查清单路径无效")
        return request

    def _publish(self, job_dir: Path, result: ArtifactScanResult) -> None:
        result_bytes = json.dumps(result.model_dump(mode="json"), ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        manifest = ArtifactResultManifest(
            artifact_id=result.artifact_id,
            project_id=result.project_id,
            result_sha256=hashlib.sha256(result_bytes).hexdigest(),
            input_manifest_sha256=result.manifest_sha256,
            files=(ArtifactResultFile(path="artifact-result.json", byte_count=len(result_bytes), sha256=hashlib.sha256(result_bytes).hexdigest()),),
        )
        final_dir = job_dir / "published"
        if final_dir.exists():
            existing = final_dir / "artifact-result.json"
            if existing.is_file() and existing.read_bytes() == result_bytes:
                return
            raise JiejianError(ErrorCode.ARTIFACT_SCAN_FAILED, "既有产物检查结果不可覆盖")
        temporary = job_dir / f".published.tmp-{uuid4().hex}"
        try:
            temporary.mkdir(parents=True, exist_ok=False)
            (temporary / "artifact-result.json").write_bytes(result_bytes)
            (temporary / "artifact-check-manifest.json").write_bytes(json.dumps(manifest.model_dump(mode="json"), ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8"))
            os.replace(temporary, final_dir)
        except OSError:
            raise JiejianError(ErrorCode.ARTIFACT_SCAN_FAILED, "产物检查结果发布失败") from None
        finally:
            if temporary.exists():
                import shutil
                shutil.rmtree(temporary, ignore_errors=True)
