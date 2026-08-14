from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from jiejian.api.app import create_app
from jiejian.cli.app import app as cli_app
from jiejian.execution import (
    PermissionExecutionProfileV2,
    canonical_permission_execution_profile_json_bytes,
    parse_permission_execution_profile,
    permission_execution_profile_sha256,
)
from jiejian.execution.permission_execution import PermissionExecutionService
from jiejian.protocols import runner_v2 as runner_v2_module
from jiejian.storage import create_sqlite_engine, default_database_path
from jiejian.errors import JiejianError
from typer.testing import CliRunner

from tests.execution.protocol.test_runner_v2 import _snapshot


def _profile(profile_id: str = "profile-runner") -> PermissionExecutionProfileV2:
    snapshot = _snapshot()
    return PermissionExecutionProfileV2(
        profile_id=profile_id,
        project_id=snapshot.project_id,
        project_name=snapshot.project_name,
        target=snapshot.target,
        identities=snapshot.identities,
        flow=snapshot.flow,
        contract=snapshot.contract,
        observers=snapshot.observers,
        subject_bindings=snapshot.subject_bindings,
        action_bindings=snapshot.action_bindings,
        observer_bindings=snapshot.observer_bindings,
        seed=4,
        case_budget=1,
        max_relation_depth=8,
        max_duration_us=20_000_000,
    )


def _write_profile(path: Path, profile: PermissionExecutionProfileV2) -> None:
    path.write_bytes(canonical_permission_execution_profile_json_bytes(profile))


def test_profile_canonical_schema_and_strict_parser() -> None:
    profile = _profile()
    encoded = canonical_permission_execution_profile_json_bytes(profile)
    assert parse_permission_execution_profile(encoded) == profile
    assert permission_execution_profile_sha256(profile) == permission_execution_profile_sha256(profile)
    assert json.loads(encoded) == json.loads(canonical_permission_execution_profile_json_bytes(profile))
    assert profile.model_json_schema() == json.loads(
        Path("schemas/execution/permission-execution-profile-v2.schema.json").read_text(
            encoding="utf-8"
        )
    )
    with pytest.raises(JiejianError):
        parse_permission_execution_profile(encoded[:-1] + b" ")
    duplicate = b'{"schema_version":"2","schema_version":"2"}'
    with pytest.raises(JiejianError):
        parse_permission_execution_profile(duplicate)


def test_profile_service_register_drift_revalidate_and_request(tmp_path: Path) -> None:
    source = tmp_path / "permission-profile.json"
    _write_profile(source, _profile())
    application = create_app(tmp_path / "var", start_worker=False).state.context
    try:
        record = application.permission_execution.register(source)
        request = application.permission_execution.build_request(
            record.profile_id,
            project_id=record.project_id,
        )
        assert request.schema_version == "2"
        assert request.project_snapshot.plan.plan_fingerprint == record.plan_fingerprint
        assert application.permission_execution.current(record.profile_id).profile_id == record.profile_id

        changed = _profile().model_copy(update={"seed": 5})
        _write_profile(source, changed)
        with pytest.raises(JiejianError) as error:
            application.permission_execution.register(source)
        assert error.value.code == "PERMISSION_PROFILE_SOURCE_DRIFT"
        updated = application.permission_execution.register(source, revalidate=True)
        assert updated.source_hash != record.source_hash

        engine = create_sqlite_engine(default_database_path(tmp_path / "var"))
        try:
            columns = {column["name"] for column in __import__("sqlalchemy").inspect(engine).get_columns("permission_execution_profiles")}
            assert "source_path" in columns and "contract_fingerprint" in columns
            assert "profile_json" not in columns and "plan_json" not in columns
        finally:
            engine.dispose()
    finally:
        application.close()


def test_profile_api_and_cli_use_v2_surfaces(tmp_path: Path) -> None:
    source = tmp_path / "permission-profile.json"
    _write_profile(source, _profile())
    with TestClient(create_app(tmp_path / "var", start_worker=False)) as client:
        response = client.post(
            "/api/v2/permission-execution-profiles",
            json={"schema_version": "2", "path": str(source)},
        )
        assert response.status_code == 201
        assert response.json()["data"]["profile_id"] == "profile-runner"
        listed = client.get(
            "/api/v2/projects/runner-project/permission-execution-profiles"
        )
        assert listed.status_code == 200
        assert len(listed.json()["data"]) == 1

    result = CliRunner().invoke(cli_app, ["permission-run", "--help"])
    assert result.exit_code == 0
    assert "Profile" in result.stdout
