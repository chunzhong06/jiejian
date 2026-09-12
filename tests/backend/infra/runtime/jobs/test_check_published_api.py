# 验证正式 API 读取真实发布文件与收据，禁用 AI 时保留确定性结果，篡改后拒绝详情。
import hashlib
import json
import socket
from types import SimpleNamespace as N

import pytest
import sqlite3
import subprocess
from unittest.mock import Mock

from product.backend.core.check_repair import repair_context
from product.backend.core.lifecycle import CaseVerdict, RunVerdict
from product.backend.infra.artifacts.check_publication import CheckPublisher
from product.backend.infra.runtime.jobs.models import ClaimJob
from product.backend.infra.runtime.paths import RuntimePaths
from product.backend.workflows.checks.repair import build_current_repair_contract
from product.backend.workflows.checks.results import CheckResultReader
from product.backend.workflows.checks.story import CheckStoryBuilder
from product.protocols.check_result import CheckCaseOutcome, CheckCaseResult, CheckObservation, canonical_check_document, check_request_marker, seal_check_evidence
from product.protocols.check_runtime import canonical_check_runtime_bytes, parse_check_runtime
from product.protocols.execution_v3 import ChangeContext, PersistedExecutionRequestV3, canonical_execution_request_v3_bytes
from tests.backend.infra.runtime.jobs.test_check_publication import package_parts, NOW
from tests.fixtures.action_preparation import MemorySecretStore
from tests.fixtures.control_plane import create_app, TestClient



def frozen_labels(payload):
    for index, identity in enumerate(payload["identities"]):
        identity["label"] = f"冻结测试账号 {index}"
    payload["actions"][0]["display_name"] = "读取归属对象"


def stage_outcomes(directory, template, *, identity_status="MATCH", forbidden=False):
    # 合成确定性执行事实后仍走真实 Publisher 重验与持久化；GET 期间禁止调用判定器。
    request = PersistedExecutionRequestV3.model_validate_json((directory / "request.json").read_bytes())
    bundle = parse_check_runtime((directory / "runtime.json").read_bytes())
    proofs = {proof.binding_fingerprint: proof for action in bundle.actions for proof in action.proofs}
    results = []
    for path in (directory / "evidence").glob("*.json"):
        path.unlink()
    for action in request.actions:
        for case in action.cases:
            deny = case.permission.expectation == "DENY"
            outcome = CheckCaseOutcome(execution_outcome="DENIED" if deny else "ACCEPTED",
                actual_identity_status=identity_status, baseline_trusted=True, recovery_verified=True,
                run_correlated=True, resource_correlated=True)
            observations = tuple(CheckObservation(effect_id=proof.effect_id, proof_fingerprint=proof.proof_fingerprint,
                observer_id=proofs[proof.binding_fingerprint].observer_id, level=proof.level, phase="AFTER",
                state="CONFIRMED" if not deny or forbidden else "ABSENT", closure="CLOSED", complete=True,
                reliable=True, correlated=True, authoritative=True, window_start_us=NOW+12, window_end_us=NOW+13,
                correlation_refs=(check_request_marker(template.run_id, template.job_id, template.attempt, case.case_id),))
                for proof in case.proof_requirements)
            evidence = seal_check_evidence(run_id=template.run_id, job_id=template.job_id, attempt=template.attempt,
                action_id=action.action_id, action_revision=action.action_revision, request_hash=template.request_hash,
                config_hash=request.config_fingerprint, case=case, outcome=outcome, observations=observations)
            (directory / "evidence" / f"{evidence.evidence_id}.json").write_bytes(canonical_check_document(evidence))
            verdict = CaseVerdict.INCONCLUSIVE if identity_status != "MATCH" else CaseVerdict.VULNERABLE if deny and forbidden else CaseVerdict.SAFE
            results.append(CheckCaseResult(case_id=case.case_id, action_id=action.action_id, verdict=verdict,
                reason_codes=(), evidence_ids=(evidence.evidence_id,), outcome=outcome))
    result = template.model_copy(update={"case_results": tuple(results), "verdict": RunVerdict.INCONCLUSIVE
        if identity_status != "MATCH" else RunVerdict.BLOCK if forbidden else RunVerdict.PASS})
    (directory / "result.json").write_bytes(canonical_check_document(result))
    return result


