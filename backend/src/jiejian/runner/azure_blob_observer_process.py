# 包内专用 Azure Blob 只读观察器子进程入口，不是用户可见产品入口。

from __future__ import annotations

import argparse

from .blob_observer import child_main


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    arguments = parser.parse_args()
    return child_main(arguments.input, arguments.output)


if __name__ == "__main__":
    raise SystemExit(main())
