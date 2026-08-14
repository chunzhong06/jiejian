from __future__ import annotations

import argparse

from .sqlite_observer import child_main


def main() -> int:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    return child_main(args.input, args.output)


if __name__ == "__main__":
    raise SystemExit(main())
