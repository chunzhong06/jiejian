# 验证观察器基础设施中的Azure Blob 观察器。

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import httpx
import pytest

import product.backend.infra.observers.azure_blob as blob_module
from product.protocols import (
    AzureBlobObjectLocator,
    BlobObjectScanBudget,
    Correlation,
    ObservationCompleteness,
    ObservationPhase,
    ObserverBudget,
    ObserverOutcomeStatus,
    ObserverSpec,
    ObserverTarget,
    ObserverType,
)
from tests.fixtures.runtime_environment import runtime_identity_environment


SAS = "sv=2023-11-03&se=2099-01-01T00%3A00%3A00Z&sp=rl&sr=c&sig=opaque-signature"
CORRELATION = Correlation(case_id="case-1", resource_id="resource-a", request_marker="case-1")


def _spec(
    *,
    page_size: int = 2,
    max_pages: int = 4,
    max_objects: int = 8,
    max_object_bytes: int = 4096,
    max_total_bytes: int = 32_768,
    max_attempts: int = 1,
    timeout_us: int = 5_000_000,
    prefix_template: str = "cases/{request_marker}/",
) -> ObserverSpec:
    locator = AzureBlobObjectLocator(
        allow_loopback_http=True,
        service_url="http://127.0.0.1:10000/devstoreaccount1",
        container_name="container-test",
        prefix_template=prefix_template,
        read_only_sas_ref="env:BLOB_SAS",
        exclusive_test_container=True,
        allowed_metadata_fields=("case_tag", "resource_id", "effect", "revision"),
        scan_budget=BlobObjectScanBudget(
            page_size=page_size,
            max_pages=max_pages,
            max_objects=max_objects,
            max_object_bytes=max_object_bytes,
            max_total_bytes=max_total_bytes,
            max_attempts=max_attempts,
            per_request_timeout_us=100_000,
            retry_interval_us=0,
        ),
    )
    return ObserverSpec(
        observer_id="blob-observer",
        observer_type=ObserverType.AZURE_BLOB_OBJECT,
        target=ObserverTarget(target_id="blob-target", locator=locator, normalization_id="blob", normalization_version="1.0"),
        phases=(ObservationPhase.BEFORE,),
        required=True,
        budget=ObserverBudget(timeout_us=timeout_us, max_rows=max_objects, max_bytes=max_total_bytes),
    )


def _metadata(case_tag: str = "case-1", resource_id: str = "resource-a", **extra: str) -> dict[str, str]:
    return {"case_tag": case_tag, "resource_id": resource_id, **extra}


def _blob(name: str, content: bytes = b"alpha", *, etag: str = "etag-a", metadata: dict[str, str] | None = None) -> dict[str, Any]:
    return {"name": name, "etag": etag, "content_length": len(content), "content": content, "metadata": metadata or _metadata()}


def _list_xml(items: list[dict[str, Any]], *, next_marker: str = "") -> bytes:
    blobs = []
    for item in items:
        metadata = "".join(f"<{key}>{value}</{key}>" for key, value in sorted(item["metadata"].items()))
        blobs.append(
            f"<Blob><Name>{item['name']}</Name><Properties><Etag>{item['etag']}</Etag>"
            f"<Content-Length>{item['content_length']}</Content-Length></Properties><Metadata>{metadata}</Metadata></Blob>"
        )
    return f"<EnumerationResults><Blobs>{''.join(blobs)}</Blobs><NextMarker>{next_marker}</NextMarker></EnumerationResults>".encode()


class _Response:
    def __init__(self, payload: bytes = b"", status_code: int = 200, headers: dict[str, str] | None = None) -> None:
        self.payload = payload
        self.status_code = status_code
        self.headers = headers or {}

    def iter_bytes(self):
        yield self.payload


class _Stream:
    def __init__(self, response: _Response) -> None:
        self.response = response

    def __enter__(self) -> _Response:
        return self.response

    def __exit__(self, *args: object) -> None:
        return None


def _run_fake(monkeypatch: pytest.MonkeyPatch, responses: list[_Response | Exception], *, spec: ObserverSpec | None = None):
    monkeypatch.setenv("BLOB_SAS", SAS)
    queue = list(responses)
    calls: list[tuple[str, str, dict[str, str]]] = []

    class Client:
        def stream(self, method: str, url: str, *, headers: dict[str, str]) -> _Stream:
            calls.append((method, url, headers))
            item = queue.pop(0)
            if isinstance(item, Exception):
                raise item
            return _Stream(item)

        def close(self) -> None:
            return None

    monkeypatch.setattr(blob_module.httpx, "Client", lambda **kwargs: Client())
    invocation = blob_module.ObserverInvocation(spec=spec or _spec(), correlation=CORRELATION, phase=ObservationPhase.BEFORE)
    envelope = blob_module._run_child(invocation, utc_now_us=lambda: 100)
    return envelope, blob_module.evaluate_observer_outcome(envelope, required=True), calls


