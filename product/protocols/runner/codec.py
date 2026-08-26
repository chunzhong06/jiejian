# Runner 严格 canonical、秘密扫描与 JSON 解析边界。

from __future__ import annotations

import json
import hashlib
from collections.abc import Sequence
from typing import Any, TypeAlias, TypeVar

from pydantic import ValidationError

from product.backend.core.errors import JiejianError

from .input import (
    EVIDENCE_MAX_BYTES,
    RUNNER_INPUT_MAX_BYTES,
    RUNNER_RESULT_MAX_BYTES,
    RunnerInput,
)
from .evidence import Evidence, _canonical_bytes, _jsonable
from .result import RunnerResult, _reject_secret_material

ProtocolDocument: TypeAlias = RunnerInput | RunnerResult | Evidence


ProtocolT = TypeVar("ProtocolT", RunnerInput, RunnerResult, Evidence)


def canonical_runner_json_bytes(document: ProtocolDocument, *, known_secrets: Sequence[str] = ()) -> bytes:
    if not isinstance(document, (RunnerInput, RunnerResult, Evidence)):
        raise TypeError("canonical JSON only accepts a Runner  document")
    if any(not isinstance(secret, str) for secret in known_secrets):
        raise TypeError("known_secrets must contain only strings")
    data = _jsonable(document)
    _reject_secret_material(data)
    for secret in known_secrets:
        if secret and secret in json.dumps(data, ensure_ascii=False, sort_keys=True):
            raise JiejianError("PROTOCOL_SECRET_EXPOSED", " protocol contains known secret material")
    encoded = _canonical_bytes(data)
    maximum = RUNNER_INPUT_MAX_BYTES if isinstance(document, RunnerInput) else RUNNER_RESULT_MAX_BYTES
    if isinstance(document, Evidence):
        maximum = EVIDENCE_MAX_BYTES
    if len(encoded) > maximum:
        raise JiejianError("PROTOCOL_TOO_LARGE", "Runner  document exceeds its size limit")
    return encoded


def canonical_runner_sha256(document: ProtocolDocument, *, known_secrets: Sequence[str] = ()) -> str:
    return hashlib.sha256(canonical_runner_json_bytes(document, known_secrets=known_secrets)).hexdigest()


def _reject_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(" JSON contains duplicate keys")
        result[key] = value
    return result


def _reject_nonfinite(value: str) -> None:
    raise ValueError(" JSON contains a non-finite number")


def _parse_(
    raw: bytes,
    model: type[ProtocolT],
    maximum: int,
    label: str,
    known_secrets: Sequence[str],
    *,
    expected_schema_version: str | None = None,
) -> ProtocolT:
    if not isinstance(raw, bytes):
        raise TypeError(" parser requires bytes")
    if len(raw) > maximum or raw.startswith(b"\xef\xbb\xbf"):
        raise JiejianError("PROTOCOL_INVALID", f"{label} is oversized or contains a BOM")
    try:
        parsed = json.loads(raw.decode("utf-8"), object_pairs_hook=_reject_pairs, parse_constant=_reject_nonfinite)
        if not isinstance(parsed, dict):
            raise ValueError(" root must be an object")
        if expected_schema_version is not None and parsed.get("schema_version") != expected_schema_version:
            raise ValueError(" schema_version is missing or unsupported")
        _reject_secret_material(parsed)
        if any(secret and secret in raw.decode("utf-8") for secret in known_secrets):
            raise JiejianError("PROTOCOL_SECRET_EXPOSED", f"{label} contains known secret material")
        return model.model_validate_json(raw)
    except JiejianError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError, ValidationError) as exc:
        raise JiejianError("PROTOCOL_INVALID", f"{label} is not a valid strict  document", details={"reason": type(exc).__name__}) from None


def parse_runner_input(raw: bytes, *, known_secrets: Sequence[str] = ()) -> RunnerInput:
    return _parse_(
        raw,
        RunnerInput,
        RUNNER_INPUT_MAX_BYTES,
        "Runner  input",
        known_secrets,
        expected_schema_version="1",
    )

def parse_runner_result(raw: bytes, *, known_secrets: Sequence[str] = ()) -> RunnerResult:
    return _parse_(
        raw,
        RunnerResult,
        RUNNER_RESULT_MAX_BYTES,
        "Runner  result",
        known_secrets,
        expected_schema_version="1",
    )


def parse_evidence(raw: bytes, *, known_secrets: Sequence[str] = ()) -> Evidence:
    return _parse_(
        raw,
        Evidence,
        EVIDENCE_MAX_BYTES,
        "Evidence ",
        known_secrets,
        expected_schema_version="1",
    )
