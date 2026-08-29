# 为协作空间三态 Golden 装配正式项目、测试身份与已确认录制工件。
#
# 职责：通过既有 API 和持久化边界创建可编译的真实项目输入；测试正文只保留三态行为与验收断言。
# 边界：仅保存运行期不透明测试凭据，不生成 Verdict，不绕过执行、Evidence 或结果发布接口。

from __future__ import annotations

import hashlib
import json
import time
from itertools import pairwise
from pathlib import Path
from secrets import token_urlsafe
from uuid import uuid4

from product.backend.core.lifecycle import JobState
from product.backend.core.recording import (
    Recording,
    RecordingState,
    RecordingStateEvent,
)
from product.backend.core.test_identity import (
    TestIdentityAuthMethod as IdentityAuthMethod,
    TestIdentityCookie as IdentityCookie,
)
from product.backend.infra.storage import (
    FlowDraftRevisionRecord,
    JobRecord,
    RecordingRecord,
)
from product.backend.workflows.application_understanding.endpoints import (
    EndpointProbeObservation,
    TargetEndpointDiscovery,
)
from product.backend.workflows.recording.lifecycle import RecordingLifecycle
from product.backend.workflows.recording.processing import FlowDraftProcessor
from product.backend.workflows.recording.review import FlowDraftReviewer
from product.backend.workflows.test_identities import PreparedLoginState
from product.protocols import (
    ConfirmFlowDraftResource,
    ConfirmFlowDraftTarget,
    ConfirmFlowDraftVariable,
    RecordingBudget,
    RecordingEvent,
    RecordingEventKind,
    RecordingRunnerRequest,
    ValueSlotConsumer,
    canonical_flow_draft_json_bytes,
)
from product.protocols.web.target import WebTargetScope
from samples.web.collaboration_space.source.storage import (
    PROJECT_ID as SAMPLE_PROJECT_ID,
    RESOURCE_ID,
)
from tests.fixtures.control_plane import TestClient


SOURCE_ROOT = Path(__file__).resolve().parents[2] / "samples" / "web"
EXPORT_ACTION_KEY = "POST /api/projects/{project_id}/exports"
COOKIE_NAME = "jiejian_sample_session"


class InMemorySecretStore:
    """测试边界内保存不透明值；正式 Profile 和运行工件仍只接收引用。"""

    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    def configured(self, secret_ref: str) -> bool:
        return secret_ref in self.values

    def read(self, secret_ref: str) -> str:
        return self.values[secret_ref]

    def write(self, secret_ref: str, value: str) -> None:
        self.values[secret_ref] = value

    def delete(self, secret_ref: str) -> None:
        self.values.pop(secret_ref, None)


def sample_credentials() -> dict[str, object]:
    """为单次 Golden 生成彼此隔离且不会进入公共工件的 Sample 凭据。"""

    return {
        "passwords": {
            account: f"collaboration-{account}-{token_urlsafe(18)}"
            for account in ("alice", "bob")
        },
        "session_material": {
            account: f"session-{account}-{token_urlsafe(18)}"
            for account in ("alice", "bob")
        },
        "queue_sas": (
            "sv=2023-11-03&se=2099-01-01T00%3A00%3A00Z&sp=r&sr=q&sig="
            + token_urlsafe(24)
        ),
        "blob_sas": (
            "sv=2023-11-03&se=2099-01-01T00%3A00%3A00Z&sp=rl&sr=c&sig="
            + token_urlsafe(24)
        ),
        "task_bearer": f"task-{token_urlsafe(24)}",
        "owner_observer": f"owner-{token_urlsafe(24)}",
    }


def reachable_discovery(endpoint: str) -> TargetEndpointDiscovery:
    """只把当前 loopback Sample 端点声明为可达。"""

    def probe(candidate: str, _limits) -> EndpointProbeObservation:
        return EndpointProbeObservation(
            reachable=candidate == endpoint,
            status_code=200 if candidate == endpoint else None,
            detail="协作空间已响应" if candidate == endpoint else "地址未响应",
        )

    return TargetEndpointDiscovery(probe=probe)


