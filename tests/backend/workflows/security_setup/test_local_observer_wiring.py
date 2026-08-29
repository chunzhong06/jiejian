# 验证本地协作空间环境描述到六类 Observer/Profile 绑定的严格组合边界。

from __future__ import annotations

import json
from pathlib import Path

import pytest

from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.infra.runtime.runner.executor import _requirements_to_run
from product.backend.workflows.security_setup.local_observer_wiring import (
    load_local_observer_wiring,
)
from product.backend.workflows.security_setup.local_observer_registry import (
    LocalObserverEnvironmentRegistry,
)
from product.protocols import (
    ObservationPhase,
    ObserverType,
    WorkflowStepPurpose,
)
from product.protocols.web.profile import (
    canonical_web_execution_profile_json_bytes,
    parse_web_execution_profile,
)
from tests.fixtures.collaboration_golden import (
    InMemorySecretStore,
    prepare_formal_project,
    reachable_discovery,
    sample_credentials,
)
from tests.fixtures.control_plane import TestClient, create_app


PROJECT_ID = "campus-digital-museum"
ACTION_ID = "action_" + "a" * 32
RESOURCE_ID = "campus-digital-museum-package"
ORIGIN = "http://127.0.0.1:8865"


def _descriptor(*, origin: str = ORIGIN, resource_id: str = RESOURCE_ID) -> dict[str, object]:
    return {
        "application": {
            "origin": origin,
            "project_id": "target-internal-project",
            "resource_id": resource_id,
        },
        "owner_api": {
            "origin": origin,
            "relative_path_template": "/api/observer/resources/{resource_id}",
            "credential_ref": "env:JIEJIAN_SAMPLE_OWNER_OBSERVER",
        },
        "sqlite": {
            "relative_path": "state/data.sqlite3",
            "database_secret_ref": "env:JIEJIAN_SAMPLE_SQLITE_DATABASE",
            "query_template_id": "resource-state",
            "table_or_view": "resource_state",
        },
        "audit": {
            "relative_path": "logs/events.jsonl",
            "authorized_root_ref": "env:JIEJIAN_SAMPLE_AUDIT_ROOT",
            "relative_file_pattern": "events.jsonl",
            "allowed_fields": [
                "case_tag",
                "event_id",
                "event_type",
                "resource_id",
                "sequence",
                "task_id",
            ],
        },
        "task": {
            "base_url": origin,
            "relative_path_template": "/api/tasks/{request_marker}",
            "read_only_credential_ref": "env:JIEJIAN_SAMPLE_TASK_BEARER",
        },
        "queue": {
            "service_url": f"{origin}/queacct",
            "account": "queacct",
            "queue_name": "export-events",
            "read_only_sas_ref": "env:JIEJIAN_SAMPLE_QUEUE_SAS",
            "allowed_fields": [
                "case_tag",
                "event_id",
                "event_type",
                "resource_id",
                "sequence",
            ],
        },
        "blob": {
            "service_url": f"{origin}/blobacct",
            "account": "blobacct",
            "container_name": "exports",
            "prefix_template": "{request_marker}/",
            "read_only_sas_ref": "env:JIEJIAN_SAMPLE_BLOB_SAS",
            "allowed_metadata_fields": ["case_tag", "resource_id"],
        },
    }


def _write_descriptor(tmp_path: Path, descriptor: dict[str, object]) -> tuple[Path, Path]:
    var_dir = tmp_path / "var"
    path = var_dir / "runtime" / "official-samples" / ("exp_" + "a" * 32) / "environment.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(descriptor), encoding="utf-8")
    return path, var_dir


def _load(tmp_path: Path, descriptor: dict[str, object] | None = None):
    descriptor_path, var_dir = _write_descriptor(tmp_path, descriptor or _descriptor())
    return load_local_observer_wiring(
        str(descriptor_path),
        var_dir=var_dir,
        action_id=ACTION_ID,
        expected_origin=ORIGIN,
        expected_resource_id=RESOURCE_ID,
    )