def _responses_for(items: list[dict[str, Any]], *, status: int = 200) -> list[_Response]:
    items = sorted(items, key=lambda item: item["name"])
    responses: list[_Response] = [_Response(_list_xml(items), status)]
    for item in items:
        responses.append(_Response(b"", 200, {"etag": f'"{item["etag"]}"', "content-length": str(item["content_length"]), **{f"x-ms-meta-{key}": value for key, value in item["metadata"].items()}}))
        responses.append(_Response(item["content"], 200, {"etag": item["etag"], "content-length": str(item["content_length"])}))
    return responses


def test_blob_complete_is_stable_sorted_and_only_list_head_get(monkeypatch: pytest.MonkeyPatch) -> None:
    items = [_blob("cases/case-1/z.txt", b"z", etag="z"), _blob("cases/case-1/a.txt", b"a", etag="a")]
    first, first_outcome, calls = _run_fake(monkeypatch, _responses_for(items))
    second, second_outcome, _ = _run_fake(monkeypatch, _responses_for(items))
    assert first.completeness is ObservationCompleteness.COMPLETE
    assert first_outcome.status is ObserverOutcomeStatus.AVAILABLE
    assert second_outcome.status is ObserverOutcomeStatus.AVAILABLE
    assert first.state == second.state
    assert first.state is not None
    objects = first.state.canonical_data["objects"]
    assert [item["name"] for item in objects] == ["a.txt", "z.txt"]
    assert all(method in {"GET", "HEAD"} for method, _, _ in calls)
    assert [method for method, _, _ in calls] == ["GET", "HEAD", "GET", "HEAD", "GET"]
    assert all("sig=opaque-signature" in url for _, url, _ in calls)
    assert all("x-ms-version" in headers for _, _, headers in calls)
    assert all(word not in blob_module._object_url.__code__.co_consts for word in ("PUT", "POST", "DELETE"))


def test_blob_empty_prefix_is_complete_and_metadata_correlations_are_strict(monkeypatch: pytest.MonkeyPatch) -> None:
    empty, outcome, _ = _run_fake(monkeypatch, [_Response(_list_xml([]))])
    assert empty.completeness is ObservationCompleteness.COMPLETE
    assert outcome.status is ObserverOutcomeStatus.AVAILABLE
    assert empty.state is not None and empty.state.canonical_data["objects"] == []
    wrong = _blob("cases/case-1/wrong.txt", metadata=_metadata(case_tag="other"))
    envelope, outcome, _ = _run_fake(monkeypatch, [_Response(_list_xml([wrong]))])
    assert envelope.completeness is ObservationCompleteness.PARTIAL
    assert outcome.status is ObserverOutcomeStatus.INCONCLUSIVE
    assert blob_module.AZURE_BLOB_CORRELATION_CONFLICT in envelope.reason_codes


def test_blob_pagination_and_budget_boundaries(monkeypatch: pytest.MonkeyPatch) -> None:
    first = _blob("cases/case-1/a.txt", b"a", etag="a")
    second = _blob("cases/case-1/b.txt", b"b", etag="b")
    responses = [_Response(_list_xml([first], next_marker="page-2")), _Response(_list_xml([second]))]
    responses.extend(_responses_for([first])[1:])
    responses.extend(_responses_for([second])[1:])
    complete, outcome, calls = _run_fake(monkeypatch, responses, spec=_spec(page_size=1))
    assert complete.completeness is ObservationCompleteness.COMPLETE
    assert outcome.status is ObserverOutcomeStatus.AVAILABLE
    assert [method for method, _, _ in calls].count("GET") == 4
    limited, outcome, _ = _run_fake(monkeypatch, [_Response(_list_xml([first], next_marker="page-2"))], spec=_spec(page_size=1, max_pages=1))
    assert limited.completeness is ObservationCompleteness.PARTIAL
    assert limited.reason_codes == (blob_module.AZURE_BLOB_PAGE_LIMIT,)
    assert outcome.status is ObserverOutcomeStatus.INCONCLUSIVE


def test_blob_head_get_lengths_and_object_budget_are_not_silent(monkeypatch: pytest.MonkeyPatch) -> None:
    item = _blob("cases/case-1/a.txt", b"alpha")
    bad_head = _Response(b"", 200, {"etag": '"a"', "content-length": "99", "x-ms-meta-case_tag": "case-1", "x-ms-meta-resource_id": "resource-a"})
    envelope, outcome, _ = _run_fake(monkeypatch, [_Response(_list_xml([item])), bad_head], spec=_spec())
    assert envelope.completeness is ObservationCompleteness.PARTIAL
    assert outcome.status is ObserverOutcomeStatus.INCONCLUSIVE


