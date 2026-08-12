# `python -B -m jiejian.recording_runner` 可执行入口。

from __future__ import annotations

import sys

from .execution import execute_recording_runner


def main() -> int:
    return execute_recording_runner(
        stdin=sys.stdin.buffer,
        stdout=sys.stdout.buffer,
        stderr=sys.stderr,
    )


if __name__ == "__main__":
    raise SystemExit(main())
