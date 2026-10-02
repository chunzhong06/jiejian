# 选择公开场景并编排独立重复验收。
from __future__ import annotations

import sys
from pathlib import Path
from tests.acceptance.sample_test.oracle import OracleEvaluation, PrivateOracleEvaluator
from tests.acceptance.sample_test.registry import (
    PublicValidationCase,
    ValidationCaseResult,
    load_public_registry,
    public_registry_payload,
)
import tests.acceptance.sample_test.validation.evaluation as sample_validation_evaluation
import tests.acceptance.sample_test.validation.models as sample_validation_models
import tests.acceptance.sample_test.validation.runtime as sample_validation_runtime
import tests.acceptance.sample_test.validation.summary as sample_validation_summary


def run_validation_suite(
    root: Path,
    var_dir: Path,
    *,
    repetitions: int,
    representative_only: bool = False,
) -> dict[str, object]:
    """执行公开 registry，private oracle 只决定最终退出状态。"""

    if repetitions not in {1, 3}:
        raise sample_validation_models.ValidationSuiteError("VALIDATION_REPETITIONS_INVALID")
    root = root.resolve()
    if str(root) not in sys.path:
        # samples 是仓库内验证资产而非发布包；validation suite 只在 tests 边界显式装配它。
        sys.path.insert(0, str(root))
    var_dir = var_dir.resolve()
    var_dir.mkdir(parents=True, exist_ok=True)
    if any(var_dir.iterdir()):
        raise sample_validation_models.ValidationSuiteError("VALIDATION_VAR_DIR_NOT_EMPTY")
    cases = load_public_registry(root)
    if representative_only:
        cases = _representative_cases(cases)
    public_input = public_registry_payload(root, cases)
    audit_dir = var_dir / "audit" / "sample-test"
    audit_dir.mkdir(parents=True)
    sample_validation_summary._write_json(audit_dir / "validation-public-input.json", public_input)
    evaluator = PrivateOracleEvaluator(root, cases)
    all_results: list[dict[str, object]] = []
    evaluations: list[OracleEvaluation] = []
    for repetition in range(1, repetitions + 1):
        current: list[ValidationCaseResult] = []
        for index, case in enumerate(cases, start=1):
            case_dir = var_dir / "runtime" / "validation" / f"r{repetition}" / case.case_id
            observation = sample_validation_runtime._execute_case(case, case_dir)
            if not observation.process_cleanup_success:
                raise sample_validation_models.ValidationSuiteError("VALIDATION_PROCESS_CLEANUP_FAILED")
            result = sample_validation_evaluation._evaluate_case(case, observation)
            current.append(result)
            all_results.append(
                {
                    "repetition": repetition,
                    "process_cleanup_success": observation.process_cleanup_success,
                    **result.public_payload(),
                }
            )
            print(
                f"[validation {repetition}/{repetitions}] "
                f"{index}/{len(cases)} {case.case_id}: {result.verdict}",
                flush=True,
            )
        evaluation = evaluator.evaluate(tuple(current))
        evaluations.append(evaluation)
        full_metrics = evaluation.method_metrics["full"]
        if (
            full_metrics["wrong_pass_vulnerable"]
            or full_metrics["wrong_pass_evidence_gap"]
        ):
            sample_validation_summary._write_public_summary(
                root,
                audit_dir,
                repetitions,
                cases,
                all_results,
                evaluations,
                status="failed",
            )
            raise sample_validation_models.ValidationSuiteError("VALIDATION_SECURITY_FLOOR_FAILED")
        if evaluation.mismatch_count:
            sample_validation_summary._write_public_summary(
                root,
                audit_dir,
                repetitions,
                cases,
                all_results,
                evaluations,
                status="failed",
            )
            raise sample_validation_models.ValidationSuiteError(
                f"VALIDATION_PRIVATE_ORACLE_MISMATCH:{evaluation.mismatch_count}"
            )
    summary = sample_validation_summary._write_public_summary(
        root,
        audit_dir,
        repetitions,
        cases,
        all_results,
        evaluations,
        status="accepted",
    )
    print(
        f"validation suite 完成：{len(cases)} Case × {repetitions}。",
        flush=True,
    )
    return summary


def _representative_cases(
    cases: tuple[PublicValidationCase, ...],
) -> tuple[PublicValidationCase, ...]:
    """每个应用取同一公开模式的三态代表，不根据 private oracle 选样。"""

    applications = sorted({item.application_id for item in cases})
    selected = tuple(
        item
        for item in cases
        if item.application_id in applications
        and item.mode == "object_tenant_check_missing"
    )
    if len(selected) != len(applications) * 3:
        raise sample_validation_models.ValidationSuiteError("VALIDATION_REPRESENTATIVE_SET_INVALID")
    return selected


__all__ = [
    "ValidationSuiteError",
    "build_presentation_summary",
    "run_validation_suite",
]
