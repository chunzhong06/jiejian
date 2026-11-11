# 以固定模块启动当前 CHECK Runner，仅接受受控 input/staging 路径。
import argparse
import os
from pathlib import Path
from contextlib import nullcontext
from product.backend.infrastructure.runtime.workflow_timing import workflow_timings

from product.backend.infrastructure.runtime.check_runner.executor import execute_check_attempt


def main() -> int:
    parser = argparse.ArgumentParser(prog="python -m product.backend.infrastructure.runtime.check_runner")
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--staging", type=Path, required=True)
    arguments = parser.parse_args()
    scope = workflow_timings() if os.environ.get('JIEJIAN_WORKFLOW_TIMING') == '1' else nullcontext()
    with scope as timings:
        try:
            return execute_check_attempt(arguments.input, arguments.staging, environ=os.environ)
        finally:
            if timings is not None:
                timings.save(Path(os.environ['JIEJIAN_VAR_DIR']))


if __name__ == "__main__":
    raise SystemExit(main())