@pytest.mark.parametrize("package_parts", [{"configure": frozen_labels}], indirect=True)
@pytest.mark.parametrize("identity_status", ["UNKNOWN", "MISMATCH"])
def test_published_api_story_evidence_disabled_assistant_and_tamper(package_parts, worker_services, monkeypatch, identity_status):
    var_dir, factory, job, staging, result = package_parts
    result = stage_outcomes(staging, result, identity_status=identity_status)
    package = CheckPublisher(var_dir, factory, clock_us=lambda: NOW + 20).publish(staging)
    (var_dir / "data").mkdir(exist_ok=True)
    with sqlite3.connect(worker_services.database_path) as source, sqlite3.connect(var_dir / "data/jiejian.db") as destination:
        source.backup(destination)
    app = create_app(var_dir, start_worker=False, secret_store=MemorySecretStore(), environ={})
    with TestClient(app) as client:
        forbidden = Mock(side_effect=AssertionError("published API must not execute target or recompute verdict"))
        monkeypatch.setattr(socket.socket, "connect", forbidden)
        monkeypatch.setattr(subprocess, "Popen", forbidden)
        monkeypatch.setattr("product.backend.core.verification.checks.evaluate_check_case", forbidden)
        prefix = f"/api/runs/{job.run_id}"
        story = client.get(prefix + "/result-story")
        assert story.status_code == 200
        comparison = next(item for item in story.json()["data"]["actions"] if item["permission"]["expectation"] == "DENY")["fact_comparison"]
        assert comparison["planned_identity"]["identity_id"] is not None
        assert comparison["verified_actual_identity"]["verification_status"] == identity_status
        owner = comparison["planned_resource_owner"]
        assert owner["verification_status"] == "PLANNED"
        assert owner["label"] != comparison["planned_identity"]["label"]
        frozen_case = next(case for action in package.request.actions for case in action.cases if case.permission.expectation == "DENY")
        frozen_owner = next(item for item in package.bundle.identities if item.identity_id == frozen_case.resource_owner_test_identity_id)
        assert owner["label"] == frozen_owner.label and owner["identity_id"] == frozen_owner.identity_id
        assert comparison["resource_id"] == frozen_case.resource_id
        assert comparison["verified_actual_identity"]["identity_id"] is None
        assert comparison["verified_actual_identity"]["label"] is None
        assert client.get(prefix).json()["data"]["run"]["verdict"] == result.verdict.value
        index = client.get(prefix + "/evidence").json()["data"]
        assert len(index) == len(package.evidence)
        assert "observations" not in index[0] and "case" not in index[0]
        detail = client.get(prefix + "/evidence/" + index[0]["evidence_id"])
        assert detail.status_code == 200 and "observations" in detail.json()["data"]
        explanation = client.get(prefix + "/assistant/result-explanation")
        assert explanation.status_code == 200
        assert explanation.json()["data"]["status"] == "DISABLED"
        assert client.get(prefix + "/result-story").json() == story.json()
        forbidden.assert_not_called()
        (package.directory / "result.json").write_bytes(b"{}")
        status = client.get(prefix).json()["data"]
        assert status["result_integrity"] == "INVALID" and status["run"]["verdict"] is None
        assert client.get(prefix + "/result-story").status_code >= 400
        assert client.get(prefix + "/evidence").status_code >= 400


