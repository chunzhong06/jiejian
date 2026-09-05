# 构造录制接受与动作技术绑定测试共用的正式 SQLite fixture。

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from product.backend.composition.application import ApplicationCore
from product.backend.core.application_understanding import (
    ActionCandidate,
    CandidateConfidence,
    CandidateDecision,
    CandidateEvidence,
    CandidateOrigin,
    RoleCandidate,
    candidate_id,
)
from product.backend.core.business_boundary import (
    ActionImplementationBinding,
    ActorImplementationBinding,
    BusinessAction,
    BusinessActor,
    boundary_sha256,
)
from product.backend.core.errors import JiejianError
from product.backend.core.lifecycle import ProjectStatus
from product.backend.core.permission_intent import ProjectPolicyState
from product.backend.core.recording import RecordingPurpose, RecordingState
from product.backend.core.test_identity import TestIdentity, TestIdentityAuthMethod
from product.backend.infra.storage import FlowDraftRevisionRecord, RecordingRecord
from product.backend.workflows.recording.source import recording_source_fingerprint
from product.protocols.flow_draft import (
    FlowDraft,
    FlowDraftResourceCandidate,
    FlowDraftStep,
    canonical_flow_draft_json_bytes,
)
from product.protocols.recording import RecordingEvent, RecordingEventKind
from product.protocols.web.workflow import ValueSlotConsumer

from tests.fixtures import assurance


class MemorySecretStore:
    """仅为离线测试提供按引用判断，不连接平台凭据管理器。"""

    def __init__(self) -> None:
        self._values: dict[str, str] = {}

    def write(self, secret_ref: str, secret: str) -> None:
        self._values[secret_ref] = secret

    def read(self, secret_ref: str) -> str | None:
        return self._values.get(secret_ref)

    def delete(self, secret_ref: str) -> None:
        self._values.pop(secret_ref, None)

    def configured(self, secret_ref: str | None) -> bool:
        return secret_ref is not None and secret_ref in self._values


@dataclass(frozen=True)
class PreparationHarness:
    core: ApplicationCore
    project_id: str
    source_root: Path
    action: object
    actor: object
    identities: tuple[TestIdentity, ...]
    effect_id: str

    @property
    def var_dir(self) -> Path:
        return self.core.var_dir

    def close(self) -> None:
        self.core.close()


