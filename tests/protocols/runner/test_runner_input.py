# 验证 RunnerInput 与 Web snapshot 的严格输入边界。

from __future__ import annotations
import json
from pathlib import Path
import pytest
from product.backend.core.lifecycle import CaseVerdict, JobState, RunLifecycle, RunVerdict
from product.backend.core.errors import JiejianError
from product.backend.core.verification.facts import ExecutionOutcome, ObservedEffect, TargetType
from product.protocols import (
    CleanupResult,
    CleanupIssue,
    CleanupIssueCode,
    CleanupStatus,
    Evidence,
    PreparedCookieCredential,
    PreparedCookieSessionIdentityBinding,
    ResponseExtractor,
    ResponseExtractorKind,
    RunnerInput,
    RunnerFailurePhase,
    RunnerResult,
    RunnerResultType,
    WebExecutionIdentity,
    WebExecutionSnapshot,
    build_evidence,
    canonical_runner_json_bytes,
    canonical_runner_sha256,
    parse_runner_result,
    parse_runner_input,
)
from product.protocols.runner.result import _reject_secret_material
from tests.fixtures.runner import evidence, runner_input
pytestmark = pytest.mark.essential

def test_current_runner_input_round_trips_with_web_target_and_execution_binding() -> None:
    document = runner_input()
    raw = canonical_runner_json_bytes(document)
    assert parse_runner_input(raw) == document
    assert document.project_snapshot.target_type is TargetType.WEB
    assert canonical_runner_sha256(document) == canonical_runner_sha256(parse_runner_input(raw))


def test_recorded_response_extractor_round_trips_across_snapshot_and_runner() -> None:
    source = runner_input()
    extractor = ResponseExtractor(
        extractor_id="recorded-state",
        kind=ResponseExtractorKind.JSON_PATH,
        json_path="$.state",
    )
    snapshot_payload = source.project_snapshot.model_dump(mode="python")
    workflow = snapshot_payload["workflow_bindings"][0]
    step = workflow["steps"][0]
    step["output_extractors"] = (extractor,)
    step["request_template"]["response_extractors"] = (extractor,)
    workflow["workflow_fingerprint"] = None
    snapshot = WebExecutionSnapshot.model_validate(snapshot_payload)
    document = source.model_copy(update={"project_snapshot": snapshot})

    raw = canonical_runner_json_bytes(document)

    assert parse_runner_input(raw) == document
    with pytest.raises(ValueError, match="inline secret field"):
        _reject_secret_material({"password": "not-allowed"})
    with pytest.raises(JiejianError, match="known secret"):
        canonical_runner_json_bytes(
            document,
            known_secrets=(document.project_snapshot.project_name,),
        )

def test_runner_input_accepts_only_snapshot_cookie_descriptors() -> None:
    source = runner_input()
    existing = source.project_snapshot.identities[0]
    identity = WebExecutionIdentity(
        identity_id=existing.identity_id,
        role=existing.role,
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
    snapshot = source.project_snapshot.model_copy(
        update={"identities": (identity,)}
    )
    document = source.model_copy(update={"project_snapshot": snapshot})

    raw = canonical_runner_json_bytes(document)

    assert b"JIEJIAN_TEST_IDENTITY_COOKIE" in raw
    with pytest.raises(ValueError, match="inline secret field"):
        _reject_secret_material(
            {
                "project_snapshot": {
                    "workflow_bindings": [
                        {"cookies": [{"value_ref": "env:SAFE_REFERENCE"}]}
                    ]
                }
            }
        )


def test_runner_secret_boundary_allows_only_public_authorization_metadata() -> None:
    _reject_secret_material(
        {
            "credential_source": "session-cookie",
            "authorization_decision": "DENY",
            "origin_authorization_event_id": "authorization-event",
        }
    )

    with pytest.raises(ValueError, match="inline secret field"):
        _reject_secret_material({"credential": "session-cookie"})
    with pytest.raises(ValueError, match="inline secret material"):
        _reject_secret_material({"credential_source": "token=private-value"})
