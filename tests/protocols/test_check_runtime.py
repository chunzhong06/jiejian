# 验证冻结检查配置的严格 reader、秘密边界、有限预算和独立导入闭包。
import hashlib
import json
import os
import subprocess
import sys

import pytest

from product.protocols.check_runtime import (
    CheckRuntimeProtocolError, canonical_check_runtime_bytes, check_runtime_fingerprint, parse_check_runtime,
)
from tests.fixtures.check_runtime import runtime_bundle


def test_five_auxiliary_sources_are_supported_but_six_are_rejected():
    from pydantic import ValidationError
    from product.protocols.check_runtime import CheckProofConfig
    proof = runtime_bundle().actions[0].proofs[0].model_dump(mode="json")
    proof["auxiliary_sources"] = [dict(observer_id=f"aux-{index}", descriptor_fingerprint="a" * 64,
        observation_identity_id=proof["observation_identity_id"], level="SUPPORTING",
        source_label="独立辅助来源", source_location=f"observer/source-{index}") for index in range(5)]
    assert len(CheckProofConfig.model_validate_json(json.dumps(proof)).auxiliary_sources) == 5
    proof["auxiliary_sources"].append(proof["auxiliary_sources"][-1] | {"observer_id": "aux-six"})
    with pytest.raises(ValidationError) as error:
        CheckProofConfig.model_validate_json(json.dumps(proof))
    assert any(item["type"] == "too_long" for item in error.value.errors(include_input=False))


def test_runtime_is_independent_of_backend_and_legacy_contracts():
    result = subprocess.run([sys.executable, "-B", "-c",
        "import sys; import product.protocols.check_runtime; assert not any(n.startswith('product.backend') for n in sys.modules)"],
        env=os.environ | {"PYTHONDONTWRITEBYTECODE": "1"}, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_runtime_canonical_roundtrip_and_all_config_changes_are_bound():
    bundle = runtime_bundle()
    raw = canonical_check_runtime_bytes(bundle)
    assert parse_check_runtime(raw) == bundle
    assert check_runtime_fingerprint(bundle) == hashlib.sha256(raw).hexdigest()
    changed = bundle.model_copy(update={"identities": (bundle.identities[0].model_copy(update={"verification": None}),)})
    assert check_runtime_fingerprint(changed) != check_runtime_fingerprint(bundle)
    assert bundle.budget.fingerprint() != bundle.budget.model_copy(update={"max_requests": 65}).fingerprint()


@pytest.mark.parametrize("mutate", [
    lambda raw: b"\xef\xbb\xbf" + raw,
    lambda raw: raw + b"\n",
    lambda raw: raw.replace(b'"schema_version":"1"', b'"schema_version":"2"', 1),
    lambda raw: raw.replace(b'"project_id":"test"', b'"project_id":"test","project_id":"test"'),
    lambda raw: raw.replace(b'"max_parallel_cases":1', b'"max_parallel_cases":2'),
    lambda raw: raw.replace(b'"max_requests":64', b'"max_requests":501'),
    lambda raw: raw.replace(b'"timeout_seconds":5.0', b'"timeout_seconds":NaN'),
    lambda raw: raw[:-1] + b',"extra":true}',
    lambda raw: raw.replace(b'Test identity', b'Bearer forbidden-value'),
    lambda raw: raw.replace(b'provider/object', b'C:/private/object'),
    lambda raw: raw.replace(b'provider/object', b'provider/../object'),
    lambda raw: b" " * 1_048_577,
])
def test_runtime_rejects_invalid_or_unsafe_bytes(mutate):
    with pytest.raises(CheckRuntimeProtocolError) as caught:
        parse_check_runtime(mutate(canonical_check_runtime_bytes(runtime_bundle())))
    assert str(caught.value) == "执行快照格式无效"


@pytest.mark.parametrize("path", ["/objects/prefix-{resource}", "/objects/{resource}.json", "/objects/fixed"])
def test_presence_proof_rejects_partial_or_unused_resource_slot(path):
    payload = runtime_bundle().model_dump(mode="json")
    payload["actions"][0]["proofs"][0]["request"]["path"] = path
    with pytest.raises(CheckRuntimeProtocolError):
        parse_check_runtime(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode())


def test_presence_proof_accepts_one_whole_query_value():
    payload = runtime_bundle().model_dump(mode="json")
    request = payload["actions"][0]["proofs"][0]["request"]
    request.update(path="/objects", query=[dict(name="resource", slot_id="resource")])
    request["input_slots"][0]["consumer"] = "QUERY"
    from product.protocols.check_runtime import CheckRuntimeBundle
    bundle = CheckRuntimeBundle.model_validate_json(json.dumps(payload))
    assert parse_check_runtime(canonical_check_runtime_bytes(bundle)) == bundle


@pytest.mark.parametrize("location", ["proof", "identity"])
def test_readonly_proof_and_identity_requests_cannot_have_body(location):
    payload = runtime_bundle().model_dump(mode="json")
    request = (payload["actions"][0]["proofs"][0]["request"] if location == "proof"
        else payload["identities"][0]["verification"]["request"])
    request["body"] = dict(kind="JSON", value={"write": True})
    with pytest.raises(CheckRuntimeProtocolError):
        parse_check_runtime(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode())