def build_preparation_harness(tmp_path: Path, *, identity_count: int = 1, state_changing: bool = True,
                              endpoint: str = "http://127.0.0.1:8765", core: ApplicationCore | None = None) -> PreparationHarness:
    """建立 loopback 应用理解、当前实现绑定、权限事实和已准备身份。"""

    var_dir = tmp_path / "var"
    source_root = tmp_path / "fixture-app"
    source_root.mkdir()
    source_file = source_root / "routes.py"
    source_file.write_text("def update_document():\n    return True\n", encoding="utf-8")
    secret_store = MemorySecretStore()
    core = core or ApplicationCore(var_dir, secret_store=secret_store, environ={})
    secret_store = core.secret_store
    connection = core.application_understanding.connect(source_root, project_name="fixture-app")
    project_id = connection.project.project_id
    # connect 使用当前时钟建立项目；后续替换必须保持同一时间单调性。
    now_us = connection.understanding.created_at_us

    source_fingerprint = core.application_understanding.analyzer.analyze(
        project_id, str(source_root)
    ).source_fingerprint
    role_id = candidate_id("role", "member")
    action_candidate_id = candidate_id("action", "update_document")
    content_hash = hashlib.sha256(source_file.read_bytes()).hexdigest()
    evidence = CandidateEvidence(
        relative_path="routes.py",
        line_start=1,
        line_end=2,
        symbol="update_document",
        detector="fixture",
        content_sha256=content_hash,
    )
    understanding = connection.understanding.model_copy(
        update={
            "confirmed_endpoint": endpoint,
            "endpoint_source_fingerprint": hashlib.sha256(
                str(source_root).encode("utf-8")
            ).hexdigest(),
            "endpoint_confirmed_at_us": now_us,
            "endpoint_last_checked_at_us": now_us,
            "endpoint_reachable": True,
            "source_analysis_authorized": True,
            "source_analysis_authorized_at_us": now_us,
            "source_fingerprint": source_fingerprint,
            "analysis_completed_at_us": now_us,
            "role_candidates": (
                RoleCandidate(
                    candidate_id=role_id,
                    canonical_key="member",
                    display_name="普通成员",
                    confidence=CandidateConfidence.HIGH,
                    decision=CandidateDecision.CONFIRMED,
                    origin=CandidateOrigin.DETECTED,
                    evidence=(evidence,),
                ),
            ),
            "action_candidates": (
                ActionCandidate(
                    candidate_id=action_candidate_id,
                    canonical_key="update_document",
                    display_name="更新文档",
                    confidence=CandidateConfidence.HIGH,
                    decision=CandidateDecision.CONFIRMED,
                    origin=CandidateOrigin.DETECTED,
                    evidence=(evidence,),
                ),
            ),
            "revision": 3,
            "updated_at_us": now_us,
        }
    )

    actor_revision = assurance.actor().model_copy(update={"project_id": project_id})
    actor_revision = actor_revision.model_copy(
        update={"semantic_fingerprint": boundary_sha256(actor_revision.semantic_payload())}
    )
    action_revision = assurance.action(state_changing=state_changing).model_copy(
        update={"project_id": project_id}
    )
    action_revision = action_revision.model_copy(
        update={"semantic_fingerprint": boundary_sha256(action_revision.semantic_payload())}
    )
    actor_root = BusinessActor(
        actor_id=actor_revision.actor_id,
        project_id=project_id,
        current_revision=1,
        created_at_us=now_us,
        updated_at_us=now_us,
    )
    action_root = BusinessAction(
        action_id=action_revision.action_id,
        project_id=project_id,
        current_revision=1,
        created_at_us=now_us,
        updated_at_us=now_us,
    )
    actor_binding_values = {
        "actor_id": actor_revision.actor_id,
        "actor_revision": 1,
        "understanding_revision": understanding.revision,
        "source_fingerprint": understanding.source_fingerprint,
        "role_candidate_ids": (role_id,),
    }
    actor_binding = ActorImplementationBinding(
        **actor_binding_values,
        basis_version=1,
        binding_fingerprint=boundary_sha256(actor_binding_values),
        updated_at_us=now_us,
    )
    action_binding_values = {
        "action_id": action_revision.action_id,
        "action_revision": 1,
        "understanding_revision": understanding.revision,
        "source_fingerprint": understanding.source_fingerprint,
        "action_candidate_ids": (action_candidate_id,),
    }
    action_binding = ActionImplementationBinding(
        **action_binding_values,
        basis_version=1,
        binding_fingerprint=boundary_sha256(action_binding_values),
        updated_at_us=now_us,
    )
    permission = assurance.permission().model_copy(update={"project_id": project_id})

    identities: list[TestIdentity] = []
    for ordinal in range(identity_count):
        identity_id = f"tid_{(ordinal + 1):032x}"
        secret_ref = f"cred:jiejian/test-identity/{project_id}/{identity_id}/bearer"
        secret_store.write(secret_ref, "fixture-secret")
        identities.append(
            TestIdentity(
                identity_id=identity_id,
                project_id=project_id,
                actor_id=actor_revision.actor_id,
                actor_revision=1,
                label=f"测试账号 {ordinal + 1}",
                auth_method=TestIdentityAuthMethod.BEARER,
                bearer_secret_ref=secret_ref,
                prepared_at_us=now_us,
                refreshed_at_us=now_us,
                created_at_us=now_us,
                updated_at_us=now_us,
            )
        )
    with core.uow_factory() as work:
        work.application_understanding.replace(understanding)
        work.projects.replace(
            connection.project.model_copy(update={"status": ProjectStatus.READY, "updated_at_us": now_us})
        )
        work.business_boundaries.add_actor_revision(actor_revision)
        work.business_boundaries.add_actor(actor_root)
        work.business_boundaries.add_action_revision(action_revision)
        work.business_boundaries.add_action(action_root)
        work.business_boundaries.replace_actor_binding(actor_binding)
        work.business_boundaries.replace_action_binding(action_binding)
        work.permission_intents.add_revision(permission)
        work.permission_intents.replace_policy_state(
            ProjectPolicyState(project_id=project_id, policy_epoch=1, updated_at_us=now_us)
        )
        for identity in identities:
            work.test_identities.add(identity)
        work.commit()
    return PreparationHarness(
        core=core,
        project_id=project_id,
        source_root=source_root,
        action=action_revision,
        actor=actor_revision,
        identities=tuple(identities),
        effect_id=assurance.EFFECT,
    )


