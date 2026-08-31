# sample-test 唯一 Python 入口：解析 suite，并把执行分派给 official 或 validation。

"""保持 dev.ps1 sample-test 的公共参数合同和退出码。"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from uuid import uuid4


if __package__ in {None, ""}:
    # PowerShell 直接执行本文件时只在入口补仓库根；子系统内部一律使用包导入。
    project_root = Path(__file__).resolve().parents[3]
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))
    __package__ = "scripts.dev.sample_test"

from . import official
from .validation import build_presentation_summary, run_validation_suite


SUITES = ("official", "validation", "competition", "all")


def run_suite(
    root: Path,
    var_dir: Path,
    suite: str,
    *,
    publish_summary: Path | None = None,
) -> None:
    """保留 official 原链，并把 validation/competition 纳入同一公共入口。"""

    if suite == "official":
        official.run(root, var_dir)
        return
    if suite == "validation":
        summary = run_validation_suite(root, var_dir, repetitions=1)
        _publish_summary(publish_summary, summary)
        return
    if suite == "competition":
        summary = run_validation_suite(root, var_dir, repetitions=3)
        _publish_summary(publish_summary, summary)
        return
    if suite == "all":
        official_dir = var_dir / "official"
        validation_dir = var_dir / "validation"
        official_dir.mkdir(parents=True)
        validation_dir.mkdir(parents=True)
        official.run(root, official_dir)
        summary = run_validation_suite(root, validation_dir, repetitions=1)
        _publish_summary(publish_summary, summary)
        return
    raise official.SampleTestError("SAMPLE_TEST_SUITE_INVALID")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the official sample delivery validation.")
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--var-dir", required=True, type=Path)
    parser.add_argument("--suite", choices=SUITES, default="official")
    parser.add_argument("--publish-summary", type=Path)
    arguments = parser.parse_args()
    try:
        if arguments.publish_summary is None:
            run_suite(arguments.root, arguments.var_dir, arguments.suite)
        else:
            run_suite(
                arguments.root,
                arguments.var_dir,
                arguments.suite,
                publish_summary=arguments.publish_summary,
            )
    except Exception as exc:
        code, summary = official._failure_identity(exc)
        print(f"sample-test failed: {code}: {summary}", file=sys.stderr, flush=True)
        return 1
    return 0


def _publish_summary(path: Path | None, summary: dict[str, object]) -> None:
    """验收成功后原子替换稳定汇总；失败运行继续保留上一份已接受结果。"""

    if path is None:
        return
    payload = build_presentation_summary(summary)
    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f".{uuid4().hex}.tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )
    os.replace(temporary, path)


if __name__ == "__main__":
    raise SystemExit(main())
