# 验证 v3 请求资产的并发非覆盖、哈希绑定与旧格式拒绝。
import json
from concurrent.futures import ThreadPoolExecutor

import pytest

from product.backend.core.errors import JiejianError
from product.backend.infra.runtime.jobs.check_requests import CheckRequestStore
from product.protocols.execution_v3 import PersistedExecutionRequestV3
from tests.fixtures.check_plan import plan
from tests.fixtures.check_runtime import runtime_bundle


def frozen_request():
    payload = plan().model_dump(mode="json", exclude={"gaps"})
    for action in payload["actions"]:
        action.pop("gaps")
    payload.update(config_fingerprint="c" * 64, budget_fingerprint="d" * 64)
    return PersistedExecutionRequestV3.model_validate_json(json.dumps(payload))


def test_concurrent_identical_request_has_one_creator(tmp_path):
    store = CheckRequestStore(tmp_path)
    job_id = "job_" + "1" * 32
    request = frozen_request()
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: store.write(job_id, request), range(2)))
    assert sorted(created for _, created in results) == [False, True]
    assert results[0][0] == results[1][0]
    assert store.load(job_id, expected_hash=results[0][0]) == request


def test_conflicting_request_never_overwrites_original(tmp_path):
    store = CheckRequestStore(tmp_path)
    job_id = "job_" + "1" * 32
    request = frozen_request()
    digest, _ = store.write(job_id, request)
    changed = request.model_copy(update={"budget_fingerprint": "e" * 64})
    with pytest.raises(JiejianError):
        store.write(job_id, changed)
    assert store.load(job_id, expected_hash=digest) == request


def test_bundle_content_address_and_exact_orphan_cleanup(tmp_path):
    store = CheckRequestStore(tmp_path)
    job_id = "job_" + "1" * 32
    bundle = runtime_bundle()
    digest, created = store.write_bundle(job_id, bundle)
    assert created and store.load_bundle(job_id, expected_hash=digest) == bundle
    assert store.write_bundle(job_id, bundle) == (digest, False)
    store.remove_if_matches(job_id, "0" * 64)
    assert store.load_bundle(job_id, expected_hash=digest) == bundle
    store.remove_if_matches(job_id, "0" * 64, config_hash=digest)
    assert not store.path_for(job_id, config_hash=digest).exists()


def test_current_reader_rejects_old_format_and_tampering(tmp_path):
    import hashlib
    store = CheckRequestStore(tmp_path)
    job_id = "job_" + "1" * 32
    digest, _ = store.write(job_id, frozen_request())
    path = store.path_for(job_id)
    raw = path.read_bytes().replace(b'"schema_version":"3"', b'"schema_version":"2"')
    path.write_bytes(raw)
    with pytest.raises(JiejianError):
        store.load(job_id, expected_hash=digest)
    with pytest.raises(JiejianError) as caught:
        store.load(job_id, expected_hash=hashlib.sha256(raw).hexdigest())
    assert caught.value.code == "RUNNER_PROTOCOL_INVALID"


@pytest.mark.parametrize("job_id", ["../job", "job_bad", "C:/outside", "job_" + "g" * 32])
def test_asset_paths_reject_invalid_job_ids(tmp_path, job_id):
    with pytest.raises(JiejianError):
        CheckRequestStore(tmp_path).path_for(job_id)
