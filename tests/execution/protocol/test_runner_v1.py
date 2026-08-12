from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from jiejian.domain.lifecycle import ContractStatus, JobState, RunLifecycle, RunVerdict
from jiejian.verification.models import (
    ContractRule,
    Flow,
    FlowStep,
    Identity,
    ResourceDefinition,
    RuleKind,
    SecurityContract,
    TargetScope,
)
from jiejian.errors import JiejianError
from jiejian.protocols import (
    RUNNER_INPUT_MAX_BYTES,
    RUNNER_RESULT_MAX_BYTES,
    STAGED_ARTIFACT_TOTAL_MAX_BYTES,
    CleanupResultV1,
    CleanupStatus,
    ExecutionBudgetV1,
    ExecutionProjectSnapshotV1,
    RunnerErrorV1,
    RunnerInputV1,
    RunnerResultType,
    RunnerResultV1,
    StagedArtifactV1,
    canonical_json_bytes,
    canonical_json_sha256,
    parse_runner_input,
    parse_runner_result,
)

PROJECT_ROOT = Path(__file__).resolve().parents[3]


def _runner_input(*, json_body: dict | None = None) -> RunnerInputV1:
    target = TargetScope(
        schema_version="1",
        base_url="http://127.0.0.1:8765",
        allowed_origins=("http://127.0.0.1:8765",),
        allowed_hosts=("127.0.0.1",),
        allowed_ports=(8765,),
        allow_private_network=True,
        timeout_seconds=5,
        max_requests=64,
        max_response_bytes=262_144,
    )
    identities = (
        Identity(
            schema_version="1",
            id="owner",
            role="user",
            secret_ref="env:JIEJIAN_SAMPLE_OWNER_TOKEN",
        ),
        Identity(
            schema_version="1",
            id="attacker",
            role="user",
            secret_ref="env:JIEJIAN_SAMPLE_ATTACKER_TOKEN",
        ),
    )
    resources = (
        ResourceDefinition(
            schema_version="1", id="owner-resource", owner_identity_id="owner"
        ),
        ResourceDefinition(
            schema_version="1",
            id="attacker-resource",
            owner_identity_id="attacker",
        ),
    )
    flow = Flow(
        schema_version="1",
        id="ownership-flow",
        steps=(
            FlowStep(
                schema_version="1",
                id="update-resource",
                method="PATCH",
                path="/resources/{resource_id}",
                identity_id="owner",
                resource_id="owner-resource",
                alternate_identity_id="attacker",
                alternate_resource_id="attacker-resource",
                json_body=json_body or {"value": "baseline-value"},
                expected_statuses=(200,),
            ),
        ),
    )
    contract = SecurityContract(
        schema_version="1",
        id="ownership-contract",
        version=1,
        status=ContractStatus.ACTIVE,
        rules=(
            ContractRule(
                schema_version="1",
                id="foreign-read",
                kind=RuleKind.FOREIGN_READ,
                required_observers=("http",),
                severity="high",
            ),
            ContractRule(
                schema_version="1",
                id="unauthorized-side-effect",
                kind=RuleKind.UNAUTHORIZED_SIDE_EFFECT,
                required_observers=("http", "owner_api"),
                severity="critical",
            ),
            ContractRule(
                schema_version="1",
                id="privileged-field",
                kind=RuleKind.PRIVILEGED_FIELD,
                required_observers=("http", "owner_api"),
                severity="critical",
            ),
        ),
    )
    return RunnerInputV1(
        schema_version="1",
        run_id="run_0123456789abcdef0123456789abcdef",
        job_id="job_fedcba9876543210fedcba9876543210",
        attempt=1,
        lease_owner="worker-local-1",
        fencing_token=7,
        created_at_us=1_754_630_400_000_000,
        budget=ExecutionBudgetV1(
            schema_version="1",
            max_requests=64,
            request_timeout_us=5_000_000,
            max_duration_us=600_000_000,
            max_response_bytes=262_144,
            max_parallel_cases=1,
        ),
        project_snapshot=ExecutionProjectSnapshotV1(
            schema_version="1",
            project_id="ownership-safe",
            project_name="Ownership safe",
            target=target,
            identities=identities,
            resources=resources,
            flow=flow,
            contract=contract,
            owner_observer_enabled=True,
            mutation_seed=7,
        ),
    )


