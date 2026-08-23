from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.infra.runtime.job_requests import (
    ExecutionRequestStore,
    PersistedExecutionRequest,
    canonical_execution_request_bytes,
    parse_execution_request,
    required_secret_names,
)
from product.backend.infra.runtime.process_environment import ProcessEnvironmentRole, minimal_process_environment
from tests.fixtures.runtime_environment import runtime_identity_environment
from tests.fixtures.runner import runner_input as make_runner_input


def test_request_store_is_canonical_hashed_atomic_and_idempotent(
    runtime_request_factory,
    tmp_path: Path,
) -> None:
    request = runtime_request_factory()
    store = ExecutionRequestStore(tmp_path / "var")
    job_id = "job_0123456789abcdef0123456789abcdef"
    request_hash, created = store.write(job_id, request)
    repeated_hash, repeated_created = store.write(job_id, request)

    assert created is True
    assert repeated_created is False
    assert repeated_hash == request_hash
    assert request_hash == hashlib.sha256(
        canonical_execution_request_bytes(request)
    ).hexdigest()
    assert store.load(job_id, expected_hash=request_hash) == request
    assert not list((tmp_path / "var").rglob("*.tmp-*"))


def test_request_store_rejects_drift_duplicate_keys_and_known_secrets(
    runtime_request_factory,
    tmp_path: Path,
) -> None:
    request = runtime_request_factory()
    store = ExecutionRequestStore(tmp_path / "var")
    job_id = "job_fedcba9876543210fedcba9876543210"
    request_hash, _ = store.write(job_id, request)
    path = store.path_for(job_id)
    path.write_bytes(path.read_bytes().replace(b'"schema_version":"4"', b'"schema_version":"4","schema_version":"4"', 1))
    drift_hash = hashlib.sha256(path.read_bytes()).hexdigest()
    with pytest.raises(JiejianError) as duplicate:
        store.load(job_id, expected_hash=drift_hash)
    assert duplicate.value.code == ErrorCode.JOB_REQUEST_CONFLICT.value

    sentinel = "runtime-request-real-secret-sentinel"
    exposed_payload = request.model_dump(mode="python")
    exposed_payload["project_snapshot"]["project_name"] = f"ordinary-{sentinel}"
    exposed_request = PersistedExecutionRequest.model_validate(
        exposed_payload, strict=True
    )
    with pytest.raises(JiejianError) as exposed:
        canonical_execution_request_bytes(exposed_request, known_secrets=(sentinel,))
    assert exposed.value.code == ErrorCode.JOB_SECRET.value
    assert sentinel not in str(exposed.value)
    assert sentinel not in json.dumps(exposed.value.to_dict(), ensure_ascii=False)
    assert request_hash != drift_hash


def test_request_parser_and_minimal_environment_do_not_copy_parent_values(
    runtime_request_factory,
    tmp_path: Path,
) -> None:
    request = runtime_request_factory()
    raw = canonical_execution_request_bytes(request)
    assert parse_execution_request(raw) == request
    environment = minimal_process_environment(
        runtime_identity_environment(
            tmp_path / "var",
            extra={
                "PATH": "C:\\Tools",
                "UNRELATED_PARENT_SECRET": "must-not-cross",
                "NEEDED_SECRET": "only-this-value",
            },
        ),
        role=ProcessEnvironmentRole.RUNNER,
        secret_names=("NEEDED_SECRET",),
    )
    assert environment["NEEDED_SECRET"] == "only-this-value"
    assert "UNRELATED_PARENT_SECRET" not in environment
    assert environment["PYTHONDONTWRITEBYTECODE"] == "1"


def test_current_request_store_dispatches_canonical_and_uses_minimal_secret_refs(tmp_path: Path) -> None:
    runner_input = make_runner_input()
    request = PersistedExecutionRequest(
        schema_version="4",
        budget=runner_input.budget,
        project_snapshot=runner_input.project_snapshot,
    )
    store = ExecutionRequestStore(tmp_path / "var")
    job_id = "job_abcdef0123456789abcdef0123456789"
    request_hash, created = store.write(job_id, request)
    assert created is True
    assert parse_execution_request(canonical_execution_request_bytes(request)) == request
    assert store.load(job_id, expected_hash=request_hash) == request
    assert required_secret_names(request) == ("JIEJIAN_TEST_TOKEN", "OWNER_READ_ONLY")
    assert not list((tmp_path / "var").rglob("*.tmp-*"))
