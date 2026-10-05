# 验证 GUI 重开快捷键的输入隔离、失败重试、停止竞态及与当前服务地址的接线。
from threading import Event
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from typer.testing import CliRunner

from product.backend.cli import gui_console
from product.backend.cli.app import app
from product.backend.cli.commands import system


def test_console_reopen_is_serial_and_ignores_key_repeat():
    stopped, messages, calls, clock = Event(), [], [], [0.0]
    keys = iter([(10.0, 'G'), (10.1, 'g'), (11.0, 'x'), (13.0, 'g')])

    def read():
        item = next(keys, None)
        if item is None:
            stopped.set()
            return None
        clock[0], key = item
        return key

    gui_console.run_gui_console(open_browser=lambda: calls.append(clock[0]) or True,
        stopped=stopped, is_stopping=lambda: False, emit=messages.append,
        read_key=read, monotonic=lambda: clock[0])
    assert calls == [10.0, 13.0]
    assert messages == ['controls-ready', 'opened', 'opened']


def test_console_open_failure_keeps_retry_available():
    stopped, messages, clock = Event(), [], [0.0]
    opened = Mock(side_effect=[OSError('unavailable'), True])

    def read():
        clock[0] += 3
        if opened.call_count == 2:
            stopped.set()
            return None
        return 'g'

    gui_console.run_gui_console(open_browser=opened, stopped=stopped,
        is_stopping=lambda: False, emit=messages.append, read_key=read,
        monotonic=lambda: clock[0])
    assert messages == ['controls-ready', 'open-failed', 'opened']


def test_console_shutdown_between_key_and_open_prevents_launch():
    stopped, opened = Event(), Mock()

    def read():
        stopped.set()
        return 'g'

    gui_console.run_gui_console(open_browser=opened, stopped=stopped,
        is_stopping=lambda: False, emit=lambda _: None, read_key=read)
    opened.assert_not_called()


def test_redirected_input_is_not_consumed(monkeypatch):
    stdin = Mock()
    stdin.isatty.return_value = False
    monkeypatch.setattr(gui_console.sys, 'stdin', stdin)
    emitted, opened = Mock(), Mock()
    gui_console.run_gui_console(open_browser=opened, stopped=Event(),
        is_stopping=lambda: False, emit=emitted)
    stdin.read.assert_not_called()
    emitted.assert_not_called()
    opened.assert_not_called()


def test_lost_console_stops_only_shortcuts():
    opened, messages = Mock(), []
    gui_console.run_gui_console(open_browser=opened, stopped=Event(),
        is_stopping=lambda: False, emit=messages.append,
        read_key=Mock(side_effect=OSError('console closed')))
    assert messages == ['controls-ready', 'input-unavailable']
    opened.assert_not_called()


@pytest.mark.parametrize('browser', ['managed', 'system'])
def test_serve_reopens_same_url_profile_and_browser_without_new_server(tmp_path, monkeypatch, browser):
    from product.backend.cli import gui_browser
    frontend = tmp_path / 'frontend'
    frontend.mkdir()
    (frontend / 'index.html').write_text('<html>fixture</html>', encoding='utf-8')
    var_dir = tmp_path / 'var'
    finished, launches, servers = Event(), [], []
    monkeypatch.setattr(system, 'runtime_settings', lambda _: SimpleNamespace(var_dir=var_dir, log_level='INFO'))
    monkeypatch.setattr('product.backend.api.create_app', lambda *_args, **_kwargs: object())
    monkeypatch.setattr('uvicorn.Config', lambda *_args, **_kwargs: object())

    class Server:
        should_exit = False

        def __init__(self, _config):
            servers.append(self)

        def run(self):
            assert finished.wait(2), 'GUI controls were not connected after readiness'

    monkeypatch.setattr('uvicorn.Server', Server)
    monkeypatch.setattr(gui_browser, 'open_gui_browser', lambda url, root, **kw: launches.append((url, root, kw)) or True)

    def ready(*_args, **kwargs):
        kwargs['open_browser']('http://127.0.0.1:18766/')
        return system.ServeReadinessStatus.READY_BROWSER_OPENED

    def console(**kwargs):
        try:
            kwargs['open_browser']()
        finally:
            finished.set()

    monkeypatch.setattr(system, '_wait_for_ready', ready)
    monkeypatch.setattr(gui_console, 'run_gui_console', console)
    result = CliRunner().invoke(app, ['serve', '--open', '--port', '18766', '--browser', browser, '--frontend-dir', str(frontend)])
    assert result.exit_code == 0, result.output
    assert len(servers) == 1
    assert [(url, path, kw['system_browser']) for url, path, kw in launches] == [('http://127.0.0.1:18766/', var_dir, browser == 'system')] * 2
    assert launches[0][2]['session'] is launches[1][2]['session']
    assert launches[0][2]['session'].closed is True