def _cleanup(status: CleanupStatus = CleanupStatus.SUCCEEDED) -> CleanupResultV1:
    return CleanupResultV1(
        schema_version="1",
        status=status,
        reason_codes=("CLEANUP_FAILED",) if status is CleanupStatus.FAILED else (),
    )


def _runner_result(
    *,
    result_type: RunnerResultType = RunnerResultType.SUCCESS,
    run_lifecycle: RunLifecycle = RunLifecycle.COMPLETED,
    job_state: JobState = JobState.SUCCEEDED,
    verdict: RunVerdict | None = RunVerdict.PASS,
    cleanup: CleanupResultV1 | None = None,
    error: RunnerErrorV1 | None = None,
    reason_codes: tuple[str, ...] = (),
) -> RunnerResultV1:
    return RunnerResultV1(
        schema_version="1",
        run_id="run_0123456789abcdef0123456789abcdef",
        job_id="job_fedcba9876543210fedcba9876543210",
        attempt=1,
        lease_owner="worker-local-1",
        fencing_token=7,
        finished_at_us=1_754_630_400_500_000,
        result_type=result_type,
        run_lifecycle=run_lifecycle,
        job_state=job_state,
        verdict=verdict,
        reason_codes=reason_codes,
        cleanup=cleanup or _cleanup(),
        error=error,
        artifacts=(
            StagedArtifactV1(
                schema_version="1",
                path="evidence/ev_abc.json",
                byte_count=128,
                sha256="a" * 64,
            ),
        ),
    )


def test_runner_protocols_are_strict_frozen_round_trip_documents() -> None:
    runner_input = _runner_input()
    runner_result = _runner_result()

    assert parse_runner_input(canonical_json_bytes(runner_input)) == runner_input
    assert parse_runner_result(canonical_json_bytes(runner_result)) == runner_result
    assert RunnerInputV1.model_config["extra"] == "forbid"
    assert RunnerInputV1.model_config["frozen"] is True
    assert RunnerResultV1.model_config["extra"] == "forbid"
    assert RunnerResultV1.model_config["frozen"] is True
    assert "flow_path" not in runner_input.project_snapshot.model_dump()
    assert "contract_path" not in runner_input.project_snapshot.model_dump()
    with pytest.raises(ValidationError):
        runner_input.attempt = 2


def test_canonical_json_and_hash_ignore_input_key_order() -> None:
    original = _runner_input()
    document = json.loads(canonical_json_bytes(original))
    reversed_document = dict(reversed(tuple(document.items())))

    first = parse_runner_input(
        json.dumps(document, ensure_ascii=False, separators=(",", ":")).encode()
    )
    second = parse_runner_input(
        json.dumps(reversed_document, ensure_ascii=False, separators=(",", ":")).encode()
    )

    assert canonical_json_bytes(first) == canonical_json_bytes(second)
    assert canonical_json_sha256(first) == canonical_json_sha256(second)
    assert len(canonical_json_sha256(first)) == 64


@pytest.mark.parametrize(
    "raw",
    [
        b'{"schema_version":"1","schema_version":"1"}',
        b'{"schema_version":"1","value":NaN}',
        b'{"schema_version":"1","value":Infinity}',
        b'\xef\xbb\xbf{"schema_version":"1"}',
    ],
)
def test_parser_rejects_duplicate_keys_non_finite_values_and_bom(raw: bytes) -> None:
    with pytest.raises(JiejianError) as captured:
        parse_runner_input(raw)
    assert captured.value.code == "PROTOCOL_INVALID"


def test_parser_rejects_unknown_fields_versions_and_non_integer_time() -> None:
    data = json.loads(canonical_json_bytes(_runner_input()))
    invalid_documents = []
    invalid_documents.append({**data, "unknown": True})
    invalid_documents.append({**data, "schema_version": "2"})
    invalid_documents.append({**data, "created_at_us": "1754630400000000"})
    invalid_documents.append({**data, "created_at_us": 1.5})

    for document in invalid_documents:
        with pytest.raises(JiejianError) as captured:
            parse_runner_input(json.dumps(document, separators=(",", ":")).encode())
        assert captured.value.code == "PROTOCOL_INVALID"


