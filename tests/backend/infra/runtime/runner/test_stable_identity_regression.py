# 验证隔离 Runner 运行时中的稳定执行身份回归。

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

from product.backend.core.verification.permissions import (
    PermissionContract,
    permission_model_sha256,
)
from product.backend.workflows.runs.execution import ExecutionWorkflow
from product.backend.workflows.results.findings import finding_inputs
from product.protocols.web.profile import (
    parse_web_execution_profile,
    web_execution_profile_sha256,
)
from product.protocols.execution_request import (
    PersistedExecutionRequest,
    build_permission_policy_snapshot,
    canonical_execution_request_bytes,
)
from product.protocols.report import (
    GateRunReport,
    ReportGate,
    gate_semantic_input_sha256,
    report_id_for,
)
from product.protocols.execution import ExecutionBudget
from tests.backend.workflows.results.test_reports import GATE_ID, PROJECT_ID, RUN_ID, _base
from tests.backend.workflows.results.test_stable_findings import _result, _view
from tests.fixtures.runner import evidence, runner_input, write_web_test_profile


ROOT = Path(__file__).resolve().parents[5]
EXPECTED = json.loads(
    (ROOT / "tests/fixtures/execution/web_runtime_regression.json").read_text(
        encoding="utf-8"
    )
)


def test_current_web_stable_identities_do_not_drift(tmp_path: Path) -> None:
    profile_path, contract_path = write_web_test_profile(tmp_path)
    profile = parse_web_execution_profile(profile_path.read_bytes())
    contract = PermissionContract.model_validate_json(
        contract_path.read_bytes(), strict=True
    )
    plan = ExecutionWorkflow._compile_plan(profile, contract)
    snapshot = profile.build_snapshot(contract, plan)
    request = PersistedExecutionRequest(
        source_fingerprint="d" * 64,
        budget=ExecutionBudget(
            max_requests=profile.target.scope.max_requests,
            request_timeout_us=int(profile.target.scope.timeout_seconds * 1_000_000),
            max_duration_us=profile.max_duration_us,
            max_response_bytes=profile.target.scope.max_response_bytes,
            max_cases=profile.case_budget,
            max_parallel_cases=1,
        ),
        permission_policy=build_permission_policy_snapshot(snapshot.project_id, 0, ()),
        project_snapshot=snapshot,
    )
    current_evidence = evidence()
    actual = {
        "profile_sha256": web_execution_profile_sha256(profile),
        "contract_fingerprint": permission_model_sha256(contract),
        "plan_fingerprint": plan.plan_fingerprint,
        "differential_fingerprint": snapshot.differential_fingerprint,
        "execution_request_sha256": hashlib.sha256(
            canonical_execution_request_bytes(request)
        ).hexdigest(),
        "evidence_id": current_evidence.evidence_id,
        "evidence_hash": current_evidence.evidence_hash,
        "finding_pre_identity": current_evidence.finding_pre_identity,
    }
    result = _result("run_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", current_evidence)
    finding = finding_inputs(
        SimpleNamespace(
            request_snapshot=lambda _view: runner_input().project_snapshot
        ),
        _view(result.run_id, result),
    )
    actual["finding_id"] = finding[0].identity.finding_id()

    base = _base()
    gate_input = gate_semantic_input_sha256(
        base.report_id, base.canonical_sha256, GATE_ID, "c" * 64
    )
    gate = GateRunReport.create(
        report_type="GATE",
        report_id=report_id_for("GATE", gate_input),
        run_id=RUN_ID,
        project_id=PROJECT_ID,
        base_report_id=base.report_id,
        base_report_sha256=base.canonical_sha256,
        gate_result_id=GATE_ID,
        semantic_input_sha256=gate_input,
        run=base.run,
        runtime=base.runtime,
        presentation=base.presentation,
        artifact_summary=base.artifact_summary,
        versions=base.versions,
        limitations=base.limitations,
        gate=ReportGate(
            gate_result_id=GATE_ID,
            baseline_id="baseline_" + "c" * 32,
            run_id=RUN_ID,
            policy_version="gate-v1",
            input_hash="c" * 64,
            decision="PASS",
            reasons=(),
            evaluated_at_us=3,
        ),
    )
    actual.update(
        {
            "base_report_id": base.report_id,
            "base_report_sha256": base.canonical_sha256,
            "gate_report_id": gate.report_id,
            "gate_report_sha256": gate.canonical_sha256,
        }
    )
    assert actual == EXPECTED
