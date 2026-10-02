# 验证验收脚本的唯一命令入口。
from __future__ import annotations
import sys
from pathlib import Path
import pytest
from tests.acceptance.sample_test import driver as suite_driver
from tests.scripts._support_sample_test import ROOT

def test_sample_test_suite_keeps_no_argument_semantics_on_official(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[Path, Path]] = []
    monkeypatch.setattr(
        suite_driver.official,
        "run",
        lambda root, var_dir: calls.append((root, var_dir)),
    )

    suite_driver.run_suite(ROOT, tmp_path, "official")

    assert calls == [(ROOT, tmp_path)]

@pytest.mark.parametrize("arguments,expected", [((), "official")] + [(("--suite", name), name) for name in suite_driver.SUITES])
def test_sample_test_argument_parser_accepts_the_single_public_suite_form(tmp_path, monkeypatch, arguments, expected):
    observed = []
    monkeypatch.setattr(suite_driver, "run_suite", lambda _root, _var_dir, suite: observed.append(suite))
    monkeypatch.setattr(sys, "argv", [str(Path(suite_driver.__file__)), "--root", str(ROOT), "--var-dir", str(tmp_path), *arguments])
    assert suite_driver.main() == 0
    assert observed == [expected]


@pytest.mark.parametrize("status,exit_code,accepted", [("PASSED", 0, True), ("EMPTY", 0, False), ("INCOMPLETE", 0, False), ("PASSED", 1, False)])
def test_profile_requires_both_exit_and_complete_evidence(tmp_path, monkeypatch, status, exit_code, accepted):
    import json
    from types import SimpleNamespace
    from tests.acceptance.sample_test import profiles
    from tests.acceptance.sample_test.harness.state import SampleTestError
    calls = []
    def run(command, **kwargs):
        calls.append(command)
        report = Path(kwargs["env"]["JIEJIAN_TEST_REPORT"])
        report.parent.mkdir(parents=True)
        report.write_text(json.dumps({"schema_version": "1", "status": status}), encoding="utf-8")
        return SimpleNamespace(returncode=exit_code)
    monkeypatch.setattr(profiles.subprocess, "run", run)
    if accepted:
        profiles.run_profile(ROOT, tmp_path, "ordinary")
    else:
        with pytest.raises(SampleTestError, match="NOT_VERIFIED"):
            profiles.run_profile(ROOT, tmp_path, "ordinary")
    assert "test" in calls[0] and str(ROOT / "scripts/dev.ps1") in calls[0]