def test_parser_rejects_oversize_before_json_parsing() -> None:
    with pytest.raises(JiejianError) as input_error:
        parse_runner_input(b"x" * (RUNNER_INPUT_MAX_BYTES + 1))
    assert input_error.value.code == "PROTOCOL_TOO_LARGE"

    with pytest.raises(JiejianError) as result_error:
        parse_runner_result(b"x" * (RUNNER_RESULT_MAX_BYTES + 1))
    assert result_error.value.code == "PROTOCOL_TOO_LARGE"


def test_non_finite_nested_snapshot_is_rejected() -> None:
    with pytest.raises(ValidationError):
        _runner_input(json_body={"value": float("nan")})


def test_real_secret_never_appears_in_protocol_errors_or_schemas() -> None:
    sentinel = "stage2-real-secret-sentinel"
    document = json.loads(canonical_json_bytes(_runner_input()))
    document["project_snapshot"]["identities"][0]["secret_ref"] = sentinel
    secret_documents = (document, {**document, sentinel: True})

    for secret_document in secret_documents:
        raw = json.dumps(
            secret_document, ensure_ascii=False, separators=(",", ":")
        ).encode()
        with pytest.raises(JiejianError) as captured:
            parse_runner_input(raw)
        assert sentinel not in str(captured.value)
        assert sentinel not in json.dumps(captured.value.to_dict())
    assert sentinel.encode() not in canonical_json_bytes(_runner_input())
    for model in (RunnerInputV1, RunnerResultV1):
        assert sentinel not in json.dumps(model.model_json_schema())
    assert all(
        identity.secret_ref.startswith("env:")
        for identity in _runner_input().project_snapshot.identities
    )


def test_known_secret_scan_covers_models_parsed_values_and_unknown_keys() -> None:
    sentinel = "stage2-real-secret-sentinel"
    secret_input = _runner_input().model_copy(update={"lease_owner": sentinel})
    input_document = json.loads(canonical_json_bytes(_runner_input()))
    input_document["project_snapshot"]["project_name"] = f"project-{sentinel}"
    result_document = json.loads(canonical_json_bytes(_runner_result()))
    result_document["artifacts"][0]["path"] = f"evidence/{sentinel}.json"
    unknown_key_document = {
        **json.loads(canonical_json_bytes(_runner_input())),
        f"unknown-{sentinel}": True,
    }
    operations = (
        lambda: canonical_json_bytes(secret_input, known_secrets=(sentinel,)),
        lambda: canonical_json_sha256(secret_input, known_secrets=(sentinel,)),
        lambda: parse_runner_input(
            json.dumps(input_document, separators=(",", ":")).encode(),
            known_secrets=(sentinel,),
        ),
        lambda: parse_runner_result(
            json.dumps(result_document, separators=(",", ":")).encode(),
            known_secrets=(sentinel,),
        ),
        lambda: parse_runner_input(
            json.dumps(unknown_key_document, separators=(",", ":")).encode(),
            known_secrets=(sentinel,),
        ),
    )

    for operation in operations:
        with pytest.raises(JiejianError) as captured:
            operation()
        assert captured.value.code == "PROTOCOL_SECRET_EXPOSED"
        assert str(captured.value) == (
            "PROTOCOL_SECRET_EXPOSED: 协议文档包含已知秘密"
        )
        assert sentinel not in str(captured.value)
        assert sentinel not in json.dumps(captured.value.to_dict())
    assert canonical_json_bytes(_runner_input(), known_secrets=("",)) == (
        canonical_json_bytes(_runner_input())
    )
    assert parse_runner_input(
        canonical_json_bytes(_runner_input()), known_secrets=("",)
    ) == _runner_input()
    for model in (RunnerInputV1, RunnerResultV1):
        assert sentinel not in json.dumps(model.model_json_schema())


