# 验证端到端安全闭环中的授权安全闭环。

from __future__ import annotations

import json
import os
import secrets
import urllib.request
from http import HTTPStatus
from urllib.error import HTTPError
from pathlib import Path
from threading import Thread

import pytest

from product.backend.core.lifecycle import RunVerdict
from product.backend.core.verification.permissions import PermissionContract
from product.backend.infra.runtime.jobs.dispatch import WorkerDispatcher
from product.backend.workflows.context import ApplicationCore
from product.backend.workflows.runs.execution import ExecutionWorkflow
from product.protocols.web.profile import (
    WebExecutionProfile,
    canonical_web_execution_profile_json_bytes,
    parse_web_execution_profile,
)
from samples.web.target.server import create_authorization_sample_server


ROOT = Path(__file__).resolve().parents[2]
SAMPLE_ROOT = ROOT / "samples" / "web"
SECRET_NAMES = (
    "JIEJIAN_AUTHORIZATION_OWNER_TOKEN",
    "JIEJIAN_AUTHORIZATION_ATTACKER_TOKEN",
    "JIEJIAN_AUTHORIZATION_PEER_TOKEN",
    "JIEJIAN_AUTHORIZATION_OWNER_OBSERVER",
)
MACHINE_ID_SENSITIVE_WORDS = (
    "authorization",
    "bearer",
    "cookie",
    "credential",
    "password",
    "passwd",
    "secret",
    "token",
    "api-key",
    "apikey",
)


def _temporary_environment() -> dict[str, str]:
    return {name: secrets.token_urlsafe(24) for name in SECRET_NAMES}


def _dynamic_profile(variant: str, source: Path, destination: Path, port: int) -> WebExecutionProfile:
    profile = WebExecutionProfile.model_validate_json(source.read_bytes())
    dynamic_id = f"permission-check-{variant}-e2e"
    scope = profile.target.scope.model_copy(
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
            "project_name": f"Permission check {variant} sample",
            "target": profile.target.model_copy(update={"scope": scope}),
        }
    )
    destination.write_bytes(canonical_web_execution_profile_json_bytes(result) + b"\n")
    return result


def _assert_no_secret_bytes(root: Path, secrets_to_find: tuple[str, ...]) -> None:
    for path in root.rglob("*"):
        if path.is_file():
            content = path.read_bytes()
            assert not any(value.encode("utf-8") in content for value in secrets_to_find)


def _assert_safe_machine_id(value: str) -> None:
    lowered = value.casefold()
    assert not any(word in lowered for word in MACHINE_ID_SENSITIVE_WORDS)


