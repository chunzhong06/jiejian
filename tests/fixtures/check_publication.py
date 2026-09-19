# 构造真实检查队列、冻结请求与待发布证据，供发布和只读消费者测试共享。
import hashlib
from functools import partial

import pytest

from product.backend.core.lifecycle import CaseVerdict, ProjectStatus, RunLifecycle, RunVerdict
from product.backend.infra.runtime.jobs.models import ClaimJob
from product.backend.infra.runtime.paths import RuntimePaths
from product.backend.infra.storage import ProjectRecord, StorageUnitOfWork
from product.protocols.check_result import CheckCaseOutcome, CheckCaseResult, CheckRunnerResult, canonical_check_document, seal_check_evidence
from product.protocols.check_runtime import canonical_check_runtime_bytes
from product.protocols.execution_v3 import canonical_execution_request_v3_bytes
from tests.fixtures.check_execution import execution_pair

NOW = 1_790_000_000_000_000


@pytest.fixture
def package_parts(worker_services, tmp_path, request):
    options = getattr(request, "param", {})
    frozen_request, bundle = execution_pair(**options)
    return build_package_parts(worker_services, tmp_path, request=frozen_request, bundle=bundle)


def build_package_parts(worker_services, var_dir, *, request, bundle):
    """以显式冻结输入构造待发布包；上下文必须在请求、证据与收据计算哈希之前确定。"""
    factory = partial(StorageUnitOfWork, worker_services.session_factory)
    with factory() as work:
        work.projects.add(ProjectRecord(project_id=request.project_id, name="发布检查测试", status=ProjectStatus.READY,
            created_at_us=NOW, updated_at_us=NOW))
        work.commit()
    raw_request = canonical_execution_request_v3_bytes(request)
    request_hash = hashlib.sha256(raw_request).hexdigest()
    submitted = worker_services.queue.submit(worker_services.submit_request(project_id=request.project_id,
        request_hash=request_hash, plan_fingerprint=request.plan_fingerprint, source_fingerprint=request.source_fingerprint,
        policy_epoch=request.policy_epoch, engine_version=request.engine_version, max_attempts=1))
    job = worker_services.attempts.claim(ClaimJob(job_id=submitted.job.job_id, lease_owner="check-worker",
        now_us=NOW + 10, lease_duration_us=1000)).job
    directory = RuntimePaths(var_dir).jobs / job.job_id / "attempts" / "1-1" / "staging"
    (directory / "evidence").mkdir(parents=True)
    (directory / "request.json").write_bytes(raw_request)
    (directory / "runtime.json").write_bytes(canonical_check_runtime_bytes(bundle))
    results = []
    outcome = CheckCaseOutcome(execution_outcome="UNKNOWN", actual_identity_status="UNKNOWN",
        baseline_trusted=False, recovery_verified=False, run_correlated=False, resource_correlated=False)
    for action in request.actions:
        for case in action.cases:
            evidence = seal_check_evidence(run_id=job.run_id, job_id=job.job_id, attempt=job.attempt,
                action_id=action.action_id, action_revision=action.action_revision, request_hash=request_hash,
                config_hash=request.config_fingerprint, case=case, outcome=outcome, observations=())
            (directory / "evidence" / f"{evidence.evidence_id}.json").write_bytes(canonical_check_document(evidence))
            results.append(CheckCaseResult(case_id=case.case_id, action_id=action.action_id,
                verdict=CaseVerdict.INCONCLUSIVE, reason_codes=("ACTUAL_IDENTITY_UNKNOWN",),
                evidence_ids=(evidence.evidence_id,), outcome=outcome))
    result = CheckRunnerResult(run_id=job.run_id, job_id=job.job_id, attempt=job.attempt,
        lease_owner=job.lease_owner, fencing_token=job.fencing_token, request_hash=request_hash,
        config_hash=request.config_fingerprint, result_type="SUCCESS", lifecycle=RunLifecycle.COMPLETED,
        case_results=tuple(results), verdict=RunVerdict.INCONCLUSIVE, started_at_us=NOW + 11, completed_at_us=NOW + 19)
    (directory / "result.json").write_bytes(canonical_check_document(result))
    return var_dir, factory, job, directory, result