def test_snapshot_rejects_duplicate_step_rule_ids_and_rule_kinds() -> None:
    snapshot = _runner_input().project_snapshot
    step = snapshot.flow.steps[0]
    duplicate_step_flow = snapshot.flow.model_copy(update={"steps": (step, step)})
    first_rule, second_rule, third_rule = snapshot.contract.rules
    duplicate_id_contract = snapshot.contract.model_copy(
        update={
            "rules": (
                first_rule,
                second_rule.model_copy(update={"id": first_rule.id}),
                third_rule,
            )
        }
    )
    duplicate_kind_contract = snapshot.contract.model_copy(
        update={
            "rules": (
                first_rule,
                second_rule.model_copy(
                    update={"id": "second-foreign-read", "kind": first_rule.kind}
                ),
                third_rule,
            )
        }
    )

    for changes in (
        {"flow": duplicate_step_flow},
        {"contract": duplicate_id_contract},
        {"contract": duplicate_kind_contract},
    ):
        data = snapshot.model_dump(mode="python")
        data.update(changes)
        with pytest.raises(ValidationError):
            ExecutionProjectSnapshotV1.model_validate(data)


def test_snapshot_requires_active_contract_and_flow_relationship_rules() -> None:
    snapshot = _runner_input().project_snapshot
    foreign_rule, side_effect_rule, _ = snapshot.contract.rules
    draft_contract = snapshot.contract.model_copy(
        update={"status": ContractStatus.DRAFT}
    )
    mutation_contract = snapshot.contract.model_copy(update={"rules": (foreign_rule,)})
    get_flow = snapshot.flow.model_copy(
        update={
            "steps": (
                snapshot.flow.steps[0].model_copy(update={"method": "GET"}),
            )
        }
    )
    get_contract = snapshot.contract.model_copy(update={"rules": (side_effect_rule,)})

    for changes in (
        {"contract": draft_contract},
        {"contract": mutation_contract},
        {"flow": get_flow, "contract": get_contract},
    ):
        data = snapshot.model_dump(mode="python")
        data.update(changes)
        with pytest.raises(ValidationError):
            ExecutionProjectSnapshotV1.model_validate(data)


@pytest.mark.parametrize("verdict", tuple(RunVerdict))
def test_success_result_accepts_all_security_verdicts(verdict: RunVerdict) -> None:
    result = _runner_result(verdict=verdict)
    assert result.run_lifecycle is RunLifecycle.COMPLETED
    assert result.job_state is JobState.SUCCEEDED


def test_non_success_result_matrix_accepts_only_defined_combinations() -> None:
    safety_stop = _runner_result(
        result_type=RunnerResultType.SAFETY_STOPPED,
        run_lifecycle=RunLifecycle.SAFETY_STOPPED,
        job_state=JobState.SUCCEEDED,
        verdict=None,
        reason_codes=("SCOPE_PRIVATE_NETWORK",),
    )
    cancelled = _runner_result(
        result_type=RunnerResultType.CANCELLED,
        run_lifecycle=RunLifecycle.CANCELLED,
        job_state=JobState.CANCELLED,
        verdict=None,
    )
    retryable = _runner_result(
        result_type=RunnerResultType.RETRYABLE_ERROR,
        run_lifecycle=RunLifecycle.EXECUTING,
        job_state=JobState.RETRY_WAIT,
        verdict=None,
        error=RunnerErrorV1(
            schema_version="1", code="EXEC_TIMEOUT", retryable=True
        ),
    )
    fatal = _runner_result(
        result_type=RunnerResultType.FATAL_ERROR,
        run_lifecycle=RunLifecycle.FAILED,
        job_state=JobState.FAILED,
        verdict=None,
        cleanup=_cleanup(CleanupStatus.FAILED),
        error=RunnerErrorV1(
            schema_version="1", code="CLEANUP_FAILED", retryable=False
        ),
    )

    assert safety_stop.verdict is None
    assert cancelled.cleanup.status is CleanupStatus.SUCCEEDED
    assert retryable.run_lifecycle is RunLifecycle.EXECUTING
    assert fatal.cleanup.status is CleanupStatus.FAILED


