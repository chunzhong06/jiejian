# `python -B -m jiejian.runner` 可执行入口。

from __future__ import annotations

import argparse
from pathlib import Path

from .execution import execute_runner_attempt


def main() -> int:
    parser = argparse.ArgumentParser(prog="python -m jiejian.runner")
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--staging", type=Path, required=True)
    arguments = parser.parse_args()
    return execute_runner_attempt(arguments.input, arguments.staging)


if __name__ == "__main__":
    raise SystemExit(main())