def prepare_formal_project(
    client: TestClient,
    core,
    store: InMemorySecretStore,
    *,
    endpoint: str,
    sessions: dict[str, str],
    observer_descriptor_path: Path | None = None,
) -> dict[str, str]:
    """经应用接入、理解确认、身份和安全设置创建正式可编译项目。"""

    connected = client.post(
        "/api/applications/connect",
        json={
            "schema_version": "1",
            "source_root": str(SOURCE_ROOT),
            "project_name": "协作空间——项目资料管理应用",
        },
    )
    assert connected.status_code == 201, connected.text
    project_id = connected.json()["data"]["project"]["project_id"]
    confirmed = client.put(
        f"/api/projects/{project_id}/endpoint",
        json={"schema_version": "1", "endpoint": endpoint, "revision": 0},
    )
    assert confirmed.status_code == 200, confirmed.text
    # 六面本地观察只信任活跃体验注册表中精确匹配的源码根、
    # origin 与 descriptor；测试不得恢复已移除的环境变量旁路。
    if observer_descriptor_path is not None:
        core.local_observer_environments.register(
            experience_id=f"exp_{uuid4().hex}",
            source_root=SOURCE_ROOT,
            confirmed_endpoint=endpoint,
            descriptor_path=observer_descriptor_path,
        )
    authorized = client.put(
        f"/api/projects/{project_id}/source-analysis-authorization",
        json={"schema_version": "1", "authorized": True, "revision": 1},
    )
    assert authorized.status_code == 200, authorized.text
    analyzed = client.post(
        f"/api/projects/{project_id}/source-analysis",
        json={"schema_version": "1", "revision": 2},
    )
    assert analyzed.status_code == 200, analyzed.text
    understanding = analyzed.json()["data"]
    revision = understanding["revision"]
    role_labels = {
        "project_owner": "项目负责人",
        "member": "普通成员",
    }
    role_ids: dict[str, str] = {}
    for role in understanding["role_candidates"]:
        key = role["canonical_key"].casefold()
        if key not in role_labels:
            continue
        decided = client.put(
            f"/api/projects/{project_id}/roles/{role['candidate_id']}",
            json={
                "schema_version": "1",
                "decision": "CONFIRMED",
                "display_name": role_labels[key],
                "revision": revision,
            },
        )
        assert decided.status_code == 200, decided.text
        revision = decided.json()["data"]["revision"]
        role_ids[key] = role["candidate_id"]
    assert set(role_ids) == set(role_labels)

    action_id = ""
    for action in understanding["action_candidates"]:
        selected = action["canonical_key"] == EXPORT_ACTION_KEY
        decided = client.put(
            f"/api/projects/{project_id}/actions/{action['candidate_id']}",
            json={
                "schema_version": "1",
                "decision": "CONFIRMED" if selected else "REJECTED",
                "display_name": (
                    "导出完整项目资料包" if selected else action["display_name"]
                ),
                "revision": revision,
            },
        )
        assert decided.status_code == 200, decided.text
        revision = decided.json()["data"]["revision"]
        if selected:
            action_id = action["candidate_id"]
    assert action_id

    identity_ids: dict[str, str] = {}
    for account, role_key in (
        ("alice", "project_owner"),
        ("bob", "member"),
    ):
        response = client.post(
            f"/api/projects/{project_id}/test-identities",
            json={
                "schema_version": "1",
                "role_candidate_id": role_ids[role_key],
                "label": f"{account.capitalize()} · {role_labels[role_key]}",
            },
        )
        assert response.status_code == 201, response.text
        identity_id = response.json()["data"]["identity_id"]
        secret_ref = (
            f"cred:jiejian/test-identity/{project_id}/{identity_id}/cookie-00"
        )
        store.write(secret_ref, sessions[account])
        core.test_identities.save_prepared_state(
            identity_id,
            PreparedLoginState(
                auth_method=IdentityAuthMethod.COOKIE_SESSION,
                cookies=(
                    IdentityCookie(
                        name=COOKIE_NAME,
                        domain="127.0.0.1",
                        path="/",
                        secure=False,
                        http_only=True,
                        same_site="LAX",
                        value_secret_ref=secret_ref,
                    ),
                ),
                prepared_at_us=time.time_ns() // 1_000,
            ),
        )
        identity_ids[account] = identity_id

    recording_id = _persist_export_recording(
        core,
        project_id=project_id,
        action_id=action_id,
        alice_id=identity_ids["alice"],
        endpoint=endpoint,
    )
    safety = client.get(f"/api/recordings/{recording_id}/safety-setup")
    assert safety.status_code == 200, safety.text
    view = safety.json()["data"]
    resource = next(
        item
        for item in view["resource_candidates"]
        if item["actual_resource_id"] == RESOURCE_ID
        and item["consumer"] == "JSON_BODY"
    )
    observation = next(
        item for item in view["observation_candidates"] if item["method"] == "GET"
    )
    recovery = next(
        item for item in view["recovery_candidates"] if item["method"] == "DELETE"
    )
    effect = next(
        item
        for item in view["security_effect_candidates"]
        if item["kind"] == "OBJECT_CREATION"
    )
    confirmed_setup = client.put(
        f"/api/recordings/{recording_id}/safety-setup",
        json={
            "schema_version": "1",
            "resource_candidate_id": resource["candidate_id"],
            "logical_name": "校园数字展馆完整项目资料包",
            "resource_type": "项目资料包",
            "owner_test_identity_id": identity_ids["alice"],
            "observation_candidate_id": observation["candidate_id"],
            "recovery_candidate_id": recovery["candidate_id"],
            "confirm_recovery_not_required": False,
            "security_effect_candidate_id": effect["candidate_id"],
        },
    )
    assert confirmed_setup.status_code == 200, confirmed_setup.text
    assert confirmed_setup.json()["data"]["automatic_execution_allowed"] is True

    for subject_role, relation, expectation in (
        (role_ids["project_owner"], "OWNS", "ALLOW"),
        (role_ids["member"], "OTHER_ROLE", "DENY"),
    ):
        response = client.put(
            f"/api/projects/{project_id}/permission-intents/{action_id}/"
            f"{subject_role}/{role_ids['project_owner']}/{relation}",
            json={
                "schema_version": "1",
                "expectation": expectation,
                "actor": "协作空间 Golden 验收",
            },
        )
        assert response.status_code == 200, response.text
    return {
        "project_id": project_id,
        "action_id": action_id,
        "alice_id": identity_ids["alice"],
        "bob_id": identity_ids["bob"],
    }