def test_valid_descriptor_builds_six_sources_with_frozen_roles_and_phases(tmp_path: Path) -> None:
    wiring = _load(tmp_path)

    assert wiring is not None
    assert [item.observer_type for item in wiring.observers] == [
        ObserverType.OWNER_API,
        ObserverType.READ_ONLY_SQLITE,
        ObserverType.STRUCTURED_AUDIT_LOG,
        ObserverType.ASYNC_TASK_STATUS,
        ObserverType.AZURE_QUEUE_PEEK,
        ObserverType.AZURE_BLOB_OBJECT,
    ]
    assert wiring.required_channels == (
        wiring.bindings[0].requirement_id,
        wiring.bindings[5].requirement_id,
    )
    assert wiring.corroborating_channels == tuple(
        item.requirement_id for item in wiring.bindings[1:5]
    )
    assert wiring.observers[0].required is True
    assert wiring.observers[5].required is True
    assert all(not item.required for item in wiring.observers[1:5])
    assert wiring.observers[0].phases == (
        ObservationPhase.AFTER,
        ObservationPhase.BASELINE,
        ObservationPhase.BEFORE,
        ObservationPhase.EVENTUAL,
    )
    assert wiring.observers[3].phases == (ObservationPhase.EVENTUAL,)
    assert wiring.observers[4].phases == (ObservationPhase.EVENTUAL,)
    assert wiring.observers[1].target.locator.database_secret_ref == "env:JIEJIAN_SAMPLE_SQLITE_DATABASE"
    assert wiring.observers[1].target.locator.query_template_id == "resource-state"
    assert wiring.observers[2].target.locator.relative_file_pattern == "events.jsonl"
    assert wiring.observers[4].target.locator.service_url == f"{ORIGIN}/queacct"
    assert wiring.observers[5].target.locator.service_url == f"{ORIGIN}/blobacct"


@pytest.mark.parametrize(
    "mutate",
    [
        lambda descriptor: descriptor.update({"unexpected": "field"}),
        lambda descriptor: descriptor["owner_api"].update({"secret": "inline"}),
        lambda descriptor: descriptor["application"].update({"origin": "http://127.0.0.1:8866"}),
    ],
)
def test_descriptor_extra_secret_or_origin_mismatch_fails_closed(tmp_path: Path, mutate) -> None:
    descriptor = _descriptor()
    mutate(descriptor)

    with pytest.raises(JiejianError) as error:
        _load(tmp_path, descriptor)
    assert error.value.code == ErrorCode.STATE_PRECONDITION.value


def test_descriptor_path_outside_var_dir_fails_closed(tmp_path: Path) -> None:
    outside = tmp_path / "outside.json"
    outside.write_text(json.dumps(_descriptor()), encoding="utf-8")

    with pytest.raises(JiejianError) as error:
        load_local_observer_wiring(
            str(outside),
            var_dir=tmp_path / "var",
            action_id=ACTION_ID,
            expected_origin=ORIGIN,
            expected_resource_id=RESOURCE_ID,
        )
    assert error.value.code == ErrorCode.STATE_PRECONDITION.value


def test_missing_environment_file_keeps_wiring_disabled(tmp_path: Path) -> None:
    assert (
        load_local_observer_wiring(
            None,
            var_dir=tmp_path / "var",
            action_id=ACTION_ID,
            expected_origin=ORIGIN,
            expected_resource_id=RESOURCE_ID,
        )
        is None
    )


def test_registry_requires_exact_source_and_origin_match(tmp_path: Path) -> None:
    descriptor_path, _ = _write_descriptor(tmp_path, _descriptor())
    source_root = tmp_path / "source"
    source_root.mkdir()
    registry = LocalObserverEnvironmentRegistry()
    registry.register(
        experience_id="exp_" + "a" * 32,
        source_root=source_root,
        confirmed_endpoint=ORIGIN,
        descriptor_path=descriptor_path,
    )

    assert registry.resolve(source_root, ORIGIN) == str(descriptor_path.resolve())
    assert registry.resolve(tmp_path, ORIGIN) is None
    assert registry.resolve(source_root, "http://127.0.0.1:8866") is None
    registry.unregister("exp_" + "a" * 32)
    assert registry.resolve(source_root, ORIGIN) is None


