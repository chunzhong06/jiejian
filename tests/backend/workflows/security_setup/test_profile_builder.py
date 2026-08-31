# 验证 SecuritySetup Profile builder 的执行 Profile 与可运行范围。

from pathlib import Path
import pytest
from product.backend.core.application_understanding import (
    CandidateConfidence,
    CandidateDecision,
    CandidateOrigin,
    RoleCandidate,
)
from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.core.permission_intent import PermissionIntentRelation
from product.backend.core.test_identity import (
    TestIdentity as IdentityRecord,
    TestIdentityAuthMethod as IdentityAuthMethod,
)
from product.backend.core.verification.permissions import PermissionExpectation
from product.backend.composition import ApplicationCore
from product.protocols import HttpPredicateKind
from product.protocols.web.profile import parse_web_execution_profile
from tests.backend.workflows.recording.test_action_safety_setup import (
    ACTION_ID,
    ENDPOINT_FINGERPRINT,
    IDENTITY_ID,
    NOW_US,
    PROJECT_ID,
    RECORDING_ID,
    ROLE_ID,
    _FakeSecretStore,
    _confirmation,
    _persist_completed_recording,
)
pytestmark = pytest.mark.database
PEER_IDENTITY_ID = "tid_" + "7" * 32
REPLACEMENT_IDENTITY_ID = "tid_" + "6" * 32
OTHER_ROLE_ID = "role_" + "8" * 32
OTHER_IDENTITY_ID = "tid_" + "6" * 32
OTHER_LATER_IDENTITY_ID = "tid_" + "9" * 32

def test_other_role_uses_stable_prepared_representative_and_keeps_partial_scope_runnable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from tests.backend.workflows.recording import test_action_safety_setup as setup_fixture

    original_understanding = setup_fixture._understanding

    def understanding_with_other_role():
        current = original_understanding()
        other = RoleCandidate(
            candidate_id=OTHER_ROLE_ID,
            canonical_key="member",
            display_name="成员",
            confidence=CandidateConfidence.HIGH,
            decision=CandidateDecision.CONFIRMED,
            origin=CandidateOrigin.MANUAL,
        )
        return current.model_copy(
            update={"role_candidates": (*current.role_candidates, other)}
        )

    monkeypatch.setattr(setup_fixture, "_understanding", understanding_with_other_role)
    store = _FakeSecretStore()
    owner_ref = f"cred:jiejian/test-identity/{PROJECT_ID}/{IDENTITY_ID}/bearer"
    store.write(owner_ref, "owner-secret")
    core = ApplicationCore(
        tmp_path / "var",
        secret_store=store,
        clock_us=lambda: NOW_US + 100,
    )
    try:
        _persist_completed_recording(core, owner_ref)
        setup_preview = core.action_safety_setup.preview(RECORDING_ID)
        core.action_safety_setup.confirm(
            RECORDING_ID,
            _confirmation(setup_preview, include_recovery=True),
        )
        _add_prepared_identity(
            core,
            store,
            OTHER_IDENTITY_ID,
            role_id=OTHER_ROLE_ID,
            role_key="member",
            role_name="成员",
        )
        core.permission_intents.confirm(
            PROJECT_ID,
            ACTION_ID,
            ROLE_ID,
            ROLE_ID,
            PermissionIntentRelation.OWNS,
            expectation=PermissionExpectation.ALLOW,
        )
        core.permission_intents.confirm(
            PROJECT_ID,
            ACTION_ID,
            OTHER_ROLE_ID,
            ROLE_ID,
            PermissionIntentRelation.OTHER_ROLE,
            expectation=PermissionExpectation.DENY,
        )
        first = core.permission_intents.execution_intents(PROJECT_ID)
        other = next(
            item
            for item in first
            if item.revision.relation is PermissionIntentRelation.OTHER_ROLE
        )
        assert other.subject_test_identity_id == OTHER_IDENTITY_ID

        _add_prepared_identity(
            core,
            store,
            OTHER_LATER_IDENTITY_ID,
            role_id=OTHER_ROLE_ID,
            role_key="member",
            role_name="成员",
        )
        second = core.permission_intents.execution_intents(PROJECT_ID)
        stable = next(
            item
            for item in second
            if item.revision.relation is PermissionIntentRelation.OTHER_ROLE
        )
        assert stable.subject_test_identity_id == OTHER_IDENTITY_ID

        core.security_setup.compile(PROJECT_ID)
        preview = core.checks.preview(PROJECT_ID)
        assert preview.ready is True
        assert preview.gaps
        readiness = core.project_readiness.get(PROJECT_ID)
        assert readiness.current_scope_runnable is True
        assert readiness.remaining_gap_count > 0
        assert readiness.confirmed_permission_requirement_count == 2
        assert readiness.executable_permission_requirement_count == 2
    finally:
        core.close()

def _add_prepared_identity(
    core: ApplicationCore,
    store: _FakeSecretStore,
    identity_id: str,
    *,
    role_id: str,
    role_key: str,
    role_name: str,
) -> str:
    secret_ref = f"cred:jiejian/test-identity/{PROJECT_ID}/{identity_id}/bearer"
    store.write(secret_ref, f"secret-{identity_id[-4:]}")
    with core.uow_factory() as work:
        work.test_identities.add(
            _identity_record(
                identity_id,
                secret_ref,
                role_id=role_id,
                role_key=role_key,
                role_name=role_name,
            )
        )
        work.commit()
    return secret_ref

def _identity_record(
    identity_id: str,
    secret_ref: str,
    *,
    role_id: str,
    role_key: str,
    role_name: str,
) -> IdentityRecord:
    return IdentityRecord(
        identity_id=identity_id,
        project_id=PROJECT_ID,
        role_candidate_id=role_id,
        role_canonical_key=role_key,
        role_display_name=role_name,
        label=f"{role_name}测试账号",
        confirmed_endpoint="http://127.0.0.1:18080",
        endpoint_source_fingerprint=ENDPOINT_FINGERPRINT,
        understanding_revision=3,
        auth_method=IdentityAuthMethod.BEARER,
        bearer_secret_ref=secret_ref,
        prepared_at_us=NOW_US + 1,
        refreshed_at_us=NOW_US + 1,
        created_at_us=NOW_US,
        updated_at_us=NOW_US + 1,
    )
