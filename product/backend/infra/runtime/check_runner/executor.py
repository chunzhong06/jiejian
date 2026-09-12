# 独立 Runner 重验冻结资产后执行，并把完整根文档写入一次性 staging；不访问数据库。
from __future__ import annotations

import os
import logging
import time
from pathlib import Path

from product.backend.core.errors import JiejianError
from product.backend.infra.artifacts.check_packages import read_check_bytes, reject_check_links
from product.backend.infra.execution.check_executor import CheckExecutor
from product.backend.infra.execution.web.check_runtime import check_secret_names
from product.backend.infra.runtime.jobs.check_requests import CheckRequestStore
from product.backend.infra.runtime.paths import RuntimePaths
from product.protocols.check_result import CheckRunnerInput, CheckRunnerProgress, canonical_check_document, parse_check_document
from product.protocols.check_runtime import canonical_check_runtime_bytes, check_payload_contains_secret
from product.protocols.execution_v3 import canonical_execution_request_v3_bytes


def _write_new(path: Path, raw: bytes) -> None:
    with path.open("xb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())


def execute_check_attempt(input_path: Path, staging: Path, *, environ) -> int:
    """路径、根协议或资产不一致在任何 TARGET 前退出；再次运行同一 staging 也会拒绝。"""
    try:
        runner_input = parse_check_document(read_check_bytes(input_path), CheckRunnerInput)
        attempt = input_path.parent
        if len(input_path.parents) < 6:
            return 64
        var_dir = input_path.parents[5]
        expected = RuntimePaths(var_dir).jobs / runner_input.job_id / "attempts" / f"{runner_input.attempt}-{runner_input.fencing_token}"
        if input_path != expected / "input.json" or staging != expected / "staging":
            return 64
        reject_check_links(RuntimePaths(var_dir).jobs, input_path)
        reject_check_links(RuntimePaths(var_dir).jobs, staging)
        store = CheckRequestStore(var_dir)
        request = store.load(runner_input.job_id, expected_hash=runner_input.request_hash)
        bundle = store.load_bundle(runner_input.job_id, expected_hash=runner_input.config_hash)
        names = check_secret_names(bundle)
        if any(not environ.get(name) for name in names):
            return 64
        known = tuple(environ[name] for name in names)
        if any(check_payload_contains_secret(item.model_dump(mode="json"), known) for item in (request, bundle, runner_input)):
            return 64
        staging.mkdir(exist_ok=False)
        (staging / "evidence").mkdir()
        _write_new(staging / "request.json", canonical_execution_request_v3_bytes(request))
        _write_new(staging / "runtime.json", canonical_check_runtime_bytes(bundle))
        def progress(phase, completed, planned):
            try:
                value = CheckRunnerProgress(run_id=runner_input.run_id, job_id=runner_input.job_id,
                    attempt=runner_input.attempt, fencing_token=runner_input.fencing_token,
                    request_hash=runner_input.request_hash, phase=phase, completed_cases=completed,
                    planned_cases=planned, observed_at_us=time.time_ns() // 1000)
                temporary, destination = attempt / "progress.tmp", attempt / "progress.json"
                reject_check_links(attempt, temporary)
                reject_check_links(attempt, destination)
                with temporary.open("wb") as stream:
                    stream.write(canonical_check_document(value))
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(temporary, destination)
            except (OSError, JiejianError, ValueError):
                # 展示进度写入失败不能导致重放目标，也不能覆盖既有业务事实。
                logging.getLogger(__name__).warning("CHECK_PROGRESS_UNAVAILABLE")
        output = CheckExecutor(request, bundle, runner_input, environ=environ, attempt_dir=attempt,
            cancellation_requested=lambda: (attempt / "cancel.requested").exists(),
            progress=progress,
            reserved_origins=(environ["JIEJIAN_CONTROL_ORIGIN"],) if environ.get("JIEJIAN_CONTROL_ORIGIN") else ()).execute()
        for evidence in output.evidence:
            _write_new(staging / "evidence" / f"{evidence.evidence_id}.json", canonical_check_document(evidence, known_secrets=known))
        # 最后写 result；缺少完整 result 的 staging 永远不进入发布路径。
        _write_new(staging / "result.json", canonical_check_document(output.result, known_secrets=known))
        return 0
    except (ValueError, OSError, JiejianError):
        return 64