def test_blob_etag_normalization_accepts_service_quote_difference_and_rejects_conflicts(monkeypatch: pytest.MonkeyPatch) -> None:
    assert blob_module._normalize_etag("etag-a") == "etag-a"
    assert blob_module._normalize_etag('"etag-a"') == "etag-a"
    for value in ("", '"unterminated', 'unterminated"', 'W/"weak"', '"in"ternal"', '"back\\slash"'):
        with pytest.raises(ValueError):
            blob_module._normalize_etag(value)
    item = _blob("cases/case-1/a.txt", b"alpha", etag="list-etag")
    conflicting_head = _Response(b"", 200, {"etag": '"different-etag"', "content-length": "5", "x-ms-meta-case_tag": "case-1", "x-ms-meta-resource_id": "resource-a"})
    envelope, outcome, _ = _run_fake(monkeypatch, [_Response(_list_xml([item])), conflicting_head], spec=_spec())
    assert envelope.completeness is ObservationCompleteness.PARTIAL
    assert envelope.reason_codes == (blob_module.AZURE_BLOB_OBJECT_CONFLICT,)
    assert outcome.status is ObserverOutcomeStatus.INCONCLUSIVE
    small = _blob("cases/case-1/a.txt", b"alpha")
    envelope, outcome, _ = _run_fake(monkeypatch, [_Response(_list_xml([small]))], spec=_spec(max_object_bytes=2))
    assert envelope.completeness is ObservationCompleteness.PARTIAL
    assert envelope.reason_codes == (blob_module.AZURE_BLOB_OBJECT_BYTES,)
    assert outcome.status is ObserverOutcomeStatus.INCONCLUSIVE


@pytest.mark.parametrize("status,reason", [(401, blob_module.AZURE_BLOB_AUTH), (403, blob_module.AZURE_BLOB_AUTH), (404, blob_module.AZURE_BLOB_RESOURCE_MISSING), (302, blob_module.AZURE_BLOB_REDIRECT), (400, blob_module.AZURE_BLOB_HTTP_ERROR)])
def test_blob_http_failures_are_stable_and_not_retried(monkeypatch: pytest.MonkeyPatch, status: int, reason: str) -> None:
    envelope, outcome, calls = _run_fake(monkeypatch, [_Response(b"failure", status)], spec=_spec(max_attempts=3, timeout_us=6_000_000))
    assert envelope.completeness is ObservationCompleteness.PARTIAL
    assert envelope.reason_codes == (reason,)
    assert outcome.status is ObserverOutcomeStatus.INCONCLUSIVE
    assert len(calls) == 1


def test_blob_retry_matrix(monkeypatch: pytest.MonkeyPatch) -> None:
    item = _blob("cases/case-1/a.txt", b"a")
    envelope, outcome, calls = _run_fake(monkeypatch, [_Response(b"busy", 429), *_responses_for([item])], spec=_spec(max_attempts=2, timeout_us=6_000_000))
    assert envelope.completeness is ObservationCompleteness.COMPLETE
    assert outcome.status is ObserverOutcomeStatus.AVAILABLE
    assert len(calls) == 4
    envelope, outcome, calls = _run_fake(monkeypatch, [httpx.ConnectError("offline"), *_responses_for([item])], spec=_spec(max_attempts=2, timeout_us=6_000_000))
    assert envelope.completeness is ObservationCompleteness.COMPLETE
    assert outcome.status is ObserverOutcomeStatus.AVAILABLE
    assert len(calls) == 4


@pytest.mark.parametrize(
    "value",
    [SAS, "?" + SAS, "sv=1&se=2&sp=rwl&sr=c&sig=x", "sv=1&se=2&sp=rl&sr=q&sig=x", "sv=1&se=2&sp=rl&sr=c&sig=x&unknown=y", "sv=1&se=2&sp=rl&sr=c&sig=x&sig=y", "sv=1&se=2&sp=rl&sr=c&sig=x%0A", "https://secret.example/?x=1"],
)
def test_blob_sas_is_strict(value: str) -> None:
    if value in {SAS, "?" + SAS}:
        assert blob_module._parse_sas(value).startswith("sv=")
    else:
        with pytest.raises(ValueError):
            blob_module._parse_sas(value)


