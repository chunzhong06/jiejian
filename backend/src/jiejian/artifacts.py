"""阶段 1 规范 JSON 产物的原子提交、哈希和报告读取。"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from .domain.stage1 import RunResult
from .errors import ErrorCode, JiejianError
from .inputs import ProjectBundle
from .redaction import redact

_RUN_ID = re.compile(r"^run_[0-9a-f]{32}$")


def persist_run(
    result: RunResult,
    bundle: ProjectBundle,
    plan: dict[str, Any],
    *,
    started_at: datetime,
    finished_at: datetime,
) -> None:
    final_dir = Path(result.artifact_dir)
    temporary_dir = final_dir.with_name(f".{final_dir.name}.tmp-{uuid4().hex}")
    try:
        temporary_dir.mkdir(parents=True, exist_ok=False)
        case_counts: dict[str, int] = {}
        for item in result.evidence:
            case_counts[item.verdict.value] = case_counts.get(item.verdict.value, 0) + 1
        report = redact(
            {
                "schema_version": "1",
                "run_id": result.run_id,
                "project_id": result.project_id,
                "engine_version": result.engine_version,
                "verdict": result.verdict.value,
                "reason_codes": result.reason_codes,
                "summary": {"total": len(result.evidence), "case_counts": case_counts},
                "evidence": [
                    item.model_dump(mode="json") for item in result.evidence
                ],
            }
        )
        _atomic_write_json(temporary_dir / "mutation-plan.json", plan)
        _atomic_write_json(
            temporary_dir / "events.json",
            {
                "schema_version": "1",
                "cases": [
                    {
                        "case_id": item.case_id,
                        "verdict": item.verdict.value,
                        "reason_codes": item.reason_codes,
                    }
                    for item in result.evidence
                ],
            },
        )
        for item in result.evidence:
            payload = item.model_dump(mode="json")
            _atomic_write_json(
                temporary_dir / "cases" / item.case_id / "evidence.json",
                payload,
            )
            _atomic_write_json(
                temporary_dir / "evidence" / f"{item.evidence_id}.json",
                payload,
            )
        _atomic_write_json(temporary_dir / "report" / "report.json", report)
        artifact_hashes = {
            str(path.relative_to(temporary_dir)).replace("\\", "/"): _hash_file(path)
            for path in sorted(temporary_dir.rglob("*.json"))
        }
        manifest = {
            "schema_version": "1",
            "run_id": result.run_id,
            "project_id": result.project_id,
            "contract_id": bundle.contract.id,
            "contract_version": bundle.contract.version,
            "contract_hash": _hash_json(bundle.contract.model_dump(mode="json")),
            "engine_version": result.engine_version,
            "configuration_hash": _hash_json(bundle.project.model_dump(mode="json")),
            "mutation_seed": plan["seed"],
            "target_snapshot": bundle.project.target.model_dump(mode="json"),
            "started_at": started_at.isoformat(),
            "finished_at": finished_at.isoformat(),
            "lifecycle": "COMPLETED",
            "verdict": result.verdict.value,
            "case_ids": [item.case_id for item in result.evidence],
            "evidence_ids": [item.evidence_id for item in result.evidence],
            "artifact_hashes": artifact_hashes,
        }
        _atomic_write_json(temporary_dir / "manifest.json", manifest)
        final_dir.parent.mkdir(parents=True, exist_ok=True)
        temporary_dir.replace(final_dir)
    except JiejianError:
        shutil.rmtree(temporary_dir, ignore_errors=True)
        raise
    except OSError as exc:
        shutil.rmtree(temporary_dir, ignore_errors=True)
        raise JiejianError(
            ErrorCode.ARTIFACT_WRITE,
            "运行产物写入失败",
            details={"reason": type(exc).__name__},
        ) from exc


def load_report(var_dir: Path, run_id: str) -> dict[str, Any]:
    if not _RUN_ID.fullmatch(run_id):
        raise JiejianError(ErrorCode.REPORT_NOT_FOUND, "运行 ID 格式无效")
    project_root = var_dir.resolve() / "projects"
    matches = list(project_root.glob(f"*/runs/{run_id}/report/report.json"))
    if len(matches) != 1:
        raise JiejianError(ErrorCode.REPORT_NOT_FOUND, "未找到唯一运行报告")
    report_path = matches[0]
    manifest_path = report_path.parents[1] / "manifest.json"
    try:
        document = json.loads(report_path.read_text(encoding="utf-8"))
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise JiejianError(ErrorCode.REPORT_NOT_FOUND, "运行报告不可读取") from exc
    if not isinstance(document, dict) or not isinstance(manifest, dict):
        raise JiejianError(ErrorCode.REPORT_NOT_FOUND, "运行报告结构无效")
    expected_hash = manifest.get("artifact_hashes", {}).get("report/report.json")
    if not isinstance(expected_hash, str) or not hmac.compare_digest(
        expected_hash, _hash_file(report_path)
    ):
        raise JiejianError(ErrorCode.REPORT_NOT_FOUND, "运行报告完整性校验失败")
    return redact(document)


def _atomic_write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp-{uuid4().hex}")
    encoded = json.dumps(
        redact(payload),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    try:
        temporary.write_text(f"{encoded}\n", encoding="utf-8")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _hash_json(payload: Any) -> str:
    encoded = json.dumps(
        redact(payload),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _hash_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()