def add_recording(
    harness: PreparationHarness,
    *,
    identity_index: int = 0,
    purpose: RecordingPurpose = RecordingPurpose.TARGET,
    parent_recording_id: str | None = None,
    effect_id: str | None = None,
    step_count: int = 1,
    target_step_id: str | None = None,
    method: str | None = None,
    action_revision: int | None = None,
) -> RecordingRecord:
    """把受控脱敏事件和当前 revision 的 FlowDraft 以真实记录形式落库。"""

    identity = harness.identities[identity_index]
    recorded_action_revision = action_revision or harness.action.revision
    with harness.core.uow_factory() as work:
        action = work.business_boundaries.action_revision(harness.action.action_id, harness.action.revision)
        current_identity = work.test_identities.get(identity.identity_id)
        understanding = work.application_understanding.get(harness.project_id)
        action_binding = work.business_boundaries.action_binding(harness.action.action_id, 1)
        actor_binding = work.business_boundaries.actor_binding(identity.actor_id, identity.actor_revision)
        assert action is not None and current_identity is not None and understanding is not None
        assert action_binding is not None and actor_binding is not None
        source_fingerprint = recording_source_fingerprint(
            action, current_identity, understanding, action_binding, actor_binding
        )
    recording_id = f"rec_{uuid4().hex}"
    flow_id = f"flow_{uuid4().hex}"
    is_target = purpose is RecordingPurpose.TARGET
    request_method = method or ("POST" if is_target or purpose is RecordingPurpose.RECOVERY else "GET")
    steps: list[FlowDraftStep] = []
    events: list[RecordingEvent] = []
    for index in range(step_count):
        sequence = index + 1
        step_id = f"step_{sequence:06d}"
        request_id = f"request_{sequence:06d}"
        query = "?view=summary" if index == 0 and purpose is RecordingPurpose.OBSERVATION else (
            f"?view=variant{sequence}" if purpose is RecordingPurpose.OBSERVATION else ""
        )
        url = f"http://127.0.0.1:8765/docs/doc-123{query}"
        steps.append(
            FlowDraftStep(
                id=step_id,
                name="业务请求",
                method=request_method,
                path=f"/docs/doc-123{query}",
                json_body={"title": "fixture"} if request_method != "GET" else {},
                expected_statuses=(200,),
                request_id=request_id,
                source_event_sequences=(sequence * 2 - 1, sequence * 2),
                depends_on_step_ids=(),
                resource_candidates=(
                    (
                        FlowDraftResourceCandidate(
                            candidate_id="resource-0123456789abcdef",
                            consumer=ValueSlotConsumer.PATH,
                            location="path[1]",
                            label="文档标识",
                        ),
                    )
                    if is_target
                    else ()
                ),
            )
        )
        events.extend(
            (
                RecordingEvent(
                    sequence=sequence * 2 - 1,
                    occurred_at_us=sequence * 2,
                    kind=RecordingEventKind.REQUEST,
                    identity_id=identity.identity_id,
                    request_id=request_id,
                    url=url,
                    method=request_method,
                    resource_type="document",
                    body=json.dumps({"title": "fixture"}) if request_method != "GET" else None,
                ),
                RecordingEvent(
                    sequence=sequence * 2,
                    occurred_at_us=sequence * 2 + 1,
                    kind=RecordingEventKind.RESPONSE,
                    identity_id=identity.identity_id,
                    request_id=request_id,
                    url=url,
                    method=request_method,
                    status_code=200,
                    body=json.dumps({"ok": True}),
                ),
            )
        )
    confirmed_target_step = (
        "step_000001"
        if is_target or target_step_id == "first"
        else target_step_id
    )
    draft = FlowDraft(
        recording_id=recording_id,
        flow_id=flow_id,
        business_action_id=harness.action.action_id,
        action_revision=recorded_action_revision,
        test_identity_id=identity.identity_id,
        purpose=purpose,
        parent_recording_id=parent_recording_id,
        effect_id=effect_id,
        revision=1,
        steps=tuple(steps),
        target_step_id=confirmed_target_step,
        resource_candidate_id="resource-0123456789abcdef" if is_target else None,
    )
    record = RecordingRecord(
        recording_id=recording_id,
        project_id=harness.project_id,
        business_action_id=harness.action.action_id,
        action_revision=recorded_action_revision,
        test_identity_id=identity.identity_id,
        preparation_source_fingerprint=source_fingerprint,
        purpose=purpose,
        parent_recording_id=parent_recording_id,
        effect_id=effect_id,
        flow_id=flow_id,
        state=RecordingState.PENDING_REVIEW,
        created_at_us=1,
        updated_at_us=3,
        started_at_us=1,
        capture_finished_at_us=3,
        browser_events=tuple(events),
    )
    draft_bytes = canonical_flow_draft_json_bytes(draft)
    draft_record = FlowDraftRevisionRecord(
        recording_id=recording_id,
        revision=1,
        flow_id=flow_id,
        draft=draft,
        draft_sha256=hashlib.sha256(draft_bytes).hexdigest(),
        created_at_us=3,
    )
    with harness.core.uow_factory() as work:
        work.recordings.add(record)
        work.flow_drafts.add(draft_record)
        work.commit()
    return record


def current_identity(harness: PreparationHarness, identity_index: int = 0) -> TestIdentity:
    with harness.core.uow_factory() as work:
        record = work.test_identities.get(harness.identities[identity_index].identity_id)
    assert record is not None
    return record


__all__ = ["MemorySecretStore", "PreparationHarness", "add_recording", "build_preparation_harness", "current_identity"]
