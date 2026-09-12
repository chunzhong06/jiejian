# 以固定模块启动当前 CHECK Runner，仅接受受控 input/staging 路径。
import argparse
import os
from pathlib import Path

from product.backend.infra.runtime.check_runner.executor import execute_check_attempt


def main() -> int:
    parser = argparse.ArgumentParser(prog="python -m product.backend.infra.runtime.check_runner")
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--staging", type=Path, required=True)
    arguments = parser.parse_args()
    return execute_check_attempt(arguments.input, arguments.staging, environ=os.environ)


if __name__ == "__main__":
    raise SystemExit(main())
