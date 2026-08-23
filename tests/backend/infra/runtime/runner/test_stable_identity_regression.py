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
from tests.fixtures.runner import evidence, runner_input


ROOT = Path(__file__).resolve().parents[5]
EXPECTED = json.loads(
    (ROOT / "tests/fixtures/execution/web_runtime_regression.json").read_text(
        encoding="utf-8"
    )
)


def test_current_web_stable_identities_and_three_golden_verdicts_do_not_drift() -> None:
    profile_path = ROOT / "samples/web/fixed/profile.json"
    profile = parse_web_execution_profile(profile_path.read_bytes())
    contract = PermissionContract.model_validate_json(
        profile_path.with_name("contract.json").read_bytes(), strict=True
    )
    plan = ExecutionWorkflow._compile_plan(profile, contract)
    snapshot = profile.build_snapshot(contract, plan)
    request = PersistedExecutionRequest(
        budget=ExecutionBudget(
            max_requests=profile.target.scope.max_requests,
            request_timeout_us=int(profile.target.scope.timeout_seconds * 1_000_000),
            max_duration_us=profile.max_duration_us,
            max_response_bytes=profile.target.scope.max_response_bytes,
            max_cases=profile.case_budget,
            max_parallel_cases=1,
        ),
        project_snapshot=snapshot,
    )
    current_evidence = evidence()
    assert web_execution_profile_sha256(profile) == EXPECTED["profile_sha256"]
    assert permission_model_sha256(contract) == EXPECTED["contract_fingerprint"]
    assert plan.plan_fingerprint == EXPECTED["plan_fingerprint"]
    assert snapshot.differential_fingerprint == EXPECTED["differential_fingerprint"]
    assert (
        hashlib.sha256(canonical_execution_request_bytes(request)).hexdigest()
        == EXPECTED["execution_request_sha256"]
    )
    assert current_evidence.evidence_id == EXPECTED["evidence_id"]
    assert current_evidence.evidence_hash == EXPECTED["evidence_hash"]
    assert current_evidence.finding_pre_identity == EXPECTED["finding_pre_identity"]
    result = _result("run_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", current_evidence)
    finding = finding_inputs(
        SimpleNamespace(
            request_snapshot=lambda _view: runner_input().project_snapshot
        ),
        _view(result.run_id, result),
    )
    assert finding[0].identity.finding_id() == EXPECTED["finding_id"]

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
    assert (base.report_id, base.canonical_sha256) == (
        EXPECTED["base_report_id"],
        EXPECTED["base_report_sha256"],
    )
    assert (gate.report_id, gate.canonical_sha256) == (
        EXPECTED["gate_report_id"],
        EXPECTED["gate_report_sha256"],
    )
    assert {
        variant: json.loads(
            (ROOT / f"samples/web/{variant}/truth.json").read_text(encoding="utf-8")
        )["formal_profile"]["run_verdict"]
        for variant in ("fixed", "vulnerable", "inconclusive")
    } == EXPECTED["golden_run_verdicts"]