@pytest.mark.parametrize("package_parts", [{"configure": frozen_labels}], indirect=True)
def test_published_story_and_project_repair_share_read_only_comparison(package_parts, worker_services, monkeypatch):
    var_dir, factory, source_job, staging, template = package_parts
    stage_outcomes(staging, template, forbidden=True)
    source = CheckPublisher(var_dir, factory, clock_us=lambda: NOW + 20).publish(staging)
    deny = next(item for item in source.result.case_results if item.verdict is CaseVerdict.VULNERABLE)
    # 与正式 CurrentRepairService 一样从已发布 Story 冻结 Breakpoint，不能手造另一份合同指纹。
    reader = CheckResultReader(var_dir=var_dir, uow_factory=factory)
    story = CheckStoryBuilder(reader).build(source_job.run_id, include_repair=False)
    breakpoint = next(item.breakpoint for item in story.actions if item.case_id == deny.case_id)
    contract = build_current_repair_contract(source, deny.case_id, breakpoint=breakpoint)
    contract_bytes = contract.model_dump_json()
    change = ChangeContext(change_id="chg_" + "3" * 32, impact_fingerprint="4" * 64,
        required_intent_ids=tuple(ref.intent_id for ref in contract.original_intents))
    payload = source.request.model_dump(mode="json")
    payload.update(repair_context=repair_context(contract).model_dump(mode="json"), change_context=change.model_dump(mode="json"))
    request = PersistedExecutionRequestV3.model_validate_json(json.dumps(payload))
    raw = canonical_execution_request_v3_bytes(request)
    request_hash = hashlib.sha256(raw).hexdigest()
    submitted = worker_services.queue.submit(worker_services.submit_request(project_id=request.project_id,
        idempotency_key="repair-comparison-new", request_hash=request_hash, plan_fingerprint=request.plan_fingerprint,
        source_fingerprint=request.source_fingerprint, policy_epoch=request.policy_epoch, engine_version=request.engine_version,
        max_attempts=1, now_us=NOW+30, available_at_us=NOW+30))
    job = worker_services.attempts.claim(ClaimJob(job_id=submitted.job.job_id, lease_owner="comparison",
        now_us=NOW+31, lease_duration_us=1000)).job
    directory = RuntimePaths(var_dir).jobs / job.job_id / "attempts" / "1-1" / "staging"
    (directory / "evidence").mkdir(parents=True)
    (directory / "request.json").write_bytes(raw)
    (directory / "runtime.json").write_bytes(canonical_check_runtime_bytes(source.bundle))
    new_template = template.model_copy(update={"run_id": job.run_id, "job_id": job.job_id,
        "lease_owner": job.lease_owner, "fencing_token": job.fencing_token, "request_hash": request_hash})
    stage_outcomes(directory, new_template)
    current = CheckPublisher(var_dir, factory, clock_us=lambda: NOW + 40).publish(directory)
    with sqlite3.connect(worker_services.database_path) as source_db, sqlite3.connect(var_dir / "data/jiejian.db") as destination:
        source_db.backup(destination)
    app = create_app(var_dir, start_worker=False, secret_store=MemorySecretStore(), environ={})
    context = app.state.context
    monkeypatch.setattr(context.business_boundaries, "view", lambda _: N(policy_epoch=contract.original_policy_epoch,
        permission_intents=contract.original_intents))
    monkeypatch.setattr(context.source_changes, "latest_for_repair", lambda *args: N(manifest=N(change_id=change.change_id),
        revalidation=N(status="READY", can_execute=True)))
    # 服务构造时已保存 bound method，必须注入实际使用的只读依赖，而非事后替换未被调用的方法。
    monkeypatch.setattr(context.check_repairs, "_change_context_reader", lambda *args: change)
    original_files = {path: path.read_bytes() for package in (source, current) for path in package.directory.rglob("*.json")}
    with TestClient(app) as client:
        forbidden = Mock(side_effect=AssertionError("projection must remain read only"))
        monkeypatch.setattr(socket.socket, "connect", forbidden)
        monkeypatch.setattr(subprocess, "Popen", forbidden)
        monkeypatch.setattr("product.backend.core.verification.checks.evaluate_check_case", forbidden)
        monkeypatch.setattr(context.test_identities, "list", forbidden)
        prefix = f"/api/runs/{source_job.run_id}"
        response = client.get(prefix + "/result-story")
        assert response.status_code == 200
        story_case = next(item for item in response.json()["data"]["actions"] if item["case_id"] == deny.case_id)
        before = story_case["repair_comparison"]
        assert [row["role"] for row in before] == ["DENY", "SELECTED_ALLOW", "REGRESSION"]
        assert all(row["match_status"] == "NOT_AVAILABLE" and row["after_verdict"] is None for row in before)
        repair_response = client.get(f"/api/projects/{request.project_id}/repair")
        assert repair_response.status_code == 200, repair_response.text
        repair = repair_response.json()["data"]
        assert repair["status"] == "VERIFIED"
        task = repair["tasks"][0]
        assert task["verification"]["status"] == "VERIFIED"
        rows = task["comparison"]
        assert [row["source_case_id"] for row in rows] == [row["source_case_id"] for row in before]
        assert rows[1]["source_case_id"] == rows[2]["source_case_id"]
        for row, old in zip(rows, before):
            assert row["before_verdict"] == old["before_verdict"]
            assert row["before_evidence_refs"] == old["before_evidence_refs"]
            assert row["match_status"] == "MATCHED" and row["after_run_id"] == job.run_id
            result = next(item for item in current.result.case_results if item.case_id == row["after_case_id"])
            assert row["after_verdict"] == result.verdict.value == "SAFE"
            assert row["after_evidence_refs"] == list(result.evidence_ids)
        assert client.get(prefix + "/repair-contracts").json()["data"] == [json.loads(contract_bytes)]
        assert all(path.read_bytes() == original for path, original in original_files.items())
        assert "secret_ref" not in response.text + repair_response.text
        forbidden.assert_not_called()
        (current.directory / "result.json").write_bytes(b"{}")
        assert client.get(f"/api/projects/{request.project_id}/repair").status_code >= 400
        client.cookies.clear()
        assert client.get(prefix + "/result-story").status_code == 403