def _persist_export_recording(
    core,
    *,
    project_id: str,
    action_id: str,
    alice_id: str,
    endpoint: str,
) -> str:
    now_us = time.time_ns() // 1_000
    recording_id = f"rec_{uuid4().hex}"
    job_id = f"job_{uuid4().hex}"
    events = _recording_events(endpoint, alice_id, now_us)
    draft = FlowDraftProcessor().build(
        recording_id=recording_id,
        flow_id="collaboration-export-package",
        action_candidate_id=action_id,
        events=events,
    )
    target_step = next(
        step for step in draft.steps if step.request_id == "request_000001"
    )
    reviewer = FlowDraftReviewer()
    reviewed = draft
    for variable in draft.variables:
        source = variable.candidate_sources[0]
        reviewed = reviewer.apply(
            reviewed,
            ConfirmFlowDraftVariable(
                schema_version="1",
                operation="CONFIRM_VARIABLE_SOURCE",
                variable_name=variable.name,
                source_event_sequence=source.source_event_sequence,
                source_json_path=source.json_path,
            ),
        )
    targeted = reviewer.apply(
        reviewed,
        ConfirmFlowDraftTarget(
            schema_version="1",
            operation="CONFIRM_TARGET_STEP",
            step_id=target_step.id,
        ),
    )
    resource = next(
        item
        for item in target_step.resource_candidates
        if item.consumer is ValueSlotConsumer.JSON_BODY
        and item.location == "$.resource_id"
    )
    confirmed = reviewer.apply(
        targeted,
        ConfirmFlowDraftResource(
            schema_version="1",
            operation="CONFIRM_RESOURCE_SLOT",
            candidate_id=resource.candidate_id,
        ),
    )
    request = RecordingRunnerRequest(
        schema_version="1",
        recording_id=recording_id,
        project_id=project_id,
        action_candidate_id=action_id,
        created_at_us=now_us,
        target_scope=_target_scope(endpoint),
        sessions=(
            core.recording_credentials.prepare(
                project_id=project_id,
                test_identity_id=alice_id,
                recording_id=recording_id,
                session_ref=f"session_{uuid4().hex}",
                now_us=now_us,
                expires_at_us=now_us + 60_000_000,
            ),
        ),
        budget=RecordingBudget(max_duration_us=60_000_000, max_contexts=1),
        headless=False,
        trace_enabled=False,
    )
    request_hash, _ = core.recording_request_store.write(job_id, request)
    recording = Recording(
        recording_id=recording_id,
        project_id=project_id,
        state=RecordingState.PENDING_REVIEW,
        created_at_us=now_us,
        updated_at_us=now_us + 6,
        started_at_us=now_us + 2,
        capture_finished_at_us=now_us + 5,
        events=_recording_state_events(now_us),
    )
    with core.uow_factory() as work:
        work.recordings.add(
            RecordingRecord.from_domain(
                recording,
                flow_id="collaboration-export-package",
                browser_events=events,
            )
        )
        encoded = canonical_flow_draft_json_bytes(confirmed)
        work.flow_drafts.add(
            FlowDraftRevisionRecord(
                recording_id=recording_id,
                revision=confirmed.revision,
                flow_id=confirmed.flow_id,
                draft=confirmed,
                draft_sha256=hashlib.sha256(encoded).hexdigest(),
                created_at_us=now_us + 6,
            )
        )
        work.jobs.add(
            JobRecord(
                job_id=job_id,
                project_id=project_id,
                recording_id=recording_id,
                operation_type="BROWSER_RECORDING",
                state=JobState.SUCCEEDED,
                idempotency_key="collaboration-golden-recording",
                request_hash=request_hash,
                attempt=0,
                max_attempts=1,
                available_at_us=now_us,
                fencing_token=0,
                created_at_us=now_us,
                updated_at_us=now_us + 6,
            )
        )
        work.commit()
    RecordingLifecycle(core.uow_factory, var_dir=core.var_dir).finalize(
        recording_id,
        var_dir=core.var_dir,
        now_us=now_us + 7,
    )
    core.recording_credentials.clear(recording_id)
    return recording_id