def test_compiler_publishes_local_observer_contract_and_profile_snapshot(tmp_path: Path) -> None:
    endpoint = "http://127.0.0.1:18080"
    descriptor_path, var_dir = _write_descriptor(
        tmp_path,
        _descriptor(origin=endpoint, resource_id=RESOURCE_ID),
    )
    credentials = sample_credentials()
    store = InMemorySecretStore()
    app = create_app(
        var_dir,
        secret_store=store,
        environ={},
    )
    app.state.context.application_understanding.endpoint_discovery = (
        reachable_discovery(endpoint)
    )
    with TestClient(app) as client:
        setup = prepare_formal_project(
            client,
            app.state.context,
            store,
            endpoint=endpoint,
            sessions=credentials["session_material"],
        )
        core = app.state.context
        core.local_observer_environments.register(
            experience_id="exp_" + "a" * 32,
            source_root=Path(__file__).resolve().parents[4] / "samples" / "web",
            confirmed_endpoint=endpoint,
            descriptor_path=descriptor_path,
        )
        compiled = core.security_setup.compile(setup["project_id"])
        contract = core.contracts.list_versions(
            setup["project_id"], compiled.contract_id
        )[0].snapshot
        profile = parse_web_execution_profile(Path(compiled.profile_path).read_bytes())
        assert canonical_web_execution_profile_json_bytes(profile) == Path(
            compiled.profile_path
        ).read_bytes()
        assert set(contract.rules[0].required_observations) == {
            profile.observer_bindings[0].requirement_id,
            profile.observer_bindings[5].requirement_id,
        }
        assert [item.observer_type for item in profile.observers] == [
            ObserverType.OWNER_API,
            ObserverType.READ_ONLY_SQLITE,
            ObserverType.STRUCTURED_AUDIT_LOG,
            ObserverType.ASYNC_TASK_STATUS,
            ObserverType.AZURE_QUEUE_PEEK,
            ObserverType.AZURE_BLOB_OBJECT,
        ]
        assert set(profile.effect_bindings[0].required_channels) == set(
            contract.rules[0].required_observations
        )
        assert profile.effect_bindings[0].corroborating_channels == tuple(
            item.requirement_id for item in profile.observer_bindings[1:5]
        )
        assert [item.required for item in profile.observers] == [True, False, False, False, False, True]
        async_binding = next(
            item.requirement_id
            for item in profile.observer_bindings
            if item.observer_type is ObserverType.ASYNC_TASK_STATUS
        )
        target_step = next(
            step
            for workflow in profile.workflow_bindings
            for step in workflow.steps
            if step.purpose is WorkflowStepPurpose.TARGET
        )
        assert target_step.classifier.completion_binding == async_binding
        request = core.execution.build_request(
            compiled.profile_id,
            project_id=setup["project_id"],
        )
        assert [item.observer_type for item in request.project_snapshot.observers] == [
            ObserverType.OWNER_API,
            ObserverType.READ_ONLY_SQLITE,
            ObserverType.STRUCTURED_AUDIT_LOG,
            ObserverType.ASYNC_TASK_STATUS,
            ObserverType.AZURE_QUEUE_PEEK,
            ObserverType.AZURE_BLOB_OBJECT,
        ]
        case = request.project_snapshot.plan.cases[0]
        action = next(
            item
            for item in request.project_snapshot.contract.actions
            if item.action_id == case.action_id
        )
        scheduled = _requirements_to_run(
            case,
            action,
            {
                item.effect_id: item
                for item in request.project_snapshot.effect_bindings
            },
        )
        assert set(scheduled) == {
            item.requirement_id
            for item in request.project_snapshot.observer_bindings
        }
        assert len(scheduled) == 6
