# GUI 启动只共用浏览器程序，验证持久配置隔离、失败回退与一次打开。
from pathlib import Path
import subprocess

import pytest

from product.backend.cli import gui_browser


@pytest.fixture
def browser(tmp_path: Path, monkeypatch):
    executable = tmp_path / "controlled chromium" / "chrome.exe"
    executable.parent.mkdir()
    executable.touch()
    monkeypatch.setenv("JIEJIAN_PLAYWRIGHT_EXECUTABLE", str(executable))
    calls, fallback = [], []

    class Process:
        closed = False
        def poll(self):
            return 0 if self.closed else None
        def wait(self, timeout):
            if self.closed: return 0
            raise subprocess.TimeoutExpired("chromium", timeout)

    monkeypatch.setattr(gui_browser, "spawn_managed_process", lambda args, **kw: calls.append((args, kw)) or Process())
    monkeypatch.setattr(gui_browser.webbrowser, "open", lambda url: fallback.append(url) or True)
    monkeypatch.setattr(gui_browser, "release_process_tree", lambda *args, **kwargs: None)
    monkeypatch.setattr(gui_browser, "terminate_process_tree", lambda process, **kwargs: setattr(process, "closed", True))
    monkeypatch.setattr(gui_browser, "_request_window_close", lambda process: setattr(process, "closed", True) or True)
    return executable, calls, fallback


def test_gui_reuses_executable_and_separate_persistent_profile(tmp_path, browser):
    executable, calls, fallback = browser
    var = tmp_path / "var"
    assert gui_browser.open_gui_browser("http://127.0.0.1:18766/", var, session=gui_browser.GuiBrowserSession())
    args, options = calls[0]
    assert args[0] == str(executable.resolve())
    assert f"--user-data-dir={var.resolve() / 'runtime' / 'gui-browser'}" in args
    assert "--app=http://127.0.0.1:18766/" in args
    assert "--disable-extensions" in args
    assert "--disable-infobars" in args
    assert not any("remote-debugging" in arg or "no-sandbox" in arg for arg in args)
    assert options["close_fds"] is True
    marker = var / "runtime" / "gui-browser" / "preference-marker"
    marker.write_text("retained", encoding="utf-8")
    assert gui_browser.open_gui_browser("http://127.0.0.1:18766/", var, session=gui_browser.GuiBrowserSession())
    assert marker.read_text(encoding="utf-8") == "retained"
    assert not fallback


@pytest.mark.parametrize("failure", ["missing", "spawn", "exited"])
def test_managed_failure_falls_back_once(tmp_path, browser, monkeypatch, failure):
    executable, _, fallback = browser
    if failure == "missing":
        executable.unlink()
    elif failure == "spawn":
        def fail(*_, **__):
            raise OSError("cannot launch")
        monkeypatch.setattr(gui_browser, "spawn_managed_process", fail)
    else:
        monkeypatch.setattr(gui_browser, "spawn_managed_process", lambda *_, **__: type("P", (), {"wait": lambda self, timeout: 1})())
    assert gui_browser.open_gui_browser("http://127.0.0.1:8765/", tmp_path / "var", session=gui_browser.GuiBrowserSession())
    assert fallback == ["http://127.0.0.1:8765/"]


def test_system_option_does_not_touch_gui_profile(tmp_path, browser):
    _, calls, fallback = browser
    assert gui_browser.open_gui_browser("http://127.0.0.1:8765/", tmp_path / "var", session=gui_browser.GuiBrowserSession(), system_browser=True)
    assert not calls
    assert not (tmp_path / "var").exists()
    assert len(fallback) == 1


def test_existing_profile_handoff_is_not_treated_as_failure(tmp_path, browser, monkeypatch):
    _, _, fallback = browser
    monkeypatch.setattr(gui_browser, "spawn_managed_process", lambda *_, **__: type("P", (), {"wait": lambda self, timeout: 0})())
    assert gui_browser.open_gui_browser("http://127.0.0.1:8765/", tmp_path, session=gui_browser.GuiBrowserSession())
    assert not fallback


@pytest.mark.parametrize("url", ["https://example.com/", "http://127.0.0.1.evil/", "http://user@127.0.0.1/"])
def test_gui_launcher_rejects_nonlocal_or_credential_urls(tmp_path, browser, url):
    _, calls, fallback = browser
    assert not gui_browser.open_gui_browser(url, tmp_path, session=gui_browser.GuiBrowserSession())
    assert not calls and not fallback


def test_shutdown_closes_only_owned_browser_and_keeps_profile(tmp_path, browser, monkeypatch):
    _, _, fallback = browser
    session = gui_browser.GuiBrowserSession()
    released = []
    monkeypatch.setattr(gui_browser, "release_process_tree", lambda process, **kwargs: released.append(process))
    var = tmp_path / "var"
    assert gui_browser.open_gui_browser("http://127.0.0.1:8765/", var, session=session)
    marker = var / "runtime/gui-browser/preference-marker"
    marker.write_text("retained", encoding="utf-8")
    session.close(); session.close()
    assert len(released) == 1 and released[0].closed
    assert marker.read_text(encoding="utf-8") == "retained" and not fallback


def test_late_launch_is_closed_after_session_shutdown(tmp_path, browser):
    session = gui_browser.GuiBrowserSession(); session.close()
    assert not gui_browser.open_gui_browser("http://127.0.0.1:8765/", tmp_path, session=session)
    assert not browser[1] and not browser[2]


def test_unresponsive_owned_window_uses_bounded_tree_cleanup(tmp_path, browser, monkeypatch):
    session = gui_browser.GuiBrowserSession(); terminated = []
    monkeypatch.setattr(gui_browser, "_request_window_close", lambda process: False)
    monkeypatch.setattr(gui_browser, "terminate_process_tree", lambda process, **kwargs: terminated.append((process, kwargs)))
    assert gui_browser.open_gui_browser("http://127.0.0.1:8765/", tmp_path, session=session)
    session.close()
    assert len(terminated) == 1 and terminated[0][1] == {"timeout": 3.0}


@pytest.mark.parametrize("mode", ["system", "handoff"])
def test_shutdown_never_closes_a_browser_without_owned_launch(tmp_path, browser, monkeypatch, mode):
    session = gui_browser.GuiBrowserSession()
    closes = []
    monkeypatch.setattr(gui_browser, "_request_window_close", lambda process: closes.append(process) or True)
    if mode == "handoff":
        monkeypatch.setattr(gui_browser, "spawn_managed_process", lambda *args, **kw: type("Handoff", (), {"wait": lambda self, timeout: 0})())
    assert gui_browser.open_gui_browser("http://127.0.0.1:8765/", tmp_path, session=session, system_browser=mode == "system")
    session.close()
    assert not closes


def test_shutdown_between_spawn_and_adoption_closes_the_new_owned_tree(tmp_path, browser, monkeypatch):
    session = gui_browser.GuiBrowserSession()
    spawn = gui_browser.spawn_managed_process
    processes = []
    def racing_spawn(*args, **kwargs):
        process = spawn(*args, **kwargs)
        wait = process.wait
        def race(timeout):
            if timeout == 0.6: session.close()
            return wait(timeout)
        process.wait = race
        processes.append(process)
        return process
    monkeypatch.setattr(gui_browser, "spawn_managed_process", racing_spawn)
    assert not gui_browser.open_gui_browser("http://127.0.0.1:8765/", tmp_path, session=session)
    assert len(processes) == 1 and processes[0].closed
    assert not browser[2]