def _assert_target_boundaries(server, token: str) -> None:
    invalid_path = urllib.request.Request(
        f"http://127.0.0.1:{server.server_port}/invalid",
        data=b'{"value":"x"}',
        method="PATCH",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    with pytest.raises(HTTPError) as invalid_error:
        urllib.request.urlopen(invalid_path, timeout=3)
    assert invalid_error.value.code == HTTPStatus.NOT_FOUND

    oversized = urllib.request.Request(
        f"http://127.0.0.1:{server.server_port}/resources/owner-resource",
        data=b'{"value":"' + b"x" * 9000 + b'"}',
        method="PATCH",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    with pytest.raises(HTTPError) as oversized_error:
        urllib.request.urlopen(oversized, timeout=3)
    assert oversized_error.value.code == HTTPStatus.REQUEST_ENTITY_TOO_LARGE


def _reset_target(server, *, variant: str, observer_token: str) -> None:
    request = urllib.request.Request(
        f"http://127.0.0.1:{server.server_port}/reset",
        method="POST",
        headers={"X-Jiejian-Test-Mode": "1"},
    )
    with urllib.request.urlopen(request, timeout=3) as response:
        assert response.status == HTTPStatus.OK
    request = urllib.request.Request(
        f"http://127.0.0.1:{server.server_port}/owner/resources/owner-resource",
        headers={"Authorization": f"Bearer {observer_token}"},
    )
    try:
        response_context = urllib.request.urlopen(request, timeout=3)
    except HTTPError as error:
        assert variant == "inconclusive"
        assert error.code == HTTPStatus.SERVICE_UNAVAILABLE
        return
    with response_context as response:
        assert response.status == HTTPStatus.OK
        assert json.loads(response.read())["value"] == "initial-owner-value"


def test_authorization_sample_keeps_bounded_test_controls() -> None:
    owner_token = "sample-owner-control"
    canary = "sample-secret-canary"
    server = create_authorization_sample_server(
        variant="fixed",
        port=0,
        tokens={"owner": owner_token, "attacker": "sample-attacker", "peer": "sample-peer"},
        observer_token="sample-observer",
        fail_cleanup=True,
        echo_secret=canary,
        request_delay_seconds=0.001,
    )
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        request = urllib.request.Request(
            f"http://127.0.0.1:{server.server_port}/resources/owner-resource",
            headers={
                "Authorization": f"Bearer {owner_token}",
                "X-Jiejian-Runner-PID": "4242",
            },
        )
        with urllib.request.urlopen(request, timeout=3) as response:
            payload = json.loads(response.read())
        assert payload["ordinary_field"] == f"prefix::{canary}::suffix"
        assert payload["nested"] == {"items": [canary]}
        assert server.runner_process_ids == [4242]
        assert server.request_delay_seconds == 0.001
        reset = urllib.request.Request(
            f"http://127.0.0.1:{server.server_port}/reset",
            method="POST",
            headers={"X-Jiejian-Test-Mode": "1"},
        )
        with pytest.raises(HTTPError) as failed_cleanup:
            urllib.request.urlopen(reset, timeout=3)
        assert failed_cleanup.value.code == HTTPStatus.INTERNAL_SERVER_ERROR
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
        assert not thread.is_alive()


@pytest.mark.e2e
@pytest.mark.database
@pytest.mark.process
@pytest.mark.slow
@pytest.mark.essential
@pytest.mark.parametrize("variant", ("fixed", "vulnerable", "inconclusive"))
def test_authorization_profile_worker_runner_publication_loop(variant: str, tmp_path: Path) -> None:
    secret_values = _temporary_environment()
    process_environment = {**os.environ, **secret_values}
    server = create_authorization_sample_server(
        variant=variant,
        port=0,
        tokens={
            "owner": secret_values["JIEJIAN_AUTHORIZATION_OWNER_TOKEN"],
            "attacker": secret_values["JIEJIAN_AUTHORIZATION_ATTACKER_TOKEN"],
            "peer": secret_values["JIEJIAN_AUTHORIZATION_PEER_TOKEN"],
        },
        observer_token=secret_values["JIEJIAN_AUTHORIZATION_OWNER_OBSERVER"],
    )
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    _assert_target_boundaries(server, secret_values["JIEJIAN_AUTHORIZATION_ATTACKER_TOKEN"])
    context: ApplicationCore | None = None
    process = None
    try:
        source = SAMPLE_ROOT / variant / "profile.json"
        profile_path = tmp_path / "profile.json"
        profile = _dynamic_profile(variant, source, profile_path, server.server_port)
        contract = PermissionContract.model_validate_json(source.with_name("contract.json").read_bytes(), strict=True)
        plan = ExecutionWorkflow._compile_plan(profile, contract)
        assert not plan.gaps
        scenario_data = json.loads(source.with_name("scenario.json").read_text(encoding="utf-8"))
        assert len(plan.cases) == scenario_data["formal_profile"]["required_case_count"]
        assert any(
            case.action_id == "modify"
            and tuple(expectation.value for expectation in case.expectations) == ("DENY",)
            and "resource_state" in case.required_observations
            for case in plan.cases
        )

        context = ApplicationCore(tmp_path / "var", environ=process_environment)
        context.projects.register(profile_path)
        draft = context.contracts.create_draft(profile.project_id, contract.contract_id, snapshot=contract, actor="e2e")
        reviewed = context.contracts.submit_review(profile.project_id, contract.contract_id, draft.version, actor="e2e")
        context.contracts.activate_review(profile.project_id, contract.contract_id, reviewed.version, actor="e2e")
        record = context.execution.register(profile_path)
        submitted, request, runner_secret_names = context.execution.submit(
            record.profile_id,
            project_id=record.project_id,
            idempotency_key=f"permission-check-{variant}-e2e",
            max_attempts=1,
        )
        process = WorkerDispatcher(
            var_dir=tmp_path / "var",
            uow_factory=context.uow_factory,
            environ=process_environment,
        ).start(
            job_id=submitted.job.job_id,
            lease_owner="permission-check-e2e-worker",
            secret_names=runner_secret_names,
        )
        dispatcher = WorkerDispatcher(var_dir=tmp_path / "var", uow_factory=context.uow_factory, environ=process_environment)
        published = dispatcher.wait(
            submitted.job.job_id,
            process,
            known_secrets=tuple(secret_values.values()),
            timeout_seconds=180,
        )
        assert published.result.result_type.value == "SUCCESS"
        view = context.results.read(submitted.run.run_id)
        truth = json.loads(source.with_name("truth.json").read_text(encoding="utf-8"))
        expected = RunVerdict(truth["formal_profile"]["run_verdict"])
        assert published.result.verdict is expected
        assert view.publication.result.verdict is expected
        paired_case_ids = {
            case.case_id
            for twin in request.project_snapshot.differential_plan.twins
            for case in (twin.allow_case, twin.deny_case)
        }
        expected_evidence_count = (
            2 * len(request.project_snapshot.differential_plan.twins)
            + sum(case.case_id not in paired_case_ids for case in request.project_snapshot.plan.cases)
        )
        assert len(view.evidence) == expected_evidence_count
        assert view.publication.result.coverage_gap_count == truth["formal_profile"]["coverage_gaps"]
        assert context.results.overview(submitted.run.run_id, published=view)["execution_schema_version"] == "1"
        _reset_target(
            server,
            variant=variant,
            observer_token=secret_values["JIEJIAN_AUTHORIZATION_OWNER_OBSERVER"],
        )
        process.wait(timeout=10)
        assert process.poll() is not None
        _assert_no_secret_bytes(tmp_path / "var", tuple(secret_values.values()))
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


def test_checked_in_authorization_profiles_are_strict_identical_and_gap_free() -> None:
    contracts = []
    for variant in ("fixed", "vulnerable", "inconclusive"):
        asset_dir = SAMPLE_ROOT / variant
        profile_path = asset_dir / "profile.json"
        profile = parse_web_execution_profile(profile_path.read_bytes())
        assert canonical_web_execution_profile_json_bytes(profile).rstrip() == profile_path.read_bytes().rstrip()
        contract = PermissionContract.model_validate_json((asset_dir / "contract.json").read_bytes(), strict=True)
        plan = ExecutionWorkflow._compile_plan(profile, contract)
        assert not plan.gaps
        assert plan.cases
        contracts.append(contract)
        scenario_data = json.loads((asset_dir / "scenario.json").read_text(encoding="utf-8"))
        truth = json.loads((asset_dir / "truth.json").read_text(encoding="utf-8"))
        for machine_id in (
            profile.profile_id,
            profile.project_id,
            profile.contract_id,
            contract.contract_id,
            scenario_data["formal_profile"]["project_id"],
        ):
            _assert_safe_machine_id(machine_id)
        assert len(plan.cases) == scenario_data["formal_profile"]["required_case_count"]
        assert scenario_data["formal_profile"]["project_id"] == profile.project_id
        assert RunVerdict(truth["formal_profile"]["run_verdict"]) in {
            RunVerdict.PASS,
            RunVerdict.BLOCK,
            RunVerdict.INCONCLUSIVE,
        }
    assert contracts[0] == contracts[1] == contracts[2]
