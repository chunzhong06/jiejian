# sample-test 唯一 Python 入口：解析 suite，并把执行分派给 official 或 validation。

"""保持 dev.ps1 sample-test 的公共参数合同和退出码。"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


if __package__ in {None, ""}:
    # PowerShell 直接执行本文件时只在入口补仓库根；子系统内部一律使用包导入。
    project_root = Path(__file__).resolve().parents[3]
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))
    __package__ = "scripts.dev.sample_test"

from . import official
from .validation import run_validation_suite


SUITES = ("official", "validation", "competition", "all")


def run_suite(root: Path, var_dir: Path, suite: str) -> None:
    """保留 official 原链，并把 validation/competition 纳入同一公共入口。"""

    if suite == "official":
        official.run(root, var_dir)
        return
    if suite == "validation":
        run_validation_suite(root, var_dir, repetitions=1)
        return
    if suite == "competition":
        run_validation_suite(root, var_dir, repetitions=3)
        return
    if suite == "all":
        official_dir = var_dir / "official"
        validation_dir = var_dir / "validation"
        official_dir.mkdir(parents=True)
        validation_dir.mkdir(parents=True)
        official.run(root, official_dir)
        run_validation_suite(root, validation_dir, repetitions=1)
        return
    raise official.SampleTestError("SAMPLE_TEST_SUITE_INVALID")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the official sample delivery validation.")
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--var-dir", required=True, type=Path)
    parser.add_argument("--suite", choices=SUITES, default="official")
    arguments = parser.parse_args()
    try:
        run_suite(arguments.root, arguments.var_dir, arguments.suite)
    except Exception as exc:
        code, summary = official._failure_identity(exc)
        print(f"sample-test failed: {code}: {summary}", file=sys.stderr, flush=True)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
