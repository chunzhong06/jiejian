# 验证官方 Sample 的显式安装、隔离复制、动态端口与秘密/进程树边界。

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.infra.observers.azure_blob import _parse_sas as parse_blob_sas
from product.backend.infra.observers.azure_queue import _parse_sas as parse_queue_sas
from product.backend.infra.samples import OfficialSampleManager
from product.backend.infra.samples.official import _new_secret_values
from product.backend.infra.runtime.process.environment import (
    minimal_process_environment,
)
from tests.fixtures.runtime_environment import runtime_identity_environment


_PROJECT_ROOT = Path(__file__).resolve().parents[4]
_SAMPLE_ROOT = _PROJECT_ROOT / "samples" / "web" / "collaboration_space"


def test_generated_observer_sas_matches_blob_and_queue_contracts(
    tmp_path: Path,
) -> None:
    values = _new_secret_values(tmp_path / "runtime")

    assert parse_queue_sas(values["JIEJIAN_SAMPLE_QUEUE_SAS"]) == values["JIEJIAN_SAMPLE_QUEUE_SAS"]
    assert parse_blob_sas(values["JIEJIAN_SAMPLE_BLOB_SAS"]) == values["JIEJIAN_SAMPLE_BLOB_SAS"]
    opaque_names = {
        "JIEJIAN_SAMPLE_ALICE_PASSWORD",
        "JIEJIAN_SAMPLE_BOB_PASSWORD",
        "JIEJIAN_SAMPLE_ALICE_SESSION",
        "JIEJIAN_SAMPLE_BOB_SESSION",
        "JIEJIAN_SAMPLE_TASK_BEARER",
        "JIEJIAN_SAMPLE_OWNER_OBSERVER",
    }
    opaque_values = {values[name] for name in opaque_names}
    assert len(opaque_values) == len(opaque_names)
    assert all("=" not in value and "&" not in value for value in opaque_values)


def test_missing_or_invalid_installation_is_non_fatal_but_cannot_start(
    tmp_path: Path,
) -> None:
    missing = OfficialSampleManager(
        tmp_path / "var-missing",
        None,
        runtime_identity_environment(tmp_path / "var-missing"),
    )
    assert missing.installation.available is False

    invalid_root = tmp_path / "invalid"
    invalid_root.mkdir()
    (invalid_root / "sample.json").write_text("{}", encoding="utf-8")
    invalid = OfficialSampleManager(
        tmp_path / "var-invalid",
        invalid_root,
        runtime_identity_environment(tmp_path / "var-invalid"),
    )
    assert invalid.installation.available is False
    with pytest.raises(JiejianError) as error:
        invalid.start()
    assert error.value.code == ErrorCode.OFFICIAL_SAMPLE_UNAVAILABLE.value


def test_start_failure_log_keeps_only_stable_error_and_process_state(
    tmp_path: Path,
) -> None:
    var_dir = tmp_path / "var-failed"

    def fail_launch(*_arguments, **_keyword_arguments):
        raise OSError("sensitive launch detail")

    manager = OfficialSampleManager(
        var_dir,
        _SAMPLE_ROOT,
        runtime_identity_environment(var_dir),
        process_launcher=fail_launch,
    )
    with pytest.raises(JiejianError) as error:
        manager.start(experience_id="exp_" + "1" * 32)
    assert error.value.code == ErrorCode.OFFICIAL_SAMPLE_START_FAILED.value
    event = json.loads(
        (var_dir / "logs" / "official-samples" / ("exp_" + "1" * 32 + ".log"))
        .read_text(encoding="utf-8")
        .strip()
    )
    assert event == {
        "event_code": "OFFICIAL_SAMPLE_START_FAILED",
        "error_code": "OFFICIAL_SAMPLE_START_FAILED",
        "failure_type": "OSError",
        "process_state": "NOT_CREATED",
    }
    assert "sensitive" not in json.dumps(event)


