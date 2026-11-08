"""短期秘密不回退平台持久化；匿名管道的来源与格式失败不暴露输入。"""
import json
import os
import sys
from threading import Thread

import pytest

from product.backend.domain.errors import JiejianError
from product.backend.infrastructure.secrets.session import EphemeralSecretStore


REFERENCE='cred:jiejian/test-identity/orders/member/bearer'


def test_session_expires_without_renewal_or_persistent_fallback():
    now=[0]
    store=EphemeralSecretStore({REFERENCE:'canary-session-value'},lifetime_seconds=60,clock=lambda:now[0])
    assert store.configured(REFERENCE) and store.read(REFERENCE)=='canary-session-value'
    now[0]=59;store.write(REFERENCE,'new-session-value')
    now[0]=60
    assert not store.configured(REFERENCE) and store.read(REFERENCE) is None
    with pytest.raises(JiejianError) as error:store.write(REFERENCE,'later-value')
    assert error.value.code=='SECRET_STORE_UNAVAILABLE'
    assert 'canary' not in repr(store) and 'new-session-value' not in str(error.value)


def test_close_and_reference_validation_do_not_expose_secret_values():
    store=EphemeralSecretStore({REFERENCE:'canary-private-value'})
    with pytest.raises(ValueError):store.read('cred:other/unknown')
    with pytest.raises(ValueError):store.write(REFERENCE,'bad\x00value')
    store.close()
    assert store.read(REFERENCE) is None and not store.configured(None)
    assert 'canary-private-value' not in repr(store)


@pytest.mark.skipif(sys.platform!='linux',reason='匿名管道FD来源核对只在Linux实际执行')
def test_anonymous_pipe_is_consumed_once_without_retaining_the_descriptor():
    reader,writer=os.pipe()
    payload=json.dumps(dict(document_type='jiejian.private-secret-session',schema_version='1',values={REFERENCE:'pipe-canary'})).encode()
    def send():
        os.write(writer,payload);os.close(writer)
    thread=Thread(target=send);thread.start()
    store=EphemeralSecretStore.from_fd(reader);thread.join(2)
    assert not thread.is_alive() and store.read(REFERENCE)=='pipe-canary'
    with pytest.raises(OSError):os.fstat(reader)
    store.close()


@pytest.mark.skipif(sys.platform!='linux',reason='FD来源核对只在Linux实际执行')
def test_regular_file_and_unknown_private_format_are_rejected_without_input_in_error(tmp_path):
    path=tmp_path/'private-input';path.write_text('not-an-injection-channel',encoding='utf-8')
    descriptor=os.open(path,os.O_RDONLY)
    with pytest.raises(JiejianError) as rejected:EphemeralSecretStore.from_fd(descriptor)
    assert 'not-an-injection-channel' not in str(rejected.value)
    reader,writer=os.pipe()
    os.write(writer,b'{"document_type":"jiejian.private-secret-session","schema_version":"future-canary","values":{}}');os.close(writer)
    with pytest.raises(JiejianError) as rejected:EphemeralSecretStore.from_fd(reader)
    assert 'future-canary' not in str(rejected.value)


pytestmark=[pytest.mark.level3]
