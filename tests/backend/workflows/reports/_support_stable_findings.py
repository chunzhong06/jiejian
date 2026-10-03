# 所属业务域的共享测试构造器；不导入测试用例。
from __future__ import annotations
from pathlib import Path
from types import SimpleNamespace
from product.backend.core.lifecycle import JobState, RunLifecycle, RunVerdict
from product.protocols import (
    CleanupResult,
    CleanupStatus,
    RunnerResultType,
    RunnerResult,
)
from product.backend.workflows.reports.published import PublishedRunView
from product.backend.infra.artifacts.run_packages import PublicationManifest, StagedArtifact, ValidatedPublication
from tests.fixtures.runtime.runner import evidence, runner_input

PROJECT_ID = "runner-project"

RUN_ONE = "run_11111111111111111111111111111111"

def _view(run_id: str, result: RunnerResult):
    timestamp = 100 if run_id == RUN_ONE else 200
    manifest = PublicationManifest(
        project_id=PROJECT_ID,
        run_id=run_id,
        job_id=result.job_id,
        attempt=1,
        lease_owner="finding-test",
        fencing_token=1,
        lease_expires_at_us=1000,
        published_at_us=timestamp,
        result_sha256="a" * 64,
        files=(StagedArtifact(path="result.json", byte_count=1, sha256="a" * 64),),
    )
    return PublishedRunView(
        run=SimpleNamespace(
            project_id=PROJECT_ID,
            run_id=run_id,
            finished_at_us=timestamp,
            updated_at_us=timestamp,
            lifecycle=RunLifecycle.COMPLETED,
        ),
        job=SimpleNamespace(job_id=result.job_id),
        publication=ValidatedPublication(result=result, manifest=manifest, final_dir=Path(".")),
        evidence=(),
    )

def _result(run_id: str, evidence):
    snapshot = runner_input().project_snapshot
    return RunnerResult(
        schema_version="1",
        run_id=run_id,
        job_id="job_" + run_id[4:],
        attempt=1,
        lease_owner="finding-test",
        fencing_token=1,
        finished_at_us=100 if run_id == RUN_ONE else 200,
        result_type=RunnerResultType.SUCCESS,
        run_lifecycle=RunLifecycle.COMPLETED,
        job_state=JobState.SUCCEEDED,
        verdict=RunVerdict.BLOCK if evidence.verdict.value == "VULNERABLE" else RunVerdict.PASS,
        reason_codes=(),
        cleanup=CleanupResult(status=CleanupStatus.SUCCEEDED, finished_at_us=100 if run_id == RUN_ONE else 200),
        error=None,
        plan_fingerprint=snapshot.plan.plan_fingerprint,
        coverage_record_count=len(snapshot.plan.coverage),
        coverage_gap_count=0,
        evidence=(evidence,),
        artifacts=(),
    )
