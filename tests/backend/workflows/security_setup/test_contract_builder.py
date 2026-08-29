# 验证 SecuritySetup Contract builder 的权限意图与代表变化规则。

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
from product.backend.workflows.context import ApplicationCore
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

def test_group_intent_survives_missing_added_and_replaced_representative(
    tmp_path: Path,
) -> None:
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
        core.permission_intents.confirm(
            PROJECT_ID,
            ACTION_ID,
            ROLE_ID,
            ROLE_ID,
            PermissionIntentRelation.OWNS,
            expectation=PermissionExpectation.ALLOW,
        )
        initial = core.permission_intents.confirm(
            PROJECT_ID,
            ACTION_ID,
            ROLE_ID,
            ROLE_ID,
            PermissionIntentRelation.SAME_ROLE_OTHER_ACCOUNT,
            expectation=PermissionExpectation.DENY,
        )
        same_role = next(
            cell
            for cell in initial.actions[0].cells
            if cell.relation is PermissionIntentRelation.SAME_ROLE_OTHER_ACCOUNT
        )
        intent_hash = same_role.intent_hash
        initial_intent = next(
            item
            for item in core.permission_intents.current_intents(PROJECT_ID)
            if item.relation is PermissionIntentRelation.SAME_ROLE_OTHER_ACCOUNT
        )
        assert same_role.status.value == "CURRENT"
        assert same_role.execution_gap == "TEST_IDENTITY_MISSING"
        assert initial.actions[0].compilable is False

        peer_ref = _add_prepared_identity(
            core,
            store,
            PEER_IDENTITY_ID,
            role_id=ROLE_ID,
            role_key="owner",
            role_name="所有者",
        )
        with_peer = core.permission_intents.matrix(PROJECT_ID)
        selected = next(
            cell
            for cell in with_peer.actions[0].cells
            if cell.relation is PermissionIntentRelation.SAME_ROLE_OTHER_ACCOUNT
        )
        assert selected.intent_hash == intent_hash
        assert selected.representative_test_identity_id == PEER_IDENTITY_ID
        assert selected.execution_gap is None
        first = core.security_setup.compile(PROJECT_ID)

        replacement_ref = (
            f"cred:jiejian/test-identity/{PROJECT_ID}/{REPLACEMENT_IDENTITY_ID}/bearer"
        )
        store.write(replacement_ref, "replacement-secret")
        with core.uow_factory() as work:
            work.test_identities.delete(PEER_IDENTITY_ID)
            work.test_identities.add(
                _identity_record(
                    REPLACEMENT_IDENTITY_ID,
                    replacement_ref,
                    role_id=ROLE_ID,
                    role_key="owner",
                    role_name="所有者",
                )
            )
            work.commit()
        replaced = core.permission_intents.matrix(PROJECT_ID)
        replacement = next(
            cell
            for cell in replaced.actions[0].cells
            if cell.relation is PermissionIntentRelation.SAME_ROLE_OTHER_ACCOUNT
        )
        assert replacement.intent_hash == intent_hash
        assert replacement.representative_test_identity_id == REPLACEMENT_IDENTITY_ID
        replacement_intent = next(
            item
            for item in core.permission_intents.current_intents(PROJECT_ID)
            if item.relation is PermissionIntentRelation.SAME_ROLE_OTHER_ACCOUNT
        )
        assert replacement_intent.approval == initial_intent.approval
        assert replacement_intent.created_at_us == initial_intent.created_at_us
        second = core.security_setup.compile(PROJECT_ID)
        assert second.profile_id != first.profile_id
        assert peer_ref not in Path(second.profile_path).read_text(encoding="utf-8")

        with core.uow_factory() as work:
            owner = work.test_identities.get(IDENTITY_ID)
            assert owner is not None
            work.test_identities.replace(
                owner.model_copy(
                    update={
                        "auth_method": None,
                        "bearer_secret_ref": None,
                        "prepared_at_us": None,
                        "refreshed_at_us": None,
                        "updated_at_us": owner.updated_at_us + 1,
                    }
                )
            )
            work.commit()
        expired = core.permission_intents.matrix(PROJECT_ID)
        assert expired.confirmed_count == 2
        assert expired.representative_gap_count == 1
        assert "TEST_IDENTITY_NOT_PREPARED" in expired.actions[0].gaps
        assert "ACTION_SAFETY_SETUP_STALE" not in expired.actions[0].gaps

        with core.uow_factory() as work:
            understanding = work.application_understanding.get(PROJECT_ID)
            assert understanding is not None
            rejected_role = understanding.role_candidates[0].model_copy(
                update={"decision": CandidateDecision.REJECTED}
            )
            work.application_understanding.replace(
                understanding.model_copy(
                    update={
                        "role_candidates": (rejected_role,),
                        "revision": understanding.revision + 1,
                        "updated_at_us": understanding.updated_at_us + 1,
                    }
                )
            )
            work.commit()
        active = core.permission_intents.current_intents(PROJECT_ID)
        assert len(active) == 2
        core.permission_intents.refresh_bindings(PROJECT_ID)
        assert core.permission_intents.execution_intents(PROJECT_ID) == ()
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
