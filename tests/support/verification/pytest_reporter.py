# pytest 的即时脱敏报告；保留 setup/call/teardown 区别和收集错误，不接管测试断言。
from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

from tests.support.verification.reporting import public_node, result_status, write_report

_state: dict = {}
_path: Path | None = None
_last_write = 0.0


def pytest_sessionstart(session):
    global _path, _state
    configured = os.environ.get("JIEJIAN_TEST_REPORT")
    _path = Path(configured) if configured else None
    _state = {"schema_version": "1", "engine": "pytest", "status": "RUNNING", "started_at": time.time(),
              "collected": 0, "deselected": 0, "collection_errors": [], "cases": []}
    _save()


def _save(force=True):
    global _last_write
    if _path is not None and (force or time.monotonic() - _last_write >= 2):
        write_report(_path, _state)
        _last_write = time.monotonic()


def pytest_collection_finish(session):
    _state["collected"] = len(session.items)
    _state["collected_nodes"] = [public_node(item.nodeid) for item in session.items]
    _save()


def pytest_deselected(items):
    _state["deselected"] += len(items)


def pytest_collectreport(report):
    if report.failed:
        _state["collection_errors"].append(public_node(report.nodeid))
        _save()


def pytest_runtest_logreport(report):
    entry = {"node": public_node(report.nodeid), "rerun": report.nodeid.split("[", 1)[0],
             "phase": report.when, "outcome": report.outcome, "seconds": round(report.duration, 4),
             "file": report.location[0], "line": report.location[1] + 1,
             "exception_type": getattr(report, "verification_exception_type", None)}
    _state["cases"].append(entry)
    if report.failed:
        print(f"\n[即时失败] {entry['node']} ({report.when})", flush=True)
    _save(force=report.failed)


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    report = outcome.get_result()
    if call.excinfo is not None:
        report.verification_exception_type = call.excinfo.type.__name__


def pytest_sessionfinish(session, exitstatus):
    failures = len(_state["collection_errors"]) + sum(c["outcome"] == "failed" for c in _state["cases"])
    skips = sum(c["outcome"] == "skipped" for c in _state["cases"])
    _state.update(status=result_status(failures=failures, collected=_state["collected"], skipped=skips,
                                      exit_code=int(exitstatus), collect_only=session.config.option.collectonly),
                  exit_code=int(exitstatus), failures=failures, skipped=skips,
                  seconds=round(time.time() - _state["started_at"], 4))
    _save()
