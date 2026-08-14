from __future__ import annotations

import json
import os
import secrets
from pathlib import Path
from threading import Thread

import pytest

from jiejian.application.context import ApplicationContext
from jiejian.execution.dispatch import WorkerDispatcher
from jiejian.execution.permission_execution import PermissionExecutionService
from jiejian.execution.permission_profile import (
    PermissionExecutionProfileV2,
    canonical_permission_execution_profile_json_bytes,
    parse_permission_execution_profile,
)
from jiejian.permission_sample_app import create_permission_sample_server
from jiejian.domain.lifecycle import RunVerdict
from jiejian.verification.permissions import PermissionContractV2


ROOT = Path(__file__).resolve().parents[2]
SAMPLE_ROOT = ROOT / "samples"
SECRET_NAMES = (
    "JIEJIAN_PERMISSION_MEMBER_A",
    "JIEJIAN_PERMISSION_MEMBER_A2",
    "JIEJIAN_PERMISSION_MEMBER_B",
    "JIEJIAN_PERMISSION_DEPT_ADMIN_A",
    "JIEJIAN_PERMISSION_DEPT_ADMIN_A2",
    "JIEJIAN_PERMISSION_TENANT_ADMIN_A",
    "JIEJIAN_PERMISSION_PEER_A",
    "JIEJIAN_PERMISSION_OWNER_OBSERVER",
)


def _temporary_environment() -> dict[str, str]:
    return {name: secrets.token_urlsafe(24) for name in SECRET_NAMES}


def _profile_asset(variant: str) -> Path:
    return SAMPLE_ROOT / f"{variant}_apps" / "permissions_v2" / "profile.json"


def _dynamic_profile(variant: str, source: Path, destination: Path, port: int) -> PermissionExecutionProfileV2:
    profile = PermissionExecutionProfileV2.model_validate_json(source.read_bytes())
    dynamic_id = f"{variant}-profile-e2e"
    target = profile.target.model_copy(
        update={
            "base_url": f"http://127.0.0.1:{port}",
            "allowed_origins": (f"http://127.0.0.1:{port}",),
            "allowed_ports": (port,),
        }
    )
    result = profile.model_copy(
        update={
            "profile_id": dynamic_id,
            "project_id": dynamic_id,
            "project_name": f"{variant} dynamic permissions",
            "target": target,
        }
    )
    destination.write_bytes(canonical_permission_execution_profile_json_bytes(result) + b"\n")
    return result


def _assert_no_secret_bytes(root: Path, secrets_to_find: tuple[str, ...]) -> None:
    for path in root.rglob("*"):
        if path.is_file():
            content = path.read_bytes()
            assert not any(value.encode("utf-8") in content for value in secrets_to_find)


