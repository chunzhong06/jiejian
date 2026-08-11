from __future__ import annotations

import hashlib
import json
import time
from functools import partial
from pathlib import Path

from typer.testing import CliRunner

from jiejian.cli import app
from jiejian.domain.lifecycle import ProjectStatus
from jiejian.domain.recording import Recording, RecordingState, transition_recording_state
from jiejian.protocols import (
    FlowDraftStepV1,
    FlowDraftV1,
    canonical_flow_draft_json_bytes,
)
from jiejian.storage import (
    FlowDraftRevisionRecord,
    ProjectRecord,
    RecordingRecord,
    StorageUnitOfWork,
    create_session_factory,
    create_sqlite_engine,
    default_database_path,
    upgrade_database,
)
from jiejian.verification.inputs import load_project_bundle


def test_finalize_and_replay_three_times_through_cli(
    sample_server_factory,
    stage1_project_factory,
    monkeypatch,
    tmp_path: Path,
) -> None:
    server = sample_server_factory("safe")
    project_path = stage1_project_factory(server.port)
    bundle = load_project_bundle(project_path)
    for name, value in server.environ.items():
        monkeypatch.setenv(name, value)

    var_dir = tmp_path / "var"
    database_path = default_database_path(var_dir)
    upgrade_database(database_path)
    engine = create_sqlite_engine(database_path)
    factory = partial(StorageUnitOfWork, create_session_factory(engine))
    now_us = time.time_ns() // 1_000 - 1_000
    recording_id = "rec_" + "8" * 32
    domain = Recording(
        schema_version="1",
        recording_id=recording_id,
        project_id=bundle.project.id,
        created_at_us=now_us,
        updated_at_us=now_us,
    )
    domain = transition_recording_state(
        domain, RecordingState.STARTING, operator="TEST", occurred_at_us=now_us + 1
    )
    domain = transition_recording_state(
        domain, RecordingState.RECORDING, operator="TEST", occurred_at_us=now_us + 2
    )
    domain = transition_recording_state(
        domain, RecordingState.CLEANING, operator="TEST", occurred_at_us=now_us + 3
    )
    domain = transition_recording_state(
        domain, RecordingState.PROCESSING, operator="TEST", occurred_at_us=now_us + 4
    )
    domain = transition_recording_state(
        domain,
        RecordingState.PENDING_REVIEW,
        operator="TEST",
        occurred_at_us=now_us + 5,
    )
    recording = RecordingRecord.from_domain(domain, flow_id=bundle.flow.id)
    steps = tuple(
        FlowDraftStepV1(
            schema_version="1",
            id=step.id,
            name=step.name or step.id,
            identity_id=step.identity_id,
            alternate_identity_id=step.alternate_identity_id,
            resource_id=step.resource_id,
            alternate_resource_id=step.alternate_resource_id,
            bindings_confirmed=True,
            method=step.method,
            path=step.path,
            json_body=step.json_body,
            expected_statuses=step.expected_statuses,
            request_id=f"request_{index:06d}",
            source_event_sequences=(index,),
            depends_on_step_ids=step.depends_on_step_ids,
            sensitive_fields=step.sensitive_fields,
        )
        for index, step in enumerate(bundle.flow.steps, start=1)
    )
    draft = FlowDraftV1(
        schema_version="1",
        recording_id=recording_id,
        flow_id=bundle.flow.id,
        revision=1,
        steps=steps,
    )
    encoded = canonical_flow_draft_json_bytes(draft)
    try:
        with factory() as work:
            work.projects.add(
                ProjectRecord(
                    project_id=bundle.project.id,
                    name=bundle.project.name,
                    status=ProjectStatus.READY,
                    created_at_us=now_us,
                    updated_at_us=now_us,
                )
            )
            work.recordings.add(recording)
            work.flow_drafts.add(
                FlowDraftRevisionRecord(
                    recording_id=recording_id,
                    revision=1,
                    flow_id=bundle.flow.id,
                    draft=draft,
                    draft_sha256=hashlib.sha256(encoded).hexdigest(),
                    created_at_us=now_us + 5,
                )
            )
            work.commit()
        runner = CliRunner()
        finalized = runner.invoke(
            app,
            ["--var-dir", str(var_dir), "recording", "finalize", recording_id],
        )
        assert finalized.exit_code == 0, finalized.output
        replayed = runner.invoke(
            app,
            [
                "--var-dir",
                str(var_dir),
                "recording",
                "replay",
                recording_id,
                "--project",
                str(project_path),
                "--runs",
                "3",
            ],
        )
        assert replayed.exit_code == 0, replayed.output
        payload = json.loads(replayed.stdout)
        assert len(payload["runs"]) == 3
    finally:
        engine.dispose()
