# 运行场景等待只重读状态，终态失败立即交还断言，超时不无限轮询。
from unittest.mock import Mock
import pytest
from tests.support.official import until
from scripts.quality.syntax import check

def test_terminal_failure_is_returned_without_replaying_an_operation():
    read=Mock(side_effect=['RUNNING','FAILED'])
    sleep=Mock()
    assert until(read,lambda value:value in {'SUCCEEDED','FAILED'},sleep=sleep)=='FAILED'
    assert read.call_count==2
    sleep.assert_called_once()

def test_polling_has_a_bounded_deadline():
    clock=[0.0]
    read=Mock(return_value='RUNNING')
    def advance(seconds):clock[0]+=seconds
    with pytest.raises(AssertionError,match='预算'):
        until(read,lambda value:value=='SUCCEEDED',seconds=.3,clock=lambda:clock[0],sleep=advance)
    assert read.call_count==2

def test_syntax_selection_does_not_import_or_execute_code(tmp_path):
    source=tmp_path/'example.py'
    source.write_text('raise RuntimeError("must not run")',encoding='utf-8')
    assert check(['example.py'],root=tmp_path)==1
    source.write_text('def broken(',encoding='utf-8')
    with pytest.raises(SyntaxError):check(['example.py'],root=tmp_path)

def test_syntax_selection_rejects_paths_outside_its_root(tmp_path):
    with pytest.raises(ValueError,match='越界'):check(['../outside.py'],root=tmp_path)
