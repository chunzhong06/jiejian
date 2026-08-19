from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from product.backend.infra.runtime.process_environment import minimal_process_environment


PROJECT_ROOT = Path(__file__).resolve().parents[5]


def test_runner_process_rejects_invalid_current_input(tmp_path: Path) -> None:
    input_path = tmp_path / "input.json"
    staging = tmp_path / "staging"
    input_path.write_text('{"schema_version":"2"}', encoding="utf-8")
    completed = subprocess.run(
        [
            sys.executable,
            "-B",
            "-m",
            "product.backend.infra.runtime.runner",
            "--input",
            str(input_path),
            "--staging",
            str(staging),
        ],
        cwd=PROJECT_ROOT,
        env=minimal_process_environment(os.environ),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=30,
        check=False,
    )
    assert completed.returncode == 64
    assert completed.stdout == b""
    assert completed.stderr == b""
    assert not (staging / "result.json").exists()
