from __future__ import annotations

import json
from pathlib import Path

import pytest

from product.backend.core.errors import JiejianError
from product.backend.core.verification.permissions import PermissionContract
from product.backend.workflows.context import ApplicationCore
from product.protocols import ExecutionIdentity, ExecutionProfile, TargetType
from product.protocols.execution_profile import canonical_execution_profile_json_bytes, parse_execution_profile
from tests.fixtures.runner import execution_snapshot


def _profile(profile_id: str = "profile-runner") -> ExecutionProfile:
    snapshot = execution_snapshot()
    return ExecutionProfile(
        profile_id=profile_id, project_id=snapshot.project_id, project_name=snapshot.project_name,
        target_type=TargetType.WEB, target=snapshot.target,
        identities=tuple(ExecutionIdentity(schema_version="2", id=item.id, role=item.role, secret_ref=item.secret_ref) for item in snapshot.identities),
        contract_id=snapshot.contract.contract_id, contract_version=snapshot.contract.version,
        observers=snapshot.observers, subject_bindings=snapshot.subject_bindings,
        action_bindings=snapshot.action_bindings, observer_bindings=snapshot.observer_bindings,
        seed=4, case_budget=1, max_relation_depth=8, max_duration_us=20_000_000,
    )


def _write_profile(path: Path, profile: ExecutionProfile) -> None:
    path.write_bytes(canonical_execution_profile_json_bytes(profile))


def test_profile_roundtrip_has_explicit_contract_reference_only() -> None:
    profile = _profile()
    encoded = canonical_execution_profile_json_bytes(profile)
    assert parse_execution_profile(encoded) == profile
    payload = json.loads(encoded)
    assert payload["target_type"] == "WEB"
    assert payload["contract_id"] == profile.contract_id
    assert "contract" not in payload and "flow" not in payload


def test_profile_registration_requires_active_governed_version_and_rejects_drift(tmp_path: Path) -> None:
    source = tmp_path / "profile.json"
    profile = _profile()
    _write_profile(source, profile)
    application = ApplicationCore(tmp_path / "var", environ={})
    try:
        application.projects.register(source)
        project = application.projects.get(profile.project_id)
        assert project.governed_contract_id is None
        assert project.governed_contract_version is None
        draft = application.contracts.create_draft(
            profile.project_id, profile.contract_id, snapshot=profile_contract(profile), actor="test"
        )
        reviewed = application.contracts.submit_review(profile.project_id, profile.contract_id, draft.version, actor="test")
        application.contracts.activate_review(profile.project_id, profile.contract_id, reviewed.version, actor="test")
        record = application.execution.register(source)
        assert application.execution.current(record.profile_id).contract_id == profile.contract_id
        changed = profile.model_copy(update={"seed": 5})
        _write_profile(source, changed)
        with pytest.raises(JiejianError, match="漂移"):
            application.execution.register(source)
        updated = application.execution.register(source, accept_source_changes=True)
        assert updated.source_hash != record.source_hash
    finally:
        application.close()


def profile_contract(profile: ExecutionProfile) -> PermissionContract:
    return execution_snapshot().contract
