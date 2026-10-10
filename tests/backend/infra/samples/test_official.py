# 验证官方 Sample 的显式安装、隔离复制、动态端口与秘密/进程树边界。

from __future__ import annotations

import json
from pathlib import Path

import pytest

from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.infra.observers.adapters.azure_blob import _parse_sas as parse_blob_sas
from product.backend.infra.observers.adapters.azure_queue import _parse_sas as parse_queue_sas
from product.backend.infra.samples import OfficialSampleManager
from product.backend.infra.samples.official import _new_secret_values
from product.backend.infra.runtime.process.environment import (
    minimal_process_environment,
)
from tests.fixtures.runtime.runtime_environment import runtime_identity_environment, write_python_installation_contract




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
        write_python_installation_contract(tmp_path / "installation-contract"),
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
        write_python_installation_contract(tmp_path / "installation-contract"),
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
