# sample-test private oracle：只在外层验收器中比较实际结果，不向产品、MCP 或公开报告投影答案。

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from sample_test_registry import PublicValidationCase, ValidationCaseResult


_ORACLE_KEYS = frozenset(
    {
        "expected_verdict",
        "breakpoint_type",
        "breakpoint_location",
        "breakpoint_range",
        "maximum_precision",
        "golden_answer",
    }
)


class PrivateOracleError(RuntimeError):
    """表示 private oracle 缺失、泄露到源码根或与公开清单不一致。"""


@dataclass(frozen=True, slots=True)
class OracleEvaluation:
    """只供外层流程决定退出码；公开输出只使用计数。"""

    matched_count: int
    mismatch_count: int
    mismatched_case_ids: tuple[str, ...]
    method_metrics: Mapping[str, Mapping[str, int]]


class PrivateOracleEvaluator:
    """private oracle 的唯一读取者。"""

    def __init__(
        self,
        root: Path,
        cases: tuple[PublicValidationCase, ...],
    ) -> None:
        self._root = root.resolve()
        self._path = self._root / "tests" / "validation" / "private_oracle.json"
        self._assert_outside_authorized_roots(cases)
        self._oracle = self._load(cases)

    @property
    def path(self) -> Path:
        """只给隔离测试核对物理位置，不提供 oracle 内容。"""

        return self._path

    def evaluate(
        self,
        results: tuple[ValidationCaseResult, ...],
    ) -> OracleEvaluation:
        actual_ids = tuple(item.case_id for item in results)
        if len(actual_ids) != len(set(actual_ids)) or set(actual_ids) != set(self._oracle):
            raise PrivateOracleError("VALIDATION_RESULT_CASE_SET_INVALID")
        mismatches: list[str] = []
        for result in results:
            oracle = self._oracle[result.case_id]
            actual = {
                "expected_verdict": result.verdict,
                "breakpoint_type": result.breakpoint_type,
                "breakpoint_location": result.breakpoint_location,
                "breakpoint_range": list(result.breakpoint_range),
                "maximum_precision": result.precision or "NOT_APPLICABLE",
            }
            if any(actual[name] != oracle[name] for name in actual):
                mismatches.append(result.case_id)
        method_metrics = {
            "full": self._method_metrics(results, method="full"),
            "http_only": self._method_metrics(results, method="http_only"),
            "single_state": self._method_metrics(results, method="single_state"),
            "authorization_regression": self._method_metrics(
                results,
                method="authorization_regression",
            ),
        }
        return OracleEvaluation(
            matched_count=len(results) - len(mismatches),
            mismatch_count=len(mismatches),
            mismatched_case_ids=tuple(sorted(mismatches)),
            method_metrics=method_metrics,
        )

    def _method_metrics(
        self,
        results: tuple[ValidationCaseResult, ...],
        *,
        method: str,
    ) -> Mapping[str, int]:
        """聚合方法级指标；只公开计数，不公开任一 Case 的答案或匹配关系。"""

        metrics = {
            "total": len(results),
            "exact_match_count": 0,
            "wrong_pass_vulnerable": 0,
            "wrong_pass_evidence_gap": 0,
        }
        if method == "full":
            metrics.update(
                {
                    "effect_decision_correct_count": 0,
                    "continuity_or_orphan_correct_count": 0,
                    "actual_identity_attributed_count": 0,
                    "breakpoint_type_match_count": 0,
                    "breakpoint_precision_match_count": 0,
                    "allow_control_valid_count": 0,
                    "recovery_success_count": 0,
                    "repair_verification_applicable_count": 0,
                    "repair_verification_success_count": 0,
                }
            )
        for result in results:
            oracle = self._oracle[result.case_id]
            expected = str(oracle["expected_verdict"])
            actual = (
                result.verdict
                if method == "full"
                else str(result.baseline_verdicts[method])
            )
            metrics["exact_match_count"] += int(actual == expected)
            metrics["wrong_pass_vulnerable"] += int(
                expected == "BLOCK" and actual == "PASS"
            )
            metrics["wrong_pass_evidence_gap"] += int(
                expected == "INCONCLUSIVE" and actual == "PASS"
            )
            if method != "full":
                continue
            expected_effect = {
                "BLOCK": "CONFIRMED",
                "PASS": "ABSENT",
                "INCONCLUSIVE": "UNKNOWN",
            }[expected]
            metrics["effect_decision_correct_count"] += int(
                result.effect_state == expected_effect
            )
            expected_continuity = {
                "BLOCK": ("BROKEN", True),
                "PASS": ("INTACT", False),
                "INCONCLUSIVE": ("UNKNOWN", None),
            }[expected]
            metrics["continuity_or_orphan_correct_count"] += int(
                (
                    result.authorization_continuity,
                    result.orphan_effect_detected,
                )
                == expected_continuity
            )
            metrics["actual_identity_attributed_count"] += int(
                result.actual_identity_attributed
            )
            metrics["breakpoint_type_match_count"] += int(
                result.breakpoint_type == oracle["breakpoint_type"]
            )
            metrics["breakpoint_precision_match_count"] += int(
                (result.precision or "NOT_APPLICABLE")
                == oracle["maximum_precision"]
            )
            metrics["allow_control_valid_count"] += int(result.allow_control_valid)
            metrics["recovery_success_count"] += int(result.recovery_success)
            if expected == "PASS":
                metrics["repair_verification_applicable_count"] += 1
                metrics["repair_verification_success_count"] += int(
                    result.verdict == "PASS"
                    and result.allow_control_valid
                    and result.authorization_continuity == "INTACT"
                )
        return metrics

    def _assert_outside_authorized_roots(
        self,
        cases: tuple[PublicValidationCase, ...],
    ) -> None:
        oracle = self._path.resolve()
        for item in cases:
            try:
                oracle.relative_to(item.source_root.resolve())
            except ValueError:
                continue
            raise PrivateOracleError("VALIDATION_ORACLE_INSIDE_SOURCE_ROOT")

    def _load(
        self,
        cases: tuple[PublicValidationCase, ...],
    ) -> dict[str, Mapping[str, object]]:
        try:
            payload = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise PrivateOracleError("VALIDATION_PRIVATE_ORACLE_UNREADABLE") from exc
        if (
            not isinstance(payload, dict)
            or set(payload) != {"schema_version", "cases"}
            or payload.get("schema_version") != "1"
            or not isinstance(payload.get("cases"), dict)
        ):
            raise PrivateOracleError("VALIDATION_PRIVATE_ORACLE_SHAPE_INVALID")
        oracle = payload["cases"]
        selected_ids = {item.case_id for item in cases}
        if not selected_ids.issubset(oracle):
            raise PrivateOracleError("VALIDATION_PRIVATE_ORACLE_CASE_SET_INVALID")
        normalized: dict[str, Mapping[str, object]] = {}
        for case_id in selected_ids:
            value = oracle[case_id]
            if not isinstance(value, dict) or set(value) != _ORACLE_KEYS:
                raise PrivateOracleError("VALIDATION_PRIVATE_ORACLE_ENTRY_INVALID")
            if value["expected_verdict"] not in {"BLOCK", "PASS", "INCONCLUSIVE"}:
                raise PrivateOracleError("VALIDATION_PRIVATE_ORACLE_VERDICT_INVALID")
            if value["maximum_precision"] not in {
                "EXACT",
                "RANGE",
                "VIOLATION_ONLY",
                "NOT_APPLICABLE",
            }:
                raise PrivateOracleError("VALIDATION_PRIVATE_ORACLE_PRECISION_INVALID")
            if not isinstance(value["breakpoint_range"], list) or not isinstance(
                value["golden_answer"], str
            ):
                raise PrivateOracleError("VALIDATION_PRIVATE_ORACLE_ENTRY_INVALID")
            normalized[case_id] = value
        return normalized


__all__ = [
    "OracleEvaluation",
    "PrivateOracleError",
    "PrivateOracleEvaluator",
]