def test_start_failure_log_identifies_missing_common_identity_without_values(
    tmp_path: Path,
) -> None:
    var_dir = tmp_path / "var-missing-identity"

    def fail_launch(environment, *_arguments, **keyword_arguments):
        missing = dict(environment)
        missing.pop("JIEJIAN_RUNTIME_FINGERPRINT")
        return minimal_process_environment(
            missing,
            role=keyword_arguments["role"],
            secret_names=keyword_arguments["secret_names"],
        )

    manager = OfficialSampleManager(
        var_dir,
        _SAMPLE_ROOT,
        runtime_identity_environment(var_dir),
        process_launcher=fail_launch,
    )
    with pytest.raises(JiejianError) as error:
        manager.start(experience_id="exp_" + "2" * 32)
    assert error.value.code == ErrorCode.RUNTIME_ENVIRONMENT_INVALID.value
    event = json.loads(
        (var_dir / "logs" / "official-samples" / ("exp_" + "2" * 32 + ".log"))
        .read_text(encoding="utf-8")
        .strip()
    )
    assert event == {
        "event_code": "OFFICIAL_SAMPLE_START_FAILED",
        "error_code": "RUNTIME_ENVIRONMENT_INVALID",
        "failure_type": "JiejianError",
        "process_state": "NOT_CREATED",
        "reason": "COMMON_IDENTITY_MISSING",
        "missing_names": ["JIEJIAN_RUNTIME_FINGERPRINT"],
    }


def test_official_sample_runs_from_copied_source_with_dynamic_port_and_no_secret_files(
    tmp_path: Path,
) -> None:
    var_dir = tmp_path / "var"
    manager = OfficialSampleManager(
        var_dir,
        _SAMPLE_ROOT,
        runtime_identity_environment(var_dir),
    )
    assert manager.installation.available is True

    runtime = manager.start()
    try:
        assert runtime.experience_id.startswith("exp_")
        assert runtime.source_root == (
            var_dir / "runtime" / "official-samples" / runtime.experience_id / "source"
        ).resolve()
        assert runtime.runtime_root == (
            var_dir / "runtime" / "official-samples" / runtime.experience_id / "state"
        ).resolve()
        assert runtime.origin.startswith("http://127.0.0.1:")
        assert not runtime.origin.endswith(":8865")
        assert (runtime.source_root / "server.py").is_file()
        assert not (runtime.source_root / "collaboration_space").exists()
        assert runtime.descriptor_path.is_file()
        descriptor = json.loads(runtime.descriptor_path.read_text(encoding="utf-8"))
        assert "mode" not in descriptor
        with httpx.Client(base_url=runtime.origin, trust_env=False) as client:
            assert client.get("/health").status_code == 200
        requested = manager.resolve_secret_names(
            [
                "JIEJIAN_SAMPLE_OWNER_OBSERVER",
                "JIEJIAN_SAMPLE_QUEUE_SAS",
                "JIEJIAN_SAMPLE_BLOB_SAS",
                "UNRELATED_SECRET",
            ]
        )
        assert set(requested) == {
            "JIEJIAN_SAMPLE_OWNER_OBSERVER",
            "JIEJIAN_SAMPLE_QUEUE_SAS",
            "JIEJIAN_SAMPLE_BLOB_SAS",
        }
        assert parse_queue_sas(requested["JIEJIAN_SAMPLE_QUEUE_SAS"])
        assert parse_blob_sas(requested["JIEJIAN_SAMPLE_BLOB_SAS"])
        secret_values = tuple(runtime.secrets.values())
        for root in (runtime.source_root, runtime.runtime_root):
            for path in root.rglob("*"):
                if path.is_file():
                    content = path.read_bytes()
                    assert not any(value.encode("utf-8") in content for value in secret_values)
    finally:
        manager.stop(runtime.experience_id)
    assert manager.active is None
    assert not runtime.experience_root.exists()
    assert runtime.log_path.is_file()
    assert runtime.secrets == {}


def test_behavior_switch_keeps_origin_and_source_but_resets_sample_state(
    tmp_path: Path,
) -> None:
    var_dir = tmp_path / "var"
    manager = OfficialSampleManager(
        var_dir,
        _SAMPLE_ROOT,
        runtime_identity_environment(var_dir),
    )
    runtime = manager.start()
    try:
        switched = manager.switch_behavior(
            runtime.experience_id,
            authorization_order="AUTHORIZE_BEFORE_ENQUEUE",
            blob_observation="UNAVAILABLE",
        )
        assert switched.origin == runtime.origin
        assert switched.source_root == runtime.source_root
        assert json.loads(runtime.control_path.read_text(encoding="utf-8")) == {
            "schema_version": "1",
            "authorization_order": "AUTHORIZE_BEFORE_ENQUEUE",
            "blob_observation": "UNAVAILABLE",
        }
    finally:
        manager.stop()
