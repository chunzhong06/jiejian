# 验证历史请求读取先确认字节身份且将非对象根收口为稳定协议错误。
import hashlib
import pytest
from product.backend.core.errors import JiejianError
from product.backend.infra.recording.request_store import RecordingRequestStore
from tests.fixtures.recording import runner_request


def test_history_nonobject_root_fails_with_stable_protocol_error(tmp_path):
    store = RecordingRequestStore(tmp_path)
    job_id = "job_"+"1"*32
    store.write(job_id, runner_request("rec_"+"1"*32))
    raw = b"[]"
    store.path_for(job_id).write_bytes(raw)
    with pytest.raises(JiejianError) as error:
        store.load_history(job_id, expected_hash=hashlib.sha256(raw).hexdigest())
    assert error.value.code == "RECORD_PROTOCOL_INVALID"