@pytest.mark.parametrize(
    "payload",
    [b"\xef\xbb\xbf<EnumerationResults />", b"<!DOCTYPE EnumerationResults><EnumerationResults />", b"<EnumerationResults><Blobs><Blob></Blob></Blobs></EnumerationResults>"],
)
def test_blob_xml_and_path_boundaries(monkeypatch: pytest.MonkeyPatch, payload: bytes) -> None:
    envelope, outcome, _ = _run_fake(monkeypatch, [_Response(payload)])
    assert envelope.completeness is ObservationCompleteness.PARTIAL
    assert outcome.status is ObserverOutcomeStatus.INCONCLUSIVE
    escaped = _blob("cases/case-1/../escape.txt")
    envelope, outcome, _ = _run_fake(monkeypatch, [_Response(_list_xml([escaped]))])
    assert envelope.completeness is ObservationCompleteness.PARTIAL
    assert outcome.status is ObserverOutcomeStatus.INCONCLUSIVE


def test_blob_secret_stays_out_of_envelope_and_parent_environment(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    secret = "sv=secret&sp=rl&sr=c&sig=opaque"
    monkeypatch.setenv("BLOB_SAS", secret)
    invocation = blob_module.ObserverInvocation(spec=_spec(), correlation=CORRELATION, phase=ObservationPhase.BEFORE)
    envelope = blob_module._run_child(invocation, utc_now_us=lambda: 100)
    assert secret not in envelope.model_dump_json()
    captured: dict[str, Any] = {}

    class Process:
        returncode = 7

        def poll(self) -> int:
            return self.returncode

        def wait(self, timeout: float | None = None) -> int:
            return 0

    def fake_popen(command: list[str], **kwargs: Any) -> Process:
        captured["command"] = command
        captured["environment"] = kwargs["env"]
        return Process()

    monkeypatch.setattr(blob_module.subprocess, "Popen", fake_popen)
    result = blob_module.run_azure_blob_observer(
        _spec(), CORRELATION, ObservationPhase.BEFORE, attempt_dir=tmp_path / "env", parent_environ=runtime_identity_environment(tmp_path / "var", extra={"BLOB_SAS": secret, "UNRELATED_SECRET": "hidden", "PATH": "C:\\Windows"}), python_executable=sys.executable
    )
    assert result.envelope is None
    assert result.outcome.status is ObserverOutcomeStatus.EXECUTION_ERROR
    assert captured["environment"]["BLOB_SAS"] == secret
    assert "UNRELATED_SECRET" not in captured["environment"]
    assert secret not in " ".join(captured["command"])
    assert not list((tmp_path / "env").rglob("*observer*"))


def test_blob_parent_timeout_and_corrupt_output_are_bounded(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    class Process:
        returncode = None
        killed = False

        def wait(self, timeout: float | None = None) -> int:
            if self.killed:
                return -9
            raise subprocess.TimeoutExpired("blob", timeout)

        def poll(self) -> int | None:
            return -9 if self.killed else None

        def terminate(self) -> None:
            return None

        def kill(self) -> None:
            self.killed = True

    process = Process()
    monkeypatch.setattr(blob_module.subprocess, "Popen", lambda *args, **kwargs: process)
    result = blob_module.run_azure_blob_observer(_spec(page_size=1, max_pages=1, max_objects=1, max_attempts=1, timeout_us=400_000), CORRELATION, ObservationPhase.BEFORE, attempt_dir=tmp_path / "timeout", parent_environ=runtime_identity_environment(tmp_path / "var", extra={"BLOB_SAS": SAS}), python_executable=sys.executable)
    assert result.envelope is not None and result.envelope.completeness is ObservationCompleteness.TIMED_OUT
    assert result.outcome.status is ObserverOutcomeStatus.INCONCLUSIVE
    assert process.killed
    assert not list((tmp_path / "timeout").rglob("*observer*"))

    def corrupt_popen(command: list[str], **kwargs: Any) -> Process:
        output = Path(command[command.index("--output") + 1])

        class DoneProcess:
            returncode = 0

            def poll(self) -> int:
                return self.returncode

            def wait(self, timeout: float | None = None) -> int:
                output.write_bytes(b"{}")
                return 0

        return DoneProcess()

    monkeypatch.setattr(blob_module.subprocess, "Popen", corrupt_popen)
    result = blob_module.run_azure_blob_observer(_spec(), CORRELATION, ObservationPhase.BEFORE, attempt_dir=tmp_path / "corrupt", parent_environ=runtime_identity_environment(tmp_path / "var", extra={"BLOB_SAS": SAS}), python_executable=sys.executable)
    assert result.envelope is None
    assert result.outcome.status is ObserverOutcomeStatus.EXECUTION_ERROR
    assert not list((tmp_path / "corrupt").rglob("*observer*"))


def test_blob_process_entry_delegates_to_core(monkeypatch: pytest.MonkeyPatch) -> None:
    import product.backend.infra.observers.azure_blob as process_module

    monkeypatch.setattr(process_module, "child_main", lambda input_path, output_path: 9)
    monkeypatch.setattr(sys, "argv", ["azure_blob_observer_process", "--input", "input.json", "--output", "output.json"])
    assert process_module.main() == 9
