# 验证当前 CHECK API 的冻结输入、提交幂等、取消与持久失败事实；不恢复旧事件接口。
from __future__ import annotations

import time
import json
import pytest

from product.backend.infra.runtime.jobs.requests.checks import CheckRequestStore
from product.backend.infra.runtime.jobs.models import ClaimJob, FatalFailure, FatalFailureCode
from product.protocols import CleanupIssueCode, RunnerFailurePhase
from tests.fixtures.preparation.action_preparation import MemorySecretStore
from tests.fixtures.checks.check_service import ready_check_harness
from tests.fixtures.control_plane import TestClient, create_app


@pytest.fixture
def current_run_api(tmp_path):
    app = create_app(tmp_path / 'var', start_worker=False, secret_store=MemorySecretStore(), environ={})
    harness = ready_check_harness(tmp_path, core=app.state.context)
    with TestClient(app) as client:
        yield app.state.context, harness, client


def _submit(client, project, key):
    preview = client.get(f'/api/projects/{project}/check-preview')
    assert preview.status_code == 200
    facts = preview.json()['data']
    assert facts['can_execute'] is True
    body = {'schema_version': '2', 'expected_plan_fingerprint': facts['plan_fingerprint'], 'idempotency_key': key}
    response = client.post(f'/api/projects/{project}/runs', json=body)
    assert response.status_code == 202, response.text
    return response.json()['data'], body


def test_run_idempotency_cancel_and_unmounted_events(current_run_api):
    _, harness, client = current_run_api
    accepted, body = _submit(client, harness.project_id, 'api-sse-test')
    repeated = client.post(f'/api/projects/{harness.project_id}/runs', json=body)
    assert repeated.status_code == 202 and repeated.json()['data'] == accepted
    job_id, run_id = accepted['job']['job_id'], accepted['run']['run_id']
    assert client.post(f'/api/jobs/{job_id}/cancel').status_code == 200
    detail = client.get(f'/api/runs/{run_id}').json()['data']
    assert detail['run']['lifecycle'] == 'CANCELLED' and detail['run']['verdict'] is None
    assert client.get(f'/api/jobs/{job_id}/events').status_code == 404


def test_failed_check_separates_lifecycle_from_verdict_and_persists_failure_details(current_run_api):
    core, harness, client = current_run_api
    accepted, _ = _submit(client, harness.project_id, 'api-failure-test')
    job_id, run_id = accepted['job']['job_id'], accepted['run']['run_id']
    now = time.time_ns() // 1000
    claim = core.job_attempts.claim(ClaimJob(job_id=job_id, lease_owner='diagnostic-worker', now_us=now, lease_duration_us=30_000_000))
    assert claim is not None
    core.job_attempts.record_fatal_failure(FatalFailure(job_id=job_id, lease_owner='diagnostic-worker',
        fencing_token=claim.job.fencing_token, now_us=now+1, reason_code=FatalFailureCode.RUNNER_FATAL,
        error_code='PREPARE_RECOVERY_FAILED', phase=RunnerFailurePhase.PREPARE_RECOVERY,
        cause_code='TARGET_UNREACHABLE', cleanup_issue_codes=(CleanupIssueCode.POST_CASE_RECOVERY_FAILED,)))
    detail = client.get(f'/api/runs/{run_id}').json()['data']
    assert detail['run']['lifecycle'] == 'FAILED' and detail['run']['verdict'] is None
    assert detail['result_integrity'] == 'NOT_PUBLISHED'
    assert client.get(f'/api/runs/{run_id}/result-story').status_code == 404
    with core.uow_factory() as work:
        events = json.dumps([item.model_dump(mode='json') for item in work.job_events.list_for_job(job_id)])
    for code in ('JOB_FAILED', 'PREPARE_RECOVERY_FAILED', 'TARGET_UNREACHABLE', 'POST_CASE_RECOVERY_FAILED'):
        assert code in events


def test_api_submission_freezes_current_policy_plan_and_source(current_run_api):
    core, harness, client = current_run_api
    accepted, body = _submit(client, harness.project_id, 'api-frozen-input')
    job_id = accepted['job']['job_id']
    with core.uow_factory() as work:
        job = work.jobs.get(job_id)
        source = work.application_understanding.get(harness.project_id)
    request = CheckRequestStore(core.var_dir).load(job_id, expected_hash=job.request_hash)
    assert job.operation_type == 'CHECK'
    assert request.schema_version == '3'
    assert request.plan_fingerprint == body['expected_plan_fingerprint']
    assert request.policy_epoch == core.business_boundaries.view(harness.project_id).policy_epoch
    assert request.source_fingerprint == source.source_fingerprint
    assert [item.action_id for item in request.actions] == [harness.action.action_id]
    assert sum(len(item.cases) for item in request.actions) == 1
