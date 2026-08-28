# 验证协议与 Schema中的执行配置协议。

from __future__ import annotations

import json
from pathlib import Path

import pytest

from product.backend.core.errors import JiejianError
from product.backend.core.verification.permissions import PermissionContract
from product.backend.workflows.context import ApplicationCore
from product.protocols import (
    PreparedCookieCredential,
    PreparedCookieSessionIdentityBinding,
    TargetType,
    WebExecutionIdentity,
    WebExecutionProfile,
    WebExecutionSnapshot,
)
from product.protocols.web.profile import (
    _reject_secret_material,
    canonical_web_execution_profile_json_bytes,
    parse_web_execution_profile,
)
from tests.fixtures.runner import execution_snapshot


def _profile(profile_id: str = "profile-runner") -> WebExecutionProfile:
    snapshot = execution_snapshot()
    return WebExecutionProfile(
        profile_id=profile_id, project_id=snapshot.project_id, project_name=snapshot.project_name,
        target_type=TargetType.WEB, target=snapshot.target,
        identities=snapshot.identities,
        contract_id=snapshot.contract.contract_id, contract_version=snapshot.contract.version,
        observers=snapshot.observers, subject_bindings=snapshot.subject_bindings,
        workflow_bindings=snapshot.workflow_bindings, effect_bindings=snapshot.effect_bindings,
        observer_bindings=snapshot.observer_bindings,
        seed=4, case_budget=1, max_relation_depth=8, max_duration_us=20_000_000,
    )


def _write_profile(path: Path, profile: WebExecutionProfile) -> None:
    path.write_bytes(canonical_web_execution_profile_json_bytes(profile))


def test_profile_roundtrip_has_explicit_contract_reference_only() -> None:
    profile = _profile()
    encoded = canonical_web_execution_profile_json_bytes(profile)
    assert parse_web_execution_profile(encoded) == profile
    payload = json.loads(encoded)
    assert payload["target_type"] == "WEB"
    assert payload["contract_id"] == profile.contract_id
    assert "contract" not in payload and "flow" not in payload


def test_profile_accepts_only_typed_prepared_cookie_descriptors() -> None:
    source = _profile()
    identity = WebExecutionIdentity(
        identity_id=source.identities[0].identity_id,
        role=source.identities[0].role,
        binding=PreparedCookieSessionIdentityBinding(
            cookies=(
                PreparedCookieCredential(
                    name="sample_session",
                    domain="127.0.0.1",
                    path="/",
                    secure=False,
                    value_ref="env:JIEJIAN_TEST_IDENTITY_COOKIE",
                ),
            )
        ),
    )
    payload = source.model_dump(mode="python")
    payload["identities"] = (identity,)

    profile = WebExecutionProfile.model_validate(payload)

    assert profile.identities == (identity,)
    with pytest.raises(ValueError, match="sensitive field"):
        _reject_secret_material(
            {"workflow_bindings": [{"cookies": [{"value_ref": "env:SAFE_REFERENCE"}]}]}
        )


def test_profile_secret_scan_ignores_empty_optional_metadata() -> None:
    _reject_secret_material(
        {"workflow_bindings": [{"response_extractors": [{"cookie_name": None}]}]}
    )

    with pytest.raises(ValueError, match="sensitive field"):
        _reject_secret_material(
            {"workflow_bindings": [{"response_extractors": [{"cookie_name": "session"}]}]}
        )


def test_checked_in_web_execution_profile_schema_has_no_drift() -> None:
    schema_path = (
        Path(__file__).parents[3]
        / "product/protocols/schemas/execution/web-execution-profile.schema.json"
    )
    assert json.loads(schema_path.read_text(encoding="utf-8")) == (
        WebExecutionProfile.model_json_schema()
    )


@pytest.mark.parametrize("completion_binding", ["missing_requirement", "resource_state"])
def test_snapshot_rejects_missing_or_non_async_completion_binding(
    completion_binding: str,
) -> None:
    payload = execution_snapshot().model_dump(mode="python")
    payload["workflow_bindings"][0]["steps"][0]["classifier"]["completion_binding"] = completion_binding
    payload["workflow_bindings"][0]["workflow_fingerprint"] = None

    with pytest.raises(ValueError, match="EVENTUAL async task observer"):
        WebExecutionSnapshot.model_validate(payload)


def test_snapshot_accepts_corroborating_observer_with_matching_optional_spec() -> None:
    source = execution_snapshot()
    payload = source.model_dump(mode="python")
    supporting_spec = source.observers[0].model_dump(mode="python")
    supporting_spec.update({"observer_id": "support_observer", "required": False})
    supporting_binding = source.observer_bindings[0].model_dump(mode="python")
    supporting_binding.update(
        {"requirement_id": "support_state", "observer_id": "support_observer"}
    )
    effect_binding = payload["effect_bindings"][0]
    effect_binding["corroborating_channels"] = ("support_state",)
    payload["observers"] = (*payload["observers"], supporting_spec)
    payload["observer_bindings"] = (*payload["observer_bindings"], supporting_binding)

    snapshot = WebExecutionSnapshot.model_validate(payload)

    assert snapshot.observers[-1].required is False
    assert snapshot.effect_bindings[0].corroborating_channels == ("support_state",)


def test_snapshot_rejects_corroborating_observer_with_required_spec() -> None:
    source = execution_snapshot()
    payload = source.model_dump(mode="python")
    supporting_spec = source.observers[0].model_dump(mode="python")
    supporting_spec["observer_id"] = "support_observer"
    supporting_binding = source.observer_bindings[0].model_dump(mode="python")
    supporting_binding.update(
        {"requirement_id": "support_state", "observer_id": "support_observer"}
    )
    payload["effect_bindings"][0]["corroborating_channels"] = ("support_state",)
    payload["observers"] = (*payload["observers"], supporting_spec)
    payload["observer_bindings"] = (*payload["observer_bindings"], supporting_binding)

    with pytest.raises(ValueError, match="stable role"):
        WebExecutionSnapshot.model_validate(payload)


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


def profile_contract(profile: WebExecutionProfile) -> PermissionContract:
    return execution_snapshot().contract
