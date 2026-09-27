# 净化并发布跨应用聚合统计，不泄露 private oracle 答案。
from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path
from typing import Mapping
from uuid import uuid4
from scripts.dev.sample_test.oracle import OracleEvaluation
from scripts.dev.sample_test.registry import PublicValidationCase
import scripts.dev.sample_test.validation.models as sample_validation_models


def _write_public_summary(
    root: Path,
    audit_dir: Path,
    repetitions: int,
    cases: tuple[PublicValidationCase, ...],
    results: list[dict[str, object]],
    evaluations: list[OracleEvaluation],
    *,
    status: str,
) -> dict[str, object]:
    revision, dirty = _repository_source(root)
    payload: dict[str, object] = {
        "schema_version": "1",
        "generated_at_us": time.time_ns() // 1_000,
        "suite": "competition" if repetitions == 3 else "validation",
        "status": status,
        "repetitions": repetitions,
        "case_count": len(cases),
        "case_run_count": len(results),
        "applications": sorted({item.application_id for item in cases}),
        "matrix": {
            "application_count": len({item.application_id for item in cases}),
            "mode_count": len({item.mode for item in cases}),
            "state_count": len(
                {
                    (
                        str(item.state_selector.get("implementation")),
                        str(item.state_selector.get("observation")),
                    )
                    for item in cases
                }
            ),
        },
        "source": {"revision": revision, "dirty": dirty},
        "full_method_sources": {
            "case_verdict": (
                "product.backend.core.verification.permissions.evaluation."
                "evaluate_permission_case"
            ),
            "authorization_continuity": (
                "product.backend.core.verification.continuity."
                "assess_authorization_continuity"
            ),
            "breakpoint": (
                "product.backend.core.verification.breakpoints."
                "BreakpointLocator.locate"
            ),
        },
        "method_metrics": _aggregate_method_metrics(evaluations),
        "repeat_consistency": _repeat_consistency(results),
        "results": results,
    }
    _write_json(audit_dir / "validation-summary.json", payload)
    return payload


def build_presentation_summary(summary: Mapping[str, object]) -> dict[str, object]:
    """只发布比赛数据页需要的计数与来源，不携带逐 Case 结果。"""

    if summary.get("status") != "accepted":
        raise sample_validation_models.ValidationSuiteError("VALIDATION_PRESENTATION_SUMMARY_NOT_ACCEPTED")
    metrics = summary.get("method_metrics")
    matrix = summary.get("matrix")
    source = summary.get("source")
    if not isinstance(metrics, Mapping) or not isinstance(matrix, Mapping):
        raise sample_validation_models.ValidationSuiteError("VALIDATION_PRESENTATION_SUMMARY_INVALID")
    full = metrics.get("full")
    http = metrics.get("http_only")
    if not isinstance(full, Mapping) or not isinstance(http, Mapping):
        raise sample_validation_models.ValidationSuiteError("VALIDATION_PRESENTATION_SUMMARY_INVALID")
    repetitions = _summary_int(summary, "repetitions")
    http_wrong_vulnerable = _summary_int(http, "wrong_pass_vulnerable")
    http_wrong_gap = _summary_int(http, "wrong_pass_evidence_gap")
    http_wrong_total = http_wrong_vulnerable + http_wrong_gap
    if repetitions not in {1, 3} or http_wrong_total % repetitions:
        raise sample_validation_models.ValidationSuiteError("VALIDATION_PRESENTATION_SUMMARY_INVALID")
    revision = source.get("revision") if isinstance(source, Mapping) else None
    dirty = source.get("dirty") if isinstance(source, Mapping) else None
    return {
        "schema_version": "1",
        "generated_at_us": _summary_int(summary, "generated_at_us"),
        "suite": str(summary.get("suite")),
        "status": "accepted",
        "repetitions": repetitions,
        "case_count": _summary_int(summary, "case_count"),
        "case_run_count": _summary_int(summary, "case_run_count"),
        "application_count": _summary_int(matrix, "application_count"),
        "mode_count": _summary_int(matrix, "mode_count"),
        "state_count": _summary_int(matrix, "state_count"),
        "full_exact_match_count": _summary_int(full, "exact_match_count"),
        "full_wrong_pass_vulnerable": _summary_int(
            full,
            "wrong_pass_vulnerable",
        ),
        "full_wrong_pass_evidence_gap": _summary_int(
            full,
            "wrong_pass_evidence_gap",
        ),
        "http_exact_match_count": _summary_int(http, "exact_match_count"),
        "http_wrong_pass_vulnerable": http_wrong_vulnerable,
        "http_wrong_pass_evidence_gap": http_wrong_gap,
        "http_wrong_pass_per_matrix": http_wrong_total // repetitions,
        "source_revision": revision if isinstance(revision, str) else None,
        "source_dirty": dirty if isinstance(dirty, bool) else None,
    }


def _summary_int(value: Mapping[str, object], key: str) -> int:
    item = value.get(key)
    if not isinstance(item, int) or isinstance(item, bool) or item < 0:
        raise sample_validation_models.ValidationSuiteError("VALIDATION_PRESENTATION_SUMMARY_INVALID")
    return item


def _repository_source(root: Path) -> tuple[str | None, bool | None]:
    """记录验证对应的 Git 源状态；仓库视图不可用时保持未知。"""

    try:
        revision_result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            check=False,
            capture_output=True,
            text=True,
        )
        status_result = subprocess.run(
            ["git", "status", "--short"],
            cwd=root,
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError:
        return None, None
    revision = revision_result.stdout.strip().lower()
    if revision_result.returncode != 0 or len(revision) != 40:
        revision = None
    dirty = None if status_result.returncode != 0 else bool(status_result.stdout.strip())
    return revision, dirty


def _aggregate_method_metrics(
    evaluations: list[OracleEvaluation],
) -> dict[str, dict[str, int]]:
    aggregate: dict[str, dict[str, int]] = {}
    for evaluation in evaluations:
        for method, metrics in evaluation.method_metrics.items():
            target = aggregate.setdefault(method, {})
            for name, value in metrics.items():
                target[name] = target.get(name, 0) + int(value)
    return aggregate


def _repeat_consistency(results: list[dict[str, object]]) -> dict[str, int]:
    signatures: dict[str, set[str]] = {}
    for result in results:
        case_id = str(result.get("case_id"))
        public_result = {key: value for key, value in result.items() if key != "repetition"}
        signatures.setdefault(case_id, set()).add(
            json.dumps(public_result, ensure_ascii=False, sort_keys=True)
        )
    consistent = sum(len(items) == 1 for items in signatures.values())
    return {
        "case_count": len(signatures),
        "consistent_case_count": consistent,
        "inconsistent_case_count": len(signatures) - consistent,
    }


def _write_json(path: Path, payload: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f".{uuid4().hex}.tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )
    os.replace(temporary, path)