@pytest.mark.parametrize(
    "changes",
    [
        {"run_lifecycle": RunLifecycle.FAILED},
        {"job_state": JobState.FAILED},
        {"verdict": None},
        {
            "result_type": RunnerResultType.SAFETY_STOPPED,
            "run_lifecycle": RunLifecycle.SAFETY_STOPPED,
            "verdict": RunVerdict.INCONCLUSIVE,
            "reason_codes": ("EXEC_BUDGET",),
        },
        {
            "result_type": RunnerResultType.CANCELLED,
            "run_lifecycle": RunLifecycle.CANCELLED,
            "job_state": JobState.CANCELLED,
            "verdict": None,
            "cleanup": _cleanup(CleanupStatus.NOT_REQUIRED),
        },
        {
            "result_type": RunnerResultType.RETRYABLE_ERROR,
            "run_lifecycle": RunLifecycle.EXECUTING,
            "job_state": JobState.RETRY_WAIT,
            "verdict": RunVerdict.INCONCLUSIVE,
            "error": RunnerErrorV1(
                schema_version="1", code="EXEC_TIMEOUT", retryable=True
            ),
        },
        {
            "result_type": RunnerResultType.FATAL_ERROR,
            "run_lifecycle": RunLifecycle.FAILED,
            "job_state": JobState.FAILED,
            "verdict": RunVerdict.INCONCLUSIVE,
            "error": RunnerErrorV1(
                schema_version="1", code="EXEC_REQUEST", retryable=False
            ),
        },
    ],
)
def test_result_model_rejects_matrix_contradictions(changes: dict) -> None:
    data = _runner_result().model_dump(mode="python")
    data.update(changes)
    with pytest.raises(ValidationError):
        RunnerResultV1.model_validate(data)


@pytest.mark.parametrize(
    "path",
    [
        "/absolute.json",
        "C:/drive.json",
        "evidence\\item.json",
        "evidence/file.txt:stream",
        "evidence//item.json",
        "./item.json",
        "evidence/../item.json",
        "evidence/./item.json",
        "NUL",
        "nul.json",
        "PRN.log",
        "COM1",
        "lpt9.txt",
        "name.",
        "name ",
        "evidence/item\x00.json",
        f"evidence/{'a' * 256}",
    ],
)
def test_artifact_path_rejects_non_normalized_relative_paths(path: str) -> None:
    with pytest.raises(ValidationError):
        StagedArtifactV1(
            schema_version="1", path=path, byte_count=1, sha256="a" * 64
        )


def test_artifact_hash_size_and_casefold_duplicate_paths_are_constrained() -> None:
    with pytest.raises(ValidationError):
        StagedArtifactV1(
            schema_version="1", path="a.json", byte_count=-1, sha256="a" * 64
        )
    with pytest.raises(ValidationError):
        StagedArtifactV1(
            schema_version="1", path="a.json", byte_count=1, sha256="A" * 64
        )
    first = StagedArtifactV1(
        schema_version="1", path="A.json", byte_count=1, sha256="a" * 64
    )
    second = StagedArtifactV1(
        schema_version="1", path="a.json", byte_count=1, sha256="b" * 64
    )
    data = _runner_result().model_dump(mode="python")
    data["artifacts"] = (first, second)
    with pytest.raises(ValidationError):
        RunnerResultV1.model_validate(data)


def test_artifact_total_byte_count_limit_is_inclusive() -> None:
    at_limit = StagedArtifactV1(
        schema_version="1",
        path="at-limit.bin",
        byte_count=STAGED_ARTIFACT_TOTAL_MAX_BYTES,
        sha256="a" * 64,
    )
    extra_byte = StagedArtifactV1(
        schema_version="1",
        path="extra-byte.bin",
        byte_count=1,
        sha256="b" * 64,
    )
    data = _runner_result().model_dump(mode="python")
    data["artifacts"] = (at_limit,)
    assert RunnerResultV1.model_validate(data).artifacts == (at_limit,)

    data["artifacts"] = (at_limit, extra_byte)
    with pytest.raises(ValidationError):
        RunnerResultV1.model_validate(data)


@pytest.mark.parametrize(
    ("model", "schema_path"),
    [
        (
            RunnerInputV1,
            PROJECT_ROOT / "schemas" / "runner" / "runner-input-v1.schema.json",
        ),
        (
            RunnerResultV1,
            PROJECT_ROOT / "schemas" / "runner" / "runner-result-v1.schema.json",
        ),
    ],
)
def test_checked_in_json_schema_has_no_drift(model, schema_path: Path) -> None:
    checked_in = json.loads(schema_path.read_text(encoding="utf-8"))
    assert checked_in == model.model_json_schema()