def _recording_events(
    endpoint: str,
    identity_id: str,
    now_us: int,
) -> tuple[RecordingEvent, ...]:
    requests = (
        (
            "POST",
            "request_000001",
            f"{endpoint}/api/projects/{SAMPLE_PROJECT_ID}/exports",
            json.dumps({"resource_id": RESOURCE_ID}),
            202,
            "{}",
        ),
        (
            "GET",
            "request_000002",
            f"{endpoint}/api/observer/resources/{RESOURCE_ID}",
            None,
            200,
            json.dumps(
                {
                    "resource_id": RESOURCE_ID,
                    "workflow_state": "READY",
                    "value": "recorded-artifact",
                }
            ),
        ),
        (
            "DELETE",
            "request_000003",
            f"{endpoint}/api/projects/{SAMPLE_PROJECT_ID}/exports",
            json.dumps({"resource_id": RESOURCE_ID}),
            200,
            "{}",
        ),
        (
            "GET",
            "request_000004",
            f"{endpoint}/api/observer/resources/{RESOURCE_ID}",
            None,
            200,
            json.dumps(
                {
                    "resource_id": RESOURCE_ID,
                    "workflow_state": "ABSENT",
                    "value": "",
                }
            ),
        ),
    )
    events: list[RecordingEvent] = []
    sequence = 1
    for method, request_id, url, body, status, response_body in requests:
        events.append(
            RecordingEvent(
                sequence=sequence,
                occurred_at_us=now_us + 10 + sequence,
                kind=RecordingEventKind.REQUEST,
                identity_id=identity_id,
                page_id="page_000001",
                frame_id="frame_000001",
                request_id=request_id,
                url=url,
                method=method,
                resource_type="fetch",
                body=body,
            )
        )
        sequence += 1
        events.append(
            RecordingEvent(
                sequence=sequence,
                occurred_at_us=now_us + 10 + sequence,
                kind=RecordingEventKind.RESPONSE,
                identity_id=identity_id,
                page_id="page_000001",
                frame_id="frame_000001",
                request_id=request_id,
                url=url,
                status_code=status,
                body=response_body,
            )
        )
        sequence += 1
    return tuple(events)


def _recording_state_events(now_us: int) -> tuple[RecordingStateEvent, ...]:
    states = (
        RecordingState.CREATED,
        RecordingState.STARTING,
        RecordingState.RECORDING,
        RecordingState.CLEANING,
        RecordingState.PROCESSING,
        RecordingState.PENDING_REVIEW,
    )
    return tuple(
        RecordingStateEvent(
            sequence=index,
            source=source,
            target=target,
            operator="COLLABORATION_GOLDEN_SETUP",
            occurred_at_us=now_us + index + 1,
        )
        for index, (source, target) in enumerate(pairwise(states), start=1)
    )


def _target_scope(endpoint: str) -> WebTargetScope:
    port = int(endpoint.rsplit(":", 1)[1])
    return WebTargetScope(
        base_url=endpoint,
        allowed_origins=(endpoint,),
        allowed_hosts=("127.0.0.1",),
        allowed_ports=(port,),
        allow_private_network=True,
        timeout_seconds=5,
        max_requests=128,
        max_response_bytes=262_144,
    )