@pytest.mark.e2e
@pytest.mark.database
@pytest.mark.process
@pytest.mark.slow
@pytest.mark.parametrize(
    ("variant", "expected"),
    (("fixed", RunVerdict.PASS), ("vulnerable", RunVerdict.BLOCK), ("inconclusive", RunVerdict.INCONCLUSIVE)),
)
def test_permission_profile_worker_runner_publication_loop(
    variant: str,
    expected: RunVerdict,
    tmp_path: Path,
) -> None:
    secret_values = _temporary_environment()
    process_environment = {**os.environ, **secret_values}
    tokens = {
        "member-a": secret_values["JIEJIAN_PERMISSION_MEMBER_A"],
        "member-a2": secret_values["JIEJIAN_PERMISSION_MEMBER_A2"],
        "member-b": secret_values["JIEJIAN_PERMISSION_MEMBER_B"],
        "dept-admin-a": secret_values["JIEJIAN_PERMISSION_DEPT_ADMIN_A"],
        "dept-admin-a2": secret_values["JIEJIAN_PERMISSION_DEPT_ADMIN_A2"],
        "tenant-admin-a": secret_values["JIEJIAN_PERMISSION_TENANT_ADMIN_A"],
        "peer-a": secret_values["JIEJIAN_PERMISSION_PEER_A"],
    }
    root = tmp_path / variant
    var_dir = root / "var"
    database_path = root / "target.sqlite"
    server = create_permission_sample_server(
        variant=variant,
        port=0,
        tokens=tokens,
        database_path=database_path,
        observer_token=secret_values["JIEJIAN_PERMISSION_OWNER_OBSERVER"],
    )
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    context: ApplicationContext | None = None
    process = None
    try:
        source = _profile_asset(variant)
        profile_path = root / "profile.json"
        profile = _dynamic_profile(variant, source, profile_path, server.server_port)
        plan = PermissionExecutionService._compile_plan(profile)
        assert not plan.gaps
        expected_count = json.loads(source.with_name("scenario.json").read_text(encoding="utf-8"))["formal_profile"]["retained_case_count"]
        assert len(plan.cases) == expected_count
        merged = next(
            case for case in plan.cases
            if case.subject_id == "peer-a" and case.action_id == "modify"
        )
        assert {dimension.value for dimension in merged.dimensions} == {"ROLE", "RELATION"}
        assert tuple(expectation.value for expectation in merged.expectations) == ("DENY",)

        context = ApplicationContext(var_dir, environ=process_environment)
        record = context.permission_execution.register(profile_path)
        submitted, request, secret_names = context.permission_execution.submit(
            record.profile_id,
            project_id=record.project_id,
            idempotency_key=f"{variant}-profile-e2e",
            max_attempts=1,
        )
        process = WorkerDispatcher(
            var_dir=var_dir,
            uow_factory=context.uow_factory,
            environ=process_environment,
        ).start(
            job_id=submitted.job.job_id,
            lease_owner="profile-e2e-worker",
            secret_names=secret_names,
        )
        dispatcher = WorkerDispatcher(
            var_dir=var_dir,
            uow_factory=context.uow_factory,
            environ=process_environment,
        )
        published = dispatcher.wait(
            submitted.job.job_id,
            process,
            known_secrets=tuple(secret_values.values()),
            timeout_seconds=180,
        )
        assert published.result.result_type.value == "SUCCESS"
        assert published.result.verdict is expected
        view = context.results.read(submitted.run.run_id)
        assert view.publication.result.verdict is expected
        assert len(view.evidence) == len(request.project_snapshot.plan.cases)
        assert view.publication.result.coverage_gap_count == 0
        assert context.results.overview(submitted.run.run_id, published=view)["execution_schema_version"] == "2"
        process.wait(timeout=10)
        assert process.poll() is not None
        _assert_no_secret_bytes(var_dir, tuple(secret_values.values()))
    finally:
        if process is not None and process.poll() is None:
            process.terminate()
            process.wait(timeout=10)
        if context is not None:
            context.close()
        server.shutdown()
        server.server_close()
        thread.join(timeout=10)
        assert not thread.is_alive()


def test_checked_in_permission_profiles_are_strict_identical_and_gap_free() -> None:
    profiles = []
    contracts = []
    for variant in ("fixed", "vulnerable", "inconclusive"):
        profile_path = _profile_asset(variant)
        profile = parse_permission_execution_profile(profile_path.read_bytes())
        profile_bytes = canonical_permission_execution_profile_json_bytes(profile)
        assert profile_bytes.rstrip() == profile_path.read_bytes().rstrip()
        plan = PermissionExecutionService._compile_plan(profile)
        assert not plan.gaps
        profiles.append(profile)
        contracts.append(profile.contract)
        scenario = json.loads((profile_path.parent / "scenario.json").read_text(encoding="utf-8"))
        truth = json.loads((profile_path.parent / "truth.json").read_text(encoding="utf-8"))
        assert len(plan.cases) == scenario["formal_profile"]["retained_case_count"]
        assert scenario["formal_profile"]["project_id"] == profile.project_id
        assert truth["formal_profile"]["run_verdict"] == {
            "fixed": "PASS",
            "vulnerable": "BLOCK",
            "inconclusive": "INCONCLUSIVE",
        }[variant]
        asset_contract = PermissionContractV2.model_validate_json(
            (profile_path.parent / "contract.json").read_bytes()
        )
        assert profile.contract == asset_contract
    assert contracts[0] == contracts[1] == contracts[2]
