# 验证验收脚本的唯一命令入口。
from __future__ import annotations
import sys
from pathlib import Path
import pytest
from scripts.dev.sample_test import driver as suite_driver
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

def test_sample_test_argument_parser_accepts_the_single_public_suite_form(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed: list[str] = []
    monkeypatch.setattr(
        suite_driver,
        "run_suite",
        lambda _root, _var_dir, suite: observed.append(suite),
    )
    for arguments, expected in (
        ((), "official"),
        (("--suite", "official"), "official"),
        (("--suite", "validation"), "validation"),
        (("--suite", "competition"), "competition"),
        (("--suite", "all"), "all"),
    ):
        monkeypatch.setattr(
            sys,
            "argv",
            [
                str(Path(suite_driver.__file__)),
                "--root",
                str(ROOT),
                "--var-dir",
                str(tmp_path),
                *arguments,
            ],
        )
        assert suite_driver.main() == 0
    assert observed == [
        "official",
        "official",
        "validation",
        "competition",
        "all",
    ]
